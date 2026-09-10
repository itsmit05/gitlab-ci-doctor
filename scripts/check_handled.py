"""Read-only: show details of the jobs the analyzer has already handled,
to confirm they were genuine failures."""

import json
import sys
import requests
import config

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

H = {"PRIVATE-TOKEN": config.GITLAB_TOKEN}
state = json.load(open(config.STATE_FILE, encoding="utf-8"))
handled = state.get("handled", [])
print(f"Handled jobs: {len(handled)}  |  last_check: {state.get('last_check')}\n")

for key in handled:
    parts = key.split(":")          # "<pid>:job:<jid>"
    pid, jid = parts[0], parts[2]
    r = requests.get(f"{config.GITLAB_URL}/api/v4/projects/{pid}/jobs/{jid}",
                     headers=H, timeout=30)
    if r.ok:
        j = r.json()
        print(f"  {j.get('name')}  (project {pid})")
        print(f"     status={j.get('status')}  allow_failure={j.get('allow_failure')}  finished={j.get('finished_at')}")
        print(f"     {j.get('web_url')}")
    else:
        print(f"  project {pid} job {jid} -> HTTP {r.status_code}")
