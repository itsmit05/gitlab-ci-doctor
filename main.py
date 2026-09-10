"""
GitLab CI Failure Analyzer — polling service.

Every POLL_INTERVAL_SECONDS it:
  1. finds recently-active projects (or a fixed PROJECT_IDS list),
  2. asks each for pipelines that FAILED since the last check,
  3. downloads the failed job's log,
  4. gets an AI analysis from local Ollama,
  5. emails the team.

Read-only against GitLab. No inbound connection required.
A small FastAPI app is included only for a status page + manual "check now".
"""

import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI

import config
import logsetup
import state
from analyzer import analyze
from gitlab_client import GitLabClient, parse_ts
from notifier import send as send_email

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Route all output to the rotating log file (must run before any print/log).
logsetup.setup()

_client = GitLabClient(config.GITLAB_URL, config.GITLAB_TOKEN)
_lock = threading.Lock()          # only one cycle runs at a time
_last_run = {"time": None, "new_failures": 0, "error": None}
_forbidden = set()                # project ids that returned 403; skipped afterwards


def _projects_to_scan(last_activity_after):
    """Fixed list from config, or auto-discover active projects."""
    if config.PROJECT_IDS:
        out = []
        for pid in config.PROJECT_IDS:
            try:
                out.append(_client.get_project(pid))
            except Exception as e:
                print(f"[cycle] Could not load project {pid}: {e}")
        return out
    projects = _client.list_projects(last_activity_after)
    seen = {str(p.get("id")) for p in projects}
    # Also cover repos each teammate can access (admin token can read them).
    for uid in config.TEAM_MEMBER_IDS:
        try:
            for pr in _client.user_projects(uid):
                if str(pr["id"]) not in seen:
                    seen.add(str(pr["id"]))
                    projects.append({"id": pr["id"], "name": pr["name"]})
        except Exception as e:
            print(f"[cycle] Could not load memberships for user {uid}: {e}")
    return projects


def _handle_job(project, job, handled):
    """Analyze one failed job and email the team. Returns True if alerted."""
    pid = project["id"]
    jid = job["id"]
    key = f"{pid}:job:{jid}"
    if key in handled:
        return False

    name = job.get("name", "unknown")
    if name in config.EXCLUDE_JOBS:
        handled.append(key)  # mark handled so we don't re-check it every cycle
        print(f"[cycle] Skipping excluded job '{name}' in {pid}")
        return False

    trace = ""
    try:
        trace = _client.get_job_trace(pid, jid)
    except Exception as e:
        print(f"[cycle] Could not fetch job trace for {key}: {e}")

    analysis, used_ai = analyze(trace)

    pipeline = job.get("pipeline") or {}
    commit = job.get("commit") or {}
    info = {
        "project": project.get("name") or project.get("path_with_namespace") or str(pid),
        "branch": job.get("ref", "?"),
        "pipeline_id": pipeline.get("id", "?"),
        "failed_job": name,
        "author": commit.get("author_name", "unknown"),
        "pipeline_url": job.get("web_url") or pipeline.get("web_url", ""),
        "allow_failure": bool(job.get("allow_failure")),
    }

    send_email(info, analysis)
    handled.append(key)
    print(f"[cycle] Handled job {key} '{name}' (allow_failure={info['allow_failure']}, ai={used_ai})")
    return True


def run_cycle():
    """One polling pass. Returns number of new failures alerted."""
    with _lock:
        st = state.load()
        last_check = st["last_check"]
        handled = st["handled"]
        now_iso = state.utcnow_iso()

        activity_after = None
        if config.ACTIVITY_WINDOW_HOURS > 0:
            activity_after = (
                datetime.now(timezone.utc) - timedelta(hours=config.ACTIVITY_WINDOW_HOURS)
            ).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Look at failed jobs finished since the last check (with a small
        # overlap; the handled set prevents duplicate alerts).
        since_dt = parse_ts(last_check)
        if since_dt:
            since_dt = since_dt - timedelta(seconds=120)

        new_failures = 0
        try:
            projects = _projects_to_scan(activity_after)
            scan_list = [p for p in projects if str(p.get("id")) not in _forbidden]
            print(f"[cycle] Scanning {len(scan_list)} project(s) "
                  f"({len(_forbidden)} skipped, no access) for failed jobs since {last_check}")
            for project in scan_list:
                try:
                    jobs = _client.iter_failed_jobs(project["id"], since_dt)
                except Exception as e:
                    if "403" in str(e):
                        # No access to this repo's jobs — remember and skip it next time.
                        _forbidden.add(str(project.get("id")))
                    else:
                        print(f"[cycle] Job query failed for {project.get('id')}: {e}")
                    continue
                for job in jobs:
                    try:
                        if _handle_job(project, job, handled):
                            new_failures += 1
                    except Exception as e:
                        print(f"[cycle] Error handling job {job.get('id')}: {e}")
        finally:
            # Advance the clock even on partial errors so we keep moving forward.
            st["last_check"] = now_iso
            st["handled"] = handled
            state.save(st)

        _last_run.update(time=now_iso, new_failures=new_failures, error=None)
        print(f"[cycle] Done. New failures alerted: {new_failures}")
        return new_failures


def _poll_loop():
    print(f"[loop] Polling every {config.POLL_INTERVAL_SECONDS}s. Model={config.OLLAMA_MODEL}")
    while True:
        try:
            run_cycle()
        except Exception as e:
            _last_run.update(error=str(e))
            print(f"[loop] Cycle error: {e}")
        time.sleep(config.POLL_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app):
    problems = config.missing_required()
    if problems:
        print("=" * 55)
        print(" CONFIG INCOMPLETE — fill these in your .env file:")
        for p in problems:
            print(f"   - {p}")
        print(" The service will still start but stay idle until fixed.")
        print("=" * 55)
    else:
        t = threading.Thread(target=_poll_loop, daemon=True)
        t.start()
    yield


app = FastAPI(title="GitLab CI Failure Analyzer", lifespan=lifespan)


@app.get("/")
def status():
    return {
        "service": "gitlab-ci-failure-analyzer",
        "gitlab_url": config.GITLAB_URL or "(not set)",
        "model": config.OLLAMA_MODEL,
        "poll_interval_seconds": config.POLL_INTERVAL_SECONDS,
        "watching": config.PROJECT_IDS or "all active projects",
        "config_missing": config.missing_required(),
        "last_run": _last_run,
    }


@app.post("/check-now")
def check_now():
    """Trigger one polling cycle immediately (handy for testing)."""
    count = run_cycle()
    return {"triggered": True, "new_failures": count, "last_run": _last_run}


if __name__ == "__main__":
    import uvicorn

    # log_config=None so uvicorn doesn't replace our logging setup;
    # its logs propagate to our root logger (and thus the log file).
    uvicorn.run(app, host="127.0.0.1", port=8099, log_config=None)
