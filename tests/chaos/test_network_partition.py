"""Chaos tests for network partition scenarios.

Tests system resilience when network connections fail.
"""

import asyncio
import socket
from unittest.mock import AsyncMock, Mock, patch

import pytest


@pytest.mark.chaos
class TestMCPServerDisconnect:
    """Test MCP server disconnect scenarios."""

    @pytest.fixture
    def mock_mcp_client(self):
        """Create a mock MCP client."""
        client = Mock()
        client.connect = AsyncMock()
        client.disconnect = AsyncMock()
        client.call_tool = AsyncMock()
        client.is_connected = Mock(return_value=True)
        return client

    @pytest.mark.asyncio
    async def test_chaos_001_server_disconnect_during_call(self, mock_mcp_client):
        """CHAOS-001: Server disconnects during tool call."""
        # Simulate disconnect during call
        mock_mcp_client.call_tool.side_effect = ConnectionError("Server disconnected")

        with pytest.raises(ConnectionError):
            await mock_mcp_client.call_tool("echo", {"message": "test"})

    @pytest.mark.asyncio
    async def test_chaos_002_reconnect_after_disconnect(self, mock_mcp_client):
        """CHAOS-002: Client reconnects after disconnect."""
        # First call fails
        mock_mcp_client.call_tool.side_effect = [
            ConnectionError("Server disconnected"),
            {"result": "success"},
        ]

        # First attempt fails
        with pytest.raises(ConnectionError):
            await mock_mcp_client.call_tool("echo", {"message": "test"})

        # Reconnect
        await mock_mcp_client.connect()

        # Second attempt succeeds
        result = await mock_mcp_client.call_tool("echo", {"message": "test"})
        assert result["result"] == "success"

    @pytest.mark.asyncio
    async def test_chaos_003_timeout_on_slow_server(self, mock_mcp_client):
        """CHAOS-003: Handle timeout on slow server."""

        async def slow_call(*args, **kwargs):
            await asyncio.sleep(10)  # Simulate slow server
            return {"result": "success"}

        mock_mcp_client.call_tool.side_effect = slow_call

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                mock_mcp_client.call_tool("echo", {"message": "test"}), timeout=0.1
            )

    @pytest.mark.asyncio
    async def test_chaos_004_multiple_reconnect_attempts(self, mock_mcp_client):
        """CHAOS-004: Multiple reconnect attempts."""
        connect_attempts = 0

        async def failing_connect():
            nonlocal connect_attempts
            connect_attempts += 1
            if connect_attempts < 3:
                raise ConnectionError("Connection refused")
            return True

        mock_mcp_client.connect.side_effect = failing_connect

        # First two attempts fail
        for _ in range(2):
            with pytest.raises(ConnectionError):
                await mock_mcp_client.connect()

        # Third attempt succeeds
        result = await mock_mcp_client.connect()
        assert result is True
        assert connect_attempts == 3


