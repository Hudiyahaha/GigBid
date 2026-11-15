"""Regression test: audit records larger than one read block (long LLM cover letters) must not break the chain."""

from mcp_servers.common import AuditLog


def test_audit_chain_survives_large_records(tmp_path, monkeypatch):
    import mcp_servers.common as common
    monkeypatch.setattr(common, "AUDIT_DIR", tmp_path)
    log = AuditLog("big")
    long_letter = "word " * 6000  # ~30 KB record, far above the 8 KB first read block
    for i in range(3):
        log.write("create_proposal_draft", {"cover_letter": long_letter, "i": i}, {"ok": True})
    ok, n = log.verify()
    assert ok and n == 3
