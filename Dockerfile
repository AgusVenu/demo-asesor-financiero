# Imagen de producción: Hermes Agent (imagen oficial de Nous Research) +
# el MCP server de este demo + las skills del proyecto, listas para correr
# en Railway (o cualquier host que corra un Dockerfile).
#
# Build context esperado: la raíz de demo-asesor-financiero. Este Dockerfile
# vive en la raíz a propósito — Railway (y la mayoría de los PaaS) usan
# automáticamente un Dockerfile en la ubicación default sin necesitar
# configuración adicional.
#
# Seguridad: esta imagen NO trae PPI_PUBLIC_KEY/PPI_PRIVATE_KEY/
# PPI_ACCOUNT_NUMBER/ALLOW_REAL_TRADES horneadas — son variables de entorno
# que se cargan aparte (Railway → Variables) según cuánto riesgo se quiera
# aceptar para ESTE deploy en particular:
#   - Sin ninguna de las 3 de PPI: get_portfolio_summary/buy_stock no pueden
#     llegar a una cuenta real, sin importar ALLOW_REAL_TRADES (más seguro
#     para una URL pública).
#   - Con las 3 de PPI pero ALLOW_REAL_TRADES sin activar: portafolio real,
#     compra siempre simulada.
#   - Con las 3 de PPI + ALLOW_REAL_TRADES=true: compra real habilitada
#     para quien tenga el usuario/contraseña del dashboard — solo si se
#     decidió explícitamente aceptar ese riesgo.

FROM nousresearch/hermes-agent:latest

# --- MCP server del demo (research, dólar/bitcoin ya van por skills) -------
# El mcp del proyecto usa Python 3.10+; la imagen base trae Python 3.13 del
# sistema, así que alcanza con un venv nuevo (no hace falta el split de
# venvs que se usa en desarrollo local por el Python 3.9 del .venv del repo).
COPY . /app/demo-asesor-financiero
RUN python3 -m venv /app/demo-asesor-financiero/.venv-mcp \
 && /app/demo-asesor-financiero/.venv-mcp/bin/pip install --no-cache-dir \
      -r /app/demo-asesor-financiero/requirements.txt

# --- Skills bundleadas con el proyecto -------------------------------------
# Se copian a /app/hermes-skills (parte inmutable de la imagen) y el
# entrypoint las siembra en el volumen de datos (/opt/data/skills) la
# primera vez que arranca el contenedor — así sobreviven a restarts sin
# perder ediciones hechas en vivo después del primer boot.
COPY hermes/skills /app/hermes-skills

COPY entrypoint-provision.sh /opt/entrypoint-provision.sh
RUN chmod +x /opt/entrypoint-provision.sh

ENTRYPOINT ["/opt/entrypoint-provision.sh"]
CMD ["gateway", "run"]
