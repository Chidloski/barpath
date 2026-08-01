"""Gates on the concurrency board, `HEARTBEAT.md`. See CLAUDE.md.

The board is what stops two concurrent agents writing the same file. It is
plain prose that agents edit by appending, so the two things that can go wrong
are a block nobody can parse and two agents holding the same path. Both are
silent — a malformed block reads as "no claim here" to the next agent, which is
the failure mode that loses work.

**This is a format gate, not a lock manager.** Passing it does not mean you hold
what you think you hold; nothing here runs at the moment of an edit, and an
agent that never claimed at all is invisible to it. It catches drift in the
board, which is worth catching, and it should not be read as more.

Two sources, deliberately, because the board is two things at once:

- The **header** is a committed artefact — the format and the pointer at the
  protocol. Gated against the LOCAL copy, so an agent editing the template in a
  worktree tests what it just wrote.
- The **claims** are live shared state. Gated against the SHARED CHECKOUT,
  resolved through git's common dir, because a worktree's copy is a stale base
  revision by construction and its claims are nobody's claims.

Both fall back to the local copy when git cannot answer, so the gate still runs
outside a repo.
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

LOCAL_ROOT = Path(__file__).resolve().parents[1]

STATUSES = {"active", "waiting", "released"}
REQUIRED = ("since", "paths", "status", "note")
SECTIONS = {"Active": "active", "Waiting": "waiting", "Released": "released"}
IMMUTABLE = ("data/raw",)

HEADING = re.compile(r"^##\s+(\w+)", re.M)
BLOCK = re.compile(r"^###\s+(.+)$", re.M)
FIELD = re.compile(r"^-\s*(\w+)\s*:\s*(.*)$")
FENCE = re.compile(r"^```.*?^```", re.M | re.S)
SINCE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?Z$")


def shared_root() -> Path:
    """The shared checkout, not this worktree. See the module docstring."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=LOCAL_ROOT, capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return LOCAL_ROOT
    if out.returncode != 0 or not out.stdout.strip():
        return LOCAL_ROOT
    root = Path(out.stdout.strip()).parent
    return root if (root / "HEARTBEAT.md").is_file() else LOCAL_ROOT


BOARD = shared_root() / "HEARTBEAT.md"
LOCAL_BOARD = LOCAL_ROOT / "HEARTBEAT.md"

needs_board = pytest.mark.skipif(not BOARD.is_file(), reason="no HEARTBEAT.md")
needs_local = pytest.mark.skipif(
    not LOCAL_BOARD.is_file(), reason="no local HEARTBEAT.md")


def claims() -> list[dict]:
    """Every live claim block, tagged with the section it sits under.

    Fenced code is stripped first: the header documents the claim format with a
    worked example, and a gate that cannot tell the example from a live claim
    would fail the moment anyone documented anything.
    """
    text = FENCE.sub("", BOARD.read_text())

    section, out = None, []
    for line in text.splitlines():
        head = HEADING.match(line)
        if head:
            section = SECTIONS.get(head.group(1))
            continue
        block = BLOCK.match(line)
        if block:
            out.append({"_title": block.group(1).strip(), "_section": section})
            continue
        field = FIELD.match(line)
        if field and out:
            out[-1][field.group(1).lower()] = field.group(2).strip()
    return out


def paths_of(claim: dict) -> list[str]:
    raw = claim.get("paths", "")
    return [p.strip().strip("/") for p in raw.split(",") if p.strip()]


def overlap(a: str, b: str) -> bool:
    """True if writing `a` could touch `b`. A directory claims its subtree."""
    pa, pb = Path(a).parts, Path(b).parts
    n = min(len(pa), len(pb))
    return pa[:n] == pb[:n]


@needs_local
def test_board_states_where_it_lives_and_points_at_the_protocol():
    """The header carries the two facts an agent cannot recover on its own."""
    text = LOCAL_BOARD.read_text()
    assert "CLAUDE.md" in text, "board must point at the binding protocol"
    assert "Concurrency protocol" in text
    assert "HEARTBEAT.md" in text, "board must state its own absolute path"


@needs_board
def test_every_claim_block_parses():
    """A block missing a field reads as 'no claim' to the next agent."""
    for claim in claims():
        title = claim["_title"]
        assert claim["_section"] is not None, (
            f"{title!r} sits outside Active/Waiting/Released")
        for key in REQUIRED:
            assert key in claim, f"{title!r} is missing '{key}:'"
        assert SINCE.match(claim["since"]), (
            f"{title!r} has since={claim['since']!r}, want 2026-08-01T15:40Z")
        datetime.strptime(claim["since"][:17], "%Y-%m-%dT%H:%MZ")
        assert claim["status"] in STATUSES, (
            f"{title!r} has status={claim['status']!r}, want one of {STATUSES}")
        assert paths_of(claim), f"{title!r} claims no paths"


@needs_board
def test_status_agrees_with_the_section_it_sits_in():
    """A released block left under Active is a lock nobody will touch."""
    for claim in claims():
        assert claim["status"] == claim["_section"], (
            f"{claim['_title']!r} is status={claim['status']!r} under "
            f"'{claim['_section'].title()}' — move it or fix the status")


@needs_board
def test_no_two_active_claims_overlap():
    """The invariant the whole board exists to hold."""
    held = [(c, p) for c in claims() if c["status"] == "active"
            for p in paths_of(c)]
    for i, (claim_a, path_a) in enumerate(held):
        for claim_b, path_b in held[i + 1:]:
            if claim_a is claim_b:
                continue
            assert not overlap(path_a, path_b), (
                f"{claim_a['_title']!r} holds {path_a!r} and "
                f"{claim_b['_title']!r} holds {path_b!r} — the earlier "
                f"'since' wins, the later block withdraws")


@needs_board
def test_immutable_paths_are_not_claimed():
    """`data/raw/` is read-only for everyone, so a claim on it is a mistake."""
    for claim in claims():
        for path in paths_of(claim):
            for locked in IMMUTABLE:
                assert not overlap(path, locked), (
                    f"{claim['_title']!r} claims {path!r}; {locked}/ is "
                    f"immutable and never needs claiming")


def test_overlap_is_subtree_aware():
    """The rule the board's 'a directory claims everything under it' rests on."""
    assert overlap("src/correct.py", "src/correct.py")
    assert overlap("src", "src/correct.py")
    assert overlap("src/correct.py", "src")
    assert not overlap("src/correct.py", "src/segment.py")
    assert not overlap("src", "tests")
    assert not overlap("analysis/35_a.png", "analysis/36_b.png")
