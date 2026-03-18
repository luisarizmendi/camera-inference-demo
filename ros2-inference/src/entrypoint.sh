#!/bin/bash
set -e

export ROS_HOME=/tmp/ros_home

# Source ROS2
source /opt/ros/kilted/setup.bash
source /ros2_ws/install/setup.bash

exec ros2 run inference_node inference_node
