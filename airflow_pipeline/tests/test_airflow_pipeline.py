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
from dags.utils.db_storage import DBStorage, ALL_COLUMNS
from dags.real_estate_collector_dag import (
    dag,
    task_init_storage,
    task_export_csv,
    task_pipeline_summary,
    task_collect_and_enrich_city,
)


class TestFlareSolverrClient:
    """Tests for FlareSolverrClient rate limiter, exponential backoff, and header handling."""

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
        res = client.request_via_flaresolverr(
            "https://api.realtor.ca/test",
            method="POST",
            post_data={"CultureId": 1, "PriceMin": 500000},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert res["status_code"] == 200
        called_payload = mock_post.call_args[1]["json"]
        assert "CultureId=1&PriceMin=500000" in called_payload["postData"] or "PriceMin=500000&CultureId=1" in called_payload["postData"]

    @patch("requests.Session.post")
    def test_flaresolverr_case_insensitive_content_type(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "ok",
            "solution": {"status": 200, "response": '{"ok": true}'}
        }
        mock_post.return_value = mock_resp

        client = FlareSolverrClient(flaresolverr_url="http://mock:8191/v1")
        res = client.request_via_flaresolverr(
            "https://api.realtor.ca/test",
            method="POST",
            post_data={"query": "test"},
            headers={"content-type": "application/json"}
        )
        assert res["status_code"] == 200
        called_payload = mock_post.call_args[1]["json"]
        assert called_payload["postData"] == '{"query": "test"}'

    @patch("requests.Session.get")
    def test_flaresolverr_backoff_on_503(self, mock_get):
        mock_resp_503 = MagicMock()
        mock_resp_503.status_code = 503
        mock_resp_503.text = "Service Unavailable"
        mock_resp_503.headers = {}

        mock_resp_ok = MagicMock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.text = '{"success": true}'
        mock_resp_ok.cookies = []
        mock_resp_ok.headers = {}
        mock_resp_ok.url = "http://test.com"

        mock_get.side_effect = [mock_resp_503, mock_resp_ok]

        client = FlareSolverrClient(
            rate_limit_delay=0.01,
            jitter_range=0.0,
            max_retries=2,
            base_backoff=0.01,
        )
        res = client.fetch("http://test.com", method="GET")
        assert res["status_code"] == 200
        assert mock_get.call_count == 2

    def test_flaresolverr_extract_json_html_wrapper(self):
        # FlareSolverr / Chromium wrapping JSON in HTML <pre> or <body>
        html_pre = '<html><head></head><body><pre style="word-wrap: break-word;">{"Results": [{"Id": "991"}]}</pre></body></html>'
        data1 = FlareSolverrClient.extract_json_response(html_pre)
        assert data1 == {"Results": [{"Id": "991"}]}

        html_body = '<html><body>{"status": "ok", "value": 123}</body></html>'
        data2 = FlareSolverrClient.extract_json_response(html_body)
        assert data2 == {"status": "ok", "value": 123}

        # Plain string JSON
        data3 = FlareSolverrClient.extract_json_response('{"direct": true}')
        assert data3 == {"direct": True}


class TestRealtorScraper:
    """Tests for Realtor scraper regions, parsing, and pagination."""

    def test_covered_regions_coverage(self):
        expected_gva = [
            "Vancouver", "Surrey", "Burnaby", "Richmond", "Coquitlam",
            "New Westminster", "West Vancouver", "North Vancouver", "Delta",
            "White Rock", "Maple Ridge", "Port Coquitlam", "Port Moody", "Langley"
        ]
        expected_fv = ["Abbotsford", "Mission", "Chilliwack", "Aldergrove", "Hope"]

        for city in expected_gva + expected_fv:
            assert city in COVERED_REGIONS, f"Missing region definition for {city}"
            bounds = COVERED_REGIONS[city]["bounds"]
            assert len(bounds) == 4
            assert bounds[0] < bounds[1], f"Lat min >= lat max for {city}"
            assert bounds[2] < bounds[3], f"Lon min >= lon max for {city}"

    def test_get_region_config_case_insensitive_and_aliases(self):
        cfg1 = RealtorScraper.get_region_config("vancouver")
        assert cfg1 is not None
        assert cfg1["region"] == "Greater Vancouver"

        cfg2 = RealtorScraper.get_region_config("Langley")
        assert cfg2 is not None

        cfg3 = RealtorScraper.get_region_config("chilliwack")
        assert cfg3 is not None
        assert cfg3["region"] == "Fraser Valley"

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
        # ASP.NET with timezone offset e.g. -0700 (Pacific Time)
        assert scraper.parse_ms_date("/Date(1710000000000-0700)/") == "2024-03-09"
        assert scraper.parse_ms_date("2026-05-15T00:00:00Z") == "2026-05-15"

    def test_realtor_scraper_paging_string_and_fresh_cutoff(self):
        # Test that string TotalPages does not raise TypeError
        mock_client = MagicMock()
        mock_client.fetch.return_value = {
            "status_code": 200,
            "response": '{"Results": [{"Id": "1", "InsertedDateUTC": "2026-05-10T00:00:00Z"}], "Paging": {"TotalPages": "1"}}'
        }
        scraper = RealtorScraper(client=mock_client)
        listings = list(scraper.fetch_city_listings("Vancouver", max_pages=1))
        assert len(listings) == 1
        assert listings[0]["Id"] == "1"


class TestBCAssessmentScraper:
    """Tests for BC Assessment scraper formatting and parsing."""

    def test_clean_address_query(self):
        scraper = BCAssessmentScraper()
        assert scraper.clean_address_query("#304 - 1250 Robson St") == "1250 Robson St"
        assert scraper.clean_address_query("1250 Robson St, Vancouver, BC") == "1250 Robson St Vancouver BC"
        # Test pipe delimiter replacement from Realtor.ca addresses
        assert scraper.clean_address_query("1250 Robson St|Vancouver, BC") == "1250 Robson St Vancouver BC"
        # Test unit prefixes and postal code cleaning
        assert scraper.clean_address_query("Unit 12B, 456 Elm Ave|Richmond, BC V6X 1A1") == "456 Elm Ave Richmond BC"
        assert scraper.clean_address_query("Apt 402, 1100 Cambie St, Vancouver, BC") == "1100 Cambie St Vancouver BC"

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

        # Unit without dash
        addr3 = "Unit 12B, 456 Elm Ave|Richmond, BC V6X 1A1"
        parts3 = DataTransformer.parse_address_parts(addr3)
        assert parts3["unit_number"] == "12B"
        assert parts3["street_number"] == "456"
        assert "Elm Ave" in parts3["street_name"]

        # Trailing unit notations
        addr4 = "1234 Main St Apt 4B, Vancouver, BC"
        parts4 = DataTransformer.parse_address_parts(addr4)
        assert parts4["unit_number"] == "4B"
        assert parts4["street_number"] == "1234"
        assert parts4["street_name"] == "Main St"

        addr5 = "1234 Main St #301"
        parts5 = DataTransformer.parse_address_parts(addr5)
        assert parts5["unit_number"] == "301"
        assert parts5["street_number"] == "1234"
        assert parts5["street_name"] == "Main St"

        # None input safe handling
        parts_none = DataTransformer.parse_address_parts(None)
        assert parts_none["full_address"] == ""
        assert parts_none["unit_number"] is None

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
        assert row["latitude"] == 49.2827
        assert row["longitude"] == -123.1000
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
        # Textual date format: "15 Jan 2026" and "May 15, 2026"
        assert DataTransformer.parse_date("15 Jan 2026") == "2026-01-15"
        assert DataTransformer.parse_date("May 15, 2026") == "2026-05-15"
        # ASP.NET date with timezone offset
        assert DataTransformer.parse_date("/Date(1710000000000-0700)/") == "2024-03-09"

    def test_parse_numeric_ranges_and_plus_sums(self):
        # "3 + 1" bedrooms (3 main + 1 basement)
        assert DataTransformer.parse_numeric("3 + 1") == 4.0
        assert DataTransformer.parse_int("3 + 1") == 4
        # Range averaging: "1,200 - 1,400 sqft" -> 1300.0
        assert DataTransformer.parse_numeric("1,200 - 1,400 sqft") == 1300.0
        # Range with plus suffix: "1,200 - 1,400+ sqft" -> 1300.0
        assert DataTransformer.parse_numeric("1,200 - 1,400+ sqft") == 1300.0
        # Suffix plus (e.g. 4+ bedrooms -> 4)
        assert DataTransformer.parse_numeric("4+ beds") == 4.0
        # Negative coordinates e.g. Canadian longitude
        assert DataTransformer.parse_numeric("-123.128") == -123.128
        # Negative currency
        assert DataTransformer.parse_numeric("-$500") == -500.0

    def test_denormalize_sale_history_deduplication(self):
        # When same sale exists in both BC Assessment and Realtor.ca
        bca_sales = [{"price": 1150000.0, "date": "2021-03-15"}, {"price": 950000.0, "date": "2017-06-20"}]
        realtor_sales = [{"Price": "$1,150,000", "Date": "2021-03-15"}, {"Price": "$750,000", "Date": "2012-04-10"}]
        denorm = DataTransformer.denormalize_sale_history(bca_sales + realtor_sales)
        # Unique sales: 1150000 on 2021-03-15, 950000 on 2017-06-20, 750000 on 2012-04-10
        assert denorm["sale_price_1"] == 1150000.0
        assert denorm["sale_date_1"] == "2021-03-15"
        assert denorm["sale_price_2"] == 950000.0
        assert denorm["sale_date_2"] == "2017-06-20"
        assert denorm["sale_price_3"] == 750000.0
        assert denorm["sale_date_3"] == "2012-04-10"

    def test_transform_listing_safe_null_subobjects_and_amenities(self):
        # Gracefully handle when Property or Building is None
        row_null = DataTransformer.transform_listing({"Property": None})
        assert row_null["city"] == "Vancouver"
        assert row_null["region"] == "Greater Vancouver"

        # Test Fraser Valley city resolution when _region is missing
        row_fv = DataTransformer.transform_listing({
            "Property": {"Address": {"City": "Chilliwack"}}
        })
        assert row_fv["city"] == "Chilliwack"
        assert row_fv["region"] == "Fraser Valley"

        # Amenity parsing robustness
        row_amenity = DataTransformer.transform_listing({
            "Building": {"PoolType": "None", "FireplacePresent": True}
        })
        assert row_amenity["pool"] == 0
        assert row_amenity["fireplace"] == 1

    def test_mls_number_collision_prevention(self):
        listing1 = {"Property": {"Address": {"AddressText": "100 A St"}, "Price": 500000}}
        listing2 = {"Property": {"Address": {"AddressText": "200 B St"}, "Price": 750000}}
        row1 = DataTransformer.transform_listing(listing1)
        row2 = DataTransformer.transform_listing(listing2)
        assert row1["mls_number"].startswith("GEN_")
        assert row2["mls_number"].startswith("GEN_")
        assert row1["mls_number"] != row2["mls_number"]


class TestDBStorage:
    """Tests SQLite persistence, indexing, upserts, WAL mode, and CSV exports."""

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

    def test_empty_db_csv_export_has_headers(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp_db:
            storage = DBStorage(db_path=tmp_db.name)
            with tempfile.NamedTemporaryFile(suffix=".csv") as tmp_csv:
                rows = storage.export_to_csv(tmp_csv.name)
                assert rows == 0
                with open(tmp_csv.name, "r") as f:
                    header = f.readline().strip()
                    assert "mls_number" in header
                    assert "listing_price" in header


class TestAirflowDAGStructure:
    """Tests Airflow DAG topology, task structure, and callables."""

    def test_dag_properties(self):
        assert dag.dag_id == "daily_real_estate_collector"
        assert dag.schedule_interval == "@daily"
        assert dag.catchup is False
        assert dag.max_active_runs == 1
        assert dag.max_active_tasks == 4

    def test_dag_task_graph_dependencies(self):
        # init_storage is upstream of city tasks
        init_task = next(t for t in dag.tasks if t.task_id == "init_storage")
        export_task = next(t for t in dag.tasks if t.task_id == "export_csv_dataset")
        summary_task = next(t for t in dag.tasks if t.task_id == "pipeline_summary_report")

        assert len(init_task.downstream_list) >= 15
        assert summary_task in export_task.downstream_list
        # Fan-in tasks use all_done so single city failure does not abort CSV export or summary report
        assert getattr(export_task, "trigger_rule", None) in ("all_done", "ALL_DONE")
        assert getattr(summary_task, "trigger_rule", None) in ("all_done", "ALL_DONE")

    def test_task_init_storage_and_summary_callables(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp_db:
            with patch("dags.real_estate_collector_dag.SQLITE_PATH", tmp_db.name):
                res_init = task_init_storage()
                assert res_init["status"] == "initialized"

                res_summary = task_pipeline_summary()
                assert res_summary["total_listings"] == 0

    def test_end_to_end_dag_pipeline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            csv_path = os.path.join(tmpdir, "test.csv")

            with patch("dags.real_estate_collector_dag.SQLITE_PATH", db_path), \
                 patch("dags.real_estate_collector_dag.CSV_PATH", csv_path):

                # 1. Initialize DB schema
                init_res = task_init_storage()
                assert init_res["status"] == "initialized"
                assert os.path.exists(db_path)

                # 2. Mock listing and assessment
                mock_listing = {
                    "MlsNumber": "R9998887",
                    "Id": "8887776",
                    "Property": {
                        "Price": "$1,388,000",
                        "Address": {
                            "AddressText": "#301 - 1234 Robson St|Vancouver, BC V6E 1B2",
                            "City": "Vancouver",
                            "Latitude": 49.285,
                            "Longitude": -123.128,
                        },
                        "ParkingSpaceTotal": "2",
                    },
                    "Building": {
                        "Bedrooms": "3 + 1",
                        "BathroomTotal": "3",
                        "SizeInterior": "1,400 - 1,600 sqft",
                        "ConstructedDate": "2015",
                        "HeatingType": "Heat Pump",
                        "CoolingType": "Air Conditioned",
                    },
                    "PublicRemarks": "Luxury townhome with fireplace and private garden.",
                    "InsertedDateUTC": "2026-05-01T00:00:00Z",
                    "HistoricalSales": [
                        {"Price": "$1,150,000", "Date": "2021-03-15"},
                        {"Price": "$950,000", "Date": "2017-06-20"},
                    ],
                }

                mock_bca_res = {
                    "bc_assessment_id": "01-081-999-001",
                    "bc_total_assessed_value": 1290000.0,
                    "bc_land_value": 700000.0,
                    "bc_improvement_value": 590000.0,
                    "bc_previous_year_value": 1210000.0,
                    "bc_assessment_year": 2026,
                    "bc_property_class": "01 - Residential",
                    "bc_sales_history": [],
                }

                from dags.real_estate_collector_dag import RealtorScraper, BCAssessmentScraper
                with patch.object(RealtorScraper, "fetch_city_listings", return_value=[mock_listing]), \
                     patch.object(BCAssessmentScraper, "fetch_assessment_for_address", return_value=mock_bca_res):
                    collect_res = task_collect_and_enrich_city("Vancouver", max_pages=1)
                    assert collect_res["listings_processed"] == 1

                # 3. Export CSV
                export_res = task_export_csv()
                assert export_res["rows_exported"] == 1
                assert os.path.exists(csv_path)

                # 4. Pipeline Summary
                summary = task_pipeline_summary()
                assert summary["total_listings"] == 1
                assert summary["with_sale_history"] == 1
                assert summary["with_bc_assessment"] == 1

                # Verify database content directly
                storage = DBStorage(db_path=db_path)
                with storage.get_connection() as conn:
                    c = conn.cursor()
                    c.execute("SELECT mls_number, unit_number, street_number, bedrooms, square_footage, listing_price, sale_price_1, sale_date_1, sale_price_2, sale_date_2, fireplace, garden FROM real_estate_listings")
                    row = c.fetchone()
                    assert row["mls_number"] == "R9998887"
                    assert row["unit_number"] == "301"
                    assert row["street_number"] == "1234"
                    assert row["bedrooms"] == 4  # 3+1
                    assert row["square_footage"] == 1500.0  # avg 1400-1600
                    assert row["listing_price"] == 1388000.0
                    assert row["sale_price_1"] == 1150000.0
                    assert row["sale_date_1"] == "2021-03-15"
                    assert row["sale_price_2"] == 950000.0
                    assert row["sale_date_2"] == "2017-06-20"
                    assert row["fireplace"] == 1
                    assert row["garden"] == 1
