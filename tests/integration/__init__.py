"""
AEL Integration Tests

This package contains integration tests that verify multiple components
working together correctly.

Test Categories:
- WF-*   : Workflow engine tests
- TR-*   : Tool registry tests
- SEC-*  : Security/sandbox tests
- FE-*   : MCP frontend tests
- CLI-*  : CLI tests

Run all integration tests:
    pytest tests/integration/ -v

Run specific category:
    pytest tests/integration/ -m "security" -v
"""
