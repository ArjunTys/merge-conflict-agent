from crewai import Agent, Task
from pydantic import BaseModel, Field
from typing import Literal
 
llm = "groq/llama-3.3-70b-versatile"
 
 

 
class ReplyClassification(BaseModel):
    decision: Literal["approve", "reject", "abort"] = Field(
        description=(
            "The developer's decision. "
            "'approve' = they accept the proposed merge as-is. "
            "'reject' = they want changes (they gave feedback or picked an alternative). "
            "'abort' = they want to stop and handle this conflict manually themselves."
        )
    )
    feedback: str = Field(
        default="",
        description=(
            "On 'reject', the developer's concrete instruction for the rework, in plain terms "
            "(e.g. 'prioritize the cart-total discount' or 'use alternative 2: ...'). "
            "If they referenced a numbered alternative, resolve it to that alternative's actual text. "
            "Empty for approve or abort."
        )
    )
 
 

 
def get_classifier_agent():
    return Agent(
        role="An assistant that reads a developer's email reply about a proposed "
             "merge-conflict resolution and determines their decision.",
        goal="Accurately classify the reply as approve, reject, or abort, and on "
             "reject, capture the developer's intended change as clear feedback.",
        backstory=(
            "Careful reader of terse developer messages. Understands that natural "
            "language carries intent that keywords miss -- 'no problem, ship it' is "
            "an approval, 'not quite' is a rejection. Never guesses: when a reply is "
            "genuinely ambiguous, treats it as a rejection asking for clarification "
            "rather than risking an unwanted merge."
        ),
        llm=llm,
    )
 
 
def _format_alternatives(alternatives) -> str:
    if not alternatives:
        return "(none were offered)"
    return "\n".join(f"  {i}. {alt}" for i, alt in enumerate(alternatives, start=1))
 
 
def classify_reply(agent, reply_text, alternatives=None):
    """
    Given the developer's raw reply text (and the alternatives that were
    offered), return a ReplyClassification (decision + feedback).
    Returns None if the model failed to produce a valid classification.
    """
    alternatives = alternatives or []
 
    task = Task(
        description=f"""A developer was emailed a proposed merge-conflict resolution and asked to
approve it, reject it with feedback, or abort (handle it manually).
 
Here are the alternative resolutions that were offered to them, numbered:
{_format_alternatives(alternatives)}
 
Here is the developer's reply (only their own words, quoted history removed):
\"\"\"
{reply_text}
\"\"\"
 
Classify their decision:
- approve: they accept the proposed resolution as-is (e.g. "yes", "lgtm", "ship it",
  "looks good", "no problem, merge it"). Note that words like "no" can appear in an
  approval -- judge the overall intent, not individual words.
- reject: they want changes -- they gave instructions, objected, or picked one of the
  numbered alternatives above. Capture what they want in the feedback field. If they
  referenced an alternative by number or description, resolve it to that alternative's
  actual text and put it in feedback.
- abort: they want to stop and handle this conflict themselves manually (e.g.
  "don't bother", "I'll handle this one", "leave it, I'll do it").
 
If the reply is genuinely ambiguous or you cannot tell, classify it as 'reject'
with feedback explaining that the reply was unclear -- never approve on a guess.
""",
        expected_output="A classification with a decision (approve/reject/abort) and, on reject, the feedback.",
        agent=agent,
        output_pydantic=ReplyClassification,
    )
 
    try:
        crew_task = task
        from crewai import Crew
        crew = Crew(agents=[agent], tasks=[crew_task])
        crew.kickoff()
        return crew_task.output.pydantic
    except Exception as e:
        print(f"Reply classification failed: {e}")
        return None
 