"""Native Tools MCP Server.

This server exposes native tool implementations from ploston_core.native_tools
via the Model Context Protocol (MCP) using FastMCP.

The server can run in two modes:
1. stdio (for MCP client integration)
2. HTTP (for production deployment)
"""

# CRITICAL: Configure logging to stderr BEFORE any imports
# When running as MCP server with stdio transport, stdout is used for JSONRPC
# ALL logging must go to stderr to avoid polluting the JSONRPC channel
import logging
import sys

# Configure standard logging to stderr
root_logger = logging.getLogger()
root_logger.handlers.clear()
stderr_handler = logging.StreamHandler(sys.stderr)
stderr_handler.setFormatter(logging.Formatter("%(levelname)-8s [%(name)s] %(message)s"))
root_logger.addHandler(stderr_handler)
root_logger.setLevel(logging.DEBUG)

# Configure structlog to use stderr BEFORE any imports that use structlog
import structlog

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(colors=False),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

# Now safe to import other modules
import os
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP

# Reconfigure MCP library loggers to use stderr
for logger_name in ["mcp", "mcp.client", "mcp.server", "fastmcp"]:
    mcp_logger = logging.getLogger(logger_name)
    mcp_logger.handlers.clear()
    mcp_logger.addHandler(stderr_handler)
    mcp_logger.setLevel(logging.WARNING)

# Import core tool implementations from ploston_core
from ploston_core.native_tools import (
    analyze_sentiment,
    calculate_text_similarity,
    check_health_firecrawl,
    check_health_kafka,
    check_port,
    classify_text,
    consume_messages_kafka,
    create_topic_kafka,
    delete_file_or_directory,
    dns_lookup,
    extract_data_firecrawl,
    extract_metadata,
    extract_structured_data,
    # Extraction
    extract_text_content,
    # ML
    generate_text_embedding,
    list_directory_content,
    list_topics_kafka,
    # Network
    make_http_request,
    map_website_firecrawl,
    ping_host,
    # Kafka
    publish_message_kafka,
    # Filesystem
    read_file_content,
    # Firecrawl
    search_web_firecrawl,
    transform_csv_to_json,
    transform_json_to_csv,
    transform_json_to_xml,
    transform_xml_to_json,
    # Data
    validate_data_schema,
    write_file_content,
)

# Import Docker utilities
from ploston_core.native_tools.utils import (
    is_running_in_docker,
    resolve_kafka_servers_for_docker,
    resolve_url_for_docker,
)

# Import config manager for reactive config updates
from .config_manager import ToolConfig, get_config, get_config_manager

# Initialize FastMCP server
mcp = FastMCP("native-tools")

# =============================================================================
# Configuration - uses ConfigManager for reactive updates from Redis
# =============================================================================

# Get initial config from environment (ConfigManager handles this)
_cfg = get_config()

# These are accessed by tools - they get updated when config changes
WORKSPACE_DIR = _cfg.workspace_dir
FIRECRAWL_BASE_URL = _cfg.firecrawl_base_url
FIRECRAWL_API_KEY = _cfg.firecrawl_api_key
KAFKA_BOOTSTRAP_SERVERS = _cfg.kafka_bootstrap_servers
KAFKA_CLIENT_ID = _cfg.kafka_client_id
KAFKA_SECURITY_PROTOCOL = _cfg.kafka_security_protocol
KAFKA_SASL_MECHANISM = _cfg.kafka_sasl_mechanism
KAFKA_SASL_USERNAME = _cfg.kafka_sasl_username
KAFKA_SASL_PASSWORD = _cfg.kafka_sasl_password
OLLAMA_HOST = _cfg.ollama_host
DEFAULT_EMBEDDING_MODEL = _cfg.default_embedding_model


def _update_config_globals(new_config: ToolConfig) -> None:
    """Update global config variables when config changes.

    This is called by the ConfigManager when Redis publishes new config.
    """
    global WORKSPACE_DIR, FIRECRAWL_BASE_URL, FIRECRAWL_API_KEY
    global KAFKA_BOOTSTRAP_SERVERS, KAFKA_CLIENT_ID, KAFKA_SECURITY_PROTOCOL
    global KAFKA_SASL_MECHANISM, KAFKA_SASL_USERNAME, KAFKA_SASL_PASSWORD
    global OLLAMA_HOST, DEFAULT_EMBEDDING_MODEL

    WORKSPACE_DIR = new_config.workspace_dir
    FIRECRAWL_BASE_URL = new_config.firecrawl_base_url
    FIRECRAWL_API_KEY = new_config.firecrawl_api_key
    KAFKA_BOOTSTRAP_SERVERS = new_config.kafka_bootstrap_servers
    KAFKA_CLIENT_ID = new_config.kafka_client_id
    KAFKA_SECURITY_PROTOCOL = new_config.kafka_security_protocol
    KAFKA_SASL_MECHANISM = new_config.kafka_sasl_mechanism
    KAFKA_SASL_USERNAME = new_config.kafka_sasl_username
    KAFKA_SASL_PASSWORD = new_config.kafka_sasl_password
    OLLAMA_HOST = new_config.ollama_host
    DEFAULT_EMBEDDING_MODEL = new_config.default_embedding_model

    print(f"[Config] Updated configuration from Redis", file=sys.stderr)


