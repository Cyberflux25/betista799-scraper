import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import concurrent.futures as cf
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, JavascriptException, TimeoutException, NoSuchElementException

# Silence known harmless UC __del__ warnings on Windows
try:
	if hasattr(uc.Chrome, "__del__"):
		def _uc_silent_del(self):
			try:
				# Avoid calling quit/sleep in __del__ to prevent WinError noise
				pass
			except Exception:
				pass
		uc.Chrome.__del__ = _uc_silent_del  # type: ignore[attr-defined]
except Exception:
	pass


BETISTA_HOME_URL = "https://www.betista799.com/"
ALTENAR_API_BASE = "https://sb2frontend-altenar2.biahosted.com/api/widget"

# Defaults based on user's provided payload
DEFAULT_EVENTS_QUERY = (
	"culture=pt-BR&timezoneOffset=0&integration=betista&deviceType=1"
	"&numFormat=en-GB&countryCode=PT&eventCount=0&sportId=0"
)

DEFAULT_DETAILS_QUERY = (
	"culture=pt-BR&timezoneOffset=0&integration=betista&deviceType=1"
	"&numFormat=en-GB&countryCode=PT&showNonBoosts=false"
)

DEFAULT_SPORT_MENU_QUERY = (
	"culture=pt-BR&timezoneOffset=0&integration=betista&deviceType=1"
	"&numFormat=en-GB&countryCode=PT&period=0"
)


