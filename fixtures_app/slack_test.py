"""Send a test message to Slack: python -m fixtures_app.slack_test

Uses the next few real fixtures from data/fixtures.json so the test looks like a
normal alert. Nothing in the data or the Excel file changes.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

from . import slack, state
from .run import ALERT_MIN_DAYS, STATE, excel_url, far_enough


def main() -> int:
    webhook = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not webhook:
        print("::error::SLACK_WEBHOOK_URL is not set. Add it under Settings -> Secrets and variables "
              "-> Actions -> New repository secret, then run this again.")
        return 2
    if not webhook.startswith("https://hooks.slack.com/"):
        print("::error::SLACK_WEBHOOK_URL doesn't look like a Slack webhook "
              "(it should start with https://hooks.slack.com/).")
        return 3

    now = datetime.now(timezone.utc)
    upcoming = sorted((r for r in state.load(STATE).values() if far_enough(r, now)),
                      key=lambda r: r.get("date_utc") or "")[:3]
    sample = [dict(r, change_note="New") for r in upcoming]
    messages = slack.build_messages(sample, [], excel_url(), False, len(sample), [])
    intro = {"type": "section", "text": {"type": "mrkdwn", "text":
             ":test_tube: *This is a test message.* Real alerts look like this and arrive on Monday "
             "and Friday mornings when fixtures at least "
             f"{ALERT_MIN_DAYS} days away are announced or change. Below are {len(sample)} upcoming "
             "fixtures as an example."}}
    if messages:
        messages[0]["blocks"].insert(0, intro)
        messages[0]["text"] = "Partner fixtures: test message"
    else:
        messages = [{"text": "Partner fixtures: test message", "blocks": [intro]}]
    slack.post(webhook, messages)
    print("Test message sent to Slack.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
