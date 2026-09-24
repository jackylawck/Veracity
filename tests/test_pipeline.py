import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from adapters.tna_adapter import TnaProductionAdapter
from scripts.circuit_breaker import RollingAnomalyGuard
import scripts.ingest as ingest_mod

MOCK_BATCH = [
    {"id": "C101", "reference": "PREM 19/1", "title": "Doc 1", "coveringDates": "1956"}
]

def test_html_unescape_and_clean():
    adapter = TnaProductionAdapter()
    raw = "<b>Diplomatic</b> Dispatch &amp; Assessment"
    assert adapter.clean_html_markup(raw) == "Diplomatic Dispatch & Assessment"

def test_pagination_loop_detection_prevents_duplicate_crawl(monkeypatch):
    adapter = TnaProductionAdapter()
    monkeypatch.setattr(adapter, "_execute_with_retry", lambda params: {"records": MOCK_BATCH})
    records = adapter.fetch_records(max_pages=3)
    assert len(records) == 1

def test_circuit_breaker_mutation_signal_surge():
    history = [2, 3, 4, 3, 2, 4, 3]
    guard = RollingAnomalyGuard(history)
    eval_res = guard.evaluate(current_mutations=60)
    assert eval_res["is_anomaly"] is True
    assert eval_res["severity"] == "CRITICAL"
    assert eval_res["action"] == "HALT_PIPELINE"

def test_atomic_write_raises_on_failure(tmp_path):
    protected_file = tmp_path / "protected.json"
    with patch("builtins.open", side_effect=PermissionError("Disk write denied")):
        with pytest.raises(IOError) as exc_info:
            ingest_mod.write_json_atomically(protected_file, {"test": 1})
        assert "Atomic write failure" in str(exc_info.value)
