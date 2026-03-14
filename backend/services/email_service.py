import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid, formataddr
from database import DB_PATH
import aiosqlite
import logging
from html import escape
from datetime import datetime

logger = logging.getLogger(__name__)


async def get_smtp_config():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT key, value FROM app_settings WHERE key LIKE 'smtp_%'"
        ) as cur:
            rows = await cur.fetchall()
    return {r["key"]: r["value"] for r in rows}


async def get_saved_articles_for_digest(user_id: int):
    """Returns (saved_articles_list, new_since_last_digest_count)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT last_sent FROM digest_schedule WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        last_sent = row["last_sent"] if row and row["last_sent"] else None

        async with db.execute("""
            SELECT a.title, a.url, a.source, a.published_at,
                   a.ai_summary, a.summary,
                   t.name as topic_name, t.icon as topic_icon,
                   sa.saved_at
            FROM saved_articles sa
            JOIN articles a ON a.id = sa.article_id
            LEFT JOIN topics t ON a.topic_id = t.id
            WHERE sa.user_id = ?
            ORDER BY sa.saved_at DESC
            LIMIT 20
        """, (user_id,)) as cur:
            saved = [dict(r) for r in await cur.fetchall()]

        if last_sent:
            async with db.execute(
                "SELECT COUNT(*) as c FROM saved_articles WHERE user_id = ? AND saved_at > ?",
                (user_id, last_sent)
            ) as cur:
                new_count = (await cur.fetchone())["c"]
        else:
            new_count = len(saved)

    return saved, new_count


async def send_password_reset_email(to_email: str, token: str):
    """Send a password reset link to the user."""
    config = await get_smtp_config()

    if not config.get("smtp_host") or not config.get("smtp_user"):
        raise RuntimeError("SMTP is not configured — cannot send password reset email.")

    # Build the reset URL from site_url setting, fallback to smtp_from domain
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT value FROM app_settings WHERE key = 'site_url'") as cur:
            row = await cur.fetchone()
    site_url = (row["value"] if row else "").rstrip("/")
    if not site_url:
        # Derive a best-effort URL from the from address domain
        from_addr = config.get("smtp_from") or config.get("smtp_user", "")
        domain = from_addr.split("@")[-1] if "@" in from_addr else "localhost"
        site_url = f"http://{domain}"

    reset_url = f"{site_url}/reset-password?token={token}"

    smtp_from = config.get("smtp_from") or config["smtp_user"]
    if "<" in smtp_from and ">" in smtp_from:
        display = smtp_from[:smtp_from.index("<")].strip()
        addr = smtp_from[smtp_from.index("<")+1:smtp_from.index(">")].strip()
        from_formatted = formataddr((display, addr))
        from_domain = addr.split("@")[-1]
    else:
        from_formatted = formataddr(("NewsFlow", smtp_from))
        from_domain = smtp_from.split("@")[-1]

    plain = (
        "Password Reset Request\n"
        "======================\n\n"
        "You requested a password reset for your NewsFlow account.\n\n"
        f"Reset your password here:\n{reset_url}\n\n"
        "This link expires in 1 hour. If you did not request this, ignore this email.\n\n"
        "— NewsFlow"
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Reset your NewsFlow password</title>
</head>
<body style="margin:0;padding:0;background:#f5f7fb;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" bgcolor="#f5f7fb">
  <tr><td align="center" style="padding:40px 20px;">
  <table width="520" cellpadding="0" cellspacing="0" style="max-width:520px;">
    <tr><td style="background:#1a1a2e;border-radius:16px;padding:32px;text-align:center;">
      <div style="font-size:32px;margin-bottom:8px;">📰</div>
      <h1 style="color:#fff;margin:0;font-size:24px;font-weight:700;">NewsFlow</h1>
    </td></tr>
    <tr><td style="background:#fff;border-radius:12px;padding:32px;margin-top:16px;box-shadow:0 2px 8px rgba(0,0,0,0.07);">
      <h2 style="margin:0 0 16px;font-size:20px;color:#1a1a2e;">Reset your password</h2>
      <p style="color:#555;font-size:15px;line-height:1.6;margin:0 0 24px;">
        We received a request to reset your NewsFlow password.
        Click the button below to choose a new one.
      </p>
      <div style="text-align:center;margin:0 0 24px;">
        <a href="{escape(reset_url)}"
           style="display:inline-block;background:#3b5bdb;color:#fff;font-size:15px;
                  font-weight:600;padding:14px 32px;border-radius:8px;text-decoration:none;">
          Reset Password
        </a>
      </div>
      <p style="color:#888;font-size:13px;line-height:1.6;margin:0;">
        This link expires in <strong>1 hour</strong>. If you didn't request a password reset,
        you can safely ignore this email — your password won't change.
      </p>
    </td></tr>
    <tr><td style="text-align:center;padding:20px 0;color:#aaa;font-size:12px;">
      Powered by NewsFlow
    </td></tr>
  </table>
  </td></tr>
</table>
</body>
</html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Reset your NewsFlow password"
    msg["From"] = from_formatted
    msg["To"] = to_email
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=from_domain)

    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    await aiosmtplib.send(
        msg,
        hostname=config["smtp_host"],
        port=int(config.get("smtp_port", 587)),
        username=config["smtp_user"],
        password=config["smtp_password"],
        start_tls=True,
    )
    logger.info(f"Password reset email sent to {to_email}")


async def send_digest_email(to_email: str, username: str, user_id: int, articles: list, intro: str):
    config = await get_smtp_config()

    if not config.get("smtp_host") or not config.get("smtp_user"):
        logger.warning("SMTP not configured, skipping email")
        return

    saved_data = await get_saved_articles_for_digest(user_id)
    html = build_digest_html(username, articles, intro, saved_data)
    plain = build_digest_plain(username, articles, intro, saved_data)

    smtp_from = config.get("smtp_from") or config["smtp_user"]
    if "<" in smtp_from and ">" in smtp_from:
        display = smtp_from[:smtp_from.index("<")].strip()
        addr = smtp_from[smtp_from.index("<")+1:smtp_from.index(">")].strip()
        from_formatted = formataddr((display, addr))
        from_domain = addr.split("@")[-1]
    else:
        from_formatted = formataddr(("NewsFlow", smtp_from))
        from_domain = smtp_from.split("@")[-1]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Your NewsFlow Digest — {datetime.utcnow().strftime('%B %d, %Y')}"
    msg["From"] = from_formatted
    msg["To"] = to_email
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=from_domain)
    msg["MIME-Version"] = "1.0"
    msg["X-Mailer"] = "NewsFlow"

    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=config["smtp_host"],
            port=int(config.get("smtp_port", 587)),
            username=config["smtp_user"],
            password=config["smtp_password"],
            start_tls=True,
        )
        logger.info(f"Digest sent to {to_email}")
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        raise


def build_digest_plain(username: str, articles: list, intro: str, saved_data=None) -> str:
    date_str = datetime.utcnow().strftime("%A, %B %d, %Y")
    lines = [
        f"NEWSFLOW DIGEST — {date_str}",
        "=" * 40,
        "",
        f"Good morning, {escape(username)}!",
        "",
        intro,
        "",
        "TODAY'S TOP STORIES",
        "-" * 40,
    ]
    for i, a in enumerate(articles[:15], 1):
        lines.append("")
        lines.append(f"{i}. {a['title']}")
        lines.append(f"   {a.get('source', '')} | {a['url']}")
        summary = a.get("ai_summary") or a.get("summary") or ""
        if summary:
            lines.append(f"   {summary[:200]}")

    if saved_data:
        saved, new_count = saved_data
        if saved:
            lines += ["", "=" * 40, "YOUR READ LATER LIST", "-" * 40]
            if new_count > 0:
                noun = "article" if new_count == 1 else "articles"
                lines.append(f"{new_count} {noun} added since your last digest.")
            lines.append("")
            for i, a in enumerate(saved[:10], 1):
                lines.append(f"{i}. {a['title']}")
                lines.append(f"   {a.get('source', '')} | {a['url']}")
                lines.append(f"   Saved: {str(a.get('saved_at', ''))[:10]}")
                lines.append("")

    lines += [
        "",
        "-" * 40,
        "You're receiving this because you enabled daily digests in NewsFlow.",
        "Powered by NewsFlow.",
    ]
    return "\n".join(lines)


def _saved_cards_html(saved: list) -> str:
    cards = ""
    for article in saved[:10]:
        summary = article.get("ai_summary") or article.get("summary") or ""
        summary_html = (
            f'<p style="color:#777777;font-size:13px;line-height:1.6;margin:6px 0 10px;">'
            f'{escape(summary[:150])}...</p>'
        ) if summary else ""
        saved_date = str(article.get("saved_at", ""))[:10]
        icon = article.get("topic_icon", "📰")
        topic = article.get("topic_name", "Saved")
        cards += (
            f'<table width="100%" cellpadding="0" cellspacing="0" style="background:#fff8f0;'
            f'border:1px solid #ffe4c0;border-radius:10px;margin-bottom:12px;">'
            f'<tr><td style="padding:16px;">'
            f'<div style="display:inline-block;background:#fff0dc;color:#e07b00;font-size:10px;'
            f'font-weight:700;padding:2px 7px;border-radius:20px;margin-bottom:7px;">'
            f'&#128278; {icon} {topic}</div>'
            f'<h3 style="margin:0 0 6px;font-size:15px;line-height:1.4;color:#1a1a2e;">'
            f'<a href="{escape(article["url"])}" style="color:#1a1a2e;text-decoration:none;">{escape(article["title"])}</a>'
            f'</h3>'
            f'{summary_html}'
            f'<table width="100%" cellpadding="0" cellspacing="0"><tr>'
            f'<td style="color:#999999;font-size:11px;">{article.get("source","")} &middot; saved {saved_date}</td>'
            f'<td align="right"><a href="{article["url"]}" style="color:#e07b00;font-size:12px;'
            f'font-weight:600;text-decoration:none;">Read &rarr;</a></td>'
            f'</tr></table>'
            f'</td></tr></table>'
        )
    return cards


def _read_later_section_html(saved_data) -> str:
    if not saved_data:
        return ""
    saved, new_count = saved_data
    if not saved:
        return ""

    if new_count > 0:
        noun = "article" if new_count == 1 else "articles"
        rl_intro = (
            f"You've added <strong>{new_count} {noun}</strong> to your Read Later list "
            f"since your last digest. Here's everything waiting for you:"
        )
    else:
        total = len(saved)
        tnoun = "article" if total == 1 else "articles"
        rl_intro = f"You have <strong>{total} {tnoun}</strong> waiting in your Read Later list:"

    cards_html = _saved_cards_html(saved)
    return (
        '<tr><td style="padding-top:8px;"></td></tr>'
        '<tr><td>'
        '<h2 style="font-size:14px;font-weight:700;color:#1a1a2e;margin:0 0 12px;'
        'text-transform:uppercase;letter-spacing:0.5px;">&#128278; Read Later</h2>'
        '<table width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#fffbf5;border-radius:12px;margin-bottom:16px;">'
        '<tr><td style="padding:16px 20px 8px;">'
        f'<p style="margin:0 0 16px;color:#555555;font-size:14px;line-height:1.6;">{rl_intro}</p>'
        f'{cards_html}'
        '</td></tr></table>'
        '</td></tr>'
    )


def build_digest_html(username: str, articles: list, intro: str, saved_data=None) -> str:
    date_str = datetime.utcnow().strftime("%A, %B %d, %Y")

    article_cards = ""
    for article in articles[:15]:
        image_html = ""
        if article.get("image_url"):
            image_html = (
                f'<img src="{article["image_url"]}" alt="" style="width:100%;max-height:200px;'
                f'object-fit:cover;border-radius:8px;margin-bottom:12px;">'
            )
        summary = article.get("ai_summary") or article.get("summary") or ""
        summary_html = (
            f'<p style="color:#555555;font-size:14px;line-height:1.6;margin:8px 0;">{summary[:200]}...</p>'
        ) if summary else ""

        article_cards += (
            f'<table width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff;'
            f'border-radius:12px;margin-bottom:16px;box-shadow:0 2px 8px rgba(0,0,0,0.08);">'
            f'<tr><td style="padding:20px;">'
            f'{image_html}'
            f'<div style="display:inline-block;background:#f0f4ff;color:#4f6ef7;font-size:11px;'
            f'font-weight:600;padding:3px 8px;border-radius:20px;margin-bottom:8px;">'
            f'{escape(str(article.get("topic_icon","📰")))} {escape(str(article.get("topic_name","News")))}</div>'
            f'<h3 style="margin:0 0 8px;font-size:17px;line-height:1.4;color:#1a1a2e;">'
            f'<a href="{escape(article["url"])}" style="color:#1a1a2e;text-decoration:none;">{escape(article["title"])}</a>'
            f'</h3>'
            f'{summary_html}'
            f'<table width="100%" cellpadding="0" cellspacing="0"><tr>'
            f'<td style="color:#999999;font-size:12px;">{article.get("source","")}</td>'
            f'<td align="right"><a href="{article["url"]}" style="color:#4f6ef7;font-size:13px;'
            f'font-weight:600;text-decoration:none;">Read &rarr;</a></td>'
            f'</tr></table></td></tr></table>'
        )

    read_later_section = _read_later_section_html(saved_data)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
  <title>NewsFlow Digest</title>
</head>
<body style="margin:0;padding:0;background-color:#f5f7fb;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" bgcolor="#f5f7fb">
  <tr><td align="center" style="padding:20px;">
  <table width="620" cellpadding="0" cellspacing="0" style="max-width:620px;">

    <tr><td style="background:#1a1a2e;border-radius:16px;padding:32px;text-align:center;">
      <div style="font-size:32px;margin-bottom:8px;">&#128240;</div>
      <h1 style="color:#ffffff;margin:0;font-size:28px;font-weight:700;">NewsFlow</h1>
      <p style="color:rgba(255,255,255,0.6);margin:8px 0 0;font-size:14px;">{date_str}</p>
    </td></tr>

    <tr><td style="padding-top:24px;"></td></tr>

    <tr><td style="background:#ffffff;border-radius:12px;padding:24px;box-shadow:0 2px 8px rgba(0,0,0,0.06);">
      <p style="margin:0 0 12px;font-size:18px;font-weight:600;color:#1a1a2e;">Good morning, {escape(username)}!</p>
      <p style="margin:0;color:#555555;font-size:15px;line-height:1.7;">{intro}</p>
    </td></tr>

    <tr><td style="padding-top:20px;"></td></tr>

    <tr><td>
      <h2 style="font-size:14px;font-weight:700;color:#1a1a2e;margin:0 0 16px;text-transform:uppercase;letter-spacing:0.5px;">
        Today&#39;s Top Stories
      </h2>
    </td></tr>

    <tr><td>{article_cards}</td></tr>

    {read_later_section}

    <tr><td style="text-align:center;padding:24px 0;color:#aaaaaa;font-size:12px;">
      <p style="margin:0;">You&#39;re receiving this because you enabled daily digests in NewsFlow.</p>
      <p style="margin:8px 0 0;">Powered by NewsFlow</p>
    </td></tr>

  </table>
  </td></tr>
</table>
</body>
</html>"""
