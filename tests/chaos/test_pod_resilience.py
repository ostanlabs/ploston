"""Chaos tests for pod failure and recovery.

These tests verify that Ploston recovers correctly when pods are
killed or restarted. They run against the homelab K8s infrastructure.

IMPORTANT: These tests should NEVER be skipped. If they fail,
the infrastructure or test must be fixed.
"""

import os
import subprocess
import time

import pytest
import requests

# Homelab configuration
HOMELAB_URL = os.environ.get("PLOSTON_URL", "http://ploston.ostanlabs.homelab")
NAMESPACE = os.environ.get("PLOSTON_NAMESPACE", "ploston")


@pytest.fixture(scope="module")
def kubectl_available():
    """Verify kubectl is available and can connect to cluster."""
    # Check kubectl is installed
    result = subprocess.run(["kubectl", "version", "--client"], capture_output=True, text=True)
    assert result.returncode == 0, "kubectl is not installed. Install kubectl to run chaos tests."

    # Check cluster connectivity
    result = subprocess.run(["kubectl", "cluster-info"], capture_output=True, text=True)
    assert result.returncode == 0, f"Cannot connect to Kubernetes cluster.\nError: {result.stderr}"

    return "kubectl"


@pytest.fixture(scope="module")
def ploston_pods_exist(kubectl_available):
    """Verify ploston pods exist in the cluster."""
    result = subprocess.run(
        ["kubectl", "get", "pods", "-n", NAMESPACE, "-l", "app=ploston", "-o", "name"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Cannot query ploston pods: {result.stderr}"
    assert result.stdout.strip(), (
        f"No ploston pods found in namespace '{NAMESPACE}'. Deploy Ploston first."
    )

    return result.stdout.strip().split("\n")


def wait_for_health(url: str, timeout: int = 60, interval: int = 5) -> tuple[bool, str]:
    """Wait for health endpoint to respond.

    Returns:
        Tuple of (success, last_error_message)
    """
    last_error = "No attempts made"
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            response = requests.get(f"{url}/health", timeout=5)
            if response.status_code == 200:
                return True, ""
            last_error = f"Health check returned status {response.status_code}"
        except requests.RequestException as e:
            last_error = str(e)
        time.sleep(interval)

    return False, last_error


def get_pod_status(namespace: str) -> str:
    """Get current pod status for debugging."""
    result = subprocess.run(
        ["kubectl", "get", "pods", "-n", namespace, "-o", "wide"], capture_output=True, text=True
    )
    return result.stdout if result.returncode == 0 else result.stderr


@pytest.mark.chaos
@pytest.mark.homelab
class TestPodResilience:
    """Test Ploston's resilience to pod failures."""

    def test_chaos_001_ploston_pod_restart_recovery(self, kubectl_available, ploston_pods_exist):
        """
        CHAOS-001: System recovers when Ploston pod is deleted.

        This test:
        1. Verifies system is healthy
        2. Deletes the ploston pod
        3. Waits for Kubernetes to reschedule
        4. Verifies system recovers
        """
        # Verify system is healthy before test
        healthy, error = wait_for_health(HOMELAB_URL, timeout=30)
        assert healthy, f"System not healthy before test: {error}"

        # Delete ploston pod (Kubernetes will reschedule)
        result = subprocess.run(
            [
                kubectl_available,
                "delete",
                "pod",
                "-n",
                NAMESPACE,
                "-l",
                "app=ploston",
                "--wait=false",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Failed to delete pod: {result.stderr}"

        # Wait for new pod to be scheduled and become ready
        # Give it more time since pod needs to pull image and start
        time.sleep(10)  # Initial wait for pod termination

        # Verify recovery
        healthy, error = wait_for_health(HOMELAB_URL, timeout=90, interval=5)

        if not healthy:
            pod_status = get_pod_status(NAMESPACE)
            pytest.fail(
                f"Ploston did not recover after pod restart.\n"
                f"Last error: {error}\n"
                f"Pod status:\n{pod_status}"
            )

    def test_chaos_002_native_tools_pod_restart(self, kubectl_available):
        """
        CHAOS-002: System handles native-tools pod restart.

        Native-tools provides HTTP and other tools. When it restarts,
        Ploston should reconnect automatically.
        """
        # Verify system is healthy
        healthy, error = wait_for_health(HOMELAB_URL, timeout=30)
        assert healthy, f"System not healthy before test: {error}"

        # Delete native-tools pod
        result = subprocess.run(
            [
                kubectl_available,
                "delete",
                "pod",
                "-n",
                NAMESPACE,
                "-l",
                "app=native-tools",
                "--wait=false",
            ],
            capture_output=True,
            text=True,
        )
        # native-tools might not exist, that's OK
        if result.returncode != 0 and "not found" not in result.stderr.lower():
            pytest.fail(f"Failed to delete native-tools pod: {result.stderr}")

        # Wait for recovery
        time.sleep(15)

        # Verify ploston is still healthy
        healthy, error = wait_for_health(HOMELAB_URL, timeout=60)
        assert healthy, f"Ploston not healthy after native-tools restart: {error}"

    def test_chaos_003_redis_pod_restart(self, kubectl_available):
        """
        CHAOS-003: System handles Redis pod restart.

        Redis is used for caching/state. System should handle
        temporary Redis unavailability gracefully.
        """
        # Verify system is healthy
        healthy, error = wait_for_health(HOMELAB_URL, timeout=30)
        assert healthy, f"System not healthy before test: {error}"

        # Delete redis pod (try both possible names)
        for label in ["app=ploston-redis", "app=redis"]:
            result = subprocess.run(
                [kubectl_available, "delete", "pod", "-n", NAMESPACE, "-l", label, "--wait=false"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                break

        # Wait for recovery
        time.sleep(15)

        # Verify ploston is still healthy
        healthy, error = wait_for_health(HOMELAB_URL, timeout=60)
        assert healthy, f"Ploston not healthy after Redis restart: {error}"


@pytest.mark.chaos
@pytest.mark.homelab
class TestConcurrentRequests:
    """Test system behavior under load during chaos."""

    def test_chaos_010_requests_during_pod_restart(self, kubectl_available, ploston_pods_exist):
        """
        CHAOS-010: Requests during pod restart are handled gracefully.

        Some requests may fail during restart, but:
        1. No requests should hang indefinitely
        2. System should recover quickly
        3. Errors should be clear (not 500 with stack trace)
        """
        import concurrent.futures

        # Verify system is healthy
        healthy, error = wait_for_health(HOMELAB_URL, timeout=30)
        assert healthy, f"System not healthy before test: {error}"

        errors = []
        successes = []

        def make_request():
            try:
                response = requests.get(f"{HOMELAB_URL}/health", timeout=10)
                if response.status_code == 200:
                    return "success"
                else:
                    return f"error:{response.status_code}"
            except requests.RequestException as e:
                return f"exception:{type(e).__name__}"

        # Start making requests in background
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            # Submit initial requests
            futures = [executor.submit(make_request) for _ in range(10)]

            # Delete pod while requests are in flight
            subprocess.run(
                [
                    kubectl_available,
                    "delete",
                    "pod",
                    "-n",
                    NAMESPACE,
                    "-l",
                    "app=ploston",
                    "--wait=false",
                ],
                capture_output=True,
            )

            # Submit more requests during restart
            for _ in range(20):
                futures.append(executor.submit(make_request))
                time.sleep(0.5)

            # Collect results
            for future in concurrent.futures.as_completed(futures, timeout=60):
                result = future.result()
                if result == "success":
                    successes.append(result)
                else:
                    errors.append(result)

        # Wait for full recovery
        time.sleep(30)
        healthy, error = wait_for_health(HOMELAB_URL, timeout=60)

        # Assertions
        assert healthy, f"System did not recover: {error}"
        # Some errors during restart are expected, but not all
        assert len(successes) > 0, "No successful requests during test"
        # After recovery, requests should succeed
        response = requests.get(f"{HOMELAB_URL}/health", timeout=10)
        assert response.status_code == 200, "System not healthy after test"
