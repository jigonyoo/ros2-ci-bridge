"""Deterministically generate synthetic colcon build/test logs for two
scenarios, matching the exact line formats documented in SCHEMA.md.

No randomness. Running this twice produces byte-identical output files.
The package names (nav_bridge_core, sensor_fusion_utils,
diagnostics_reporter) mirror the package.xml stubs under
workspace/src/ so the demo reads as one coherent workspace, even though
the heavy ROS2 build itself only actually runs in CI (see README.md).

Usage:
    python3 data/generate_logs.py [--out-dir data]
"""

import argparse
import os

PACKAGES = ["nav_bridge_core", "sensor_fusion_utils", "diagnostics_reporter"]


def _green_build_log():
    return "\n".join(
        [
            "Starting >>> nav_bridge_core",
            "Starting >>> sensor_fusion_utils",
            "Starting >>> diagnostics_reporter",
            "Finished <<< nav_bridge_core [8.10s]",
            "Finished <<< sensor_fusion_utils [11.40s]",
            "Finished <<< diagnostics_reporter [4.20s]",
            "Summary: 3 packages finished [11.9s]",
            "",
        ]
    )


def _green_test_log():
    return "\n".join(
        [
            "--- nav_bridge_core ---",
            "Summary: 6 tests, 0 errors, 0 failures, 0 skipped",
            "--- sensor_fusion_utils ---",
            "Summary: 9 tests, 0 errors, 0 failures, 0 skipped",
            "--- diagnostics_reporter ---",
            "Summary: 4 tests, 0 errors, 0 failures, 0 skipped",
            "",
        ]
    )


def _broken_build_log():
    return "\n".join(
        [
            "Starting >>> nav_bridge_core",
            "Starting >>> sensor_fusion_utils",
            "Starting >>> diagnostics_reporter",
            "--- stderr: nav_bridge_core",
            "CMake Warning at CMakeLists.txt:42 (message):",
            "  Deprecated API tf::TransformListener used; migrate to tf2 before",
            "  the next distro upgrade.",
            "---",
            "WARNING: non-reproducible timestamp detected in nav_bridge_core build "
            "artifact (mtime varies between runs)",
            "Finished <<< nav_bridge_core [8.30s]",
            "--- stderr: sensor_fusion_utils",
            "CMake Error at CMakeLists.txt:17 (find_package):",
            '  Could not find a package configuration file provided by "custom_msgs"',
            "---",
            "ERROR: the following rosdep keys could not be resolved for package "
            "'sensor_fusion_utils': ['libpcl-fusion-dev']",
            "Failed   <<< sensor_fusion_utils [3.10s, exited with code 2]",
            "Finished <<< diagnostics_reporter [4.50s]",
            "Summary: 2 packages finished [8.5s]",
            "  1 package failed: sensor_fusion_utils",
            "  1 package had stderr output: nav_bridge_core, sensor_fusion_utils",
            "",
        ]
    )


def _broken_test_log():
    return "\n".join(
        [
            "--- nav_bridge_core ---",
            "Summary: 6 tests, 0 errors, 0 failures, 0 skipped",
            "--- sensor_fusion_utils ---",
            "Summary: 0 tests, 1 errors, 0 failures, 0 skipped",
            "ERROR: sensor_fusion_utils.build_precondition (package failed to build; "
            "tests were not run)",
            "--- diagnostics_reporter (attempt 1) ---",
            "Summary: 4 tests, 0 errors, 1 failures, 0 skipped",
            "FAILURE: diagnostics_reporter.test_reporting_latency (assertion failed: "
            "elapsed 0.021s > 0.020s threshold)",
            "--- diagnostics_reporter (attempt 2) ---",
            "Summary: 4 tests, 0 errors, 0 failures, 0 skipped",
            "",
        ]
    )


def write_scenario(out_dir, name, build_log_text, test_log_text, build_log_run2_text=None):
    scenario_dir = os.path.join(out_dir, "logs_%s" % name)
    os.makedirs(scenario_dir, exist_ok=True)
    with open(os.path.join(scenario_dir, "build_log.txt"), "w", encoding="utf-8") as fh:
        fh.write(build_log_text)
    with open(os.path.join(scenario_dir, "test_log.txt"), "w", encoding="utf-8") as fh:
        fh.write(test_log_text)
    if build_log_run2_text is not None:
        with open(os.path.join(scenario_dir, "build_log_run2.txt"), "w", encoding="utf-8") as fh:
            fh.write(build_log_run2_text)
    return scenario_dir


def generate(out_dir):
    green_build = _green_build_log()
    # run2 of the green scenario is identical on purpose: it demonstrates
    # the "same package set across two runs" reproducibility signal for a
    # healthy build. Deterministic -- not randomly generated.
    green_dir = write_scenario(
        out_dir, "green", green_build, _green_test_log(), build_log_run2_text=green_build
    )
    broken_dir = write_scenario(
        out_dir, "broken", _broken_build_log(), _broken_test_log()
    )
    return {"green": green_dir, "broken": broken_dir}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    default_out = os.path.dirname(os.path.abspath(__file__))
    parser.add_argument("--out-dir", default=default_out)
    args = parser.parse_args(argv)
    result = generate(args.out_dir)
    for scenario, path in result.items():
        print("Wrote %s scenario logs to %s" % (scenario, path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
