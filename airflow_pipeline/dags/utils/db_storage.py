"""Database Storage and CSV Exporter for Real Estate Pipeline.

Manages SQLite storage, table creation, indexing, atomic upserts,
and CSV exports.
"""

import csv
import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS real_estate_listings (
    mls_number TEXT PRIMARY KEY,
    realtor_id TEXT,
    url TEXT,
    region TEXT,
    city TEXT,
    province TEXT,
    unit_number TEXT,
    street_number TEXT,
    street_name TEXT,
    postal_code TEXT,
    full_address TEXT,
    latitude REAL,
    longitude REAL,
    listing_price REAL,
    date_listed TEXT,
    days_on_market INTEGER,
    transaction_type TEXT,
    property_type TEXT,
    bedrooms INTEGER,
    bathrooms INTEGER,
    half_bathrooms INTEGER,
    stories REAL,
    year_built INTEGER,
    square_footage REAL,
    lot_size_sqft REAL,
    acreage REAL,
    parking_spaces INTEGER,
    garage INTEGER,
    heating TEXT,
    cooling TEXT,
    basement TEXT,
    exterior TEXT,
    roof TEXT,
    flooring TEXT,
    sewer TEXT,
    pool INTEGER,
    fireplace INTEGER,
    waterfront INTEGER,
    garden INTEGER,
    balcony INTEGER,
    bc_assessment_id TEXT,
    bc_total_assessed_value REAL,
    bc_land_value REAL,
    bc_improvement_value REAL,
    bc_previous_year_value REAL,
    bc_assessment_year INTEGER,
    bc_property_class TEXT,
    sale_price_1 REAL,
    sale_date_1 TEXT,
    sale_price_2 REAL,
    sale_date_2 TEXT,
    sale_price_3 REAL,
    sale_date_3 TEXT,
    sales_history_json TEXT,
    scraped_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_listings_city ON real_estate_listings(city);
CREATE INDEX IF NOT EXISTS idx_listings_region ON real_estate_listings(region);
CREATE INDEX IF NOT EXISTS idx_listings_price ON real_estate_listings(listing_price);
CREATE INDEX IF NOT EXISTS idx_listings_date ON real_estate_listings(date_listed);
"""


class DBStorage:
    """Handles SQLite persistence and CSV file output for real estate listings."""

    def __init__(self, db_path: str = "/opt/airflow/data/real_estate.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """Initializes tables and indices."""
        with self.get_connection() as conn:
            conn.executescript(CREATE_TABLE_SQL)
            conn.commit()

    def upsert_listings(self, listings: List[Dict[str, Any]]) -> int:
        """Upserts a batch of listing records. Returns number of rows inserted/updated."""
        if not listings:
            return 0

        columns = [
            "mls_number", "realtor_id", "url", "region", "city", "province",
            "unit_number", "street_number", "street_name", "postal_code", "full_address",
            "latitude", "longitude", "listing_price", "date_listed", "days_on_market",
            "transaction_type", "property_type", "bedrooms", "bathrooms", "half_bathrooms",
            "stories", "year_built", "square_footage", "lot_size_sqft", "acreage",
            "parking_spaces", "garage", "heating", "cooling", "basement", "exterior",
            "roof", "flooring", "sewer", "pool", "fireplace", "waterfront",
            "garden", "balcony", "bc_assessment_id", "bc_total_assessed_value",
            "bc_land_value", "bc_improvement_value", "bc_previous_year_value",
            "bc_assessment_year", "bc_property_class", "sale_price_1", "sale_date_1",
            "sale_price_2", "sale_date_2", "sale_price_3", "sale_date_3", "sales_history_json", "scraped_at"
        ]

        placeholders = ", ".join(["?"] * len(columns))
        col_names = ", ".join(columns)
        update_assignments = ", ".join(
            [f"{col} = excluded.{col}" for col in columns if col != "mls_number"]
        )

        upsert_sql = f"""
        INSERT INTO real_estate_listings ({col_names})
        VALUES ({placeholders})
        ON CONFLICT(mls_number) DO UPDATE SET
        {update_assignments};
        """

        rows = []
        for item in listings:
            rows.append(tuple(item.get(c) for c in columns))

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(upsert_sql, rows)
            conn.commit()
            return cursor.rowcount

    def export_to_csv(self, csv_path: str = "/opt/airflow/data/real_estate_listings.csv") -> int:
        """Exports all database listings to a CSV file. Returns total exported rows."""
        os.makedirs(os.path.dirname(os.path.abspath(csv_path)), exist_ok=True)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM real_estate_listings ORDER BY date_listed DESC")
            rows = cursor.fetchall()

            if not rows:
                return 0

            headers = [desc[0] for desc in cursor.description]
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for row in rows:
                    writer.writerow(list(row))

            return len(rows)

    def get_summary_stats(self) -> Dict[str, Any]:
        """Calculates high-level dataset metrics."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM real_estate_listings")
            total_count = cursor.fetchone()[0]

            cursor.execute(
                "SELECT city, COUNT(*), AVG(listing_price) FROM real_estate_listings GROUP BY city ORDER BY COUNT(*) DESC"
            )
            by_city = [
                {"city": row[0], "count": row[1], "avg_price": round(row[2], 2) if row[2] else 0}
                for row in cursor.fetchall()
            ]

            cursor.execute(
                "SELECT COUNT(*) FROM real_estate_listings WHERE sale_price_1 IS NOT NULL"
            )
            with_sale_history = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM real_estate_listings WHERE bc_total_assessed_value IS NOT NULL"
            )
            with_bc_assessment = cursor.fetchone()[0]

            return {
                "total_listings": total_count,
                "with_sale_history": with_sale_history,
                "with_bc_assessment": with_bc_assessment,
                "city_breakdown": by_city,
            }
