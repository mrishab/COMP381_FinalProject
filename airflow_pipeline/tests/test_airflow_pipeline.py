"""Comprehensive Unit & Integration Tests for Project 1: Airflow Real Estate Pipeline."""

import os
import sqlite3
import tempfile
import time
from unittest.mock import MagicMock, patch
import pytest

from dags.utils.flaresolverr_client import FlareSolverrClient
from dags.utils.realtor_scraper import RealtorScraper, COVERED_REGIONS
from dags.utils.bcassessment_scraper import BCAssessmentScraper
from dags.utils.data_transformer import DataTransformer
from dags.utils.db_storage import DBStorage


class TestFlareSolverrClient:
    """Tests for FlareSolverrClient rate limiter and exponential backoff."""

    def test_rate_limiter_enforces_delay(self):
        client = FlareSolverrClient(rate_limit_delay=0.1, jitter_range=0.0)
        t0 = time.time()
        client._apply_rate_limit()
        client._apply_rate_limit()
        elapsed = time.time() - t0
        assert elapsed >= 0.09, f"Elapsed {elapsed}s was less than minimum rate limit delay"

    @patch("requests.Session.post")
    def test_exponential_backoff_on_429(self, mock_post):
        # First 2 calls return 429, 3rd call succeeds
        mock_resp_429 = MagicMock()
        mock_resp_429.status_code = 429
        mock_resp_429.text = "Too Many Requests"

        mock_resp_ok = MagicMock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.text = '{"success": true}'
        mock_resp_ok.cookies = []
        mock_resp_ok.headers = {}
        mock_resp_ok.url = "http://test.com"

        mock_post.side_effect = [mock_resp_429, mock_resp_429, mock_resp_ok]

        client = FlareSolverrClient(
            rate_limit_delay=0.01,
            jitter_range=0.0,
            max_retries=3,
            base_backoff=0.02,
        )
        res = client.fetch("http://test.com", method="POST", data={"k": "v"})
        assert res["status_code"] == 200
        assert mock_post.call_count == 3

    @patch("requests.Session.post")
    def test_flaresolverr_form_encoding(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "ok",
            "solution": {"status": 200, "response": '{"ok": true}'}
        }
        mock_post.return_value = mock_resp

        client = FlareSolverrClient(flaresolverr_url="http://mock:8191/v1")
        # Test form urlencoding
        res = client.request_via_flaresolverr(
            "https://api.realtor.ca/test",
            method="POST",
            post_data={"CultureId": 1, "PriceMin": 500000},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert res["status_code"] == 200
        called_payload = mock_post.call_args[1]["json"]
        assert "CultureId=1&PriceMin=500000" in called_payload["postData"] or "PriceMin=500000&CultureId=1" in called_payload["postData"]


class TestRealtorScraper:
    """Tests for Realtor scraper regions and parsing."""

    def test_covered_regions_coverage(self):
        expected_gva = [
            "Vancouver", "Surrey", "Burnaby", "Richmond", "Coquitlam",
            "New Westminster", "West Vancouver", "North Vancouver", "Delta",
            "White Rock", "Maple Ridge", "Port Coquitlam", "Port Moody"
        ]
        expected_fv = ["Abbotsford", "Mission", "Chilliwack", "Aldergrove", "Hope"]

        for city in expected_gva + expected_fv:
            assert city in COVERED_REGIONS, f"Missing region definition for {city}"
            bounds = COVERED_REGIONS[city]["bounds"]
            assert len(bounds) == 4
            assert bounds[0] < bounds[1], f"Lat min >= lat max for {city}"
            assert bounds[2] < bounds[3], f"Lon min >= lon max for {city}"

    def test_price_and_numeric_parsing(self):
        scraper = RealtorScraper()
        assert scraper.parse_price("$1,450,000") == 1450000.0
        assert scraper.parse_price("$899,900.50") == 899900.50
        assert scraper.parse_price(None) is None
        assert scraper.parse_numeric("2,450 sqft") == 2450.0
        assert scraper.parse_numeric("3 Beds") == 3.0

    def test_date_parsing(self):
        scraper = RealtorScraper()
        # ASP.NET ms timestamp: /Date(1710000000000)/ is 2024-03-09
        parsed = scraper.parse_ms_date("/Date(1710000000000)/")
        assert parsed == "2024-03-09"
        assert scraper.parse_ms_date("2026-05-15T00:00:00Z") == "2026-05-15"


class TestBCAssessmentScraper:
    """Tests for BC Assessment scraper formatting and parsing."""

    def test_clean_address_query(self):
        scraper = BCAssessmentScraper()
        assert scraper.clean_address_query("#304 - 1250 Robson St") == "1250 Robson St"
        assert scraper.clean_address_query("1250 Robson St, Vancouver, BC") == "1250 Robson St Vancouver BC"

    def test_parse_detailed_assessment(self):
        scraper = BCAssessmentScraper()
        data = {
            "Id": "01-081-300-010",
            "TotalAssessedValue": "$1,850,000",
            "AssessedLandValue": "$1,350,000",
            "AssessedImprovementValue": "$500,000",
            "PreviousYearTotalAssessedValue": "$1,720,000",
            "AssessmentYear": 2026,
            "PropertyClass": "01 - Residential",
            "SalesHistory": [
                {"SalePrice": "$1,600,000", "SaleDate": "2023-08-15"},
                {"SalePrice": "$1,200,000", "SaleDate": "2019-04-10"},
            ],
        }
        res = scraper._parse_detailed(data)
        assert res["bc_total_assessed_value"] == 1850000.0
        assert res["bc_land_value"] == 1350000.0
        assert res["bc_improvement_value"] == 500000.0
        assert res["bc_previous_year_value"] == 1720000.0
        assert res["bc_assessment_year"] == 2026
        assert len(res["bc_sales_history"]) == 2


class TestDataTransformer:
    """Tests for address parsing, sales denormalization, and listing transformation."""

    def test_parse_address_parts(self):
        addr1 = "#402 - 1100 Cambie St|Vancouver, British Columbia V6B5L7"
        parts1 = DataTransformer.parse_address_parts(addr1)
        assert parts1["unit_number"] == "402"
        assert parts1["street_number"] == "1100"
        assert parts1["street_name"] == "Cambie St"
        assert parts1["postal_code"] == "V6B5L7"

        addr2 = "7890 120th Street, Surrey, BC V3W 3N1"
        parts2 = DataTransformer.parse_address_parts(addr2)
        assert parts2["street_number"] == "7890"
        assert "120th Street" in parts2["street_name"]
        assert parts2["postal_code"] == "V3W3N1"

    def test_denormalize_sale_history_last_3_sales(self):
        sales = [
            {"price": 500000, "date": "2015-01-10"},
            {"price": 750000, "date": "2018-06-20"},
            {"price": 950000, "date": "2021-09-15"},
            {"price": 1100000, "date": "2023-11-01"},
        ]
        denorm = DataTransformer.denormalize_sale_history(sales)
        # Should contain top 3 newest sales
        assert denorm["sale_price_1"] == 1100000.0
        assert denorm["sale_date_1"] == "2023-11-01"
        assert denorm["sale_price_2"] == 950000.0
        assert denorm["sale_date_2"] == "2021-09-15"
        assert denorm["sale_price_3"] == 750000.0
        assert denorm["sale_date_3"] == "2018-06-20"

    def test_transform_listing_full_record(self):
        raw_listing = {
            "MlsNumber": "R2891234",
            "Id": "12345678",
            "RelativeURLEn": "/real-estate/12345678/101-200-main-st-vancouver",
            "Property": {
                "Price": "$1,250,000",
                "Type": "Apartment",
                "Address": {
                    "AddressText": "#101 - 200 Main St|Vancouver, BC V6A 2S7",
                    "City": "Vancouver",
                    "Latitude": "49.2827",
                    "Longitude": "-123.1000",
                },
                "ParkingSpaceTotal": "1",
            },
            "Building": {
                "Bedrooms": "2",
                "BathroomTotal": "2",
                "SizeInterior": "950 sqft",
                "ConstructedDate": "2018",
                "HeatingType": "Baseboard",
                "CoolingType": "Central Air",
            },
            "PublicRemarks": "Stunning condo with private balcony, fireplace, and mountain view.",
            "InsertedDateUTC": "/Date(1715000000000)/",
            "_region": "Greater Vancouver",
            "_queried_city": "Vancouver",
        }

        assessment = {
            "bc_assessment_id": "01-081-999-001",
            "bc_total_assessed_value": 1180000.0,
            "bc_land_value": 600000.0,
            "bc_improvement_value": 580000.0,
            "bc_previous_year_value": 1100000.0,
            "bc_assessment_year": 2026,
            "bc_property_class": "01 - Residential",
            "bc_sales_history": [
                {"price": 980000.0, "date": "2020-03-01"},
            ],
        }

        row = DataTransformer.transform_listing(raw_listing, assessment=assessment)
        assert row["mls_number"] == "R2891234"
        assert row["listing_price"] == 1250000.0
        assert row["unit_number"] == "101"
        assert row["street_number"] == "200"
        assert row["bedrooms"] == 2
        assert row["bathrooms"] == 2
        assert row["square_footage"] == 950.0
        assert row["balcony"] == 1
        assert row["fireplace"] == 1
        assert row["bc_total_assessed_value"] == 1180000.0
        assert row["sale_price_1"] == 980000.0
        assert row["sale_date_1"] == "2020-03-01"
        assert "sales_history_json" in row

    def test_parse_date_formats_and_disambiguation(self):
        # Canadian DD/MM/YYYY disambiguation
        assert DataTransformer.parse_date("25/08/2023") == "2023-08-25"
        # Standard MM/DD/YYYY
        assert DataTransformer.parse_date("04/28/2024") == "2024-04-28"
        # YYYY/MM/DD
        assert DataTransformer.parse_date("2025/11/05") == "2025-11-05"
        # ISO
        assert DataTransformer.parse_date("2026-03-15") == "2026-03-15"

    def test_mls_number_collision_prevention(self):
        listing1 = {"Property": {"Address": {"AddressText": "100 A St"}, "Price": 500000}}
        listing2 = {"Property": {"Address": {"AddressText": "200 B St"}, "Price": 750000}}
        row1 = DataTransformer.transform_listing(listing1)
        row2 = DataTransformer.transform_listing(listing2)
        assert row1["mls_number"].startswith("GEN_")
        assert row2["mls_number"].startswith("GEN_")
        assert row1["mls_number"] != row2["mls_number"]


class TestDBStorage:
    """Tests SQLite persistence, indexing, upserts, and CSV exports."""

    def test_db_init_and_upsert(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp_db:
            storage = DBStorage(db_path=tmp_db.name)

            listing = {
                "mls_number": "TEST001",
                "city": "Vancouver",
                "region": "Greater Vancouver",
                "listing_price": 999000.0,
                "date_listed": "2026-04-01",
                "bedrooms": 3,
                "bathrooms": 2,
                "square_footage": 1200.0,
                "sale_price_1": 850000.0,
                "sale_date_1": "2021-05-10",
            }

            # First insert
            inserted = storage.upsert_listings([listing])
            assert inserted == 1

            # Update with new price (UPSERT test)
            listing["listing_price"] = 949000.0
            storage.upsert_listings([listing])

            with storage.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT listing_price FROM real_estate_listings WHERE mls_number = 'TEST001'")
                val = cursor.fetchone()[0]
                assert val == 949000.0

            # Export CSV
            with tempfile.NamedTemporaryFile(suffix=".csv") as tmp_csv:
                rows_exp = storage.export_to_csv(tmp_csv.name)
                assert rows_exp == 1
                with open(tmp_csv.name, "r") as f:
                    content = f.read()
                    assert "TEST001" in content
                    assert "949000" in content

            # Summary stats
            stats = storage.get_summary_stats()
            assert stats["total_listings"] == 1
            assert stats["with_sale_history"] == 1
            assert len(stats["city_breakdown"]) == 1
            assert stats["city_breakdown"][0]["city"] == "Vancouver"
