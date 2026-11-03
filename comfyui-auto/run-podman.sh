#!/usr/bin/env bash
# ============================================================
# iguana ComfyUI GUI — Podman run script (mirrors companion/story)
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="localhost/iguana-comfyui:latest"
CONTAINER="iguana"
NETWORK="ai-net"
PORT="7862"

REBUILD=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --rebuild|-r) REBUILD=1; shift ;;
    --port|-p)    PORT="$2"; shift 2 ;;
    --help|-h)    echo "Usage: $0 [--rebuild] [--port PORT]"; exit 0 ;;
    *) echo "Unknown flag: $1"; exit 1 ;;
  esac
done

if [[ "$REBUILD" -eq 1 ]] || ! podman image exists "$IMAGE"; then
  echo "==> Building image $IMAGE …"
  # amd64 explicitly: a cached arm64 python base once had this image running under emulation.
  podman build --format docker --platform linux/amd64 -t "$IMAGE" -f "$SCRIPT_DIR/Containerfile" "$SCRIPT_DIR"
fi

if podman container exists "$CONTAINER"; then
  echo "==> Removing existing container $CONTAINER …"
  podman rm -f "$CONTAINER"
fi

mkdir -p "$SCRIPT_DIR/outputs" "$SCRIPT_DIR/data"

# Join ai-net: ComfyUI is a container on it now, reached by name at comfyui:8188.
# Required now, not optional: comfyui:8188 only resolves on this network.
podman network exists "$NETWORK" || podman network create "$NETWORK" >/dev/null
NET_ARG="--network=$NETWORK"

# Host check (service.py): the GUI answers only to names this machine is really reached by,
# so a web page can't DNS-rebind its own name here. Add more (a DNS name, a proxy) with
# IGUANA_ALLOWED_HOSTS=a,b. A new LAN address needs a re-run of this script.
SHORT="$(hostname -s)"
HOSTS="${SHORT},${SHORT}.local,iguana"
for ip in $(hostname -I 2>/dev/null); do
  [[ "$ip" == *:* ]] || HOSTS+=",${ip}"            # IPv4 only: Starlette can't parse [v6]:port
done
[[ -n "${IGUANA_ALLOWED_HOSTS:-}" ]] && HOSTS+=",${IGUANA_ALLOWED_HOSTS}"
echo "==> Allowed host names: localhost,${HOSTS}"

echo "==> Starting $CONTAINER on port $PORT …"
podman run -d \
  --name "$CONTAINER" \
  --restart unless-stopped \
  $NET_ARG \
  -p "${PORT}:7862" \
  -e COMFY_HOST=comfyui \
  -e COMFY_PORT=8188 \
  -e PORT=7862 \
  -e IGUANA_HOST=0.0.0.0 \
  -e "IGUANA_ALLOWED_HOSTS=${HOSTS}" \
  -v "$SCRIPT_DIR/outputs:/app/outputs:z" \
  -v "$SCRIPT_DIR/data:/app/data:z" \
  "$IMAGE"

echo ""
echo "✓  iguana ComfyUI GUI is running."
echo "   Open: http://localhost:${PORT}   (other devices: http://$(hostname -s).local:${PORT})"
echo "   Logs: podman logs -f $CONTAINER"
