cmake_minimum_required(VERSION 3.8)
project(sensor_fusion_utils)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
# NOTE: pcl_fusion_extras is deliberately not a real, resolvable rosdep key
# in this sample workspace -- it is the synthetic missing dependency used
# by data/generate_logs.py's "broken" scenario. A real workspace would
# either vendor this dependency or drop it.
find_package(pcl_fusion_extras REQUIRED)

add_library(${PROJECT_NAME} src/sensor_fusion_utils.cpp)
ament_target_dependencies(${PROJECT_NAME} rclcpp sensor_msgs pcl_fusion_extras)

install(TARGETS ${PROJECT_NAME}
  DESTINATION lib/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
