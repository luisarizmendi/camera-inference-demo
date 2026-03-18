# image-inference-viewer

Static single-page HTML viewer served by nginx. Displays the camera stream
with live bounding-box overlay from YOLOv11 detections.

## Structure

```
image-inference-viewer/
├── README.md
├── build.sh
└── src/
    ├── Containerfile
    ├── nginx.conf
    └── index.html
```

## How it works

nginx serves `index.html` once. After that the browser makes two independent connections:

1. **WebRTC** → MediaMTX WHEP endpoint (`:8889`) — receives the live video stream.
2. **WebSocket** → rosbridge (`:9099`) — receives detection messages.

The browser composites them using a `<canvas>` element layered over the `<video>` element.
Bounding boxes, class labels, and confidence scores are drawn on the canvas every animation
frame using the latest detections received.

The overlay correctly handles `object-fit: contain` letterboxing — boxes stay
aligned with the video content even when the video is pillarboxed or letterboxed.

nginx runs rootless (as `nobody`). All temp/cache paths are under `/tmp`
via a fully custom `nginx.conf`.

## Build

```bash
cd image-inference-viewer
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
```

## Environment variables

None — all connection settings are entered in the browser UI at runtime.

## Run (standalone)

```bash
podman run --rm -p 8080:8080 \
  quay.io/luisarizmendi/image-inference-viewer:latest
```

Open `http://<host-ip>:8080` in any browser on the network.

## Browser UI

In the connection sidebar:

| Field                | Example                   | Description |
|----------------------|---------------------------|-------------|
| MediaMTX host        | `192.168.1.41`            | IP of the host running camera-gateway-rtsp |
| MediaMTX WebRTC port | `8889`                    | WebRTC WHEP port |
| Stream name          | `stream`                  | Matches `RTSP_NAME` in camera-gateway-rtsp |
| rosbridge WebSocket  | `ws://192.168.1.41:9099`  | rosbridge server address |

The host fields are auto-filled from the hostname the page was served from.

Click **Connect** to start. The video and detection overlay activate independently —
the overlay starts as soon as the first detection message arrives.

## Detection overlay behaviour

- Each class gets a consistent colour derived from its name.
- Labels show class name and confidence percentage.
- When no detections arrive for `DETECTION_TTL` seconds (configured in `ros2-inference`),
  the inference node publishes an empty array and the overlay clears automatically.
