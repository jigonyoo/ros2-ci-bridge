# ROS2 CI & Build-Health Report

Scenario: **broken build (missing dependency + candidate-flaky test + timestamp warning)**

This report was generated entirely offline by the analysis layer in `ci/` from the build/test logs listed below. It is a data/CI verification artifact, not a robotics-runtime diagnosis -- see README.md's Limitations section.

## Confirmed evidence

Facts read directly from the build/test logs. No interpretation.

- **build-summary** -- colcon build discovered 3 package(s): nav_bridge_core, sensor_fusion_utils, diagnostics_reporter.
  - Evidence: packages_discovered=['nav_bridge_core', 'sensor_fusion_utils', 'diagnostics_reporter'] (parsed from 'Starting >>> <pkg>' lines)
- **build-summary** -- 2 package(s) finished the build successfully: nav_bridge_core, diagnostics_reporter.
  - Evidence: packages_built_ok=['nav_bridge_core', 'diagnostics_reporter'] (parsed from 'Finished <<<' lines)
- **build-failure `[sensor_fusion_utils]`** -- 1 package(s) failed the build: sensor_fusion_utils.
  - Evidence: packages_failed=['sensor_fusion_utils'], exit_codes={'sensor_fusion_utils': 2} (parsed from 'Failed <<<' lines)
- **build-warning `[nav_bridge_core]`** -- nav_bridge_core produced 1 line(s) matching 'Warning' in its stderr block.
  - Evidence: warning_counts['nav_bridge_core']=1
- **missing-dependency-reference `[sensor_fusion_utils]`** -- Build log contains a missing-dependency reference for 'custom_msgs' (source: cmake) attributed to package sensor_fusion_utils.
  - Evidence: missing_deps entry={'package': 'sensor_fusion_utils', 'dependency': 'custom_msgs', 'source': 'cmake'}
- **missing-dependency-reference `[sensor_fusion_utils]`** -- Build log contains a missing-dependency reference for 'libpcl-fusion-dev' (source: rosdep) attributed to package sensor_fusion_utils.
  - Evidence: missing_deps entry={'package': 'sensor_fusion_utils', 'dependency': 'libpcl-fusion-dev', 'source': 'rosdep'}
- **test-summary** -- Test results (latest attempt per package): 10 test(s), 1 error(s), 0 failure(s), 0 skipped.
  - Evidence: totals={'tests': 10, 'errors': 1, 'failures': 0, 'skipped': 0}
- **nondeterministic-timestamp-warning `[nav_bridge_core]`** -- Build log contains 1 non-reproducible-timestamp warning line(s), for package(s): nav_bridge_core.
  - Evidence: nondeterministic_timestamp_warning_count=1
- **dockerfile-pin** -- Dockerfile base-image pin status: tag-pinned (image ref: ros:humble-ros-base).
  - Evidence: check_dockerfile_pin() -> ('tag-pinned', 'ros:humble-ros-base')

## Likely causes

Reasoned hypotheses. Each item is explicitly hedged, lists its supporting evidence, and states what additional data would confirm or rule it out.

- **likely-missing-dependency `[sensor_fusion_utils]`** -- sensor_fusion_utils's build failure is likely related to unresolved dependency reference(s) (custom_msgs, libpcl-fusion-dev) logged for the same package, but this is not confirmed as the sole or exact cause.
  - Evidence: sensor_fusion_utils failed with exit code 2; missing-dependency lines for sensor_fusion_utils: custom_msgs, libpcl-fusion-dev. Would be confirmed by: re-running the build after installing custom_msgs, libpcl-fusion-dev and observing sensor_fusion_utils transition from Failed to Finished with no other changes.
- **likely-reproducibility-gap** -- The base image is tag-pinned rather than digest-pinned, which is likely to allow the build environment to drift between runs -- though whether it actually has drifted is not verified here.
  - Evidence: check_dockerfile_pin() returned 'tag-pinned' for image ref 'ros:humble-ros-base'. Would be confirmed by: pulling the tag on two different dates and diffing the resulting image digests.

## Unverified hypotheses

Signals that are consistent with a problem but are not confirmed with the data on hand.

- **candidate-flaky-test `[diagnostics_reporter]`** -- diagnostics_reporter.test_reporting_latency failed in attempt 1 and did not fail in attempt 2 for the same package -- this pattern is consistent with a flaky (intermittently failing) test, but two attempts is not enough to confirm flakiness versus a one-off environmental fluke.
  - Evidence: candidate_flaky_tests entry={'package': 'diagnostics_reporter', 'test': 'test_reporting_latency', 'failed_attempt': 1, 'later_passing_attempt': 2}
- **unverified-reproducibility-impact `[nav_bridge_core]`** -- The non-reproducible-timestamp warning(s) logged above are consistent with build artifacts that would differ byte-for-byte across runs, but this demo does not diff actual artifact checksums, so the impact on reproducibility is unverified.
  - Evidence: 1 timestamp-warning line(s) parsed from the build log. No artifact checksum comparison was performed.

## Additional data required

Concrete, specific requests for logs/data that would move an item above toward Confirmed or ruled-out.

- **ask-rebuild-after-dependency-fix `[sensor_fusion_utils]`** -- Provide a rebuild log for sensor_fusion_utils captured after installing/resolving dependency(ies) custom_msgs, libpcl-fusion-dev, so the likely-cause hypothesis above can be confirmed or ruled out.
  - Evidence: Would move finding 'likely-missing-dependency' (package=sensor_fusion_utils) from Likely to Confirmed or ruled-out.
- **ask-repeated-test-runs `[diagnostics_reporter]`** -- Run diagnostics_reporter.test_reporting_latency at least 5 additional independent times (ideally on different CI runners/days) and provide the pass/fail log for each run to confirm or rule out flakiness.
  - Evidence: Would move finding 'candidate-flaky-test' (package=diagnostics_reporter, test=test_reporting_latency) from Unverified to Confirmed-flaky or Confirmed-one-off.
- **ask-digest-pin** -- Pin the Dockerfile FROM line to a specific @sha256 digest and provide a build log from the pinned image to establish a stable baseline for future reproducibility comparisons.
  - Evidence: Would upgrade the 'likely-reproducibility-gap' finding from Likely to either Confirmed-stable or a specific new failure mode.
- **ask-second-build-run** -- Provide a second independent build log (same commit, same Dockerfile) so the discovered package set can be compared across runs. Only one run is available in this scenario, so package-set reproducibility could not be evaluated at all.
  - Evidence: Would populate the 'package-set-comparison' confirmed finding and enable the 'unverified-package-set-drift' check for this scenario.
- **ask-artifact-checksum-diff** -- Provide sha256 checksums of the build output artifacts from two independent runs of the same commit, so the 'unverified-reproducibility-impact' finding can be confirmed or ruled out.
  - Evidence: Would move finding 'unverified-reproducibility-impact' to Confirmed non-reproducible-artifact or Confirmed-stable.

---

_Generated by `ci/report.py`. Re-running the analysis layer on unchanged input logs reproduces this report byte-for-byte._
