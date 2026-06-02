"""
sanitize.py — Keep student data away from the API. Full stop.
=============================================================

This module exists on its own, in isolation, on purpose: it's the single most
important piece of the updater from a trust standpoint, so it should be small
enough to read in one sitting and audit without wading through unrelated logic.

The contract: give `sanitize_bulletin_text()` the raw text of a bulletin, and it
returns text that is safe to send to the API — with the student roster and the
trailing form-link junk removed. It also returns a short, PII-free report of
WHAT it removed, so the updater can show you ("removed 14 lines from the
'Differentiated Assistance' section onward") without ever echoing a single name.

Two layers of defense, intentionally redundant:
  1. The CUT — find the first "stop marker" and delete from there to the end.
     In every bulletin we've seen, the student names and the form links all sit
     together at the tail, so one clean cut removes the whole sensitive region.
  2. The SCRUB — even above the cut, drop any individual line that pattern-
     matches a roster entry. This catches the case where someone reorders the
     bulletin and a roster ends up higher in the document.

And then, outside this module, there's a third layer you control: the updater
prints exactly what survived and waits for you to type "yes". Three layers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import config


@dataclass
class SanitizeReport:
    """A PII-free summary of what the sanitizer did. Safe to print/log."""

    cut_marker: str | None = None          # which stop marker triggered the cut
    lines_cut: int = 0                      # how many lines the cut removed
    lines_scrubbed: int = 0                 # how many extra lines the scrub removed
    scrubbed_reasons: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """One-line, name-free description for humans."""
        parts: list[str] = []
        if self.cut_marker:
            parts.append(
                f'cut {self.lines_cut} line(s) from "{self.cut_marker}" to end'
            )
        if self.lines_scrubbed:
            parts.append(f"scrubbed {self.lines_scrubbed} roster-like line(s)")
        if not parts:
            return "no student-data sections detected (nothing removed)"
        return "; ".join(parts)


def _compile(patterns: list[str]) -> list[re.Pattern[str]]:
    """Pre-compile the configured regexes once. IGNORECASE throughout."""
    return [re.compile(p, re.IGNORECASE) for p in patterns]


def sanitize_bulletin_text(raw_text: str) -> tuple[str, SanitizeReport]:
    """
    Return (safe_text, report).

    `safe_text` is what may be sent to the API. `report` describes what was
    removed without containing any of the removed content.
    """
    report = SanitizeReport()
    lines = raw_text.splitlines()

    # --- Layer 1: the CUT -------------------------------------------------
    # Find the EARLIEST line that contains any stop marker, and drop from there.
    # We search case-insensitively and take the minimum index so that whichever
    # sensitive section appears first wins.
    markers = [(m, m.lower()) for m in config.SANITIZE_STOP_MARKERS]
    cut_index: int | None = None
    cut_marker: str | None = None

    for i, line in enumerate(lines):
        low = line.lower()
        for original, needle in markers:
            if needle in low:
                # Found a marker on this line. Is it the earliest so far?
                if cut_index is None or i < cut_index:
                    cut_index = i
                    cut_marker = original
                break  # no need to check other markers on this same line

    if cut_index is not None:
        report.cut_marker = cut_marker
        report.lines_cut = len(lines) - cut_index
        lines = lines[:cut_index]

    # --- Layer 2: the SCRUB ----------------------------------------------
    # Walk what's left and drop any line that looks like a roster entry.
    line_patterns = _compile(config.SANITIZE_LINE_PATTERNS)
    kept: list[str] = []
    for line in lines:
        matched = next((p for p in line_patterns if p.search(line)), None)
        if matched is None:
            kept.append(line)
            continue
        report.lines_scrubbed += 1
        # Record the PATTERN that matched, never the line itself.
        report.scrubbed_reasons.append(matched.pattern)

    safe_text = "\n".join(kept).strip()
    return safe_text, report


def looks_clean(safe_text: str) -> list[str]:
    """
    A final paranoid pass for the confirmation screen. Returns a list of
    human-readable WARNINGS if anything in the supposedly-clean text still
    smells like a roster, so the updater can flag it in red before you approve.

    This does NOT block anything — it just sharpens your eyes at the gate.
    """
    warnings: list[str] = []
    patterns = _compile(config.SANITIZE_LINE_PATTERNS)
    for i, line in enumerate(safe_text.splitlines(), start=1):
        if any(p.search(line) for p in patterns):
            warnings.append(f"line {i} still matches a roster pattern")
    return warnings
