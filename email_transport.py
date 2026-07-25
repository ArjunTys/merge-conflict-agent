"""
Email transport for the approval loop (Part 3 plumbing).

This module is ONLY the plumbing: real SMTP sending and real IMAP inbox
polling. It exposes exactly the two functions Arjun's approval loop stubs
out, with the same signatures, so it drops in as a replacement:

    send_email(to_address, conflict_id, resolution) -> None
    get_reply(conflict_id) -> DeveloperReply | None

No loop logic lives here (that's Arjun's run_approval_loop), and no reply
classification lives here (that's the LLM classifier, plugged in on top).
get_reply returns the RAW reply text in .feedback with decision="reject"
as a placeholder, exactly as agreed.

get_reply BLOCKS: it polls the inbox every POLL_INTERVAL_SECONDS and only
returns None after REPLY_TIMEOUT_SECONDS with no reply. This matches the
loop's existing assumption that None is a final answer, so the loop file
needs no changes for timing.

Setup:
    pip install python-dotenv
    .env file next to this module (and .env listed in .gitignore):
        AGENT_EMAIL=githubbotemail@gmail.com
        AGENT_EMAIL_PASSWORD=xxxx xxxx xxxx xxxx   (Gmail app password;
                             requires 2-Step Verification + IMAP enabled)
"""

import os
import re
import time
import email
import imaplib
import smtplib
from dataclasses import dataclass
from email.mime.text import MIMEText
from email.header import decode_header
from typing import Literal, Optional
from shared_types import DeveloperReply

from dotenv import load_dotenv
load_dotenv()   # reads .env into os.environ before we look anything up

# ---------------------------------------------------------------- config ---

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
IMAP_HOST = os.environ.get("IMAP_HOST", "imap.gmail.com")

AGENT_EMAIL = os.environ["AGENT_EMAIL"]
AGENT_PASSWORD = os.environ["AGENT_EMAIL_PASSWORD"]

# get_reply blocks and polls internally, so Arjun's loop can keep treating
# None as a final answer ("timed out") rather than "not yet".
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "30"))
REPLY_TIMEOUT_SECONDS = int(os.environ.get("REPLY_TIMEOUT_SECONDS", str(60 * 60)))


# ---------------------------------------------------------------- types ----




# ------------------------------------------------------------- sending ----

def _format_resolution_body(resolution) -> str:
    """Turn the resolution object's fields into a readable email body."""
    lines = [
        "A merge conflict resolution is ready for your review.",
        "",
        "What each side was trying to do:",
        f"  main:     {resolution.main_intent}",
        f"  incoming: {resolution.incoming_intent}",
        "",
        "Reasoning behind the proposed fix:",
        f"{resolution.reasoning}",
        "",
        "Proposed merged code:",
        "-" * 60,
        resolution.merged_code,
        "-" * 60,
        "",
        f"Confidence: {resolution.confidence}",
    ]
    if resolution.confidence_note:
        lines.append(f"Note: {resolution.confidence_note}")
    if resolution.alternatives:
        lines.append("")
        lines.append("Alternatives considered:")
        for i, alt in enumerate(resolution.alternatives, start=1):
            lines.append(f"  {i}. {alt}")
    lines += [
        "",
        "Reply to this email with your decision (approve / reject with",
        "feedback / abort). Please keep the subject line intact -- the",
        "conflict-id tag in it is how your reply gets matched.",
    ]
    return "\n".join(lines)


def send_email(to_address, conflict_id, resolution) -> None:
    """
    Send the proposed resolution via real SMTP.
    Subject carries the tag [conflict-id: {conflict_id}], same format as
    the stub, so replies can be found by get_reply.
    """
    subject = f"Merge conflict resolution needed [conflict-id: {conflict_id}]"

    msg = MIMEText(_format_resolution_body(resolution))
    msg["Subject"] = subject
    msg["From"] = AGENT_EMAIL
    msg["To"] = to_address

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()                       # encrypt the connection
        server.login(AGENT_EMAIL, AGENT_PASSWORD)
        server.send_message(msg)


# ------------------------------------------------------------ receiving ---

