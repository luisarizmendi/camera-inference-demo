"""
Image Streamer Node

Subscribes to a ROS2 image topic (sensor_msgs/Image) and forwards frames
to MediaMTX via FFmpeg (rawvideo pipe -> RTSP), making them available as:
  - RTSP   -> rtsp://<RTSP_HOST>:<RTSP_PORT>/<RTSP_NAME>
  - HLS    -> http://<RTSP_HOST>:<RTSP_PORT_HLS>/<RTSP_NAME>
  - WebRTC -> http://<RTSP_HOST>:<RTSP_PORT_WEBRTC>/<RTSP_NAME>

The node writes raw frames into a pipe to an FFmpeg subprocess which pushes
the encoded stream to the local MediaMTX instance.

Environment variables
---------------------
ROS_TOPIC           ROS2 image topic to subscribe to
                    (default: /camera/image_raw)
RTSP_HOST           Host where MediaMTX is running (default: 127.0.0.1)
RTSP_PORT           RTSP port of MediaMTX (default: 8554)
                    Change this when another MediaMTX instance is already
                    using the default port on the same host.
RTSP_NAME           RTSP path name (default: stream)
VIDEO_CODEC         FFmpeg video codec (default: libx264)
VIDEO_BITRATE       Output stream bitrate (default: 1000k)
VIDEO_PRESET        x264 preset (default: ultrafast)
VIDEO_TUNE          x264 tune (default: zerolatency)
TARGET_FPS          Output stream frame rate (default: 30)
IMAGE_WIDTH         Resize width before encoding; 0 = no resize (default: 0)
IMAGE_HEIGHT        Resize height before encoding; 0 = no resize (default: 0)
QOS_DEPTH           Subscriber QoS history depth (default: 1)
VERBOSE             Log every processed frame: 1/true/yes (default: false)
ROS_DOMAIN_ID       ROS2 DDS domain ID (default: 0)
"""

import os
import subprocess
import threading
from typing import Optional

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
from sensor_msgs.msg import Image
from cv_bridge import CvBridge


# ── Helpers ───────────────────────────────────────────────────────────────────

def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except ValueError:
        return default


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key, "").lower()
    return val in ("1", "true", "yes") if val else default


def _h264_compat_flags() -> list[str]:
    """Extra flags required for H264 WebRTC browser compatibility."""
    return [
        "-pix_fmt",   "yuv420p",
        "-profile:v", "baseline",
        "-level:v",   "4.2",
        "-bf",        "0",   # no B-frames (WebRTC requirement)
    ]


# ── Node ──────────────────────────────────────────────────────────────────────

