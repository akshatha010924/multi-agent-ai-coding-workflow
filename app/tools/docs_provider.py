"""Documentation tool port + adapters (Adapter / Null Object patterns).

`McpDocsProvider` talks to ANY MCP server over stdio that exposes a resolve tool and a docs tool shaped like
Context7's (`resolve-library-id{libraryName,query}` and `query-docs{libraryId,query}`).
Security: only the two configured tools may be called, arguments are schema-validated, every call is time-boxed.
"""
import asyncio
import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client
from pydantic import BaseModel, Field, ValidationError

from app.config import Settings
from app.core.exceptions import ToolError

logger = logging.getLogger(__name__)
T = TypeVar("T")

_LIB_ID = re.compile(r"(?<![\w:/])/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)?")


class DocsResult(BaseModel):
    library: str
    library_id: str
    content: str
    source: str


class ResolveArgs(BaseModel):
    libraryName: str = Field(min_length=1, max_length=80, pattern=r"^[\w .@/+\-]+$")  # noqa: N815
    query: str = Field(min_length=1, max_length=300)


class QueryArgs(BaseModel):
    libraryId: str = Field(pattern=r"^/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+(/[A-Za-z0-9_.\-]+)?$")  # noqa: N815
    query: str = Field(min_length=1, max_length=300)


class DocsProvider(ABC):
    @abstractmethod
    def fetch(self, library: str, query: str) -> DocsResult | None:
        """Return docs, None if no provider is configured, or raise ToolError on failure."""


class NullDocsProvider(DocsProvider):
    def fetch(self, library: str, query: str) -> DocsResult | None:
        return None


def _leaf_exceptions(exc: BaseException) -> list[BaseException]:
    """anyio wraps errors raised inside task groups in ExceptionGroups; flatten to the real causes."""
    if isinstance(exc, BaseExceptionGroup):
        return [leaf for sub in exc.exceptions for leaf in _leaf_exceptions(sub)]
    return [exc]


def _run_sync(factory: Callable[[], Awaitable[T]], timeout: float) -> T:
    """Run a coroutine to completion from sync code, safe even if the caller already has an event loop."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(factory())).result(timeout=timeout)  # type: ignore[arg-type]


class McpDocsProvider(DocsProvider):
    def __init__(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: float = 30,
        resolve_tool: str = "resolve-library-id",
        docs_tool: str = "query-docs",
        env: Mapping[str, str] | None = None,
        max_chars: int = 6000,
    ):
        if not command:
            raise ToolError("MCP server command is empty")
        self._command = list(command)
        self._timeout = timeout_seconds
        self._resolve_tool = resolve_tool
        self._docs_tool = docs_tool
        self._allowed = {resolve_tool, docs_tool}
        self._env = {**get_default_environment(), **(env or {})}
        self._max_chars = max_chars

    # -- public API ----------------------------------------------------------------------------
    def discover(self) -> list[str]:
        """Connect, initialise, and list tool names (used for health checks)."""
        return self._run(self._discover)

    def fetch(self, library: str, query: str) -> DocsResult:
        try:
            resolve_args = ResolveArgs(libraryName=library, query=query)
        except ValidationError as e:
            raise ToolError("Invalid arguments for documentation lookup") from e
        return self._run(lambda: self._fetch(resolve_args))

    # -- internals -----------------------------------------------------------------------------
    def _run(self, factory: Callable[[], Awaitable[T]]) -> T:
        try:
            return _run_sync(factory, self._timeout + 5)
        except Exception as e:
            leaves = _leaf_exceptions(e)
            tool_err = next((x for x in leaves if isinstance(x, ToolError)), None)
            if tool_err is not None:  # keep our specific, client-safe message
                raise tool_err from e
            if any(isinstance(x, TimeoutError) for x in leaves):
                raise ToolError("MCP server timed out") from e
            logger.warning("MCP call failed: %s", "; ".join(f"{type(x).__name__}: {x}" for x in leaves))
            raise ToolError("MCP server unavailable or returned an error") from e

    def _params(self) -> StdioServerParameters:
        return StdioServerParameters(command=self._command[0], args=self._command[1:], env=self._env)

    async def _discover(self) -> list[str]:
        async with asyncio.timeout(self._timeout):
            async with stdio_client(self._params()) as (r, w), ClientSession(r, w) as session:
                await session.initialize()
                return sorted(t.name for t in (await session.list_tools()).tools)

    async def _call(self, session: ClientSession, tool: str, args: BaseModel) -> str:
        if tool not in self._allowed:  # least-privilege whitelist
            raise ToolError(f"Tool '{tool}' is not permitted")
        result = await session.call_tool(tool, args.model_dump())
        text = "\n".join(c.text for c in result.content if getattr(c, "type", "") == "text")
        if result.isError:
            raise ToolError(f"MCP tool '{tool}' reported an error")
        return text

    async def _fetch(self, resolve_args: ResolveArgs) -> DocsResult:
        async with asyncio.timeout(self._timeout):
            async with stdio_client(self._params()) as (r, w), ClientSession(r, w) as session:
                await session.initialize()
                names = {t.name for t in (await session.list_tools()).tools}
                missing = self._allowed - names
                if missing:
                    raise ToolError(f"MCP server lacks required tools: {sorted(missing)}")
                resolved = await self._call(session, self._resolve_tool, resolve_args)
                match = _LIB_ID.search(resolved)
                if not match:
                    raise ToolError(f"No documentation found for '{resolve_args.libraryName}'")
                try:
                    query_args = QueryArgs(libraryId=match.group(0), query=resolve_args.query)
                except ValidationError as e:
                    raise ToolError("MCP server returned an invalid library id") from e
                docs = await self._call(session, self._docs_tool, query_args)
                if not docs.strip():
                    raise ToolError("MCP server returned empty documentation")
                return DocsResult(
                    library=resolve_args.libraryName,
                    library_id=query_args.libraryId,
                    content=docs[: self._max_chars],
                    source=f"mcp-docs:{query_args.libraryId}",
                )


def build_docs_provider(settings: Settings) -> DocsProvider:
    """Factory. MCP is optional: when disabled the workflow still runs (researcher flags 'no docs consulted')."""
    if not settings.mcp_enabled:
        return NullDocsProvider()
    import shlex

    env = {}
    if settings.context7_api_key:
        env["CONTEXT7_API_KEY"] = settings.context7_api_key.get_secret_value()
    return McpDocsProvider(
        shlex.split(settings.mcp_server_command),
        timeout_seconds=settings.mcp_timeout_seconds,
        resolve_tool=settings.mcp_resolve_tool,
        docs_tool=settings.mcp_docs_tool,
        env=env,
    )
