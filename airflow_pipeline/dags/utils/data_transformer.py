"""Data Transformer for Real Estate Pipeline.

Normalizes raw Realtor.ca listings and BC Assessment data into clean,
atomic tabular fields, including denormalized sale history (last 3 sales).
"""

import datetime
import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple


class DataTransformer:
    """Transforms raw listing and assessment records into atomic schema rows."""

    @staticmethod
    def parse_numeric(val: Any) -> Optional[float]:
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        cleaned = re.sub(r"[^\d.]", "", str(val))
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None

    @staticmethod
    def parse_int(val: Any) -> Optional[int]:
        num = DataTransformer.parse_numeric(val)
        return int(round(num)) if num is not None else None

    @staticmethod
    def parse_address_parts(raw_address: str) -> Dict[str, Optional[str]]:
        """Parses address string into atomic unit, street number, street name, and postal code."""
        parts = {
            "unit_number": None,
            "street_number": None,
            "street_name": None,
            "postal_code": None,
            "full_address": raw_address.replace("|", ", ").strip(),
        }

        # Postal code regex (e.g. V6E 1C1 or V6E1C1)
        pc_match = re.search(r"([A-Za-z]\d[A-Za-z]\s?\d[A-Za-z]\d)", raw_address)
        if pc_match:
            parts["postal_code"] = pc_match.group(1).upper().replace(" ", "")

        street_part = raw_address.split("|")[0].strip() if "|" in raw_address else raw_address.split(",")[0].strip()

        # Check for unit e.g. #301 - 1234 Main St or 301-1234 Main St
        unit_match = re.match(r"(?:#|APT|UNIT|SUITE)?\s*(\w+)\s*[-/]\s*(\d+)\s+(.+)", street_part, re.IGNORECASE)
        if unit_match:
            parts["unit_number"] = unit_match.group(1)
            parts["street_number"] = unit_match.group(2)
            parts["street_name"] = unit_match.group(3).strip()
            return parts

        # Standard street number and name: 1234 Main St
        num_match = re.match(r"(\d+)\s+(.+)", street_part)
        if num_match:
            parts["street_number"] = num_match.group(1)
            parts["street_name"] = num_match.group(2).strip()
        else:
            parts["street_name"] = street_part

        return parts

    @staticmethod
    def parse_date(date_val: Any) -> Optional[str]:
        """Converts diverse date representations into ISO YYYY-MM-DD format."""
        if not date_val:
            return None
        # /Date(1710000000000)/
        ms_match = re.search(r"/Date\((\d+)\)/", str(date_val))
        if ms_match:
            ts = int(ms_match.group(1)) / 1000.0
            return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime("%Y-%m-%d")

        s = str(date_val).strip()
        # ISO format YYYY-MM-DD
        iso_match = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", s)
        if iso_match:
            try:
                y, m, d = int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))
                return datetime.date(y, m, d).isoformat()
            except ValueError:
                pass

        # YYYY/MM/DD
        slash_ymd = re.search(r"\b(\d{4})/(\d{1,2})/(\d{1,2})\b", s)
        if slash_ymd:
            try:
                y, m, d = int(slash_ymd.group(1)), int(slash_ymd.group(2)), int(slash_ymd.group(3))
                return datetime.date(y, m, d).isoformat()
            except ValueError:
                pass

        # DD/MM/YYYY or MM/DD/YYYY
        slash_match = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", s)
        if slash_match:
            p1, p2, yr = int(slash_match.group(1)), int(slash_match.group(2)), int(slash_match.group(3))
            # Disambiguate if one part is > 12
            if p1 > 12 and p2 <= 12:
                # p1 is day, p2 is month
                try:
                    return datetime.date(yr, p2, p1).isoformat()
                except ValueError:
                    pass
            elif p2 > 12 and p1 <= 12:
                # p1 is month, p2 is day
                try:
                    return datetime.date(yr, p1, p2).isoformat()
                except ValueError:
                    pass
            else:
                # Default to MM/DD/YYYY, fallback to DD/MM/YYYY
                try:
                    return datetime.date(yr, p1, p2).isoformat()
                except ValueError:
                    try:
                        return datetime.date(yr, p2, p1).isoformat()
                    except ValueError:
                        pass

        return None

    @staticmethod
    def denormalize_sale_history(sales: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Denormalizes a list of past sales into last 3 sale prices and dates, plus full overflow JSON."""
        result = {
            "sale_price_1": None,
            "sale_date_1": None,
            "sale_price_2": None,
            "sale_date_2": None,
            "sale_price_3": None,
            "sale_date_3": None,
            "sales_history_json": "[]",
        }

        # Filter valid sales and sort by date descending
        valid_sales = []
        for s in sales:
            p = DataTransformer.parse_numeric(s.get("price") or s.get("SalePrice"))
            d = DataTransformer.parse_date(s.get("date") or s.get("SaleDate"))
            if p or d:
                valid_sales.append({"price": p, "date": d})

        valid_sales.sort(key=lambda x: x["date"] or "", reverse=True)
        result["sales_history_json"] = json.dumps(valid_sales)

        for i in range(min(3, len(valid_sales))):
            idx = i + 1
            result[f"sale_price_{idx}"] = valid_sales[i]["price"]
            result[f"sale_date_{idx}"] = valid_sales[i]["date"]

        return result

    @classmethod
    def transform_listing(
        cls,
        listing: Dict[str, Any],
        assessment: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Converts raw Realtor listing and assessment dict into complete atomic record."""
        prop = listing.get("Property", {})
        bldg = listing.get("Building", {})
        land = listing.get("Land", {})
        addr = prop.get("Address", {})
        raw_addr = addr.get("AddressText", "")
        addr_parts = cls.parse_address_parts(raw_addr)

        # Region & City
        city = (
            addr.get("City")
            or listing.get("_queried_city")
            or "Vancouver"
        )
        region = listing.get("_region", "Greater Vancouver")

        # Geo Coordinates
        lat = cls.parse_numeric(prop.get("Latitude") or addr.get("Latitude"))
        lon = cls.parse_numeric(prop.get("Longitude") or addr.get("Longitude"))

        # Price
        price = cls.parse_numeric(prop.get("Price"))

        # Square Footage / Acreage
        size_str = bldg.get("SizeInterior") or prop.get("SizeInterior") or ""
        sqft = cls.parse_numeric(size_str)
        land_size_str = land.get("SizeTotal") or ""
        lot_size_sqft = cls.parse_numeric(land_size_str)
        acreage = None
        if "acre" in land_size_str.lower():
            acreage = cls.parse_numeric(land_size_str)
        elif lot_size_sqft:
            acreage = round(lot_size_sqft / 43560.0, 4)

        # Date listed
        date_listed = cls.parse_date(listing.get("InsertedDateUTC") or listing.get("DateListed"))
        if not date_listed:
            # Fallback to current date if missing from active feed
            date_listed = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

        days_on_market = None
        if date_listed:
            try:
                listed_dt = datetime.date.fromisoformat(date_listed)
                today = datetime.datetime.now(datetime.timezone.utc).date()
                days_on_market = max(0, (today - listed_dt).days)
            except Exception:
                pass

        # Sale History extraction
        sales: List[Dict[str, Any]] = []
        if assessment and assessment.get("bc_sales_history"):
            sales.extend(assessment["bc_sales_history"])
        if listing.get("HistoricalSales"):
            sales.extend(listing["HistoricalSales"])
        denorm_sales = cls.denormalize_sale_history(sales)

        # Binary and categorical amenities
        desc = (listing.get("PublicRemarks") or "").lower()
        has_pool = 1 if ("pool" in desc or bldg.get("PoolType")) else 0
        has_fireplace = 1 if ("fireplace" in desc or bldg.get("FireplacePresent") == "True") else 0
        has_waterfront = 1 if ("waterfront" in desc or "ocean" in desc or "lake" in desc) else 0
        has_garden = 1 if ("garden" in desc or "yard" in desc) else 0
        has_balcony = 1 if ("balcony" in desc or "deck" in desc or "patio" in desc) else 0

        # Identity resolution with collision prevention
        mls_id = listing.get("MlsNumber") or listing.get("Id")
        if not mls_id or str(mls_id).strip() == "":
            unique_seed = f"{raw_addr}_{price}_{lat}_{lon}_{date_listed}"
            mls_id = f"GEN_{hashlib.md5(unique_seed.encode()).hexdigest()[:12]}"
        else:
            mls_id = str(mls_id).strip()

        # Construct atomic record
        record: Dict[str, Any] = {
            # Identity
            "mls_number": mls_id,
            "realtor_id": str(listing.get("Id") or ""),
            "url": f"https://www.realtor.ca{listing.get('RelativeURLEn', '')}" if listing.get("RelativeURLEn") else "",
            "region": region,
            "city": city,
            "province": "BC",
            # Address
            "unit_number": addr_parts["unit_number"],
            "street_number": addr_parts["street_number"],
            "street_name": addr_parts["street_name"],
            "postal_code": addr_parts["postal_code"],
            "full_address": addr_parts["full_address"],
            # Coordinates
            "latitude": lat,
            "longitude": lon,
            # Core Valuation
            "listing_price": price,
            "date_listed": date_listed,
            "days_on_market": days_on_market,
            "transaction_type": "For Sale",
            "property_type": prop.get("Type") or bldg.get("Type") or "Single Family",
            # Specs
            "bedrooms": cls.parse_int(bldg.get("Bedrooms")),
            "bathrooms": cls.parse_int(bldg.get("BathroomTotal")),
            "half_bathrooms": cls.parse_int(bldg.get("HalfBathTotal")),
            "stories": cls.parse_numeric(bldg.get("StoriesTotal")),
            "year_built": cls.parse_int(bldg.get("ConstructedDate")),
            "square_footage": sqft,
            "lot_size_sqft": lot_size_sqft,
            "acreage": acreage,
            "parking_spaces": cls.parse_int(prop.get("ParkingSpaceTotal") or bldg.get("ParkingSpaceTotal")),
            "garage": 1 if ("garage" in (prop.get("ParkingType") or "").lower() or "garage" in desc) else 0,
            # Features
            "heating": bldg.get("HeatingType") or "Forced Air",
            "cooling": bldg.get("CoolingType") or "None",
            "basement": bldg.get("BasementType") or ("Finished" if "basement" in desc else "None"),
            "exterior": bldg.get("ExteriorFinish") or "Wood/Vinyl",
            "roof": bldg.get("RoofMaterial") or "Asphalt",
            "flooring": bldg.get("Flooring") or "Hardwood/Carpet",
            "sewer": prop.get("Sewer") or "Municipal",
            "pool": has_pool,
            "fireplace": has_fireplace,
            "waterfront": has_waterfront,
            "garden": has_garden,
            "balcony": has_balcony,
            # BC Assessment Enrichment
            "bc_assessment_id": assessment.get("bc_assessment_id") if assessment else None,
            "bc_total_assessed_value": assessment.get("bc_total_assessed_value") if assessment else None,
            "bc_land_value": assessment.get("bc_land_value") if assessment else None,
            "bc_improvement_value": assessment.get("bc_improvement_value") if assessment else None,
            "bc_previous_year_value": assessment.get("bc_previous_year_value") if assessment else None,
            "bc_assessment_year": assessment.get("bc_assessment_year") if assessment else None,
            "bc_property_class": assessment.get("bc_property_class") if assessment else None,
            # Denormalized Sales History (last 3 sales)
            "sale_price_1": denorm_sales["sale_price_1"],
            "sale_date_1": denorm_sales["sale_date_1"],
            "sale_price_2": denorm_sales["sale_price_2"],
            "sale_date_2": denorm_sales["sale_date_2"],
            "sale_price_3": denorm_sales["sale_price_3"],
            "sale_date_3": denorm_sales["sale_date_3"],
            "sales_history_json": denorm_sales["sales_history_json"],
            # Metadata
            "scraped_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        return record
