"""CLI orchestrator: read colcon logs from a directory, run all parsers,
emit the four-section build-health report + CSV.

Usage:
    python3 -m ci.run --logs-dir data/logs_broken --out-dir sample_output \\
        [--dockerfile Dockerfile] [--workspace-src workspace/src] \\
        [--build-log-run2 data/logs_broken/build_log_run2.txt] \\
        [--scenario-name "broken build"]

Pure stdlib. No network calls.
"""

import argparse
import os
import sys

# Allow running as `python3 ci/run.py` (script) as well as `python3 -m ci.run`
# (module) by making sure the repo root is on sys.path either way.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_THIS_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from ci.parse_build import parse_build_log
from ci.parse_test import parse_test_log
from ci.reproducibility import collect_signals
from ci.report import build_findings, write_report


def run(
    logs_dir,
    out_dir,
    dockerfile_path=None,
    workspace_src_dir=None,
    build_log_run2_path=None,
    scenario_name=None,
):
    build_log_path = os.path.join(logs_dir, "build_log.txt")
    test_log_path = os.path.join(logs_dir, "test_log.txt")

    build_result = parse_build_log(build_log_path)
    test_result = parse_test_log(test_log_path)

    build_result_run2 = None
    if build_log_run2_path and os.path.isfile(build_log_run2_path):
        build_result_run2 = parse_build_log(build_log_run2_path)

    repro_signals = collect_signals(
        dockerfile_path=dockerfile_path,
        workspace_src_dir=workspace_src_dir,
        build_result_run1=build_result,
        build_result_run2=build_result_run2,
    )

    scenario_name = scenario_name or os.path.basename(os.path.normpath(logs_dir))
    findings = build_findings(scenario_name, build_result, test_result, repro_signals)
    report_path, csv_path, report_text, report_md5 = write_report(
        scenario_name, findings, build_result, test_result, repro_signals, out_dir
    )

    return {
        "scenario_name": scenario_name,
        "build_result": build_result,
        "test_result": test_result,
        "repro_signals": repro_signals,
        "findings": findings,
        "report_path": report_path,
        "csv_path": csv_path,
        "report_text": report_text,
        "report_md5": report_md5,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs-dir", required=True, help="Directory containing build_log.txt and test_log.txt")
    parser.add_argument("--out-dir", required=True, help="Directory to write build_health_report.md and findings.csv into")
    parser.add_argument("--dockerfile", default=None, help="Path to Dockerfile for reproducibility pin check")
    parser.add_argument("--workspace-src", default=None, help="Path to workspace/src for dependency-manifest check")
    parser.add_argument("--build-log-run2", default=None, help="Optional second build log for package-set comparison")
    parser.add_argument("--scenario-name", default=None, help="Human-readable scenario label for the report")
    args = parser.parse_args(argv)

    result = run(
        args.logs_dir,
        args.out_dir,
        dockerfile_path=args.dockerfile,
        workspace_src_dir=args.workspace_src,
        build_log_run2_path=args.build_log_run2,
        scenario_name=args.scenario_name,
    )
    print("Wrote %s" % result["report_path"])
    print("Wrote %s" % result["csv_path"])
    print("Report md5: %s" % result["report_md5"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
