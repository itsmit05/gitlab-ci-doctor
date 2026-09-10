<h1 align="center">GitLab CI Doctor</h1>

<p align="center">
  <strong>Your pipeline failed. This tells you why — in plain English, in your inbox.</strong>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat" alt="MIT License" /></a>
  <img src="https://img.shields.io/badge/python-3.9%2B-3776AB?style=flat&logo=python&logoColor=white" alt="Python 3.9+" />
  <img src="https://img.shields.io/badge/GitLab-API%20v4-FC6D26?style=flat&logo=gitlab&logoColor=white" alt="GitLab API v4" />
  <img src="https://img.shields.io/badge/LLM-Ollama%20(local)-000000?style=flat&logo=ollama&logoColor=white" alt="Ollama" />
  <img src="https://img.shields.io/badge/data-never%20leaves%20your%20network-blue?style=flat" alt="Self-hosted" />
  <img src="https://img.shields.io/badge/GitLab%20access-read--only-brightgreen?style=flat" alt="Read-only" />
</p>

---

## The problem

A CI job fails at 2 AM. GitLab emails someone *"Pipeline #4821 failed"* — no reason, no log,
no fix. Whoever opens it has to log into GitLab, find the pipeline, find the failed job,
scroll 4,000 lines of log output, and work out what broke.

Multiply that by 270 repositories.

## What this does

Polls GitLab for failed pipelines, pulls the failed job's log, sends it to a **local** LLM,
and emails the owning team an explanation plus concrete fix steps.

```
Project:    checkout-service
Branch:     develop
Pipeline:   #4821
Failed job: build
Type:       ❌ Blocking failure
Pushed by:  A Developer

WHY IT FAILED
The build could not install dependencies. package.json requires lodash@9.9.9,
but the highest version published on npm is 4.17.21, so npm aborted with
"No matching version found".

HOW TO FIX
1. Open package.json and change "lodash": "9.9.9" to "^4.17.21"
2. Run npm install locally to refresh package-lock.json
3. Commit both files and push

🔗 View in GitLab:
   https://gitlab.example.com/team/checkout-service/-/pipelines/4821
```

---

## Why it's built this way

| Decision | Reason |
|---|---|
| **Polling, not webhooks** | Needs no admin rights on 270 repos, and no inbound port. Runs from anywhere that can reach GitLab. |
| **Local LLM via Ollama** | Job logs contain source paths, internal hostnames and stack traces. None of it should go to a third-party API. |
| **Read-only token** (`read_api`) | The tool physically cannot change your pipelines. Every GitLab call is a `GET`. |
| **Email, not chat** | Alerts land where the owning team already looks, with no new tool to adopt. |
| **Degrades instead of failing** | If Ollama is down, you still get the raw log tail. A failure is never silently dropped. |
| **Package facts injected into the prompt** | For npm errors it looks up the *real* latest version, so the model states a fact rather than guessing. |

---

## Install

```bash
git clone https://github.com/itsmit05/gitlab-ci-doctor.git
cd gitlab-ci-doctor
pip install -r requirements.txt
cp .env.example .env
```

Fill in the four values marked `TODO` in `.env`, then:

```bash
python main.py
```

It serves a status page on `http://127.0.0.1:8099` and starts polling.

### Try it without GitLab

```bash
python demo.py
```

Feeds a fake failure log straight to Ollama, so you can see the output quality
before wiring anything up.

---

## Configuration

| Variable | Required | Default | What it does |
|---|:--:|---|---|
| `GITLAB_URL` | ✅ | — | Your GitLab base URL |
| `GITLAB_TOKEN` | ✅ | — | Personal access token, scope `read_api` |
| `SMTP_PASSWORD` | ✅ | — | Password for the sending mailbox |
| `EMAIL_TO` | ✅ | — | Comma-separated recipients |
| `PROJECT_IDS` | | *(all)* | Limit to specific projects; empty watches everything the token can see |
| `EXCLUDE_JOBS` | | — | Job names to ignore, e.g. noisy `allow_failure` jobs |
| `TEAM_MEMBER_IDS` | | — | Also watch these GitLab users' repos |
| `POLL_INTERVAL_SECONDS` | | `180` | How often to check |
| `ACTIVITY_WINDOW_HOURS` | | `0` | `0` scans everything each cycle. Above `0` is lighter but **can miss** failures on re-runs |
| `AI_ENABLED` | | `true` | `false` emails the raw log tail and never calls the LLM |
| `OLLAMA_URL` | | `http://localhost:11434` | Ollama endpoint |
| `OLLAMA_MODEL` | | `qwen2.5:7b` | Any Ollama model |
| `OLLAMA_TIMEOUT` | | `600` | CPU inference is slow; be generous |
| `LOG_MAX_CHARS` | | `12000` | How much of the log tail reaches the model |

---

## How a cycle works

```
   every POLL_INTERVAL_SECONDS
              │
              ▼
   list projects the token can see  ──►  GET /projects
              │
              ▼
   failed jobs since last check     ──►  GET /projects/:id/jobs?scope[]=failed
              │
              ▼
   already alerted?  ── yes ──►  skip   (state.json)
              │ no
              ▼
   download the job log             ──►  GET /jobs/:id/trace
              │
              ▼
   strip ANSI codes, keep the tail
              │
              ▼
   look up real npm versions if the log names a package
              │
              ▼
   Ollama  ── unreachable ──►  fall back to raw log tail
              │
              ▼
   email the team, record in state.json
```

Both **blocking failures** and **`allow_failure` "Warning" jobs** are caught — the second
kind is what usually goes unnoticed for weeks.

State lives in `state.json`, so a restart neither re-alerts old failures nor misses new
ones. First run starts watching from *now* rather than emailing your entire history.

---

## Requirements

- Python 3.9+
- [Ollama](https://ollama.com) reachable from wherever this runs — optional, set `AI_ENABLED=false` to skip
- A GitLab personal access token with `read_api`
- An SMTP mailbox to send from

Model choice is a speed/quality trade-off. `qwen2.5:7b` gives good explanations;
`llama3.2:1b` runs on almost anything but is noticeably vaguer.

---

## `scripts/`

One-off read-only helpers, useful when setting the tool up:

| Script | Purpose |
|---|---|
| `count_projects.py` / `count_ci_enabled.py` | How many projects the token sees, and how many actually use CI |
| `current_failures.py` | What is failing right now |
| `probe_forbidden.py` | Which projects return `403` so you know your coverage gaps |
| `probe_job.py <project_id>` | Dump one project's failed jobs |
| `report_access.py` / `team_access.py` | Which projects you and your teammates can reach (`TEAM_EMAILS=`) |
| `test_email.py` | Send one sample alert to yourself before pointing it at the team |
| `test_job_alert.py` | Run the full analysis on a real failure, email only yourself |
| `verify_scan.py` / `diag.py` / `check_handled.py` | Sanity checks and state inspection |

---

## Notes

- Every GitLab call is a `GET`. There is no code path that writes to GitLab.
- Job logs are sent only to your own Ollama instance.
- `.env`, `state.json` and log files are gitignored.

## License

MIT — see [LICENSE](LICENSE).
