#!/bin/bash
# =============================================================================
# Ploston Docker Entrypoint
# =============================================================================
# Starts the Ploston server using the ploston-server command.
# =============================================================================

set -e

# Build command arguments
CMD_ARGS="--host ${AEL_HOST:-0.0.0.0} --port ${AEL_PORT:-8080}"

# Add config file if specified
if [ -n "${AEL_CONFIG}" ]; then
    CMD_ARGS="--config ${AEL_CONFIG} ${CMD_ARGS}"
fi

# Execute the command using ploston-server
exec ploston-server ${CMD_ARGS}

