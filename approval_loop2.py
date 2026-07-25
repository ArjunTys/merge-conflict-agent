from dataclasses import dataclass
from typing import Literal 
from typing import Optional
from runner import resolve_one_conflict
from classifier import get_classifier_agent, classify_reply
from email_transport import send_email, get_reply
from shared_types import DeveloperReply, ApprovalOutcome






MAX_ROUNDS = 5

def run_approval_loop(agent, conflict, conflict_id, resolution, to_address, classifier_agent):
    for round_number in range(MAX_ROUNDS):
        send_email(to_address, conflict_id, resolution)

        reply = get_reply(conflict_id)

        if reply is None: 
            return ApprovalOutcome(conflict_id=conflict_id, status="pending", rounds=round_number + 1)

        
        classification = classify_reply(classifier_agent, reply.feedback, resolution.alternatives)
        if classification is None:
            real_decision = "reject"
            real_feedback = reply.feedback
        else:
            real_decision = classification.decision
            real_feedback = classification.feedback


        if real_decision == "approve":
            return ApprovalOutcome(
                conflict_id=conflict_id,
                status="approved",
                final_resolution=resolution,
                rounds=round_number + 1,
            )
        
        if real_decision == "abort":
            return ApprovalOutcome(conflict_id=conflict_id, status="aborted", rounds=round_number + 1)
        
        if real_decision == "reject":
            resolution = rework_with_feedback(agent, conflict, real_feedback)
    return ApprovalOutcome(conflict_id=conflict_id, status="pending", rounds=MAX_ROUNDS)


def rework_with_feedback(agent, conflict, feedback):
    # make a copy so we don't modify the original conflict
    conflict_with_feedback = dict(conflict)

    # append the developer's feedback to the existing context
    conflict_with_feedback["extra_context"] = (
        conflict["extra_context"]
        + "\n\nDEVELOPER FEEDBACK ON THE PREVIOUS ATTEMPT:\n"
        + feedback
    )

    # ask Part 2 to resolve again, now with the feedback in context
    return resolve_one_conflict(agent, conflict_with_feedback)

