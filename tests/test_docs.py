"""Gates that keep the documentation from drifting away from the code.

**These exist because the same-commit docs rule in `CLAUDE.md` has not been
enough on its own.** It is a good rule and it is followed most of the time, but
it is enforced by nothing, so what it actually produces is documentation that is
correct until somebody is in a hurry. The failures it has let through are all
the same shape — a claim outliving its evidence:

  * `FINDINGS.md` reached 9,407 lines, of which 6,800 were a reverse-
    chronological task log, and went uncommitted for a day while two sessions
    of findings piled up behind a stale lock.
  * `NON_GOALS.md` kept rejections whose evidence had expired.
  * The reserved-module banners survived the lockout being lifted.
  * Milestones 1-6 passed on gates that no longer tested anything.

A rule cannot catch those. A test run can catch some of them, and the ones it
can catch are worth catching mechanically rather than by review. Everything
here is cheap, reads only text, and needs no data.

Added 2026-08-23 (H32) on the owner's instruction to "update the behaviour so
that findings.md stays up to date".
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FINDINGS = ROOT / "FINDINGS.md"

# Docs that are prose about the project, as opposed to captured output.
DOCS = ["CLAUDE.md", "FINDINGS.md", "TASKS.md", "README.md",
        "analysis/README.md", "src/README.md", "watch/README.md"]

# Files deleted on 2026-08-23 (H32). A live reference to one of these is a
# broken pointer, not history — unlike `markers.py` and `truth.py`, which are
# also gone but are referenced ON PURPOSE, with `git show` recovery lines, all
# over the docs and the code. That is the distinction this list encodes: it
# names the paths that should have no mentions at all, and nothing else.
DELETED_PATHS = [
    "HANDOFF.md",
    "NON_GOALS.md",
    "analysis/tracking/v2_rebuild",
]

# `FINDINGS.md` is a verdict list. Above this it is turning back into a diary.
#
# 376 lines when rewritten, from 9,407. The budget is deliberately loose — it
# has to admit real growth, since new mechanisms genuinely do need entries —
# and deliberately finite, because the failure mode here is not one bad commit
# but a hundred good ones each adding a paragraph. If this fires, the fix is to
# REWRITE the entries that have accumulated qualifications, not to raise the
# number.
FINDINGS_MAX_LINES = 700


def _text(rel):
    p = ROOT / rel
    return p.read_text() if p.is_file() else ""


def _all_sources():
    for pat in ("src/**/*.py", "tests/*.py", "analysis/*.py", "run.py"):
        yield from ROOT.glob(pat)


# --------------------------------------------------------------- shape ------

def test_findings_is_a_verdict_list_not_a_diary():
    """No dated task entries. The narrative belongs in `git log`.

    `FINDINGS.md` accumulated 57 entries of the form `### H28 — ... (2026-08-20)`,
    newest first. Each one was a good account of a day's work and collectively
    they were 6,800 lines nobody could read, wrapped around the verdicts, which
    are what a reader actually comes for. The rule is that a finding is stated
    once, in the present tense, and rewritten when it changes.
    """
    diary = re.findall(r"^#{2,4} +(?:[A-Z]\d+[a-z]? +[—-] .*)$",
                       _text("FINDINGS.md"), re.M)
    assert not diary, (
        "FINDINGS.md has grown dated task entries again:\n  "
        + "\n  ".join(diary[:10])
        + "\nState the verdict in the relevant section and rewrite what it "
          "replaced; the chronology is in git log.")


def test_findings_has_not_bloated_again():
    n = len(_text("FINDINGS.md").splitlines())
    assert n <= FINDINGS_MAX_LINES, (
        f"FINDINGS.md is {n} lines against a {FINDINGS_MAX_LINES} budget. "
        f"Rewrite the entries that have accumulated qualifications rather than "
        f"raising the budget — the point of the budget is that it forces that.")


def test_findings_still_carries_the_load_bearing_sections():
    """The budget must not be met by deleting the content instead.

    Paired with the test above deliberately: a line cap with no floor is an
    invitation to satisfy it the wrong way.
    """
    text = _text("FINDINGS.md")
    for heading in ("Reading a number here", "What ships", "What works",
                    "What does not work", "The open problems"):
        assert heading in text, f"FINDINGS.md lost its '{heading}' section"
    # P1-P6 are the problems this project is organised around.
    for p in ("P1", "P2", "P3", "P4", "P5", "P6"):
        assert re.search(rf"\b{p}\b", text), f"FINDINGS.md no longer mentions {p}"


# ------------------------------------------------------ dangling pointers ---

@pytest.mark.parametrize("gone", DELETED_PATHS)
def test_nothing_points_at_a_deleted_file(gone):
    """A reference to a file that no longer exists is a broken pointer.

    Distinct from a reference to deleted CODE, which this repo does on purpose
    and at length — `markers.py` and `truth.py` are cited all over the docs with
    `git show` recovery lines, and that is the record working as intended. The
    difference is that those citations say "this is gone, here is how to get
    it"; a leftover path reads as though the file is still there.
    """
    def _live_hits(name, lines):
        """Mentions that read as though the file still exists.

        A mention within `WINDOW` lines of the word "delet" is an epitaph — the
        repo writes those deliberately, with `git show` recovery lines, and they
        are the record working as intended. Anything else is a pointer at
        nothing.
        """
        window = 12
        out = []
        for i, line in enumerate(lines):
            if gone not in line:
                continue
            near = " ".join(lines[max(0, i - window):i + window + 1]).lower()
            if "delet" in near:
                continue
            out.append(f"{name}:{i + 1}")
        return out

    hits = []
    for rel in DOCS:
        hits += _live_hits(rel, _text(rel).splitlines())
    for src in _all_sources():
        if src.name == "test_docs.py":
            continue          # this file names them to forbid them
        try:
            hits += _live_hits(str(src.relative_to(ROOT)),
                               src.read_text().splitlines())
        except (UnicodeDecodeError, OSError):
            continue
    assert not hits, (
        f"{gone} was deleted on 2026-08-23 but is still referenced, as though "
        f"it exists, at:\n  " + "\n  ".join(hits)
        + "\nEither drop the reference or write it as an epitaph — say it was "
          "deleted and how to recover it.")


# ------------------------------------------------------ analysis hygiene ----

def test_analysis_holds_only_figures_and_its_readme():
    """`analysis/` is PNGs and a README. Owner's rule, 2026-08-25.

    It had accumulated 21 measurement scripts, 6 JSON caches, 6 working notes
    and a generated HTML page beside 89 figures. Each script was a one-off whose
    RESULT is written into `analysis/README.md`, so what they added was bulk and
    a second place to look.

    The trade is real and is stated in that README: a figure here is no longer
    reproducible from the repo, and `git show` is the recovery path. **Anything
    that must stay runnable belongs in `src/`** — `src/gallery.py` moved there
    on the same day rather than being deleted with the rest, because it
    generates a deliverable rather than recording a measurement.
    """
    strays = sorted(p.name for p in (ROOT / "analysis").iterdir()
                    if p.is_file() and p.suffix.lower() != ".png"
                    and p.name.lower() != "readme.md")
    assert not strays, (
        "analysis/ holds only PNGs and README.md; these do not belong: "
        + ", ".join(strays)
        + ". If it must stay runnable it goes in src/; if it is a result, "
          "write the result into analysis/README.md.")


# ------------------------------------------------- code the docs never met --

def test_every_src_module_is_documented_somewhere():
    """A module that ships undocumented is the drift this file exists to stop.

    Names only — this cannot check that what is written is TRUE, and does not
    pretend to. What it catches is the case that actually happens: a new module
    lands, the docs describe the pipeline as it was, and a reader is given a
    complete-looking account with a piece missing.
    """
    prose = "\n".join(_text(d) for d in DOCS)
    undocumented = []
    for mod in sorted(ROOT.glob("src/**/*.py")):
        if mod.name == "__init__.py":
            continue
        if mod.name not in prose:
            undocumented.append(str(mod.relative_to(ROOT)))
    assert not undocumented, (
        "these modules are not named in any prose doc: "
        + ", ".join(undocumented)
        + " — add them where the pipeline or the referee is described")
