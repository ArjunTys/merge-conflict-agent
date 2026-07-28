"""
Integration test: real approval_loop2 + real ui_transport + real Flask UI.
crewai is stubbed at import time and the LLM calls (classify_reply,
resolve_one_conflict) are replaced with fakes, so this runs offline.
Run from repo root:  python tests/test_ui_integration.py
(ui/app.py must NOT already be running; this test starts its own.)
"""
import os, sys, threading, time, types, subprocess, requests
os.environ.setdefault("AGENT_EMAIL", "test@test.com")
os.environ.setdefault("AGENT_EMAIL_PASSWORD", "dummy")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- stub crewai so imports work without the package/API key -----------
crewai_stub = types.ModuleType("crewai")
for name in ("Agent", "Task", "Crew"):
    setattr(crewai_stub, name, type(name, (), {"__init__": lambda self, **k: None,
                                               "kickoff": lambda self: None}))
sys.modules.setdefault("crewai", crewai_stub)

import approval_loop2, ui_transport
from shared_types import ApprovalOutcome

BASE = "http://localhost:5051"
os.environ["UI_BASE_URL"] = BASE
ui_transport.UI_BASE = BASE
ui_transport.POLL_INTERVAL_SECONDS = 1
ui_transport.REPLY_TIMEOUT_SECONDS = 30

# --- fakes for the two LLM steps ---------------------------------------
class FakeResolution:
    def __init__(self, code):
        self.merged_code = code; self.reasoning = "test reasoning"
        self.confidence = "high"; self.confidence_note = ""; self.alternatives = []

class FakeClassification:
    def __init__(self, decision, feedback=""): self.decision, self.feedback = decision, feedback

def fake_classify(agent, reply_text, alternatives=None):
    t = reply_text
    if t.startswith("Approved."): return FakeClassification("approve")
    if t.startswith("Abort."):    return FakeClassification("abort")
    return FakeClassification("reject", t)   # incl. the EXACT-code edit text

def fake_resolve(agent, conflict):
    fb = conflict["extra_context"].split("DEVELOPER FEEDBACK ON THE PREVIOUS ATTEMPT:")[-1]
    if "EXACTLY the following code" in fb:
        return FakeResolution(fb.split("developer's own edit:\n\n", 1)[-1].strip())
    return FakeResolution("v2 after: " + fb.strip()[:40])

approval_loop2.classify_reply = fake_classify
approval_loop2.resolve_one_conflict = fake_resolve
approval_loop2.send_email = ui_transport.send_email
approval_loop2.get_reply = ui_transport.get_reply

# --- start the real Flask server ---------------------------------------
env = dict(os.environ); server = subprocess.Popen(
    [sys.executable, "-c",
     "import sys; sys.path.insert(0,'ui'); import app; app.DB_PATH=type(app.DB_PATH)('/tmp/test_conflicts.db'); "
     "app.BASE_URL='http://localhost:5051'; app.init_db(); app.app.run(port=5051)"],
    env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(30):
        try: requests.get(BASE + "/", timeout=1); break
        except Exception: time.sleep(0.3)

    def clicker(cid, actions):
        """Simulated developer: waits for pending, performs next action."""
        for action, data in actions:
            for _ in range(60):
                d = requests.get(f"{BASE}/api/conflicts/{cid}/decision").json()
                if d.get("status") == "pending": break
                time.sleep(0.5)
            requests.post(f"{BASE}/conflict/{cid}/decide",
                          data={"action": action, **data})

    conflict = {"filename": "auth.py", "ancestor": "", "main_version": "A",
                "incoming_version": "B", "extra_context": "ctx"}

    # 1: straight accept
    cid = "uitest1"; ui_transport.set_conflict_context(cid, conflict)
    threading.Thread(target=clicker, args=(cid, [("accept", {})]), daemon=True).start()
    out = approval_loop2.run_approval_loop(None, conflict, cid,
            FakeResolution("v1"), "dev", None)
    assert out.status == "approved" and out.rounds == 1, out
    print("PASS accept: approved in 1 round")

    # 2: reject with feedback -> rework -> accept
    cid = "uitest2"; ui_transport.set_conflict_context(cid, conflict)
    threading.Thread(target=clicker, args=(cid,
        [("reject", {"feedback": "keep rate limiter first"}), ("accept", {})]),
        daemon=True).start()
    out = approval_loop2.run_approval_loop(None, conflict, cid,
            FakeResolution("v1"), "dev", None)
    assert out.status == "approved" and out.rounds == 2, out
    assert "keep rate limiter first" in out.final_resolution.merged_code
    print("PASS reject->rework->accept: 2 rounds, feedback reached resolver")

    # 3: edit -> exact code round-trips -> accept
    cid = "uitest3"; ui_transport.set_conflict_context(cid, conflict)
    threading.Thread(target=clicker, args=(cid,
        [("edit", {"edited_code": "DEV_EXACT_CODE()"}), ("accept", {})]),
        daemon=True).start()
    out = approval_loop2.run_approval_loop(None, conflict, cid,
            FakeResolution("v1"), "dev", None)
    assert out.status == "approved" and out.final_resolution.merged_code == "DEV_EXACT_CODE()", out
    print("PASS edit: developer's exact code came back as the final resolution")

    # 4: abort
    cid = "uitest4"; ui_transport.set_conflict_context(cid, conflict)
    threading.Thread(target=clicker, args=(cid, [("abort", {})]), daemon=True).start()
    out = approval_loop2.run_approval_loop(None, conflict, cid,
            FakeResolution("v1"), "dev", None)
    assert out.status == "aborted", out
    print("PASS abort")
    print("ALL UI INTEGRATION TESTS PASS")
finally:
    server.terminate()
