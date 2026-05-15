# ─────────────────────────────────────────────────────────────────────────────
# email_sender.py  —  SendGrid HTML email delivery
#
# Sign up free at: https://sendgrid.com  (100 emails/day free forever)
# After signup:
#   1. Settings → API Keys → Create API Key (Full Access)
#   2. Settings → Sender Authentication → verify your sender email
#   3. Add SENDGRID_API_KEY to GitHub Secrets
# ─────────────────────────────────────────────────────────────────────────────
import os
import logging
from datetime import date
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Content
from config import EMAIL

logger = logging.getLogger(__name__)

# ── GRADE STYLING ──────────────────────────────────────────────────────────────
GRADE_STYLE = {
    "A": {"bg": "#E8F5E9", "border": "#2E7D32", "badge_bg": "#2E7D32", "label": "A-GRADE DEAL"},
    "B": {"bg": "#E3F2FD", "border": "#1565C0", "badge_bg": "#1565C0", "label": "B-GRADE DEAL"},
    "C": {"bg": "#FFF8E1", "border": "#E65100", "badge_bg": "#E65100", "label": "C-GRADE DEAL"},
}


def _fmt_money(n: int) -> str:
    return f"${n:,}"


def _profit_color(profit: int) -> str:
    if profit >= 40_000: return "#2E7D32"
    if profit >= 25_000: return "#1565C0"
    if profit >= 10_000: return "#E65100"
    return "#C62828"


