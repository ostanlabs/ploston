#!/bin/bash
# =============================================================================
# Ploston Docker Entrypoint
# =============================================================================
# Starts the Ploston server using the ploston-server command.
# =============================================================================

set -e

# Build command arguments
CMD_ARGS="--host ${AEL_HOST:-0.0.0.0} --port ${AEL_PORT:-8080}"

# Add config file if specified (check both PLOSTON_CONFIG_PATH and AEL_CONFIG)
CONFIG_FILE="${PLOSTON_CONFIG_PATH:-${AEL_CONFIG}}"
if [ -n "${CONFIG_FILE}" ]; then
    CMD_ARGS="--config ${CONFIG_FILE} ${CMD_ARGS}"
fi

# Execute the command using ploston-server
exec ploston-server ${CMD_ARGS}

