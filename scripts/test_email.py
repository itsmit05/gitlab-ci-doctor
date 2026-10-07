"""One-off SMTP test: sends a single SAMPLE alert to you@example.com only.

Confirms the email path (SMTP host/port/login) works before trusting the tool.
Does NOT touch GitLab and does NOT email the team.
"""

import smtplib
import sys
from email.message import EmailMessage

import config

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TEST_RECIPIENT = "you@example.com"  # you only — not the team

SAMPLE = """This is a TEST email from the GitLab CI Failure Analyzer.
If you can read this, your SMTP settings work. ✅

Below is a SAMPLE of what a real failure alert looks like:

Project:    my-next-app
Branch:     staging
Pipeline:   #1234
Failed job: build

🔍 WHY IT FAILED
The build failed because 'sharp' requires Node.js >= 18.17.0,
but the runner is using Node 16.20.

🛠️ HOW TO FIX
1. Update .gitlab-ci.yml to use image: node:18
2. Re-run the pipeline.

🔗 View in GitLab:
   https://gitlab.example.com/dev/my-next-app/-/pipelines/1234
"""


def main():
    msg = EmailMessage()
    msg["From"] = config.SMTP_FROM
    msg["To"] = TEST_RECIPIENT
    msg["Subject"] = "✅ TEST — GitLab CI Failure Analyzer email works"
    msg.set_content(SAMPLE)

    print(f"[test] Connecting to {config.SMTP_HOST}:{config.SMTP_PORT} (TLS={config.SMTP_USE_TLS})")
    print(f"[test] Sending test email to {TEST_RECIPIENT} ...")
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as server:
            if config.SMTP_USE_TLS:
                server.starttls()
            if config.SMTP_USER:
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.send_message(msg)
        print("[test] SUCCESS — test email sent. Check your inbox. ✅")
    except Exception as e:
        print(f"[test] FAILED — {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
