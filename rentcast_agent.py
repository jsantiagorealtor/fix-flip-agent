# ─────────────────────────────────────────────────────────────────────────────
# rentcast_agent.py  —  On-market search via Rentcast API (free tier)
#
# Free tier: 50 calls/month
# This script uses 2 calls per run (one per city).
# Running every other day = ~30 calls/month — safely within free tier.
# For true daily alerts upgrade to Rentcast Starter ($29/mo = 1,000 calls).
#
# Sign up: https://app.rentcast.io/app/api-access
# ─────────────────────────────────────────────────────────────────────────────
import os
import time
import logging
import requests
from config import SEARCH, RENTCAST

logger = logging.getLogger(__name__)


def _get_headers() -> dict:
    api_key = os.environ.get("RENTCAST_API_KEY", "")
    if not api_key:
        raise EnvironmentError("RENTCAST_API_KEY secret is not set.")
    return {"X-Api-Key": api_key, "Accept": "application/json"}


def _normalize_listing(raw: dict, city: str) -> dict:
    """Map Rentcast response fields → unified property dict used by deal_scorer."""
    sqft = raw.get("squareFootage") or raw.get("livingArea") or 0
    return {
        # Location
        "address":        raw.get("formattedAddress") or raw.get("address", ""),
        "city":           raw.get("city", city),
        "state":          raw.get("state", SEARCH["state"]),
        "zip_code":       raw.get("zipCode", ""),
        # Property details
        "bedrooms":       raw.get("bedrooms", 0),
        "bathrooms":      raw.get("bathrooms", 0),
        "square_footage": int(sqft),
        "year_built":     raw.get("yearBuilt", 0),
        "stories":        raw.get("stories") or raw.get("numStories", None),
        "property_type":  raw.get("propertyType", ""),
        "pool":           raw.get("pool", False),
        # Listing details
        "price":          raw.get("price") or raw.get("listPrice", 0),
        "days_on_market": raw.get("daysOnMarket", 0),
        "listing_status": raw.get("status", "Active"),
        "listing_url":    raw.get("listingUrl") or _build_zillow_url(raw),
        # Meta
        "source":         "rentcast",
        "source_id":      raw.get("id", ""),
    }


def _build_zillow_url(raw: dict) -> str:
    """Fallback: build a Zillow search URL from address if no direct link."""
    addr = raw.get("formattedAddress") or raw.get("address", "")
    if not addr:
        return ""
    slug = addr.replace(" ", "-").replace(",", "").replace(".", "")
    return f"https://www.zillow.com/homes/{slug}_rb/"


def _passes_filters(prop: dict) -> bool:
    """Apply post-API filters that Rentcast can't handle server-side."""
    # Square footage
    if prop["square_footage"] < SEARCH["min_sqft"]:
        return False
    # Bedrooms / bathrooms
    if prop["bedrooms"] < SEARCH["min_beds"]:
        return False
    if prop["bathrooms"] < SEARCH["min_baths"]:
        return False
    # Price range
    if not (SEARCH["min_price"] <= prop["price"] <= SEARCH["max_price"]):
        return False
    # Stories — only filter if data is present (many listings omit this field)
    stories = prop.get("stories")
    if stories and stories > SEARCH["stories"]:
        return False
    # Days on market
    if prop["days_on_market"] > SEARCH["max_dom"]:
        return False
    # Must be single-family residential
    pt = (prop["property_type"] or "").lower()
    if pt and "single" not in pt and "sfr" not in pt and "residential" not in pt:
        return False
    return True


def search_city(city: str) -> list:
    """
    Call Rentcast /listings/sale for a single city.
    Returns list of normalized, filtered property dicts.
    """
    url = f"{RENTCAST['base_url']}/listings/sale"
    params = {
        "city":            city,
        "state":           SEARCH["state"],
        "propertyType":    SEARCH["property_type"],
        "bedrooms":        SEARCH["min_beds"],
        "bathrooms":       SEARCH["min_baths"],
        "minPrice":        SEARCH["min_price"],
        "maxPrice":        SEARCH["max_price"],
        "minSquareFootage": SEARCH["min_sqft"],
        "status":          "Active",
        "limit":           RENTCAST["limit"],
    }

    try:
        logger.info(f"Rentcast search → {city}, {SEARCH['state']}")
        resp = requests.get(url, headers=_get_headers(), params=params, timeout=30)
        resp.raise_for_status()
        raw_listings = resp.json()

        if not isinstance(raw_listings, list):
            # Some API versions wrap results: {"listings": [...]}
            raw_listings = raw_listings.get("listings", [])

        normalized = [_normalize_listing(r, city) for r in raw_listings]
        filtered   = [p for p in normalized if _passes_filters(p)]

        logger.info(f"  {city}: {len(raw_listings)} raw → {len(filtered)} after filters")
        return filtered

    except requests.HTTPError as e:
        if e.response.status_code == 429:
            logger.warning("Rentcast rate limit hit — free tier may be exhausted for this month.")
        else:
            logger.error(f"Rentcast HTTP error for {city}: {e}")
        return []
    except Exception as e:
        logger.error(f"Rentcast unexpected error for {city}: {e}")
        return []


def fetch_on_market_listings() -> list:
    """
    Search all configured cities and return deduplicated results.
    Adds a 1-second pause between calls to respect rate limits.
    """
    all_results = []
    seen_ids    = set()

    for i, city in enumerate(SEARCH["cities"]):
        if i > 0:
            time.sleep(1)  # Polite pause between API calls
        listings = search_city(city)
        for prop in listings:
            # Deduplicate by source ID or address
            key = prop.get("source_id") or prop.get("address")
            if key and key not in seen_ids:
                seen_ids.add(key)
                all_results.append(prop)

    logger.info(f"On-market total (deduplicated): {len(all_results)} properties")
    return all_results
