import json

with open('examples/exports/tor_det_combined_report.json') as f:
    data = json.load(f)

yesavage = [p for p in data if 'Yesavage' in p.get('name', '')]
print(f'Yesavage found: {len(yesavage) > 0}')
for p in yesavage:
    print(f"  {p['name']}: ID {p.get('player_id')}")
    print(f"    Full entry: {json.dumps(p, indent=6)}")
