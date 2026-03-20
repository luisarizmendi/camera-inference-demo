#!/usr/bin/env python3
"""
RTSP streamer: tries USB webcams first, falls back to looping video files.
All configuration via environment variables.

Codec requirements for WebRTC browser compatibility:
  - Video: libx264 with yuv420p, baseline profile, no B-frames
  - Audio: libopus (AAC not supported by WebRTC)
"""

import os
import subprocess
import glob
import sys
import time
import logging
from fractions import Fraction

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ── Environment configuration ────────────────────────────────────────────────
RTSP_HOST       = os.environ.get("RTSP_HOST",       "127.0.0.1")
RTSP_PORT       = os.environ.get("RTSP_PORT",       "8554")
RTSP_NAME       = os.environ.get("RTSP_NAME",       "stream")

# Webcam FFmpeg options
# NOTE: CAM_FRAMERATE and CAM_RESOLUTION intentionally default to "" so that
# the device's native values (discovered via v4l2-ctl) are used as fallback.
# Set these env vars to override the native values.
CAM_RTBUFSIZE     = os.environ.get("CAM_RTBUFSIZE",     "100M")
CAM_VIDEO_CODEC   = os.environ.get("CAM_VIDEO_CODEC",   "libx264")
CAM_AUDIO_CODEC   = os.environ.get("CAM_AUDIO_CODEC",   "libopus")
CAM_VIDEO_BITRATE = os.environ.get("CAM_VIDEO_BITRATE", "600k")
CAM_AUDIO_BITRATE = os.environ.get("CAM_AUDIO_BITRATE", "64k")
CAM_PRESET        = os.environ.get("CAM_PRESET",        "ultrafast")
CAM_TUNE          = os.environ.get("CAM_TUNE",          "zerolatency")
CAM_FRAMERATE     = os.environ.get("CAM_FRAMERATE",     "")   # "" = use native
CAM_RESOLUTION    = os.environ.get("CAM_RESOLUTION",    "")   # "" = use native
CAM_TARGET_FPS    = int(os.environ.get("CAM_TARGET_FPS", "30"))  # desired fps

# Video-file FFmpeg options
VID_VIDEO_CODEC   = os.environ.get("VID_VIDEO_CODEC",   "libx264")
VID_AUDIO_CODEC   = os.environ.get("VID_AUDIO_CODEC",   "libopus")
VID_VIDEO_BITRATE = os.environ.get("VID_VIDEO_BITRATE", "600k")
VID_AUDIO_BITRATE = os.environ.get("VID_AUDIO_BITRATE", "64k")
VID_PRESET        = os.environ.get("VID_PRESET",        "fast")
VID_DIR           = os.environ.get("VID_DIR",           "/videos")

# Misc
DEVICE_PROBE_TIMEOUT = int(os.environ.get("DEVICE_PROBE_TIMEOUT", "5"))
# ─────────────────────────────────────────────────────────────────────────────

# Formats we know how to pass to ffmpeg's -input_format.
# Any format not in this map will be skipped during selection.
_FMT_MAP = {
    "yuyv": "yuyv422",
    "yuyv422": "yuyv422",
    "mjpg": "mjpeg",
    "mjpeg": "mjpeg",
    "h264": "h264",
    "nv12": "nv12",
    "rgb3": "rgb24",
    "rgb24": "rgb24",
}


def rtsp_url() -> str:
    return f"rtsp://{RTSP_HOST}:{RTSP_PORT}/{RTSP_NAME}"


def list_video_devices() -> list[str]:
    return sorted(glob.glob("/dev/video*"))


# ── Format / resolution / fps enumeration ────────────────────────────────────

def _parse_fraction(s: str) -> float:
    """Parse '30/1', '5/1', '30.000' etc. into a float fps value."""
    s = s.strip()
    try:
        if "/" in s:
            return float(Fraction(s))
        return float(s)
    except (ValueError, ZeroDivisionError):
        return 0.0


