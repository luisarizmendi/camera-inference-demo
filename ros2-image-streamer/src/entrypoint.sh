#!/bin/bash
# Starts MediaMTX on configurable ports, waits for it to be ready,
# then launches the ROS2 image streamer node.

set -e

RTSP_PORT="${RTSP_PORT:-8554}"
RTSP_PORT_RTP="${RTSP_PORT_RTP:-8000}"
RTSP_PORT_RTCP="${RTSP_PORT_RTCP:-8001}"
RTSP_PORT_HLS="${RTSP_PORT_HLS:-8888}"
RTSP_PORT_WEBRTC="${RTSP_PORT_WEBRTC:-8889}"
RTSP_PORT_ICE_UDP="${RTSP_PORT_ICE_UDP:-8189}"
RTSP_PORT_SRT="${RTSP_PORT_SRT:-8890}"
RTSP_PORT_RTMP="${RTSP_PORT_RTMP:-1935}"

echo "[entrypoint] Sourcing ROS2 environment ..."
source /usr/lib64/ros2-kilted/setup.bash
source /ros2_ws/install/setup.bash

# Copy mediamtx.yml to a writable location and patch all ports.
# /etc/mediamtx/ is read-only at runtime (owned by root, built during image build).
MEDIAMTX_CFG=/tmp/mediamtx.yml
cp /etc/mediamtx/mediamtx.yml "${MEDIAMTX_CFG}"

echo "[entrypoint] Configuring MediaMTX ports: RTSP=${RTSP_PORT} RTP=${RTSP_PORT_RTP} RTCP=${RTSP_PORT_RTCP} HLS=${RTSP_PORT_HLS} WebRTC=${RTSP_PORT_WEBRTC} ICE=${RTSP_PORT_ICE_UDP}/udp SRT=${RTSP_PORT_SRT} RTMP=${RTSP_PORT_RTMP}"
sed -i "s|^rtspAddress:.*|rtspAddress: :${RTSP_PORT}|"                               "${MEDIAMTX_CFG}"
sed -i "s|^rtpAddress:.*|rtpAddress: :${RTSP_PORT_RTP}|"                             "${MEDIAMTX_CFG}"
sed -i "s|^rtcpAddress:.*|rtcpAddress: :${RTSP_PORT_RTCP}|"                          "${MEDIAMTX_CFG}"
sed -i "s|^rtmpAddress:.*|rtmpAddress: :${RTSP_PORT_RTMP}|"                          "${MEDIAMTX_CFG}"
sed -i "s|^hlsAddress:.*|hlsAddress: :${RTSP_PORT_HLS}|"                             "${MEDIAMTX_CFG}"
sed -i "s|^webRTCAddress:.*|webRTCAddress: :${RTSP_PORT_WEBRTC}|"                     "${MEDIAMTX_CFG}"
sed -i "s|^srtAddress:.*|srtAddress: :${RTSP_PORT_SRT}|"                             "${MEDIAMTX_CFG}"
sed -i "s|^webRTCICEUDPMuxAddress:.*|webRTCICEUDPMuxAddress: :${RTSP_PORT_ICE_UDP}|" "${MEDIAMTX_CFG}"

echo "[entrypoint] Starting MediaMTX on RTSP port ${RTSP_PORT} ..."
mediamtx "${MEDIAMTX_CFG}" &
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
