import inspect


def test_fastmcp_exposes_streamable_http_features() -> None:
    from mcp.server.fastmcp import FastMCP

    init_params = inspect.signature(FastMCP.__init__).parameters
    assert 'streamable_http_path' in init_params
    assert 'transport_security' in init_params
    assert hasattr(FastMCP, 'streamable_http_app')


def test_tool_annotations_shape() -> None:
    from mcp.types import ToolAnnotations

    annotations = ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
    assert annotations.readOnlyHint is True
    assert annotations.destructiveHint is False
    assert annotations.idempotentHint is True
    assert annotations.openWorldHint is False


def test_transport_security_settings_shape() -> None:
    from mcp.server.fastmcp.server import TransportSecuritySettings

    settings = TransportSecuritySettings(
        allowed_hosts=['127.0.0.1'],
        allowed_origins=['http://127.0.0.1'],
    )
    assert settings.allowed_hosts == ['127.0.0.1']
    assert settings.allowed_origins == ['http://127.0.0.1']


def test_streamable_http_client_api_exists() -> None:
    from mcp.client import streamable_http

    assert hasattr(streamable_http, 'streamablehttp_client') or hasattr(
        streamable_http, 'streamable_http_client'
    )
