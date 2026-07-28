"""
Run the full pipeline with the browser UI instead of email.

    Terminal 1:  python ui/app.py            (the review UI, port 5050)
    Terminal 2:  python run_with_ui.py <repo_path> <developer_name>

No existing file changes. This works because approval_loop2 binds
send_email/get_reply as names in its own module namespace at import time
(`from email_transport import send_email, get_reply`), and module names
can be reassigned from outside. We point them at ui_transport before the
pipeline runs -- same wiring idea as tests injecting fakes, used here to
swap one real transport for another. Wiring parts together is the
orchestrator layer's job, which is where this file sits.

We also wrap orchestrator.run_approval_loop so the UI receives the
conflict's context (filename, both code versions) -- the loop's transport
interface only carries the resolution, but the wrapper sees the whole
conflict dict and registers it with ui_transport first.
"""

import sys

import ui_transport
import approval_loop2
import orchestrator

# --- swap the transport -----------------------------------------------
approval_loop2.send_email = ui_transport.send_email
approval_loop2.get_reply = ui_transport.get_reply

# --- give the UI the conflict context ---------------------------------
_real_loop = orchestrator.run_approval_loop


def _loop_with_context(agent, conflict, conflict_id, resolution,
                       to_address, classifier_agent):
    ui_transport.set_conflict_context(conflict_id, conflict)
    return _real_loop(agent=agent, conflict=conflict,
                      conflict_id=conflict_id, resolution=resolution,
                      to_address=to_address,
                      classifier_agent=classifier_agent)


orchestrator.run_approval_loop = _loop_with_context


if __name__ == "__main__":
    repo = sys.argv[1] if len(sys.argv) > 1 else "."
    dev = sys.argv[2] if len(sys.argv) > 2 else "developer"
    orchestrator.run_pipeline(repo, dev)
