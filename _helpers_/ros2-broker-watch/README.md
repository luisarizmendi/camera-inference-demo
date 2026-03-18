# ros2-broker-watch

Optional monitoring service. Subscribes to ROS2 topics and publishes health diagnostics on `/broker/camera_status` as `diagnostic_msgs/DiagnosticArray`.

This container is not in the critical path. Run it if you want visibility into detection rates and topic liveness without touching the main pipeline.

## Structure

```
ros2-broker-watch/
├── README.md
└── src/
    ├── Containerfile
    ├── entrypoint.sh
    └── ros2_pkg/
        ├── package.xml
        ├── setup.cfg
        ├── setup.py
        ├── resource/
        │   └── image_broker
        └── image_broker/
            ├── __init__.py
            └── image_broker_node.py
```

## How it works

Built on `ros:kilted-ros-base`. The `image_broker` node subscribes to the topics listed in `CAMERA_TOPICS`, periodically evaluates their health, and publishes a `DiagnosticArray` on `/broker/camera_status`. Optionally it re-publishes received messages on `/broker/<original_topic>`.

## Build

No standalone `build.sh` here. Use the root `build-all.sh` or build manually:

```bash
podman build -t ros2-broker-watch:latest _helpers_/ros2-broker-watch/src/
```

## Environment variables

| Variable                | Default        | Description |
|-------------------------|----------------|-------------|
| `BROKER_NODE_NAME`      | `image_broker` | ROS2 node name |
| `CAMERA_TOPICS`         | _(empty)_      | Comma-separated topics to monitor |
| `HEALTH_CHECK_INTERVAL` | `5`            | Seconds between health evaluations |
| `STALE_TIMEOUT`         | `10`           | Seconds without messages before STALE |
| `REPUBLISH`             | `false`        | Re-publish on `/broker/<topic>` |
| `QOS_DEPTH`             | `5`            | QoS history depth |
| `VERBOSE`               | `false`        | Log every received message |
| `ROS_DOMAIN_ID`         | `0`            | ROS2 DDS domain ID |

## Run (standalone)

```bash
podman run --rm --network host \
  -e CAMERA_TOPICS="/detections" \
  -e STALE_TIMEOUT="5" \
  -v /dev/shm:/dev/shm \
  ros2-broker-watch:latest
```

## Diagnostics

```bash
podman exec -it <broker_container> /bin/bash
source /opt/ros/kilted/setup.bash
ros2 topic echo /broker/camera_status
```

Each entry in the `DiagnosticArray` reports:

| Field           | Description |
|-----------------|-------------|
| `level`         | `0` = OK, `2` = STALE |
| `total_frames`  | Messages received since startup |
| `fps_estimate`  | Estimated messages/s over the last 2 s |
| `last_seen_ago` | Time since the last message |
