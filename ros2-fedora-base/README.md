# ros2-fedora-base

Common base image for all ROS2 containerized services.

Built on `fedora:42` and includes:
- ROS2 Kilted via COPR (`tavie/ros2`)
- `ros-kilted-rmw-cyclonedds-cpp` — DDS middleware shared by all services
- Common runtime dependencies (`spdlog`, `lttng-ust`, `numpy`, etc.)
- Development tools (`cmake`, `gcc`, `colcon`, `rosdep`, `flake8`, etc.)
- OpenSSH server with X11 forwarding enabled

## Structure

```
ros2-fedora-base/
├── README.md
└── src/
    └── Containerfile
```

## Build

```bash
cd ros2-fedora-base/src
podman build -t ros2-fedora-base:latest .
```

## Usage in derived images

```dockerfile
FROM ros2-fedora-base:latest
```

The three services that use this base are:
- `ros2-rtsp-bridge`
- `ros2-broker`
- `ros2-image-streamer`
