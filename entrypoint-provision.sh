#!/bin/bash
# Siembra las skills y registra el MCP server del demo en el volumen de
# datos de Hermes (/opt/data, persistente entre restarts/deploys) antes de
# arrancar Hermes normalmente. Es idempotente a propósito: no pisa una
# skill que ya exista en el volumen (por si Hermes la editó en vivo, como
# pasó con `asesor-financiero` durante el desarrollo de este proyecto), ni
# vuelve a registrar el MCP server si ya está.
set -e

DATA_DIR="${HERMES_HOME:-/opt/data}"
PROJECT_DIR="/app/demo-asesor-financiero"

mkdir -p "$DATA_DIR/skills"

for skill_src in /app/hermes-skills/*/; do
  name="$(basename "$skill_src")"
  if [ ! -d "$DATA_DIR/skills/$name" ]; then
    cp -r "$skill_src" "$DATA_DIR/skills/$name"
    echo "[provision] Sembrada skill: $name"
  fi
done

# El sync de las skills bundleadas propias de Hermes (58 built-in) corre
# después de este script, como parte del cont-init original, y necesita
# poder crear subcarpetas nuevas bajo skills/ — dejamos el directorio
# abierto a escritura para evitar "Permission denied" ahí (no es sensible:
# /opt/data es un volumen privado del contenedor, no algo expuesto).
chmod -R 777 "$DATA_DIR/skills"

# La imagen trae un modelo default propio (no Anthropic) que rompe en
# cuanto se usa una ANTHROPIC_API_KEY sin elegir modelo explícitamente —
# forzamos acá el mismo par provider/modelo que ya funciona en desarrollo
# local (ver ~/.hermes/config.yaml tras 'hermes setup model').
if [ -n "$ANTHROPIC_API_KEY" ]; then
  hermes config set model.provider anthropic >/dev/null 2>&1 || true
  hermes config set model.default claude-sonnet-5 >/dev/null 2>&1 || true
fi

if ! hermes mcp list 2>/dev/null | grep -q "asesor_financiero"; then
  echo "[provision] Registrando MCP server asesor_financiero..."
  yes | hermes mcp add asesor_financiero \
    --command "$PROJECT_DIR/.venv-mcp/bin/python" \
    --args "$PROJECT_DIR/mcp_server/server.py" \
    || echo "[provision] ADVERTENCIA: no se pudo registrar el MCP server automáticamente — revisar logs y registrarlo a mano con 'hermes mcp add' si hace falta."
fi

exec /opt/hermes/docker/entrypoint-dispatch.sh "$@"
