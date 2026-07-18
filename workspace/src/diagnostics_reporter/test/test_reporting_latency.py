"""Timing-sensitive test.

This test is the real-world shape of test that produces the
"candidate-flaky-test" finding in the synthetic broken scenario: a fixed
threshold compared against a value that can legitimately vary by a
millisecond or two depending on machine load. It is not run by this
repo's offline demo (which uses pre-generated log text instead, per
README.md) -- it exists so the CI recipe in .github/workflows/ci.yml has
a genuine test to execute.
"""

from diagnostics_reporter.reporter import latency_within_threshold


def test_latency_within_threshold_nominal():
    assert latency_within_threshold(0.010) is True


def test_latency_within_threshold_boundary():
    # Deliberately timing-sensitive: this is the assertion whose CI
    # behavior data/generate_logs.py's broken scenario dramatizes as an
    # intermittent failure. Kept here so the analogy in the generated
    # logs corresponds to a real test in the workspace.
    assert latency_within_threshold(0.019) is True