# Register callback for config changes
get_config_manager().on_change(_update_config_globals)

# Log resolved configuration if in Docker
if is_running_in_docker():
    print(f"[Docker] FIRECRAWL_BASE_URL: {FIRECRAWL_BASE_URL}", file=sys.stderr)
    print(f"[Docker] KAFKA_BOOTSTRAP_SERVERS: {KAFKA_BOOTSTRAP_SERVERS}", file=sys.stderr)
    print(f"[Docker] OLLAMA_HOST: {OLLAMA_HOST}", file=sys.stderr)


# =============================================================================
# Filesystem Tools
# =============================================================================


@mcp.tool()
def fs_read(path: str, encoding: str = "utf-8", format: str = "text") -> Dict[str, Any]:
    """Read content from a file with format parsing."""
    return read_file_content(
        path=path, workspace_dir=WORKSPACE_DIR, encoding=encoding, format=format
    )


@mcp.tool()
def fs_write(
    path: str,
    content: Any,
    format: str = "text",
    encoding: str = "utf-8",
    overwrite: bool = True,
    create_dirs: bool = True,
) -> Dict[str, Any]:
    """Write content to a file with format serialization."""
    return write_file_content(
        path=path,
        content=content,
        workspace_dir=WORKSPACE_DIR,
        format=format,
        encoding=encoding,
        overwrite=overwrite,
        create_dirs=create_dirs,
    )


@mcp.tool()
def fs_list(
    path: str = ".",
    recursive: bool = False,
    pattern: Optional[str] = None,
    include_files: bool = True,
    include_dirs: bool = True,
    include_hidden: bool = False,
) -> Dict[str, Any]:
    """List directory contents with filtering options."""
    return list_directory_content(
        path=path,
        workspace_dir=WORKSPACE_DIR,
        recursive=recursive,
        pattern=pattern,
        include_files=include_files,
        include_dirs=include_dirs,
        include_hidden=include_hidden,
    )


@mcp.tool()
def fs_delete(path: str, recursive: bool = False) -> Dict[str, Any]:
    """Delete a file or directory."""
    return delete_file_or_directory(path=path, workspace_dir=WORKSPACE_DIR, recursive=recursive)


# =============================================================================
# Network Tools
# =============================================================================


@mcp.tool()
async def http_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    data: Optional[Any] = None,
    params: Optional[Dict[str, str]] = None,
    timeout: int = 30,
    max_retries: int = 3,
    retry_delay: int = 1,
) -> Dict[str, Any]:
    """Make HTTP requests with retry logic."""
    return await make_http_request(
        url=url,
        method=method,
        headers=headers,
        data=data,
        params=params,
        timeout=timeout,
        max_retries=max_retries,
        retry_delay=retry_delay,
    )


@mcp.tool()
async def network_ping(host: str, count: int = 4, timeout: int = 5) -> Dict[str, Any]:
    """Ping a host to check connectivity."""
    return await ping_host(host=host, count=count, timeout=timeout)


@mcp.tool()
async def network_dns_lookup(hostname: str, record_type: str = "A") -> Dict[str, Any]:
    """Perform DNS lookup for a hostname."""
    return await dns_lookup(hostname=hostname, record_type=record_type)


@mcp.tool()
async def network_port_check(host: str, port: int, timeout: int = 5) -> Dict[str, Any]:
    """Check if a port is open on a host."""
    return await check_port(host=host, port=port, timeout=timeout)


# =============================================================================
# Data Transformation Tools
# =============================================================================


@mcp.tool()
async def data_validate(data: Any, schema: Dict[str, Any]) -> Dict[str, Any]:
    """Validate data against a JSON schema."""
    return await validate_data_schema(data=data, schema=schema)


