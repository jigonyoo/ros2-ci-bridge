"""Run the offline analysis layer over both synthetic scenarios and write
sample_output/.

This is the "verify the analysis layer offline" half of the honesty split
described in README.md: it never invokes Docker, ROS2, or colcon. It
regenerates the synthetic logs deterministically (data/generate_logs.py),
runs ci/ over them, and writes:

    sample_output/build_health_report.md   (broken scenario -- illustrative)
    sample_output/findings.csv             (broken scenario)
    sample_output/run_summary.txt          (both scenarios, for contrast)
    sample_output/repro_steps.txt          (how to reproduce this + how CI runs for real)

Running this script twice produces byte-identical output files (see
tests/test_ci_bridge.py's determinism test).
"""

import os
import sys
import tempfile

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from data.generate_logs import generate as generate_logs
from ci.run import run as run_analysis

DOCKERFILE_PATH = os.path.join(_REPO_ROOT, "Dockerfile")
WORKSPACE_SRC_DIR = os.path.join(_REPO_ROOT, "workspace", "src")
DATA_DIR = os.path.join(_REPO_ROOT, "data")
SAMPLE_OUTPUT_DIR = os.path.join(_REPO_ROOT, "sample_output")

REPRO_STEPS = """\
How to reproduce this sample_output/ directory
================================================

Offline analysis-layer demo (what this repo actually verifies here):

    cd ros2-ci-bridge
    python3 run_demo.py

This regenerates data/logs_green/ and data/logs_broken/ deterministically
(data/generate_logs.py, no randomness) and runs the ci/ analysis layer
over both, writing this directory. Running it twice produces
byte-identical files -- see tests/test_ci_bridge.py's md5 determinism
test.

Unit tests:

    python3 -m unittest discover -s tests -v

Docker Compose (same offline analysis, in a container with no network):

    docker compose run --rm analyze

The real, heavy ROS2 build (NOT run by this demo or by the unit tests):

    docker build -t ros2-ci-bridge-build -f Dockerfile .

...which is exactly what .github/workflows/ci.yml runs on every push --
a real colcon build + colcon test inside ros:humble-ros-base, with the
resulting logs fed back into this same ci/ analysis layer and uploaded
as a workflow artifact. See README.md "How to run" and "Limitations".
"""


def _write_text(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def main():
    generate_logs(DATA_DIR)

    # Ensure the output dir exists. We intentionally do NOT rmtree it: every
    # file written below uses open(..., "w"), so overwriting is sufficient,
    # and avoiding unlink keeps run_demo working on filesystems that permit
    # writes but block deletion (e.g. some read-through network mounts).
    os.makedirs(SAMPLE_OUTPUT_DIR, exist_ok=True)

    green_dir = os.path.join(DATA_DIR, "logs_green")
    broken_dir = os.path.join(DATA_DIR, "logs_broken")

    # Green scenario: analyzed for the run_summary.txt contrast, but its
    # full report/CSV are not shipped in sample_output/ (the broken
    # scenario is the illustrative one per the brief) -- write it to a
    # throwaway temp dir instead of littering the repo.
    with tempfile.TemporaryDirectory() as tmp_out:
        green_result = run_analysis(
            green_dir,
            tmp_out,
            dockerfile_path=DOCKERFILE_PATH,
            workspace_src_dir=WORKSPACE_SRC_DIR,
            build_log_run2_path=os.path.join(green_dir, "build_log_run2.txt"),
            scenario_name="clean green build",
        )

    broken_result = run_analysis(
        broken_dir,
        SAMPLE_OUTPUT_DIR,
        dockerfile_path=DOCKERFILE_PATH,
        workspace_src_dir=WORKSPACE_SRC_DIR,
        build_log_run2_path=None,
        scenario_name="broken build (missing dependency + candidate-flaky test + timestamp warning)",
    )

    summary_lines = []
    summary_lines.append("ROS2 CI & Build-Health Bridge -- run_demo.py summary")
    summary_lines.append("=" * 56)
    summary_lines.append("")
    for label, result in (("green", green_result), ("broken", broken_result)):
        br = result["build_result"]
        tr = result["test_result"]
        summary_lines.append("Scenario: %s (%s)" % (label, result["scenario_name"]))
        summary_lines.append(
            "  packages discovered: %d, built ok: %d, failed: %d"
            % (
                len(br["packages_discovered"]),
                len(br["packages_built_ok"]),
                len(br["packages_failed"]),
            )
        )
        if br["packages_failed"]:
            summary_lines.append("  failed packages: %s" % ", ".join(br["packages_failed"]))
        summary_lines.append(
            "  tests: %d total, %d errors, %d failures, %d skipped"
            % (
                tr["totals"]["tests"],
                tr["totals"]["errors"],
                tr["totals"]["failures"],
                tr["totals"]["skipped"],
            )
        )
        summary_lines.append(
            "  candidate flaky tests: %d" % len(tr["candidate_flaky_tests"])
        )
        summary_lines.append("  findings emitted: %d" % len(result["findings"]))
        summary_lines.append("  report md5: %s" % result["report_md5"])
        summary_lines.append("")

    summary_lines.append(
        "Only the 'broken' scenario's full report and findings.csv are shipped "
        "in this sample_output/ directory (it is the illustrative one). The "
        "'green' scenario above is included in this summary for contrast: it "
        "shows the same analysis layer producing an almost-empty Likely/"
        "Unverified/Additional-data-required set when the underlying logs "
        "don't contain anything to hedge about."
    )
    summary_lines.append("")

    _write_text(os.path.join(SAMPLE_OUTPUT_DIR, "run_summary.txt"), "\n".join(summary_lines))
    _write_text(os.path.join(SAMPLE_OUTPUT_DIR, "repro_steps.txt"), REPRO_STEPS)

    print("Wrote sample_output/ (broken-scenario report md5: %s)" % broken_result["report_md5"])
    for name in sorted(os.listdir(SAMPLE_OUTPUT_DIR)):
        print("  sample_output/%s" % name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
