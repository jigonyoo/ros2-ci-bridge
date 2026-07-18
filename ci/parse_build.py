"""Parse `colcon build` console log text into a structured dict.

Only recognizes the line formats documented in SCHEMA.md. Anything else is
ignored on purpose -- an unrecognized line is not evidence of anything.
"""

import re

from ci.util import read_lines

RE_START = re.compile(r"^Starting >>> (\S+)\s*$")
RE_FINISHED = re.compile(r"^Finished <<< (\S+) \[([\d.]+)s\]\s*$")
RE_FAILED = re.compile(
    r"^Failed\s+<<< (\S+) \[([\d.]+)s, exited with code (-?\d+)\]\s*$"
)
RE_STDERR_START = re.compile(r"^--- stderr: (\S+)\s*$")
RE_STDERR_END = re.compile(r"^---\s*$")
RE_CMAKE_MISSING_DEP = re.compile(
    r'Could not find a package configuration file provided by "([^"]+)"'
)
RE_ROSDEP_MISSING = re.compile(
    r"the following rosdep keys could not be resolved for package '([^']+)':\s*\[([^\]]*)\]"
)
RE_NONDETERMINISTIC_TS = re.compile(
    r"WARNING: non-reproducible timestamp detected in (\S+) build artifact"
)
RE_SUMMARY = re.compile(
    r"^Summary: (\d+) packages? finished \[([\d.]+)s\]\s*$"
)


def parse_build_log(path):
    """Parse a colcon build log file at `path`.

    Returns a dict:
      {
        "packages_discovered": [pkg, ...]   # in the order first seen
        "packages_built_ok":   [pkg, ...]
        "packages_failed":     [pkg, ...]
        "build_times":         {pkg: seconds}
        "exit_codes":          {pkg: code}       # failed packages only
        "warning_counts":      {pkg: n}          # lines containing "Warning" inside a stderr block
        "missing_deps":        [{"package": pkg, "dependency": dep, "source": "cmake"|"rosdep"}]
        "nondeterministic_timestamp_warnings": [pkg, ...]
        "summary_total_packages": int or None
        "summary_total_seconds": float or None
        "raw_line_count": int
      }
  """
    lines = read_lines(path)

    packages_discovered = []
    packages_built_ok = []
    packages_failed = []
    build_times = {}
    exit_codes = {}
    warning_counts = {}
    missing_deps = []
    nondet_ts_warnings = []
    summary_total_packages = None
    summary_total_seconds = None

    in_stderr_block = None  # package name, or None

    for line in lines:
        m = RE_START.match(line)
        if m:
            pkg = m.group(1)
            if pkg not in packages_discovered:
                packages_discovered.append(pkg)
            continue

        m = RE_STDERR_START.match(line)
        if m:
            in_stderr_block = m.group(1)
            warning_counts.setdefault(in_stderr_block, 0)
            continue

        if in_stderr_block is not None and RE_STDERR_END.match(line):
            in_stderr_block = None
            continue

        if in_stderr_block is not None and "Warning" in line:
            warning_counts[in_stderr_block] = warning_counts.get(in_stderr_block, 0) + 1

        m = RE_CMAKE_MISSING_DEP.search(line)
        if m:
            pkg = in_stderr_block or ""
            missing_deps.append(
                {"package": pkg, "dependency": m.group(1), "source": "cmake"}
            )
            continue

        m = RE_ROSDEP_MISSING.search(line)
        if m:
            pkg = m.group(1)
            deps_raw = m.group(2)
            deps = [d.strip().strip("'\"") for d in deps_raw.split(",") if d.strip()]
            for dep in deps:
                missing_deps.append(
                    {"package": pkg, "dependency": dep, "source": "rosdep"}
                )
            continue

        m = RE_NONDETERMINISTIC_TS.search(line)
        if m:
            nondet_ts_warnings.append(m.group(1))
            continue

        m = RE_FINISHED.match(line)
        if m:
            pkg, seconds = m.group(1), float(m.group(2))
            packages_built_ok.append(pkg)
            build_times[pkg] = seconds
            continue

        m = RE_FAILED.match(line)
        if m:
            pkg, seconds, code = m.group(1), float(m.group(2)), int(m.group(3))
            packages_failed.append(pkg)
            build_times[pkg] = seconds
            exit_codes[pkg] = code
            continue

        m = RE_SUMMARY.match(line)
        if m:
            summary_total_packages = int(m.group(1))
            summary_total_seconds = float(m.group(2))
            continue

    return {
        "packages_discovered": packages_discovered,
        "packages_built_ok": packages_built_ok,
        "packages_failed": packages_failed,
        "build_times": build_times,
        "exit_codes": exit_codes,
        "warning_counts": {k: v for k, v in warning_counts.items() if v > 0},
        "missing_deps": missing_deps,
        "nondeterministic_timestamp_warnings": nondet_ts_warnings,
        "summary_total_packages": summary_total_packages,
        "summary_total_seconds": summary_total_seconds,
        "raw_line_count": len(lines),
    }
