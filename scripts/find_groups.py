"""Read-only: list the GitLab groups you're a member of, with how many
projects each contains (so we can pick which to monitor)."""

import sys
import requests
import config

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

H = {"PRIVATE-TOKEN": config.GITLAB_TOKEN}
base = config.GITLAB_URL + "/api/v4"


def paginated(path, params):
    params = dict(params); params.setdefault("per_page", 100)
    page, out = 1, []
    while True:
        params["page"] = page
        r = requests.get(base + path, headers=H, params=params, timeout=60)
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


groups = paginated("/groups", {"membership": "true", "all_available": "false"})
rows = []
for g in groups:
    gid = g["id"]
    # count projects in the group incl. subgroups
    r = requests.get(f"{base}/groups/{gid}/projects", headers=H,
                     params={"include_subgroups": "true", "per_page": 1,
                             "archived": "false"}, timeout=60)
    total = r.headers.get("X-Total", "?")
    rows.append((g.get("full_path"), total, gid))

rows.sort(key=lambda x: (int(x[1]) if str(x[1]).isdigit() else 0), reverse=True)
print(f"You are a member of {len(groups)} group(s):\n")
print(f"{'Group':<40}{'projects':>10}{'id':>8}")
print("-" * 58)
for path, total, gid in rows:
    print(f"{path:<40}{str(total):>10}{gid:>8}")
