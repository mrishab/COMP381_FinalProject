# Project 1: Airflow Real Estate Data Pipeline (Realtor.ca & BC Assessment)

Daily Apache Airflow DAG orchestrated data ingestion pipeline covering all municipalities in the Greater Vancouver Area and Fraser Valley. Integrates Realtor.ca active listings with BC Assessment valuation roll data and historical transfer records.

## Architecture

- **Airflow 2.11.2**: Webserver, Scheduler, Setup, and Postgres metadata store. Configured with `LocalExecutor` for parallel task scheduling with health check dependencies.
- **FlareSolverr v3.5.2 Proxy**: Dockerized proxy that resolves Cloudflare turnstile and anti-bot challenges.
- **Rate Limiter & Backoff**: Randomized jitter delay (`2.0s ± 1.0s`) and exponential backoff (`3.0 * 2^attempt`) on HTTP 429, 500, 502, and 503.
- **Atomic Data Model**: Normalizes addresses, dates, unit specifications, utilities, and tax values into single-attribute columns.
- **Denormalized Sales History**: Captures the last 3 historical sale transactions (`sale_price_1`, `sale_date_1`, `sale_price_2`, `sale_date_2`, `sale_price_3`, `sale_date_3`), plus full overflow JSON.
- **Dual Storage**: ACID SQLite database (`real_estate.db`) with WAL mode (`PRAGMA journal_mode=WAL`), busy timeouts, and indexes (`mls_number`, `city`, `region`, `listing_price`, `date_listed`), plus automatic daily CSV export (`real_estate_listings.csv`).

## Geographic Coverage

### Greater Vancouver Area
- Vancouver, Surrey, Burnaby, Richmond, Coquitlam, New Westminster
- West Vancouver, North Vancouver, Delta, White Rock, Langley (Langley City & Township of Langley)
- Port Coquitlam, Port Moody, Maple Ridge, Pitt Meadows
- Bowen Island, Lions Bay, Anmore, Belcarra

### Fraser Valley
- Abbotsford, Mission, Chilliwack, Aldergrove, Hope, Kent, Harrison Hot Springs

## Directory Layout

```
airflow_pipeline/
├── docker-compose.yml              # Multi-container stack (Airflow, Postgres, FlareSolverr)
├── .env.example                    # Environment template
├── .env                            # Active configuration
├── requirements.txt                # Python dependencies
├── db-init-scripts/
│   └── airflow.sh                  # Idempotent Postgres role and schema initialization
├── dags/
│   ├── __init__.py
│   ├── real_estate_collector_dag.py # Daily Airflow DAG
│   └── utils/
│       ├── __init__.py
│       ├── flaresolverr_client.py   # Cloudflare solver & rate limiter
│       ├── realtor_scraper.py      # Bounding boxes and Realtor.ca search
│       ├── bcassessment_scraper.py # BC Assessment search and valuation extractor
│       ├── data_transformer.py     # Schema normalizer and 3-sale denormalizer
│       └── db_storage.py           # SQLite upsert, WAL mode, lock retry, and CSV export
└── tests/
    └── test_airflow_pipeline.py    # 23 comprehensive unit and integration tests
```

## Running with Docker Compose

```bash
cd /workspace/airflow_pipeline
cp .env.example .env
docker-compose up -d
```

- Access Airflow Webserver at `http://localhost:8080` (credentials: `admin` / `AdminPassword123!`).
- Access FlareSolverr at `http://localhost:8191`.

## Running Pipeline Tests

```bash
PYTHONPATH=/workspace/airflow_pipeline python3 -m pytest /workspace/airflow_pipeline/tests/test_airflow_pipeline.py -v
```
