"""REAL integration tests: spawn the local MCP server over stdio. (Context7 itself is NOT contacted here.)"""
import sys
from pathlib import Path

import pytest

from app.core.exceptions import ToolError
from app.tools.docs_provider import McpDocsProvider

pytestmark = pytest.mark.integration
SERVER = [sys.executable, str(Path(__file__).parent.parent / "mcp_servers" / "local_docs_server.py")]


def provider(**kw):
    return McpDocsProvider(kw.pop("command", SERVER), timeout_seconds=kw.pop("timeout_seconds", 20), **kw)


def test_connect_and_discover_tools():
    assert provider().discover() == ["query-docs", "resolve-library-id"]


def test_successful_tool_invocation_resolve_then_query():
    res = provider().fetch("python re", "regex syntax")
    assert res.library_id == "/python/re" and "re.compile" in res.content and res.source == "mcp-docs:/python/re"


def test_unknown_library_raises_tool_error():
    with pytest.raises(ToolError, match="No documentation found"):
        provider().fetch("nonexistent-lib", "anything")


@pytest.mark.parametrize("lib,q", [("bad;name!", "q"), ("", "q"), ("ok", ""), ("x" * 200, "q")])
def test_invalid_tool_arguments_rejected_before_any_connection(lib, q):
    with pytest.raises(ToolError, match="Invalid arguments"):
        provider(command=["/definitely/not/a/binary"]).fetch(lib, q)


def test_unavailable_server_raises_tool_error():
    with pytest.raises(ToolError, match="unavailable"):
        provider(command=["/definitely/not/a/binary"]).fetch("python re", "q")


def test_hanging_server_times_out(tmp_path):
    hang = tmp_path / "hang.py"
    hang.write_text("import time\ntime.sleep(60)\n")
    with pytest.raises(ToolError, match="timed out"):
        provider(command=[sys.executable, str(hang)], timeout_seconds=2).fetch("python re", "q")


def test_server_missing_required_tools_is_detected():
    with pytest.raises(ToolError):
        provider(docs_tool="not-a-real-tool").fetch("python re", "q")


def test_tool_whitelist_blocks_unlisted_tools():
    import asyncio

    from app.tools.docs_provider import ResolveArgs

    with pytest.raises(ToolError, match="not permitted"):
        asyncio.run(provider()._call(None, "delete-everything", ResolveArgs(libraryName="a", query="b")))
