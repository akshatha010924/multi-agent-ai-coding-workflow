"""Tiny LOCAL MCP server (stdio) with the same tool contract as Context7.

It is a stand-in for integration tests/demos so the MCP client path can be verified offline.
It is NOT Context7 and serves only a few hand-written snippets.
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("local-docs")

_DOCS = {
    "/python/re": "re module: use re.compile(pattern) and pattern.fullmatch(text). Anchors ^ and $; "
                  "character classes [A-Za-z0-9]; non-capturing groups (?:...). Avoid catastrophic backtracking.",
    "/tiangolo/fastapi": "FastAPI: declare routes with @app.get/@app.post, validate bodies with Pydantic models, "
                         "use Depends() for dependency injection.",
}
_ALIASES = {"python re": "/python/re", "re": "/python/re", "fastapi": "/tiangolo/fastapi"}


@mcp.tool(name="resolve-library-id")
def resolve_library_id(libraryName: str, query: str) -> str:  # noqa: N803
    lib_id = _ALIASES.get(libraryName.lower().strip())
    if not lib_id:
        return "No matching libraries found."
    return f"Available Libraries:\n- Title: {libraryName}\n- Context7-compatible library ID: {lib_id}"


@mcp.tool(name="query-docs")
def query_docs(libraryId: str, query: str) -> str:  # noqa: N803
    return _DOCS.get(libraryId, "")


if __name__ == "__main__":
    mcp.run(transport="stdio")
