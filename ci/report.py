"""Assemble the four-section build-health report (markdown + CSV) from
parsed build/test results and reproducibility signals.

This module's only job is to phrase facts. It must never state a root
cause as certain -- confirmed facts go in "Confirmed evidence" verbatim;
everything else is hedged and carries its own evidence and a concrete
follow-up ask. See README.md's "The four-section method".
"""

from ci.util import (
    Finding,
    SECTION_ADDITIONAL_DATA,
    SECTION_CONFIRMED,
    SECTION_LIKELY,
    SECTION_ORDER,
    SECTION_TITLES,
    SECTION_UNVERIFIED,
    md5_of_text,
    write_csv,
)

CSV_FIELDNAMES = ["section", "category", "package", "summary", "evidence"]


def build_findings(scenario_name, build_result, test_result, repro_signals):
    """Turn parsed results into a list of Finding objects, four-section-bucketed.

    build_result:  dict from ci.parse_build.parse_build_log
    test_result:   dict from ci.parse_test.parse_test_log
    repro_signals: dict from ci.reproducibility.collect_signals
    """
    findings = []

    # ---------------------------------------------------------------
    # 1. Confirmed evidence -- directly measured facts, no interpretation
    # ---------------------------------------------------------------
    discovered = build_result["packages_discovered"]
    built_ok = build_result["packages_built_ok"]
    failed = build_result["packages_failed"]

    findings.append(
        Finding(
            SECTION_CONFIRMED,
            "build-summary",
            "",
            "colcon build discovered %d package(s): %s."
            % (len(discovered), ", ".join(discovered) if discovered else "(none)"),
            "packages_discovered=%r (parsed from 'Starting >>> <pkg>' lines)" % (discovered,),
        )
    )
    findings.append(
        Finding(
            SECTION_CONFIRMED,
            "build-summary",
            "",
            "%d package(s) finished the build successfully: %s."
            % (len(built_ok), ", ".join(built_ok) if built_ok else "(none)"),
            "packages_built_ok=%r (parsed from 'Finished <<<' lines)" % (built_ok,),
        )
    )
    if failed:
        findings.append(
            Finding(
                SECTION_CONFIRMED,
                "build-failure",
                ", ".join(failed),
                "%d package(s) failed the build: %s."
                % (len(failed), ", ".join(failed)),
                "packages_failed=%r, exit_codes=%r (parsed from 'Failed <<<' lines)"
                % (failed, build_result["exit_codes"]),
            )
        )
    else:
        findings.append(
            Finding(
                SECTION_CONFIRMED,
                "build-failure",
                "",
                "0 packages failed the build.",
                "packages_failed=[] (no 'Failed <<<' lines matched)",
            )
        )

    for pkg, count in sorted(build_result["warning_counts"].items()):
        findings.append(
            Finding(
                SECTION_CONFIRMED,
                "build-warning",
                pkg,
                "%s produced %d line(s) matching 'Warning' in its stderr block."
                % (pkg, count),
                "warning_counts[%r]=%d" % (pkg, count),
            )
        )

    if build_result["missing_deps"]:
        for md in build_result["missing_deps"]:
            findings.append(
                Finding(
                    SECTION_CONFIRMED,
                    "missing-dependency-reference",
                    md["package"],
                    "Build log contains a missing-dependency reference for '%s' "
                    "(source: %s)%s."
                    % (
                        md["dependency"],
                        md["source"],
                        " attributed to package %s" % md["package"] if md["package"] else "",
                    ),
                    "missing_deps entry=%r" % (md,),
                )
            )

    totals = test_result["totals"]
    findings.append(
        Finding(
            SECTION_CONFIRMED,
            "test-summary",
            "",
            "Test results (latest attempt per package): %d test(s), %d error(s), "
            "%d failure(s), %d skipped."
            % (totals["tests"], totals["errors"], totals["failures"], totals["skipped"]),
            "totals=%r" % (totals,),
        )
    )

    if repro_signals["nondeterministic_timestamp_warning_count"] > 0:
        findings.append(
            Finding(
                SECTION_CONFIRMED,
                "nondeterministic-timestamp-warning",
                ", ".join(repro_signals["nondeterministic_timestamp_warning_packages"]),
                "Build log contains %d non-reproducible-timestamp warning line(s), "
                "for package(s): %s."
                % (
                    repro_signals["nondeterministic_timestamp_warning_count"],
                    ", ".join(repro_signals["nondeterministic_timestamp_warning_packages"]),
                ),
                "nondeterministic_timestamp_warning_count=%d"
                % repro_signals["nondeterministic_timestamp_warning_count"],
            )
        )

    findings.append(
        Finding(
            SECTION_CONFIRMED,
            "dockerfile-pin",
            "",
            "Dockerfile base-image pin status: %s (image ref: %s)."
            % (repro_signals["dockerfile_pin_status"], repro_signals["dockerfile_pinned_image_ref"]),
            "check_dockerfile_pin() -> (%r, %r)"
            % (repro_signals["dockerfile_pin_status"], repro_signals["dockerfile_pinned_image_ref"]),
        )
    )

    pkg_cmp = repro_signals["package_set_comparison"]
    if pkg_cmp is not None:
        findings.append(
            Finding(
                SECTION_CONFIRMED,
                "package-set-comparison",
                "",
                "Comparing two build runs: discovered package set was %s "
                "(run1=%d packages, run2=%d packages)."
                % (
                    "identical" if pkg_cmp["identical"] else "NOT identical",
                    pkg_cmp["run1_count"],
                    pkg_cmp["run2_count"],
                ),
                "package_set_comparison=%r" % (pkg_cmp,),
            )
        )

    # ---------------------------------------------------------------
    # 2. Likely causes -- hedged hypotheses, with evidence AND what
    #    would confirm them
    # ---------------------------------------------------------------
    missing_dep_by_pkg = {}
    for md in build_result["missing_deps"]:
        if md["package"]:
            missing_dep_by_pkg.setdefault(md["package"], []).append(md["dependency"])

    for pkg in failed:
        deps_for_pkg = missing_dep_by_pkg.get(pkg, [])
        if deps_for_pkg:
            dep_list = ", ".join(sorted(set(deps_for_pkg)))
            findings.append(
                Finding(
                    SECTION_LIKELY,
                    "likely-missing-dependency",
                    pkg,
                    "%s's build failure is likely related to unresolved dependency "
                    "reference(s) (%s) logged for the same package, but this is not "
                    "confirmed as the sole or exact cause."
                    % (pkg, dep_list),
                    "%s failed with exit code %s; missing-dependency lines "
                    "for %s: %s. Would be confirmed by: re-running the build after "
                    "installing %s and observing %s transition from Failed to "
                    "Finished with no other changes."
                    % (
                        pkg,
                        build_result["exit_codes"].get(pkg, "?"),
                        pkg,
                        dep_list,
                        dep_list,
                        pkg,
                    ),
                )
            )
        elif pkg in failed:
            findings.append(
                Finding(
                    SECTION_LIKELY,
                    "likely-unclassified-build-failure",
                    pkg,
                    "%s's build failure has no matching missing-dependency or "
                    "warning signature in this log, so no specific likely cause "
                    "is proposed here." % pkg,
                    "%s exit code %s, no missing_deps entries attributed "
                    "to this package. Would be confirmed by: the full stderr/stdout "
                    "of the failed build step, which this log does not include."
                    % (pkg, build_result["exit_codes"].get(pkg, "?")),
                )
            )

    if repro_signals["dockerfile_pin_status"] in ("tag-pinned", "unpinned"):
        findings.append(
            Finding(
                SECTION_LIKELY,
                "likely-reproducibility-gap",
                "",
                "The base image is %s rather than digest-pinned, which is likely "
                "to allow the build environment to drift between runs -- though "
                "whether it actually has drifted is not verified here."
                % repro_signals["dockerfile_pin_status"],
                "check_dockerfile_pin() returned %r for image ref %r. "
                "Would be confirmed by: pulling the tag on two different dates and "
                "diffing the resulting image digests."
                % (
                    repro_signals["dockerfile_pin_status"],
                    repro_signals["dockerfile_pinned_image_ref"],
                ),
            )
        )

    # ---------------------------------------------------------------
    # 3. Unverified hypotheses -- signals consistent with a problem,
    #    not confirmed
    # ---------------------------------------------------------------
    for flaky in test_result["candidate_flaky_tests"]:
        findings.append(
            Finding(
                SECTION_UNVERIFIED,
                "candidate-flaky-test",
                flaky["package"],
                "%s.%s failed in attempt %d and did not fail in attempt %d for the "
                "same package -- this pattern is consistent with a flaky "
                "(intermittently failing) test, but two attempts is not enough "
                "to confirm flakiness versus a one-off environmental fluke."
                % (
                    flaky["package"],
                    flaky["test"],
                    flaky["failed_attempt"],
                    flaky["later_passing_attempt"],
                ),
                "candidate_flaky_tests entry=%r" % (flaky,),
            )
        )

    if repro_signals["nondeterministic_timestamp_warning_count"] > 0:
        findings.append(
            Finding(
                SECTION_UNVERIFIED,
                "unverified-reproducibility-impact",
                ", ".join(repro_signals["nondeterministic_timestamp_warning_packages"]),
                "The non-reproducible-timestamp warning(s) logged above are "
                "consistent with build artifacts that would differ byte-for-byte "
                "across runs, but this demo does not diff actual artifact "
                "checksums, so the impact on reproducibility is unverified.",
                "%d timestamp-warning line(s) parsed from the build log. "
                "No artifact checksum comparison was performed."
                % repro_signals["nondeterministic_timestamp_warning_count"],
            )
        )

    if pkg_cmp is not None and not pkg_cmp["identical"]:
        findings.append(
            Finding(
                SECTION_UNVERIFIED,
                "unverified-package-set-drift",
                "",
                "The two build runs discovered different package sets (run1-only: "
                "%s; run2-only: %s), which is consistent with a nondeterministic "
                "or environment-dependent package discovery step, but the cause of "
                "the difference is unverified from these logs alone."
                % (
                    ", ".join(pkg_cmp["run1_only"]) or "(none)",
                    ", ".join(pkg_cmp["run2_only"]) or "(none)",
                ),
                "package_set_comparison=%r" % (pkg_cmp,),
            )
        )

    # ---------------------------------------------------------------
    # 4. Additional data required -- concrete, specific asks
    # ---------------------------------------------------------------
    for pkg in failed:
        deps_for_pkg = missing_dep_by_pkg.get(pkg, [])
        if deps_for_pkg:
            dep_list = ", ".join(sorted(set(deps_for_pkg)))
            findings.append(
                Finding(
                    SECTION_ADDITIONAL_DATA,
                    "ask-rebuild-after-dependency-fix",
                    pkg,
                    "Provide a rebuild log for %s captured after installing/"
                    "resolving dependency(ies) %s, so the likely-cause hypothesis "
                    "above can be confirmed or ruled out."
                    % (pkg, dep_list),
                    "Would move finding 'likely-missing-dependency' (package=%s) "
                    "from Likely to Confirmed or ruled-out." % pkg,
                )
            )
        else:
            findings.append(
                Finding(
                    SECTION_ADDITIONAL_DATA,
                    "ask-full-build-stderr",
                    pkg,
                    "Provide the full stdout/stderr of the failed build step for "
                    "%s (this log only captured the summary Failed/exit-code line)."
                    % pkg,
                    "Would allow a specific likely-cause hypothesis to be formed "
                    "for %s instead of 'unclassified'." % pkg,
                )
            )

    for flaky in test_result["candidate_flaky_tests"]:
        findings.append(
            Finding(
                SECTION_ADDITIONAL_DATA,
                "ask-repeated-test-runs",
                flaky["package"],
                "Run %s.%s at least 5 additional independent times (ideally on "
                "different CI runners/days) and provide the pass/fail log for "
                "each run to confirm or rule out flakiness."
                % (flaky["package"], flaky["test"]),
                "Would move finding 'candidate-flaky-test' (package=%s, test=%s) "
                "from Unverified to Confirmed-flaky or Confirmed-one-off."
                % (flaky["package"], flaky["test"]),
            )
        )

    if repro_signals["dockerfile_pin_status"] != "digest-pinned":
        findings.append(
            Finding(
                SECTION_ADDITIONAL_DATA,
                "ask-digest-pin",
                "",
                "Pin the Dockerfile FROM line to a specific @sha256 digest and "
                "provide a build log from the pinned image to establish a stable "
                "baseline for future reproducibility comparisons.",
                "Would upgrade the 'likely-reproducibility-gap' finding from "
                "Likely to either Confirmed-stable or a specific new failure mode.",
            )
        )

    if pkg_cmp is None:
        findings.append(
            Finding(
                SECTION_ADDITIONAL_DATA,
                "ask-second-build-run",
                "",
                "Provide a second independent build log (same commit, same "
                "Dockerfile) so the discovered package set can be compared across "
                "runs. Only one run is available in this scenario, so package-set "
                "reproducibility could not be evaluated at all.",
                "Would populate the 'package-set-comparison' confirmed finding and "
                "enable the 'unverified-package-set-drift' check for this scenario.",
            )
        )

    if repro_signals["nondeterministic_timestamp_warning_count"] > 0:
        findings.append(
            Finding(
                SECTION_ADDITIONAL_DATA,
                "ask-artifact-checksum-diff",
                "",
                "Provide sha256 checksums of the build output artifacts from two "
                "independent runs of the same commit, so the 'unverified-"
                "reproducibility-impact' finding can be confirmed or ruled out.",
                "Would move finding 'unverified-reproducibility-impact' to "
                "Confirmed non-reproducible-artifact or Confirmed-stable.",
            )
        )

    return findings


