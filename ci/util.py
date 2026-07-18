"""Small shared helpers used across the ci/ package. Stdlib only."""

import csv
import hashlib
import os

SECTION_CONFIRMED = "confirmed"
SECTION_LIKELY = "likely"
SECTION_UNVERIFIED = "unverified"
SECTION_ADDITIONAL_DATA = "additional_data_required"

SECTION_ORDER = [
    SECTION_CONFIRMED,
    SECTION_LIKELY,
    SECTION_UNVERIFIED,
    SECTION_ADDITIONAL_DATA,
]

SECTION_TITLES = {
    SECTION_CONFIRMED: "Confirmed evidence",
    SECTION_LIKELY: "Likely causes",
    SECTION_UNVERIFIED: "Unverified hypotheses",
    SECTION_ADDITIONAL_DATA: "Additional data required",
}


def read_lines(path):
    """Read a text file and return a list of lines with trailing
    newlines stripped. Returns an empty list if the file does not exist,
    so callers can treat "log not supplied" as "no evidence" rather than
    crashing."""
    if not path or not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        return [line.rstrip("\n") for line in fh]


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def write_csv(path, rows, fieldnames):
    """Write rows (list of dicts) to path as CSV, deterministically
    (dict iteration order follows fieldnames, not insertion order)."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def md5_of_text(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def md5_of_file(path):
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


class Finding:
    """One line item in the four-section report.

    section:  one of SECTION_ORDER
    category: short machine-friendly tag, e.g. "build-failure", "missing-dependency"
    package:  package name the finding is about, or "" for workspace-wide findings
    summary:  one hedged, human-readable sentence (must not assert an
              unverified fact as certain outside the "confirmed" section)
    evidence: the concrete log line(s)/counts that back the summary
    """

    __slots__ = ("section", "category", "package", "summary", "evidence")

    def __init__(self, section, category, package, summary, evidence):
        assert section in SECTION_ORDER, "unknown section: %r" % (section,)
        self.section = section
        self.category = category
        self.package = package
        self.summary = summary
        self.evidence = evidence

    def as_row(self):
        return {
            "section": self.section,
            "category": self.category,
            "package": self.package,
            "summary": self.summary,
            "evidence": self.evidence,
        }