def _property_card(prop: dict, index: int) -> str:
    """Render a single property as an HTML card block."""
    grade = prop.get("grade", "C")
    gs    = GRADE_STYLE.get(grade, GRADE_STYLE["C"])
    src   = prop.get("source", "")
    is_off = (src == "paslc")

    # Header flags
    flags = []
    if prop.get("absentee_owner"):
        flags.append('<span style="background:#6A1B9A;color:#fff;padding:2px 8px;border-radius:3px;font-size:11px;font-weight:700;margin-right:4px;">ABSENTEE OWNER</span>')
    if prop.get("at_or_below_mao"):
        flags.append('<span style="background:#2E7D32;color:#fff;padding:2px 8px;border-radius:3px;font-size:11px;font-weight:700;margin-right:4px;">AT/BELOW MAO ✓</span>')
    if prop.get("pool"):
        flags.append('<span style="background:#0277BD;color:#fff;padding:2px 8px;border-radius:3px;font-size:11px;font-weight:700;">HAS POOL</span>')

    flag_html = " ".join(flags)

    dom_str   = f'{prop.get("days_on_market", 0)} DOM' if not is_off else "Off-Market"
    yr        = prop.get("year_built", 0)
    yr_str    = str(yr) if yr else "Unknown"

    stories_raw = prop.get("stories")
    stories_str = f"{int(stories_raw)}-story" if stories_raw else "1-story (assumed)"

    link_url  = prop.get("listing_url", "")
    link_html = (f'<a href="{link_url}" style="color:#1565C0;font-size:12px;">View Listing →</a>'
                 if link_url else "")
    if is_off and prop.get("parcel"):
        link_html += (f' &nbsp;|&nbsp; <a href="{PASLC_URL}/{prop["parcel"]}" '
                      f'style="color:#6A1B9A;font-size:12px;">PASLC Record →</a>')

    return f"""
    <div style="border:2px solid {gs['border']};border-radius:8px;margin-bottom:16px;
                background:{gs['bg']};overflow:hidden;">
      <!-- Card Header -->
      <div style="background:{gs['badge_bg']};padding:8px 14px;display:flex;
                  justify-content:space-between;align-items:center;">
        <span style="color:#fff;font-weight:700;font-size:13px;">
          #{index} — {gs['label']}
        </span>
        <span style="color:#fff;font-size:12px;opacity:0.9;">
          {'🔑 OFF-MARKET' if is_off else '🏠 ON-MARKET'}
        </span>
      </div>
      <!-- Address + Flags -->
      <div style="padding:12px 14px 4px;">
        <div style="font-size:16px;font-weight:700;color:#1B2A4A;margin-bottom:4px;">
          {prop.get('address','N/A')}
        </div>
        <div style="font-size:13px;color:#555;margin-bottom:8px;">
          {prop.get('city','')}, {prop.get('state','FL')}  &nbsp;|&nbsp;  {dom_str}
        </div>
        <div style="margin-bottom:8px;">{flag_html}</div>
      </div>
      <!-- Stats Grid -->
      <div style="padding:4px 14px 12px;display:flex;flex-wrap:wrap;gap:8px;">

        <!-- Left column: property facts -->
        <div style="flex:1;min-width:180px;background:#fff;border-radius:6px;padding:10px 12px;">
          <div style="font-size:11px;color:#888;font-weight:700;margin-bottom:6px;
                      text-transform:uppercase;letter-spacing:0.5px;">Property</div>
          <table style="width:100%;border-collapse:collapse;font-size:13px;">
            <tr><td style="color:#555;padding:2px 0;">List Price</td>
                <td style="font-weight:700;color:#1B2A4A;text-align:right;">{_fmt_money(prop.get('price',0))}</td></tr>
            <tr><td style="color:#555;padding:2px 0;">Beds / Baths</td>
                <td style="font-weight:700;color:#1B2A4A;text-align:right;">
                  {prop.get('bedrooms',0)} bed / {prop.get('bathrooms',0)} bath</td></tr>
            <tr><td style="color:#555;padding:2px 0;">Size</td>
                <td style="font-weight:700;color:#1B2A4A;text-align:right;">
                  {prop.get('square_footage',0):,} SF</td></tr>
            <tr><td style="color:#555;padding:2px 0;">Year Built</td>
                <td style="font-weight:700;color:#1B2A4A;text-align:right;">{yr_str}</td></tr>
            <tr><td style="color:#555;padding:2px 0;">Stories</td>
                <td style="font-weight:700;color:#1B2A4A;text-align:right;">{stories_str}</td></tr>
          </table>
        </div>

        <!-- Middle column: deal math -->
        <div style="flex:1;min-width:180px;background:#fff;border-radius:6px;padding:10px 12px;">
          <div style="font-size:11px;color:#888;font-weight:700;margin-bottom:6px;
                      text-transform:uppercase;letter-spacing:0.5px;">Deal Math (70% Rule)</div>
          <table style="width:100%;border-collapse:collapse;font-size:13px;">
            <tr><td style="color:#555;padding:2px 0;">Est. ARV</td>
                <td style="font-weight:700;color:#1B2A4A;text-align:right;">
                  {_fmt_money(prop.get('arv_conservative',0))}–{_fmt_money(prop.get('arv_optimistic',0))}</td></tr>
            <tr><td style="color:#555;padding:2px 0;">Est. Rehab</td>
                <td style="font-weight:700;color:#E65100;text-align:right;">
                  {_fmt_money(prop.get('rehab_estimate',0))}</td></tr>
            <tr><td style="color:#555;padding:2px 0;">Your MAO</td>
                <td style="font-weight:700;color:#1B2A4A;text-align:right;">
                  {_fmt_money(prop.get('mao',0))}</td></tr>
            <tr><td style="color:#555;padding:2px 0;">All-In Cost</td>
                <td style="font-weight:700;color:#1B2A4A;text-align:right;">
                  {_fmt_money(prop.get('total_cost',0))}</td></tr>
          </table>
        </div>

        <!-- Right column: profit -->
        <div style="flex:1;min-width:150px;background:{gs['bg']};border:1.5px solid {gs['border']};
                    border-radius:6px;padding:10px 12px;text-align:center;">
          <div style="font-size:11px;color:#888;font-weight:700;margin-bottom:4px;
                      text-transform:uppercase;letter-spacing:0.5px;">Est. Net Profit</div>
          <div style="font-size:28px;font-weight:700;color:{_profit_color(prop.get('net_profit',0))};">
            {_fmt_money(prop.get('net_profit',0))}
          </div>
          <div style="font-size:13px;color:#555;margin-top:4px;">
            ROI: <strong>{prop.get('roi_pct',0)}%</strong>
          </div>
          <div style="margin-top:8px;">{link_html}</div>
        </div>

      </div>
    </div>"""


