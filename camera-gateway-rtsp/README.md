# camera-gateway-rtsp

Captures a USB webcam (or loops video files as fallback) and broadcasts it via MediaMTX as RTSP, WebRTC and HLS.

This is the entry point for the whole pipeline: the browser gets the video directly via WebRTC (~150 ms latency), and the inference service pulls the same stream over RTSP.

## Structure

```
camera-gateway-rtsp/
├── README.md
├── build.sh
└── src/
    ├── Containerfile
    ├── entrypoint.sh
    ├── mediamtx.yml
    └── stream.py
```

## How it works

`entrypoint.sh` starts MediaMTX, waits for the RTSP port to be ready, then runs `stream.py`. The script probes `/dev/video*` devices, enumerates all supported format/resolution/fps combinations via `v4l2-ctl --list-formats-ext`, and selects the best mode: it targets 30 fps (configurable via `CAM_TARGET_FPS`), picks the closest available fps, and among equally-close options prefers the largest resolution. If no camera is found it falls back to looping video files from `VID_DIR`.

The base image is Fedora latest with FFmpeg from RPM Fusion.

## Build

```bash
cd camera-gateway-rtsp
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

# Build and push to a custom registry
./build.sh --registry ghcr.io/myuser

# Cross-build amd64 + arm64 from an x86_64 host
./build.sh --cross
```

Or build manually:

```bash
podman build -t camera-gateway-rtsp:latest src/
```

## Environment variables

### Stream output

| Variable    | Default     | Description |
|-------------|-------------|-------------|
| `RTSP_HOST` | `127.0.0.1` | MediaMTX host for FFmpeg to push to |
| `RTSP_PORT` | `8554`      | RTSP port |
| `RTSP_NAME` | `stream`    | Stream path (`rtsp://host:8554/stream`) |

### Webcam options

| Variable            | Default       | Description |
|---------------------|---------------|-------------|
| `CAM_TARGET_FPS`    | `30`          | Desired capture framerate. The script selects the closest fps the camera supports, preferring larger resolutions on a tie. |
| `CAM_FRAMERATE`     | _(auto)_      | Override: force a specific framerate, skipping auto-selection |
| `CAM_RESOLUTION`    | _(auto)_      | Override: force a specific resolution (e.g. `1280x720`), skipping auto-selection |
| `CAM_VIDEO_CODEC`   | `libx264`     | FFmpeg video codec |
| `CAM_VIDEO_BITRATE` | `600k`        | Video bitrate |
| `CAM_AUDIO_CODEC`   | `libopus`     | Audio codec |
| `CAM_AUDIO_BITRATE` | `64k`         | Audio bitrate |
| `CAM_PRESET`        | `ultrafast`   | x264 preset |
| `CAM_TUNE`          | `zerolatency` | x264 tune |
| `CAM_RTBUFSIZE`     | `100M`        | FFmpeg input ring-buffer size |

### Video file fallback

| Variable            | Default   | Description |
|---------------------|-----------|-------------|
| `VID_DIR`           | `/videos` | Directory to scan for video files |
| `VID_VIDEO_CODEC`   | `libx264` | Video codec for file streaming |
| `VID_VIDEO_BITRATE` | `600k`    | Bitrate for file streaming |
| `VID_PRESET`        | `fast`    | x264 preset for file streaming |

### Misc

| Variable               | Default | Description |
|------------------------|---------|-------------|
| `DEVICE_PROBE_TIMEOUT` | `5`     | Seconds to wait when probing a camera device |

## Ports

| Port     | Protocol | Description |
|----------|----------|-------------|
| 8554     | RTSP     | Camera stream, pulled by ros2-inference |
| 8888     | HLS      | Web player |
| 8889     | WebRTC   | Browser viewer (WHEP endpoint) |
| 8189/udp | ICE      | WebRTC media transport |

## Camera device permissions

The container needs read/write access to the camera device (e.g. `/dev/video0`). The user running the container must be a member of the `video` group:

```bash
sudo usermod -aG video $USER
# Log out and back in for the group change to take effect, then verify:
id $USER | grep video
```

Pass the device and group when running the container:

```bash
--device /dev/video0 \
--group-add $(getent group video | cut -d: -f3)
```

## Run (standalone)

```bash
podman run --rm \
  --network host \
  --device /dev/video0 \
  --security-opt label=disable \
  --group-add $(getent group video | cut -d: -f3) \
  -e MTX_WEBRTCADDITIONALHOSTS=192.168.1.41 \
  -e CAM_TARGET_FPS=30 \
  quay.io/luisarizmendi/camera-gateway-rtsp:latest
```

Set `MTX_WEBRTCADDITIONALHOSTS` to your host LAN IP so browsers on other machines receive usable WebRTC ICE candidates.
