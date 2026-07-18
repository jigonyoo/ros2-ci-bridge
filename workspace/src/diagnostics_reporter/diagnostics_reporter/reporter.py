"""Placeholder diagnostics-reporting logic.

Intentionally trivial: this workspace exists to give the CI recipe and the
synthetic colcon logs something real to point at, not to demonstrate
production diagnostics-aggregation logic.
"""


def latency_within_threshold(elapsed_seconds, threshold_seconds=0.020):
    """Return True if elapsed_seconds is within threshold_seconds.

    The synthetic "broken" scenario's flaky test exercises a
    timing-sensitive check shaped like this one -- see
    test/test_reporting_latency.py and data/generate_logs.py.
    """
    return elapsed_seconds <= threshold_seconds
