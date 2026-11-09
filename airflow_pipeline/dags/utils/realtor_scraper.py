"""Realtor.ca Scraper for Greater Vancouver Area and Fraser Valley.

Provides coverage for all municipalities in GVA and Fraser Valley,
handles bounding-box pagination, atomic field extraction, and date parsing.
"""

import datetime
import json
import logging
import re
from typing import Any, Dict, Generator, List, Optional
from .flaresolverr_client import FlareSolverrClient

logger = logging.getLogger(__name__)

# Municipality bounding boxes (lat_min, lat_max, lon_min, lon_max)
COVERED_REGIONS: Dict[str, Dict[str, Any]] = {
    # Greater Vancouver Area
    "Vancouver": {"bounds": (49.1989, 49.3162, -123.2247, -123.0232), "region": "Greater Vancouver"},
    "Surrey": {"bounds": (49.0021, 49.2155, -122.9213, -122.6841), "region": "Greater Vancouver"},
    "Burnaby": {"bounds": (49.1950, 49.2950, -123.0232, -122.8900), "region": "Greater Vancouver"},
    "Richmond": {"bounds": (49.1000, 49.2100, -123.2100, -123.0500), "region": "Greater Vancouver"},
    "Coquitlam": {"bounds": (49.2300, 49.3800, -122.8300, -122.7000), "region": "Greater Vancouver"},
    "New Westminster": {"bounds": (49.1850, 49.2380, -122.9600, -122.8800), "region": "Greater Vancouver"},
    "West Vancouver": {"bounds": (49.3100, 49.4200, -123.2900, -123.1200), "region": "Greater Vancouver"},
    "North Vancouver": {"bounds": (49.2900, 49.3900, -123.1200, -122.9500), "region": "Greater Vancouver"},
    "Delta": {"bounds": (49.0020, 49.1900, -123.1600, -122.8700), "region": "Greater Vancouver"},
    "White Rock": {"bounds": (49.0100, 49.0400, -122.8300, -122.7800), "region": "Greater Vancouver"},
    "Langley": {"bounds": (49.0020, 49.1800, -122.6800, -122.4400), "region": "Greater Vancouver"},
    "Langley City": {"bounds": (49.0850, 49.1200, -122.6800, -122.6300), "region": "Greater Vancouver"},
    "Township of Langley": {"bounds": (49.0020, 49.1800, -122.6800, -122.4800), "region": "Greater Vancouver"},
    "Port Coquitlam": {"bounds": (49.2300, 49.2900, -122.8000, -122.7300), "region": "Greater Vancouver"},
    "Port Moody": {"bounds": (49.2600, 49.3400, -122.8900, -122.8000), "region": "Greater Vancouver"},
    "Maple Ridge": {"bounds": (49.1700, 49.3000, -122.6500, -122.4500), "region": "Greater Vancouver"},
    "Pitt Meadows": {"bounds": (49.1800, 49.2700, -122.7300, -122.6400), "region": "Greater Vancouver"},
    "Bowen Island": {"bounds": (49.3500, 49.4200, -123.4000, -123.3000), "region": "Greater Vancouver"},
    "Anmore": {"bounds": (49.3000, 49.3500, -122.8800, -122.8200), "region": "Greater Vancouver"},
    "Belcarra": {"bounds": (49.3000, 49.3400, -122.9300, -122.8800), "region": "Greater Vancouver"},
    "Lions Bay": {"bounds": (49.4300, 49.4800, -123.2600, -123.2100), "region": "Greater Vancouver"},

    # Fraser Valley
    "Abbotsford": {"bounds": (49.0020, 49.1400, -122.4500, -122.1500), "region": "Fraser Valley"},
    "Mission": {"bounds": (49.1000, 49.2500, -122.4000, -122.1800), "region": "Fraser Valley"},
    "Chilliwack": {"bounds": (49.0500, 49.2500, -122.0500, -121.8500), "region": "Fraser Valley"},
    "Aldergrove": {"bounds": (49.0300, 49.0800, -122.5200, -122.4400), "region": "Fraser Valley"},
    "Hope": {"bounds": (49.3500, 49.4200, -121.5000, -121.3800), "region": "Fraser Valley"},
    "Kent": {"bounds": (49.2000, 49.2800, -121.8200, -121.7000), "region": "Fraser Valley"},
    "Harrison Hot Springs": {"bounds": (49.2800, 49.3300, -121.8200, -121.7500), "region": "Fraser Valley"},
}

REALTOR_API_URL = "https://api.realtor.ca/Listing.svc/PropertySearch_Post"