def render_markdown(scenario_name, findings, build_result, test_result, repro_signals):
    """Render findings into the four-section markdown report."""
    lines = []
    lines.append("# ROS2 CI & Build-Health Report")
    lines.append("")
    lines.append("Scenario: **%s**" % scenario_name)
    lines.append("")
    lines.append(
        "This report was generated entirely offline by the analysis layer in "
        "`ci/` from the build/test logs listed below. It is a data/CI "
        "verification artifact, not a robotics-runtime diagnosis -- see "
        "README.md's Limitations section."
    )
    lines.append("")

    by_section = {s: [] for s in SECTION_ORDER}
    for f in findings:
        by_section[f.section].append(f)

    section_intro = {
        SECTION_CONFIRMED: (
            "Facts read directly from the build/test logs. No interpretation."
        ),
        SECTION_LIKELY: (
            "Reasoned hypotheses. Each item is explicitly hedged, lists its "
            "supporting evidence, and states what additional data would "
            "confirm or rule it out."
        ),
        SECTION_UNVERIFIED: (
            "Signals that are consistent with a problem but are not confirmed "
            "with the data on hand."
        ),
        SECTION_ADDITIONAL_DATA: (
            "Concrete, specific requests for logs/data that would move an item "
            "above toward Confirmed or ruled-out."
        ),
    }

    for section in SECTION_ORDER:
        items = by_section[section]
        lines.append("## %s" % SECTION_TITLES[section])
        lines.append("")
        lines.append(section_intro[section])
        lines.append("")
        if not items:
            lines.append("_None for this scenario._")
            lines.append("")
            continue
        for f in items:
            pkg_tag = " `[%s]`" % f.package if f.package else ""
            lines.append("- **%s%s** -- %s" % (f.category, pkg_tag, f.summary))
            lines.append("  - Evidence: %s" % f.evidence)
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "_Generated by `ci/report.py`. Re-running the analysis layer on "
        "unchanged input logs reproduces this report byte-for-byte._"
    )
    lines.append("")
    return "\n".join(lines)


def write_report(scenario_name, findings, build_result, test_result, repro_signals, out_dir):
    """Write build_health_report.md and findings.csv into out_dir.

    Returns (report_path, csv_path, report_text, report_md5).
    """
    import os

    os.makedirs(out_dir, exist_ok=True)
    report_text = render_markdown(scenario_name, findings, build_result, test_result, repro_signals)
    report_path = os.path.join(out_dir, "build_health_report.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(report_text)

    csv_path = os.path.join(out_dir, "findings.csv")
    write_csv(csv_path, [f.as_row() for f in findings], CSV_FIELDNAMES)

    return report_path, csv_path, report_text, md5_of_text(report_text)
