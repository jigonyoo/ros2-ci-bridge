from setuptools import find_packages, setup

package_name = "diagnostics_reporter"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Jigon Yoo",
    maintainer_email="jigondaniel1224@gmail.com",
    description=(
        "Sample diagnostics-reporting package used as a realistic CI target "
        "for the ROS2 CI & Build-Health Bridge portfolio sample."
    ),
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [],
    },
)
