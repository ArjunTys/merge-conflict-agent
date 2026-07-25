
from utils.config import GROQ_API_KEY  # triggers load_dotenv()
 
from agent import get_merge_conflict_agent
from runner import resolve_one_conflict
import approval_loop2
from approval_loop2 import run_approval_loop, DeveloperReply
 
# --- the conflict we resolve (same discount example) ---
conflict = {
    "filename": "discounts.py",
    "ancestor":
'''def get_discount(user, cart_total):
    if user.is_member:
        return 0.10
    return 0.0
''',
    "main_version":
'''def get_discount(user, cart_total):
    if cart_total > 100:
        return 0.15
    if user.is_member:
        return 0.10
    return 0.0
''',
    "incoming_version":
'''def get_discount(user, cart_total):
    if user.is_member and user.days_as_member < 30:
        return 0.20
    if user.is_member:
        return 0.10
    return 0.0
''',
    "extra_context": "# discounts.py -- checkout pricing rules",
}
 
CONFLICT_ID = "abc123"
DEV_EMAIL = "developer@example.com"
 
agent = get_merge_conflict_agent()
resolution = resolve_one_conflict(agent, conflict)
 
 
def show(outcome):
    print("\n>>> FINAL OUTCOME:")
    print(f"    conflict_id: {outcome.conflict_id}")
    print(f"    status:      {outcome.status}")
    print(f"    rounds:      {outcome.rounds}")
    print()
 
 
# =============================================================================
# MONKEYPATCH HELPER
# -----------------------------------------------------------------------------
# Your loop calls get_reply(conflict_id) with NO scripted argument -- which is
# clean. To feed it fake replies without touching your loop, we temporarily
# REPLACE approval_loop.get_reply with our own version that returns a scripted
# reply, one per round, from a list we control.
#
# (This is "monkeypatching" -- swapping out a function at runtime. Fine for
# tests; worth understanding properly later. It leaves your real loop untouched.)
# =============================================================================
 
def script_replies(replies):
    """Return a fake get_reply that hands back `replies` one at a time."""
    calls = {"n": 0}
 
    def fake_get_reply(conflict_id):
        i = calls["n"]
        calls["n"] += 1
        return replies[i] if i < len(replies) else None
 
    return fake_get_reply
 
 
def run_scenario(name, replies):
    print(f"\n########## {name} ##########")
    # swap the real get_reply for our scripted one
    approval_loop2.get_reply = script_replies(replies)
    outcome = run_approval_loop(agent, conflict, CONFLICT_ID, resolution, DEV_EMAIL)
    show(outcome)
 
 
# --- SCENARIO 1: approve immediately ---
run_scenario("SCENARIO 1: APPROVE",
             [DeveloperReply(conflict_id=CONFLICT_ID, decision="approve")])
 
# --- SCENARIO 2: reject with feedback, then approve the revision ---
run_scenario("SCENARIO 2: REJECT then APPROVE", [
    DeveloperReply(conflict_id=CONFLICT_ID, decision="reject",
                   feedback="Prioritize the cart-total discount over the new-member discount."),
    DeveloperReply(conflict_id=CONFLICT_ID, decision="approve"),
])
 
# --- SCENARIO 3: abort ---
run_scenario("SCENARIO 3: ABORT",
             [DeveloperReply(conflict_id=CONFLICT_ID, decision="abort")])
 
# --- SCENARIO 4: no reply (timeout) ---
run_scenario("SCENARIO 4: NO REPLY", [None])

 