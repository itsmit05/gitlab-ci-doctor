"""Read-only diagnostic: what can the token actually see?

Lists projects the token is a member of, and for each checks whether it can
READ pipelines (the permission the analyzer needs). Helps explain 403s and
why only a few projects are scanned. Touches nothing, sends nothing.
"""

import sys
import requests
import config

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = config.GITLAB_URL + "/api/v4"
H = {"PRIVATE-TOKEN": config.GITLAB_TOKEN}


def get(path, params=None):
    return requests.get(BASE + path, headers=H, params=params, timeout=30)


def main():
    # Who is the token?
    me = get("/user")
    if me.ok:
        u = me.json()
        print(f"Token user: {u.get('username')} (id={u.get('id')}, is_admin={u.get('is_admin')})")
    else:
        print(f"/user failed: {me.status_code} {me.text[:200]}")

    # All membership projects (no activity filter), with our access level.
    print("\nProjects the token is a MEMBER of:")
    page, total = 1, 0
    ok_pipes, forbidden = 0, 0
    while True:
        r = get("/projects", {"membership": "true", "simple": "false",
                              "per_page": 100, "page": page,
                              "order_by": "last_activity_at"})
        if not r.ok:
            print(f"  /projects failed: {r.status_code} {r.text[:200]}")
            break
        batch = r.json()
        if not batch:
            break
        for p in batch:
            total += 1
            access = (p.get("permissions", {}).get("project_access") or {})
            level = access.get("access_level", "?")
            # Try reading pipelines
            pr = get(f"/projects/{p['id']}/pipelines", {"per_page": 1})
            if pr.status_code == 403:
                forbidden += 1
                mark = "FORBIDDEN(403)"
            elif pr.ok:
                ok_pipes += 1
                mark = f"pipelines-ok ({len(pr.json())} recent)"
            else:
                mark = f"err {pr.status_code}"
            print(f"  id={p['id']:>6}  access_level={level:>3}  {mark}  {p.get('path_with_namespace')}")
        nxt = r.headers.get("X-Next-Page")
        if not nxt:
            break
        page = int(nxt)

    print(f"\nTotal membership projects: {total}")
    print(f"  can read pipelines: {ok_pipes}")
    print(f"  forbidden (403):    {forbidden}")
    print("\nNote: access_level 10=Guest 20=Reporter 30=Developer 40=Maintainer 50=Owner")
    print("Reading pipelines needs Reporter(20)+ on private projects.")


if __name__ == "__main__":
    main()
