"""Read-only: for repos that return 403 on jobs, find out WHY —
is CI/CD disabled (nothing to monitor) or is it a permissions issue?"""

import sys
from collections import Counter

import requests
import config
from gitlab_client import GitLabClient

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

client = GitLabClient(config.GITLAB_URL, config.GITLAB_TOKEN)
H = {"PRIVATE-TOKEN": config.GITLAB_TOKEN}

projects = client.list_projects()
reasons = Counter()
samples = []

for p in projects:
    pid = p["id"]
    jr = requests.get(f"{config.GITLAB_URL}/api/v4/projects/{pid}/jobs",
                      headers=H, params={"per_page": 1}, timeout=30)
    if jr.status_code != 403:
        continue
    # 403 on jobs -> inspect the project's CI/CD settings
    builds = p.get("builds_access_level")           # from list (simple=false)
    if builds is None:
        det = requests.get(f"{config.GITLAB_URL}/api/v4/projects/{pid}", headers=H, timeout=30)
        if det.ok:
            builds = det.json().get("builds_access_level")
    # does it have ANY pipelines?
    plr = requests.get(f"{config.GITLAB_URL}/api/v4/projects/{pid}/pipelines",
                       headers=H, params={"per_page": 1}, timeout=30)
    has_pipes = "403" if plr.status_code == 403 else (len(plr.json()) if plr.ok else f"err{plr.status_code}")

    key = f"builds_access_level={builds}"
    reasons[key] += 1
    if len(samples) < 12:
        samples.append(f"  {p.get('path_with_namespace')}: builds={builds}, pipelines_visible={has_pipes}")

print("Why the 403 repos are forbidden (grouped by CI/CD setting):\n")
for k, v in reasons.most_common():
    print(f"  {v:>4}  {k}")
print("\nSamples:")
print("\n".join(samples))
print("\nNote: builds_access_level 'disabled' = no CI on that repo (nothing to monitor).")
print("      'private'/'enabled' + 403 = a real permissions gap.")
