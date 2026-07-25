# Merge Conflict Resolution Agent

An AI agent that automatically resolves Git merge conflicts. When two branches change the same code in different ways, Git can't decide how to combine them and stops for a human. Today a senior developer resolves these by hand — understanding what each side intended and merging them. This system does that automatically: it detects conflicts, resolves them with an LLM, emails a developer for approval, and loops on their feedback until they sign off.

## Why this exists

In development environments where many automated agents commit to the same
branches — for example, AI systems that read change requests, write code, and
push commits on their own — merge conflicts pile up faster than developers can
resolve them by hand. Development becomes fast, but delivery slows down because
conflict resolution is the bottleneck. This agent removes that bottleneck by
resolving conflicts automatically while keeping a human in the loop for approval.

## How it works (the pipeline)

The project is split into four parts with clean interfaces between them:

**Part 1 — Detection** (`detector.py`)
Reads any repo from a path, maps its branches, finds files both sides changed, and extracts each conflicting region. Outputs a list of conflict dicts, each with five fields: `filename`, `ancestor`, `main_version`, `incoming_version`, `extra_context`. Works on any repo — nothing hardcoded.

**Part 2 — Resolution** (`agent.py`, `runner.py`)
Takes one conflict and resolves it with an LLM. It reasons in two phases: first it *understands* each version separately (what each side changed and why), then it *decides* how to resolve. Returns a structured object with the merged code, each side's intent, the reasoning, a confidence level, a note on any uncertainty, and a list of alternatives.

**Part 3 — Approval loop** (`approval_loop2.py`, `email_transport.py`, `classifier.py`)
Emails the developer the proposed resolution and waits for a reply. A classifier reads their plain-English response and decides whether it's an approve, reject, or abort. On approve → done. On reject → the developer's feedback goes back to Part 2 for a reworked resolution, which is re-emailed (loops until approved or aborted). On abort → the conflict is left for manual handling.

**Part 4 — Orchestration** (`orchestrator.py`)
The conductor. Chains everything: detect → resolve → email loop → act on the outcome → write results to JSON. Assigns each conflict a unique id used to tag its email so replies can be matched back.

## File guide

| File | Part | What it does |
|------|------|--------------|
| `detector.py` | 1 | Reads a repo, finds conflicts, outputs the five-field dicts. |
| `agent.py` | 2 | Defines the resolver agent, its task/prompt, and the `ConflictResolution` schema. |
| `runner.py` | 2 | Runs the resolver over a conflict (`resolve_one_conflict`, `resolve_all_conflicts`). |
| `approval_loop2.py` | 3 | The approval loop — emails, gets the reply, classifies it, routes approve/reject/abort. |
| `email_transport.py` | 3 | Real email: SMTP sending + IMAP inbox polling. |
| `classifier.py` | 3 | LLM step that turns a plain-English reply into approve/reject/abort + feedback. |
| `orchestrator.py` | 4 | Chains all parts together and writes results to JSON. |
| `shared_types.py` | — | Shared dataclasses (`DeveloperReply`, `ApprovalOutcome`), imported by others. |
| `json_writer.py` | — | Writes resolution outcomes to a JSON file. |
| `utils/config.py` | — | Loads credentials from `.env` into the environment. |

## Setup

1. Install dependencies:
pip install -r requirements.txt

2. Create a `.env` file in the project root (and make sure it's in `.gitignore`):
GROQ_API_KEY=your_groq_api_key
AGENT_EMAIL=the_bot_email@gmail.com
AGENT_EMAIL_PASSWORD=gmail_app_password

The email password must be a Gmail **App Password** (requires 2-Step Verification enabled on the account), not the regular account password.

## Running it
python3 orchestrator.py /path/to/repo developer@email.com

It detects conflicts in the repo, resolves them, emails the developer address for each, and waits for replies. Reply to the email with your decision (approve / reject with feedback / abort), keeping the subject line intact — the conflict-id tag in it is how your reply gets matched. Results are written to `resolutions.json`.

## Model

Uses Groq-hosted Llama 3.3 70B. Chosen to prove the pipeline cheaply first; validated on both simple and ambiguous conflicts, including honest confidence calibration on hard cases. Note: the free Groq tier has a 12,000 tokens/minute limit, which a busy run can hit — a paid tier or call spacing would be needed at scale.

## Status

Working end to end and tested across all reply paths: approve, reject-and-rework, picking a listed alternative, novel free-text feedback, abort, and the tricky "no means yes" case. The full loop (detect → resolve → email → classify → rework → approve) has been validated with real email round-trips.

## Known limitations / future work

- **The actual Git merge on approval is not yet implemented** — on approval the system currently marks the conflict approved but does not perform the real merge into main (a Git write operation, Part 1's domain).
- **Developer-supplied code is re-interpreted, not adopted verbatim.** If a developer pastes literal code in a reply, it's fed to Part 2 as feedback and re-resolved rather than used as-is. In practice a developer wanting to write the fix themselves would use the *abort* path, so this is minor — but could be added.
- **No UI yet** — currently run from the terminal; a Streamlit front end is planned.
- Conflict detection uses a line-overlap heuristic rather than Git's real three-way merge detection, so it may occasionally over- or under-flag.