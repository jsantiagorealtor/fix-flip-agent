#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# main.py  —  Fix & Flip Agent Orchestrator
#
# Run manually:   python main.py
# Run on-market only:   python main.py --on-market-only
# Run off-market only:  python main.py --off-market-only
# Dry run (no email):   python main.py --dry-run
#
# Scheduled automatically via GitHub Actions (.github/workflows/daily_search.yml)
# ─────────────────────────────────────────────────────────────────────────────
import os
import sys
import logging
import argparse
from datetime import datetime

from rentcast_agent  import fetch_on_market_listings
from paslc_scraper   import fetch_off_market_leads
from deal_scorer     import filter_and_score
from email_sender    import send_deal_report

# ── LOGGING ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S",
    handlers= [logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")


def run(on_market: bool = True, off_market: bool = True, dry_run: bool = False):
    start = datetime.now()
    logger.info("=" * 60)
    logger.info("  FIX & FLIP AGENT  —  St. Lucie County, FL")
    logger.info(f"  Started: {start.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # ── Step 1: Fetch On-Market via Rentcast ──────────────────────────────────
    on_market_raw    = []
    on_market_scored = []

    if on_market:
        logger.info("\n▶ Step 1: Fetching on-market listings (Rentcast)...")
        try:
            on_market_raw    = fetch_on_market_listings()
            on_market_scored = filter_and_score(on_market_raw)
            logger.info(f"  On-market: {len(on_market_raw)} fetched → "
                        f"{len(on_market_scored)} A/B/C deals")
        except Exception as e:
            logger.error(f"  On-market fetch failed: {e}")

    # ── Step 2: Scrape Off-Market from PASLC ──────────────────────────────────
    off_market_raw    = []
    off_market_scored = []

    if off_market:
        logger.info("\n▶ Step 2: Scraping off-market leads (PASLC)...")
        try:
            off_market_raw    = fetch_off_market_leads()
            off_market_scored = filter_and_score(off_market_raw)
            logger.info(f"  Off-market: {len(off_market_raw)} scraped → "
                        f"{len(off_market_scored)} A/B/C deals")
        except Exception as e:
            logger.error(f"  Off-market scrape failed: {e}")

    # ── Step 3: Summary ───────────────────────────────────────────────────────
    all_deals = on_market_scored + off_market_scored
    a_deals   = [d for d in all_deals if d["grade"] == "A"]
    b_deals   = [d for d in all_deals if d["grade"] == "B"]
    c_deals   = [d for d in all_deals if d["grade"] == "C"]

    logger.info(f"\n── Deal Summary ─────────────────────────────────────")
    logger.info(f"  A-grade (profit ≥ $40K):  {len(a_deals)}")
    logger.info(f"  B-grade (profit ≥ $25K):  {len(b_deals)}")
    logger.info(f"  C-grade (profit ≥ $10K):  {len(c_deals)}")
    logger.info(f"  Total qualifying deals:   {len(all_deals)}")

    if a_deals:
        logger.info("\n  ⭐ A-GRADE DEALS:")
        for d in a_deals:
            logger.info(f"    {d['address']} | ${d['price']:,} list | "
                        f"ARV ~${d['arv_conservative']:,} | Profit ~${d['net_profit']:,}")

    # ── Step 4: Send Email ────────────────────────────────────────────────────
    if dry_run:
        logger.info("\n▶ DRY RUN — Email not sent. Here's what would be sent:")
        for d in (on_market_scored + off_market_scored)[:3]:
            logger.info(f"  [{d['grade']}] {d['address']} | "
                        f"${d['price']:,} → profit ~${d['net_profit']:,} | {d['source']}")
    else:
        if all_deals:
            logger.info("\n▶ Step 3: Sending email report...")
            success = send_deal_report(on_market_scored, off_market_scored)
            if success:
                logger.info("  Email sent successfully ✓")
            else:
                logger.error("  Email failed — check SENDGRID_API_KEY")
                sys.exit(1)
        else:
            logger.info("\n  No qualifying deals found today — no email sent.")

    elapsed = (datetime.now() - start).seconds
    logger.info(f"\n✓ Agent finished in {elapsed}s")
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fix & Flip Property AI Agent")
    parser.add_argument("--on-market-only",  action="store_true",
                        help="Only run Rentcast on-market search")
    parser.add_argument("--off-market-only", action="store_true",
                        help="Only run PASLC off-market scraper")
    parser.add_argument("--dry-run",         action="store_true",
                        help="Run everything but don't send the email")
    args = parser.parse_args()

    run(
        on_market  = not args.off_market_only,
        off_market = not args.on_market_only,
        dry_run    = args.dry_run,
    )
