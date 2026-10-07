"""Read-only (admin): list projects that you + your teammates have access to.
Writes a combined report to team_access.txt."""

import os
import sys

import requests
import config

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

H = {"PRIVATE-TOKEN": config.GITLAB_TOKEN}
base = config.GITLAB_URL + "/api/v4"

# Comma-separated emails, e.g. TEAM_EMAILS=you@example.com,teammate@example.com
TEAM = [e.strip() for e in os.environ.get("TEAM_EMAILS", "").split(",") if e.strip()]
if not TEAM:
    sys.exit("Set TEAM_EMAILS=a@example.com,b@example.com before running this.")

LEVELS = {10: "Guest", 20: "Reporter", 30: "Developer", 40: "Maintainer", 50: "Owner"}


def find_user(email):
    r = requests.get(f"{base}/users", headers=H, params={"search": email}, timeout=30)
    r.raise_for_status()
    users = r.json()
    for u in users:
        if (u.get("email") or "").lower() == email.lower():
            return u
    return users[0] if users else None


def memberships(user_id):
    out, page = [], 1
    while True:
        r = requests.get(f"{base}/users/{user_id}/memberships",
                         headers=H, params={"type": "Project", "per_page": 100, "page": page},
                         timeout=60)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        out.extend(batch)
        nxt = r.headers.get("X-Next-Page")
        if not nxt:
            break
        page = int(nxt)
    return out


# project_id -> {"name":..., "access": {email: level}}
projects = {}
who = {}
for email in TEAM:
    u = find_user(email)
    if not u:
        print(f"!! Could not find GitLab user for {email}")
        continue
    who[email] = u["username"]
    mems = memberships(u["id"])
    print(f"{email}  (@{u['username']}, id={u['id']}): {len(mems)} project memberships")
    for m in mems:
        pid = m["source_id"]
        projects.setdefault(pid, {"name": m.get("source_name", str(pid)), "access": {}})
        projects[pid]["access"][email] = LEVELS.get(m.get("access_level"), m.get("access_level"))

print(f"\nDistinct projects the team can access: {len(projects)}")

with open("team_access.txt", "w", encoding="utf-8") as fh:
    header = "project_id | " + " | ".join(who.get(e, e) for e in TEAM) + " | project"
    fh.write(header + "\n" + "-" * len(header) + "\n")
    for pid, info in sorted(projects.items(), key=lambda x: x[1]["name"].lower()):
        cols = [str(pid)]
        for e in TEAM:
            cols.append(info["access"].get(e, "-"))
        cols.append(info["name"])
        fh.write(" | ".join(cols) + "\n")

print("Full combined list written to: team_access.txt")
