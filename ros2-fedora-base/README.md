# ros2-fedora-base

Imagen base común para todos los servicios ROS2 contenerizados.

Construida sobre `fedora:42` e incluye:
- ROS2 Kilted (vía COPR `tavie/ros2`)
- `ros-kilted-rmw-cyclonedds-cpp` — middleware DDS compartido por todos los servicios
- Dependencias de runtime comunes (`spdlog`, `lttng-ust`, `numpy`, etc.)
- Herramientas de desarrollo (`cmake`, `gcc`, `colcon`, `rosdep`, `flake8`, etc.)
- Configuración SSH con X11 forwarding habilitado

## Estructura

```
ros2-fedora-base/
├── README.md
└── src/
    └── Containerfile
```

## Construir

```bash
cd ros2-fedora-base/src
podman build -t ros2-fedora-base:latest .
```

## Uso en servicios derivados

```dockerfile
FROM ros2-fedora-base:latest
```

Los tres servicios que usan esta base son:
- `ros2-rtsp-bridge`
- `ros2-broker`
- `ros2-image-streamer`
