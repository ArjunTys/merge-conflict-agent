# =============================================================================
# STEP 1 + STEP 2 -- MERGE CONFLICT AGENT (single file)
# =============================================================================
# Install dependencies before running:
# pip install gitpython crewai pydantic
#
# Run from the terminal:
# python merge_conflict_agent.py /path/to/your/repo
#
# Output: for every conflict found, prints the structured resolution produced
# by the CrewAI agent defined in agent.py.
# =============================================================================

# --- imports -----------------------------------------------------------------
from dataclasses import dataclass, field
from typing import Optional
import difflib
import git

# --- constants ---------------------------------------------------------------
CONTEXT_LINES = 8


# =============================================================================
# STEP 1: READ THE REPO
# =============================================================================

@dataclass
class BranchInfo:
    name: str
    head_commit: str
    head_message: str
    ahead_of_main: int
    behind_main: int
    is_merged_into_main: bool


@dataclass
class RepoSnapshot:
    repo_path: str
    main_branch: str
    current_branch: str
    branches: list[BranchInfo] = field(default_factory=list)
    diverged_pairs: list[tuple[str, str]] = field(default_factory=list)


def _detect_main_branch(repo: git.Repo) -> str:
    candidates = ["main", "master", "trunk", "develop"]
    branch_names = [h.name for h in repo.heads]
    for candidate in candidates:
        if candidate in branch_names:
            return candidate
    try:
        remote_head = repo.remotes.origin.refs.HEAD.reference.remote_head
        if remote_head in branch_names:
            return remote_head
    except Exception:
        pass
    return sorted(branch_names)[0] if branch_names else ""


def _ahead_behind(repo: git.Repo, branch: str, main: str) -> tuple[int, int]:
    if branch == main:
        return 0, 0
    ahead = sum(1 for _ in repo.iter_commits(f"{main}..{branch}"))
    behind = sum(1 for _ in repo.iter_commits(f"{branch}..{main}"))
    return ahead, behind


def _is_merged(repo: git.Repo, branch: str, main: str) -> bool:
    if branch == main:
        return True
    merge_base = repo.merge_base(branch, main)
    if not merge_base:
        return False
    return merge_base[0].hexsha == repo.heads[branch].commit.hexsha


def read_repo(repo_path: str) -> RepoSnapshot:
    repo = git.Repo(repo_path)
    if repo.bare:
        raise ValueError(f"{repo_path} is a bare repo with no working branches")
    main = _detect_main_branch(repo)
    current = repo.active_branch.name if not repo.head.is_detached else "DETACHED"
    branches: list[BranchInfo] = []
    for head in repo.heads:
        ahead, behind = _ahead_behind(repo, head.name, main)
        branches.append(
            BranchInfo(
                name=head.name,
                head_commit=head.commit.hexsha[:8],
                head_message=head.commit.message.strip().splitlines()[0],
                ahead_of_main=ahead,
                behind_main=behind,
                is_merged_into_main=_is_merged(repo, head.name, main),
            )
        )
    diverged_pairs = []
    active = [b for b in branches if b.name != main and not b.is_merged_into_main]
    for i in range(len(active)):
        for j in range(i + 1, len(active)):
            diverged_pairs.append((active[i].name, active[j].name))
    return RepoSnapshot(
        repo_path=repo_path,
        main_branch=main,
        current_branch=current,
        branches=branches,
        diverged_pairs=diverged_pairs,
    )


# =============================================================================
# STEP 2: EXTRACT CONFLICTS
# =============================================================================

def _get_blob_content(commit: git.Commit, filepath: str) -> Optional[str]:
    try:
        blob = commit.tree[filepath]
        return blob.data_stream.read().decode("utf-8", errors="replace")
    except KeyError:
        return None


def _changed_files(base: git.Commit, tip: git.Commit) -> set[str]:
    return {
        diff.b_path or diff.a_path
        for diff in base.diff(tip)
    }


def _changed_ranges(a: list[str], b: list[str]) -> list[tuple[int, int]]:
    ranges = []
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            ranges.append((i1, i2))
    return ranges


