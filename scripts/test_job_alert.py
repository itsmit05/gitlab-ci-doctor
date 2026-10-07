"""Controlled end-to-end test of JOB-LEVEL detection.

Targets ONE project, finds its most recent failed job in the lookback window,
runs the real AI analysis, and emails ONLY you@example.com (not the team).

Usage:  python test_job_alert.py [project_id] [hours]   (default 4859, 2h)
"""

import sys
from datetime import datetime, timedelta, timezone

import config
# TEST SAFETY: route this test email to me only, never the team.
config.EMAIL_TO = ["you@example.com"]

from gitlab_client import GitLabClient
from analyzer import analyze
import notifier

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

project_id = sys.argv[1] if len(sys.argv) > 1 else "4859"
hours = int(sys.argv[2]) if len(sys.argv) > 2 else 2
since_dt = datetime.now(timezone.utc) - timedelta(hours=hours)

client = GitLabClient(config.GITLAB_URL, config.GITLAB_TOKEN)
project = client.get_project(project_id)
print(f"Project: {project.get('path_with_namespace')} (id={project_id})")
print(f"Looking for failed jobs in the last {hours}h ...\n")

jobs = client.iter_failed_jobs(project_id, since_dt, max_pages=5)
print(f"Found {len(jobs)} failed job(s).")
if not jobs:
    print("Nothing to test. Try a bigger window, e.g. python test_job_alert.py 4859 6")
    sys.exit(0)

job = jobs[0]  # newest failed job
name = job.get("name", "unknown")
print(f"Testing newest: '{name}' (job #{job['id']}, allow_failure={job.get('allow_failure')})")

trace = client.get_job_trace(project_id, job["id"])
print("Running AI analysis (this can take ~2 min on CPU)...")
analysis, used_ai = analyze(trace)

pipeline = job.get("pipeline") or {}
commit = job.get("commit") or {}
info = {
    "project": project.get("path_with_namespace"),
    "branch": job.get("ref", "?"),
    "pipeline_id": pipeline.get("id", "?"),
    "failed_job": name,
    "author": commit.get("author_name", "unknown"),
    "pipeline_url": job.get("web_url") or pipeline.get("web_url", ""),
    "allow_failure": bool(job.get("allow_failure")),
}

ok = notifier.send(info, analysis)
print(f"\nEmail sent to you@example.com only: {ok} (ai_used={used_ai})")
