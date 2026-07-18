# Log & Data Schema

This file documents the exact text formats the `ci/` parsers consume. It is
the contract between "whatever produced the logs" (a real `colcon build` /
`colcon test` run in CI, or `data/generate_logs.py` in this demo) and the
analysis layer.

The parsers are line-oriented and intentionally forgiving: unrecognized
lines are ignored rather than raising errors, because real `colcon` output
varies by version and by which packages are in the workspace. Anything the
parser *does* match becomes a fact in the "Confirmed evidence" section;
anything it doesn't recognize is simply not counted — it never becomes a
guess.

## 1. Build log (`build_log.txt`)

One `colcon build` invocation, plain text, one event per line.

| Pattern | Meaning |
|---|---|
| `Starting >>> <pkg>` | `<pkg>` was discovered and its build started |
| `Finished <<< <pkg> [<seconds>s]` | `<pkg>` built successfully in `<seconds>` |
| `Failed   <<< <pkg> [<seconds>s, exited with code <code>]` | `<pkg>` build failed with exit code `<code>` |
| `--- stderr: <pkg>` ... `---` | stderr block for `<pkg>`; lines inside are scanned for `Warning` (counted as a build warning) and for missing-dependency signatures below |
| `CMake Error: Could not find a package configuration file provided by "<dep>"` | a CMake-level missing dependency reference to `<dep>` |
| `ERROR: the following rosdep keys could not be resolved for package '<pkg>': ['<dep>']` | a rosdep-level missing system dependency `<dep>` for `<pkg>` |
| `WARNING: non-reproducible timestamp detected in <pkg> build artifact (mtime varies between runs)` | a nondeterminism signal for `<pkg>` (heuristic, not proof) |
| `Summary: <n> packages finished [<total>s]` | end-of-build summary line |
| `  <n> package failed: <pkg1>, <pkg2>` | (optional) explicit failed-package list in the summary |
| `  <n> package had stderr output: <pkg1>` | (optional) explicit stderr-package list in the summary |

A build log may cover more than one attempt of the same workspace (e.g.
`build_log.txt` and `build_log_run2.txt`) so `reproducibility.py` can compare
the discovered package set across runs.

## 2. Test log (`test_log.txt`)

Output of `colcon test` + `colcon test-result --all`, grouped per package,
optionally per attempt (to capture retries/flakiness).

```
--- <pkg> (attempt <n>) ---
Summary: <total> tests, <errors> errors, <failures> failures, <skipped> skipped
FAILURE: <pkg>.<test_name> (<free-text reason>)
ERROR: <pkg>.<test_name> (<free-text reason>)
```

- `(attempt <n>)` is optional; a bare `--- <pkg> ---` means attempt 1.
- A test name that appears in a `FAILURE:`/`ERROR:` line in one attempt for
  a package and does **not** appear in a later, higher-numbered attempt's
  failure/error lines for the same package is flagged as a **candidate
  flaky test** — two data points, not a confirmed intermittent-failure
  diagnosis.

## 3. Reproducibility inputs

`reproducibility.py` inspects, when present:

- `Dockerfile` — the first `FROM ...` line. A trailing `@sha256:<64 hex>`
  counts as "digest-pinned". A trailing `:tag` with no digest counts as
  "tag-pinned" (weaker — tags can move). No tag/digest at all is
  "unpinned".
- `workspace/src/*/package.xml` — presence is treated as "dependency
  manifest present" (a proxy signal only; it does not by itself prove the
  build is reproducible).
- Two build logs for the same scenario (e.g. `build_log.txt` and
  `build_log_run2.txt`) — if both are supplied, the set of packages
  discovered (`Starting >>> <pkg>` lines) is diff'ed. Identical sets across
  runs is a positive signal; it is still not proof of bit-for-bit
  reproducibility, only of consistent package discovery.
- Nondeterministic-timestamp warning lines (see build log table above) —
  counted, not interpreted.

All of the above are returned as a `signals` dict of raw facts. Nothing in
`reproducibility.py` computes or prints a "reproducible: yes/no" verdict.

## 4. Output artifacts (`ci/report.py`)

- `build_health_report.md` — the four-section markdown report described in
  README.md.
- `findings.csv` — one row per finding, columns:
  `section,category,package,summary,evidence`
  where `section` is one of `confirmed`, `likely`, `unverified`,
  `additional_data_required`.

Both are generated deterministically from the same in-memory findings list,
so re-running the pipeline on unchanged input logs reproduces both files
byte-for-byte.
