# Running the stack

This directory contains two ways to run the camera inference stack:

- **`compose.yml`** — run everything with a single `podman compose` command. Best for development and quick testing.
- **`quadlets/`** — run each container as a native systemd service via Podman quadlets. Best for production deployments and boot-persistent setups.

---

## Before you start

### 1. Set your host LAN IP

Both run methods need to know the LAN IP of the machine running the stack, so WebRTC ICE candidates and the RTSP pull URL point to the right address. Replace `192.168.1.41` in the examples below with your actual IP.

Find your IP:
```bash
ip -4 addr show | grep -oP '(?<=inet )\d+\.\d+\.\d+\.\d+' | grep -v 127
```

### 2. Check your camera device

The default camera device is `/dev/video0`. Verify yours:
```bash
v4l2-ctl --list-devices
# or
ls /dev/video*
```

---

## Option A — Podman Compose

### Requirements

- `podman-compose` installed (`dnf install podman-compose` or `pip install podman-compose`)

### Configure

Open `compose.yml` and update the two values marked with `########`:

```yaml
# In the ros2-inference service:
RTSP_URL: "rtsp://<YOUR_HOST_IP>:8554/stream"

# In the camera-gateway-rtsp service (uncomment):
# MTX_WEBRTCADDITIONALHOSTS: "<YOUR_HOST_IP>"
```

Also update the camera device if needed (default is `/dev/video0`):
```yaml
devices:
  - /dev/video0
```

### Start the stack

```bash
cd _run_
podman compose up -d
```

### Check status

```bash
podman compose ps
podman compose logs -f               # all services
podman compose logs -f ros2-inference  # single service
```

### Stop the stack

```bash
podman compose down
```

### GPU inference

Uncomment the `devices` block in the `ros2-inference` service section of `compose.yml`:

```yaml
ros2-inference:
  ...
  devices:
    - nvidia.com/gpu=all
  environment:
    DEVICE: "cuda"
```

### Service summary

| Service | Ports | Notes |
|---------|-------|-------|
| `camera-gateway-rtsp` | 8554 (RTSP), 8888 (HLS), 8889 (WebRTC), 8189/udp (ICE) | Uses `network_mode: host` |
| `ros2-inference` | — | Uses `network_mode: host`; RTSP pull + DDS |
| `ros2-rosbridge` | 9099 (WebSocket) | Uses `network_mode: host`; DDS |
| `image-inference-viewer` | 8080 (HTTP) | Bridge network is fine |

`network_mode: host` is used for the ROS2 containers because DDS multicast does not traverse bridge networks reliably.

---

## Option B — Podman Quadlets (systemd)

Quadlets translate `.container` files into systemd units automatically. Each container becomes a proper systemd service that starts on boot, restarts on failure, and integrates with `journalctl`.

### Requirements

- Podman ≥ 4.4 (quadlet support built-in)
- systemd (standard on Fedora, RHEL, CentOS Stream)

### Configure

Edit the `.container` files in `quadlets/` before installing them. At minimum:

**`camera-gateway-rtsp.container`** — set your LAN IP and video device:
```ini
Environment=MTX_WEBRTCADDITIONALHOSTS=192.168.1.41   # ← your LAN IP
AddDevice=/dev/video0                                 # ← your camera
AddGroup=44                                           # ← GID of 'video' group
```

Find the `video` group GID:
```bash
getent group video | cut -d: -f3
```

**`ros2-inference.container`** — set your LAN IP for the RTSP pull:
```ini
Environment=RTSP_URL=rtsp://192.168.1.41:8554/stream  # ← your LAN IP
```

### Install — rootless (user session)

Rootless quadlets run under your user session and do not require root. They start automatically when you log in (or when the system boots if lingering is enabled).

```bash
# Create the quadlet directory
mkdir -p ~/.config/containers/systemd/

# Copy all quadlet files
cp quadlets/*.container quadlets/*.network ~/.config/containers/systemd/

# Reload systemd so it picks up the new units
systemctl --user daemon-reload

# Verify that systemd generated the units correctly
systemctl --user list-units 'camera-*' 'ros2-*' 'image-*'
```

