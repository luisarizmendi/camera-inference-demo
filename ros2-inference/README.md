# ros2-inference

Pulls frames directly from an RTSP stream, runs YOLOv11 object detection,
and publishes results as `vision_msgs/Detection2DArray` on `/detections`.

Video never enters ROS2 — only the tiny detection metadata is transported
through the ROS2 graph. The browser receives video via WebRTC directly from
MediaMTX and detections via rosbridge WebSocket from this node.

## Structure

```
ros2-inference/
├── README.md
├── build.sh
└── src/
    ├── Containerfile
    ├── entrypoint.sh
    └── ros2_pkg/
        ├── package.xml
        ├── setup.cfg
        ├── setup.py
        ├── resource/
        │   └── inference_node
        └── inference_node/
            ├── __init__.py
            └── inference_node.py
```

## How it works

The image is built in three stages:

1. **python-builder** — NVIDIA CUDA 12.6 base, installs PyTorch + Ultralytics and downloads `yolo11n.pt` weights at build time so the container starts without network access.
2. **ros-builder** — official `ros:kilted-ros-base` image, builds the `inference_node` ROS2 package with `colcon`.
3. **Final runtime** — CUDA base again, installs the ROS2 runtime from the official ROS apt repo, copies Python packages and the built ROS2 workspace from the previous stages.

The inference node opens the RTSP stream with OpenCV (`CAP_FFMPEG`, buffer size = 1). On each cycle it **drains the capture buffer** with `grab()` before calling `retrieve()` — ensuring it always operates on the most recent frame regardless of the stream FPS vs `TARGET_FPS` ratio. No frame accumulation, no stale detections.

After each publish, a TTL timer fires every 200 ms. If `DETECTION_TTL` seconds pass without a new result, an empty `Detection2DArray` is sent to clear the browser overlay automatically.

## Build

```bash
cd ros2-inference
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

# Cross-build both architectures
./build.sh --cross

# Push to a different registry
./build.sh --registry ghcr.io/myuser
```

> The build downloads `yolo11n.pt` from GitHub — requires internet access.

## Environment variables

| Variable                | Default                        | Description |
|-------------------------|--------------------------------|-------------|
| `RTSP_URL`              | `rtsp://127.0.0.1:8554/stream` | RTSP stream to pull frames from |
| `DETECTION_TOPIC`       | `/detections`                  | ROS2 topic to publish on |
| `YOLO_MODEL`            | `yolo11n.pt`                   | Model weights filename |
| `CONFIDENCE_THRESHOLD`  | `0.4`                          | Minimum detection confidence (0–1) |
| `INFERENCE_WIDTH`       | `640`                          | Frame width fed to YOLO |
| `INFERENCE_HEIGHT`      | `640`                          | Frame height fed to YOLO |
| `TARGET_FPS`            | `30`                           | Max inference rate; frames between cycles are dropped |
| `DETECTION_TTL`         | `1.0`                          | Seconds after last detection before publishing empty array |
| `DEVICE`                | `auto`                         | `auto`, `cpu`, `cuda`, `cuda:0` |
| `VERBOSE`               | `false`                        | Log every detection |
| `ROS_DOMAIN_ID`         | `0`                            | ROS2 DDS domain ID |

### YOLO model sizes

| Model        | GPU latency | CPU latency | Notes |
|--------------|-------------|-------------|-------|
| `yolo11n.pt` | ~5 ms       | ~100–200 ms | Pre-downloaded at build time |
| `yolo11s.pt` | ~8 ms       | ~200–400 ms | Download or mount at runtime |
| `yolo11m.pt` | ~15 ms      | ~500 ms     | Download or mount at runtime |
| `yolo11l.pt` | ~25 ms      | ~1 s        | Download or mount at runtime |
| `yolo11x.pt` | ~40 ms      | ~2 s        | Download or mount at runtime |

## Run (standalone)

```bash
podman run --rm --network host \
  -e RTSP_URL="rtsp://192.168.1.41:8554/stream" \
  -e DEVICE="auto" \
  -v /dev/shm:/dev/shm \
  quay.io/luisarizmendi/ros2-inference:latest
```

### With NVIDIA GPU

```bash
podman run --rm --network host \
  --security-opt=label=disable \
  --device nvidia.com/gpu=all \
  -e RTSP_URL="rtsp://192.168.1.41:8554/stream" \
  -e DEVICE="cuda" \
  -v /dev/shm:/dev/shm \
  quay.io/luisarizmendi/ros2-inference:latest
```

### Using a custom model

```bash
podman run --rm --network host \
  -v /path/to/my_model.pt:/opt/yolo_models/my_model.pt:ro \
  -e YOLO_MODEL="my_model.pt" \
  -v /dev/shm:/dev/shm \
  quay.io/luisarizmendi/ros2-inference:latest
```

## Detection message format

Topic: `/detections`  
Type: `vision_msgs/msg/Detection2DArray`

Each `Detection2D` contains:
- `bbox.center.position.x/y` — bounding-box centre in original-frame pixels
- `bbox.size_x/size_y` — bounding-box width and height in pixels
- `results[0].hypothesis.class_id` — class label string (e.g. `"person"`)
- `results[0].hypothesis.score` — confidence 0–1
