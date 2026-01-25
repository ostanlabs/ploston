#!/usr/bin/env python3
"""Migration verification script.

This script compares the AEL codebase with the Ploston packages
to identify any gaps in the migration.

Usage:
    python scripts/verify_migration.py [--verbose]
"""

import argparse
import importlib
import sys


def check_import_compatibility():
    """Check that key imports work."""
    results = []

    imports_to_check = [
        ("ploston_core", "PlostApplication"),
        ("ploston_core.config", "ConfigLoader"),
        ("ploston_core.engine", "WorkflowEngine"),
        ("ploston_core.registry", "ToolRegistry"),
        ("ploston_core.mcp_frontend", "MCPFrontend"),
        ("ploston_core.api.app", "create_rest_app"),
        ("ploston_core.types", "MCPTransport"),
        ("ploston.server", "main"),
        ("ploston.workflow", "WorkflowRegistry"),
    ]

    for module, attr in imports_to_check:
        try:
            mod = importlib.import_module(module)
            if hasattr(mod, attr):
                results.append((f"{module}.{attr}", "OK"))
            else:
                results.append((f"{module}.{attr}", "MISSING"))
        except ImportError as e:
            results.append((f"{module}.{attr}", f"IMPORT ERROR: {e}"))

    return results


def check_server_functionality():
    """Check that server can be created."""
    results = []

    try:
        from ploston_core import PlostApplication
        from ploston_core.types import MCPTransport

        _app = PlostApplication(
            transport=MCPTransport.HTTP,
            http_host="127.0.0.1",
            http_port=9999,
            with_rest_api=True,
        )
        results.append(("PlostApplication creation", "OK"))
        del _app  # Explicitly mark as used
    except Exception as e:
        results.append(("PlostApplication creation", f"ERROR: {e}"))

    return results


def main():
    parser = argparse.ArgumentParser(description="Verify AEL to Ploston migration")
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output",
    )
    _args = parser.parse_args()  # noqa: F841 - reserved for future verbose mode

    print("=" * 60)
    print("Migration Verification Report")
    print("=" * 60)
    print()

    # Check imports
    print("## Import Compatibility")
    print()
    import_results = check_import_compatibility()
    all_ok = True
    for name, status in import_results:
        icon = "✓" if status == "OK" else "✗"
        print(f"  {icon} {name}: {status}")
        if status != "OK":
            all_ok = False
    print()

    # Check server functionality
    print("## Server Functionality")
    print()
    server_results = check_server_functionality()
    for name, status in server_results:
        icon = "✓" if status == "OK" else "✗"
        print(f"  {icon} {name}: {status}")
        if status != "OK":
            all_ok = False
    print()

    # Summary
    print("=" * 60)
    if all_ok:
        print("✓ All checks passed!")
        return 0
    else:
        print("✗ Some checks failed. Review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
