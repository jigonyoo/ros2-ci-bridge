"""
ci: offline analysis layer for the ROS2 CI & Build-Health Bridge.

Pure Python standard library. No network calls. No API keys.

This package parses colcon build/test logs that were produced elsewhere
(a real CI run, or the synthetic generator in data/generate_logs.py) and
assembles a four-section build-health report:

    1. Confirmed evidence      - directly measured facts only
    2. Likely causes           - hedged hypotheses with supporting evidence
    3. Unverified hypotheses   - signals consistent with a problem, not confirmed
    4. Additional data required - concrete follow-up asks

See README.md for the full method and its limitations.
"""

__version__ = "0.1.0"