class BetistaScraper:
	def __init__(self, headless: bool = True, timeout_sec: int = 30) -> None:
		self.headless = headless
		self.timeout_sec = timeout_sec
		print(f"🚀 Launching Chrome (headless={self.headless})...", flush=True)
		self.driver = self._init_driver()
		self.session = requests.Session()
		self.session.headers.update({
			"Accept": "application/json, text/plain, */*",
			"Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
			"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari",
		})

	def _init_driver(self):
		options = Options()
		if self.headless:
			# Use new headless mode
			options.add_argument("--headless=new")
		options.add_argument("--disable-gpu")
		options.add_argument("--no-sandbox")
		options.add_argument("--disable-dev-shm-usage")
		options.add_argument("--window-size=1280,1024")
		options.add_argument("--lang=pt-BR")
		# Use generally safe flags only
		options.add_argument("--disable-blink-features=AutomationControlled")

		driver = uc.Chrome(options=options)
		driver.set_page_load_timeout(self.timeout_sec)
		return driver

	def ensure_origin(self) -> None:
		print("🌐 Opening homepage…", flush=True)
		self.driver.get(BETISTA_HOME_URL)
		# Wait for body presence to ensure page fully initialised
		WebDriverWait(self.driver, self.timeout_sec).until(
			EC.presence_of_element_located((By.TAG_NAME, "body"))
		)
		print("✅ Homepage loaded.", flush=True)

	@retry(
		stop=stop_after_attempt(3),
		wait=wait_exponential(multiplier=1, min=1, max=4),
		retry=retry_if_exception_type((WebDriverException, JavascriptException)),
		reraise=True,
	)
	def _browser_fetch_json(self, url: str) -> Dict[str, Any]:
		script = """
const url = arguments[0];
const done = arguments[arguments.length - 1];
try {
	fetch(url, {
		method: 'GET',
		credentials: 'include',
		headers: { 'Accept': 'application/json, text/plain, */*' }
	})
		.then(r => r.json())
		.then(j => done(JSON.stringify({ ok: true, data: j })))
		.catch(err => done(JSON.stringify({ ok: false, error: String(err) })));
} catch (e) {
	done(JSON.stringify({ ok: false, error: String(e) }));
}
"""
		raw = self.driver.execute_async_script(script, url)
		if not isinstance(raw, str):
			raise JavascriptException(f"Unexpected return type from fetch script: {type(raw)}")
		payload = json.loads(raw)
		if not payload.get("ok"):
			raise JavascriptException(f"Fetch failed: {payload.get('error')}")
		return payload["data"]

	def _navigate_fetch_json(self, url: str) -> Dict[str, Any]:
		# Reuse a single API tab to reduce overhead
		if not hasattr(self, "_api_tab_handle") or self._api_tab_handle is None:
			main_handle = self.driver.current_window_handle
			self.driver.switch_to.new_window('tab')
			self._api_tab_handle = self.driver.current_window_handle
			self._main_handle = main_handle
		main_handle = getattr(self, "_main_handle", self.driver.current_window_handle)
		self.driver.switch_to.window(self._api_tab_handle)
		try:
			self.driver.get(url)
			# Wait for document complete
			WebDriverWait(self.driver, self.timeout_sec).until(
				lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
			)
			# Prefer <pre> tag that Chrome uses for JSON, else body
			text_content = None
			try:
				pre = WebDriverWait(self.driver, 2).until(
					EC.presence_of_element_located((By.TAG_NAME, "pre"))
				)
				text_content = pre.text
			except TimeoutException:
				try:
					body = self.driver.find_element(By.TAG_NAME, "body")
					text_content = body.text
				except NoSuchElementException:
					pass
			if not text_content:
				raise JavascriptException("No content returned from navigation fetch")
			return json.loads(text_content)
		finally:
			# Switch back to main handle
			try:
				self.driver.switch_to.window(main_handle)
			except Exception:
				pass

	def get_events(self) -> Dict[str, Any]:
		url = f"{ALTENAR_API_BASE}/GetEvents?{DEFAULT_EVENTS_QUERY}"
		try:
			# Prefer direct HTTP for performance
			return self._http_get_json(url)
		except Exception:
			print("↪️ Fetch failed for events, using navigation fallback…", flush=True)
			return self._navigate_fetch_json(url)

	def get_events_for_cat(self, cat_id: int) -> Dict[str, Any]:
		url = f"{ALTENAR_API_BASE}/GetEvents?{DEFAULT_EVENTS_QUERY}&catIds={cat_id}"
		try:
			return self._http_get_json(url)
		except Exception:
			print(f"↪️ Fetch failed for cat {cat_id}, using navigation fallback…", flush=True)
			return self._navigate_fetch_json(url)

	def get_sport_menu(self) -> Dict[str, Any]:
		url = f"{ALTENAR_API_BASE}/GetSportMenu?{DEFAULT_SPORT_MENU_QUERY}"
		try:
			return self._http_get_json(url)
		except Exception:
			print("↪️ Fetch failed for sport menu, using navigation fallback…", flush=True)
			return self._navigate_fetch_json(url)

	def get_event_details(self, event_id: int) -> Dict[str, Any]:
		url = f"{ALTENAR_API_BASE}/GetEventDetails?{DEFAULT_DETAILS_QUERY}&eventId={event_id}"
		try:
			return self._http_get_json(url)
		except Exception:
			print(f"↪️ Fetch failed for event {event_id}, using navigation fallback…", flush=True)
			return self._navigate_fetch_json(url)

	@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=0.5, max=3), reraise=True)
	def _http_get_json(self, url: str) -> Dict[str, Any]:
		resp = self.session.get(url, timeout=self.timeout_sec)
		resp.raise_for_status()
		return resp.json()

	def close(self) -> None:
		try:
			self.driver.quit()
		except Exception:
			pass
		finally:
			self.driver = None


def flatten_event_ids(events_payload: Dict[str, Any]) -> List[int]:
	event_ids: List[int] = []
	for day in events_payload.get("dates", []):
		for eid in day.get("eventIds", []):
			if isinstance(eid, int):
				event_ids.append(eid)
	return event_ids

def extract_soccer_cat_ids(menu_payload: Dict[str, Any]) -> List[int]:
	cat_ids: List[int] = []
	for sport in menu_payload.get("sports", []):
		# Match by name "Futebol" and/or known soccer id 66
		name = str(sport.get("name", "")).strip().lower()
		sport_id = sport.get("id")
		if name == "futebol" or sport_id == 66:
			for cid in sport.get("catIds", []):
				if isinstance(cid, int):
					cat_ids.append(cid)
			break
	return cat_ids


