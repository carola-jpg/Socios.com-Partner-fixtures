"""Remember what we've seen before, so each run can report what's new or changed."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

TRACKED = ("date_utc", "time_confirmed", "stadium", "status")


def load(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False, sort_keys=True)


def key(fx: dict) -> str:
    return f"{fx['event_id']}|{fx['partner']}"


def _describe(old: dict, new: dict) -> list[str]:
    notes = []
    if old.get("date_utc") != new.get("date_utc"):
        old_day, new_day = (old.get("date_utc") or "")[:10], (new.get("date_utc") or "")[:10]
        notes.append("Date changed" if old_day != new_day else "Kick-off time changed")
    if not old.get("time_confirmed") and new.get("time_confirmed"):
        notes.append("Kick-off time confirmed")
    if old.get("stadium") != new.get("stadium") and new.get("stadium"):
        notes.append("Stadium changed" if old.get("stadium") else "Stadium confirmed")
    st = (new.get("status") or "").lower()
    if old.get("status") != new.get("status") and any(w in st for w in ("postpon", "cancel", "suspend", "delay")):
        notes.append(f"Status: {new['status']}")
    return notes


def merge(state: dict, fetched: list[dict], now: datetime | None = None) -> tuple[dict, list[dict], list[dict]]:
    """Returns (new_state, new_fixtures, changed_fixtures)."""
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    new_state = dict(state)
    added, changed = [], []
    for fx in fetched:
        k = key(fx)
        old = state.get(k)
        rec = dict(fx)
        rec["last_seen"] = stamp
        if old is None:
            rec["first_seen"] = stamp
            rec["last_changed"] = stamp
            rec["change_note"] = "New"
            added.append(rec)
        else:
            rec["first_seen"] = old.get("first_seen", stamp)
            notes = _describe(old, fx)
            if notes:
                rec["last_changed"] = stamp
                rec["change_note"] = "; ".join(notes)
                rec["previous_date_utc"] = old.get("date_utc")
                changed.append(rec)
            else:
                rec["last_changed"] = old.get("last_changed", stamp)
                rec["change_note"] = old.get("change_note", "")
        new_state[k] = rec
    return new_state, added, changed
