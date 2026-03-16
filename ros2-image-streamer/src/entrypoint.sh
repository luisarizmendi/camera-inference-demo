#!/bin/bash
# Starts MediaMTX on configurable ports, waits for it to be ready,
# then launches the ROS2 image streamer node.

set -e

RTSP_PORT="${RTSP_PORT:-8554}"
RTSP_PORT_HLS="${RTSP_PORT_HLS:-8888}"
RTSP_PORT_WEBRTC="${RTSP_PORT_WEBRTC:-8889}"
RTSP_PORT_ICE_UDP="${RTSP_PORT_ICE_UDP:-8189}"

echo "[entrypoint] Sourcing ROS2 environment ..."
source /usr/lib64/ros2-kilted/setup.bash
source /ros2_ws/install/setup.bash

# Rewrite mediamtx.yml with the configured ports so that a second instance
# on the same host can use different ports without a file conflict.
echo "[entrypoint] Configuring MediaMTX ports: RTSP=${RTSP_PORT} HLS=${RTSP_PORT_HLS} WebRTC=${RTSP_PORT_WEBRTC} ICE=${RTSP_PORT_ICE_UDP}/udp"
sed -i "s|^rtspAddress:.*|rtspAddress: :${RTSP_PORT}|"           /etc/mediamtx/mediamtx.yml
sed -i "s|^hlsAddress:.*|hlsAddress: :${RTSP_PORT_HLS}|"         /etc/mediamtx/mediamtx.yml
sed -i "s|^webRTCAddress:.*|webRTCAddress: :${RTSP_PORT_WEBRTC}|" /etc/mediamtx/mediamtx.yml
sed -i "s|^webRTCICEUDPMuxAddress:.*|webRTCICEUDPMuxAddress: :${RTSP_PORT_ICE_UDP}|" /etc/mediamtx/mediamtx.yml

echo "[entrypoint] Starting MediaMTX on RTSP port ${RTSP_PORT} ..."
mediamtx /etc/mediamtx/mediamtx.yml &
MEDIAMTX_PID=$!

# Wait until the RTSP port is open (up to 15 s)
echo "[entrypoint] Waiting for MediaMTX to be ready ..."
for i in $(seq 1 15); do
    if bash -c "echo > /dev/tcp/127.0.0.1/${RTSP_PORT}" 2>/dev/null; then
        echo "[entrypoint] MediaMTX ready."
        break
    fi
    sleep 1
done

echo "[entrypoint] Starting ROS2 image streamer node ..."
exec ros2 run image_streamer image_streamer_node
