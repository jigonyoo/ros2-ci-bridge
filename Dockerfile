# ROS2 CI & Build-Health Bridge -- workspace build image.
#
# This is a genuine, runnable colcon build/test recipe: it is what
# .github/workflows/ci.yml actually invokes in CI. It is intentionally
# separate from the offline Python analysis layer in ci/, which never
# needs ROS2 or Docker installed to run -- see README.md.
#
# Base image is tag-pinned below. For a stronger reproducibility
# guarantee, pin to a specific digest instead, e.g.:
#   FROM ros:humble-ros-base@sha256:<64-hex-digest>
# Tags can be repointed by upstream; a digest cannot. Resolve the current
# digest with:
#   docker pull ros:humble-ros-base && docker inspect --format='{{index .RepoDigests 0}}' ros:humble-ros-base
FROM ros:humble-ros-base

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3-colcon-common-extensions \
        python3-rosdep \
        python3-pytest \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY workspace/src ./src

# rosdep install is expected to fail closed on the synthetic
# pcl_fusion_extras dependency declared in
# workspace/src/sensor_fusion_utils/package.xml -- that failure is the
# realistic analogue of the "missing dependency" scenario this repo's
# analysis layer is built to parse. A real workspace would either vendor
# that dependency or remove the declaration.
RUN rosdep update \
    && rosdep install --from-paths src --ignore-src -r -y || true

# Build + test. Logs are written to /workspace/build_log.txt and
# /workspace/test_log.txt so a downstream CI step can copy them out and
# feed them to `python3 -m ci.run` (see .github/workflows/ci.yml).
RUN source /opt/ros/humble/setup.bash \
    && colcon build --event-handlers console_direct+ 2>&1 | tee build_log.txt

RUN source /opt/ros/humble/setup.bash \
    && (colcon test 2>&1 | tee test_log_raw.txt; true) \
    && colcon test-result --all --verbose 2>&1 | tee test_log.txt

CMD ["/bin/bash"]
