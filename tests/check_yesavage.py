import json
from pathlib import Path

report_path = Path(__file__).resolve().parents[1] / "examples" / "exports" / "tor_det_combined_report.json"
with report_path.open(encoding="utf-8") as f:
    data = json.load(f)

yesavage = [p for p in data if 'Yesavage' in p.get('name', '')]
print(f'Yesavage found: {len(yesavage) > 0}')
for p in yesavage:
    print(f"  {p['name']}: ID {p.get('player_id')}")
    print(f"    Full entry: {json.dumps(p, indent=6)}")
