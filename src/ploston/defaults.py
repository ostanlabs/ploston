"""Community tier defaults for Ploston OSS.

This module defines the default feature flags and capabilities
for the open-source community tier.
"""

from ploston_core.extensions import FeatureFlags

COMMUNITY_FEATURE_FLAGS = FeatureFlags(
    # Core features (enabled)
    workflows=True,
    mcp=True,
    rest_api=True,
    # Premium features (disabled)
    policy=False,
    patterns=False,
    synthesis=False,
    parallel_execution=False,
    compensation_steps=False,
    human_approval=False,
    # Limits
    max_concurrent_executions=5,
    max_workflows=None,  # Unlimited in OSS
    telemetry_retention_days=7,
    # Plugins
    enabled_plugins=["logging", "metrics"],
)
