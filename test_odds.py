import requests
import json

# Buscar evento primeiro
url = 'https://sb2frontend-altenar2.biahosted.com/api/widget/GetEvents?culture=pt-BR&timezoneOffset=0&integration=betista&deviceType=1&numFormat=en-GB&countryCode=PT&eventCount=0&sportId=66'
r = requests.get(url)
data = r.json()

# Pegar primeiro event ID
event_id = data['dates'][0]['eventIds'][0] if data.get('dates') else None
print(f'Event ID: {event_id}')

# Buscar detalhes
url2 = f'https://sb2frontend-altenar2.biahosted.com/api/widget/GetEventDetails?culture=pt-BR&timezoneOffset=0&integration=betista&deviceType=1&numFormat=en-GB&countryCode=PT&showNonBoosts=false&eventId={event_id}'
r2 = requests.get(url2)
details = r2.json()

print(f"Match: {details.get('name')}")
print(f"Competitors: {[c.get('name') for c in details.get('competitors', [])]}")

# Build odd map
odd_map = {o['id']: o for o in details.get('odds', [])}

# Procurar market 1X2 (typeId=1)
print("\n=== MARKET 1X2 (Moneyline) ===")
for market in details.get('markets', []):
    if market.get('typeId') == 1:
        print(f"Market name: {market.get('name')}, id={market.get('id')}")
        all_odds = market.get('desktopOddIds', []) or market.get('mobileOddIds', [])
        print(f"OddIds groups: {all_odds}")
        for grp in all_odds:
            for oid in grp:
                odd = odd_map.get(oid)
                if odd:
                    print(f"  Odd {oid}: name='{odd.get('name')}', price={odd.get('price')}, typeId={odd.get('typeId')}, competitorId={odd.get('competitorId')}")
        break

# Procurar totals
print("\n=== MARKET TOTALS (Over/Under) ===")
for market in details.get('markets', []):
    name = str(market.get('name', '')).lower()
    if 'total' in name or market.get('typeId') in (23, 199):
        print(f"Market name: {market.get('name')}, id={market.get('id')}, typeId={market.get('typeId')}")
        all_odds = market.get('desktopOddIds', []) or market.get('mobileOddIds', [])
        for grp in all_odds[:3]:  # Only first 3 groups
            for oid in grp[:4]:  # Only first 4 odds per group
                odd = odd_map.get(oid)
                if odd:
                    print(f"  Odd {oid}: name='{odd.get('name')}', price={odd.get('price')}, typeId={odd.get('typeId')}, sv={odd.get('sv')}, sn={odd.get('sn')}")
        break

# Save full details for analysis
with open('event_details_debug.json', 'w', encoding='utf-8') as f:
    json.dump(details, f, indent=2, ensure_ascii=False)
print("\n✅ Full details saved to event_details_debug.json")
