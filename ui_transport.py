"""
UI transport for the approval loop -- same interface as email_transport:

    send_email(to_address, conflict_id, resolution) -> None
    get_reply(conflict_id) -> DeveloperReply | None

so run_with_ui.py can point approval_loop2 at these two functions and the
loop runs unchanged, reviewing conflicts in the browser instead of email.

How UI decisions flow through the EXISTING loop
-----------------------------------------------
approval_loop2 passes every reply's .feedback through the LLM classifier.
Buttons are already unambiguous, so this transport phrases each click as
plain language the classifier reads correctly:

  Accept          -> "Approved. Merge the proposed resolution as-is."
  Reject+feedback -> the developer's feedback text, verbatim
  Abort           -> "Abort. I'll handle this conflict manually myself."
  Edit            -> a rejection whose feedback says: replace the proposal
                     with EXACTLY this code (the developer's own edit).
                     The rework round then produces that code and the
                     developer accepts it -- edits flow through the
                     existing rework machinery, no loop changes needed.

Conflict context
----------------
send_email only receives (to_address, conflict_id, resolution), but the
UI page also shows the two clashing versions and the filename. Those live
in the conflict dict, which the orchestrator has. run_with_ui.py calls
set_conflict_context(conflict_id, conflict) before the loop starts, and
send_email picks it up from the registry here.

Requires: pip install flask requests   and the UI server running:
          python ui/app.py             (http://localhost:5050)
"""

import os
import time
from typing import Optional

import requests

from shared_types import DeveloperReply

UI_BASE = os.environ.get("UI_BASE_URL", "http://localhost:5050")
POLL_INTERVAL_SECONDS = int(os.environ.get("UI_POLL_INTERVAL_SECONDS", "5"))
REPLY_TIMEOUT_SECONDS = int(os.environ.get("UI_REPLY_TIMEOUT_SECONDS", str(60 * 60)))

# conflict_id -> conflict dict from the detector
_CONTEXT: dict = {}


def set_conflict_context(conflict_id: str, conflict: dict) -> None:
    """Called by the orchestrator wrapper so the UI can show the diff."""
    _CONTEXT[conflict_id] = conflict


def _deliver_link(to_address: str, url: str) -> None:
    """The doc's 'chat message delivery' step. Stand-in: print the message.
    Swap this for a Slack/Teams webhook later; nothing else changes."""
    print(f"[chat -> {to_address}] Merge conflict detected. "
          f"Review and resolve: {url}")


def send_email(to_address, conflict_id, resolution) -> None:
    """Register the conflict (or its reworked fix) on the UI, deliver link."""
    ctx = _CONTEXT.get(conflict_id, {})
    payload = {
        "id": conflict_id,
        "branch_a": ctx.get("main_branch", "main"),
        "branch_b": ctx.get("incoming_branch", "incoming"),
        "file_path": ctx.get("filename", ""),
        "summary": "",
        "main_code": ctx.get("main_version", ""),
        "incoming_code": ctx.get("incoming_version", ""),
        "proposed_code": resolution.merged_code,
        "reasoning": resolution.reasoning,
        "confidence": str(resolution.confidence),
    }
    r = requests.post(f"{UI_BASE}/api/conflicts", json=payload, timeout=10)
    r.raise_for_status()
    _deliver_link(to_address, r.json()["url"])


def _check_once(conflict_id) -> Optional[dict]:
    r = requests.get(f"{UI_BASE}/api/conflicts/{conflict_id}/decision",
                     timeout=10)
    if r.status_code != 200:
        return None
    d = r.json()
    return d if d.get("status") != "pending" else None


def get_reply(conflict_id) -> Optional[DeveloperReply]:
    """Block until the developer decides on the UI, or time out (None)."""
    deadline = time.time() + REPLY_TIMEOUT_SECONDS
    while time.time() < deadline:
        d = _check_once(conflict_id)
        if d is not None:
            status = d["status"]
            if status == "accepted":
                return DeveloperReply(
                    conflict_id, "approve",
                    "Approved. Merge the proposed resolution as-is.")
            if status == "edited":
                return DeveloperReply(
                    conflict_id, "reject",
                    "Do not use your proposal. Replace it with EXACTLY the "
                    "following code, character for character, with no "
                    "changes -- it is the developer's own edit:\n\n"
                    + d["edited_code"])
            if status == "rejected":
                return DeveloperReply(conflict_id, "reject", d["feedback"])
            if status == "aborted":
                return DeveloperReply(
                    conflict_id, "abort",
                    "Abort. I'll handle this conflict manually myself.")
        time.sleep(POLL_INTERVAL_SECONDS)
    return None
