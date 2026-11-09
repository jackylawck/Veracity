import json
import sys
from pathlib import Path
import jsonschema
from jsonschema import Draft7Validator

SCHEMA_PATH = Path("schemas/record.schema.json")
LEDGER_PATH = Path("public/api/records-latest.json")

def verify_ledger() -> None:
    # 1. 總帳實體檔案檢查
    if not LEDGER_PATH.exists():
        print(f"❌ Error: Ledger file not found at {LEDGER_PATH}", file=sys.stderr)
        sys.exit(1)

    # 2. JSON 解析防禦
    try:
        data = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"❌ Error: Ledger is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error reading ledger: {e}", file=sys.stderr)
        sys.exit(1)

    # 3. 根節點型別防衛
    if not isinstance(data, dict):
        print(f"❌ Error: Ledger root must be a JSON object, got {type(data).__name__}", file=sys.stderr)
        sys.exit(1)

    # 4. 精確區分「欄位缺失」與「欄位非陣列」
    if "records" not in data:
        print("❌ Error: Mandatory field 'records' is missing from ledger root.", file=sys.stderr)
        sys.exit(1)

    records = data["records"]
    if not isinstance(records, list):
        print(f"❌ Error: 'records' field must be a JSON array, got {type(records).__name__}", file=sys.stderr)
        sys.exit(1)

    # 5. 誠實對待冷啟動：0 筆為合法 UNINITIALIZED 狀態，非合約失敗
    if len(records) == 0:
        print("ℹ️ Ledger is empty (cold start / 0 dossiers).")
        print("   Status: UNINITIALIZED — Verified valid empty state, not a failure.")
        sys.exit(0)

    # 6. Schema 契約必須強制存在，拒絕靜默略過
    if not SCHEMA_PATH.exists():
        print(f"❌ Error: {SCHEMA_PATH} not found. Schema is a mandatory gatekeeper contract.", file=sys.stderr)
        sys.exit(1)

    # 7. 迴圈外預檢 Schema 本身合法性
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft7Validator.check_schema(schema)
    except json.JSONDecodeError as e:
        print(f"❌ Error: Schema file is invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)
    except jsonschema.exceptions.SchemaError as e:
        print(f"❌ Error: Invalid JSONSchema definition: {e.message}", file=sys.stderr)
        sys.exit(1)

    # 8. 逐筆公文實例完整性驗證
    for idx, record in enumerate(records):
        try:
            jsonschema.validate(instance=record, schema=schema)
        except jsonschema.exceptions.ValidationError as e:
            print(f"❌ Schema validation failed on record [{idx}]: {e.message}", file=sys.stderr)
            sys.exit(1)

    print(f"✅ Schema validation passed: {len(records)} dossiers strictly conform to {SCHEMA_PATH}")

if __name__ == "__main__":
    verify_ledger()
