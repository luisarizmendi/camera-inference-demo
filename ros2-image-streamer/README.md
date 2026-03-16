# ros2-image-streamer

Servicio contenerizado que **suscribe a un topic ROS2 de imágenes** y las retransmite vía MediaMTX como:

- **RTSP**   → `rtsp://<host>:8554/<RTSP_NAME>`
- **HLS**    → `http://<host>:8888/<RTSP_NAME>`
- **WebRTC** → `http://<host>:8889/<RTSP_NAME>`

Construido sobre `ros2-fedora-base:latest`.

---

## Estructura

```
ros2-image-streamer/
├── README.md
└── src/
    ├── Containerfile
    ├── entrypoint.sh
    ├── mediamtx.yml
    └── ros2_pkg/
        ├── package.xml
        ├── setup.py
        ├── resource/
        │   └── image_streamer
        └── image_streamer/
            ├── __init__.py
            └── image_streamer_node.py
```

---

## Variables de entorno

| Variable        | Por defecto         | Descripción |
|-----------------|---------------------|-------------|
| `ROS_TOPIC`     | `/camera/image_raw` | Topic ROS2 del que consumir imágenes |
| `RTSP_HOST`     | `127.0.0.1`         | Host al que publicar en MediaMTX |
| `RTSP_PORT`     | `8554`              | Puerto RTSP |
| `RTSP_NAME`     | `stream`            | Path del stream |
| `VIDEO_CODEC`   | `libx264`           | Codec FFmpeg |
| `VIDEO_BITRATE` | `1000k`             | Bitrate de salida |
| `VIDEO_PRESET`  | `ultrafast`         | Preset x264 |
| `VIDEO_TUNE`    | `zerolatency`       | Tune x264 |
| `TARGET_FPS`    | `30`                | FPS del stream de salida |
| `IMAGE_WIDTH`   | `0`                 | Redimensionado; `0` = sin cambio |
| `IMAGE_HEIGHT`  | `0`                 | Redimensionado; `0` = sin cambio |
| `QOS_DEPTH`     | `1`                 | Profundidad QoS del subscriber |
| `VERBOSE`       | `false`             | Log por frame |
| `ROS_DOMAIN_ID` | `0`                 | ID de dominio DDS |

Para WebRTC desde la red local añade: `-e MTX_WEBRTCADDITIONALHOSTS=<IP_LAN>`

---

## Construir

```bash
cd ros2-fedora-base/src    && podman build -t ros2-fedora-base:latest .
cd ros2-image-streamer/src && podman build -t ros2-image-streamer:latest .
```

## Ejecutar

```bash
podman run --rm --network host \
  -e ROS_TOPIC="/camera/front/image_raw" \
  -e RTSP_NAME="front" \
  -e MTX_WEBRTCADDITIONALHOSTS="192.168.1.41" \
  ros2-image-streamer:latest
```

| Protocolo | URL |
|-----------|-----|
| RTSP      | `rtsp://localhost:8554/front` |
| HLS/web   | `http://localhost:8888/front` |
| WebRTC    | `http://localhost:8889/front` |
