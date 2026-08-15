# ROS2 CI & Build-Health Bridge

Parses `colcon` build and test logs into a structured, evidence-graded
**build-health report**: which packages were discovered, built, or failed,
per-package warning counts, missing-dependency lines (CMake `find_package`
failures and unresolved `rosdep` keys), pass/fail/error/skip counts per
package, candidate flaky tests that failed in one attempt and passed in a
later one, and reproducibility signals such as whether the Docker base image
is pinned by digest or only by tag. Every finding lands in exactly one of
four buckets -- confirmed evidence, likely causes, unverified hypotheses,
additional data required -- carries an `evidence` field, and every
Likely/Unverified item is hedged, with a test asserting the report never
emits an unhedged root-cause sentence. The repo also ships a reproducible
Docker build + GitHub Actions recipe that runs `colcon build` and `colcon
test`, but the offline analysis layer is the actual value on offer: this
tool only claims what it can measure.

This is sample #2 in a robotics-ops bridge portfolio series. Sample #1
("ROS2 Bag Data Audit & Anomaly Report") audits recorded bag data with the
same four-section method this repo uses for CI logs. The author is a
data/automation engineer who builds verification and reporting tooling
around ROS2 pipelines — **not** a ROS2 field/runtime engineer, and this
repo does not claim to fix robot code or diagnose runtime robotics
behavior. See Limitations below.

## The problem

Two failure modes are both common and both bad:

1. **Hand-reading CI logs is slow.** A failed `colcon build` or a flaky
   `colcon test` run produces hundreds of lines of interleaved
   per-package output. Finding "which package actually failed, why, and
   is this the third time this week" by eye doesn't scale past a couple
   of packages.
2. **Tools that scream "BUILD BROKEN: dependency X" with no evidence are
   worse than the raw log.** A one-line verdict with no supporting data
   is not more useful than a red X in a CI dashboard — it just adds a
   confident-sounding guess on top. If the guess is wrong, you've lost
   time chasing it instead of reading the actual failure.

