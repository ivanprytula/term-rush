"""MCP server exposure tests (ADR-0020).

Proves the read/mutate split is actually enforced by fastapi-mcp's
operation-id filtering, not just asserted in a comment - the ADR itself
flags "read-only by default is a policy this ADR states, not something
fastapi-mcp enforces on its own" as a real risk if untested.
"""

from __future__ import annotations

from content_service.api.app import mcp


def test_mcp_exposes_only_the_read_only_tools() -> None:
    tool_names = {tool.name for tool in mcp.tools}

    assert tool_names == {"list_review_candidates", "search_document_chunks"}


def test_mcp_never_exposes_mutating_review_queue_operations() -> None:
    """approve/reject must never become MCP tools until real auth exists
    to gate them the way the REST API would (ADR-0020's stated risk).
    """
    tool_names = {tool.name for tool in mcp.tools}

    assert "approve_review_candidate" not in tool_names
    assert "reject_review_candidate" not in tool_names
    assert "submit_review_candidate" not in tool_names


def test_mcp_never_exposes_chunk_ingestion_or_embedding() -> None:
    """Only search is read-only-safe; ingest/embed mutate the corpus and
    aren't in ADR-0020's named tool list.
    """
    tool_names = {tool.name for tool in mcp.tools}

    assert "ingest_chunks" not in tool_names
    assert "embed_pending_chunks" not in tool_names