def _pixel_count(size: str) -> int:
    """'1920x1080' → 2073600, or 0 on parse failure."""
    try:
        w, h = size.lower().split("x")
        return int(w) * int(h)
    except Exception:
        return 0


def enumerate_camera_modes(device: str) -> list[dict]:
    """
    Run ``v4l2-ctl --list-formats-ext`` and return a list of dicts:
        {"fmt": "mjpeg", "size": "1920x1080", "fps": 30.0}

    Only formats present in _FMT_MAP are included (i.e. formats ffmpeg can use).
    The list is *not* sorted here — sorting / selection is done by the caller.
    """
    modes: list[dict] = []
    try:
        result = subprocess.run(
            ["v4l2-ctl", "--device", device, "--list-formats-ext"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            log.warning("v4l2-ctl --list-formats-ext failed for %s", device)
            return modes
    except (subprocess.TimeoutExpired, FileNotFoundError):
        log.warning("v4l2-ctl not available or timed out for %s", device)
        return modes

    current_fmt  = ""
    current_size = ""

    for line in result.stdout.splitlines():
        stripped = line.strip()

        # e.g. "[0]: 'MJPG' (Motion-JPEG, compressed)"
        #   or "[1]: 'YUYV' (YUYV 4:2:2)"
        if stripped.startswith("[") and "'" in stripped:
            try:
                raw = stripped.split("'")[1].strip().lower()
                current_fmt = _FMT_MAP.get(raw, "")
                current_size = ""   # reset size on new format block
            except IndexError:
                current_fmt = ""
            continue

        if not current_fmt:
            continue  # format not usable — skip everything until next format

        # e.g. "Size: Discrete 1920x1080"
        if stripped.startswith("Size:") and "Discrete" in stripped:
            try:
                current_size = stripped.split("Discrete")[1].strip()
            except IndexError:
                current_size = ""
            continue

        if not current_size:
            continue

        # e.g. "Interval: Discrete 0.033s (30.000 fps)"
        #   or "Interval: Discrete 0.200s (5.000 fps)"
        if stripped.startswith("Interval:") and "fps" in stripped:
            try:
                fps_str = stripped.split("(")[1].split("fps")[0].strip()
                fps_val = _parse_fraction(fps_str)
                if fps_val > 0:
                    modes.append({"fmt": current_fmt,
                                  "size": current_size,
                                  "fps": fps_val})
            except (IndexError, ValueError):
                pass

    log.info("Enumerated %d usable modes for %s", len(modes), device)
    for m in modes:
        log.debug("  mode: fmt=%-8s  size=%-12s  fps=%.3f", m["fmt"], m["size"], m["fps"])
    return modes


def select_best_mode(modes: list[dict], target_fps: float = 30.0) -> "dict | None":
    """
    Pick the best capture mode from *modes* using this priority:

    1. Minimise |fps - target_fps|.
    2. Among equally-close fps values, prefer higher pixel count (larger frame).
    3. Among equal pixel counts, prefer mjpeg > yuyv422 > others
       (mjpeg is lower bandwidth for the same resolution; yuyv422 is universal).

    Returns None if *modes* is empty.
    """
    if not modes:
        return None

    _FMT_RANK = {"mjpeg": 0, "yuyv422": 1}  # lower = more preferred

    def score(m: dict) -> tuple:
        fps_diff   = abs(m["fps"] - target_fps)
        pixels     = _pixel_count(m["size"])
        fmt_rank   = _FMT_RANK.get(m["fmt"], 99)
        return (fps_diff, -pixels, fmt_rank)   # sort ascending → best first

    best = min(modes, key=score)
    return best


# ─────────────────────────────────────────────────────────────────────────────


def device_has_image(device: str) -> "dict | None":
    """
    Try to grab a single frame from *device*.
    Returns a dict {"fmt", "size", "fps"} on success, None on failure.

    1. Permission check
    2. Enumerate all supported modes via v4l2-ctl --list-formats-ext
    3. Select the best mode (fps closest to CAM_TARGET_FPS, largest frame)
    4. Probe with ffmpeg using that mode (with EPROTO retry logic)
    """
    # Step 1: permission check
    if not os.access(device, os.R_OK):
        log.warning("Cannot read %s — permission denied. "
                    "Make sure the container is run with --device %s "
                    "and --group-add video", device, device)
        return None

    # Step 2: enumerate all supported modes
    modes = enumerate_camera_modes(device)

    # Step 3: select the best mode
    chosen = select_best_mode(modes, target_fps=float(CAM_TARGET_FPS))

    if chosen:
        log.info(
            "Selected mode for %s — fmt=%s  size=%s  fps=%.3f  "
            "(target fps=%d, delta=%.3f)",
            device, chosen["fmt"], chosen["size"], chosen["fps"],
            CAM_TARGET_FPS, abs(chosen["fps"] - CAM_TARGET_FPS),
        )
        # Build the probe list: chosen mode first, then a bare fallback
        probe_candidates = [chosen, None]   # None → let ffmpeg auto-detect
    else:
        # v4l2-ctl gave us nothing — fall back to the old manual format sweep
        log.info("No modes enumerated for %s — using fallback format sweep", device)
        probe_candidates = [
            {"fmt": "mjpeg",    "size": "", "fps": 0.0},
            {"fmt": "yuyv422",  "size": "", "fps": 0.0},
            {"fmt": "",         "size": "", "fps": 0.0},
        ]

    # Step 4: probe with ffmpeg
    # Compute a per-attempt timeout generous enough for slow cameras.
    fps_val = chosen["fps"] if chosen else 0.0
    extra = max(4, 3 * (1 + (1 // max(int(fps_val), 1))))
    per_attempt = DEVICE_PROBE_TIMEOUT + extra

    log.info("Probing %s (per-attempt timeout %d s) …", device, per_attempt)

    PROBE_MAX_RETRIES = 4
    PROBE_RETRY_DELAY = 3   # seconds

    for attempt in range(1, PROBE_MAX_RETRIES + 1):
        eproto_count = 0
        for candidate in probe_candidates:
            if candidate is None:
                fmt, size, fps = "", "", ""
            else:
                fmt  = candidate.get("fmt",  "")
                size = candidate.get("size", "")
                # Round fps to integer string for ffmpeg (e.g. "30", "5")
                fps_f = candidate.get("fps", 0.0)
                fps   = str(int(round(fps_f))) if fps_f > 0 else ""

            cmd = ["ffmpeg", "-loglevel", "error", "-f", "v4l2"]
            if fmt:
                cmd += ["-input_format", fmt]
            if fps:
                cmd += ["-framerate", fps]
            if size:
                cmd += ["-video_size", size]
            cmd += ["-i", device, "-vframes", "1", "-f", "null", "-"]

            try:
                result = subprocess.run(cmd, timeout=per_attempt,
                                        capture_output=True, text=True)
                if result.returncode == 0:
                    # Return the actually-used parameters (or device defaults for
                    # the None/auto fallback case, which we don't know precisely).
                    final_fmt  = fmt  or (chosen["fmt"]  if chosen else "")
                    final_size = size or (chosen["size"] if chosen else "")
                    final_fps  = fps  or (str(int(round(chosen["fps"]))) if chosen and chosen["fps"] > 0 else "")
                    log.info("Device %s working (format=%s size=%s fps=%s)",
                             device, final_fmt or "auto",
                             final_size or "?", final_fps or "?")
                    return {"fmt": final_fmt, "size": final_size, "fps": final_fps}

                err_lines = (result.stderr or "").strip().splitlines()
                is_eproto = any("Protocol error" in l or "EPROTO" in l for l in err_lines)
                if is_eproto:
                    eproto_count += 1
                    log.debug("  ffmpeg [%s fmt=%s]: Protocol error (device resetting?)",
                              device, fmt or "auto")
                else:
                    for err_line in err_lines:
                        log.warning("  ffmpeg [%s fmt=%s]: %s", device, fmt or "auto", err_line)
            except subprocess.TimeoutExpired:
                log.warning("Probe timed out for %s with format=%s (timeout=%d s) — "
                            "raise DEVICE_PROBE_TIMEOUT if the camera is genuinely slow",
                            device, fmt or "auto", per_attempt)

        if eproto_count == len(probe_candidates):
            if attempt < PROBE_MAX_RETRIES:
                log.info("Device %s returned Protocol error on all formats "
                         "(attempt %d/%d) — device still resetting, "
                         "retrying in %d s …",
                         device, attempt, PROBE_MAX_RETRIES, PROBE_RETRY_DELAY)
                time.sleep(PROBE_RETRY_DELAY)
            else:
                log.warning("Device %s returned Protocol error on all formats "
                            "after %d attempts — giving up",
                            device, PROBE_MAX_RETRIES)
        else:
            break

    log.info("No image from %s after trying all modes", device)
    return None


def find_working_camera() -> "tuple[str, dict] | tuple[None, None]":
    for dev in list_video_devices():
        params = device_has_image(dev)
        if params is not None:
            log.info("Found working camera: %s", dev)
            return dev, params
    return None, None


def h264_extra_flags() -> list[str]:
    """Extra flags needed for H264 WebRTC browser compatibility."""
    return [
        "-pix_fmt",    "yuv420p",
        "-profile:v",  "baseline",
        "-level:v",    "4.2",
        "-bf",         "0",
    ]


def device_has_audio(device: str) -> bool:
    """Check if a v4l2 device also has an associated audio capture capability."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-f", "v4l2", "-i", device,
             "-t", "0.5", "-f", "null", "-"],
            capture_output=True, text=True, timeout=5,
        )
        return "Audio" in result.stderr or "audio" in result.stderr
    except Exception:
        return False


def stream_camera(device: str, native: dict) -> None:
    url = rtsp_url()
    log.info("Streaming camera %s → %s", device, url)

    has_audio = device_has_audio(device)
    if not has_audio:
        log.info("No audio stream detected on %s — streaming video only", device)

    # Use env-var overrides when explicitly set; fall back to native device
    # values discovered during probing.
    framerate  = CAM_FRAMERATE  or native.get("fps",  "")
    resolution = CAM_RESOLUTION or native.get("size", "")

    if not CAM_FRAMERATE and framerate:
        log.info("CAM_FRAMERATE not set — using selected fps=%s", framerate)
    if not CAM_RESOLUTION and resolution:
        log.info("CAM_RESOLUTION not set — using selected size=%s", resolution)

    # Optional v4l2 flags that help with USB buffer overflows on high-bandwidth
    # cameras (e.g. Arducam 16MP YUYV at ~19 MB/s).  They were added in
    # ffmpeg 4.4; older builds reject them with "Option not found" (exit 8).
    # We try with them first and silently drop them if this build lacks support.
    OVERFLOW_FLAGS = ["-drop_pkts_on_overflow", "1",
                      "-use_wallclock_as_timestamps", "1"]
    use_overflow_flags = True   # optimistically try on first run

    def _build_cmd(overflow: bool) -> list[str]:
        c = [
            "ffmpeg", "-loglevel", "warning",
            "-f", "v4l2",
            "-rtbufsize", CAM_RTBUFSIZE,
        ]
        if overflow:
            c += OVERFLOW_FLAGS
        if framerate:
            c += ["-framerate", framerate]
        if resolution:
            c += ["-video_size", resolution]
        # Pass the selected input_format so ffmpeg doesn't have to guess
        fmt = native.get("fmt", "")
        if fmt:
            c += ["-input_format", fmt]
        c += ["-i", device, "-c:v", CAM_VIDEO_CODEC]
        if CAM_VIDEO_CODEC == "libx264":
            c += h264_extra_flags()
            c += ["-preset", CAM_PRESET, "-tune", CAM_TUNE]
        c += ["-b:v", CAM_VIDEO_BITRATE]
        c += (["-c:a", CAM_AUDIO_CODEC, "-b:a", CAM_AUDIO_BITRATE]
              if has_audio else ["-an"])
        c += ["-f", "rtsp", url]
        return c

    ENODEV_SENTINEL    = "No such device"
    OPT_NOT_FOUND      = "Option not found"

    while True:
        cmd = _build_cmd(use_overflow_flags)
        log.info("Running: %s", " ".join(cmd))
        stderr_lines: list[str] = []
        saw_enodev = False
        saw_opt_not_found = False

        with subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True) as proc:
            for line in proc.stderr:
                line = line.rstrip()
                if not line:
                    continue
                stderr_lines.append(line)
                log.warning("  ffmpeg: %s", line)
                if ENODEV_SENTINEL in line:
                    saw_enodev = True
                if OPT_NOT_FOUND in line:
                    saw_opt_not_found = True
            proc.wait()

        if proc.returncode == 0:
            break

        if saw_opt_not_found and use_overflow_flags:
            log.warning("Overflow flags not supported by this ffmpeg build — "
                        "retrying without them (USB buffer overflow protection disabled)")
            use_overflow_flags = False
            continue   # retry immediately, no sleep

        if saw_enodev:
            log.error("Camera %s disappeared (ENODEV). Will re-probe in 5 s …", device)
            time.sleep(5)
            return   # signal main() to call find_working_camera() again

        log.warning("Camera stream exited with code %d, restarting in 3 s …",
                    proc.returncode)
        time.sleep(3)


def list_video_files() -> list[str]:
    exts = ("*.mp4", "*.mkv", "*.avi", "*.mov", "*.ts", "*.flv", "*.webm")
    files: list[str] = []
    for ext in exts:
        files.extend(glob.glob(os.path.join(VID_DIR, ext)))
    return sorted(files)


def stream_videos() -> None:
    url = rtsp_url()

    files = list_video_files()
    if not files:
        log.error(
            "No video files found in '%s' and no working camera detected. "
            "Mount a directory containing video files with: "
            "-v /your/videos:%s:ro,z",
            VID_DIR, VID_DIR,
        )
        sys.exit(1)

    while True:
        files = list_video_files()
        if not files:
            log.warning("No video files found in %s. Retrying in 10 s …", VID_DIR)
            time.sleep(10)
            continue

        for vf in files:
            log.info("Streaming file %s → %s", vf, url)
            cmd = [
                "ffmpeg", "-loglevel", "warning",
                "-re",
                "-i", vf,
                "-c:v", VID_VIDEO_CODEC,
            ]
            if VID_VIDEO_CODEC == "libx264":
                cmd += h264_extra_flags()
                cmd += ["-preset", VID_PRESET]
            cmd += [
                "-b:v", VID_VIDEO_BITRATE,
                "-c:a", VID_AUDIO_CODEC,
                "-b:a", VID_AUDIO_BITRATE,
                "-f", "rtsp", url,
            ]
            log.info("Running: %s", " ".join(cmd))
            proc = subprocess.run(cmd)
            if proc.returncode not in (0, 1):
                log.warning("ffmpeg exited with code %d for file %s",
                            proc.returncode, vf)
            time.sleep(1)

        log.info("Playlist finished, restarting from the beginning …")


def main() -> None:
    log.info("RTSP streamer starting up.")
    log.info("Target URL: %s", rtsp_url())
    log.info("Target camera FPS: %d", CAM_TARGET_FPS)

    while True:
        camera, native_params = find_working_camera()
        if camera:
            stream_camera(camera, native_params)
            # stream_camera returns only when the camera is gone or cleanly done.
            # Loop back to re-probe — the device may reconnect or another camera
            # may become available.
            log.info("Returned from stream_camera. Re-probing devices …")
        else:
            log.info("No working camera found. Falling back to video files in %s.", VID_DIR)
            stream_videos()
            break   # stream_videos() only returns on empty dir (sys.exit) or never


if __name__ == "__main__":
    main()