def build_odd_map(event_details: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
	odd_map: Dict[int, Dict[str, Any]] = {}
	for odd in event_details.get("odds", []):
		oid = odd.get("id")
		if isinstance(oid, int):
			odd_map[oid] = odd
	return odd_map


def safe_get_team_names(event_details: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
	competitors = event_details.get("competitors", [])
	home = competitors[0]["name"] if len(competitors) > 0 else None
	away = competitors[1]["name"] if len(competitors) > 1 else None
	return home, away


def safe_get_team_ids(event_details: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
	competitors = event_details.get("competitors", [])
	home_id = competitors[0]["id"] if len(competitors) > 0 else None
	away_id = competitors[1]["id"] if len(competitors) > 1 else None
	return home_id, away_id


def extract_moneyline(event_details: Dict[str, Any], odd_map: Dict[int, Dict[str, Any]]) -> Optional[Dict[str, Optional[float]]]:
	# Market typeId 1 is 1x2 (ML)
	for market in event_details.get("markets", []):
		if market.get("typeId") == 1:
			groups: List[List[int]] = market.get("desktopOddIds") or market.get("mobileOddIds") or []
			# Some implementations put all three in the first group
			candidates: List[int] = []
			for grp in groups:
				candidates.extend([oid for oid in grp if isinstance(oid, int)])
			# Filter to unique and resolve odds by their 'name'
			ml = {"home": None, "draw": None, "away": None}
			home_name, away_name = safe_get_team_names(event_details)
			home_id, away_id = safe_get_team_ids(event_details)
			home_name_l = (home_name or "").strip().lower()
			away_name_l = (away_name or "").strip().lower()

			for oid in candidates:
				odd = odd_map.get(oid)
				if not odd:
					continue
				name_raw = str(odd.get("name", "")).strip()
				name = name_raw.lower()
				price = odd.get("price")
				if price is None:
					continue

				# 1) Prefer competitorId mapping when present
				comp_id = odd.get("competitorId")
				if isinstance(comp_id, int):
					if home_id is not None and comp_id == home_id:
						ml["home"] = float(price)
						if ml["away"] is not None and ml["draw"] is not None:
							break
						continue
					if away_id is not None and comp_id == away_id:
						ml["away"] = float(price)
						if ml["home"] is not None and ml["draw"] is not None:
							break
						continue

				# 2) Detect draw by name or selection typeId == 2
				if name in ("x", "empate", "draw") or odd.get("typeId") == 2:
					ml["draw"] = float(price)
					if ml["home"] is not None and ml["away"] is not None:
						break
					continue

				# 3) Match by team names
				if home_name_l and name == home_name_l:
					ml["home"] = float(price)
					if ml["away"] is not None and ml["draw"] is not None:
						break
					continue
				if away_name_l and name == away_name_l:
					ml["away"] = float(price)
					if ml["home"] is not None and ml["draw"] is not None:
						break
					continue

				# 4) Fallback to conventional labels
				if name in ("1", "casa", "home"):
					ml["home"] = float(price)
				elif name in ("x", "empate", "draw"):
					ml["draw"] = float(price)
				elif name in ("2", "fora", "away"):
					ml["away"] = float(price)

			# If we got at least one, return
			if any(v is not None for v in ml.values()):
				return ml
	return None


def extract_totals(event_details: Dict[str, Any]) -> List[Dict[str, Any]]:
	# Odds typeId: 12 (Mais de / Over), 13 (Menos de / Under)
	totals_by_line: Dict[str, Dict[str, Any]] = {}
	for odd in event_details.get("odds", []):
		ot = odd.get("typeId")
		if ot not in (12, 13):
			continue
		line = str(odd.get("sv") or odd.get("sn") or "").strip()
		if not line:
			continue
		rec = totals_by_line.setdefault(line, {"line": line, "over": None, "under": None})
		price = odd.get("price")
		if price is None:
			continue
		name = str(odd.get("name", "")).lower()
		if ot == 12 or "mais de" in name or "over" in name:
			rec["over"] = float(price)
		elif ot == 13 or "menos de" in name or "under" in name:
			rec["under"] = float(price)
	# Return sorted by numeric line when possible
	def parse_line(v: str) -> float:
		try:
			return float(v.replace("+", ""))
		except Exception:
			return float("inf")
	return sorted(totals_by_line.values(), key=lambda r: parse_line(str(r["line"])))


def extract_handicaps(event_details: Dict[str, Any]) -> List[Dict[str, Any]]:
	results: List[Dict[str, Any]] = []
	odd_map = build_odd_map(event_details)
	for market in event_details.get("markets", []):
		if market.get("typeId") != 16:
			continue
		line = str(market.get("sv") or market.get("sn") or "").strip()
		if not line:
			# Fall back to searching by odds' sv later
			pass
		groups: List[List[int]] = market.get("desktopOddIds") or market.get("mobileOddIds") or []
		if len(groups) < 2:
			# Need two sides; skip unreliable market
			continue
		home_ids = [oid for oid in groups[0] if isinstance(oid, int)]
		away_ids = [oid for oid in groups[1] if isinstance(oid, int)]

		def select_price(candidates: List[int], desired_line: Optional[str]) -> Optional[float]:
			# Prefer odds matching the exact line ('sv')
			for oid in candidates:
				odd = odd_map.get(oid)
				if not odd:
					continue
				price = odd.get("price")
				if price is None:
					continue
				if desired_line:
					sv = str(odd.get("sv") or odd.get("sn") or "").strip()
					if sv == desired_line:
						return float(price)
			# Fallback to first available
			for oid in candidates:
				odd = odd_map.get(oid)
				if odd and odd.get("price") is not None:
					return float(odd["price"])
			return None

		home_price = select_price(home_ids, line if line else None)
		away_price = select_price(away_ids, line if line else None)
		if home_price is None and away_price is None:
			continue
		results.append({"line": line if line else None, "home": home_price, "away": away_price})

	# Deduplicate by line (keep first occurrence)
	seen: set = set()
	deduped: List[Dict[str, Any]] = []
	for rec in results:
		key = rec.get("line") or f"{rec.get('home')}-{rec.get('away')}"
		if key in seen:
			continue
		seen.add(key)
		deduped.append(rec)
	return deduped


def build_output_event(event_details: Dict[str, Any]) -> Dict[str, Any]:
	odd_map = build_odd_map(event_details)
	home, away = safe_get_team_names(event_details)
	champ = (event_details.get("champ") or {}).get("name")
	category = (event_details.get("category") or {}).get("name")

	return {
		"eventId": event_details.get("id"),
		"name": event_details.get("name"),
		"league": champ,
		"category": category,
		"home": home,
		"away": away,
		"markets": {
			"ml": extract_moneyline(event_details, odd_map),
			"totals": extract_totals(event_details),
			"handicap": extract_handicaps(event_details),
		},
	}


def maybe_conform_to_template(output_data: Dict[str, Any], template_path: Optional[str]) -> Dict[str, Any]:
	"""
	If an example JSON exists, attempt to conform key naming at the top-level.
	This keeps compatibility with an external expected schema without strictly knowing it.
	"""
	if not template_path or not os.path.exists(template_path):
		return output_data
	try:
		with open(template_path, "r", encoding="utf-8") as f:
			template = json.load(f)
	except Exception:
		return output_data
	# If template has an 'events' array, keep our structure; otherwise just return as-is
	if isinstance(template, dict) and "events" in template:
		return output_data
	return output_data


def run(headless: bool, limit: int, output_path: str, template_path: Optional[str], workers: int) -> None:
	scraper = BetistaScraper(headless=headless)
	try:
		t0 = time.time()
		print("🔧 Starting scrape…", flush=True)
		scraper.ensure_origin()

		print("🏷️ Fetching sport menu…", flush=True)
		menu = scraper.get_sport_menu()
		cat_ids = extract_soccer_cat_ids(menu)
		print(f"⚽ Found {len(cat_ids)} soccer categories.", flush=True)

		all_event_ids: List[int] = []
		seen: set = set()
		for idx, cid in enumerate(cat_ids, start=1):
			print(f"🔎 [{idx}/{len(cat_ids)}] Fetching events for cat {cid}…", flush=True)
			events_payload = scraper.get_events_for_cat(cid)
			dates = events_payload.get("dates", [])
			found_ids = flatten_event_ids(events_payload)
			added = 0
			for eid in found_ids:
				if eid not in seen:
					seen.add(eid)
					all_event_ids.append(eid)
					added += 1
			print(f"📅 cat {cid}: {len(dates)} date buckets, 🎫 {len(found_ids)} ids, ➕ {added} new.", flush=True)

		print(f"🎟️ Total unique event IDs: {len(all_event_ids)}", flush=True)
		if limit > 0:
			all_event_ids = all_event_ids[:limit]
			print(f"✂️ Limiting to first {len(all_event_ids)} events.", flush=True)
		results: List[Dict[str, Any]] = []

		def fetch_and_parse(eid: int) -> Optional[Dict[str, Any]]:
			try:
				print(f"🎯 Event {eid}: fetching details…", flush=True)
				details = scraper.get_event_details(eid)
				event_obj = build_output_event(details)
				markets = event_obj.get("markets", {})
				ml_present = markets.get("ml") is not None
				totals_count = len(markets.get("totals", []) or [])
				handicap_count = len(markets.get("handicap", []) or [])
				print(
					f"✅ Event {eid}: parsed [ML={'yes' if ml_present else 'no'}, Totals={totals_count}, Handicap={handicap_count}]",
					flush=True
				)
				return event_obj
			except Exception as e:
				print(f"⚠️ Event {eid}: failed to fetch/parse: {e}", flush=True)
				return None

		workers = max(1, min(workers, 16))
		print(f"🧵 Fetching details with up to {workers} workers…", flush=True)
		with cf.ThreadPoolExecutor(max_workers=workers) as executor:
			for event_obj in executor.map(fetch_and_parse, all_event_ids):
				if event_obj:
					results.append(event_obj)

		output_obj = {
			"source": "betista799",
			"fetched_at": datetime.now(timezone.utc).isoformat(),
			"events": results,
		}
		output_obj = maybe_conform_to_template(output_obj, template_path)
		with open(output_path, "w", encoding="utf-8") as f:
			json.dump(output_obj, f, ensure_ascii=False, indent=2)
		elapsed = time.time() - t0
		print(f"💾 Wrote {len(results)} events to {output_path}", flush=True)
		print(f"🏁 Done in {elapsed:.1f}s.", flush=True)
	finally:
		scraper.close()


def parse_args(argv: List[str]) -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Scrape next soccer matches odds from betista799 using Selenium + undetected_chromedriver.")
	parser.add_argument("--no-headless", action="store_true", help="Run the browser in non-headless mode.")
	parser.add_argument("--limit", type=int, default=50, help="Maximum number of events to fetch (0 = no limit).")
	parser.add_argument("--output", type=str, default="output.json", help="Path to write the output JSON.")
	parser.add_argument("--template", type=str, default=None, help="Path to @outputExample.json to mirror top-level shape if needed.")
	parser.add_argument("--workers", type=int, default=6, help="Number of parallel workers for event details (1-16).")
	return parser.parse_args(argv)


if __name__ == "__main__":
	args = parse_args(sys.argv[1:])
	run(
		headless=not args.no_headless,
		limit=args.limit,
		output_path=args.output,
		template_path=args.template,
		workers=args.workers,
	)

