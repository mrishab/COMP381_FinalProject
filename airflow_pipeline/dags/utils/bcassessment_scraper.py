"""BC Assessment Client and Data Extractor.

Queries BC Assessment public endpoints to retrieve atomic valuation data,
including Assessed Land Value, Improvement Value, Total Value, Previous Year Value,
and property tax classification.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus
from .flaresolverr_client import FlareSolverrClient

logger = logging.getLogger(__name__)

BCA_SEARCH_URL = "https://www.bcassessment.ca/Property/Search/GetByAddress"
BCA_DETAILS_URL = "https://www.bcassessment.ca/Property/View/GetDetailedPropertyInformation"


class BCAssessmentScraper:
    """Interacts with BC Assessment public endpoints to enrich listings with tax roll valuations."""

    def __init__(self, client: Optional[FlareSolverrClient] = None):
        self.client = client or FlareSolverrClient()
        self.headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": "https://www.bcassessment.ca/",
            "X-Requested-With": "XMLHttpRequest",
        }

    def clean_address_query(self, address: str) -> str:
        """Strips unit symbols or special characters for optimal geocoding on BCAssessment."""
        cleaned = re.sub(r"^[#\s]*\w+\s*[-/]\s*", "", address.strip())
        cleaned = re.sub(r"[,#\n\r]+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def search_property(self, address: str) -> List[Dict[str, Any]]:
        """Searches BC Assessment for address matches."""
        cleaned_addr = self.clean_address_query(address)
        encoded = quote_plus(cleaned_addr)
        url = f"{BCA_SEARCH_URL}?keyword={encoded}"

        try:
            res = self.client.fetch(url, method="GET", headers=self.headers)
            body = res.get("response", "[]")
            data = json.loads(body) if isinstance(body, str) else body
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.debug(f"BCAssessment lookup failed for '{address}': {e}")
            return []

    def get_property_details(self, property_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves detailed assessment records for a given property ID."""
        url = f"{BCA_DETAILS_URL}?id={quote_plus(property_id)}"
        try:
            res = self.client.fetch(url, method="GET", headers=self.headers)
            body = res.get("response", "{}")
            return json.loads(body) if isinstance(body, str) else body
        except Exception as e:
            logger.debug(f"Failed to fetch BCAssessment details for {property_id}: {e}")
            return None

    def fetch_assessment_for_address(self, address: str, city: str = "") -> Dict[str, Any]:
        """Convenience method: Searches address and returns atomic BC Assessment fields."""
        query = f"{address} {city}".strip()
        candidates = self.search_property(query)

        if not candidates and city:
            # Fallback to address only
            candidates = self.search_property(address)

        if not candidates:
            return self._empty_assessment()

        best_match = candidates[0]
        prop_id = best_match.get("value") or best_match.get("Id") or best_match.get("Key")

        if not prop_id:
            return self._empty_assessment()

        details = self.get_property_details(prop_id)
        if not details:
            # Parse from candidate summary if detailed call fails
            return self._parse_summary(best_match)

        return self._parse_detailed(details)

    def _empty_assessment(self) -> Dict[str, Any]:
        return {
            "bc_assessment_id": None,
            "bc_total_assessed_value": None,
            "bc_land_value": None,
            "bc_improvement_value": None,
            "bc_previous_year_value": None,
            "bc_assessment_year": None,
            "bc_property_class": None,
            "bc_property_description": None,
            "bc_sales_history": [],
        }

    def _parse_currency(self, val: Any) -> Optional[float]:
        if val is None:
            return None
        cleaned = re.sub(r"[^\d.]", "", str(val))
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None

    def _parse_summary(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "bc_assessment_id": summary.get("value"),
            "bc_total_assessed_value": self._parse_currency(summary.get("label")),
            "bc_land_value": None,
            "bc_improvement_value": None,
            "bc_previous_year_value": None,
            "bc_assessment_year": None,
            "bc_property_class": None,
            "bc_property_description": summary.get("label"),
            "bc_sales_history": [],
        }

    def _parse_detailed(self, data: Dict[str, Any]) -> Dict[str, Any]:
        sales_history = []
        for s in data.get("SalesHistory", []):
            sales_history.append(
                {
                    "price": self._parse_currency(s.get("SalePrice") or s.get("Price")),
                    "date": s.get("SaleDate") or s.get("Date"),
                }
            )

        return {
            "bc_assessment_id": data.get("PropertyId") or data.get("Id"),
            "bc_total_assessed_value": self._parse_currency(
                data.get("TotalAssessedValue") or data.get("AssessedValue")
            ),
            "bc_land_value": self._parse_currency(data.get("AssessedLandValue")),
            "bc_improvement_value": self._parse_currency(data.get("AssessedImprovementValue")),
            "bc_previous_year_value": self._parse_currency(
                data.get("PreviousYearTotalAssessedValue")
            ),
            "bc_assessment_year": data.get("AssessmentYear"),
            "bc_property_class": data.get("PropertyClass") or data.get("PropertyClassDescription"),
            "bc_property_description": data.get("PropertyDescription") or data.get("GeneralDescription"),
            "bc_sales_history": sales_history,
        }
