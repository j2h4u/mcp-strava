import inspect


def test_fastmcp_exposes_streamable_http_features() -> None:
    from mcp.server.fastmcp import FastMCP

    init_params = inspect.signature(FastMCP.__init__).parameters
    assert 'streamable_http_path' in init_params
    assert 'transport_security' in init_params
    assert hasattr(FastMCP, 'streamable_http_app')


def test_streamable_http_client_api_exists() -> None:
    from mcp.client import streamable_http

    assert hasattr(streamable_http, 'streamablehttp_client') or hasattr(
        streamable_http, 'streamable_http_client'
    )