@mcp.tool()
async def data_json_to_csv(json_data: Any, include_headers: bool = True) -> Dict[str, Any]:
    """Transform JSON data to CSV format."""
    return await transform_json_to_csv(json_data=json_data, include_headers=include_headers)


@mcp.tool()
async def data_csv_to_json(csv_data: str, has_headers: bool = True) -> Dict[str, Any]:
    """Transform CSV data to JSON format."""
    return await transform_csv_to_json(csv_data=csv_data, has_headers=has_headers)


@mcp.tool()
async def data_json_to_xml(
    json_data: Any, root_element: str = "root", item_element: str = "item"
) -> Dict[str, Any]:
    """Transform JSON data to XML format."""
    return await transform_json_to_xml(
        json_data=json_data, root_element=root_element, item_element=item_element
    )


@mcp.tool()
async def data_xml_to_json(xml_data: str) -> Dict[str, Any]:
    """Transform XML data to JSON format."""
    return await transform_xml_to_json(xml_data=xml_data)


# =============================================================================
# Extraction Tools
# =============================================================================


@mcp.tool()
async def extract_text(source: str, extraction_type: str = "auto") -> Dict[str, Any]:
    """Extract text content from various sources."""
    return await extract_text_content(source=source, extraction_type=extraction_type)


@mcp.tool()
async def extract_structured(
    source: str, patterns: Dict[str, str], extraction_type: str = "regex"
) -> Dict[str, Any]:
    """Extract structured data using patterns."""
    return await extract_structured_data(
        source=source, patterns=patterns, extraction_type=extraction_type
    )


@mcp.tool()
async def extract_file_metadata(file_path: str) -> Dict[str, Any]:
    """Extract metadata from files."""
    return await extract_metadata(file_path=file_path, workspace_dir=WORKSPACE_DIR)


# =============================================================================
# Kafka Tools
# =============================================================================


@mcp.tool()
async def kafka_publish(
    topic: str, message: Any, key: Optional[str] = None, timeout: int = 30
) -> Dict[str, Any]:
    """Publish a message to a Kafka topic."""
    return await publish_message_kafka(
        topic=topic,
        message=message,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        client_id=KAFKA_CLIENT_ID,
        security_protocol=KAFKA_SECURITY_PROTOCOL,
        key=key,
        sasl_mechanism=KAFKA_SASL_MECHANISM,
        sasl_username=KAFKA_SASL_USERNAME,
        sasl_password=KAFKA_SASL_PASSWORD,
        timeout=timeout,
    )


@mcp.tool()
async def kafka_list_topics(timeout: int = 30) -> Dict[str, Any]:
    """List all Kafka topics."""
    return await list_topics_kafka(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        client_id=KAFKA_CLIENT_ID,
        security_protocol=KAFKA_SECURITY_PROTOCOL,
        sasl_mechanism=KAFKA_SASL_MECHANISM,
        sasl_username=KAFKA_SASL_USERNAME,
        sasl_password=KAFKA_SASL_PASSWORD,
        timeout=timeout,
    )


@mcp.tool()
async def kafka_create_topic(
    topic: str, num_partitions: int = 1, replication_factor: int = 1, timeout: int = 30
) -> Dict[str, Any]:
    """Create a new Kafka topic."""
    return await create_topic_kafka(
        topic=topic,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        client_id=KAFKA_CLIENT_ID,
        security_protocol=KAFKA_SECURITY_PROTOCOL,
        num_partitions=num_partitions,
        replication_factor=replication_factor,
        sasl_mechanism=KAFKA_SASL_MECHANISM,
        sasl_username=KAFKA_SASL_USERNAME,
        sasl_password=KAFKA_SASL_PASSWORD,
        timeout=timeout,
    )


@mcp.tool()
async def kafka_consume(
    topic: str, group_id: str = "mcp-consumer", max_messages: int = 10, timeout: int = 30
) -> Dict[str, Any]:
    """Consume messages from a Kafka topic."""
    return await consume_messages_kafka(
        topic=topic,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        client_id=KAFKA_CLIENT_ID,
        security_protocol=KAFKA_SECURITY_PROTOCOL,
        group_id=group_id,
        max_messages=max_messages,
        sasl_mechanism=KAFKA_SASL_MECHANISM,
        sasl_username=KAFKA_SASL_USERNAME,
        sasl_password=KAFKA_SASL_PASSWORD,
        timeout=timeout,
    )


