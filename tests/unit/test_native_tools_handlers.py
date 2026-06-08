"""Behavioral tests for the native-tools MCP server handlers (PL coverage push).

These tests invoke the *real* @mcp.tool handler functions in
``ploston.native_tools.server`` directly (via ``.fn``, the underlying callable
FastMCP wraps) and assert on the real output / error envelopes produced by the
``ploston_core.native_tools`` implementations. No mocking of the unit under
test — only filesystem temp dirs and (in the external-deps test module) the
genuine external clients are stubbed.

Scope here: data transforms, extraction, filesystem happy + edge paths, and the
network tools that don't require real outbound traffic. Security-policy wiring
is covered separately (test_native_tools_config_security.py /
integration/test_security.py) and is intentionally NOT duplicated here.
"""

from __future__ import annotations

import tempfile

import pytest
from ploston.native_tools import server as srv


# Every fs handler reads the module global WORKSPACE_DIR at call time, so a
# fixture that points it at a throwaway temp dir gives us a clean sandbox.
@pytest.fixture()
def workspace(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setattr(srv, "WORKSPACE_DIR", td)
        yield td


# =============================================================================
# Data transform tools
# =============================================================================


class TestDataValidate:
    @pytest.mark.asyncio
    async def test_valid_data_passes(self):
        schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
        result = await srv.data_validate.fn({"a": 1}, schema)
        assert result["success"] is True
        assert result["valid"] is True
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_invalid_data_reports_errors(self):
        schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
        result = await srv.data_validate.fn({"a": "not-an-int"}, schema)
        assert result["success"] is True
        assert result["valid"] is False
        assert result["errors"]
        assert "integer" in result["errors"][0]


class TestJsonCsvRoundTrip:
    @pytest.mark.asyncio
    async def test_json_to_csv_with_headers(self):
        result = await srv.data_json_to_csv.fn([{"a": 1, "b": 2}, {"a": 3, "b": 4}])
        assert result["success"] is True
        assert result["headers"] == ["a", "b"]
        assert result["row_count"] == 2
        assert "1,2" in result["csv_data"]

    @pytest.mark.asyncio
    async def test_json_to_csv_empty_list_errors(self):
        result = await srv.data_json_to_csv.fn([])
        assert result["success"] is False
        assert "non-empty list" in result["error"]

    @pytest.mark.asyncio
    async def test_csv_to_json_with_headers(self):
        result = await srv.data_csv_to_json.fn("a,b\n1,2\n3,4")
        assert result["success"] is True
        assert result["json_data"] == [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]
        assert result["headers"] == ["a", "b"]

    @pytest.mark.asyncio
    async def test_csv_to_json_without_headers_uses_generated_columns(self):
        result = await srv.data_csv_to_json.fn("1,2\n3,4", has_headers=False)
        assert result["success"] is True
        assert result["headers"] == ["column_0", "column_1"]
        assert result["json_data"][0] == {"column_0": "1", "column_1": "2"}


class TestJsonXmlRoundTrip:
    @pytest.mark.asyncio
    async def test_json_to_xml(self):
        result = await srv.data_json_to_xml.fn({"a": 1}, root_element="doc")
        assert result["success"] is True
        assert result["root_element"] == "doc"
        assert "<doc>" in result["xml_data"]
        assert "<a>1</a>" in result["xml_data"]

    @pytest.mark.asyncio
    async def test_xml_to_json(self):
        result = await srv.data_xml_to_json.fn("<root><a>1</a></root>")
        assert result["success"] is True
        assert result["json_data"] == {"root": {"a": "1"}}

    @pytest.mark.asyncio
    async def test_xml_to_json_malformed_returns_error_envelope(self):
        result = await srv.data_xml_to_json.fn("<root><a>1</")
        assert result["success"] is False
        assert "Invalid XML" in result["error"]


# =============================================================================
# Extraction tools
# =============================================================================


class TestExtractText:
    @pytest.mark.asyncio
    async def test_extract_from_html_strips_tags(self):
        result = await srv.extract_text.fn("<html><body>Hi <b>there</b></body></html>", "html")
        assert result["success"] is True
        assert result["source_type"] == "html"
        assert result["extracted_text"] == "Hi there"

    @pytest.mark.asyncio
    async def test_extract_from_json(self):
        result = await srv.extract_text.fn('{"a": 1}', "json")
        assert result["success"] is True
        assert result["source_type"] == "json"
        assert "1" in result["extracted_text"]

    @pytest.mark.asyncio
    async def test_extract_auto_plain_text(self):
        result = await srv.extract_text.fn("plain text here", "auto")
        assert result["success"] is True
        assert result["word_count"] == 3

    @pytest.mark.asyncio
    async def test_extract_markdown(self):
        result = await srv.extract_text.fn("# Title\ntext", "markdown")
        assert result["success"] is True
        assert result["source_type"] == "markdown"
        assert "Title" in result["extracted_text"]


class TestExtractStructured:
    @pytest.mark.asyncio
    async def test_regex_extraction_finds_matches(self):
        result = await srv.extract_structured.fn(
            "contact a@b.com today", {"email": r"[\w.]+@[\w.]+"}
        )
        assert result["success"] is True
        assert result["extracted_data"]["email"] == ["a@b.com"]
        assert result["fields_found"] == 1

    @pytest.mark.asyncio
    async def test_missing_field_reported(self):
        result = await srv.extract_structured.fn("no numbers here", {"digits": r"\d+"})
        assert result["success"] is True
        assert "digits" in result["fields_missing"]

    @pytest.mark.asyncio
    async def test_invalid_regex_returns_error_envelope(self):
        result = await srv.extract_structured.fn("x", {"bad": "("})
        assert result["success"] is False
        assert "failed" in result["error"].lower()


class TestExtractFileMetadata:
    @pytest.mark.asyncio
    async def test_metadata_for_existing_file(self, workspace):
        await _write(srv, "meta.txt", "abcdef")
        result = await srv.extract_file_metadata.fn("meta.txt")
        assert result["success"] is True
        assert result["file_size"] == 6
        assert result["file_name"] == "meta.txt"
        assert result["is_file"] is True

    @pytest.mark.asyncio
    async def test_metadata_missing_file_error(self, workspace):
        result = await srv.extract_file_metadata.fn("nope.txt")
        assert result["success"] is False
        assert "not found" in result["error"].lower()


# =============================================================================
# Filesystem tools (happy + edge; security paths covered elsewhere)
# =============================================================================


async def _write(srv_mod, path, content, **kw):
    """fs_write is sync; call it directly (handler is not a coroutine)."""
    return srv_mod.fs_write.fn(path, content, **kw)


class TestFilesystem:
    def test_write_then_read_text(self, workspace):
        wrote = srv.fs_write.fn("sub/a.txt", "hello")
        assert wrote["created"] is True
        assert wrote["size"] == 5

        read = srv.fs_read.fn("sub/a.txt")
        assert read["content"] == "hello"
        assert read["format"] == "text"

    def test_write_then_read_json(self, workspace):
        srv.fs_write.fn("d.json", {"k": 1}, format="json")
        read = srv.fs_read.fn("d.json", format="json")
        assert read["content"] == {"k": 1}

    def test_list_recursive_reports_files_and_dirs(self, workspace):
        srv.fs_write.fn("sub/a.txt", "x")
        srv.fs_write.fn("sub/b.txt", "y")
        listing = srv.fs_list.fn(".", recursive=True)
        names = {item["name"] for item in listing["items"]}
        assert "a.txt" in names
        assert "b.txt" in names
        assert listing["total_files"] == 2
        assert listing["total_dirs"] == 1

    def test_list_with_pattern_filter(self, workspace):
        srv.fs_write.fn("keep.log", "x")
        srv.fs_write.fn("skip.txt", "y")
        listing = srv.fs_list.fn(".", pattern="*.log")
        names = {item["name"] for item in listing["items"]}
        assert "keep.log" in names
        assert "skip.txt" not in names

    def test_read_missing_file_raises(self, workspace):
        with pytest.raises(FileNotFoundError):
            srv.fs_read.fn("ghost.txt")

    def test_delete_file(self, workspace):
        srv.fs_write.fn("temp.txt", "x")
        result = srv.fs_delete.fn("temp.txt")
        assert result["deleted"] is True
        with pytest.raises(FileNotFoundError):
            srv.fs_read.fn("temp.txt")

    def test_delete_missing_raises(self, workspace):
        with pytest.raises(FileNotFoundError):
            srv.fs_delete.fn("ghost.txt")

    def test_delete_nonempty_dir_requires_recursive(self, workspace):
        srv.fs_write.fn("d2/x.txt", "x")
        with pytest.raises(ValueError):
            srv.fs_delete.fn("d2")
        result = srv.fs_delete.fn("d2", recursive=True)
        assert result["deleted"] is True
        assert result["type"] == "directory"


# =============================================================================
# Network tools that don't need real outbound traffic
# =============================================================================


class TestNetworkPortCheck:
    @pytest.mark.asyncio
    async def test_closed_port_reports_not_open(self):
        # Port 1 on localhost is almost certainly closed; check_port maps the
        # refused/timeout connection into a successful "is_open=False" envelope.
        result = await srv.network_port_check.fn("127.0.0.1", 1, timeout=2)
        assert result["success"] is True
        assert result["is_open"] is False
        assert result["host"] == "127.0.0.1"
        assert result["port"] == 1

    @pytest.mark.asyncio
    async def test_invalid_port_rejected(self):
        result = await srv.network_port_check.fn("127.0.0.1", 0)
        assert result["success"] is False
        assert "port" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_open_port_detected(self):
        import asyncio

        server = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            result = await srv.network_port_check.fn("127.0.0.1", port, timeout=2)
            assert result["success"] is True
            assert result["is_open"] is True
        finally:
            server.close()
            await server.wait_closed()


class TestNetworkDnsLookup:
    @pytest.mark.asyncio
    async def test_localhost_resolves(self):
        result = await srv.network_dns_lookup.fn("localhost", "A")
        assert result["success"] is True
        assert any("127.0.0.1" in str(r) for r in result.get("records", []))

    @pytest.mark.asyncio
    async def test_unresolvable_hostname_errors(self):
        result = await srv.network_dns_lookup.fn("definitely-not-a-real-host.invalid", "A")
        assert result["success"] is False
