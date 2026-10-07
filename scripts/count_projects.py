"""Read-only: how many projects does the token see as a member vs how many
exist on the whole GitLab instance (admin view)?"""

import sys
import requests
import config

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

H = {"PRIVATE-TOKEN": config.GITLAB_TOKEN}

for label, params in [
    ("Repos token is a MEMBER of", {"membership": "true", "per_page": 1}),
    ("ALL repos on the instance (admin view)", {"per_page": 1}),
]:
    r = requests.get(f"{config.GITLAB_URL}/api/v4/projects",
                     headers=H, params=params, timeout=60)
    total = r.headers.get("X-Total", "unknown (server hides total for large sets)")
    print(f"{label}: {total}  [http {r.status_code}]")
