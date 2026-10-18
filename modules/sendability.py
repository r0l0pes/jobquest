"""Deterministic sendability gate for a generated application package.

This module answers one question with deterministic code only:

    Is the generated resume package safe to move to ``ready_to_apply``?

No LLM call may influence the verdict. Every input is either a pipeline
artifact, a parsed/validated LaTeX string, or an explicitly recorded outcome
from an optional pipeline stage.

Verdicts:

* ``READY_TO_SEND``         - all required checks pass, no meaningful warnings.
* ``READY_WITH_WARNINGS``   - all required checks pass, an optional stage failed.
* ``HOLD``                  - at least one required check failed.

``READY_TO_SEND`` means only "safe to move to ``ready_to_apply``". It does NOT
mean applied, submitted, tracker-complete, or interview-ready.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from modules.parsers import (
    build_evidence_corpus,
    find_unsupported_claims,
    format_unsupported_claims,
    locked_experience_drift,
    validate_resume_draft,
)

# ─── Verdicts ────────────────────────────────────────────────────

READY_TO_SEND = "READY_TO_SEND"
READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
HOLD = "HOLD"

SENDBILITY_STATUSES = (READY_TO_SEND, READY_WITH_WARNINGS, HOLD)

# ─── Check outcomes ──────────────────────────────────────────────

CHECK_PASS = "PASS"  # pi-lens-ignore: python-hardcoded-secrets
CHECK_FAIL = "FAIL"
CHECK_WARN = "WARN"
CHECK_SKIPPED = "SKIPPED"
NOT_YET_WIRED = "NOT_YET_WIRED"
NOT_APPLICABLE = "NOT_APPLICABLE"

# ─── Blocker codes ───────────────────────────────────────────────

BLOCK_RESUME_ARTIFACT_MISSING = "RESUME_ARTIFACT_MISSING"
BLOCK_RESUME_ARTIFACT_EMPTY = "RESUME_ARTIFACT_EMPTY"
BLOCK_PDF_MISSING = "PDF_MISSING"
BLOCK_PDF_EMPTY = "PDF_EMPTY"
BLOCK_INTEGRITY_FAILED = "INTEGRITY_FAILED"
BLOCK_INTEGRITY_UNVERIFIABLE = "INTEGRITY_UNVERIFIABLE"
BLOCK_LOCKED_EXPERIENCE_DRIFT = "LOCKED_EXPERIENCE_DRIFT"
BLOCK_LOCKED_EXPERIENCE_UNVERIFIABLE = "LOCKED_EXPERIENCE_UNVERIFIABLE"
BLOCK_TAILORING_MODE_UNKNOWN = "TAILORING_MODE_UNKNOWN"
BLOCK_TAILORING_FALLBACK_UNTAILORED = "TAILORING_FALLBACK_UNTAILORED"
BLOCK_TAILORING_NO_EFFECTIVE_EDITS = "TAILORING_NO_EFFECTIVE_EDITS"
BLOCK_TAILORING_OUTCOME_UNKNOWN = "TAILORING_OUTCOME_UNKNOWN"
BLOCK_UNRESOLVED_PLACEHOLDER = "UNRESOLVED_PLACEHOLDER"
# Live Pilot Hotfix H1: a materially new factual claim in the final resume that
# the candidate-controlled evidence corpus does not support.
BLOCK_UNSUPPORTED_NOVEL_CLAIM = "UNSUPPORTED_NOVEL_CLAIM"

# ─── Warning codes ───────────────────────────────────────────────

WARN_REVIEWER_FAILED = "REVIEWER_FAILED"
WARN_ATS_SEMANTIC_UNAVAILABLE = "ATS_SEMANTIC_UNAVAILABLE"
# Advisory (non-blocking) novel-claim findings: a resume that mirrors the
# employer's own wording. Visible, never a HOLD on its own.
WARN_JD_ONLY_KEYWORDS = "JD_ONLY_KEYWORDS"

# Optional stages that run AFTER the required sendability evaluation. Their
# requested-and-failed outcomes are folded into the persisted report by
# ``finalize_optional_stage_warnings``; intentional skips never appear here.
WARN_QA_FAILED = "QA_FAILED"
WARN_COVER_LETTER_FAILED = "COVER_LETTER_FAILED"
WARN_INTERVIEW_PREP_FAILED = "INTERVIEW_PREP_FAILED"
# Late-stage advisory: the cover-letter prune pass could not deliver a body that
# passed the no-ai-slop style check, so the safe first-pass draft is kept and a
# human must review it before sending. Non-blocking, like the optional-stage
# warnings above; it never produces or clears a HOLD.
WARN_COVER_LETTER_HUMAN_REVIEW_REQUIRED = "COVER_LETTER_HUMAN_REVIEW_REQUIRED"

# ─── Canonical runtime tailoring mode ────────────────────────────
#
# Which tailoring path actually produced the final resume. This is recorded once
# by the pipeline and consumed here; the gate never infers applicability from
# environment configuration such as TARGETED_EDITS.
TAILORING_TARGETED = "targeted"
TAILORING_FULL = "full"
TAILORING_UNKNOWN = "unknown"
TAILORING_MODES = (TAILORING_TARGETED, TAILORING_FULL)

# ─── Canonical runtime tailoring outcome ────────────────────
#
# Separate axis from tailoring_mode. ``tailoring_mode`` records which generation
# strategy ran; ``tailoring_outcome`` records whether a valid tailored resume
# actually survived. The pipeline recovers from a rejected draft by substituting
# the untailored base template, which is a required-output failure, not a
# factual-integrity one. A patch can also apply and validate successfully while
# leaving the artifact identical to the baseline - that is not tailoring either.
TAILORING_OUTCOME_TAILORED = "tailored"
TAILORING_OUTCOME_FALLBACK_UNTAILORED = "fallback_untailored"
TAILORING_OUTCOME_NO_EFFECTIVE_EDITS = "no_effective_edits"
TAILORING_OUTCOME_UNKNOWN = "unknown"
TAILORING_OUTCOMES = (
    TAILORING_OUTCOME_TAILORED,
    TAILORING_OUTCOME_FALLBACK_UNTAILORED,
    TAILORING_OUTCOME_NO_EFFECTIVE_EDITS,
)

# ─── Tracker lifecycle ───────────────────────────────────────────

STATUS_GENERATED = "generated"
STATUS_READY_TO_APPLY = "ready_to_apply"

# Lifecycle order. A later/manual state always wins over automatic promotion:
# Gate A.3 may move generated -> ready_to_apply, and nothing else, ever.
STATUS_RANK: dict[str, int] = {
    "generated": 0,
    "ready_to_apply": 1,
    "applied": 2,
    "screening": 3,
    "interview": 4,
    "offer": 5,
    "rejected": 6,
}

REPORT_FILENAME = "sendability_report.json"

# ─── Unresolved-placeholder detection ────────────────────────────
#
# Conservative by design: only tokens that cannot legitimately appear in a
# finished resume. Deliberately excludes brace-based markers such as ``{{``
# because LaTeX legitimately nests groups with doubled braces, which would
# cause false HOLDs.
UNRESOLVED_PLACEHOLDER_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bPLACEHOLDER\b", re.IGNORECASE), "PLACEHOLDER"),
    (re.compile(r"\bTODO\b", re.IGNORECASE), "TODO"),
    (re.compile(r"\bFIXME\b", re.IGNORECASE), "FIXME"),
    (re.compile(r"\bXXX+\b"), "XXX"),
    (re.compile(r"\bLOREM IPSUM\b", re.IGNORECASE), "LOREM IPSUM"),
    (re.compile(r"<INSERT\b", re.IGNORECASE), "<INSERT"),
    (re.compile(r"\[INSERT\b", re.IGNORECASE), "[INSERT"),
    (re.compile(r"\bINSERT_[A-Z_]+\b"), "INSERT_*"),
    (re.compile(r"\bYOUR[_ ](?:NAME|TITLE|COMPANY)\b", re.IGNORECASE), "YOUR_NAME/TITLE/COMPANY"),
)

# ``compile_and_inspect`` legitimately rewrites the .tex during its
# fix-and-recompile loop, inserting these layout-only commands as their own line
# (see scripts/render_pdf.py::_apply_fixes). They are not authored content, so
# they are stripped before content checks to avoid false HOLDs.
#
# Actual matching semantics - deliberately broader than a whole-line match:
#   * the command must start the line (leading spaces/tabs are allowed);
#   * trailing spaces/tabs and the line break are consumed with it, so a line
#     holding only the command disappears completely and the surrounding bytes
#     are restored exactly. Consuming the break is load-bearing: deleting only
#     the command text would leave a blank line behind and report phantom
#     locked-experience drift whenever a fix landed inside a locked block;
#   * a line that merely *starts* with the command keeps the remainder, and a
#     command that is not at line start is left untouched.
#
# There is intentionally no end-of-line anchor. Anchoring would leave a
# prefix-style insertion in place and thereby recreate the same false HOLD,
# whereas this form stays byte-reversible for both own-line and prefix insertions.
_COMPILE_LAYOUT_COMMAND = re.compile(
    r"^[ \t]*\\(?:needspace|enlargethispage)\{[^}]*\}[ \t]*\r?\n?", re.MULTILINE
)


def normalize_for_tailoring_effect_comparison(latex: str) -> str:
    """Normalize ONLY serialization churn for the effective-tailoring check.

    Two artifacts normalize to the same string only when they differ purely by
    meaningless serialization: CR/CRLF line endings, trailing spaces and tabs,
    and blank or whitespace-only lines.

    Blank lines are dropped rather than collapsed to one, because the resume
    patcher itself re-emits itemize blocks without the template's inter-bullet
    blank lines; keeping even a single blank line could never compare equal to a
    re-emitted block that has none.

    Everything inside a non-blank line is preserved exactly, so wording, numbers,
    punctuation, ordering, internal spacing and LaTeX commands all stay fully
    detectable. This is deliberately NOT an "remove all whitespace" comparison,
    and it is used only to classify tailoring effect - never for factual
    validation, locked-experience drift, PDF compilation, patch application or
    the shipped artifact.
    """
    text = latex.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(
        line.rstrip(" \t") for line in text.split("\n") if line.strip()
    )


def strip_compile_layout_commands(latex: str) -> str:
    """Remove layout-only commands inserted by the PDF auto-fix loop.

    A line holding only the command (plus optional trailing whitespace) is
    removed together with its line break, which restores the artifact to the
    byte sequence the author produced so a successful auto-fix cannot be
    mistaken for content drift. A line that starts with the command but carries
    further content keeps that remainder, and a command that is not at line
    start is left untouched.
    """
    return _COMPILE_LAYOUT_COMMAND.sub("", latex)


def find_unresolved_placeholders(latex: str) -> list[str]:
    """Return the sorted set of placeholder tokens present in ``latex``."""
    found = {
        label
        for pattern, label in UNRESOLVED_PLACEHOLDER_PATTERNS
        if pattern.search(latex)
    }
    return sorted(found)


# ─── Tracker status resolution ───────────────────────────────────


def promoted_tracker_status(sendability_status: str | None) -> str:
    """Map a sendability verdict onto the automatic tracker status.

    Anything that is not a clean pass stays ``generated``, so an absent or
    failed evaluation can never promote a package.
    """
    if sendability_status in (READY_TO_SEND, READY_WITH_WARNINGS):
        return STATUS_READY_TO_APPLY
    return STATUS_GENERATED


def resolve_tracker_status(existing_status: str | None, candidate: str) -> str:
    """Return the status to persist, never downgrading an existing state.

    * no existing status        -> the candidate
    * unknown/external status   -> preserved untouched
    * later lifecycle state     -> preserved (never downgraded)
    * otherwise                 -> the candidate (forward move only)
    """
    if not existing_status:
        return candidate
    existing_rank = STATUS_RANK.get(existing_status)
    if existing_rank is None:
        return existing_status
    if existing_rank > STATUS_RANK.get(candidate, 0):
        return existing_status
    return candidate


# ─── Evaluation ──────────────────────────────────────────────────


def evaluate_sendability(
    *,
    run_id: str,
    final_latex: str | None,
    resume_artifact_present: bool,
    resume_artifact_bytes: int,
    pdf_present: bool,
    pdf_bytes: int,
    master_resume: str | None,
    canonical_template: str | None,
    tailoring_mode: str | None = None,
    tailoring_outcome: str | None = None,
    tailoring_noop_reference: str | None = None,
    reviewer_failed: bool = False,
    ats_semantic_unavailable: bool = False,
    reviewer_skipped: bool = False,
    ats_semantic_skipped: bool = False,
    questions_check: str = NOT_YET_WIRED,
    skills_inventory: str | None = None,
    career_config: str | None = None,
    story_bank: str | None = None,
    jd_skill_terms: tuple[str, ...] | list[str] = (),
    evaluated_at: str | None = None,
) -> dict:
    """Evaluate a generated package deterministically.

    Pure with respect to the filesystem: callers pass already-gathered facts,
    so the same inputs always produce the same verdict given the same
    ``evaluated_at``.
    """
    blockers: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    checks: dict[str, str] = {}

    latex = strip_compile_layout_commands(final_latex or "")

    # Effective tailoring is judged on the FINAL artifact, not only on the
    # snapshot taken when the patch was applied: later stages (reviewer edits,
    # grounded ATS edits) can introduce a genuine change, and any compile layout
    # auto-fix is already stripped above. Only the snapshot outcome
    # ``no_effective_edits`` is re-judged; an explicit ``fallback_untailored`` is
    # a different event and must never be overridden here. The same helper and
    # the same run-baseline reference are used at both sites, so there is only
    # one definition of effective tailoring.
    if (
        tailoring_outcome == TAILORING_OUTCOME_NO_EFFECTIVE_EDITS
        and tailoring_noop_reference is not None
        and normalize_for_tailoring_effect_comparison(latex)
        != normalize_for_tailoring_effect_comparison(tailoring_noop_reference)
    ):
        tailoring_outcome = TAILORING_OUTCOME_TAILORED

    # 0. Required output quality: the requested tailored resume must actually
    #    have been produced. Two deterministic outcomes fail this: a draft the
    #    validator rejected and the pipeline recovered from by substituting the
    #    untailored base template, and a patch that applied successfully while
    #    leaving the artifact identical to the run baseline. Both are
    #    required-output failures rather than factual-integrity ones, so they
    #    block no matter how valid the resulting artifact is. Evaluated first so
    #    one of them is reported as the primary reason.
    if tailoring_outcome == TAILORING_OUTCOME_FALLBACK_UNTAILORED:
        blockers.append(
            {
                "code": BLOCK_TAILORING_FALLBACK_UNTAILORED,
                "detail": (
                    "requested tailored resume was not produced; the untailored "
                    "base template was substituted as a recovery fallback"
                ),
            }
        )
    elif tailoring_outcome == TAILORING_OUTCOME_NO_EFFECTIVE_EDITS:
        blockers.append(
            {
                "code": BLOCK_TAILORING_NO_EFFECTIVE_EDITS,
                "detail": (
                    "tailoring completed without any effective resume change; "
                    "requested tailored application was not produced"
                ),
            }
        )
    elif tailoring_outcome != TAILORING_OUTCOME_TAILORED:
        blockers.append(
            {
                "code": BLOCK_TAILORING_OUTCOME_UNKNOWN,
                "detail": (
                    "runtime tailoring outcome was not recorded; whether a valid "
                    "tailored resume was produced cannot be determined"
                ),
            }
        )

    # 1. Required resume artifact (.tex produced by the pipeline, then compiled).
    artifact_ok = (
        resume_artifact_present and resume_artifact_bytes > 0 and bool(latex.strip())
    )
    if not artifact_ok:
        if not resume_artifact_present:
            blockers.append(
                {
                    "code": BLOCK_RESUME_ARTIFACT_MISSING,
                    "detail": "final resume .tex artifact is missing",
                }
            )
        else:
            blockers.append(
                {
                    "code": BLOCK_RESUME_ARTIFACT_EMPTY,
                    "detail": "final resume .tex artifact is empty",
                }
            )
        checks["resume_artifact"] = CHECK_FAIL
    else:
        checks["resume_artifact"] = CHECK_PASS

    # 2. Required compiled PDF.
    if not pdf_present:
        blockers.append(
            {"code": BLOCK_PDF_MISSING, "detail": "compiled resume PDF is missing"}
        )
        checks["pdf"] = CHECK_FAIL
    elif pdf_bytes <= 0:
        blockers.append(
            {"code": BLOCK_PDF_EMPTY, "detail": "compiled resume PDF is empty"}
        )
        checks["pdf"] = CHECK_FAIL
    else:
        checks["pdf"] = CHECK_PASS

    # 3. Factual / integrity validation, recomputed on the final artifact.
    if not master_resume:
        blockers.append(
            {
                "code": BLOCK_INTEGRITY_UNVERIFIABLE,
                "detail": "master resume unavailable; integrity cannot be verified",
            }
        )
        checks["integrity"] = CHECK_FAIL
    else:
        integrity_errors = (
            validate_resume_draft(latex, master_resume) if artifact_ok else []
        )
        if integrity_errors:
            blockers.append(
                {
                    "code": BLOCK_INTEGRITY_FAILED,
                    "detail": "; ".join(integrity_errors[:5]),
                }
            )
            checks["integrity"] = CHECK_FAIL
        else:
            checks["integrity"] = CHECK_PASS

    # 3b. Novel-claim grounding, recomputed on the FINAL artifact. This is the
    #     only check that compares content-bearing additions against
    #     candidate-controlled evidence, so a claim introduced by the tailoring
    #     brief, the reviewer or the grounded ATS edits is caught here even when
    #     it looked acceptable to each earlier stage. The job description is
    #     explicitly NOT evidence: a term the employer asked for does not prove
    #     the candidate did the work, which is what made the Clickboat ATS stage
    #     certify its own inserted claim.
    if artifact_ok and master_resume:
        evidence = build_evidence_corpus(
            master_resume=master_resume,
            canonical_template=canonical_template,
            skills_inventory=skills_inventory,
            career_config=career_config,
            story_bank=story_bank,
        )
        unsupported = find_unsupported_claims(latex, evidence, jd_skill_terms)
        blocking = [item for item in unsupported if item.get("blocking", True)]
        advisory = [item for item in unsupported if not item.get("blocking", True)]
        if blocking:
            blockers.append(
                {
                    "code": BLOCK_UNSUPPORTED_NOVEL_CLAIM,
                    "detail": (
                        "final resume asserts claim(s) absent from candidate "
                        "evidence: " + format_unsupported_claims(blocking)
                    ),
                }
            )
            checks["unsupported_novel_claim"] = CHECK_FAIL
        else:
            checks["unsupported_novel_claim"] = CHECK_PASS
        # Advisory findings mirror the posting's own vocabulary. They are
        # surfaced so the operator can see them, but they never hold a run:
        # mirroring employer wording is what tailoring is for.
        if advisory:
            warnings.append(
                {
                    "code": WARN_JD_ONLY_KEYWORDS,
                    "detail": (
                        "resume mirrors posting wording not found in candidate "
                        "evidence: " + format_unsupported_claims(advisory, limit=3)
                    ),
                }
            )
    else:
        # Same condition as the integrity check above: without the artifact or
        # the master resume there is nothing to ground against.
        checks["unsupported_novel_claim"] = CHECK_SKIPPED

    # 4. Locked-experience drift. Applicable ONLY when the run actually produced
    #    the draft through targeted edits against the canonical template. A run
    #    that fell back to full generation has no template-derived locked blocks
    #    to compare, so this check is NOT_APPLICABLE rather than a false HOLD.
    #    Factual integrity (check 3) and placeholders (check 5) still apply.
    if tailoring_mode == TAILORING_FULL:
        checks["locked_experience"] = NOT_APPLICABLE
    elif tailoring_mode != TAILORING_TARGETED:
        blockers.append(
            {
                "code": BLOCK_TAILORING_MODE_UNKNOWN,
                "detail": (
                    "runtime tailoring mode was not recorded; locked-experience "
                    "applicability cannot be determined"
                ),
            }
        )
        checks["locked_experience"] = CHECK_FAIL
    elif not canonical_template:
        blockers.append(
            {
                "code": BLOCK_LOCKED_EXPERIENCE_UNVERIFIABLE,
                "detail": "canonical template unavailable; locked blocks cannot be verified",
            }
        )
        checks["locked_experience"] = CHECK_FAIL
    else:
        drifted = locked_experience_drift(
            strip_compile_layout_commands(canonical_template), latex
        )
        if drifted:
            blockers.append(
                {
                    "code": BLOCK_LOCKED_EXPERIENCE_DRIFT,
                    "detail": "locked experience changed: " + ", ".join(sorted(drifted)),
                }
            )
            checks["locked_experience"] = CHECK_FAIL
        else:
            checks["locked_experience"] = CHECK_PASS

    # 5. Unresolved template/LLM placeholders.
    placeholders = find_unresolved_placeholders(latex)
    if placeholders:
        blockers.append(
            {
                "code": BLOCK_UNRESOLVED_PLACEHOLDER,
                "detail": "unresolved placeholder(s): " + ", ".join(placeholders),
            }
        )
        checks["placeholders"] = CHECK_FAIL
    else:
        checks["placeholders"] = CHECK_PASS

    # 6. Optional stage: adversarial reviewer. Only a *failure* warns; an
    #    intentional --skip-reviewer is not a defect.
    if reviewer_failed:
        warnings.append(
            {
                "code": WARN_REVIEWER_FAILED,
                "detail": "reviewer stage ran but produced no usable feedback",
            }
        )
        checks["reviewer"] = CHECK_WARN
    elif reviewer_skipped:
        # Intentionally not run: neither a pass nor a warning.
        checks["reviewer"] = CHECK_SKIPPED
    else:
        checks["reviewer"] = CHECK_PASS

    # 7. Optional stage: semantic ATS report.
    if ats_semantic_unavailable:
        warnings.append(
            {
                "code": WARN_ATS_SEMANTIC_UNAVAILABLE,
                "detail": "semantic ATS report unavailable for this run",
            }
        )
        checks["ats_semantic"] = CHECK_WARN
    elif ats_semantic_skipped:
        # Intentionally not run: neither a pass nor a warning.
        checks["ats_semantic"] = CHECK_SKIPPED
    else:
        checks["ats_semantic"] = CHECK_PASS

    # 8. Application questions: no reliable required-signal exists yet.
    checks["application_questions_check"] = questions_check

    if blockers:
        status = HOLD
    elif warnings:
        status = READY_WITH_WARNINGS
    else:
        status = READY_TO_SEND

    return {
        "run_id": run_id,
        "status": status,
        "tailoring_mode": (
            tailoring_mode if tailoring_mode in TAILORING_MODES else TAILORING_UNKNOWN
        ),
        "tailoring_outcome": (
            tailoring_outcome
            if tailoring_outcome in TAILORING_OUTCOMES
            else TAILORING_OUTCOME_UNKNOWN
        ),
        "evaluated_at": evaluated_at
        or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "blockers": blockers,
        "warnings": warnings,
        "checks": checks,
    }


def finalize_optional_stage_warnings(
    result: dict, stage_failures: dict[str, str]
) -> dict:
    """Fold late optional-stage failures into a completed verdict.

    Q&A, cover letter and interview prep run AFTER the required sendability
    evaluation, so their outcomes cannot influence it. This merges only their
    *requested-and-failed* outcomes into the persisted report and never weakens
    it:

    * ``HOLD`` is returned untouched (never created, never cleared);
    * ``READY_TO_SEND`` becomes ``READY_WITH_WARNINGS`` only when a requested
      optional stage actually failed;
    * ``READY_WITH_WARNINGS`` is retained and new warnings merged;
    * warnings are deduplicated by code, in a deterministic order;
    * intentional skips are never passed in and produce nothing.

    No LLM call, no re-evaluation of required checks, no lifecycle effect.
    """
    if not stage_failures or result.get("status") not in (
        READY_TO_SEND,
        READY_WITH_WARNINGS,
    ):
        return result

    updated = dict(result)
    warnings = list(result.get("warnings", []))
    checks = dict(result.get("checks", {}))
    seen = {w.get("code") for w in warnings}

    for code in sorted(stage_failures):
        if code in seen:
            continue
        seen.add(code)
        warnings.append({"code": code, "detail": stage_failures[code]})
        checks[code] = CHECK_WARN

    if len(warnings) == len(result.get("warnings", [])):
        return result

    updated["warnings"] = warnings
    updated["checks"] = checks
    updated["status"] = READY_WITH_WARNINGS
    return updated


def write_sendability_report(run_dir: str | os.PathLike[str], result: dict) -> Path:
    """Write ``sendability_report.json`` atomically inside ``run_dir``."""
    directory = Path(run_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / REPORT_FILENAME
    tmp = directory / (REPORT_FILENAME + ".tmp")
    tmp.write_text(json.dumps(result, indent=2) + "\n")
    os.replace(tmp, path)
    return path
