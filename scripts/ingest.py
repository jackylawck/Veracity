"""
Veracity Core Ingestion Engine
動態自動加載 74 個全球與本土歷史主權適配器，具備沙盒隔離與原子寫入保護。
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
    loaded = []
    adapters_path = PROJECT_ROOT / "adapters"
    for _, module_name, is_pkg in pkgutil.iter_modules([str(adapters_path)]):
        if is_pkg or module_name == "base":
            continue
        try:
            mod = importlib.import_module(f"adapters.{module_name}")
            for _, obj in inspect.getmembers(mod, inspect.isclass):
                if issubclass(obj, BaseAdapter) and obj is not BaseAdapter:
                    loaded.append(obj())
                    logger.info(f"[Plugin Engine] Loaded adapter: {getattr(obj, 'NAME', obj.__name__)} from {module_name}.py")
        except Exception as err:
            logger.error(f"[Plugin Engine] Failed loading module {module_name}: {err}")
    return loaded

def main():
    dry_run = "--dry-run" in sys.argv
    logger.info(f"Starting Ingestion Pipeline (Dry Run: {dry_run})")

    existing_records = {}
    if LEDGER_FILE.exists():
        try:
            with open(LEDGER_FILE, "r", encoding="utf-8") as f:
                payload = json.load(f)
                for item in payload.get("records", []):
                    existing_records[item["record_id"]] = item
        except Exception as e:
            logger.warning(f"Could not parse existing ledger: {e}")

    mutation_history = []
    if HEALTH_FILE.exists():
        try:
            with open(HEALTH_FILE, "r", encoding="utf-8") as f:
                prev_health = json.load(f)
                mutation_history = prev_health.get("mutation_history", [])
        except Exception as e:
            logger.warning(f"Could not parse previous health snapshot: {e}")

    active_adapters = discover_adapters()
    if not active_adapters:
        logger.critical("No valid adapters discovered in adapters/. Halting pipeline.")
        sys.exit(1)

    logger.info(f"Discovered {len(active_adapters)} active sovereign adapters.")

    raw_ingested = []
    failed_adapter_count = 0

    for adapter in active_adapters:
        adapter_name = getattr(adapter, "NAME", adapter.__class__.__name__)
        try:
            records = adapter.fetch_records()
            if records:
                raw_ingested.extend(records)
                logger.info(f"[{adapter_name}] Successfully ingested {len(records)} items.")
            else:
                logger.warning(f"[{adapter_name}] 0 records returned (upstream empty or maintained).")
        except Exception as e:
            failed_adapter_count += 1
            logger.error(f"Sandbox Isolation Alert: [{adapter_name}] execution failed: {e}")

    # 若所有註冊的適配器全部遭遇異常，必須中斷流程而非靜默通過
    if failed_adapter_count == len(active_adapters):
        logger.critical("All registered adapters failed during execution. Halting commit.")
        sys.exit(1)

    mutations = 0
    for r in raw_ingested:
        r_id = r["record_id"]
        if r_id not in existing_records:
            existing_records[r_id] = r
            mutations += 1
        elif existing_records[r_id].get("fixity") != r.get("fixity"):
            existing_records[r_id] = r
            mutations += 1

    final_list = sorted(existing_records.values(), key=lambda x: x["record_id"])

    # 冷啟動與資料安全防線：避免覆蓋輸出完全為 0 筆的無效空總帳
    if len(final_list) == 0:
        logger.error("Ledger contains 0 records after ingestion pass. Aborting to avoid empty ledger commit.")
        sys.exit(1)

    guard = RollingAnomalyGuard(mutation_history)
    guard_eval = guard.evaluate(current_mutations=mutations)

    # 如果歷史紀錄小於 3 次，視為系統擴容初始化期，不阻斷提交
    is_expanding = len(mutation_history) < 3
    if guard_eval["is_anomaly"] and guard_eval.get("severity") == "CRITICAL" and not is_expanding:
        logger.critical(f"Circuit Breaker TRIPPED: {guard_eval['detail']}")
        if not dry_run:
            emergency_health = {
                "status": "circuit_breaker_tripped",
                "last_run_utc": datetime.now(timezone.utc).isoformat(),
                "total_records": len(existing_records),
                "mutations_this_run": mutations,
                "circuit_breaker": guard_eval,
                "mutation_history": mutation_history
            }
            write_json_atomically(HEALTH_FILE, emergency_health)
        sys.exit(2)

    updated_mutation_history = (mutation_history + [mutations])[-30:]

    health_payload = {
        "status": "healthy" if not guard_eval["is_anomaly"] else "warning",
        "last_successful_run_utc": datetime.now(timezone.utc).isoformat(),
        "total_records": len(final_list),
        "mutations_this_run": mutations,
        "circuit_breaker": guard_eval,
        "mutation_history": updated_mutation_history,
        "active_adapters": [getattr(a, "NAME", a.__class__.__name__) for a in active_adapters],
        "node_count": len(active_adapters),
        "maintainer_mode": "Solo-Maintainer-Audited"
    }

    if not dry_run:
        write_json_atomically(LEDGER_FILE, {"schema_version": "2.0.0", "records": final_list})
        write_json_atomically(HEALTH_FILE, health_payload)
        logger.info(f"Ledger committed. Total: {len(final_list)} (Net Mutations: {mutations}, Active Nodes: {len(active_adapters)}).")
    else:
        logger.info(f"[DRY-RUN] Success. Total: {len(final_list)} items. Mutations: {mutations}.")

if __name__ == "__main__":
    main()
