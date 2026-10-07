"""Read-only probe of one job + its pipeline, to see exactly what GitLab reports."""

import sys
import requests
import config

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = config.GITLAB_URL + "/api/v4"
H = {"PRIVATE-TOKEN": config.GITLAB_TOKEN}

PROJECT = sys.argv[1] if len(sys.argv) > 1 else ""   # pass a project id
JOB_ID = "509534"


def get(path, params=None):
    return requests.get(BASE + path, headers=H, params=params, timeout=30)


# The job itself
jr = get(f"/projects/{PROJECT}/jobs/{JOB_ID}")
print(f"GET job -> {jr.status_code}")
if jr.ok:
    j = jr.json()
    print(f"  job name:       {j.get('name')}")
    print(f"  job status:     {j.get('status')}")
    print(f"  allow_failure:  {j.get('allow_failure')}")
    print(f"  finished_at:    {j.get('finished_at')}")
    pipe = j.get("pipeline", {})
    print(f"  pipeline id:    {pipe.get('id')}")
    print(f"  pipeline status:{pipe.get('status')}")
    print(f"  branch (ref):   {pipe.get('ref')}")

    # The pipeline detail (status + updated_at is what our scan filters on)
    plid = pipe.get("id")
    if plid:
        pr = get(f"/projects/{PROJECT}/pipelines/{plid}")
        if pr.ok:
            pl = pr.json()
            print("\nPipeline detail:")
            print(f"  status:      {pl.get('status')}")
            print(f"  updated_at:  {pl.get('updated_at')}")
            print(f"  created_at:  {pl.get('created_at')}")
            print(f"  web_url:     {pl.get('web_url')}")
else:
    print(f"  body: {jr.text[:300]}")

# What our analyzer's exact query would return for this project
print("\nWhat the analyzer's failed-pipeline query returns (last 48h):")
from datetime import datetime, timedelta, timezone
since = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
q = get(f"/projects/{PROJECT}/pipelines",
        {"status": "failed", "updated_after": since, "order_by": "updated_at", "sort": "asc"})
print(f"  status=failed&updated_after={since} -> {q.status_code}, {len(q.json()) if q.ok else '?'} result(s)")
if q.ok:
    for pl in q.json():
        print(f"    #{pl['id']} {pl.get('ref')} status={pl.get('status')} updated={pl.get('updated_at')}")
