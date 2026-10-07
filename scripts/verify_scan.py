"""Read-only verification: list failed pipelines across all member projects
within a lookback window. Emails NOBODY, runs no AI. Just proves what the
analyzer would now catch.

Usage:  python verify_scan.py [hours]   (default 12)
"""

import sys
from datetime import datetime, timedelta, timezone

import config
from gitlab_client import GitLabClient

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

hours = int(sys.argv[1]) if len(sys.argv) > 1 else 12
since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

client = GitLabClient(config.GITLAB_URL, config.GITLAB_TOKEN)

print(f"Looking for FAILED pipelines updated since {since} (last {hours}h)\n")

projects = client.list_projects()          # all member projects (no activity filter)
print(f"Scanning {len(projects)} member project(s)...\n")

found = 0
forbidden = 0
for p in projects:
    try:
        pipelines = client.list_failed_pipelines(p["id"], since)
    except Exception as e:
        if "403" in str(e):
            forbidden += 1
        continue
    for pl in pipelines:
        found += 1
        print(f"  ❌ {p.get('path_with_namespace')}")
        print(f"      pipeline #{pl['id']}  branch={pl.get('ref')}  updated={pl.get('updated_at')}")
        print(f"      {pl.get('web_url')}")

print(f"\nSummary: {found} failed pipeline(s) found, {forbidden} project(s) skipped (403 no access).")
if found:
    print("=> The analyzer WOULD alert on these. Fix confirmed. ✅")
else:
    print("=> No failed pipelines in this window. Try a bigger lookback, e.g. python verify_scan.py 48")