Start the services:
```bash
systemctl --user start camera-gateway-rtsp.service
systemctl --user start ros2-inference.service
systemctl --user start ros2-rosbridge.service
systemctl --user start image-inference-viewer.service
```

Enable boot persistence (requires lingering to be active):
```bash
# Enable lingering so your user services survive after logout
loginctl enable-linger $USER

# Enable all services to start at boot
systemctl --user enable camera-gateway-rtsp.service
systemctl --user enable ros2-inference.service
systemctl --user enable ros2-rosbridge.service
systemctl --user enable image-inference-viewer.service
```

### Install — system-wide (root)

System-wide quadlets run as root and start at boot without lingering.

```bash
# Copy all quadlet files
sudo cp quadlets/*.container quadlets/*.network /etc/containers/systemd/

# Reload systemd
sudo systemctl daemon-reload

# Start services
sudo systemctl start camera-gateway-rtsp.service
sudo systemctl start ros2-inference.service
sudo systemctl start ros2-rosbridge.service
sudo systemctl start image-inference-viewer.service

# Enable at boot
sudo systemctl enable camera-gateway-rtsp.service
sudo systemctl enable ros2-inference.service
sudo systemctl enable ros2-rosbridge.service
sudo systemctl enable image-inference-viewer.service
```

### Check status

```bash
# Rootless
systemctl --user status camera-gateway-rtsp.service
journalctl --user -u ros2-inference.service -f

# System-wide
systemctl status camera-gateway-rtsp.service
journalctl -u ros2-inference.service -f
```

### Stop and remove

```bash
# Rootless
systemctl --user stop camera-gateway-rtsp.service ros2-inference.service \
  ros2-rosbridge.service image-inference-viewer.service

# To fully uninstall, remove the files and reload:
rm ~/.config/containers/systemd/camera-gateway-rtsp.container \
   ~/.config/containers/systemd/ros2-inference.container \
   ~/.config/containers/systemd/ros2-rosbridge.container \
   ~/.config/containers/systemd/image-inference-viewer.container \
   ~/.config/containers/systemd/camera-inference.network
systemctl --user daemon-reload
```

### GPU inference with quadlets

In `ros2-inference.container`, uncomment:
```ini
AddDevice=nvidia.com/gpu=all
SecurityLabelDisable=true
Environment=DEVICE=cuda
```

Then reload and restart:
```bash
systemctl --user daemon-reload
systemctl --user restart ros2-inference.service
```

### How quadlets work

Podman's quadlet generator reads `.container` and `.network` files from
`~/.config/containers/systemd/` (rootless) or `/etc/containers/systemd/`
(system) and synthesises full systemd unit files under `/run/systemd/generator/`.
You never write the `[Service]` section by hand — quadlet translates
`[Container]` directives like `Image=`, `Network=`, `Environment=`, and
`PublishPort=` into the appropriate `podman run` arguments.

To inspect the generated unit:
```bash
systemctl --user cat camera-gateway-rtsp.service
```

---

## Open the viewer

Once all services are running, open:

```
http://<host-ip>:8080
```

In the connection sidebar, fill in:

| Field | Value |
|-------|-------|
| MediaMTX host | `<host-ip>` |
| MediaMTX WebRTC port | `8889` |
| Stream name | `stream` |
| rosbridge WebSocket | `ws://<host-ip>:9099` |

The host fields are pre-filled from the page hostname when the viewer is opened from a browser on the same machine. Click **Connect** — video and detection overlay activate independently as each connection is established.

---

## Firewall

If you are running firewalld, open the required ports:

```bash
# RTSP + HLS + WebRTC
sudo firewall-cmd --add-port=8554/tcp --permanent
sudo firewall-cmd --add-port=8888/tcp --permanent
sudo firewall-cmd --add-port=8889/tcp --permanent
sudo firewall-cmd --add-port=8189/udp --permanent
# rosbridge WebSocket
sudo firewall-cmd --add-port=9099/tcp --permanent
# Viewer
sudo firewall-cmd --add-port=8080/tcp --permanent

sudo firewall-cmd --reload
```
