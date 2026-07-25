
import uuid
from utils.config import GROQ_API_KEY
from detector import find_all_conflicts          # Part 1
from agent import get_merge_conflict_agent        # Part 2
from runner import resolve_one_conflict           # Part 2
from approval_loop2 import run_approval_loop       # Part 3
from json_writer import write_resolutions_to_json # persistence
from classifier import get_classifier_agent
import json


 
def run_pipeline(repo_path, developer_email, output_path="resolutions.json"):
    # 1. PART 1 -- detect all conflicts in the repo
    conflicts = find_all_conflicts(repo_path)
    print(f"Found {len(conflicts)} conflict(s).")
 
    # make the resolver agent once, reuse for every conflict
    agent = get_merge_conflict_agent()
    classifier_agent = get_classifier_agent()

 
    outcomes = []
 
    # 2. process each conflict one at a time
    for conflict in conflicts:
        # the orchestrator CREATES the unique id (no other part produces it).
        # Part 3 uses it to tag the email so replies trace back to this conflict.
        conflict_id = uuid.uuid4().hex[:8]
 
        # 3. PART 2 -- resolve this conflict
        resolution = resolve_one_conflict(agent, conflict)
        if resolution is None:
            # Part 2 couldn't produce a resolution -- record and move on
            print(f"[{conflict_id}] resolution failed, skipping.")
            outcomes.append({"conflict_id": conflict_id, "status": "resolution_failed"})
            continue
 
        # 4. PART 3 -- email the developer and loop until approve/abort/timeout
        outcome = run_approval_loop(
            agent=agent,
            conflict=conflict,
            conflict_id=conflict_id,
            resolution=resolution,
            to_address=developer_email,
            classifier_agent=classifier_agent,
        )
 
        # 5. act on the outcome
        if outcome.status == "approved":
            # THE MERGE HAPPENS HERE -- a Git operation (Part 1's domain).
            # Not built yet: this is where approved code gets merged into main.
            print(f"[{conflict_id}] APPROVED -> (merge would happen here)")
        elif outcome.status == "aborted":
            print(f"[{conflict_id}] ABORTED -> left for manual handling")
        else:  # pending
            print(f"[{conflict_id}] PENDING -> no reply / timed out")
 
        # 6. record the outcome
        outcomes.append({
            "conflict_id": outcome.conflict_id,
            "status": outcome.status,
            "rounds": outcome.rounds,
            "merged_code": outcome.final_resolution.merged_code if outcome.final_resolution else None,
        })
 
    # 7. persist everything
    with open(output_path, "w") as f:
        json.dump(outcomes, f, indent=2)
 
 
if __name__ == "__main__":
    import sys
    repo = sys.argv[1] if len(sys.argv) > 1 else "."
    dev_email = sys.argv[2] if len(sys.argv) > 2 else "developer@example.com"
    run_pipeline(repo, dev_email)