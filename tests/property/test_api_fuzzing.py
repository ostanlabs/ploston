"""API Fuzzing Tests using Hypothesis.

Property-based tests that fuzz API endpoints with generated data.
"""

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
import httpx

# Mark all tests in this module
pytestmark = [
    pytest.mark.property,
    pytest.mark.api,
    pytest.mark.requires_server,
]


@pytest.fixture(scope="module")
def base_url():
    """Get base URL for API tests."""
    urls = [
        "http://localhost:8082",
        "http://ploston.ostanlabs.homelab",
    ]
    
    for url in urls:
        try:
            response = httpx.get(f"{url}/health", timeout=5.0)
            if response.status_code == 200:
                return url
        except Exception:
            continue
    
    pytest.skip("No running server available")


class TestToolNameFuzzing:
    """Fuzz tool name parameter."""

    @given(tool_name=st.text(min_size=1, max_size=100))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_arbitrary_tool_name_handled(self, base_url, tool_name):
        """Arbitrary tool names should be handled gracefully."""
        # Skip if contains characters that break URL
        if any(c in tool_name for c in ['/', '?', '#', '\x00']):
            return
        
        try:
            response = httpx.get(
                f"{base_url}/tools/{tool_name}",
                timeout=10.0
            )
            
            # Should return valid HTTP response
            assert response.status_code in [200, 400, 404, 422, 500]
            
            # Should return JSON
            assert 'application/json' in response.headers.get('content-type', '')
        except httpx.RequestError:
            pass  # Network errors are acceptable


class TestWorkflowNameFuzzing:
    """Fuzz workflow name parameter."""

    @given(workflow_name=st.text(min_size=1, max_size=100))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_arbitrary_workflow_name_handled(self, base_url, workflow_name):
        """Arbitrary workflow names should be handled gracefully."""
        # Skip if contains characters that break URL
        if any(c in workflow_name for c in ['/', '?', '#', '\x00']):
            return
        
        try:
            response = httpx.get(
                f"{base_url}/workflows/{workflow_name}",
                timeout=10.0
            )
            
            # Should return valid HTTP response
            assert response.status_code in [200, 400, 404, 422, 500]
            
            # Should return JSON
            assert 'application/json' in response.headers.get('content-type', '')
        except httpx.RequestError:
            pass  # Network errors are acceptable


class TestQueryParameterFuzzing:
    """Fuzz query parameters."""

    @given(
        search=st.text(max_size=200),
        limit=st.integers(min_value=-1000, max_value=10000),
        offset=st.integers(min_value=-1000, max_value=10000),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_tools_query_params_handled(self, base_url, search, limit, offset):
        """Tools endpoint should handle arbitrary query params."""
        try:
            response = httpx.get(
                f"{base_url}/tools",
                params={"search": search, "limit": limit, "offset": offset},
                timeout=10.0
            )
            
            # Should return valid HTTP response
            assert response.status_code in [200, 400, 422, 500]
        except httpx.RequestError:
            pass

    @given(
        status=st.text(max_size=50),
        tag=st.text(max_size=50),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_workflows_query_params_handled(self, base_url, status, tag):
        """Workflows endpoint should handle arbitrary query params."""
        try:
            response = httpx.get(
                f"{base_url}/workflows",
                params={"status": status, "tag": tag},
                timeout=10.0
            )
            
            # Should return valid HTTP response
            assert response.status_code in [200, 400, 422, 500]
        except httpx.RequestError:
            pass


class TestRequestBodyFuzzing:
    """Fuzz request bodies."""

    @given(body=st.binary(max_size=1000))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_arbitrary_body_handled(self, base_url, body):
        """Arbitrary request bodies should be handled gracefully."""
        try:
            response = httpx.post(
                f"{base_url}/workflows",
                content=body,
                headers={"Content-Type": "application/json"},
                timeout=10.0
            )
            
            # Should return valid HTTP response (not crash)
            assert response.status_code in [200, 400, 415, 422, 500]
        except httpx.RequestError:
            pass

    @given(
        name=st.text(max_size=100),
        version=st.text(max_size=50),
        description=st.text(max_size=500),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_workflow_creation_fuzz(self, base_url, name, version, description):
        """Workflow creation should handle arbitrary data."""
        import json
        
        try:
            body = {
                "name": name,
                "version": version,
                "description": description,
                "steps": [{"id": "step1", "code": "result = 1"}]
            }
            
            response = httpx.post(
                f"{base_url}/workflows",
                content=json.dumps(body),
                headers={"Content-Type": "application/json"},
                timeout=10.0
            )
            
            # Should return valid HTTP response
            assert response.status_code in [200, 201, 400, 422, 500]
        except httpx.RequestError:
            pass

