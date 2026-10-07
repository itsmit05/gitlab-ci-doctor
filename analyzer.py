"""Sends a failed-job log to an LLM and returns a human-readable analysis.

AI_PROVIDER picks the LLM: "ollama" (local, default) or "groq" (cloud API).
Secrets are masked before the log is sent anywhere. If the LLM is unreachable,
returns a fallback that includes the raw log tail, so an alert is still sent
and the failure is never silently dropped.
"""

import os
import re
import sys
import time

import requests

import config

# GitLab job logs contain ANSI colour codes and section markers; strip them
# so the AI (and the email) see clean text.
_ANSI = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_SECTION = re.compile(r"section_(start|end):\d+:[^\r\n]*")


def clean_log(text):
    text = _ANSI.sub("", text or "")
    text = _SECTION.sub("", text)
    return text.strip()


# Masked before the log is sent to the LLM. Order matters: the specific token
# shapes first, then generic key=value / URL credentials.
_SECRETS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "[PRIVATE KEY]"),
    (re.compile(r"\b(glpat|gldt|glrt|ghp|gho|ghs|github_pat|xox[abp]|sk|gsk)[-_][A-Za-z0-9_\-]{10,}"), "[TOKEN]"),
    (re.compile(r"\b(AKIA|ASIA)[A-Z0-9]{16}\b"), "[AWS KEY]"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]+"), "[JWT]"),
    (re.compile(r"\b\d{8,10}:[A-Za-z0-9_\-]{35}\b"), "[TELEGRAM TOKEN]"),
    (re.compile(r"(?i)(bearer|basic)\s+[A-Za-z0-9._~+/=\-]{12,}"), r"\1 [MASKED]"),
    (re.compile(r"(?i)(\w+://[^\s:/@]+):[^\s@/]+@"), r"\1:[MASKED]@"),
    (re.compile(r"(?i)\b([\w.\-]*(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key)[\w.\-]*)(['\"]?\s*[=:]\s*)(['\"]?)[^\s'\",]+"),
     r"\1\3\4[MASKED]"),
]


def redact(text):
    for pattern, repl in _SECRETS:
        text = pattern.sub(repl, text)
    return text


_LOG_LIMIT = "Job's log exceeded limit"
_LOG_LIMIT_NOTE = (
    "⚠️ GitLab stopped saving this job's log at its size limit, so the real error "
    "is probably NOT in it. Make the job print less (e.g. don't echo full SQL/schema "
    "dumps) or raise `output_limit` in the runner's config.toml, then re-run.\n\n"
)


def tail(text, max_chars):
    """Keep the END of the log — errors almost always appear there."""
    if len(text) <= max_chars:
        return text
    return "...(truncated)...\n" + text[-max_chars:]


# --------------------------------------------------------------- npm facts ---
# A failing build often names a package and a version. Looking the real latest
# version up turns a vague "dependency problem" into a concrete fact the model
# can use. Read-only, fail-soft: if the registry is unreachable we simply pass
# no facts and the prompt is exactly what it was before.

# pubapi is an optional helper. Set PUBAPI_PATH if it lives outside sys.path.
_pubapi_path = os.environ.get("PUBAPI_PATH")
if _pubapi_path:
    sys.path.insert(0, _pubapi_path)
try:
    import pubapi
except Exception:
    pubapi = None

# npm ERR! notarget No matching version found for lodash@9.9.9
# npm ERR! Could not resolve dependency: peer react@"^17.0.0"
_PKG_PATTERNS = [
    re.compile(r"No matching version found for\s+(@?[\w.\-/]+)@([\w.\-^~*]+)"),
    re.compile(r"Could not resolve dependency:\s*\w*\s*(@?[\w.\-/]+)@\"?([\w.\-^~*]+)"),
    re.compile(r"npm ERR! 404\s+'(@?[\w.\-/]+)@([\w.\-^~*]+)'"),
    re.compile(r"peer\s+(@?[\w.\-/]+)@\"?([\w.\-^~*<>= |]+)\"?"),
]


