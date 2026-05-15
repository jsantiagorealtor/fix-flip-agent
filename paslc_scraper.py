# ─────────────────────────────────────────────────────────────────────────────
# paslc_scraper.py  —  Off-market leads from St. Lucie County Property Appraiser
#                      Source: https://www.paslc.gov  (public records, free)
#
# Strategy: Search the public property database, filter to single-family homes
# matching our size/price criteria, then flag ABSENTEE OWNERS (owner mailing
# address ≠ property address) as motivated-seller candidates.
#
# HOW IT WORKS:
#   1. POST a search form to paslc.gov with section/subdivision filters
#   2. Parse the HTML results table row by row
#   3. Compare property_address vs mailing_address → absentee = True/False
#   4. Filter by SF, year built, property type
#   5. Return leads list to main.py → deal_scorer → email
#
# NOTE: Web scraping targets publicly accessible government data.
# If paslc.gov changes their HTML structure, update the CSS selectors
# in the SELECTORS dict below. Run `python paslc_scraper.py --debug`
# to print raw HTML and re-map selectors.
# ─────────────────────────────────────────────────────────────────────────────
import re
import time
import logging
import argparse
import requests
from bs4 import BeautifulSoup
from config import SEARCH, PASLC, DEAL

logger = logging.getLogger(__name__)

# ── CSS / HTML SELECTORS ──────────────────────────────────────────────────────
# Adjust these if paslc.gov updates their site layout.
SELECTORS = {
    "results_table":    "table.result-table, table#resultsTable, table.searchResults",
    "result_row":       "tr",
    # Column indices in the results table (0-based). Verify by running --debug.
    "col_parcel":       0,
    "col_owner":        1,
    "col_prop_addr":    2,
    "col_mail_addr":    3,
    "col_land_use":     4,
    "col_sqft":         5,
    "col_year_built":   6,
    "col_assessed_val": 7,
    # Detail page link (parcel number usually links to full record)
    "detail_link":      "a",
}

# Alternative: many FL county PAs use qPublic or similar — try this URL pattern
QPUBLIC_SEARCH_URL = "https://qpublic.schneidercorp.com/Application.aspx?AppID=1032&LayerID=22628&PageTypeID=2&PageID=9404"

SESSION_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection":      "keep-alive",
}


# ─────────────────────────────────────────────────────────────────────────────
# PASLC SESSION + SEARCH
# ─────────────────────────────────────────────────────────────────────────────

def _start_session() -> requests.Session:
    """Create a session and load the search page to get any required cookies."""
    session = requests.Session()
    session.headers.update(SESSION_HEADERS)
    try:
        search_url = PASLC["base_url"] + PASLC["search_path"]
        resp = session.get(search_url, timeout=20)
        resp.raise_for_status()
        logger.debug(f"PASLC session started. Status: {resp.status_code}")
    except Exception as e:
        logger.warning(f"Could not reach paslc.gov search page: {e}")
    return session


def _get_viewstate(html: str) -> dict:
    """Extract ASP.NET hidden form fields (ViewState, EventValidation) if present."""
    soup = BeautifulSoup(html, "html.parser")
    fields = {}
    for hidden in soup.find_all("input", {"type": "hidden"}):
        name = hidden.get("name", "")
        val  = hidden.get("value", "")
        if name:
            fields[name] = val
    return fields


def _search_section(session: requests.Session, section: str) -> list:
    """
    POST a search for one PSL subdivision/section and return parsed rows.
    Returns list of raw dicts; filtering happens in _parse_results().
    """
    search_url = PASLC["base_url"] + PASLC["search_path"]

    try:
        # Step 1: GET the search form to retrieve hidden ASP.NET fields
        get_resp = session.get(search_url, timeout=20)
        hidden   = _get_viewstate(get_resp.text)

        # Step 2: POST the search form
        # These field names are typical for FL county PA ASP.NET CAMA systems.
        # Adjust if paslc.gov uses different field names (check browser DevTools).
        post_data = {
            **hidden,
            "ctl00$cphMain$txtSubdivision":    section,
            "ctl00$cphMain$txtOwnerName":      "",
            "ctl00$cphMain$txtParcelNum":      "",
            "ctl00$cphMain$txtSiteAddress":    "",
            "ctl00$cphMain$txtCity":           "",
            "ctl00$cphMain$btnSearch":         "Search",
        }

        post_resp = session.post(search_url, data=post_data, timeout=30)
        post_resp.raise_for_status()
        return _parse_results(post_resp.text, section)

    except requests.HTTPError as e:
        logger.error(f"PASLC HTTP error for section '{section}': {e}")
        return []
    except Exception as e:
        logger.error(f"PASLC unexpected error for '{section}': {e}")
        return []


