"""Read-only: list CI jobs that have failed recently across all monitored
repos (yours + teammates'). Sends nothing. Usage: python current_failures.py [hours]"""

import sys
from datetime import datetime, timedelta, timezone

import config
from gitlab_client import GitLabClient

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

hours = int(sys.argv[1]) if len(sys.argv) > 1 else 24
since = datetime.now(timezone.utc) - timedelta(hours=hours)

c = GitLabClient(config.GITLAB_URL, config.GITLAB_TOKEN)

# Same project set the monitor uses: your repos + teammates' repos.
projects = c.list_projects()
seen = {str(p.get("id")) for p in projects}
for uid in config.TEAM_MEMBER_IDS:
    try:
        for pr in c.user_projects(uid):
            if str(pr["id"]) not in seen:
                seen.add(str(pr["id"]))
                projects.append({"id": pr["id"], "name": pr["name"], "path_with_namespace": pr["name"]})
    except Exception:
        pass

print(f"Scanning {len(projects)} repos for jobs failed in the last {hours}h...\n")

found = []
for p in projects:
    try:
        jobs = c.iter_failed_jobs(p["id"], since)
    except Exception:
        continue  # no access / CI disabled
    for j in jobs:
        found.append((p.get("name") or p.get("path_with_namespace") or p["id"], j))

if not found:
    print(f"✅ No failed jobs in the last {hours}h. Everything is green.")
else:
    found.sort(key=lambda x: x[1].get("finished_at") or "", reverse=True)
    print(f"❌ {len(found)} failed job(s) found:\n")
    for name, j in found:
        kind = "warning(allow_failure)" if j.get("allow_failure") else "BLOCKING"
        print(f"  {j.get('finished_at','?')}  [{kind}]")
        print(f"     {name}  ->  {j.get('name')}  (branch {j.get('ref')})")
        print(f"     {j.get('web_url')}")
