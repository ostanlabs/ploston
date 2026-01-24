"""API Property Tests using Schemathesis.

Tests API endpoints with generated data based on OpenAPI schema.
Requires a running server with OpenAPI docs enabled.
"""

import pytest
import schemathesis
from hypothesis import HealthCheck, Phase, settings
from schemathesis import Case

# Mark all tests in this module as requiring a running server
pytestmark = [
    pytest.mark.property,
    pytest.mark.api,
    pytest.mark.requires_server,
]


@pytest.fixture(scope="module")
def api_schema(request):
    """Load OpenAPI schema from running server or skip if unavailable."""
    import httpx

    # Try docker-compose first, then homelab
    urls = [
        "http://localhost:8082/openapi.json",
        "http://ploston.ostanlabs.homelab/openapi.json",
    ]

    for url in urls:
        try:
            response = httpx.get(url, timeout=5.0)
            if response.status_code == 200:
                return schemathesis.from_dict(response.json(), base_url=url.rsplit("/", 1)[0])
        except Exception:
            continue

    pytest.skip("No running server with OpenAPI schema available")


class TestAPISchemaValidation:
    """Test that API responses match OpenAPI schema."""

    def test_health_endpoint_schema(self, api_schema):
        """Health endpoint should match schema."""

        @api_schema.parametrize(endpoint="/health")
        @settings(
            max_examples=10,
            suppress_health_check=[HealthCheck.too_slow],
            phases=[Phase.explicit, Phase.generate],
        )
        def inner(case: Case):
            response = case.call()
            case.validate_response(response)

        inner()

    def test_info_endpoint_schema(self, api_schema):
        """Info endpoint should match schema."""

        @api_schema.parametrize(endpoint="/info")
        @settings(
            max_examples=10,
            suppress_health_check=[HealthCheck.too_slow],
            phases=[Phase.explicit, Phase.generate],
        )
        def inner(case: Case):
            response = case.call()
            case.validate_response(response)

        inner()


class TestAPIStability:
    """Test API stability with various inputs."""

    def test_tools_endpoint_stability(self, api_schema):
        """Tools endpoint should never crash."""

        @api_schema.parametrize(endpoint="/tools")
        @settings(
            max_examples=20,
            suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
            phases=[Phase.explicit, Phase.generate],
        )
        def inner(case: Case):
            response = case.call()

            # Should always return valid JSON
            assert response.headers.get("content-type", "").startswith("application/json")

            # Status should be expected
            assert response.status_code in [200, 400, 401, 404, 422, 500]

            # If error, should have error structure
            if response.status_code >= 400:
                data = response.json()
                assert "detail" in data or "error" in data or "message" in data

        inner()

    def test_workflows_endpoint_stability(self, api_schema):
        """Workflows endpoint should never crash."""

        @api_schema.parametrize(endpoint="/workflows")
        @settings(
            max_examples=20,
            suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
            phases=[Phase.explicit, Phase.generate],
        )
        def inner(case: Case):
            response = case.call()

            # Should always return valid JSON
            assert response.headers.get("content-type", "").startswith("application/json")

            # Status should be expected
            assert response.status_code in [200, 400, 401, 404, 422, 500]

        inner()


class TestAPIEdgeCases:
    """Test API edge cases and error handling."""

    def test_nonexistent_tool_returns_404(self, api_schema):
        """Requesting nonexistent tool should return 404."""
        import httpx

        base_url = api_schema.base_url
        response = httpx.get(f"{base_url}/tools/nonexistent_tool_12345")

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data or "error" in data

    def test_nonexistent_workflow_returns_404(self, api_schema):
        """Requesting nonexistent workflow should return 404."""
        import httpx

        base_url = api_schema.base_url
        response = httpx.get(f"{base_url}/workflows/nonexistent_workflow_12345")

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data or "error" in data

    def test_invalid_json_body_returns_422(self, api_schema):
        """Invalid JSON body should return 422."""
        import httpx

        base_url = api_schema.base_url
        response = httpx.post(
            f"{base_url}/workflows",
            content="not valid json",
            headers={"Content-Type": "application/json"},
        )

        # Should be 400 or 422 for invalid JSON
        assert response.status_code in [400, 422]

    def test_empty_body_handled(self, api_schema):
        """Empty body should be handled gracefully."""
        import httpx

        base_url = api_schema.base_url
        response = httpx.post(
            f"{base_url}/workflows", content="", headers={"Content-Type": "application/json"}
        )

        # Should be 400 or 422 for empty body
        assert response.status_code in [400, 422]