def _expand_and_merge(ranges: list[tuple[int, int]], n: int = 2) -> list[tuple[int, int]]:
    expanded = [(max(0, s - n), e + n) for s, e in ranges]
    merged: list[list[int]] = []
    for s, e in sorted(expanded):
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [tuple(r) for r in merged]  # type: ignore


def _overlapping(
    r1: list[tuple[int, int]],
    r2: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    result = []
    for s1, e1 in r1:
        for s2, e2 in r2:
            start = max(s1, s2)
            end = min(e1, e2)
            if start < end:
                result.append((start, end))
    return result


def _find_conflict_zones(
    ancestor_lines: list[str],
    main_lines: list[str],
    incoming_lines: list[str],
) -> list[dict]:
    main_ranges = _changed_ranges(ancestor_lines, main_lines)
    incoming_ranges = _changed_ranges(ancestor_lines, incoming_lines)
    main_expanded = _expand_and_merge(main_ranges)
    incoming_expanded = _expand_and_merge(incoming_ranges)
    overlapping = _overlapping(main_expanded, incoming_expanded)
    zones = []
    for start, end in overlapping:
        end = min(end, len(ancestor_lines))
        zones.append({
            "ancestor_region": "".join(ancestor_lines[start:end]),
            "main_region": "".join(main_lines[start:end]),
            "incoming_region": "".join(incoming_lines[start:end]),
            "start_line": start,
            "end_line": end,
        })
    return zones


def _extract_context(
    ancestor_lines: list[str],
    start: int,
    end: int,
    n: int = CONTEXT_LINES,
) -> str:
    ctx_start = max(0, start - n)
    ctx_end = min(len(ancestor_lines), end + n)
    before = "".join(ancestor_lines[ctx_start:start])
    after = "".join(ancestor_lines[end:ctx_end])
    return before + "\n...[conflict zone]...\n" + after


def extract_conflicts_for_pair(
    repo: git.Repo,
    main_branch: str,
    incoming_branch: str,
) -> list[dict]:
    main_commit = repo.heads[main_branch].commit
    incoming_commit = repo.heads[incoming_branch].commit
    bases = repo.merge_base(main_branch, incoming_branch)
    if not bases:
        return []
    base_commit = bases[0]
    main_changed = _changed_files(base_commit, main_commit)
    incoming_changed = _changed_files(base_commit, incoming_commit)
    both_changed = main_changed & incoming_changed
    results = []
    for filepath in sorted(both_changed):
        ancestor_content = _get_blob_content(base_commit, filepath)
        main_content = _get_blob_content(main_commit, filepath)
        incoming_content = _get_blob_content(incoming_commit, filepath)
        if any(v is None for v in [ancestor_content, main_content, incoming_content]):
            continue
        ancestor_lines = ancestor_content.splitlines(keepends=True)
        main_lines = main_content.splitlines(keepends=True)
        incoming_lines = incoming_content.splitlines(keepends=True)
        zones = _find_conflict_zones(ancestor_lines, main_lines, incoming_lines)
        for zone in zones:
            results.append({
                "filename": filepath,
                "ancestor": zone["ancestor_region"],
                "main_version": zone["main_region"],
                "incoming_version": zone["incoming_region"],
                "extra_context": _extract_context(
                    ancestor_lines, zone["start_line"], zone["end_line"]
                ),
            })
    return results


def find_all_conflicts(repo_path: str) -> list[dict]:
    snapshot = read_repo(repo_path)
    repo = git.Repo(repo_path)
    all_conflicts = []
    for b in snapshot.branches:
        if b.name == snapshot.main_branch or b.is_merged_into_main:
            continue
        conflicts = extract_conflicts_for_pair(repo, snapshot.main_branch, b.name)
        all_conflicts.extend(conflicts)
    return all_conflicts


# =============================================================================
# RUN FROM TERMINAL
# =============================================================================

if __name__ == "__main__":
    import sys
    import json
    from dataclasses import asdict

    path = sys.argv[1] if len(sys.argv) > 1 else "."

    print("=== STEP 1: Repo snapshot ===")
    snapshot = read_repo(path)
    print(json.dumps(asdict(snapshot), indent=2))

    print("\n=== STEP 2: Conflict zones ===")
    conflicts = find_all_conflicts(path)
    print(json.dumps(conflicts, indent=2))
