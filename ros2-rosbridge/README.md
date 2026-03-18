# ros2-rosbridge

Exposes ROS2 topics as a WebSocket server using `rosbridge_suite`. The browser viewer connects here to receive detection messages without needing a ROS2 installation on the client.

## Structure

```
ros2-rosbridge/
├── README.md
├── build.sh
└── src/
    ├── Containerfile
    └── entrypoint.sh
```

## How it works

Built on the official `ros:kilted` image. `rosbridge_server` and `rosbridge_library` are installed from the official ROS2 apt repository for Ubuntu Noble. The entrypoint launches `rosbridge_websocket` on `ROSBRIDGE_PORT`.

## Build

```bash
cd ros2-rosbridge
./build.sh
```

| Flag | Description |
|------|-------------|
| `--no-push` | Build locally, skip push |
| `--cross` | Also cross-build for the opposite arch |
| `--registry <reg>` | Override default registry (`quay.io/luisarizmendi`) |
| `--force-manifest-reset` | Recreate the remote multi-arch manifest from scratch |

```bash
# Local-only build
./build.sh --no-push

# Cross-build amd64 + arm64
./build.sh --cross
```

## Environment variables

| Variable         | Default | Description |
|------------------|---------|-------------|
| `ROSBRIDGE_PORT` | `9099`  | WebSocket server port |
| `ROS_DOMAIN_ID`  | `0`     | ROS2 DDS domain ID, must match `ros2-inference` |

## Run (standalone)

```bash
podman run --rm --network host \
  -e ROSBRIDGE_PORT=9099 \
  -v /dev/shm:/dev/shm \
  quay.io/luisarizmendi/ros2-rosbridge:latest
```

## Browser client protocol

The viewer connects using the native WebSocket API and speaks the rosbridge v2 JSON protocol, no roslibjs library required.

Subscribe example:
```json
{ "op": "subscribe", "topic": "/detections", "type": "vision_msgs/msg/Detection2DArray" }
```

Incoming message format:
```json
{ "op": "publish", "topic": "/detections", "msg": { "detections": [...] } }
```

## Troubleshooting

If the browser cannot connect, check:
1. `ros2-inference` and `ros2-rosbridge` are both running with `--network host`.
2. Both have the same `ROS_DOMAIN_ID`.
3. Port 9099 is reachable from the browser (check your firewall).
4. The inference node is actually publishing:
   ```bash
   podman exec -it <rosbridge_container> /bin/bash
   source /opt/ros/kilted/setup.bash
   ros2 topic echo /detections
   ```
