from crewai import Agent, Task
from pydantic import BaseModel, Field
from typing import Literal

llm = "groq/llama-3.3-70b-versatile"

class ConflictResolution(BaseModel):
    merged_code: str = Field(description="The recommended resolved code, ready to commit, following the file's language conventions.")
    main_intent: str = Field(description="What main's version was trying to do.")
    incoming_intent: str = Field(description="What the incoming branch's version was trying to do.")
    reasoning: str = Field(description="Why this resolution was chosen.")
    confidence: Literal["high", "medium", "low"] = Field(description="How confident the resolution is, for developer triage.")
    confidence_note: str = Field(description="Where the uncertainty lies, when confidence is medium or low. Empty if high.")
    #alternatives: list[str] = Field(description="Other resolutions considered but not chosen, so the developer can pick an alternative.")
    alternatives: list[str] = Field(description="Other resolutions considered but not chosen, so the developer can pick an alternative. Each alternative must be a SEPARATE, self-contained item in the list — one distinct alternative per element, never multiple alternatives combined into one string.")





def get_merge_conflict_agent():
    role = "An experienced engineer who resolves Git merge conflicts by intelligently integrating code changes from multiple branches or selectively accepting the appropriate version when necessary."
    goal = "Generate an accurate and well-justified merge conflict resolution, accompanied by a clear explanation, confidence assessment, and possible alternatives, enabling developers to efficiently review and approve or modify the solution."

    
    backstory = (
    "A senior engineer who has spent years resolving merge conflicts on large, "
    "fast-moving teams where many developers commit to the same files daily. "
    "Known for resolving conflicts not by blindly picking a side, but by carefully "
    "understanding what each developer was trying to accomplish and preserving the "
    "intent of every change wherever possible. Reads code closely, respects the "
    "conventions of whatever language is in front of them, and integrates competing "
    "changes so that nothing important is silently lost."
)

    merge_conflict_agent = Agent(role=role, goal=goal, backstory=backstory, llm=llm)
    return merge_conflict_agent

def create_merge_conflict_task(merge_conflict_agent, filename, ancestor, main_version, incoming_version, extra_context):
    task = Task(
        description = f"""You are resolving a single merge conflict. Here are the inputs.

File name: {filename}

Common ancestor (the original both sides started from):

{ancestor}

Main's current version:

{main_version}

Incoming branch's version:

{incoming_version}

Surrounding context (code around the conflict, for understanding intent):

{extra_context}


Now follow these steps to resolve the conflict.

STEP 1 — UNDERSTAND EACH VERSION

Analyze main's version and the incoming version separately. For each one, answer:

- What is this version doing?
- What did it change relative to the common ancestor?
- Why might the developer have made this change?
- What would break if this version were discarded?

If other questions would deepen your understanding of either version, ask and answer them too. In this step, only describe and understand each version. Do not yet decide how to resolve the conflict.

STEP 2 — DECIDE HOW TO RESOLVE

Now that you understand both versions, decide how to resolve the conflict.

Compare the two versions directly and weigh each one's strengths and weaknesses. Keep in mind that a resolution can take different forms:
- Combine both versions, integrating each side's changes so nothing important is lost.
- Keep one version and discard the other, if one does not belong or would break things.
- Blend them, taking parts of each.

Based on that comparison, choose a single recommended resolution. Also note the main alternative resolution(s) you considered but did not choose, so the developer has other options to pick from. List each alternative as its own separate item, one distinct alternative per item, so they can be referred to by number (alternative 1, alternative 2, and so on).


Any code you write must follow the conventions and best practices of the file's language (for example, correct indentation in Python). If the existing code does not follow them, correct it.

Finally, assign a confidence level to your recommended resolution: high, medium, or low.
Reserve HIGH confidence for cases where the resolution is essentially unambiguous: the two sides made independent, non-overlapping changes that clearly combine in only one sensible way, and you did not have to make any judgment call.
Use MEDIUM or LOW confidence whenever your resolution required a real decision that could reasonably have gone another way. In particular, if the two versions' logic OVERLAPS or INTERACTS, and you had to choose an ordering, a precedence, or which rule wins in a case both could apply to, that is NOT high confidence. Choosing between defensible alternatives is exactly the situation a developer needs to review.
Whenever confidence is medium or low, state in the confidence note precisely which decision you were unsure about and what the competing options were, so the developer knows what to scrutinize.

STEP 3 — PRODUCE THE RESOLUTION

Assemble your final answer containing all of the required parts: the merged code, an explanation of each version's intent, your reasoning for the chosen resolution, the alternative resolution(s) you considered, and your confidence level (with the location of any uncertainty if confidence is medium or low). Produce this in exactly the structured format specified below.

""",
        expected_output= "A structured resolution containing the merged code, each side's intent, the reasoning, a confidence level (high/medium/low) with a note on any uncertainty, and the alternatives considered." ,
        agent= merge_conflict_agent,
        output_pydantic= ConflictResolution
    )


        
    return task
    

    