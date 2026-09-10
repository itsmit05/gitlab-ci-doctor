"""Read-only: report which repos the token can read jobs for (monitored)
vs which return 403 (NOT monitored). Groups by top-level namespace and
writes the full lists to access_report.txt."""

import sys
from collections import defaultdict

import requests
import config
from gitlab_client import GitLabClient

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

client = GitLabClient(config.GITLAB_URL, config.GITLAB_TOKEN)
H = {"PRIVATE-TOKEN": config.GITLAB_TOKEN}

print("Checking access for every project the token is a member of...\n")
projects = client.list_projects()

accessible, forbidden = [], []
for p in projects:
    r = requests.get(f"{config.GITLAB_URL}/api/v4/projects/{p['id']}/jobs",
                     headers=H, params={"per_page": 1}, timeout=30)
    path = p.get("path_with_namespace", str(p["id"]))
    if r.status_code == 403:
        forbidden.append(path)
    elif r.ok:
        accessible.append(path)
    # other errors ignored for this report


def top(path):
    return path.split("/")[0] if "/" in path else path


groups = defaultdict(lambda: [0, 0])   # top-namespace -> [accessible, forbidden]
for pth in accessible:
    groups[top(pth)][0] += 1
for pth in forbidden:
    groups[top(pth)][1] += 1

print(f"TOTAL: {len(projects)} repos  |  MONITORED: {len(accessible)}  |  NOT accessible (403): {len(forbidden)}\n")
print(f"{'Top-level group':<32}{'monitored':>10}{'no-access':>11}")
print("-" * 53)
for g in sorted(groups):
    a, f = groups[g]
    print(f"{g:<32}{a:>10}{f:>11}")

with open("access_report.txt", "w", encoding="utf-8") as fh:
    fh.write(f"MONITORED ({len(accessible)}):\n")
    for pth in sorted(accessible):
        fh.write(f"  {pth}\n")
    fh.write(f"\nNOT ACCESSIBLE - 403 ({len(forbidden)}):\n")
    for pth in sorted(forbidden):
        fh.write(f"  {pth}\n")

print("\nFull lists written to: access_report.txt")
