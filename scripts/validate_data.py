import csv, json, pathlib, sys
base = pathlib.Path(__file__).resolve().parents[1]
csv_path = base / "data" / "soybean_resistance_qtl_collation.csv"
schema_path = base / "data" / "schema.json"
with csv_path.open(encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f)
    rows = list(reader)
fieldnames = reader.fieldnames or []
ids = [r.get("entry_id", "") for r in rows]
errors = []
if len(ids) != len(set(ids)):
    errors.append("entry_id values are not unique")
for i, entry_id in enumerate(ids, 2):
    if not entry_id.startswith("SOYRES-"):
        errors.append(f"row {i}: invalid entry_id {entry_id!r}")
if not rows:
    errors.append("no rows found")
print(f"records={len(rows)} fields={len(fieldnames)}")
print(f"target_groups={sorted(set(r.get('target_group','') for r in rows if r.get('target_group','')))}")
if errors:
    print("VALIDATION FAILED")
    for err in errors[:20]:
        print("-", err)
    sys.exit(1)
print("VALIDATION OK")
