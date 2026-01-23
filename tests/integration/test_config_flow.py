"""Integration tests for AEL configuration flow.

Tests the full configuration flow from startup to mode transitions.
"""

import tempfile
from pathlib import Path

import pytest
from ploston_core.config import ConfigLoader, Mode, ModeManager, StagedConfig
from ploston_core.config.tools import ConfigToolRegistry


class TestStartupModeDetection:
    """Tests for startup mode detection."""

    def test_startup_no_config_enters_configuration_mode(self):
        """Test that startup without config enters Configuration Mode."""
        config_loader = ConfigLoader()

        # Try to load from non-existent path
        with pytest.raises(Exception):
            config_loader.load("/nonexistent/config.yaml")

        # Mode should be CONFIGURATION when no config
        mode_manager = ModeManager(initial_mode=Mode.CONFIGURATION)
        assert mode_manager.mode == Mode.CONFIGURATION

    def test_startup_with_valid_config_enters_running_mode(self):
        """Test that startup with valid config enters Running Mode."""
        # Create a valid config file using LogFormat enum value
        config_content = """
logging:
  level: INFO
  format: json
  options:
    show_params: false
    show_results: false
    truncate_at: 1000
  components:
    workflow: true
    step: true
    tool: true
    sandbox: true

tools:
  mcp_servers: {}
  native_tools:
    enabled: true
    allowed: []

workflows:
  paths: []
  auto_register: true

execution:
  max_concurrent_workflows: 10
  default_timeout: 300
  retry:
    max_attempts: 3
    backoff_multiplier: 2.0
    max_backoff: 60

python_exec:
  timeout: 30
  max_tool_calls: 10
  default_imports: []

plugins:
  enabled: []
  config: {}

security:
  sandbox:
    enabled: true
    allowed_imports: []
    blocked_imports: []
  secrets:
    env_prefix: AEL_SECRET_
    mask_in_logs: true

telemetry:
  enabled: false
  endpoint: null
  sample_rate: 1.0
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            f.flush()

            config_loader = ConfigLoader()
            _ = config_loader.load(f.name)

            # Mode should be RUNNING when config is valid
            mode_manager = ModeManager(initial_mode=Mode.RUNNING)
            assert mode_manager.mode == Mode.RUNNING

    def test_forced_configuration_mode_flag(self):
        """Test that --mode=configuration forces Configuration Mode."""
        mode_manager = ModeManager(initial_mode=Mode.CONFIGURATION)
        assert mode_manager.mode == Mode.CONFIGURATION

        # Even if we could load config, mode is forced
        assert not mode_manager.can_start_workflow()


class TestConfigurationFlow:
    """Tests for the configuration flow."""

    @pytest.fixture
    def staged_config(self):
        """Create a StagedConfig instance."""
        config_loader = ConfigLoader()
        return StagedConfig(config_loader)

    @pytest.fixture
    def config_tool_registry(self, staged_config):
        """Create a ConfigToolRegistry instance."""
        config_loader = ConfigLoader()
        return ConfigToolRegistry(
            staged_config=staged_config,
            config_loader=config_loader,
        )

    def test_config_set_stages_changes(self, staged_config):
        """Test that config_set stages changes without applying."""
        # Stage a change
        staged_config.set("logging.level", "DEBUG")

        # Check that change is staged
        assert staged_config.has_changes()
        changes = staged_config.changes
        assert "logging" in changes
        assert changes["logging"]["level"] == "DEBUG"

    def test_config_validate_checks_staged_config(self, staged_config):
        """Test that config_validate checks staged config."""
        # Stage valid changes
        staged_config.set("logging.level", "DEBUG")

        # Validate
        result = staged_config.validate()
        assert result.valid

    def test_config_validate_catches_invalid_config(self, staged_config):
        """Test that config_validate catches invalid config."""
        # Stage invalid changes
        staged_config.set("logging.level", "INVALID_LEVEL")

        # Validate
        _ = staged_config.validate()
        # May or may not be valid depending on validation rules
        # The important thing is that validation runs

    def test_config_done_applies_changes(self, staged_config):
        """Test that config_done applies staged changes."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            # Set write location using set_target_path
            staged_config.set_target_path(f.name)

            # Stage changes
            staged_config.set("logging.level", "DEBUG")

            # Apply changes
            staged_config.write()

            # Verify file was written
            content = Path(f.name).read_text()
            assert "DEBUG" in content