def _parse_results(html: str, section: str) -> list:
    """
    Parse the HTML results table and extract property data rows.
    Returns list of raw property dicts (not yet filtered for investment criteria).
    """
    soup   = BeautifulSoup(html, "html.parser")
    table  = soup.select_one(SELECTORS["results_table"])

    if not table:
        # Try fallback — some pages embed data in any table after page load
        tables = soup.find_all("table")
        # Heuristic: find table with most rows (likely the results table)
        table = max(tables, key=lambda t: len(t.find_all("tr")), default=None) if tables else None

    if not table:
        logger.warning(f"No results table found for section: {section}")
        return []

    rows    = table.find_all(SELECTORS["result_row"])
    results = []

    for row in rows[1:]:  # skip header row
        cells = row.find_all(["td", "th"])
        if len(cells) < 6:
            continue

        def cell_text(idx):
            return cells[idx].get_text(strip=True) if idx < len(cells) else ""

        # Extract detail URL (usually the parcel number column links to full record)
        parcel_cell = cells[SELECTORS["col_parcel"]]
        detail_link = parcel_cell.find("a")
        detail_url  = ""
        if detail_link and detail_link.get("href"):
            href = detail_link["href"]
            detail_url = href if href.startswith("http") else PASLC["base_url"] + "/" + href.lstrip("/")

        parcel      = cell_text(SELECTORS["col_parcel"]).strip()
        owner       = cell_text(SELECTORS["col_owner"]).strip()
        prop_addr   = cell_text(SELECTORS["col_prop_addr"]).strip()
        mail_addr   = cell_text(SELECTORS["col_mail_addr"]).strip()
        land_use    = cell_text(SELECTORS["col_land_use"]).strip()
        sqft_raw    = cell_text(SELECTORS["col_sqft"]).replace(",", "").strip()
        yr_raw      = cell_text(SELECTORS["col_year_built"]).strip()
        assessed_v  = cell_text(SELECTORS["col_assessed_val"]).replace(",", "").replace("$", "").strip()

        sqft       = int(sqft_raw)    if sqft_raw.isdigit()    else 0
        year_built = int(yr_raw)      if yr_raw.isdigit()      else 0
        assessed   = int(assessed_v)  if assessed_v.isdigit()  else 0

        if not parcel:
            continue

        results.append({
            "parcel":       parcel,
            "owner":        owner,
            "prop_address": prop_addr,
            "mail_address": mail_addr,
            "land_use":     land_use,
            "square_footage": sqft,
            "year_built":   year_built,
            "assessed_value": assessed,
            "section":      section,
            "detail_url":   detail_url,
        })

    return results


# ─────────────────────────────────────────────────────────────────────────────
# FILTERING + NORMALIZATION
# ─────────────────────────────────────────────────────────────────────────────

def _is_absentee_owner(prop_addr: str, mail_addr: str) -> bool:
    """
    Detect absentee ownership by comparing property and mailing addresses.
    Simple but effective: if the first 10 chars differ, it's likely absentee.
    """
    if not prop_addr or not mail_addr:
        return False
    # Normalize: lowercase, remove punctuation
    clean = lambda s: re.sub(r"[^a-z0-9 ]", "", s.lower().strip())
    p = clean(prop_addr)[:30]
    m = clean(mail_addr)[:30]
    return p != m


def _is_single_family(land_use_code: str) -> bool:
    """Check if land use code indicates single-family residential."""
    code = land_use_code.upper().strip()
    sfr_codes = [c.upper() for c in PASLC["sfr_land_use_codes"]]
    # Also accept codes that start with "01" (common FL SFR convention)
    return any(code.startswith(c) or code == c for c in sfr_codes) or code.startswith("01")


def _normalize_off_market(raw: dict) -> dict:
    """Convert PASLC raw record → unified property dict for deal_scorer."""
    addr = raw["prop_address"]
    # Try to extract city from mailing address or default to PSL
    city = "Port St. Lucie"
    for c in ["FORT PIERCE", "PORT ST LUCIE", "PORT SAINT LUCIE"]:
        if c in addr.upper() or c in raw.get("mail_address", "").upper():
            city = c.title().replace("Saint", "St.")
            break

    return {
        "address":        addr,
        "city":           city,
        "state":          "FL",
        "zip_code":       "",           # Not always available in summary view
        "bedrooms":       3,            # Assumed for SFR in our SF range; verify on detail page
        "bathrooms":      2,            # Same assumption
        "square_footage": raw["square_footage"],
        "year_built":     raw["year_built"],
        "stories":        1,            # PSL CBS SFR are predominantly 1-story
        "property_type":  "Single Family",
        "pool":           False,        # Unknown from summary
        # Use assessed value × 1.15 as rough market-value proxy (FL assessment ratio)
        "price":          round(raw["assessed_value"] * 1.15) if raw["assessed_value"] > 0 else 0,
        "days_on_market": 0,            # Off-market, not listed
        "listing_status": "Off-Market",
        "listing_url":    raw.get("detail_url", PASLC["base_url"]),
        # Off-market metadata
        "source":         "paslc",
        "source_id":      raw["parcel"],
        "owner":          raw["owner"],
        "absentee_owner": raw.get("absentee", False),
        "assessed_value": raw["assessed_value"],
        "section":        raw["section"],
        "parcel":         raw["parcel"],
    }


