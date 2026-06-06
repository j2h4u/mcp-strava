from __future__ import annotations

import types
from contextlib import AsyncExitStack
from datetime import timedelta
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client

from mcp_strava.devtools.mcp_client.contracts import DEFAULT_TIMEOUT_SECONDS, McpClientError


class StdioMcpClient:
    """Small async wrapper around the official MCP stdio client transport."""

    def __init__(
        self,
        command: list[str],
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        cwd: Path | str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        if not command:
            raise ValueError("command must contain at least one program name")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self._server = StdioServerParameters(command=command[0], args=command[1:], cwd=cwd, env=env)
        self._timeout_seconds = timeout_seconds
        self._exit_stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> StdioMcpClient:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: types.TracebackType | None,
    ) -> None:
        await self.stop()

    async def start(self) -> None:
        if self._session is not None:
            return
        exit_stack = AsyncExitStack()
        try:
            read_stream, write_stream = await exit_stack.enter_async_context(stdio_client(self._server))
            session = await exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
        except Exception as exc:
            await exit_stack.aclose()
            raise McpClientError(str(exc)) from exc
        self._exit_stack = exit_stack
        self._session = session

    async def stop(self) -> None:
        exit_stack = self._exit_stack
        self._exit_stack = None
        self._session = None
        if exit_stack is not None:
            await exit_stack.aclose()

    async def list_tools(self) -> list[dict[str, Any]]:
        session = self._require_session()
        try:
            result = await session.list_tools()
        except Exception as exc:
            raise McpClientError(str(exc)) from exc
        return [tool.model_dump(mode="json", by_alias=True, exclude_none=True) for tool in result.tools]

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        session = self._require_session()
        try:
            result = await session.call_tool(
                name,
                arguments or {},
                read_timeout_seconds=timedelta(seconds=self._timeout_seconds),
            )
        except Exception as exc:
            raise McpClientError(str(exc)) from exc
        return result.model_dump(mode="json", by_alias=True, exclude_none=True)

    def _require_session(self) -> ClientSession:
        session = self._session
        if session is None:
            raise McpClientError("client session is not initialized")
        return session


class HttpMcpClient:
    """Small async wrapper around the official MCP Streamable HTTP client transport."""

    def __init__(self, url: str, *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        if not url:
            raise ValueError("url must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._url = url
        self._timeout_seconds = timeout_seconds
        self._exit_stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> HttpMcpClient:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: types.TracebackType | None,
    ) -> None:
        await self.stop()

    async def start(self) -> None:
        if self._session is not None:
            return
        exit_stack = AsyncExitStack()
        try:
            read_stream, write_stream, _get_session_id = await exit_stack.enter_async_context(
                streamable_http_client(self._url)
            )
            session = await exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
        except Exception as exc:
            await exit_stack.aclose()
            raise McpClientError(str(exc)) from exc
        self._exit_stack = exit_stack
        self._session = session

    async def stop(self) -> None:
        exit_stack = self._exit_stack
        self._exit_stack = None
        self._session = None
        if exit_stack is not None:
            await exit_stack.aclose()

    async def list_tools(self) -> list[dict[str, Any]]:
        session = self._require_session()
        try:
            result = await session.list_tools()
        except Exception as exc:
            raise McpClientError(str(exc)) from exc
        return [tool.model_dump(mode="json", by_alias=True, exclude_none=True) for tool in result.tools]

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        session = self._require_session()
        try:
            result = await session.call_tool(
                name,
                arguments or {},
                read_timeout_seconds=timedelta(seconds=self._timeout_seconds),
            )
        except Exception as exc:
            raise McpClientError(str(exc)) from exc
        return result.model_dump(mode="json", by_alias=True, exclude_none=True)

    def _require_session(self) -> ClientSession:
        session = self._session
        if session is None:
            raise McpClientError("client session is not initialized")
        return session