def _build_html_body(on_market: list, off_market: list) -> str:
    today = date.today().strftime("%B %d, %Y")
    a_count = sum(1 for p in on_market + off_market if p.get("grade") == "A")

    cards_on  = "".join(_property_card(p, i+1) for i, p in enumerate(on_market))
    cards_off = "".join(_property_card(p, i+1) for i, p in enumerate(off_market))

    on_section = f"""
    <h2 style="color:#1B2A4A;font-size:16px;margin:24px 0 8px;border-bottom:2px solid #C9A84C;
               padding-bottom:4px;">🏠 ON-MARKET DEALS ({len(on_market)} found)</h2>
    {cards_on if cards_on else '<p style="color:#888;font-style:italic;">No qualifying on-market listings found today.</p>'}
    """ if on_market is not None else ""

    off_section = f"""
    <h2 style="color:#1B2A4A;font-size:16px;margin:24px 0 8px;border-bottom:2px solid #6A1B9A;
               padding-bottom:4px;">🔑 OFF-MARKET LEADS ({len(off_market)} found)</h2>
    {cards_off if cards_off else '<p style="color:#888;font-style:italic;">No qualifying off-market leads found today.</p>'}
    """ if off_market is not None else ""

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;max-width:760px;margin:0 auto;padding:0;background:#f5f5f5;">

  <!-- HEADER -->
  <div style="background:#1B2A4A;padding:20px 24px;border-radius:8px 8px 0 0;">
    <div style="color:#C9A84C;font-size:20px;font-weight:700;margin-bottom:4px;">
      Fix &amp; Flip Deal Agent
    </div>
    <div style="color:#fff;font-size:14px;">St. Lucie County, FL &nbsp;|&nbsp; {today}</div>
    {f'<div style="background:#2E7D32;color:#fff;display:inline-block;padding:4px 12px;border-radius:4px;font-size:12px;font-weight:700;margin-top:8px;">⭐ {a_count} A-GRADE DEAL{"S" if a_count!=1 else ""} TODAY</div>' if a_count > 0 else ''}
  </div>

  <!-- CRITERIA REMINDER -->
  <div style="background:#fff;padding:12px 24px;border-bottom:1px solid #e0e0e0;">
    <span style="font-size:12px;color:#555;">
      <strong>Search criteria:</strong> &nbsp;
      $190K–$250K &nbsp;|&nbsp; 3+ bed / 2+ bath &nbsp;|&nbsp; 1,540+ SF &nbsp;|&nbsp;
      1-story SFR &nbsp;|&nbsp; St. Lucie County, FL
    </span>
  </div>

  <!-- BODY -->
  <div style="background:#f5f5f5;padding:16px 16px;">
    {on_section}
    {off_section}
  </div>

  <!-- FOOTER -->
  <div style="background:#1B2A4A;padding:14px 24px;border-radius:0 0 8px 8px;text-align:center;">
    <p style="color:#aaa;font-size:11px;margin:0;">
      Jose Santiago · Licensed Florida Real Estate Agent · jsantiagorealtor@gmail.com<br>
      ARV and profit estimates are automated projections — always verify with GC bids and pulled comps before committing.<br>
      <a href="mailto:josesantiago105@gmail.com?subject=Unsubscribe Fix Flip Agent"
         style="color:#C9A84C;font-size:10px;">Unsubscribe</a>
      &nbsp;|&nbsp; <a href="mailto:jsantiagorealtor@gmail.com"
         style="color:#C9A84C;font-size:10px;">jsantiagorealtor@gmail.com</a>
    </p>
  </div>

</body></html>"""


def send_deal_report(on_market: list, off_market: list) -> bool:
    """
    Send the HTML deal report via SendGrid.
    Returns True on success, False on failure.
    """
    api_key = os.environ.get("SENDGRID_API_KEY", "")
    if not api_key:
        raise EnvironmentError("SENDGRID_API_KEY secret is not set.")

    total = len(on_market) + len(off_market)
    if total == 0:
        logger.info("No qualifying deals found — skipping email.")
        return True

    html_body = _build_html_body(on_market, off_market)

    a_count = sum(1 for p in on_market + off_market if p.get("grade") == "A")
    subject = EMAIL["subject_both"]
    if a_count > 0:
        subject = f"⭐ {a_count} A-GRADE DEAL{'S' if a_count>1 else ''} — " + subject

    message = Mail(
        from_email  = (EMAIL["sender"], EMAIL["sender_name"]),
        to_emails   = EMAIL["recipient"],
        subject     = subject,
        html_content= Content("text/html", html_body),
    )

    try:
        sg   = SendGridAPIClient(api_key)
        resp = sg.send(message)
        logger.info(f"Email sent. Status: {resp.status_code} | "
                    f"On-market: {len(on_market)} | Off-market: {len(off_market)}")
        return True
    except Exception as e:
        logger.error(f"SendGrid error: {e}")
        return False


# PASLC base URL for record links in email
PASLC_URL = "https://www.paslc.gov/RESearch.aspx?parcel="
