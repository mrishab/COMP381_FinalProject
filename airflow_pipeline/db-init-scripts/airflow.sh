#!/bin/bash
set -e

# Idempotently create Airflow role if it does not already exist
USER_EXISTS=$(psql -d "$POSTGRES_DB" -U "$POSTGRES_USER" -tAc "SELECT 1 FROM pg_roles WHERE rolname='$AIRFLOW_DB_USER'")
if [ "$USER_EXISTS" != "1" ]; then
    psql -d "$POSTGRES_DB" -U "$POSTGRES_USER" -c "CREATE USER $AIRFLOW_DB_USER PASSWORD '$AIRFLOW_DB_PASS';"
else
    psql -d "$POSTGRES_DB" -U "$POSTGRES_USER" -c "ALTER USER $AIRFLOW_DB_USER WITH PASSWORD '$AIRFLOW_DB_PASS';"
fi

# Idempotently create Airflow database if it does not already exist
DB_EXISTS=$(psql -d "$POSTGRES_DB" -U "$POSTGRES_USER" -tAc "SELECT 1 FROM pg_database WHERE datname='$AIRFLOW_DB_NAME'")
if [ "$DB_EXISTS" != "1" ]; then
    psql -d "$POSTGRES_DB" -U "$POSTGRES_USER" -c "CREATE DATABASE $AIRFLOW_DB_NAME WITH OWNER $AIRFLOW_DB_USER;"
fi

psql -d "$POSTGRES_DB" -U "$POSTGRES_USER" -c "GRANT ALL PRIVILEGES ON DATABASE $AIRFLOW_DB_NAME TO $AIRFLOW_DB_USER;"
psql -d "$POSTGRES_DB" -U "$POSTGRES_USER" -c "ALTER ROLE $AIRFLOW_DB_USER WITH CREATEROLE;"
