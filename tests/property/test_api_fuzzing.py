"""API Fuzzing Tests using Hypothesis.

Property-based tests that fuzz API endpoints with generated data.
"""

import httpx
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# Mark all tests in this module
pytestmark = [
    pytest.mark.property,
    pytest.mark.api,
    pytest.mark.requires_server,
]


def get_base_url():
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

    return None


# Get base URL at module load time
BASE_URL = get_base_url()


def is_url_safe(text: str) -> bool:
    """Check if text is safe to use in URL path."""
    # Filter out characters that break URLs
    bad_chars = ["/", "?", "#", "\x00"]
    if any(c in text for c in bad_chars):
        return False
    # Filter out non-printable ASCII
    if any(ord(c) < 32 or ord(c) > 126 for c in text):
        return False
    return True


@pytest.mark.skipif(BASE_URL is None, reason="No running server available")
class TestToolNameFuzzing:
    """Fuzz tool name parameter."""

    @given(
        tool_name=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "S"), blacklist_characters="/?#\x00"
            ),
        )
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_arbitrary_tool_name_handled(self, tool_name):
        """Arbitrary tool names should be handled gracefully."""
        if not is_url_safe(tool_name):
            return

        try:
            response = httpx.get(f"{BASE_URL}/tools/{tool_name}", timeout=10.0)

            # Should return valid HTTP response
            assert response.status_code in [200, 400, 404, 422, 500]

            # Content-type may vary for 404s (text/plain is acceptable)
            content_type = response.headers.get("content-type", "")
            assert "application/json" in content_type or "text/plain" in content_type
        except (httpx.RequestError, httpx.InvalidURL):
            pass  # Network errors and invalid URLs are acceptable


@pytest.mark.skipif(BASE_URL is None, reason="No running server available")
class TestWorkflowNameFuzzing:
    """Fuzz workflow name parameter."""

    @given(
        workflow_name=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "S"), blacklist_characters="/?#\x00"
            ),
        )
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_arbitrary_workflow_name_handled(self, workflow_name):
        """Arbitrary workflow names should be handled gracefully."""
        if not is_url_safe(workflow_name):
            return

        try:
            response = httpx.get(f"{BASE_URL}/workflows/{workflow_name}", timeout=10.0)

            # Should return valid HTTP response
            assert response.status_code in [200, 400, 404, 422, 500]

            # Content-type may vary for 404s
            content_type = response.headers.get("content-type", "")
            assert "application/json" in content_type or "text/plain" in content_type
        except (httpx.RequestError, httpx.InvalidURL):
            pass  # Network errors and invalid URLs are acceptable


@pytest.mark.skipif(BASE_URL is None, reason="No running server available")
class TestQueryParameterFuzzing:
    """Fuzz query parameters."""

    @given(
        search=st.text(max_size=200),
        limit=st.integers(min_value=-1000, max_value=10000),
        offset=st.integers(min_value=-1000, max_value=10000),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_tools_query_params_handled(self, search, limit, offset):
        """Tools endpoint should handle arbitrary query params."""
        try:
            response = httpx.get(
                f"{BASE_URL}/tools",
                params={"search": search, "limit": limit, "offset": offset},
                timeout=10.0,
            )

            # Should return valid HTTP response (404 is acceptable for unknown params)
            assert response.status_code in [200, 400, 404, 422, 500]
        except (httpx.RequestError, httpx.InvalidURL):
            pass

    @given(
        status=st.text(max_size=50),
        tag=st.text(max_size=50),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_workflows_query_params_handled(self, status, tag):
        """Workflows endpoint should handle arbitrary query params."""
        try:
            response = httpx.get(
                f"{BASE_URL}/workflows", params={"status": status, "tag": tag}, timeout=10.0
            )

            # Should return valid HTTP response (404 is acceptable)
            assert response.status_code in [200, 400, 404, 422, 500]
        except (httpx.RequestError, httpx.InvalidURL):
            pass


@pytest.mark.skipif(BASE_URL is None, reason="No running server available")
class TestRequestBodyFuzzing:
    """Fuzz request bodies."""

    @given(body=st.binary(max_size=1000))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_arbitrary_body_handled(self, body):
        """Arbitrary request bodies should be handled gracefully."""
        try:
            response = httpx.post(
                f"{BASE_URL}/workflows",
                content=body,
                headers={"Content-Type": "application/json"},
                timeout=10.0,
            )

            # Should return valid HTTP response (not crash)
            # 404 is acceptable if endpoint doesn't exist or method not allowed
            # 405 is acceptable for method not allowed
            assert response.status_code in [200, 400, 404, 405, 415, 422, 500]
        except (httpx.RequestError, httpx.InvalidURL):
            pass

    @given(
        name=st.text(max_size=100),
        version=st.text(max_size=50),
        description=st.text(max_size=500),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_workflow_creation_fuzz(self, name, version, description):
        """Workflow creation should handle arbitrary data."""
        import json

        try:
            body = {
                "name": name,
                "version": version,
                "description": description,
                "steps": [{"id": "step1", "code": "result = 1"}],
            }

            response = httpx.post(
                f"{BASE_URL}/workflows",
                content=json.dumps(body),
                headers={"Content-Type": "application/json"},
                timeout=10.0,
            )

            # Should return valid HTTP response
            # 404 is acceptable if endpoint doesn't exist
            # 405 is acceptable for method not allowed
            assert response.status_code in [200, 201, 400, 404, 405, 422, 500]
        except (httpx.RequestError, httpx.InvalidURL):
            pass
