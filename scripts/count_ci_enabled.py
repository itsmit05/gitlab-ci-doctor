"""Read-only: across the WHOLE GitLab instance, how many repos have CI/CD
enabled? Uses keyset pagination (gentle) + retries; reports partial if the
server errors out."""

import re
import sys
import time
from collections import Counter

import requests
import config

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

H = {"PRIVATE-TOKEN": config.GITLAB_TOKEN}
url = (config.GITLAB_URL + "/api/v4/projects"
       "?pagination=keyset&per_page=100&order_by=id&sort=asc")

builds = Counter()
active_ci_on = 0
total = 0
pages = 0

last = None
while url:
    ok = False
    for attempt in range(4):
        try:
            r = requests.get(url, headers=H, timeout=60)
            if r.status_code >= 500:
                last = f"HTTP {r.status_code}"
                time.sleep(2 * (attempt + 1))
                continue
            r.raise_for_status()
            ok = True
            break
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    if not ok:
        print(f"Stopped early after {pages} pages ({total} projects) due to server error: {last}")
        break

    batch = r.json()
    if not batch:
        break
    for p in batch:
        total += 1
        lvl = p.get("builds_access_level", "unknown")
        builds[lvl] += 1
        if lvl != "disabled" and not p.get("archived"):
            active_ci_on += 1
    pages += 1

    m = re.search(r'<([^>]+)>;\s*rel="next"', r.headers.get("Link", ""))
    url = m.group(1) if m else None
    time.sleep(0.3)   # be gentle on the shared GitLab server

print(f"\nScanned {total} projects.")
print("builds_access_level breakdown:")
for k, v in builds.most_common():
    print(f"  {v:>5}  {k}")
ci_total = sum(v for k, v in builds.items() if k != "disabled")
print(f"\nCI ENABLED (any): {ci_total}")
print(f"CI ENABLED + active (not archived): {active_ci_on}")
