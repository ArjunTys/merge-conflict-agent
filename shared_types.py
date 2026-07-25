from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class DeveloperReply:
    conflict_id: str
    decision: Literal["approve", "reject", "abort"]
    feedback: str = ""


@dataclass
class ApprovalOutcome:
    conflict_id: str
    status: Literal["approved", "aborted", "pending"]
    final_resolution: Optional[object] = None
    rounds: int = 1
