import requests
import json
import sys
sys.path.insert(0, '.')
from betista_scraper import extract_moneyline, extract_totals, build_odd_map, safe_get_team_names

# Buscar vários eventos
url = 'https://sb2frontend-altenar2.biahosted.com/api/widget/GetEvents?culture=pt-BR&timezoneOffset=0&integration=betista&deviceType=1&numFormat=en-GB&countryCode=PT&eventCount=0&sportId=66'
r = requests.get(url)
data = r.json()

# Pegar primeiros 10 eventos
all_event_ids = []
for date in data.get('dates', []):
    all_event_ids.extend(date.get('eventIds', []))

print(f"Testing first 10 of {len(all_event_ids)} total events...\n")

success_ml = 0
success_totals = 0
failed = []

for event_id in all_event_ids[:10]:
    url2 = f'https://sb2frontend-altenar2.biahosted.com/api/widget/GetEventDetails?culture=pt-BR&timezoneOffset=0&integration=betista&deviceType=1&numFormat=en-GB&countryCode=PT&showNonBoosts=false&eventId={event_id}'
    r2 = requests.get(url2)
    details = r2.json()
    
    odd_map = build_odd_map(details)
    ml = extract_moneyline(details, odd_map)
    totals = extract_totals(details)
    
    name = details.get('name', 'Unknown')
    ml_ok = ml is not None and all(v is not None for v in ml.values())
    totals_ok = len(totals) > 0
    
    status = "✅" if ml_ok and totals_ok else "⚠️" if ml_ok or totals_ok else "❌"
    
    if ml_ok:
        success_ml += 1
    if totals_ok:
        success_totals += 1
    
    print(f"{status} Event {event_id}: {name[:40]}")
    print(f"   ML: {ml if ml else 'None'}")
    print(f"   Totals: {len(totals)} lines - {[t['line'] for t in totals[:3]]}")
    print()

print("=" * 50)
print(f"Results: ML success={success_ml}/10, Totals success={success_totals}/10")