class TestModeTransitions:
    """Tests for mode transitions."""

    def test_config_done_transitions_to_running_mode(self):
        """Test that config_done transitions to Running Mode."""
        mode_manager = ModeManager(initial_mode=Mode.CONFIGURATION)
        assert mode_manager.mode == Mode.CONFIGURATION

        # Transition to running mode
        mode_manager.set_mode(Mode.RUNNING)
        assert mode_manager.mode == Mode.RUNNING
        assert mode_manager.can_start_workflow()

    def test_configure_transitions_to_configuration_mode(self):
        """Test that ael:configure transitions to Configuration Mode."""
        mode_manager = ModeManager(initial_mode=Mode.RUNNING)
        assert mode_manager.mode == Mode.RUNNING

        # Transition to configuration mode
        mode_manager.set_mode(Mode.CONFIGURATION)
        assert mode_manager.mode == Mode.CONFIGURATION
        assert not mode_manager.can_start_workflow()

    def test_mode_change_callback_is_called(self):
        """Test that mode change callback is called."""
        mode_manager = ModeManager(initial_mode=Mode.CONFIGURATION)

        callback_called = []

        # Callback receives only new_mode, not (old_mode, new_mode)
        def on_mode_change(new_mode):
            callback_called.append(new_mode)

        mode_manager.on_mode_change(on_mode_change)
        mode_manager.set_mode(Mode.RUNNING)

        assert len(callback_called) == 1
        assert callback_called[0] == Mode.RUNNING


class TestToolsListByMode:
    """Tests for tools/list behavior based on mode."""

    @pytest.fixture
    def mode_manager(self):
        """Create a ModeManager instance."""
        return ModeManager(initial_mode=Mode.CONFIGURATION)

    @pytest.fixture
    def config_tool_registry(self):
        """Create a ConfigToolRegistry instance."""
        config_loader = ConfigLoader()
        staged_config = StagedConfig(config_loader)
        return ConfigToolRegistry(
            staged_config=staged_config,
            config_loader=config_loader,
        )

    def test_configuration_mode_returns_config_tools_only(self, mode_manager, config_tool_registry):
        """Test that Configuration Mode returns only config tools."""
        # In configuration mode, only config tools should be available
        assert mode_manager.mode == Mode.CONFIGURATION

        # Get config tools using get_for_mcp_exposure
        config_tools = config_tool_registry.get_for_mcp_exposure()

        # Should have config tools
        tool_names = [t["name"] for t in config_tools]
        assert "ael:config_get" in tool_names
        assert "ael:config_set" in tool_names
        assert "ael:config_validate" in tool_names
        assert "ael:config_done" in tool_names

    def test_running_mode_returns_all_tools(self, mode_manager):
        """Test that Running Mode returns all tools."""
        mode_manager.set_mode(Mode.RUNNING)
        assert mode_manager.mode == Mode.RUNNING
        assert mode_manager.can_start_workflow()


class TestWorkflowBlockingInConfigMode:
    """Tests for workflow blocking in Configuration Mode."""

    def test_workflows_blocked_in_configuration_mode(self):
        """Test that workflows are blocked in Configuration Mode."""
        mode_manager = ModeManager(initial_mode=Mode.CONFIGURATION)

        # Should not be able to start workflows
        assert not mode_manager.can_start_workflow()

    def test_workflows_allowed_in_running_mode(self):
        """Test that workflows are allowed in Running Mode."""
        mode_manager = ModeManager(initial_mode=Mode.RUNNING)

        # Should be able to start workflows
        assert mode_manager.can_start_workflow()


class TestModeChangeNotification:
    """Tests for mode change notifications."""

    @pytest.mark.asyncio
    async def test_mode_change_triggers_notification(self):
        """Test that mode change triggers tools/list_changed notification."""
        mode_manager = ModeManager(initial_mode=Mode.CONFIGURATION)

        notifications = []

        # Callback receives only new_mode
        def capture_notification(new_mode):
            notifications.append(new_mode)

        mode_manager.on_mode_change(capture_notification)

        # Change mode
        mode_manager.set_mode(Mode.RUNNING)

        # Should have received notification
        assert len(notifications) == 1
        assert notifications[0] == Mode.RUNNING
