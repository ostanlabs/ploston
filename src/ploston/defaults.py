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
    
    # Limits
    max_concurrent_workflows=5,
    max_workflow_steps=100,
)

