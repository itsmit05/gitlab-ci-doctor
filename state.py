"""Tiny JSON state file so the tool doesn't re-alert or miss failures across restarts."""

import json
import os
from datetime import datetime, timezone

import config

_MAX_HANDLED = 1000  # keep the handled list from growing forever


def utcnow_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load():
    if os.path.exists(config.STATE_FILE):
        try:
            with open(config.STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("last_check", utcnow_iso())
            data.setdefault("handled", [])
            return data
        except Exception as e:
            print(f"[state] Could not read state file ({e}); starting fresh.")
    # First run: start watching from NOW so we don't email historical failures.
    return {"last_check": utcnow_iso(), "handled": []}


def save(data):
    # Bound the handled list to the most recent entries.
    if len(data.get("handled", [])) > _MAX_HANDLED:
        data["handled"] = data["handled"][-_MAX_HANDLED:]
    try:
        with open(config.STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[state] Could not write state file: {e}")