def npm_facts(log_text, limit=5):
    """[(package, version_in_log, latest_on_registry)] found in the log.

    Empty list if nothing matched, pubapi is missing, or the registry is down -
    never raises, because a CI explanation must still go out either way.
    """
    if pubapi is None or not log_text:
        return []
    seen, facts = set(), []
    for pattern in _PKG_PATTERNS:
        for name, wanted in pattern.findall(log_text):
            name = name.strip()
            if not name or name in seen:
                continue
            seen.add(name)
            try:
                latest = pubapi.npm_latest(name)
            except Exception:
                latest = None
            if latest:
                facts.append((name, wanted.strip(), latest))
            if len(facts) >= limit:
                return facts
    return facts


def _facts_block(log_text):
    """The extra prompt section, or "" when we learned nothing useful."""
    facts = npm_facts(log_text)
    if not facts:
        return ""
    lines = ["", "--- PACKAGE FACTS (from the npm registry, use these) ---"]
    for name, wanted, latest in facts:
        lines.append("%s: the log asks for %s; latest published is %s"
                     % (name, wanted, latest))
    lines.append("--- END PACKAGE FACTS ---")
    return "\n".join(lines)


def _build_prompt(log_text, cut_off=False):
    warning = ""
    if cut_off:
        warning = """
IMPORTANT: GitLab hit its log size limit and STOPPED recording this log, so the
real error is probably missing. Say that first, then point out what is flooding
the log and how to make the job print less.
"""
    return f"""You are a CI/CD expert helping a DevOps team.
A GitLab pipeline job failed. Here is the failed job log:

--- LOG START ---
{log_text}
--- LOG END ---
{_facts_block(log_text)}{warning}
Explain in simple, clear language:
1. WHY IT FAILED  (one short paragraph)
2. HOW TO FIX     (numbered, specific steps)

Be concise. Do not repeat the whole log back."""


def _ask_ollama(prompt):
    payload = {"model": config.OLLAMA_MODEL, "prompt": prompt, "stream": False}
    resp = requests.post(f"{config.OLLAMA_URL}/api/generate", json=payload,
                         timeout=config.OLLAMA_TIMEOUT)
    resp.raise_for_status()
    return resp.json().get("response", "").strip()


def _ask_groq(prompt):
    """One Groq chat call; retries once if rate-limited. Raises on failure."""
    headers = {"Authorization": f"Bearer {config.GROQ_API_KEY}"}
    payload = {
        "model": config.GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }
    for attempt in range(2):
        resp = requests.post(config.GROQ_URL, json=payload, headers=headers,
                             timeout=config.GROQ_TIMEOUT)
        if resp.status_code == 429 and attempt == 0:
            wait = min(int(float(resp.headers.get("retry-after", "20"))), 60)
            print(f"[analyzer] Groq rate-limited; retrying in {wait}s.")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    return ""


def analyze(raw_log):
    """Return (analysis_text, used_ai). Falls back to raw log if AI is
    disabled (AI_ENABLED=false) or the LLM call fails."""
    cleaned = clean_log(raw_log)
    cut_off = _LOG_LIMIT in cleaned
    log_text = redact(tail(cleaned, config.LOG_MAX_CHARS))
    if not log_text:
        log_text = "(the job produced no readable log output)"

    if config.AI_ENABLED:
        ask = _ask_groq if config.AI_PROVIDER == "groq" else _ask_ollama
        try:
            analysis = ask(_build_prompt(log_text, cut_off))
            if analysis:
                return analysis, True
        except Exception as e:
            print(f"[analyzer] {config.AI_PROVIDER} unavailable ({e}); sending raw log instead.")
        note = "⚠️ AI analysis unavailable — showing the raw log tail instead:\n\n"
    else:
        # AI deliberately turned off — deliver the raw log, no LLM call made.
        note = "ℹ️ AI analysis is disabled — showing the raw log tail:\n\n"

    # Fallback: no AI, but still deliver the log so the team isn't blind.
    if cut_off:
        note = _LOG_LIMIT_NOTE + note
    return note + log_text, False