def _decode(value) -> str:
    """Email headers can arrive encoded; normalise them to plain text."""
    if value is None:
        return ""
    parts = decode_header(value)
    out = []
    for text, charset in parts:
        if isinstance(text, bytes):
            out.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def _body_text(msg) -> str:
    """Extract the plain-text body from a (possibly multipart) email."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(
                        part.get_content_charset() or "utf-8",
                        errors="replace")
        return ""
    payload = msg.get_payload(decode=True)
    return payload.decode(msg.get_content_charset() or "utf-8",
                          errors="replace") if payload else ""


def _strip_quoted_reply(body: str) -> str:
    """
    Keep only what the developer actually typed. Everything below the
    'On <date>, <person> wrote:' line is quoted history -- it contains OUR
    proposal text (including words like 'approve'), which would pollute
    what the classifier sees.
    """
    lines = []
    for line in body.splitlines():
        if re.match(r"^\s*On .+ wrote:\s*$", line):
            break
        if line.strip().startswith(">"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _check_inbox_once(conflict_id) -> Optional[str]:
    """
    Single IMAP check: look for an unread reply whose subject carries
    [conflict-id: {conflict_id}]. Returns the raw reply text, or None if
    nothing has arrived yet.
    """
    # Search on the inner text, not the brackets -- special characters in
    # IMAP SUBJECT search strings are unreliable across servers.
    tag = f"conflict-id: {conflict_id}"

    with imaplib.IMAP4_SSL(IMAP_HOST) as mail:
        mail.login(AGENT_EMAIL, AGENT_PASSWORD)
        mail.select("inbox")

        status, data = mail.search(None, f'(UNSEEN SUBJECT "{tag}")')
        if status != "OK" or not data[0]:
            return None

        # Take the newest matching message
        newest_id = data[0].split()[-1]
        status, msg_data = mail.fetch(newest_id, "(RFC822)")
        if status != "OK":
            return None

        msg = email.message_from_bytes(msg_data[0][1])

        # Ignore our own proposal if it somehow landed in the inbox
        if AGENT_EMAIL in _decode(msg.get("From", "")):
            return None

        return _strip_quoted_reply(_body_text(msg))


def get_reply(conflict_id) -> Optional[DeveloperReply]:
    """
    Wait for the developer's reply. Polls the inbox every
    POLL_INTERVAL_SECONDS until a reply arrives or REPLY_TIMEOUT_SECONDS
    passes. Returns None ONLY on timeout -- so the caller (Arjun's loop)
    can safely treat None as 'no answer', exactly as his loop already does.

    NOTE: decision="reject" is a PLACEHOLDER. This function's job is only
    to hand back the raw reply text (in .feedback) and the conflict_id;
    the LLM classifier decides approve/reject/abort on top of this.
    """
    deadline = time.time() + REPLY_TIMEOUT_SECONDS

    while time.time() < deadline:
        raw_text = _check_inbox_once(conflict_id)
        if raw_text is not None:
            return DeveloperReply(
                conflict_id=conflict_id,
                decision="reject",     # placeholder -- classifier overrides this
                feedback=raw_text,
            )
        time.sleep(POLL_INTERVAL_SECONDS)

    return None


# ---------------------------------------------------------------- demo ----

if __name__ == "__main__":
    # Standalone smoke test: no Git, no AI, no loop. Sends one real email,
    # then get_reply waits internally (polling every 30s) until you reply.
    from dataclasses import field, dataclass as dc

    @dc
    class FakeResolution:
        merged_code: str = "def validate_user(u):\n    ...combined version..."
        main_intent: str = "add rate limiting to login"
        incoming_intent: str = "add logging to login"
        reasoning: str = "Both changes are compatible; kept both."
        confidence: str = "high"
        confidence_note: str = ""
        alternatives: list = field(default_factory=list)

    cid = "smoketest1"
    send_email("arjuntys46@gmail.com", cid, FakeResolution())
    print("Sent. Waiting for your reply (polling every 30s, 1h timeout)...")

    reply = get_reply(cid)
    print(reply if reply is not None else "Timed out with no reply.")

