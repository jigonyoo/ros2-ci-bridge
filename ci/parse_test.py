"""Parse `colcon test` / `colcon test-result --all` style log text.

See SCHEMA.md section 2 for the exact line formats matched here.
"""

import re

from ci.util import read_lines

RE_PKG_HEADER = re.compile(r"^--- (\S+)(?: \(attempt (\d+)\))? ---\s*$")
RE_SUMMARY = re.compile(
    r"^Summary: (\d+) tests?, (\d+) errors?, (\d+) failures?, (\d+) skipped\s*$"
)
RE_FAILURE = re.compile(r"^FAILURE: (\S+)\.(\S+) \((.*)\)\s*$")
RE_ERROR = re.compile(r"^ERROR: (\S+)\.(\S+) \((.*)\)\s*$")


def parse_test_log(path):
    """Parse a colcon test log file at `path`.

    Returns a dict:
      {
        "packages": {
            pkg: {
                "attempts": {
                    attempt_no: {
                        "total": int, "errors": int, "failures": int, "skipped": int,
                        "failed_tests": [(test_name, reason), ...],
                        "errored_tests": [(test_name, reason), ...],
                    },
                    ...
                }
            },
            ...
        },
        "totals": {"tests": int, "errors": int, "failures": int, "skipped": int},
        "candidate_flaky_tests": [
            {"package": pkg, "test": name, "failed_attempt": n, "later_passing_attempt": m}
        ],
        "raw_line_count": int,
      }
    """
    lines = read_lines(path)

    packages = {}
    current_pkg = None
    current_attempt = 1

    for line in lines:
        m = RE_PKG_HEADER.match(line)
        if m:
            current_pkg = m.group(1)
            current_attempt = int(m.group(2)) if m.group(2) else 1
            packages.setdefault(current_pkg, {"attempts": {}})
            packages[current_pkg]["attempts"].setdefault(
                current_attempt,
                {
                    "total": 0,
                    "errors": 0,
                    "failures": 0,
                    "skipped": 0,
                    "failed_tests": [],
                    "errored_tests": [],
                },
            )
            continue

        if current_pkg is None:
            continue

        m = RE_SUMMARY.match(line)
        if m:
            attempt = packages[current_pkg]["attempts"][current_attempt]
            attempt["total"] = int(m.group(1))
            attempt["errors"] = int(m.group(2))
            attempt["failures"] = int(m.group(3))
            attempt["skipped"] = int(m.group(4))
            continue

        m = RE_FAILURE.match(line)
        if m:
            pkg_in_line, test_name, reason = m.group(1), m.group(2), m.group(3)
            attempt = packages[current_pkg]["attempts"][current_attempt]
            attempt["failed_tests"].append((test_name, reason))
            continue

        m = RE_ERROR.match(line)
        if m:
            pkg_in_line, test_name, reason = m.group(1), m.group(2), m.group(3)
            attempt = packages[current_pkg]["attempts"][current_attempt]
            attempt["errored_tests"].append((test_name, reason))
            continue

    # Totals: use the highest-numbered attempt per package (the latest
    # observed result), not a sum across attempts -- summing would
    # double-count retried tests.
    totals = {"tests": 0, "errors": 0, "failures": 0, "skipped": 0}
    for pkg, data in packages.items():
        attempts = data["attempts"]
        if not attempts:
            continue
        last_attempt_no = max(attempts.keys())
        last = attempts[last_attempt_no]
        totals["tests"] += last["total"]
        totals["errors"] += last["errors"]
        totals["failures"] += last["failures"]
        totals["skipped"] += last["skipped"]

    # Candidate flaky tests: a test that FAILED (or ERRORed) in an earlier
    # attempt and does not appear in the failed/errored list of a later
    # attempt for the same package. This requires at least 2 attempts to
    # be present in the log -- with only one attempt, nothing here is
    # ever flagged as flaky (correctly: one data point cannot show
    # flakiness).
    candidate_flaky = []
    for pkg, data in packages.items():
        attempts = data["attempts"]
        attempt_numbers = sorted(attempts.keys())
        if len(attempt_numbers) < 2:
            continue
        for i in range(len(attempt_numbers) - 1):
            earlier_no = attempt_numbers[i]
            later_no = attempt_numbers[i + 1]
            earlier = attempts[earlier_no]
            later = attempts[later_no]
            earlier_bad = {name for name, _ in earlier["failed_tests"]} | {
                name for name, _ in earlier["errored_tests"]
            }
            later_bad = {name for name, _ in later["failed_tests"]} | {
                name for name, _ in later["errored_tests"]
            }
            for test_name in sorted(earlier_bad - later_bad):
                candidate_flaky.append(
                    {
                        "package": pkg,
                        "test": test_name,
                        "failed_attempt": earlier_no,
                        "later_passing_attempt": later_no,
                    }
                )

    return {
        "packages": packages,
        "totals": totals,
        "candidate_flaky_tests": candidate_flaky,
        "raw_line_count": len(lines),
    }
