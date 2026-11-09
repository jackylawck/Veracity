"""
The Veracity // Autonomous Ingestion & Forensics Ledger Pipeline
自主公文採集引擎：動態載入主權檔案適配器、沙盒隔離執行、滑動統計斷路器防護與原子寫入。
（恪守認識論誠實原則：拒絕虛擬種子數據注入，真實反映 0 筆與異常狀態）
"""
import sys
import json
import logging
import inspect
import importlib
import pkgutil
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import adapters
from adapters.base import BaseAdapter
from scripts.circuit_breaker import RollingAnomalyGuard

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("Veracity.Ingest")

DATA_DIR = PROJECT_ROOT / "public" / "api"
DATA_DIR.mkdir(parents=True, exist_ok=True)

LEDGER_FILE = DATA_DIR / "records-latest.json"
HEALTH_FILE = DATA_DIR / "health.json"


def write_json_atomically(target_path: Path, payload: Dict[str, Any]) -> None:
    """原子化寫入 JSON 檔案，防止程序中斷導致損壞的半成品留在磁碟"""
    tmp_path = target_path.with_suffix(".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        tmp_path.replace(target_path)
    except Exception as err:
        if tmp_path.exists():
            tmp_path.unlink()
        logger.critical(f"Fatal I/O write error on {target_path}: {err}")
        raise IOError(f"Atomic write failure: {err}") from err


def discover_adapters() -> List[BaseAdapter]:
    """動態探索 adapters/ 目錄下繼承自 BaseAdapter 的模組類別"""
    loaded = []
    adapters_path = PROJECT_ROOT / "adapters"
    if not adapters_path.exists():
        logger.warning(f"Adapters directory not found at {adapters_path}")
        return loaded

    for _, module_name, is_pkg in pkgutil.iter_modules([str(adapters_path)]):
        if is_pkg or module_name in ("base", "__init__"):
            continue
        try:
            mod = importlib.import_module(f"adapters.{module_name}")
            for _, obj in inspect.getmembers(mod, inspect.isclass):
                if issubclass(obj, BaseAdapter) and obj is not BaseAdapter:
                    loaded.append(obj())
                    logger.info(f"[Plugin Engine] Loaded adapter class: {getattr(obj, 'NAME', obj.__name__)} from {module_name}.py")
        except Exception as err:
            logger.error(f"[Plugin Engine] Failed loading module {module_name}: {err}")
    return loaded


def main():
    dry_run = "--dry-run" in sys.argv
    logger.info(f"Starting Ingestion Pipeline (Dry Run: {dry_run})")

    # 1. 讀取現存總帳以進行增量去重
    existing_records: Dict[str, Any] = {}
    if LEDGER_FILE.exists():
        try:
            with open(LEDGER_FILE, "r", encoding="utf-8") as f:
                payload = json.load(f)
                for item in payload.get("records", []):
                    r_id = item.get("record_id")
                    if r_id:
                        existing_records[r_id] = item
            logger.info(f"Loaded {len(existing_records)} baseline records from existing ledger.")
        except Exception as e:
            logger.warning(f"Could not parse existing ledger: {e}")

    # 2. 讀取歷史變異數記錄（雙欄位容錯讀取）
    mutation_history = []
    if HEALTH_FILE.exists():
        try:
            with open(HEALTH_FILE, "r", encoding="utf-8") as f:
                prev_health = json.load(f)
                mutation_history = prev_health.get("mutation_history") or prev_health.get("metrics_history") or []
        except Exception as e:
            logger.warning(f"Could not parse previous health snapshot: {e}")

    # 3. 適配器探索
    discovered_adapters = discover_adapters()
    if not discovered_adapters:
        logger.critical("No valid adapters discovered in adapters/. Halting pipeline.")
        sys.exit(1)

    logger.info(f"Discovered {len(discovered_adapters)} adapter modules.")

    # 4. 隔離執行採集（落實零虛擬種子、如實記錄原則）
    raw_ingested = []
    active_contributors = []
    failed_adapters = []
    empty_adapters = []

    for adapter in discovered_adapters:
        adapter_name = getattr(adapter, "NAME", adapter.__class__.__name__)
        try:
            records = adapter.fetch_records()
            if records:
                valid_records = [r for r in records if isinstance(r, dict) and r.get("record_id")]
                raw_ingested.extend(valid_records)
                active_contributors.append(adapter_name)
                logger.info(f"[{adapter_name}] Successfully ingested {len(valid_records)} live items.")
            else:
                empty_adapters.append(adapter_name)
                logger.info(f"[{adapter_name}] Returned 0 records (Scaffold / Inactive window). Zero fallback injected.")
        except Exception as e:
            failed_adapters.append(adapter_name)
            logger.error(f"Sandbox Isolation Alert: [{adapter_name}] execution failed ({e}). Zero fallback injected.")

    # 5. 計算總帳實體變異數 (Mutations)
    mutations = 0
    for r in raw_ingested:
        r_id = r["record_id"]
        if r_id not in existing_records:
            existing_records[r_id] = r
            mutations += 1
        elif existing_records[r_id].get("fixity") != r.get("fixity"):
            existing_records[r_id] = r
            mutations += 1

    final_list = sorted(existing_records.values(), key=lambda x: str(x.get("record_id", "")))

    # 6. 冷啟動與空總帳誠實處理
    is_cold_start = len(final_list) == 0
    if is_cold_start:
        logger.warning("Ledger is empty (cold start / 0 active records). Honest UNINITIALIZED state accepted.")

    # 7. 統計斷路器評估（使用位置引數，由內部 BOOTSTRAP_PHASE 防護）
    guard = RollingAnomalyGuard(mutation_history)
    guard_eval = guard.evaluate(mutations)

    if guard_eval["is_anomaly"] and guard_eval.get("severity") == "CRITICAL":
        logger.critical(f"Circuit Breaker TRIPPED: {guard_eval.get('detail', 'Anomaly detected')}")
        if not dry_run:
            emergency_health = {
                "status": "circuit_breaker_tripped",
                "last_run_utc": datetime.now(timezone.utc).isoformat(),
                "total_records": len(existing_records),
                "mutations_this_run": mutations,
                "circuit_breaker": guard_eval,
                "mutation_history": mutation_history,
                "metrics_history": mutation_history,
                "failed_adapters": failed_adapters
            }
            write_json_atomically(HEALTH_FILE, emergency_health)
        sys.exit(2)

    updated_mutation_history = (mutation_history + [mutations])[-30:]

    # 8. 建構精確、不浮誇的健康狀態快照
    overall_status = "healthy"
    if is_cold_start:
        overall_status = "uninitialized"
    elif guard_eval["is_anomaly"]:
        overall_status = "warning"

    health_payload = {
        "status": overall_status,
        "last_successful_run_utc": datetime.now(timezone.utc).isoformat(),
        "total_records": len(final_list),
        "mutations_this_run": mutations,
        "circuit_breaker": guard_eval,
        "mutation_history": updated_mutation_history,
        "metrics_history": updated_mutation_history,
        "adapters_summary": {
            "total_discovered": len(discovered_adapters),
            "active_contributors": active_contributors,
            "empty_or_scaffolds": empty_adapters,
            "failed_adapters": failed_adapters
        },
        "active_pipeline_count": len(active_contributors),
        "maintainer_mode": "Solo-Maintainer-Audited"
    }

    # 9. 寫入總帳與健康快照
    if not dry_run:
        write_json_atomically(LEDGER_FILE, {"schema_version": "2.0.0", "records": final_list})
        write_json_atomically(HEALTH_FILE, health_payload)
        logger.info(
            f"Ledger committed successfully. Total: {len(final_list)} "
            f"(Net Mutations: {mutations}, Active Pipelines: {len(active_contributors)}/{len(discovered_adapters)})."
        )
    else:
        logger.info(
            f"[DRY-RUN] Verification complete. Total: {len(final_list)} items. "
            f"Mutations: {mutations}. Active: {len(active_contributors)}."
        )


if __name__ == "__main__":
    main()