class RealtorScraper:
    """Scrapes and parses property listings from Realtor.ca for specified regions."""

    def __init__(self, client: Optional[FlareSolverrClient] = None):
        self.client = client or FlareSolverrClient()

    @staticmethod
    def get_region_config(city_name: str) -> Optional[Dict[str, Any]]:
        """Resolves municipality configuration with case-insensitive and alias support."""
        if city_name in COVERED_REGIONS:
            return COVERED_REGIONS[city_name]
        lower_name = city_name.strip().lower()
        for k, v in COVERED_REGIONS.items():
            if k.lower() == lower_name:
                return v
        # Alias checks
        if lower_name == "langley":
            return COVERED_REGIONS.get("Langley") or COVERED_REGIONS.get("Township of Langley")
        return None

    def parse_ms_date(self, date_str: Optional[str]) -> Optional[str]:
        """Parses ASP.NET JSON dates like '/Date(1710000000000)/' or ISO strings."""
        if not date_str:
            return None
        match = re.search(r"/Date\((\d+)\)/", str(date_str))
        if match:
            ts_ms = int(match.group(1))
            dt = datetime.datetime.fromtimestamp(ts_ms / 1000.0, tz=datetime.timezone.utc)
            return dt.strftime("%Y-%m-%d")
        try:
            dt = datetime.datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return str(date_str)[:10]

    def parse_price(self, price_str: Any) -> Optional[float]:
        """Cleans and extracts numeric price from currency string."""
        if price_str is None:
            return None
        if isinstance(price_str, (int, float)):
            return float(price_str)
        cleaned = re.sub(r"[^\d.]", "", str(price_str))
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None

    def parse_numeric(self, val: Any) -> Optional[float]:
        """Extracts first valid float from string, handling commas."""
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        cleaned = str(val).replace(",", "")
        match = re.search(r"[-+]?\d*\.\d+|\d+", cleaned)
        return float(match.group(0)) if match else None

    def build_search_payload(
        self,
        lat_min: float,
        lat_max: float,
        lon_min: float,
        lon_max: float,
        page: int = 1,
        records_per_page: int = 50,
    ) -> Dict[str, Any]:
        """Builds standard form-encoded payload for Realtor.ca PropertySearch_Post."""
        return {
            "CultureId": 1,
            "ApplicationId": 1,
            "Version": "7.0",
            "CurrentPage": page,
            "RecordsPerPage": records_per_page,
            "MaximumResults": 1000,
            "PropertySearchTypeId": 1,
            "TransactionTypeId": 2,  # For sale
            "PriceMin": 10000,
            "PriceMax": 100000000,
            "LatitudeMin": lat_min,
            "LatitudeMax": lat_max,
            "LongitudeMin": lon_min,
            "LongitudeMax": lon_max,
            "SortBy": 6,  # Listed date descending (newest first for daily fresh inventory)
            "SortOrder": "D",
        }

    def fetch_city_listings(
        self,
        city_name: str,
        max_pages: int = 5,
        max_days_old: Optional[int] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """Yields raw property listing dicts for a city across paginated results."""
        config = self.get_region_config(city_name)
        if not config:
            logger.warning(f"Unknown city {city_name}. Skipping collection.")
            return

        lat_min, lat_max, lon_min, lon_max = config["bounds"]
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Referer": "https://www.realtor.ca/",
            "Origin": "https://www.realtor.ca",
        }

        for page in range(1, max_pages + 1):
            payload = self.build_search_payload(lat_min, lat_max, lon_min, lon_max, page=page)
            logger.info(f"Fetching {city_name} page {page}/{max_pages}...")

            try:
                res = self.client.fetch(
                    REALTOR_API_URL,
                    method="POST",
                    data=payload,
                    headers=headers,
                )
                body = res.get("response", "")
                if isinstance(body, str):
                    try:
                        data = json.loads(body)
                    except json.JSONDecodeError:
                        logger.warning(f"Non-JSON response for {city_name} page {page}")
                        break
                else:
                    data = body

                results = data.get("Results", [])
                if not results:
                    logger.info(f"No more results for {city_name} on page {page}")
                    break

                stop_early = False
                for listing in results:
                    listing["_queried_city"] = city_name
                    listing["_region"] = config["region"]

                    # Check fresh inventory cutoff if configured
                    if max_days_old is not None:
                        date_str = (
                            listing.get("InsertedDateUTC")
                            or listing.get("DateListed")
                            or listing.get("Property", {}).get("InsertedDateUTC")
                        )
                        parsed_d = self.parse_ms_date(date_str)
                        if parsed_d:
                            try:
                                dt = datetime.date.fromisoformat(parsed_d)
                                today = datetime.datetime.now(datetime.timezone.utc).date()
                                if (today - dt).days > max_days_old:
                                    # Since results are sorted newest-first, we can stop
                                    stop_early = True
                                    break
                            except Exception:
                                pass

                    yield listing

                if stop_early:
                    logger.info(f"Reached listings older than {max_days_old} days for {city_name}. Stopping page traversal.")
                    break

                paging = data.get("Paging", {})
                total_pages = paging.get("TotalPages", 1)
                if page >= total_pages:
                    break

            except Exception as e:
                logger.error(f"Error fetching {city_name} page {page}: {e}")
                break