class ImageStreamerNode(Node):

    def __init__(self):
        super().__init__("image_streamer")

        # ── Config ────────────────────────────────────────────────────────────
        self.ros_topic: str  = os.environ.get("ROS_TOPIC",      "/camera/image_raw")
        self.rtsp_host: str  = os.environ.get("RTSP_HOST",      "127.0.0.1")
        self.rtsp_port: str  = os.environ.get("RTSP_PORT",      "8554")
        self.rtsp_name: str  = os.environ.get("RTSP_NAME",      "stream")
        self.codec: str      = os.environ.get("VIDEO_CODEC",    "libx264")
        self.bitrate: str    = os.environ.get("VIDEO_BITRATE",  "1000k")
        self.preset: str     = os.environ.get("VIDEO_PRESET",   "ultrafast")
        self.tune: str       = os.environ.get("VIDEO_TUNE",     "zerolatency")
        self.target_fps: int = _env_int("TARGET_FPS",   30)
        self.img_width: int  = _env_int("IMAGE_WIDTH",  0)
        self.img_height: int = _env_int("IMAGE_HEIGHT", 0)
        self.qos_depth: int  = _env_int("QOS_DEPTH",   1)
        self.verbose: bool   = _env_bool("VERBOSE")

        # HLS/WebRTC ports are only used for the startup log message;
        # MediaMTX is already configured by entrypoint.sh before this node starts.
        rtsp_port_hls    = os.environ.get("RTSP_PORT_HLS",    "8888")
        rtsp_port_webrtc = os.environ.get("RTSP_PORT_WEBRTC", "8889")

        self.rtsp_url = f"rtsp://{self.rtsp_host}:{self.rtsp_port}/{self.rtsp_name}"

        # ── State ─────────────────────────────────────────────────────────────
        self._bridge = CvBridge()
        self._ffmpeg: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._frame_count = 0
        self._width: Optional[int] = None
        self._height: Optional[int] = None

        # ── QoS ───────────────────────────────────────────────────────────────
        qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=self.qos_depth,
        )

        self._sub = self.create_subscription(
            Image,
            self.ros_topic,
            self._on_image,
            qos,
        )

        self.get_logger().info(
            f"\n  ROS2 topic : {self.ros_topic}"
            f"\n  RTSP URL   : {self.rtsp_url}"
            f"\n  HLS        : http://{self.rtsp_host}:{rtsp_port_hls}/{self.rtsp_name}"
            f"\n  WebRTC     : http://{self.rtsp_host}:{rtsp_port_webrtc}/{self.rtsp_name}"
            f"\n  Codec      : {self.codec}  bitrate={self.bitrate}"
            f"\n  Target FPS : {self.target_fps}"
            f"\n  Resize     : {self.img_width}x{self.img_height} (0 = disabled)"
        )

    # ── ROS2 callback ─────────────────────────────────────────────────────────

    def _on_image(self, msg: Image):
        try:
            frame: np.ndarray = self._bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        except Exception as exc:
            self.get_logger().error(f"Failed to convert image: {exc}")
            return

        if self.img_width > 0 and self.img_height > 0:
            frame = cv2.resize(frame, (self.img_width, self.img_height))

        h, w = frame.shape[:2]

        with self._lock:
            if self._ffmpeg is None or self._width != w or self._height != h:
                self._restart_ffmpeg(w, h)

            if self._ffmpeg is None or self._ffmpeg.poll() is not None:
                self.get_logger().warning("FFmpeg is not running, dropping frame.")
                return

            try:
                self._ffmpeg.stdin.write(frame.tobytes())
            except BrokenPipeError:
                self.get_logger().warning("Broken pipe to FFmpeg, will restart on next frame.")
                self._ffmpeg = None
                return

        self._frame_count += 1
        if self.verbose:
            self.get_logger().info(f"Frame #{self._frame_count} sent to FFmpeg")

    # ── FFmpeg management ─────────────────────────────────────────────────────

    def _build_ffmpeg_cmd(self, width: int, height: int) -> list[str]:
        cmd = [
            "ffmpeg",
            "-loglevel", "warning",
            "-f",            "rawvideo",
            "-pixel_format", "bgr24",
            "-video_size",   f"{width}x{height}",
            "-framerate",    str(self.target_fps),
            "-i",            "pipe:0",
            "-c:v",          self.codec,
        ]

        if self.codec == "libx264":
            cmd += _h264_compat_flags()
            cmd += ["-preset", self.preset, "-tune", self.tune]

        cmd += [
            "-b:v", self.bitrate,
            "-an",          # no audio
            "-f",  "rtsp",
            self.rtsp_url,
        ]
        return cmd

    def _restart_ffmpeg(self, width: int, height: int):
        """Terminate any existing FFmpeg process and start a fresh one."""
        if self._ffmpeg is not None:
            try:
                self._ffmpeg.stdin.close()
                self._ffmpeg.wait(timeout=3)
            except Exception:
                self._ffmpeg.kill()

        self._width  = width
        self._height = height

        cmd = self._build_ffmpeg_cmd(width, height)
        self.get_logger().info(
            f"Starting FFmpeg {width}x{height} -> {self.rtsp_url}\n"
            f"  cmd: {' '.join(cmd)}"
        )

        self._ffmpeg = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        threading.Thread(
            target=self._log_ffmpeg_stderr,
            args=(self._ffmpeg,),
            daemon=True,
        ).start()

    def _log_ffmpeg_stderr(self, proc: subprocess.Popen):
        for line in proc.stderr:
            decoded = line.decode(errors="replace").rstrip()
            if decoded:
                self.get_logger().warning(f"[ffmpeg] {decoded}")

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def destroy_node(self):
        with self._lock:
            if self._ffmpeg is not None:
                try:
                    self._ffmpeg.stdin.close()
                    self._ffmpeg.wait(timeout=3)
                except Exception:
                    self._ffmpeg.kill()
        super().destroy_node()


# ── Entry point ───────────────────────────────────────────────────────────────

def main(args=None):
    rclpy.init(args=args)
    node = ImageStreamerNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