@mcp.tool()
async def kafka_health(timeout: int = 10) -> Dict[str, Any]:
    """Check Kafka cluster health."""
    return await check_health_kafka(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        client_id=KAFKA_CLIENT_ID,
        security_protocol=KAFKA_SECURITY_PROTOCOL,
        sasl_mechanism=KAFKA_SASL_MECHANISM,
        sasl_username=KAFKA_SASL_USERNAME,
        sasl_password=KAFKA_SASL_PASSWORD,
        timeout=timeout,
    )


# =============================================================================
# ML Tools
# =============================================================================


@mcp.tool()
async def ml_embed_text(text: str, model: Optional[str] = None) -> Dict[str, Any]:
    """Generate text embeddings using Ollama."""
    return await generate_text_embedding(
        text=text, model=model or DEFAULT_EMBEDDING_MODEL, ollama_host=OLLAMA_HOST
    )


@mcp.tool()
async def ml_text_similarity(
    text1: str, text2: str, method: str = "cosine", model: Optional[str] = None
) -> Dict[str, Any]:
    """Calculate similarity between two texts."""
    return await calculate_text_similarity(
        text1=text1,
        text2=text2,
        method=method,
        model=model or DEFAULT_EMBEDDING_MODEL,
        ollama_host=OLLAMA_HOST,
    )


@mcp.tool()
async def ml_classify_text(
    text: str, categories: List[str], model: Optional[str] = None
) -> Dict[str, Any]:
    """Classify text into predefined categories."""
    return await classify_text(
        text=text,
        categories=categories,
        model=model or DEFAULT_EMBEDDING_MODEL,
        ollama_host=OLLAMA_HOST,
    )


@mcp.tool()
async def ml_analyze_sentiment(text: str, method: str = "lexicon") -> Dict[str, Any]:
    """Analyze sentiment of text."""
    return await analyze_sentiment(text=text, method=method)


# =============================================================================
# Firecrawl Tools
# =============================================================================


@mcp.tool()
async def firecrawl_search(
    query: str,
    limit: int = 10,
    sources: List[str] = ["web"],
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Search the web using Firecrawl."""
    return await search_web_firecrawl(
        query=query,
        base_url=FIRECRAWL_BASE_URL,
        api_key=FIRECRAWL_API_KEY,
        limit=limit,
        sources=sources,
        include_domains=include_domains or [],
        exclude_domains=exclude_domains or [],
    )


@mcp.tool()
async def firecrawl_map(
    url: str, limit: int = 1000, exclude_tags: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Map a website to discover all URLs."""
    return await map_website_firecrawl(
        url=url,
        base_url=FIRECRAWL_BASE_URL,
        api_key=FIRECRAWL_API_KEY,
        limit=limit,
        exclude_tags=exclude_tags,
    )


@mcp.tool()
async def firecrawl_extract(
    urls: List[str], schema: Optional[Dict[str, Any]] = None, prompt: Optional[str] = None
) -> Dict[str, Any]:
    """Extract structured data from URLs."""
    return await extract_data_firecrawl(
        urls=urls,
        base_url=FIRECRAWL_BASE_URL,
        api_key=FIRECRAWL_API_KEY,
        schema=schema,
        prompt=prompt,
    )


@mcp.tool()
async def firecrawl_health() -> Dict[str, Any]:
    """Check Firecrawl service health."""
    return await check_health_firecrawl(base_url=FIRECRAWL_BASE_URL)


# =============================================================================
# Health check endpoint
# =============================================================================


@mcp.tool()
async def health_check() -> Dict[str, Any]:
    """Check native-tools health status including Redis connection."""
    config_manager = get_config_manager()
    return {
        "status": "healthy",
        "service": "native-tools",
        **config_manager.get_health_status(),
    }


# =============================================================================
# Main entry point
# =============================================================================


async def start_with_redis() -> None:
    """Start the server with Redis config watcher."""
    import asyncio

    config_manager = get_config_manager()

    # Try to start Redis watcher (non-blocking if Redis not available)
    redis_started = await config_manager.start_redis_watcher()
    if redis_started:
        print("[Startup] Redis config watcher started", file=sys.stderr)
    else:
        print("[Startup] Running without Redis config watcher", file=sys.stderr)

    # Run the MCP server
    # Note: FastMCP's run() is blocking, so we can't easily integrate async
    # For now, the Redis watcher runs in the background via asyncio tasks


if __name__ == "__main__":
    import asyncio

    # Start Redis watcher before running MCP server
    asyncio.get_event_loop().run_until_complete(
        get_config_manager().start_redis_watcher()
    )

    # Run in HTTP mode by default for Docker deployment
    mcp.run(transport="http", host="0.0.0.0", port=8081)