This repo tries to avoid both: parse the log completely and cheaply
(so you don't hand-read it), but never print a claim stronger than the
data supports (so you don't get burned by an overconfident guess).

## What it does

- Parses colcon build logs into structured facts: which packages were
  discovered, which built, which failed, per-package warning counts, and
  any missing-dependency lines (CMake `find_package` failures and
  unresolved `rosdep` keys).
- Parses colcon test logs into structured facts: pass/fail/error/skip
  counts per package, and — when a log includes more than one attempt of
  the same package — which specific tests failed in one attempt but not
  a later one (a candidate-flaky-test signal, not a flakiness verdict).
- Collects reproducibility *signals* (not a verdict): is the Docker base
  image pinned by digest or just by tag, do the packages declare
  dependency manifests, does the discovered package set match across two
  build runs, are there nondeterministic-timestamp warnings in the log.
- Assembles everything into a four-section build-health report (see
  below) plus a `findings.csv` for spreadsheet/dashboard consumption.

## The four-section method

Every finding goes in exactly one of four buckets. This is the core
design of the report, not a formatting choice — it is how the tool keeps
its claims honest.

1. **Confirmed evidence** — only facts read directly off the logs
   (`Finished <<< pkg`, an explicit `Summary:` line, a literal
   "rosdep keys could not be resolved" line, and so on). No
   interpretation, no inference, no "probably."
2. **Likely causes** — reasoned hypotheses, always explicitly hedged
   ("likely related to", "is likely to"), each one carrying both the
   supporting evidence it's built on *and* a concrete statement of what
   additional data would confirm it. Example: a failed package with a
   missing-dependency line for the same package name is a likely cause of
   that failure — but the report says so with a hedge, not a verdict, and
   spells out that a rebuild after resolving the dependency is what would
   actually confirm it.
3. **Unverified hypotheses** — signals consistent with a problem but not
   confirmed with the data on hand. A test that failed in attempt 1 and
   passed in attempt 2 is *consistent with* flakiness; two data points do
   not *confirm* flakiness, and the report says exactly that.
4. **Additional data required** — concrete, specific asks (a named log, a
   named number of repeated runs, a named checksum comparison) that would
   move an item above from Likely/Unverified into Confirmed or
   ruled-out. Never a vague "investigate further."

Every finding in this repo's reports carries an `evidence` field. Every
Likely/Unverified item is phrased with a hedge word (`likely`,
`consistent with`, `candidate`, `not confirmed`) — `tests/test_ci_bridge.py`
has an explicit test asserting the report never emits an unhedged
root-cause sentence.

## How to run

### Offline analysis-layer demo (what's actually verified in this repo)

No Docker, no ROS2, no network, no API keys:

```bash
cd ros2-ci-bridge
python3 run_demo.py
python3 -m unittest discover -s tests -v
```

`run_demo.py` deterministically regenerates two synthetic scenarios
(`data/generate_logs.py`, no randomness — same input every run) and runs
the `ci/` analysis layer over both, writing `sample_output/`. Running it
twice produces byte-identical output files; `tests/test_ci_bridge.py`
checks this with an md5 comparison.

Docker Compose runs the same offline step inside a container with no
network access (`network_mode: none`):

```bash
docker compose run --rm analyze
```

### The real ROS2 build (this is what actually runs in CI, not locally here)

`Dockerfile` is a genuine, runnable `colcon build` + `colcon test` recipe
against `ros:humble-ros-base`. It is not exercised by this repo's demo or
unit tests — building a full ROS2 base image is exactly the kind of heavy,
environment-sensitive step that doesn't belong in an offline code sample.
Instead:

```bash
docker build -t ros2-ci-bridge-build -f Dockerfile .
```

`.github/workflows/ci.yml` runs that build on every push (matrix over ROS2
distros), extracts the resulting `build_log.txt` / `test_log.txt`, feeds
them through the exact same `ci/` analysis layer used by `run_demo.py`,
and uploads the build-health report as a workflow artifact. Same parser,
same four-section method, real logs instead of synthetic ones — that's
the honest design here, the same way sample #1's parser is verified
offline against a synthetic bag export and only points at real bag files
when you hand it one.

### CLI

```bash
python3 -m ci.run \
  --logs-dir data/logs_broken \
  --out-dir /tmp/out \
  --dockerfile Dockerfile \
  --workspace-src workspace/src \
  --scenario-name "my build"
```

## Repository layout

```
README.md, SCHEMA.md          -- docs
Dockerfile, docker-compose.yml -- real colcon build/test recipe + offline analysis service
.github/workflows/ci.yml       -- GitHub Actions: real build in CI -> ci/ analysis -> artifact
ci/                             -- stdlib-only analysis layer (parse_build, parse_test,
                                    reproducibility, report, run, util)
data/generate_logs.py          -- deterministic synthetic colcon log generator
data/logs_green/, logs_broken/ -- generated fixtures (written by generate_logs.py / run_demo.py)
workspace/src/                 -- minimal real ROS2 packages the Dockerfile actually builds
run_demo.py                    -- offline demo entry point, writes sample_output/
sample_output/                 -- generated report, CSV, run summary, repro steps
tests/test_ci_bridge.py        -- 15+ unittest cases
```

## Limitations

Read this before trusting anything this tool outputs.

- **We do not verify the ROS2 code is correct.** This tool checks that a
  build/test *pipeline* is reproducible and that its results are parsed
  faithfully. It has no opinion on whether `nav_bridge_core` correctly
  implements a navigation bridge, whether a fusion algorithm is
  numerically sound, or whether a robot behaves safely. That is a robotics
  code-review question, and out of scope here.
- **We are a CI/data verification layer, not ROS2 runtime engineers.**
  Nothing in this repo runs on a real robot, reads sensor data, or claims
  domain expertise in navigation, perception, or control. It reads text
  logs.
- **The heavy build runs in CI, not in this offline demo.** `run_demo.py`
  and `tests/` never invoke Docker or `colcon`; they exercise the parsing
  and report-assembly logic against captured/synthetic log text. If the
  real `colcon build`/`colcon test` output format drifts from what
  `SCHEMA.md` documents (a `colcon` version bump, a different log
  formatter), the parser will silently under-report rather than crash —
  unmatched lines are simply not counted as evidence. Treat a
  suspiciously empty Confirmed-evidence section as a signal to check the
  log format, not as "everything passed."
- **Reproducibility signals are heuristics, not proofs.** A digest-pinned
  base image, a present `package.xml`, and a matching package set across
  two runs are all *positively correlated* with reproducibility. None of
  them, individually or together, proves bit-for-bit reproducible build
  output — this repo never diffs actual build artifact checksums, and
  `reproducibility.py` never emits a "reproducible: yes/no" verdict on
  purpose.
- **Flaky-test detection needs more than two data points.** The
  candidate-flaky-test signal fires on a fail-then-pass pattern across two
  attempts in the same log. That is consistent with flakiness and is also
  consistent with a one-off environment fluke; the report says so and
  asks for more repeated runs before treating it as confirmed.
- **Missing-dependency attribution is line-matching, not semantic
  analysis.** A `Likely causes` entry linking a failed package to a
  missing-dependency line is based on both facts appearing for the same
  package name in the same log — not on parsing CMake's actual dependency
  graph. Multiple simultaneous failures in a real workspace could produce
  a mis-attributed hypothesis; that's exactly why it's Likely, not
  Confirmed, and why the entry states what would confirm it.

## License

MIT. See `LICENSE`.
