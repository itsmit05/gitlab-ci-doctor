"""
DEMO — GitLab CI Failure Analyzer (real Ollama, no GitLab / no email)

What this does:
  1. Uses a built-in FAKE failed pipeline + build log (nothing touches GitLab).
  2. Sends that log to your LOCAL Ollama and gets a real AI analysis.
  3. PRINTS the email that WOULD be sent to your team (it does NOT send anything).

Safe: no token, no GitLab connection, no email sent. Just prints to the terminal.
Run:  python demo.py
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error

# Windows terminals default to cp1252, which can't print emoji / em-dash.
# Force UTF-8 so the email preview renders correctly.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ---------------------------------------------------------------------------
# CONFIG — change the model here if you like.
#   llama3.2:1b        -> fast, you already have it, weaker analysis
#   qwen2.5-coder:7b   -> best for reading build logs (pull it first if needed)
#   llama3.1:8b        -> good general option
# ---------------------------------------------------------------------------
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:1b")

# ---------------------------------------------------------------------------
# FAKE pipeline data (this is what the real tool would fetch from GitLab).
# ---------------------------------------------------------------------------
FAKE = {
    "project": "my-next-app",
    "branch": "staging",
    "pipeline_id": 1234,
    "failed_job": "build",
    "gitlab_url": "https://gitlab.company.com/dev/my-next-app/-/pipelines/1234",
}

FAKE_LOG = """\
$ npm run build
> my-next-app@1.0.0 build
> next build

info  - Loading config from next.config.js
Failed to compile.

./node_modules/sharp/lib/constructor.js
Error: Cannot find module '../build/Release/sharp-linux-x64.node'
Require stack:
- /builds/my-next-app/node_modules/sharp/lib/constructor.js
npm ERR! code ELIFECYCLE
npm ERR! errno 1
npm ERR! sharp requires Node.js >= 18.17.0, current: v16.20.2
ERROR: Job failed: exit code 1
"""


def build_prompt(log_text):
    """The instruction we give the AI, plus the failed job log."""
    return f"""You are a CI/CD expert helping a DevOps team.
A GitLab pipeline job failed. Here is the failed job log:

--- LOG START ---
{log_text}
--- LOG END ---

Explain in simple, clear language:
1. WHY IT FAILED  (one short paragraph)
2. HOW TO FIX     (numbered, specific steps)

Be concise. Do not repeat the whole log back."""


def ask_ollama(prompt):
    """Send the prompt to local Ollama and return the AI's text answer."""
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # CPU models can be slow, so give it plenty of time.
    with urllib.request.urlopen(req, timeout=600) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("response", "").strip()


def print_email(analysis):
    """Print the email exactly as the real tool would send it."""
    line = "-" * 60
    now = time.strftime("%Y-%m-%d %H:%M")
    print("\n" + line)
    print("From:    you@example.com")
    print("To:      dev-team@example.com")
    print(f"Subject: ❌ CI Failed — {FAKE['project']} (branch: {FAKE['branch']})")
    print(line)
    print(f"\nProject:    {FAKE['project']}")
    print(f"Branch:     {FAKE['branch']}")
    print(f"Pipeline:   #{FAKE['pipeline_id']}")
    print(f"Failed job: {FAKE['failed_job']}")
    print(f"Time:       {now}")
    print("\n" + analysis)
    print(f"\n\U0001f517 View in GitLab:\n   {FAKE['gitlab_url']}")
    print(line + "\n")


def main():
    print(f"[demo] Using Ollama model: {OLLAMA_MODEL}")
    print(f"[demo] Sending fake failure log to {OLLAMA_URL} ... (this can take a while on CPU)")

    start = time.time()
    try:
        analysis = ask_ollama(build_prompt(FAKE_LOG))
    except urllib.error.URLError as e:
        print("\n[demo] ERROR: could not reach Ollama.")
        print(f"        {e}")
        print("        Is Ollama running?  Try:  ollama serve")
        print(f"        Is the model pulled? Try:  ollama pull {OLLAMA_MODEL}")
        return
    except Exception as e:
        print(f"\n[demo] ERROR talking to Ollama: {e}")
        return

    elapsed = round(time.time() - start, 1)
    print(f"[demo] Got AI analysis in {elapsed}s. This is the email your team would get:")
    print_email(analysis)
    print("[demo] Nothing was sent. This was print-only. ✅")


if __name__ == "__main__":
    main()
