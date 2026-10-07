"""Sends the failure-analysis email via SMTP."""

import smtplib
import time
from email.message import EmailMessage

import config


def build_email_body(info, analysis):
    """Plain-text email body."""
    now = time.strftime("%Y-%m-%d %H:%M")
    if info.get("allow_failure"):
        kind = "⚠️ Allowed-to-fail job (pipeline shows 'Warning')"
    else:
        kind = "❌ Blocking failure"
    return (
        f"Project:    {info['project']}\n"
        f"Branch:     {info['branch']}\n"
        f"Pipeline:   #{info['pipeline_id']}\n"
        f"Failed job: {info['failed_job']}\n"
        f"Type:       {kind}\n"
        f"Pushed by:  {info.get('author', 'unknown')}\n"
        f"Time:       {now}\n"
        f"\n{analysis}\n"
        f"\n\U0001f517 View in GitLab:\n   {info['pipeline_url']}\n"
    )


def send(info, analysis):
    """Send one alert email. Returns True on success."""
    if not config.EMAIL_TO:
        print("[notifier] No EMAIL_TO configured; skipping send.")
        return False

    msg = EmailMessage()
    msg["From"] = config.SMTP_FROM
    msg["To"] = ", ".join(config.EMAIL_TO)
    msg["Subject"] = (
        f"❌ CI Failed — {info['project']} / {info['failed_job']} ({info['branch']})"
    )
    msg.set_content(build_email_body(info, analysis))

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as server:
            if config.SMTP_USE_TLS:
                server.starttls()
            if config.SMTP_USER:
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.send_message(msg)
        print(f"[notifier] Alert emailed for {info['project']} #{info['pipeline_id']}")
        return True
    except Exception as e:
        print(f"[notifier] Failed to send email: {e}")
        return False
