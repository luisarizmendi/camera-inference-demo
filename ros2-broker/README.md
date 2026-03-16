# ros2-broker

Servicio contenerizado que actúa como **nodo central del grafo ROS2**.
Monitoriza los topics de imagen publicados por los contenedores `ros2-rtsp-bridge` y expone diagnósticos de estado.

Construido sobre `ros2-fedora-base:latest`. Se levanta una única instancia.

---

## Estructura

```
ros2-broker/
├── README.md
└── src/
    ├── Containerfile
    ├── entrypoint.sh
    └── ros2_pkg/
        ├── package.xml
        ├── setup.py
        ├── resource/
        │   └── image_broker
        └── image_broker/
            ├── __init__.py
            └── image_broker_node.py
```

---

## Variables de entorno

| Variable                | Por defecto      | Descripción |
|-------------------------|------------------|-------------|
| `BROKER_NODE_NAME`      | `image_broker`   | Nombre del nodo ROS2 |
| `CAMERA_TOPICS`         | _(vacío)_        | Topics a monitorizar, separados por coma |
| `HEALTH_CHECK_INTERVAL` | `5`              | Segundos entre evaluaciones de estado |
| `STALE_TIMEOUT`         | `10`             | Segundos sin frames para marcar como STALE |
| `REPUBLISH`             | `false`          | Re-publica cada topic en `/broker/<topic>/image` |
| `QOS_DEPTH`             | `5`              | Profundidad del historial QoS |
| `VERBOSE`               | `false`          | Log por cada frame recibido |
| `ROS_DOMAIN_ID`         | `0`              | ID de dominio DDS de ROS2 |

---

## Construir

```bash
cd ros2-fedora-base/src && podman build -t ros2-fedora-base:latest .
cd ros2-broker/src      && podman build -t ros2-broker:latest .
```

## Ejecutar

```bash
podman run --rm --network host \
  -e CAMERA_TOPICS="/camera/front/image_raw,/camera/rear/image_raw" \
  -e STALE_TIMEOUT="10" \
  ros2-broker:latest
```

## Diagnósticos

```bash
ros2 topic echo /broker/camera_status
```
