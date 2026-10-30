"""Post new and changed fixtures to Slack through an incoming webhook."""

from __future__ import annotations

import logging
from collections import defaultdict

import requests

from .excel import uk_dt

log = logging.getLogger(__name__)
MAX_SECTION = 2900  # Slack limit is 3000 characters per section
MAX_BLOCKS = 45  # Slack limit is 50 blocks per message


def _when(r: dict, field: str = "date_utc") -> str:
    dt = uk_dt(r.get(field) or "")
    if not dt:
        return "date TBC"
    return dt.strftime("%a %d %b %Y") + (dt.strftime(", %H:%M") if r.get("time_confirmed") else ", time TBC")


def _line(r: dict) -> str:
    icon = ":new:" if r.get("change_note") == "New" else ":arrows_counterclockwise:"
    side = "" if r.get("side") == "Home" else f" ({r.get('side')})"
    text = (f"{icon} {r['home']} v {r['away']}{side} · {r.get('competition', '')} · "
            f"{_when(r)} · {r.get('stadium') or 'stadium TBC'}")
    if r.get("change_note") and r.get("change_note") != "New":
        text += f"\n      _{r['change_note']}_"
        if r.get("previous_date_utc") and r.get("previous_date_utc") != r.get("date_utc"):
            text += f" _(was {_when({'date_utc': r['previous_date_utc'], 'time_confirmed': True})})_"
    return "• " + text


def build_messages(new: list[dict], changed: list[dict], excel_url: str | None, first_run: bool,
                   total: int, partners_missing: list[str]) -> list[dict]:
    footer = []
    if excel_url:
        footer.append({"type": "context", "elements": [
            {"type": "mrkdwn", "text": f":page_facing_up: <{excel_url}|Download the full fixture list (Excel)>"}]})
    if partners_missing:
        footer.append({"type": "context", "elements": [{"type": "mrkdwn", "text":
            ":warning: Not found on ESPN: " + ", ".join(partners_missing) + ". See the Coverage sheet."}]})

    if first_run:
        n_partners = len({r["partner"] for r in new})
        return [{"text": f"Partner fixtures: first load, {total} fixtures", "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": ":soccer: Partner fixtures are set up"}},
            {"type": "section", "text": {"type": "mrkdwn", "text":
                f"First load found *{total} upcoming fixtures* for *{n_partners} partners*. "
                "From now on this channel gets a message every Monday and Friday when new fixtures are "
                "announced or kick-off times, dates or stadiums change."}},
        ] + footer}]

    if not new and not changed:
        return []

    by_partner = defaultdict(list)
    for r in sorted(new + changed, key=lambda r: (r["partner"], r.get("date_utc") or "")):
        by_partner[r["partner"]].append(r)

    title = f":soccer: {len(new)} new fixture{'s' if len(new) != 1 else ''}"
    if changed:
        title += f", {len(changed)} update{'s' if len(changed) != 1 else ''}"
    sections = []
    for partner, rows in by_partner.items():
        chunk = f"*{partner}*"
        for r in rows:
            line = _line(r)
            if len(chunk) + len(line) + 1 > MAX_SECTION:
                sections.append(chunk)
                chunk = f"*{partner}* (cont.)"
            chunk += "\n" + line
        sections.append(chunk)

    messages, blocks = [], [{"type": "header", "text": {"type": "plain_text", "text": title}}]
    for s in sections:
        if len(blocks) >= MAX_BLOCKS:
            messages.append({"text": title, "blocks": blocks})
            blocks = []
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": s}})
    blocks += footer
    messages.append({"text": title, "blocks": blocks})
    return messages


def post(webhook: str, messages: list[dict]) -> None:
    for m in messages:
        r = requests.post(webhook, json=m, timeout=20)
        if r.status_code != 200:
            log.error("Slack returned %s: %s", r.status_code, r.text[:300])
            r.raise_for_status()
