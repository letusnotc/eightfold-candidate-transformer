"""
Location normalizer — parses raw location strings into structured {city, region, country}.
Uses pycountry for ISO-3166 alpha-2 lookup.
Never invents values; returns partial results where possible.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

try:
    import pycountry
    _PYCOUNTRY_AVAILABLE = True
except ImportError:
    _PYCOUNTRY_AVAILABLE = False

logger = logging.getLogger(__name__)

# Common US state abbreviations
_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}

# Country name → ISO alpha-2 overrides for common short-forms
_COUNTRY_OVERRIDES: dict[str, str] = {
    "usa": "US",
    "united states": "US",
    "us": "US",
    "u.s.": "US",
    "u.s.a.": "US",
    "uk": "GB",
    "united kingdom": "GB",
    "england": "GB",
    "india": "IN",
    "bharat": "IN",
    "canada": "CA",
    "australia": "AU",
    "germany": "DE",
    "france": "FR",
    "spain": "ES",
    "italy": "IT",
    "netherlands": "NL",
    "singapore": "SG",
    "brazil": "BR",
    "china": "CN",
    "japan": "JP",
    "south korea": "KR",
    "korea": "KR",
    "mexico": "MX",
    "russia": "RU",
    "pakistan": "PK",
    "bangladesh": "BD",
    "nigeria": "NG",
    "kenya": "KE",
    "south africa": "ZA",
    "israel": "IL",
    "uae": "AE",
    "united arab emirates": "AE",
}

# Indian states (abbreviation or common name → keep as region string)
_INDIA_STATES = {
    "karnataka", "maharashtra", "tamil nadu", "telangana", "kerala",
    "andhra pradesh", "gujarat", "rajasthan", "uttar pradesh", "up",
    "madhya pradesh", "mp", "west bengal", "wb", "punjab", "haryana",
    "bihar", "odisha", "assam", "jharkhand", "chhattisgarh", "goa",
    "himachal pradesh", "hp", "uttarakhand", "delhi", "nct of delhi",
    "jammu and kashmir", "ladakh", "manipur", "meghalaya", "mizoram",
    "nagaland", "arunachal pradesh", "sikkim", "tripura",
}


def _lookup_country(name: str) -> Optional[str]:
    """Return ISO-3166 alpha-2 for a country name/abbreviation, or None."""
    key = name.strip().lower()
    if key in _COUNTRY_OVERRIDES:
        return _COUNTRY_OVERRIDES[key]

    if not _PYCOUNTRY_AVAILABLE:
        return None

    # Try exact match
    try:
        country = pycountry.countries.lookup(name.strip())
        return country.alpha_2
    except LookupError:
        pass

    # Try fuzzy search
    results = pycountry.countries.search_fuzzy(name.strip())
    if results:
        return results[0].alpha_2

    return None


def normalize_location(raw: str) -> dict[str, Optional[str]]:
    """
    Parse a raw location string → {city, region, country}.
    Never invents values; returns partial results where any info is found.

    Examples:
      "San Francisco, CA"         → {city: "San Francisco", region: "CA", country: "US"}
      "Bangalore, India"          → {city: "Bangalore", region: None, country: "IN"}
      "Madrid, ES"                → {city: "Madrid", region: None, country: "ES"}
      "New York, NY, USA"         → {city: "New York", region: "NY", country: "US"}
      "Bangalore, Karnataka, IN"  → {city: "Bangalore", region: "Karnataka", country: "IN"}
    """
    result: dict[str, Optional[str]] = {"city": None, "region": None, "country": None}

    if not raw or not isinstance(raw, str):
        return result

    parts = [p.strip() for p in raw.split(",") if p.strip()]

    if not parts:
        return result

    if len(parts) == 1:
        # Could be just a city or just a country
        country_code = _lookup_country(parts[0])
        if country_code:
            result["country"] = country_code
        else:
            result["city"] = parts[0]
        return result

    if len(parts) == 2:
        city_or_country, region_or_country = parts[0], parts[1]
        # Check if second part is a known US state abbreviation FIRST
        if region_or_country.strip().upper() in _US_STATES:
            result["city"] = city_or_country.strip()
            result["region"] = region_or_country.strip().upper()
            result["country"] = "US"
            return result
        # Try right part as country
        country_code = _lookup_country(region_or_country)
        if country_code:
            result["city"] = city_or_country
            result["country"] = country_code
        else:
            result["city"] = city_or_country
            result["region"] = region_or_country
        return result

    # 3+ parts
    result["city"] = parts[0]
    # Try last part as country
    country_code = _lookup_country(parts[-1])
    if country_code:
        result["country"] = country_code
        if len(parts) >= 3:
            result["region"] = parts[1]
    else:
        # Try second-to-last as country
        country_code = _lookup_country(parts[-2])
        if country_code:
            result["country"] = country_code
            result["region"] = parts[1] if len(parts) > 2 else None
        else:
            result["region"] = parts[1] if len(parts) > 1 else None
            # Check last part as US state
            if parts[-1].upper() in _US_STATES:
                result["region"] = parts[-1].upper()
                result["country"] = "US"

    return result
