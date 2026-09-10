"""Sends a failed-job log to local Ollama and returns a human-readable analysis.

If Ollama is unreachable, returns a fallback that includes the raw log tail,
so an alert is still sent and the failure is never silently dropped.
"""

import os
import re
import sys

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


def _build_prompt(log_text):
    return f"""You are a CI/CD expert helping a DevOps team.
A GitLab pipeline job failed. Here is the failed job log:

--- LOG START ---
{log_text}
--- LOG END ---
{_facts_block(log_text)}

Explain in simple, clear language:
1. WHY IT FAILED  (one short paragraph)
2. HOW TO FIX     (numbered, specific steps)

Be concise. Do not repeat the whole log back."""


def analyze(raw_log):
    """Return (analysis_text, used_ai). Falls back to raw log if AI is
    disabled (AI_ENABLED=false) or the Ollama call fails."""
    log_text = tail(clean_log(raw_log), config.LOG_MAX_CHARS)
    if not log_text:
        log_text = "(the job produced no readable log output)"

    if config.AI_ENABLED:
        payload = {
            "model": config.OLLAMA_MODEL,
            "prompt": _build_prompt(log_text),
            "stream": False,
        }
        try:
            resp = requests.post(
                f"{config.OLLAMA_URL}/api/generate",
                json=payload,
                timeout=config.OLLAMA_TIMEOUT,
            )
            resp.raise_for_status()
            analysis = resp.json().get("response", "").strip()
            if analysis:
                return analysis, True
        except Exception as e:
            print(f"[analyzer] Ollama unavailable ({e}); sending raw log instead.")
        note = "⚠️ AI analysis unavailable — showing the raw log tail instead:\n\n"
    else:
        # AI deliberately turned off — deliver the raw log, no LLM call made.
        note = "ℹ️ AI analysis is disabled — showing the raw log tail:\n\n"

    # Fallback: no AI, but still deliver the log so the team isn't blind.
    return note + log_text, False
