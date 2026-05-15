# ─────────────────────────────────────────────────────────────────────────────
# deal_scorer.py  —  70% Rule calculator + deal grader
# ─────────────────────────────────────────────────────────────────────────────
from config import DEAL


def estimate_arv(sqft: int) -> dict:
    """Estimate ARV using $/SF benchmarks from closed PSL comps (May 2026)."""
    capped_sqft = min(sqft, DEAL["arv_sqft_cap"])
    return {
        "conservative": round(capped_sqft * DEAL["arv_per_sqft_conservative"]),
        "optimistic":   round(capped_sqft * DEAL["arv_per_sqft_optimistic"]),
    }


def estimate_rehab(year_built: int) -> int:
    """Return mid-range rehab estimate based on home age."""
    if not year_built or year_built == 0:
        return DEAL["rehab_estimate"]["1990_to_1999"]  # default to middle bucket
    if year_built < 1990:
        return DEAL["rehab_estimate"]["before_1990"]
    elif year_built < 2000:
        return DEAL["rehab_estimate"]["1990_to_1999"]
    elif year_built < 2010:
        return DEAL["rehab_estimate"]["2000_to_2009"]
    else:
        return DEAL["rehab_estimate"]["2010_plus"]


def calculate_mao(arv: int, rehab: int) -> int:
    """Maximum Allowable Offer using the 70% rule."""
    return round(arv * DEAL["arv_rule_pct"] - rehab)


def calculate_profit(purchase: int, arv: int, rehab: int) -> dict:
    """
    Full deal P&L:
      Net Profit = ARV − Purchase − Rehab − Buy Closing − Sell Closing − Hold Costs
    """
    buy_closing  = round(purchase * DEAL["buy_closing_pct"])
    sell_closing = round(arv * DEAL["sell_closing_pct"])
    hold         = DEAL["hold_costs"]
    total_cost   = purchase + rehab + buy_closing + sell_closing + hold
    net_profit   = arv - total_cost
    roi          = net_profit / total_cost if total_cost > 0 else 0
    return {
        "purchase":     purchase,
        "rehab":        rehab,
        "buy_closing":  buy_closing,
        "sell_closing": sell_closing,
        "hold_costs":   hold,
        "total_cost":   total_cost,
        "net_profit":   net_profit,
        "roi_pct":      round(roi * 100, 1),
    }


def grade_deal(net_profit: int) -> str:
    """Assign A/B/C/D grade based on projected profit."""
    if net_profit >= DEAL["grade_a_profit"]:
        return "A"
    elif net_profit >= DEAL["grade_b_profit"]:
        return "B"
    elif net_profit >= DEAL["grade_c_profit"]:
        return "C"
    else:
        return "D"


def score_property(prop: dict) -> dict:
    """
    Full scoring pipeline for a single property dict.

    Expected prop keys:
        address, city, state, zip_code, price (list price),
        bedrooms, bathrooms, square_footage, year_built,
        days_on_market, source (rentcast | paslc), listing_url
    """
    price   = prop.get("price", 0)
    sqft    = prop.get("square_footage", 0)
    yr_blt  = prop.get("year_built", 0)

    arv_est  = estimate_arv(sqft)
    arv_cons = arv_est["conservative"]
    arv_opt  = arv_est["optimistic"]
    rehab    = estimate_rehab(yr_blt)
    mao      = calculate_mao(arv_cons, rehab)
    pl       = calculate_profit(price, arv_cons, rehab)
    grade    = grade_deal(pl["net_profit"])

    return {
        **prop,
        "arv_conservative": arv_cons,
        "arv_optimistic":   arv_opt,
        "rehab_estimate":   rehab,
        "mao":              mao,
        "at_or_below_mao":  price <= mao,
        **pl,
        "grade":            grade,
        "alert_now":        grade in ("A", "B"),
    }


def filter_and_score(properties: list) -> list:
    """Score all properties, discard D-grades, sort by net profit descending."""
    scored = [score_property(p) for p in properties]
    viable = [p for p in scored if p["grade"] != "D"]
    return sorted(viable, key=lambda x: x["net_profit"], reverse=True)
