# ─────────────────────────────────────────────────────────────────────────────
# config.py  —  Fix & Flip Agent · St. Lucie County, FL
# All tunable parameters in one place. Edit here, nowhere else.
# ─────────────────────────────────────────────────────────────────────────────

# ── SEARCH CRITERIA ───────────────────────────────────────────────────────────
SEARCH = {
    "cities":       ["Port St. Lucie", "Fort Pierce"],
    "state":        "FL",
    "county":       "St. Lucie",
    # All St. Lucie County zip codes (PSL + Fort Pierce + unincorporated)
    "zip_codes":    ["34983", "34984", "34986", "34952", "34982",
                     "34950", "34987", "34988", "34990", "34994"],
    "min_price":    190_000,
    "max_price":    250_000,
    "min_beds":     3,
    "min_baths":    2.0,
    "min_sqft":     1_540,
    "property_type": "Single Family",   # Rentcast filter value
    "stories":      1,                  # Applied as post-filter when data available
    "max_dom":      90,                 # Ignore stale listings over 90 days
    "exclude_hoa":  False,              # Set True to skip HOA properties if detectable
}

# ── ARV & DEAL MATH ───────────────────────────────────────────────────────────
DEAL = {
    # Conservative ARV estimate for PSL renovated 3/2 CBS (MLS-confirmed $/SF)
    # Based on closed comps May 2026: Hutchins $167/SF, Carter $199/SF, Exmore $195/SF
    "arv_per_sqft_conservative": 215,   # low end (use this for scoring)
    "arv_per_sqft_optimistic":   235,   # high end

    # Cap ARV SF at 2,000 — very large homes don't scale linearly in PSL
    "arv_sqft_cap": 2_000,

    # 70% rule: MAO = (ARV × 0.70) − Rehab
    "arv_rule_pct": 0.70,

    # Rehab estimates by year built (mid-range, CBS construction)
    "rehab_estimate": {
        "before_1990": 80_000,    # Pre-1990: full systems likely original
        "1990_to_1999": 65_000,   # 1990s: polybutylene plumbing era, original HVAC
        "2000_to_2009": 50_000,   # 2000s: better bones, still needs cosmetic + systems
        "2010_plus":    38_000,   # 2010+: lighter scope usually
    },

    # Deal grading thresholds (net profit after all costs)
    "grade_a_profit":  40_000,    # A-grade: send immediate alert
    "grade_b_profit":  25_000,    # B-grade: include in daily digest
    "grade_c_profit":  10_000,    # C-grade: include in daily digest
    # Below grade_c_profit → D (skip or log only)

    # Holding/transaction cost assumptions (on top of rehab)
    "buy_closing_pct":  0.025,    # 2.5% of purchase price
    "sell_closing_pct": 0.07,     # 7% of ARV (agent + title + taxes)
    "hold_costs":       8_400,    # 6-month hold: taxes, insurance, utilities
}

# ── EMAIL SETTINGS ────────────────────────────────────────────────────────────
EMAIL = {
    "recipient":    "jsantiagorealtor@gmail.com",
    "sender":       "alerts@fixflipagent.io",   # Must be a SendGrid-verified sender
    "sender_name":  "Fix & Flip Agent — St. Lucie",
    "subject_on":   "🏠 On-Market Fix & Flip Deals — St. Lucie County",
    "subject_off":  "🔑 Off-Market Fix & Flip Leads — St. Lucie County",
    "subject_both": "🏠 Daily Fix & Flip Deal Report — St. Lucie County, FL",
}

# ── PASLC SCRAPER SETTINGS ────────────────────────────────────────────────────
PASLC = {
    "base_url":         "https://www.paslc.gov",
    "search_path":      "/RESearch.aspx",       # Adjust if site structure differs
    "rate_limit_secs":  2.0,                    # Seconds between requests (be respectful)
    "max_results":      200,                    # Max off-market leads per run
    # Land use codes for single-family residential in FL CAMA systems
    "sfr_land_use_codes": ["01", "001", "0100", "0101", "SFR", "RES"],
    # PSL subdivisions/sections to target (high investor activity)
    "target_sections": [
        "PORT ST LUCIE SEC 28", "PORT ST LUCIE SEC 04",
        "PORT ST LUCIE SEC 13", "PORT ST LUCIE SEC 17",
        "PORT ST LUCIE SEC 21", "PORT ST LUCIE SEC 33",
        "PORT ST LUCIE SEC 36", "PORT ST LUCIE SEC 40",
    ],
}

# ── RENTCAST API SETTINGS ─────────────────────────────────────────────────────
RENTCAST = {
    "base_url":  "https://api.rentcast.io/v1",
    "limit":     500,       # Max results per call
    # Free tier = 50 calls/month. 2 cities × every-other-day = 30 calls/mo ✓
    # Upgrade to $29/mo paid tier for true daily alerts.
}