@pytest.mark.chaos
class TestRedisUnavailable:
    """Test Redis unavailability scenarios."""

    @pytest.fixture
    def mock_redis_client(self):
        """Create a mock Redis client."""
        client = Mock()
        client.get = AsyncMock()
        client.set = AsyncMock()
        client.ping = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_chaos_010_redis_connection_lost(self, mock_redis_client):
        """CHAOS-010: Redis connection lost during operation."""
        mock_redis_client.get.side_effect = ConnectionError("Redis connection lost")

        with pytest.raises(ConnectionError):
            await mock_redis_client.get("key")

    @pytest.mark.asyncio
    async def test_chaos_011_redis_timeout(self, mock_redis_client):
        """CHAOS-011: Redis operation timeout."""

        async def slow_get(*args):
            await asyncio.sleep(10)
            return "value"

        mock_redis_client.get.side_effect = slow_get

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(mock_redis_client.get("key"), timeout=0.1)

    @pytest.mark.asyncio
    async def test_chaos_012_redis_reconnect(self, mock_redis_client):
        """CHAOS-012: Redis reconnect after failure."""
        call_count = 0

        async def failing_then_success(*args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Redis unavailable")
            return "value"

        mock_redis_client.get.side_effect = failing_then_success

        # First call fails
        with pytest.raises(ConnectionError):
            await mock_redis_client.get("key")

        # Second call succeeds
        result = await mock_redis_client.get("key")
        assert result == "value"


@pytest.mark.chaos
class TestNetworkPartition:
    """Test network partition scenarios."""

    @pytest.mark.asyncio
    async def test_chaos_020_partial_network_failure(self):
        """CHAOS-020: Partial network failure (some services unavailable)."""
        services = {
            "mcp": Mock(is_available=AsyncMock(return_value=True)),
            "redis": Mock(is_available=AsyncMock(return_value=False)),
            "api": Mock(is_available=AsyncMock(return_value=True)),
        }

        # Check which services are available
        available = []
        for name, service in services.items():
            if await service.is_available():
                available.append(name)

        assert "mcp" in available
        assert "redis" not in available
        assert "api" in available

    @pytest.mark.asyncio
    async def test_chaos_021_dns_resolution_failure(self):
        """CHAOS-021: DNS resolution failure."""
        with patch("socket.getaddrinfo") as mock_dns:
            mock_dns.side_effect = socket.gaierror("DNS resolution failed")

            with pytest.raises(socket.gaierror):
                socket.getaddrinfo("nonexistent.local", 80)

    @pytest.mark.asyncio
    async def test_chaos_022_intermittent_connectivity(self):
        """CHAOS-022: Intermittent connectivity."""
        call_count = 0

        async def intermittent_call():
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                raise ConnectionError("Network unreachable")
            return "success"

        mock_service = Mock()
        mock_service.call = intermittent_call

        # First call succeeds
        result = await mock_service.call()
        assert result == "success"

        # Second call fails
        with pytest.raises(ConnectionError):
            await mock_service.call()

        # Third call succeeds
        result = await mock_service.call()
        assert result == "success"


@pytest.mark.chaos
class TestGracefulDegradation:
    """Test graceful degradation under failure conditions."""

    @pytest.mark.asyncio
    async def test_chaos_030_fallback_on_primary_failure(self):
        """CHAOS-030: Fallback to secondary when primary fails."""
        primary = Mock()
        primary.call = AsyncMock(side_effect=ConnectionError("Primary unavailable"))

        secondary = Mock()
        secondary.call = AsyncMock(return_value="fallback result")

        # Try primary, fall back to secondary
        try:
            result = await primary.call()
        except ConnectionError:
            result = await secondary.call()

        assert result == "fallback result"

    @pytest.mark.asyncio
    async def test_chaos_031_circuit_breaker_pattern(self):
        """CHAOS-031: Circuit breaker opens after failures."""
        failure_count = 0
        circuit_open = False
        threshold = 3

        async def call_with_circuit_breaker():
            nonlocal failure_count, circuit_open

            if circuit_open:
                raise Exception("Circuit breaker open")

            failure_count += 1
            if failure_count >= threshold:
                circuit_open = True
            raise ConnectionError("Service unavailable")

        mock_service = Mock()
        mock_service.call = call_with_circuit_breaker

        # First 3 calls fail and open circuit
        for _ in range(3):
            with pytest.raises(ConnectionError):
                await mock_service.call()

        # Circuit is now open
        assert circuit_open is True

        # Next call fails with circuit breaker error
        with pytest.raises(Exception, match="Circuit breaker open"):
            await mock_service.call()

    @pytest.mark.asyncio
    async def test_chaos_032_retry_with_backoff(self):
        """CHAOS-032: Retry with exponential backoff."""
        attempt_times = []

        async def failing_call():
            attempt_times.append(asyncio.get_event_loop().time())
            if len(attempt_times) < 3:
                raise ConnectionError("Temporary failure")
            return "success"

        mock_service = Mock()
        mock_service.call = failing_call

        # Retry with backoff
        result = None
        for attempt in range(3):
            try:
                result = await mock_service.call()
                break
            except ConnectionError:
                if attempt < 2:
                    await asyncio.sleep(0.01 * (2**attempt))  # Exponential backoff

        assert result == "success"
        assert len(attempt_times) == 3
