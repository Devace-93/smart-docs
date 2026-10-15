"""stdio transport for local agents. Needs DATABASE_URL and SD_API_KEY in the environment."""

from __future__ import annotations

import asyncio
import os
import sys

from smart_docs.mcp.server import current_principal, principal_from_key, server


def main() -> None:
    key = os.environ.get("SD_API_KEY")
    principal = asyncio.run(principal_from_key(key))
    if principal is None:
        print("SD_API_KEY is missing or invalid. Create one at /app/keys.", file=sys.stderr)
        sys.exit(2)
    current_principal.set(principal)
    server.run("stdio")


if __name__ == "__main__":
    main()
