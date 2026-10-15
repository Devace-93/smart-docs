"""Streamable HTTP transport mounted at /mcp, authenticated with an SD API key as bearer token."""

from __future__ import annotations

from contextlib import asynccontextmanager

from mcp.server.transport_security import TransportSecuritySettings

from smart_docs.mcp.server import current_principal, principal_from_key, server


class MCPEndpoint:
    """ASGI app: checks the bearer key, binds the principal, then hands over to the MCP transport."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        inner = self.inner
        if scope["type"] != "http":
            await inner(scope, receive, send)
            return
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        auth = headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else headers.get("x-api-key")
        principal = await principal_from_key(token)
        if principal is None:
            body = (
                b'{"code":"unauthorized","message":"Send Authorization: Bearer <sd_ API key>.",'
                b'"hint":"Create a key at /app#/keys."}'
            )
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer")],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        token_var = current_principal.set(principal)
        try:
            await inner(scope, receive, send)
        finally:
            current_principal.reset(token_var)


def build_mcp_asgi_app():
    inner = server.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    @asynccontextmanager
    async def lifespan():
        async with inner.router.lifespan_context(inner):
            yield

    return MCPEndpoint(inner), lifespan
