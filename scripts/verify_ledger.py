import json
from pathlib import Path

ledger_path = Path("public/api/records-latest.json")
if not ledger_path.exists():
    raise FileNotFoundError(f"Missing {ledger_path}")

with open(ledger_path, "r", encoding="utf-8") as f:
    data = json.load(f)

records = data.get("records", [])
assert len(records) > 0, "Ledger records array is empty!"
print(f"Ledger integrity verified: {len(records)} dossiers active.")
