"""Unit tests for the ROS2 CI & Build-Health Bridge analysis layer.

Run with:
    python3 -m unittest discover -s tests -v

Pure stdlib. No network calls, no ROS2, no Docker.
"""

import os
import re
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_TESTS_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from data.generate_logs import generate as generate_logs
from ci.parse_build import parse_build_log
from ci.parse_test import parse_test_log
from ci.reproducibility import (
    check_dockerfile_pin,
    check_dependency_manifests,
    compare_package_sets,
    collect_signals,
)
from ci.report import build_findings, render_markdown, write_report
from ci.run import run as run_pipeline
from ci.util import (
    Finding,
    SECTION_ADDITIONAL_DATA,
    SECTION_CONFIRMED,
    SECTION_LIKELY,
    SECTION_ORDER,
    SECTION_UNVERIFIED,
    md5_of_text,
    write_csv,
)

DOCKERFILE_PATH = os.path.join(_REPO_ROOT, "Dockerfile")
WORKSPACE_SRC_DIR = os.path.join(_REPO_ROOT, "workspace", "src")

# Hedge words that must appear somewhere in the summary of any Likely or
# Unverified finding. A finding whose summary contains none of these is
# suspiciously close to an unhedged, confident claim.
HEDGE_MARKERS = (
    "likely",
    "consistent with",
    "candidate",
    "not confirmed",
    "unverified",
    "may",
    "possib",
)

# Phrases that would indicate an unhedged, overconfident root-cause claim.
# None of these should ever appear in a generated report.
FORBIDDEN_UNHEDGED_PHRASES = (
    "the cause is",
    "the root cause is",
    "definitely caused by",
    "this is caused by",
    "confirmed root cause",
    "guaranteed",
)


