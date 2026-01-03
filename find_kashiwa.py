import requests
import json

# Buscar todos os eventos
url = 'https://sb2frontend-altenar2.biahosted.com/api/widget/GetEvents?culture=pt-BR&timezoneOffset=0&integration=betista&deviceType=1&numFormat=en-GB&countryCode=PT&eventCount=0&sportId=66'
r = requests.get(url)
data = r.json()

# Pegar todos os event IDs
all_event_ids = []
for date in data.get('dates', []):
    all_event_ids.extend(date.get('eventIds', []))

print(f"Total events: {len(all_event_ids)}")

# Procurar Kashiwa Reysol
for event_id in all_event_ids[:100]:
    url2 = f'https://sb2frontend-altenar2.biahosted.com/api/widget/GetEventDetails?culture=pt-BR&timezoneOffset=0&integration=betista&deviceType=1&numFormat=en-GB&countryCode=PT&showNonBoosts=false&eventId={event_id}'
    r2 = requests.get(url2)
    details = r2.json()
    name = details.get('name', '')
    if 'kashiwa' in name.lower() or 'gamba' in name.lower():
        print(f"\n=== FOUND: {name} (ID: {event_id}) ===")
        print(f"Competitors: {[c.get('name') for c in details.get('competitors', [])]}")
        
        # Build odd map
        odd_map = {o['id']: o for o in details.get('odds', [])}
        
        # Procurar market 1X2
        print("\n=== MARKET 1X2 (Moneyline) ===")
        for market in details.get('markets', []):
            if market.get('typeId') == 1:
                all_odds = market.get('desktopOddIds', []) or market.get('mobileOddIds', [])
                for grp in all_odds:
                    for oid in grp:
                        odd = odd_map.get(oid)
                        if odd:
                            print(f"  {odd.get('name')}: price={odd.get('price')}")
                break
        
        # Procurar totals
        print("\n=== MARKET TOTALS (Over/Under) ===")
        for market in details.get('markets', []):
            name_m = str(market.get('name', '')).lower()
            if 'total' in name_m and market.get('typeId') == 18:
                all_odds = market.get('desktopOddIds', []) or market.get('mobileOddIds', [])
                for grp in all_odds:
                    for oid in grp:
                        odd = odd_map.get(oid)
                        if odd and odd.get('sv') == 2.5:
                            print(f"  {odd.get('name')}: price={odd.get('price')}, sv={odd.get('sv')}")
                break
        
        # Salvar
        with open(f'kashiwa_details.json', 'w', encoding='utf-8') as f:
            json.dump(details, f, indent=2, ensure_ascii=False)
        print("\n✅ Saved to kashiwa_details.json")
        break
