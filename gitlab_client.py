"""Read-only GitLab API client. Only performs GET requests."""

from datetime import datetime

import requests


def parse_ts(ts):
    """Parse a GitLab ISO timestamp (…Z or with fractional seconds) to datetime."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


class GitLabClient:
    def __init__(self, base_url, token, timeout=30):
        self.base = base_url + "/api/v4"
        self.timeout = timeout
        self.session = requests.Session()
        # Read-only personal access token (scope: read_api).
        self.session.headers.update({"PRIVATE-TOKEN": token})

    def _get(self, path, params=None):
        resp = self.session.get(self.base + path, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp

    def _get_paginated(self, path, params=None):
        """Follow GitLab's page headers and return all items across pages."""
        params = dict(params or {})
        params.setdefault("per_page", 100)
        page = 1
        items = []
        while True:
            params["page"] = page
            resp = self._get(path, params)
            batch = resp.json()
            if not isinstance(batch, list) or not batch:
                break
            items.extend(batch)
            next_page = resp.headers.get("X-Next-Page")
            if not next_page:
                break
            page = int(next_page)
        return items

    def list_projects(self, last_activity_after=None):
        """All projects the token is a member of. If last_activity_after is
        given, restrict to projects active since then (optional optimization)."""
        params = {
            "membership": "true",
            "simple": "true",
            "archived": "false",
            "order_by": "last_activity_at",
        }
        if last_activity_after:
            params["last_activity_after"] = last_activity_after
        return self._get_paginated("/projects", params)

    def get_project(self, project_id):
        return self._get(f"/projects/{project_id}").json()

    def iter_failed_jobs(self, project_id, since_dt, max_pages=3):
        """Failed JOBS in a project (newest first), finished at/after since_dt.

        Catches failures in both 'failed' pipelines AND 'Warning' pipelines
        (allow_failure jobs). Stops paging once jobs get older than since_dt.
        max_pages caps how far back we look (100 jobs/page)."""
        out = []
        page = 1
        while page <= max_pages:
            resp = self._get(
                f"/projects/{project_id}/jobs",
                {"scope[]": "failed", "per_page": 100, "page": page},
            )
            batch = resp.json()
            if not batch:
                break
            stop = False
            for job in batch:
                finished = parse_ts(job.get("finished_at") or job.get("created_at"))
                if since_dt and finished and finished < since_dt:
                    stop = True
                    break
                out.append(job)
            if stop:
                break
            nxt = resp.headers.get("X-Next-Page")
            if not nxt:
                break
            page = int(nxt)
        return out

    def user_projects(self, user_id):
        """Direct project memberships of a user: list of {id, name}. Admin only."""
        out, page = [], 1
        while True:
            resp = self._get(f"/users/{user_id}/memberships",
                             {"type": "Project", "per_page": 100, "page": page})
            batch = resp.json()
            if not batch:
                break
            out += [{"id": m["source_id"], "name": m.get("source_name")} for m in batch]
            nxt = resp.headers.get("X-Next-Page")
            if not nxt:
                break
            page = int(nxt)
        return out

    def get_job_trace(self, project_id, job_id):
        """Raw log text of a job (may be empty if expired/unavailable)."""
        resp = self._get(f"/projects/{project_id}/jobs/{job_id}/trace")
        return resp.text

    def get_commit(self, project_id, sha):
        try:
            return self._get(f"/projects/{project_id}/repository/commits/{sha}").json()
        except Exception:
            return {}
