"""Expone el mismo MCP server de `server.py` (research, portafolio, órdenes)
por HTTP/SSE en vez de stdio — para instancias de Hermes que solo pueden
agregar MCP servers remotos por URL (Transport: HTTP/SSE), no un comando
local, como es el caso cuando no se tiene acceso al filesystem/servidor de
esa instancia.

Reutiliza el objeto `mcp` de `server.py` tal cual (mismos 6 tools, mismos
gates de confirmación y dry-run) — este archivo solo cambia el transporte y
agrega autenticación por token, porque a diferencia del stdio local (que
solo Hermes en la misma máquina puede invocar), un endpoint HTTP queda
alcanzable por cualquiera que tenga la URL.

Variables de entorno:
- MCP_AUTH_TOKEN (obligatoria): token que hay que mandar como
  `Authorization: Bearer <token>` en cada request. Sin esto, el server no
  arranca — no tiene sentido exponer estos tools sin ninguna auth.
- PORT (la asigna Railway automáticamente).
"""
from __future__ import annotations

import os
import secrets
import sys

import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_server.server import mcp

AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN")
if not AUTH_TOKEN:
    print(
        "[http_server] Falta MCP_AUTH_TOKEN en el entorno — no se puede "
        "exponer este MCP server por HTTP sin un token. Generá uno (ej. "
        "`python -c \"import secrets; print(secrets.token_urlsafe(32))\"`) "
        "y configuralo como variable de entorno.",
        file=sys.stderr,
    )
    sys.exit(1)


class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        header = request.headers.get("authorization", "")
        expected = f"Bearer {AUTH_TOKEN}"
        if not secrets.compare_digest(header, expected):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


mcp_asgi_app = mcp.streamable_http_app(streamable_http_path="/mcp")

app = Starlette(
    routes=mcp_asgi_app.routes,
    middleware=[Middleware(BearerAuthMiddleware)],
    lifespan=mcp_asgi_app.router.lifespan_context,
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
