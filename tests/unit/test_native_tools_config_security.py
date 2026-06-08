"""Tests for native-tools security config wiring (PL-C3/C5).

Covers:
- ToolConfig carries the security fields (max_file_size, allowed/denied paths,
  allowed/denied hosts, max_data_size).
- _handle_config_change wires the filesystem + network security fields through
  (not just workspace_dir).
- Workspace default does NOT silently fall back to CWD when WORKSPACE_DIR unset.
"""

from __future__ import annotations

from ploston.native_tools import config_manager as cm
from ploston.native_tools.config_watcher import (
    FilesystemConfig,
    NativeToolsConfig,
    NetworkConfig,
)


def _fresh_manager(monkeypatch):
    """Build a ConfigManager with a clean env (no WORKSPACE_DIR)."""
    monkeypatch.delenv("WORKSPACE_DIR", raising=False)
    return cm.ConfigManager()


# ---------------------------------------------------------------------------
# PL-C5: security fields exist on ToolConfig
# ---------------------------------------------------------------------------


def test_toolconfig_has_security_fields():
    config = cm.ToolConfig()
    assert hasattr(config, "max_file_size")
    assert hasattr(config, "allowed_paths")
    assert hasattr(config, "denied_paths")
    assert hasattr(config, "allowed_hosts")
    assert hasattr(config, "denied_hosts")
    assert hasattr(config, "max_data_size")


# ---------------------------------------------------------------------------
# PL-C5: _handle_config_change wires security fields through
# ---------------------------------------------------------------------------


def test_handle_config_change_wires_filesystem_security(monkeypatch):
    mgr = _fresh_manager(monkeypatch)

    new = NativeToolsConfig(
        filesystem=FilesystemConfig(
            enabled=True,
            workspace_dir="/workspace",
            allowed_paths=["/workspace/pub"],
            denied_paths=["/workspace/secrets"],
            max_file_size=1234,
        )
    )
    mgr._handle_config_change(new)

    assert mgr.config.workspace_dir == "/workspace"
    assert mgr.config.allowed_paths == ["/workspace/pub"]
    assert mgr.config.denied_paths == ["/workspace/secrets"]
    assert mgr.config.max_file_size == 1234


def test_handle_config_change_wires_network_security(monkeypatch):
    mgr = _fresh_manager(monkeypatch)

    new = NativeToolsConfig(
        network=NetworkConfig(
            enabled=True,
            allowed_hosts=["api.example.com"],
            denied_hosts=["evil.example.com"],
        )
    )
    mgr._handle_config_change(new)

    assert mgr.config.allowed_hosts == ["api.example.com"]
    assert mgr.config.denied_hosts == ["evil.example.com"]


# ---------------------------------------------------------------------------
# PL-C3: workspace default must not silently use CWD
# ---------------------------------------------------------------------------


def test_workspace_default_not_cwd(monkeypatch):
    import os

    monkeypatch.delenv("WORKSPACE_DIR", raising=False)
    mgr = cm.ConfigManager()
    # Must not silently default to the process CWD (which is /app in Docker).
    assert mgr.config.workspace_dir != os.getcwd()
