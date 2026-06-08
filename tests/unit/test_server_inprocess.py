"""In-process tests for the `ploston` OSS package surface.

These tests import and call the *real* ploston package handlers directly,
rather than driving them through a spawned subprocess. This is what makes
`--cov=ploston` reflect reality: the live ploston code is `ploston.server`
(create_server / main) and `ploston.defaults`. The legacy `ploston.plugins`
and `ploston.native_tools` subpackages are not imported by the product (see
the module-coverage note in the task report) and are intentionally not
exercised here.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, patch

import ploston
import pytest
from ploston import defaults, server

# =============================================================================
# Package metadata / defaults
# =============================================================================


def test_package_version() -> None:
    assert ploston.__version__ == "1.0.0"


def test_community_feature_flags_shape() -> None:
    flags = defaults.COMMUNITY_FEATURE_FLAGS
    # Core OSS features on, premium features off.
    assert flags.workflows is True
    assert flags.mcp is True
    assert flags.rest_api is True
    assert flags.policy is False
    assert flags.human_approval is False
    assert "logging" in flags.enabled_plugins
    assert "metrics" in flags.enabled_plugins


def test_server_public_exports() -> None:
    for name in ("create_server", "main", "PlostApplication", "MCPFrontend", "MCPServerConfig"):
        assert name in server.__all__
        assert hasattr(server, name)


# =============================================================================
# create_server (the real handler, fully in-process)
# =============================================================================


@pytest.mark.asyncio
async def test_create_server_initializes_application() -> None:
    """create_server builds and initializes a real PlostApplication."""
    app = await server.create_server(config_path=None, port=8099, with_rest_api=True)
    try:
        assert isinstance(app, server.PlostApplication)
    finally:
        await app.shutdown()


@pytest.mark.asyncio
async def test_create_server_without_rest_api() -> None:
    """create_server honors with_rest_api=False (MCP-only mode)."""
    app = await server.create_server(config_path=None, port=8100, with_rest_api=False)
    try:
        assert isinstance(app, server.PlostApplication)
    finally:
        await app.shutdown()


@pytest.mark.asyncio
async def test_create_server_sets_community_feature_flags() -> None:
    """create_server pushes the community feature flags into the registry."""
    with patch("ploston.server.FeatureFlagRegistry") as mock_registry:
        app = await server.create_server(config_path=None, port=8101)
        try:
            mock_registry.set_flags.assert_called_once_with(defaults.COMMUNITY_FEATURE_FLAGS)
        finally:
            await app.shutdown()


# =============================================================================
# main() CLI entrypoint
# =============================================================================


def test_main_parses_args_and_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() parses CLI args, sets flags, and drives the async server loop."""
    monkeypatch.setattr(
        sys, "argv", ["ploston-server", "--port", "8123", "--host", "127.0.0.1", "--no-rest"]
    )

    created: dict[str, object] = {}

    class FakeApp:
        def __init__(self, **kwargs: object) -> None:
            created["kwargs"] = kwargs
            self.initialize = AsyncMock()
            # start() returns immediately so asyncio.run() completes.
            self.start = AsyncMock()
            self.shutdown = AsyncMock()

    with (
        patch("ploston.server.PlostApplication", FakeApp),
        patch("ploston.server.FeatureFlagRegistry") as mock_registry,
    ):
        server.main()

    mock_registry.set_flags.assert_called_once_with(defaults.COMMUNITY_FEATURE_FLAGS)
    kwargs = created["kwargs"]
    assert kwargs["http_port"] == 8123
    assert kwargs["http_host"] == "127.0.0.1"
    # --no-rest disables the REST API.
    assert kwargs["with_rest_api"] is False


def test_main_handles_startup_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() shuts down and re-raises when initialization fails."""
    monkeypatch.setattr(sys, "argv", ["ploston-server"])

    shutdown = AsyncMock()

    class FakeApp:
        def __init__(self, **kwargs: object) -> None:
            self.initialize = AsyncMock(side_effect=RuntimeError("boom"))
            self.start = AsyncMock()
            self.shutdown = shutdown

    with (
        patch("ploston.server.PlostApplication", FakeApp),
        patch("ploston.server.FeatureFlagRegistry"),
        pytest.raises(RuntimeError, match="boom"),
    ):
        server.main()

    shutdown.assert_awaited_once()


def test_server_module_dunder_main_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    """`python -m ploston.server` runs main() via the __main__ guard."""
    import runpy

    monkeypatch.setattr(sys, "argv", ["ploston-server"])
    with patch("ploston.server.main") as mock_main:
        # Executing the package as __main__ triggers ploston/server/__main__.py,
        # whose guard calls main().
        runpy.run_module("ploston.server", run_name="__main__")
    mock_main.assert_called_once()


def test_main_handles_keyboard_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() shuts down cleanly on KeyboardInterrupt without re-raising."""
    monkeypatch.setattr(sys, "argv", ["ploston-server"])

    shutdown = AsyncMock()

    class FakeApp:
        def __init__(self, **kwargs: object) -> None:
            self.initialize = AsyncMock()
            self.start = AsyncMock(side_effect=KeyboardInterrupt())
            self.shutdown = shutdown

    with (
        patch("ploston.server.PlostApplication", FakeApp),
        patch("ploston.server.FeatureFlagRegistry"),
    ):
        # Should not raise.
        server.main()

    shutdown.assert_awaited_once()
