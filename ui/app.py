"""
Conflict Resolution UI -- Flask backend.

Implements the doc's "Scenario" spec:
  - each conflict gets a unique UUID and its own URL:  /conflict/<id>
  - conflict details (branches, both code versions, proposed fix) are
    stored in a database (SQLite)
  - the page shows a side-by-side diff, the agent's proposed resolution,
    and Accept / Reject / Edit actions
  - the agent polls GET /api/conflicts/<id>/decision to learn the outcome

Endpoints (agent side):
  POST /api/conflicts                     create/update a conflict, returns {id, url}
  GET  /api/conflicts/<id>/decision       {"status": "pending"} or the decision
  POST /api/conflicts/<id>/proposal       update the fix after rework (resets to pending)

Endpoints (developer side, via browser):
  GET  /                                  list of open conflicts
  GET  /conflict/<id>                     the review page
  POST /conflict/<id>/decide              form submit: accept / reject / edit / abort

Run:  pip install flask
      python app.py          (serves on http://localhost:5050)
"""

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, url_for

DB_PATH = Path(__file__).parent / "conflicts.db"
BASE_URL = "http://localhost:5050"

app = Flask(__name__)


# ------------------------------------------------------------ database ----

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conflicts (
                id            TEXT PRIMARY KEY,
                branch_a      TEXT NOT NULL,   -- e.g. main
                branch_b      TEXT NOT NULL,   -- e.g. feature/login
                file_path     TEXT DEFAULT '',
                summary       TEXT DEFAULT '',
                main_code     TEXT DEFAULT '',
                incoming_code TEXT DEFAULT '',
                proposed_code TEXT DEFAULT '',
                reasoning     TEXT DEFAULT '',
                confidence    TEXT DEFAULT '',
                revision      INTEGER DEFAULT 1,
                status        TEXT DEFAULT 'pending',  -- pending|accepted|rejected|edited|aborted
                feedback      TEXT DEFAULT '',
                edited_code   TEXT DEFAULT '',
                created_at    TEXT,
                decided_at    TEXT
            )
        """)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ----------------------------------------------------------- agent API ----

@app.post("/api/conflicts")
def create_conflict():
    """The agent registers a conflict and gets back its unique URL."""
    d = request.get_json(force=True)
    cid = d.get("id") or uuid.uuid4().hex[:12]
    with db() as conn:
        conn.execute("""
            INSERT INTO conflicts (id, branch_a, branch_b, file_path, summary,
                                   main_code, incoming_code, proposed_code,
                                   reasoning, confidence, revision, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                proposed_code=excluded.proposed_code,
                reasoning=excluded.reasoning,
                confidence=excluded.confidence,
                revision=conflicts.revision + 1,
                status='pending', feedback='', edited_code='', decided_at=NULL
        """, (cid, d.get("branch_a", "main"), d.get("branch_b", "?"),
              d.get("file_path", ""), d.get("summary", ""),
              d.get("main_code", ""), d.get("incoming_code", ""),
              d.get("proposed_code", ""), d.get("reasoning", ""),
              d.get("confidence", ""), 1, now()))
    return jsonify({"id": cid, "url": f"{BASE_URL}/conflict/{cid}"})


@app.post("/api/conflicts/<cid>/proposal")
def update_proposal(cid):
    """After rework, the agent posts the new fix; page goes back to pending."""
    d = request.get_json(force=True)
    with db() as conn:
        cur = conn.execute("""
            UPDATE conflicts
            SET proposed_code=?, reasoning=?, revision=revision+1,
                status='pending', feedback='', edited_code='', decided_at=NULL
            WHERE id=?
        """, (d.get("proposed_code", ""), d.get("reasoning", ""), cid))
        if cur.rowcount == 0:
            return jsonify({"error": "unknown conflict id"}), 404
    return jsonify({"ok": True})


@app.get("/api/conflicts/<cid>/decision")
def get_decision(cid):
    """The agent polls this to learn the developer's decision."""
    with db() as conn:
        row = conn.execute("SELECT * FROM conflicts WHERE id=?", (cid,)).fetchone()
    if row is None:
        return jsonify({"error": "unknown conflict id"}), 404
    return jsonify({
        "id": row["id"],
        "status": row["status"],
        "feedback": row["feedback"],
        "edited_code": row["edited_code"],
        "revision": row["revision"],
        "decided_at": row["decided_at"],
    })


# ------------------------------------------------------- developer side ---

@app.get("/")
def index():
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM conflicts ORDER BY created_at DESC").fetchall()
    return render_template("index.html", conflicts=rows)


@app.get("/conflict/<cid>")
def conflict_page(cid):
    with db() as conn:
        row = conn.execute("SELECT * FROM conflicts WHERE id=?", (cid,)).fetchone()
    if row is None:
        return "Unknown conflict. It may have been resolved and cleaned up.", 404
    return render_template("conflict.html", c=row)


@app.post("/conflict/<cid>/decide")
def decide(cid):
    action = request.form.get("action", "")
    feedback = request.form.get("feedback", "").strip()
    edited = request.form.get("edited_code", "")

    status_map = {"accept": "accepted", "reject": "rejected",
                  "edit": "edited", "abort": "aborted"}
    if action not in status_map:
        return "Unknown action.", 400
    if action == "reject" and not feedback:
        return redirect(url_for("conflict_page", cid=cid) + "?need_feedback=1")

    with db() as conn:
        conn.execute("""
            UPDATE conflicts SET status=?, feedback=?, edited_code=?, decided_at=?
            WHERE id=?
        """, (status_map[action], feedback,
              edited if action == "edit" else "", now(), cid))
    return redirect(url_for("conflict_page", cid=cid))


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5050, debug=False)