def _passes_off_market_filters(raw: dict) -> bool:
    """Apply investment-criteria filters to raw PASLC records."""
    # Must be single-family residential
    if not _is_single_family(raw.get("land_use", "")):
        return False
    # Minimum square footage
    if raw["square_footage"] < SEARCH["min_sqft"]:
        return False
    # Skip properties with no size data (data missing)
    if raw["square_footage"] == 0:
        return False
    # Skip brand-new construction (assessed value too high, no distress)
    if raw["year_built"] > 2020:
        return False
    # Assessed value proxy must be in rough price range
    # Assessed value is typically 80-90% of market in FL
    if raw["assessed_value"] > 0:
        est_market = raw["assessed_value"] * 1.15
        if est_market > SEARCH["max_price"] * 1.3:  # Allow 30% above max (may negotiate)
            return False
        if est_market < SEARCH["min_price"] * 0.6:  # Too cheap — likely teardown
            return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def fetch_off_market_leads() -> list:
    """
    Scrape St. Lucie County PA for off-market leads.
    Returns list of scored-ready property dicts.
    """
    session  = _start_session()
    raw_all  = []
    seen_parcels = set()

    for section in PASLC["target_sections"]:
        logger.info(f"PASLC scrape → {section}")
        rows = _search_section(session, section)

        for row in rows:
            parcel = row.get("parcel", "")
            if parcel in seen_parcels:
                continue
            seen_parcels.add(parcel)

            # Tag absentee owners
            row["absentee"] = _is_absentee_owner(row["prop_address"], row["mail_address"])

            if _passes_off_market_filters(row):
                raw_all.append(row)

        logger.info(f"  {section}: {len(rows)} scraped → {sum(1 for r in raw_all if r['section']==section)} passed filters")
        time.sleep(PASLC["rate_limit_secs"])  # Be respectful — public server

        if len(raw_all) >= PASLC["max_results"]:
            logger.info("Max off-market results reached. Stopping early.")
            break

    # Normalize
    normalized = [_normalize_off_market(r) for r in raw_all]

    # Prioritize: absentee owners first, then by SF (bigger homes = more value)
    absentee = [p for p in normalized if p["absentee_owner"]]
    resident = [p for p in normalized if not p["absentee_owner"]]
    absentee.sort(key=lambda x: x["square_footage"], reverse=True)
    resident.sort(key=lambda x: x["square_footage"], reverse=True)

    result = absentee + resident
    logger.info(f"Off-market total: {len(result)} leads ({len(absentee)} absentee owners)")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# DEBUG MODE  —  run: python paslc_scraper.py --debug
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true",
                        help="Print raw HTML of first section search to debug selectors")
    args = parser.parse_args()

    if args.debug:
        print("\n── DEBUG MODE ── Fetching raw HTML from PASLC...\n")
        session = _start_session()
        section = PASLC["target_sections"][0]

        search_url = PASLC["base_url"] + PASLC["search_path"]
        get_resp   = session.get(search_url, timeout=20)
        hidden     = _get_viewstate(get_resp.text)

        post_data  = {
            **hidden,
            "ctl00$cphMain$txtSubdivision": section,
            "ctl00$cphMain$btnSearch":      "Search",
        }
        post_resp = session.post(search_url, data=post_data, timeout=30)
        soup      = BeautifulSoup(post_resp.text, "html.parser")

        print(f"Page title: {soup.title.string if soup.title else 'N/A'}")
        print(f"\nAll tables found: {len(soup.find_all('table'))}")
        for i, t in enumerate(soup.find_all("table")):
            rows = t.find_all("tr")
            print(f"  Table {i}: {len(rows)} rows, classes={t.get('class','')}, id={t.get('id','')}")
        print("\n── First 3000 chars of body ──")
        print(post_resp.text[:3000])
    else:
        leads = fetch_off_market_leads()
        print(f"\nFound {len(leads)} off-market leads:")
        for lead in leads[:5]:
            print(f"  {lead['address']} | {lead['square_footage']} SF | "
                  f"{'ABSENTEE' if lead['absentee_owner'] else 'owner-occ'} | "
                  f"Est. price ~${lead['price']:,}")
