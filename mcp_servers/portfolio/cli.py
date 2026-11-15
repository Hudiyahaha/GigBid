"""Console entry point for `uvx ... gigbid-portfolio-mcp` (stdio by default)."""

from __future__ import annotations

import sys


def main() -> None:
    from mcp_servers.common import run
    from mcp_servers.portfolio.server import mcp
    if len(sys.argv) == 1:
        sys.argv.append("stdio")
    run(mcp, 8101, token_env="PORTFOLIO_MCP_TOKEN")


if __name__ == "__main__":
    main()