class FixtureMixin(object):
    """Generates the two synthetic scenarios into a private temp dir once
    per test class, so tests never depend on (or mutate) data/logs_green
    and data/logs_broken as left behind by a previous run_demo.py run."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.data_dir = cls._tmp.name
        result = generate_logs(cls.data_dir)
        cls.green_dir = result["green"]
        cls.broken_dir = result["broken"]

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()


class TestParseBuildLog(FixtureMixin, unittest.TestCase):
    def test_green_all_packages_discovered_and_built(self):
        result = parse_build_log(os.path.join(self.green_dir, "build_log.txt"))
        self.assertEqual(
            result["packages_discovered"],
            ["nav_bridge_core", "sensor_fusion_utils", "diagnostics_reporter"],
        )
        self.assertEqual(len(result["packages_built_ok"]), 3)
        self.assertEqual(result["packages_failed"], [])
        self.assertEqual(result["missing_deps"], [])
        self.assertEqual(result["nondeterministic_timestamp_warnings"], [])

    def test_broken_failed_package_detected(self):
        result = parse_build_log(os.path.join(self.broken_dir, "build_log.txt"))
        self.assertEqual(result["packages_failed"], ["sensor_fusion_utils"])
        self.assertEqual(result["exit_codes"]["sensor_fusion_utils"], 2)
        self.assertIn("nav_bridge_core", result["packages_built_ok"])
        self.assertIn("diagnostics_reporter", result["packages_built_ok"])

    def test_broken_missing_deps_both_sources_captured(self):
        result = parse_build_log(os.path.join(self.broken_dir, "build_log.txt"))
        sources = {(d["package"], d["dependency"], d["source"]) for d in result["missing_deps"]}
        self.assertIn(("sensor_fusion_utils", "custom_msgs", "cmake"), sources)
        self.assertIn(("sensor_fusion_utils", "libpcl-fusion-dev", "rosdep"), sources)

    def test_broken_warning_count_attributed_to_correct_package(self):
        result = parse_build_log(os.path.join(self.broken_dir, "build_log.txt"))
        self.assertEqual(result["warning_counts"].get("nav_bridge_core"), 1)
        self.assertNotIn("diagnostics_reporter", result["warning_counts"])

    def test_broken_nondeterministic_timestamp_warning_captured(self):
        result = parse_build_log(os.path.join(self.broken_dir, "build_log.txt"))
        self.assertEqual(result["nondeterministic_timestamp_warnings"], ["nav_bridge_core"])

    def test_missing_log_file_returns_empty_not_error(self):
        result = parse_build_log(os.path.join(self.broken_dir, "does_not_exist.txt"))
        self.assertEqual(result["packages_discovered"], [])
        self.assertEqual(result["raw_line_count"], 0)

    def test_summary_line_parsed(self):
        result = parse_build_log(os.path.join(self.broken_dir, "build_log.txt"))
        self.assertEqual(result["summary_total_packages"], 2)
        self.assertAlmostEqual(result["summary_total_seconds"], 8.5)


class TestParseTestLog(FixtureMixin, unittest.TestCase):
    def test_green_totals_all_passing(self):
        result = parse_test_log(os.path.join(self.green_dir, "test_log.txt"))
        self.assertEqual(result["totals"]["errors"], 0)
        self.assertEqual(result["totals"]["failures"], 0)
        self.assertEqual(result["totals"]["tests"], 19)

    def test_green_no_candidate_flaky_tests_single_attempt(self):
        result = parse_test_log(os.path.join(self.green_dir, "test_log.txt"))
        self.assertEqual(result["candidate_flaky_tests"], [])

    def test_broken_candidate_flaky_test_detected(self):
        result = parse_test_log(os.path.join(self.broken_dir, "test_log.txt"))
        flaky = result["candidate_flaky_tests"]
        self.assertEqual(len(flaky), 1)
        self.assertEqual(flaky[0]["package"], "diagnostics_reporter")
        self.assertEqual(flaky[0]["test"], "test_reporting_latency")
        self.assertEqual(flaky[0]["failed_attempt"], 1)
        self.assertEqual(flaky[0]["later_passing_attempt"], 2)

    def test_broken_totals_use_latest_attempt_not_sum(self):
        result = parse_test_log(os.path.join(self.broken_dir, "test_log.txt"))
        # diagnostics_reporter attempt 2 has 0 failures; if totals summed
        # across attempts instead of using the latest, this would be 1.
        self.assertEqual(result["totals"]["failures"], 0)

    def test_broken_errored_test_captured_for_failed_build_package(self):
        result = parse_test_log(os.path.join(self.broken_dir, "test_log.txt"))
        sfu = result["packages"]["sensor_fusion_utils"]["attempts"][1]
        self.assertEqual(sfu["errors"], 1)
        self.assertEqual(len(sfu["errored_tests"]), 1)


class TestReproducibility(FixtureMixin, unittest.TestCase):
    def test_dockerfile_tag_pinned_detected(self):
        status, image_ref = check_dockerfile_pin(DOCKERFILE_PATH)
        self.assertEqual(status, "tag-pinned")
        self.assertEqual(image_ref, "ros:humble-ros-base")

    def test_dockerfile_missing_path_returns_not_found(self):
        status, image_ref = check_dockerfile_pin("/nonexistent/Dockerfile")
        self.assertEqual(status, "not-found")
        self.assertIsNone(image_ref)

    def test_digest_pinned_image_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "Dockerfile")
            with open(path, "w") as fh:
                fh.write(
                    "FROM ros:humble-ros-base@sha256:%s\n" % ("a" * 64)
                )
            status, image_ref = check_dockerfile_pin(path)
            self.assertEqual(status, "digest-pinned")

    def test_dependency_manifests_found_in_workspace(self):
        info = check_dependency_manifests(WORKSPACE_SRC_DIR)
        self.assertTrue(info["found"])
        self.assertEqual(info["count"], 3)

    def test_dependency_manifests_missing_dir(self):
        info = check_dependency_manifests("/nonexistent/src")
        self.assertFalse(info["found"])
        self.assertEqual(info["count"], 0)

    def test_package_set_comparison_identical_for_green_two_runs(self):
        build1 = parse_build_log(os.path.join(self.green_dir, "build_log.txt"))
        build2 = parse_build_log(os.path.join(self.green_dir, "build_log_run2.txt"))
        cmp_result = compare_package_sets(build1, build2)
        self.assertTrue(cmp_result["identical"])
        self.assertEqual(cmp_result["run1_only"], [])
        self.assertEqual(cmp_result["run2_only"], [])

    def test_package_set_comparison_none_without_second_run(self):
        cmp_result = compare_package_sets(None, None)
        self.assertIsNone(cmp_result)

    def test_collect_signals_reports_nondeterministic_count(self):
        build1 = parse_build_log(os.path.join(self.broken_dir, "build_log.txt"))
        signals = collect_signals(
            dockerfile_path=DOCKERFILE_PATH,
            workspace_src_dir=WORKSPACE_SRC_DIR,
            build_result_run1=build1,
            build_result_run2=None,
        )
        self.assertEqual(signals["nondeterministic_timestamp_warning_count"], 1)
        self.assertIsNone(signals["package_set_comparison"])


class TestFourSectionBucketing(FixtureMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super(TestFourSectionBucketing, cls).setUpClass()
        cls.broken_result = run_pipeline(
            cls.broken_dir,
            tempfile.mkdtemp(),
            dockerfile_path=DOCKERFILE_PATH,
            workspace_src_dir=WORKSPACE_SRC_DIR,
            build_log_run2_path=None,
            scenario_name="test-broken",
        )
        cls.green_result = run_pipeline(
            cls.green_dir,
            tempfile.mkdtemp(),
            dockerfile_path=DOCKERFILE_PATH,
            workspace_src_dir=WORKSPACE_SRC_DIR,
            build_log_run2_path=os.path.join(cls.green_dir, "build_log_run2.txt"),
            scenario_name="test-green",
        )

    def _by_section(self, result):
        buckets = {s: [] for s in SECTION_ORDER}
        for f in result["findings"]:
            buckets[f.section].append(f)
        return buckets

    def test_failed_package_count_is_confirmed(self):
        buckets = self._by_section(self.broken_result)
        confirmed_categories = {f.category for f in buckets[SECTION_CONFIRMED]}
        self.assertIn("build-failure", confirmed_categories)
        build_failure = [f for f in buckets[SECTION_CONFIRMED] if f.category == "build-failure"][0]
        self.assertIn("sensor_fusion_utils", build_failure.summary)

    def test_missing_dependency_hypothesis_is_likely_with_evidence(self):
        buckets = self._by_section(self.broken_result)
        likely_categories = {f.category for f in buckets[SECTION_LIKELY]}
        self.assertIn("likely-missing-dependency", likely_categories)
        item = [f for f in buckets[SECTION_LIKELY] if f.category == "likely-missing-dependency"][0]
        self.assertIn("likely", item.summary.lower())
        self.assertTrue(item.evidence)  # must carry evidence
        self.assertIn("confirmed by", item.evidence.lower())

    def test_flaky_test_is_unverified(self):
        buckets = self._by_section(self.broken_result)
        unverified_categories = {f.category for f in buckets[SECTION_UNVERIFIED]}
        self.assertIn("candidate-flaky-test", unverified_categories)

    def test_flaky_test_ask_is_additional_data_required(self):
        buckets = self._by_section(self.broken_result)
        ask_categories = {f.category for f in buckets[SECTION_ADDITIONAL_DATA]}
        self.assertIn("ask-repeated-test-runs", ask_categories)

    def test_green_scenario_has_no_build_failure_or_flaky_findings(self):
        buckets = self._by_section(self.green_result)
        categories = {f.category for f in buckets[SECTION_LIKELY]}
        self.assertNotIn("likely-missing-dependency", categories)
        unverified_categories = {f.category for f in buckets[SECTION_UNVERIFIED]}
        self.assertNotIn("candidate-flaky-test", unverified_categories)

    def test_every_section_present_in_broken_report(self):
        buckets = self._by_section(self.broken_result)
        for section in SECTION_ORDER:
            self.assertTrue(len(buckets[section]) > 0, "section %r is empty" % section)


class TestReportHonesty(FixtureMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super(TestReportHonesty, cls).setUpClass()
        cls.broken_result = run_pipeline(
            cls.broken_dir,
            tempfile.mkdtemp(),
            dockerfile_path=DOCKERFILE_PATH,
            workspace_src_dir=WORKSPACE_SRC_DIR,
            build_log_run2_path=None,
            scenario_name="test-broken",
        )

    def test_report_never_emits_unhedged_root_cause_phrase(self):
        report_lower = self.broken_result["report_text"].lower()
        for phrase in FORBIDDEN_UNHEDGED_PHRASES:
            self.assertNotIn(
                phrase,
                report_lower,
                "found unhedged root-cause phrase %r in report" % phrase,
            )

    def test_likely_and_unverified_findings_are_hedged(self):
        for f in self.broken_result["findings"]:
            if f.section in (SECTION_LIKELY, SECTION_UNVERIFIED):
                summary_lower = f.summary.lower()
                self.assertTrue(
                    any(marker in summary_lower for marker in HEDGE_MARKERS),
                    "finding %r in section %r has no hedge marker: %r"
                    % (f.category, f.section, f.summary),
                )

    def test_confirmed_findings_have_evidence(self):
        for f in self.broken_result["findings"]:
            if f.section == SECTION_CONFIRMED:
                self.assertTrue(f.evidence, "confirmed finding %r missing evidence" % f.category)

    def test_additional_data_asks_are_concrete_not_vague(self):
        vague_terms = ("investigate further", "look into it", "tbd", "unclear")
        for f in self.broken_result["findings"]:
            if f.section == SECTION_ADDITIONAL_DATA:
                summary_lower = f.summary.lower()
                for term in vague_terms:
                    self.assertNotIn(term, summary_lower)


class TestDeterminism(FixtureMixin, unittest.TestCase):
    def test_running_pipeline_twice_yields_identical_report_md5(self):
        out1 = tempfile.mkdtemp()
        out2 = tempfile.mkdtemp()
        result1 = run_pipeline(
            self.broken_dir,
            out1,
            dockerfile_path=DOCKERFILE_PATH,
            workspace_src_dir=WORKSPACE_SRC_DIR,
            build_log_run2_path=None,
            scenario_name="determinism-check",
        )
        result2 = run_pipeline(
            self.broken_dir,
            out2,
            dockerfile_path=DOCKERFILE_PATH,
            workspace_src_dir=WORKSPACE_SRC_DIR,
            build_log_run2_path=None,
            scenario_name="determinism-check",
        )
        self.assertEqual(result1["report_md5"], result2["report_md5"])
        self.assertEqual(result1["report_text"], result2["report_text"])

    def test_regenerating_synthetic_logs_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            generate_logs(tmp1)
            generate_logs(tmp2)
            with open(os.path.join(tmp1, "logs_broken", "build_log.txt")) as fh:
                text1 = fh.read()
            with open(os.path.join(tmp2, "logs_broken", "build_log.txt")) as fh:
                text2 = fh.read()
            self.assertEqual(text1, text2)


class TestReportRendering(FixtureMixin, unittest.TestCase):
    def test_render_markdown_contains_all_four_section_titles(self):
        build_result = parse_build_log(os.path.join(self.broken_dir, "build_log.txt"))
        test_result = parse_test_log(os.path.join(self.broken_dir, "test_log.txt"))
        signals = collect_signals(
            dockerfile_path=DOCKERFILE_PATH,
            workspace_src_dir=WORKSPACE_SRC_DIR,
            build_result_run1=build_result,
            build_result_run2=None,
        )
        findings = build_findings("test", build_result, test_result, signals)
        report_text = render_markdown("test", findings, build_result, test_result, signals)
        self.assertIn("## Confirmed evidence", report_text)
        self.assertIn("## Likely causes", report_text)
        self.assertIn("## Unverified hypotheses", report_text)
        self.assertIn("## Additional data required", report_text)

    def test_write_report_writes_both_files(self):
        build_result = parse_build_log(os.path.join(self.broken_dir, "build_log.txt"))
        test_result = parse_test_log(os.path.join(self.broken_dir, "test_log.txt"))
        signals = collect_signals(
            dockerfile_path=DOCKERFILE_PATH,
            workspace_src_dir=WORKSPACE_SRC_DIR,
            build_result_run1=build_result,
            build_result_run2=None,
        )
        findings = build_findings("test", build_result, test_result, signals)
        with tempfile.TemporaryDirectory() as out_dir:
            report_path, csv_path, report_text, report_md5 = write_report(
                "test", findings, build_result, test_result, signals, out_dir
            )
            self.assertTrue(os.path.isfile(report_path))
            self.assertTrue(os.path.isfile(csv_path))
            self.assertEqual(md5_of_text(report_text), report_md5)


class TestUtil(unittest.TestCase):
    def test_finding_rejects_unknown_section(self):
        with self.assertRaises(AssertionError):
            Finding("not-a-real-section", "cat", "pkg", "summary", "evidence")

    def test_write_csv_round_trip(self):
        import csv

        rows = [
            {"section": "confirmed", "category": "x", "package": "p", "summary": "s", "evidence": "e"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.csv")
            write_csv(path, rows, ["section", "category", "package", "summary", "evidence"])
            with open(path) as fh:
                reader = list(csv.DictReader(fh))
            self.assertEqual(len(reader), 1)
            self.assertEqual(reader[0]["category"], "x")


if __name__ == "__main__":
    unittest.main()
