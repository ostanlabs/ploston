# AEL Integration Tests

This directory contains integration tests that verify multiple AEL components working together.

## Test Implementation Status

All tests have **actual implementation code** based on the component specs. Tests use try/except imports to gracefully skip when components aren't yet implemented.

## Test Categories

| Category | File | Tests | Prerequisite | Status |
|----------|------|-------|--------------|--------|
| Security | `test_security.py` | 25+ | Milestone M3 | ✅ Implemented |
| Tool Registry | `test_tool_registry.py` | 20+ | Milestone M1 | ✅ Implemented |
| Workflow Engine | `test_workflow_engine.py` | 25+ | Milestone M4 | ✅ Implemented |
| MCP Frontend | `test_mcp_frontend.py` | 15+ | Milestone M5 | ✅ Implemented |
| CLI | `test_cli.py` | 25+ | Milestone M5 | ✅ Implemented |

**Total: 110+ integration tests**

## Running Tests

```bash
# Run all integration tests
pytest tests/integration/ -v

# Run specific category
pytest tests/integration/ -m "security" -v
pytest tests/integration/ -m "workflow" -v
pytest tests/integration/ -m "registry" -v
pytest tests/integration/ -m "cli" -v
pytest tests/integration/ -m "frontend" -v

# Run excluding slow tests
pytest tests/integration/ -m "not slow" -v

# Run with coverage
pytest tests/integration/ --cov=ael --cov-report=html

# Run async tests only
pytest tests/integration/ -m "asyncio" -v
```

## Directory Structure

```
tests/integration/
├── __init__.py              # Package docstring
├── conftest.py              # Integration-specific fixtures
├── README.md                # This file
├── test_security.py         # SEC-* tests (sandbox security)
├── test_tool_registry.py    # TR-* tests (tool discovery, caching)
├── test_workflow_engine.py  # WF-* tests (workflow execution)
├── test_mcp_frontend.py     # FE-* tests (MCP server)
├── test_cli.py              # CLI-* tests (command line)
└── fixtures/
    ├── configs/
    │   └── test-config.yaml
    └── workflows/
        ├── simple-linear.yaml
        ├── code-step-test.yaml
        ├── dependencies-test.yaml
        ├── malicious/
        │   ├── import-os.yaml
        │   ├── import-subprocess.yaml
        │   ├── use-eval.yaml
        │   ├── use-exec.yaml
        │   └── use-open.yaml
        └── invalid/
            ├── missing-steps.yaml
            ├── bad-syntax.yaml
            └── unknown-tool.yaml
```

## How Tests Work

Tests are written with try/except imports:

```python
try:
    from ael.sandbox import PythonExecSandbox, SandboxConfig
    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False

class TestSecurity:
    @pytest.mark.asyncio
    async def test_sec_001_blocked_imports(self, ...):
        if not IMPORTS_AVAILABLE:
            pytest.skip("AEL sandbox module not yet implemented")
        
        # Actual test code that runs against real components
        result = await sandbox.execute(code, context)
        assert result.success is False
```

This approach means:
- Tests have **real implementation code** based on specs
- Tests **skip gracefully** if components don't exist yet
- Tests **run automatically** once components are implemented
- No need to update test code when components are ready

## Test Coverage by Milestone

### M1: Tool Discovery (Components 0-5)
- ✅ `test_tool_registry.py` - 20+ tests ready
- Tests: TR-001 to TR-011

### M2: Workflow Loading (+ Component 7)
- ✅ `test_workflow_engine.py` - WF-019, WF-020
- Basic workflow loading tests

### M3: Tool Execution (+ Components 6, 8, 9)
- ✅ `test_security.py` - 25+ tests ready
- Tests: SEC-001 to SEC-012

### M4: Workflow Execution (+ Component 10)
- ✅ `test_workflow_engine.py` - 25+ tests ready
- Tests: WF-001 to WF-018

### M5: Agent Integration (+ Components 11, 12)
- ✅ `test_mcp_frontend.py` - 15+ tests ready
- ✅ `test_cli.py` - 25+ tests ready
- Tests: FE-001 to FE-012, CLI-001 to CLI-020

## Test Markers

Tests use pytest markers for filtering:

```python
@pytest.mark.integration  # All integration tests
@pytest.mark.security     # Security/sandbox tests
@pytest.mark.workflow     # Workflow engine tests
@pytest.mark.registry     # Tool registry tests
@pytest.mark.frontend     # MCP frontend tests
@pytest.mark.cli          # CLI tests
@pytest.mark.slow         # Tests that take >5 seconds
@pytest.mark.asyncio      # Async tests
```

## Adding New Tests

1. Follow naming convention: `test_<category>_<number>_<description>`
2. Add appropriate markers: `@pytest.mark.integration`, `@pytest.mark.<category>`
3. Use try/except for imports to handle missing components
4. Document prerequisites in docstring
5. Use fixtures from `conftest.py` for common setup

Example:
```python
@pytest.mark.integration
@pytest.mark.security
@pytest.mark.asyncio
async def test_sec_013_new_security_check(self, sandbox, sandbox_context):
    """
    SEC-013: Verify new security check.
    
    Prerequisites: Component 8 (Sandbox)
    """
    check_imports()  # Skip if not available
    
    result = await sandbox.execute(malicious_code, sandbox_context)
    assert result.success is False
```
