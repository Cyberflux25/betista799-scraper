import requests
import json
import sys
sys.path.insert(0, '.')
from betista_scraper import extract_moneyline, extract_totals, build_odd_map, safe_get_team_names

# Buscar um evento real
url = 'https://sb2frontend-altenar2.biahosted.com/api/widget/GetEvents?culture=pt-BR&timezoneOffset=0&integration=betista&deviceType=1&numFormat=en-GB&countryCode=PT&eventCount=0&sportId=66'
r = requests.get(url)
data = r.json()
event_id = data['dates'][0]['eventIds'][0]

# Buscar detalhes
url2 = f'https://sb2frontend-altenar2.biahosted.com/api/widget/GetEventDetails?culture=pt-BR&timezoneOffset=0&integration=betista&deviceType=1&numFormat=en-GB&countryCode=PT&showNonBoosts=false&eventId={event_id}'
r2 = requests.get(url2)
details = r2.json()

print(f"=== Event: {details.get('name')} ===\n")

# Usar funções do scraper
odd_map = build_odd_map(details)
home, away = safe_get_team_names(details)
print(f"Home: {home}, Away: {away}")

# Test moneyline extraction
ml = extract_moneyline(details, odd_map)
print(f"\n=== EXTRACTED MONEYLINE ===")
print(f"ML extracted: {ml}")

# Compare with raw API odds
print(f"\n=== RAW API ODDS (1X2 Market) ===")
for market in details.get('markets', []):
    if market.get('typeId') == 1:
        all_odds = market.get('desktopOddIds', []) or market.get('mobileOddIds', [])
        for grp in all_odds:
            for oid in grp:
                odd = odd_map.get(oid)
                if odd:
                    print(f"  Odd ID {oid}: name='{odd.get('name')}', price={odd.get('price')}")
        break

# Test totals extraction
totals = extract_totals(details)
print(f"\n=== EXTRACTED TOTALS ===")
for t in totals[:5]:
    print(f"  Line {t['line']}: Over={t['over']}, Under={t['under']}")

# Compare with raw API odds for totals
print(f"\n=== RAW API ODDS (Totals Market) ===")
for market in details.get('markets', []):
    if market.get('typeId') == 18:
        print(f"Market ID: {market.get('id')}, Name: {market.get('name')}")
        all_odds = market.get('desktopOddIds', []) or market.get('mobileOddIds', [])
        for grp_idx, grp in enumerate(all_odds[:3]):
            for oid in grp[:4]:
                odd = odd_map.get(oid)
                if odd:
                    print(f"  Odd ID {oid}: name='{odd.get('name')}', price={odd.get('price')}, sv={odd.get('sv')}")
        break

print("\n=== CHECK: Does extracted match raw? ===")
if ml:
    print(f"Moneyline looks correct: {ml}")
print(f"Totals count: {len(totals)}")
