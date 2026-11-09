"""Airflow DAG: Daily Real Estate Collector for Greater Vancouver and Fraser Valley.

Collects listings from Realtor.ca, enriches with BC Assessment data,
denormalizes past sales history into 3-sale columns, handles Cloudflare
via FlareSolverr, enforces rate limits, and persists to SQLite & CSV.
"""

import datetime
import logging
import os
import sys

# Ensure dags directory is in Python path for local package imports
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from airflow import DAG
from airflow.operators.python import PythonOperator

try:
    from utils.flaresolverr_client import FlareSolverrClient
    from utils.realtor_scraper import RealtorScraper, COVERED_REGIONS
    from utils.bcassessment_scraper import BCAssessmentScraper
    from utils.data_transformer import DataTransformer
    from utils.db_storage import DBStorage
except ImportError:
    from dags.utils.flaresolverr_client import FlareSolverrClient
    from dags.utils.realtor_scraper import RealtorScraper, COVERED_REGIONS
    from dags.utils.bcassessment_scraper import BCAssessmentScraper
    from dags.utils.data_transformer import DataTransformer
    from dags.utils.db_storage import DBStorage

logger = logging.getLogger(__name__)

SQLITE_PATH = os.getenv("SQLITE_DB_PATH", "/opt/airflow/data/real_estate.db")
CSV_PATH = os.getenv("CSV_OUTPUT_PATH", "/opt/airflow/data/real_estate_listings.csv")
FLARESOLVERR_URL = os.getenv("FLARESOLVERR_URL", "http://flaresolverr:8191/v1")
RATE_LIMIT_DELAY = float(os.getenv("RATE_LIMIT_DELAY_SECONDS", "2.0"))
MAX_RETRIES = int(os.getenv("MAX_BACKOFF_RETRIES", "5"))

default_args = {
    "owner": "real_estate_pipeline",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 3,
    "retry_delay": datetime.timedelta(minutes=5),
    "start_date": datetime.datetime(2026, 1, 1),
}


def task_init_storage(**kwargs):
    """Initializes SQLite schema and verifies output directory permissions."""
    storage = DBStorage(db_path=SQLITE_PATH)
    logger.info(f"Database initialized successfully at {SQLITE_PATH}")
    return {"status": "initialized", "db_path": SQLITE_PATH}


def task_collect_and_enrich_city(city_name: str, max_pages: int = 5, **kwargs):
    """Collects listings for a specific city, enriches with BC Assessment, and upserts."""
    logger.info(f"Starting collection for municipality: {city_name}")

    client = FlareSolverrClient(
        flaresolverr_url=FLARESOLVERR_URL,
        rate_limit_delay=RATE_LIMIT_DELAY,
        max_retries=MAX_RETRIES,
    )
    realtor = RealtorScraper(client=client)
    bca = BCAssessmentScraper(client=client)
    storage = DBStorage(db_path=SQLITE_PATH)

    transformed_records = []
    scraped_count = 0

    for raw_listing in realtor.fetch_city_listings(city_name, max_pages=max_pages):
        scraped_count += 1
        addr_text = (
            raw_listing.get("Property", {}).get("Address", {}).get("AddressText", "")
        )

        assessment_data = None
        if addr_text:
            try:
                assessment_data = bca.fetch_assessment_for_address(addr_text, city=city_name)
            except Exception as e:
                logger.warning(f"Could not fetch BC assessment for '{addr_text}': {e}")

        record = DataTransformer.transform_listing(raw_listing, assessment=assessment_data)
        transformed_records.append(record)

        # Batch upsert every 25 records to conserve memory
        if len(transformed_records) >= 25:
            storage.upsert_listings(transformed_records)
            transformed_records.clear()

    # Flush remainder
    if transformed_records:
        storage.upsert_listings(transformed_records)

    logger.info(f"Finished {city_name}: {scraped_count} listings processed.")
    return {"city": city_name, "listings_processed": scraped_count}


def task_export_csv(**kwargs):
    """Exports SQLite listings to CSV."""
    storage = DBStorage(db_path=SQLITE_PATH)
    rows_exported = storage.export_to_csv(csv_path=CSV_PATH)
    logger.info(f"Exported {rows_exported} listings to {CSV_PATH}")
    return {"rows_exported": rows_exported, "csv_path": CSV_PATH}


def task_pipeline_summary(**kwargs):
    """Logs summary metrics of total listings, coverage, and prices."""
    storage = DBStorage(db_path=SQLITE_PATH)
    stats = storage.get_summary_stats()
    logger.info("================ PIPELINE RUN SUMMARY ================")
    logger.info(f"Total Listings Stored: {stats['total_listings']}")
    logger.info(f"Listings With Sale History: {stats['with_sale_history']}")
    logger.info(f"Listings With BC Assessment: {stats['with_bc_assessment']}")
    for c in stats["city_breakdown"][:10]:
        logger.info(f"  {c['city']}: {c['count']} listings, Avg Price: ${c['avg_price']:,.2f}")
    logger.info("======================================================")
    return stats


# Define DAG
with DAG(
    dag_id="daily_real_estate_collector",
    default_args=default_args,
    description="Daily ingestion of Greater Vancouver and Fraser Valley real estate data",
    schedule_interval="@daily",
    catchup=False,
    max_active_runs=1,
    tags=["real_estate", "gva", "fraser_valley", "realtor", "bcassessment"],
) as dag:

    init_storage = PythonOperator(
        task_id="init_storage",
        python_callable=task_init_storage,
    )

    # City list categorized into Greater Vancouver and Fraser Valley
    primary_cities = [
        "Vancouver",
        "Surrey",
        "Burnaby",
        "Richmond",
        "Coquitlam",
        "New Westminster",
        "West Vancouver",
        "North Vancouver",
        "Delta",
        "White Rock",
        "Township of Langley",
        "Maple Ridge",
        "Abbotsford",
        "Mission",
        "Chilliwack",
        "Aldergrove",
    ]

    city_tasks = []
    for city in primary_cities:
        safe_city_id = city.lower().replace(" ", "_")
        city_task = PythonOperator(
            task_id=f"collect_{safe_city_id}",
            python_callable=task_collect_and_enrich_city,
            op_kwargs={"city_name": city, "max_pages": 3},
        )
        init_storage >> city_task
        city_tasks.append(city_task)

    export_csv = PythonOperator(
        task_id="export_csv_dataset",
        python_callable=task_export_csv,
    )

    pipeline_summary = PythonOperator(
        task_id="pipeline_summary_report",
        python_callable=task_pipeline_summary,
    )

    for ct in city_tasks:
        ct >> export_csv

    export_csv >> pipeline_summary
