"""Reproducibility *signals*, not a verdict.

Everything in this module is a heuristic: a fact that correlates with
"this build is more/less likely to reproduce the same way twice", not
proof either way. Nothing here should ever be summarized as
"reproducible: yes/no" -- see README.md Limitations.
"""

import glob
import os
import re

RE_FROM_LINE = re.compile(r"^\s*FROM\s+(\S+)", re.IGNORECASE)
RE_DIGEST_PIN = re.compile(r"@sha256:[0-9a-f]{64}$")
RE_TAG_PIN = re.compile(r":[^@/\s]+$")


def check_dockerfile_pin(dockerfile_path):
    """Inspect the first FROM line of a Dockerfile.

    Returns one of "digest-pinned", "tag-pinned", "unpinned", or
    "not-found" (no Dockerfile / no FROM line at that path).
    """
    if not dockerfile_path or not os.path.isfile(dockerfile_path):
        return "not-found", None
    with open(dockerfile_path, "r", encoding="utf-8") as fh:
        for line in fh:
            m = RE_FROM_LINE.match(line)
            if m:
                image_ref = m.group(1)
                if RE_DIGEST_PIN.search(image_ref):
                    return "digest-pinned", image_ref
                if RE_TAG_PIN.search(image_ref):
                    return "tag-pinned", image_ref
                return "unpinned", image_ref
    return "not-found", None


def check_dependency_manifests(workspace_src_dir):
    """Look for package.xml files under a workspace src/ directory.

    This is a presence check only -- a proxy signal that packages declare
    their dependencies somewhere. It does NOT verify the manifests are
    complete, correct, or that rosdep would resolve cleanly.
    """
    if not workspace_src_dir or not os.path.isdir(workspace_src_dir):
        return {"found": False, "count": 0, "paths": []}
    paths = sorted(glob.glob(os.path.join(workspace_src_dir, "*", "package.xml")))
    return {"found": len(paths) > 0, "count": len(paths), "paths": paths}


def compare_package_sets(build_result_run1, build_result_run2):
    """Compare packages_discovered between two parsed build logs.

    Returns None if either run is missing (comparison not possible), else
    a dict describing whether the discovered package sets matched.
    """
    if build_result_run1 is None or build_result_run2 is None:
        return None
    set1 = set(build_result_run1.get("packages_discovered", []))
    set2 = set(build_result_run2.get("packages_discovered", []))
    return {
        "run1_only": sorted(set1 - set2),
        "run2_only": sorted(set2 - set1),
        "identical": set1 == set2,
        "run1_count": len(set1),
        "run2_count": len(set2),
    }


def collect_signals(
    dockerfile_path=None,
    workspace_src_dir=None,
    build_result_run1=None,
    build_result_run2=None,
):
    """Assemble all reproducibility signals into one dict of raw facts.

    Callers (report.py) decide how/whether to phrase these as hedged
    findings. This function performs no interpretation itself.
    """
    pin_status, pinned_image_ref = check_dockerfile_pin(dockerfile_path)
    manifest_info = check_dependency_manifests(workspace_src_dir)
    package_set_comparison = compare_package_sets(build_result_run1, build_result_run2)

    nondet_warnings = []
    if build_result_run1:
        nondet_warnings.extend(
            build_result_run1.get("nondeterministic_timestamp_warnings", [])
        )

    return {
        "dockerfile_pin_status": pin_status,
        "dockerfile_pinned_image_ref": pinned_image_ref,
        "dependency_manifest": manifest_info,
        "package_set_comparison": package_set_comparison,
        "nondeterministic_timestamp_warning_count": len(nondet_warnings),
        "nondeterministic_timestamp_warning_packages": nondet_warnings,
    }
