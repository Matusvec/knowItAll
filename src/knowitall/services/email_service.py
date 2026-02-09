"""Email delivery service for knowItAll daily intelligence reports."""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from knowitall.config import EmailConfig

logger = logging.getLogger(__name__)


def _build_digest_html(digest) -> str:
    """Build a simple HTML email body from a DailyDigest."""
    parts: list[str] = [
        "<html><body style='font-family:sans-serif;background:#0d1117;color:#e6edf3;padding:20px'>",
        f"<h1 style='color:#58a6ff'>🧠 {digest.headline}</h1>",
        f"<p>{digest.total_signals()} signals passed the filter today.</p>",
    ]

    if digest.papers:
        parts.append("<h2 style='color:#58a6ff'>📄 Research Signals</h2><ul>")
        for p in digest.papers:
            link = p.project_url or p.pdf_url or ""
            parts.append(
                f"<li><a style='color:#58a6ff' href='{link}'>{p.title}</a>"
                f" — relevance {p.relevance_score:.2f}</li>"
            )
        parts.append("</ul>")

    if digest.startup_ideas:
        parts.append("<h2 style='color:#58a6ff'>🚀 Startup Ideas</h2><ul>")
        for idea in digest.startup_ideas:
            parts.append(f"<li><b>{idea.title}</b>: {idea.core_insight[:200]}</li>")
        parts.append("</ul>")

    if digest.tools:
        parts.append("<h2 style='color:#58a6ff'>🛠 Tech & Tools</h2><ul>")
        for t in digest.tools:
            parts.append(f"<li><b>{t.name}</b> — {t.hype_level.value}</li>")
        parts.append("</ul>")

    if digest.opportunities:
        parts.append("<h2 style='color:#58a6ff'>🎯 Opportunities</h2><ul>")
        for o in digest.opportunities:
            parts.append(f"<li><b>{o.title}</b> — ROI {o.roi_score:.2f}</li>")
        parts.append("</ul>")

    parts.append("</body></html>")
    return "".join(parts)


def _build_scout_html(report) -> str:
    """Build a simple HTML email body from a ScoutReport."""
    parts: list[str] = [
        "<html><body style='font-family:sans-serif;background:#0d1117;color:#e6edf3;padding:20px'>",
        f"<h1 style='color:#58a6ff'>🔍 {report.headline or 'Scout Report'}</h1>",
        f"<p>{report.total_signals()} signals found.</p>",
    ]

    if report.tech_trends:
        parts.append("<h2 style='color:#58a6ff'>📈 Tech Trends</h2><ul>")
        for t in report.tech_trends:
            parts.append(f"<li><b>{t.title}</b> — interest {t.interest_score:.2f}</li>")
        parts.append("</ul>")

    if report.complaints:
        parts.append("<h2 style='color:#58a6ff'>😤 Complaints</h2><ul>")
        for c in report.complaints:
            parts.append(f"<li>{c.summary} — severity {c.severity:.2f}</li>")
        parts.append("</ul>")

    if report.industry_gaps:
        parts.append("<h2 style='color:#58a6ff'>🕳️ Industry Gaps</h2><ul>")
        for g in report.industry_gaps:
            parts.append(f"<li><b>{g.title}</b> — opportunity {g.opportunity_score:.2f}</li>")
        parts.append("</ul>")

    if report.startup_ideas:
        parts.append("<h2 style='color:#58a6ff'>🚀 Startup Ideas</h2><ul>")
        for i in report.startup_ideas:
            parts.append(f"<li><b>{i.title}</b>: {i.description[:200]}</li>")
        parts.append("</ul>")

    parts.append("</body></html>")
    return "".join(parts)


def send_digest_email(
    digest,
    email_cfg: EmailConfig,
    *,
    scout_report=None,
) -> bool:
    """Send the daily digest (and optional scout report) via SMTP.

    Returns True on success, False on failure.
    """
    if not email_cfg.smtp_user or not email_cfg.smtp_password:
        logger.warning("SMTP credentials not configured — skipping email.")
        return False

    body_parts = [_build_digest_html(digest)]
    if scout_report is not None:
        body_parts.append("<hr>")
        body_parts.append(_build_scout_html(scout_report))

    html_body = "".join(body_parts)
    subject = f"knowItAll Daily Intelligence — {digest.headline}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email_cfg.sender or email_cfg.smtp_user
    msg["To"] = email_cfg.recipient
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(email_cfg.smtp_host, email_cfg.smtp_port) as server:
            server.starttls()
            server.login(email_cfg.smtp_user, email_cfg.smtp_password)
            server.sendmail(msg["From"], [email_cfg.recipient], msg.as_string())
        logger.info("Daily digest email sent to %s", email_cfg.recipient)
        return True
    except Exception:
        logger.exception("Failed to send digest email")
        return False
