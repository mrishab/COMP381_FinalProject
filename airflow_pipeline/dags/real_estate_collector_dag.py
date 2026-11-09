"""Airflow DAG: Daily Real Estate Collector for Greater Vancouver and Fraser Valley.

Collects listings from Realtor.ca, enriches with BC Assessment data,
denormalizes past sales history into 3-sale columns, handles Cloudflare
via FlareSolverr, enforces rate limits, and persists to SQLite & CSV.
"""

import datetime
import logging
import os
import sys
from typing import Any, Dict, List, Optional

# Ensure dags directory and pipeline root are in Python path for local package imports
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
for p in (CURRENT_DIR, PARENT_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator
except ImportError:
    # Graceful fallback for non-Airflow test environments
    class DAG:  # type: ignore
        _current_dag: Optional["DAG"] = None
        def __init__(self, dag_id: str, **kwargs: Any):
            self.dag_id = dag_id
            self.kwargs = kwargs
            self.tasks: List[Any] = []
            self.schedule_interval = kwargs.get("schedule") or kwargs.get("schedule_interval")
            self.catchup = kwargs.get("catchup", True)
            self.max_active_runs = kwargs.get("max_active_runs", 16)
            self.tags = kwargs.get("tags", [])
        def __enter__(self) -> "DAG":
            DAG._current_dag = self
            return self
        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            DAG._current_dag = None

    class PythonOperator:  # type: ignore
        def __init__(self, task_id: str, python_callable: Any, op_kwargs: Any = None, **kwargs: Any):
            self.task_id = task_id
            self.python_callable = python_callable
            self.op_kwargs = op_kwargs or {}
            self.downstream_list: List["PythonOperator"] = []
            self.upstream_list: List["PythonOperator"] = []
            if DAG._current_dag is not None:
                DAG._current_dag.tasks.append(self)
        def __rshift__(self, other: Any) -> Any:
            targets = other if isinstance(other, list) else [other]
            for t in targets:
                if t not in self.downstream_list:
                    self.downstream_list.append(t)
                if self not in t.upstream_list:
                    t.upstream_list.append(self)
            return other

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
DEFAULT_MAX_PAGES = int(os.getenv("MAX_PAGES_PER_CITY", "5"))

default_args = {
    "owner": "real_estate_pipeline",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 3,
    "retry_delay": datetime.timedelta(minutes=5),
    "start_date": datetime.datetime(2026, 1, 1),
}


def task_init_storage(**kwargs: Any) -> Dict[str, Any]:
    """Initializes SQLite schema, WAL mode, and verifies storage permissions."""
    storage = DBStorage(db_path=SQLITE_PATH)
    logger.info(f"Database initialized successfully at {SQLITE_PATH}")
    return {"status": "initialized", "db_path": SQLITE_PATH}


def task_collect_and_enrich_city(city_name: str, max_pages: int = 5, **kwargs: Any) -> Dict[str, Any]:
    """Collects listings for a specific city, enriches with BC Assessment, and upserts."""
    logger.info(f"Starting daily fresh inventory collection for municipality: {city_name}")

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

        try:
            record = DataTransformer.transform_listing(raw_listing, assessment=assessment_data)
            transformed_records.append(record)
        except Exception as e:
            logger.error(f"Error transforming listing in {city_name}: {e}", exc_info=True)
            continue

        # Batch upsert every 25 records to conserve memory
        if len(transformed_records) >= 25:
            storage.upsert_listings(transformed_records)
            transformed_records.clear()

    # Flush remainder
    if transformed_records:
        storage.upsert_listings(transformed_records)

    logger.info(f"Finished {city_name}: {scraped_count} listings processed.")
    return {"city": city_name, "listings_processed": scraped_count}


def task_export_csv(**kwargs: Any) -> Dict[str, Any]:
    """Exports SQLite listings to CSV with full headers."""
    storage = DBStorage(db_path=SQLITE_PATH)
    rows_exported = storage.export_to_csv(csv_path=CSV_PATH)
    logger.info(f"Exported {rows_exported} listings to {CSV_PATH}")
    return {"rows_exported": rows_exported, "csv_path": CSV_PATH}


def task_pipeline_summary(**kwargs: Any) -> Dict[str, Any]:
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
    schedule="@daily",
    catchup=False,
    max_active_runs=1,
    tags=["real_estate", "gva", "fraser_valley", "realtor", "bcassessment"],
) as dag:

    init_storage = PythonOperator(
        task_id="init_storage",
        python_callable=task_init_storage,
    )

    # City list covering Greater Vancouver and Fraser Valley
    env_cities = os.getenv("CITIES_TO_SCRAPE")
    if env_cities:
        primary_cities = [c.strip() for c in env_cities.split(",") if c.strip()]
    else:
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
            "Langley",
            "Port Coquitlam",
            "Port Moody",
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
            op_kwargs={"city_name": city, "max_pages": DEFAULT_MAX_PAGES},
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
