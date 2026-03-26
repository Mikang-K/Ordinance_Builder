"""
Step 1: Raw HTTP Request
Purpose: Verify API key works, check actual response format, encoding, and structure.
Run: python -m pipeline_test.step1_raw_request
"""
import os
import re
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

OC = os.environ.get("LAW_API_KEY", "")
if not OC:
    print("[ERROR] LAW_API_KEY environment variable not set.")
    sys.exit(1)

HTTPS_BASE = "https://www.law.go.kr/DRF"
HTTP_BASE  = "http://www.law.go.kr/DRF"
HTTP_ROOT  = "http://www.law.go.kr"

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; LawApiTest/1.0)"})


def smart_get(url: str, params: dict, label: str) -> requests.Response:
    """
    GET request that handles two known failure modes:
      1. JS redirect (DDoS protection): parse redirect URL and re-request.
      2. ConnectionResetError: retry once with HTTPS -> HTTP fallback.
    """
    for attempt in range(2):
        try:
            r = session.get(url, params=params, timeout=15)
        except (requests.exceptions.ConnectionError, ConnectionResetError):
            if attempt == 0 and url.startswith("https://"):
                fallback = url.replace("https://", "http://")
                print(f"  [RETRY] ConnectionReset on HTTPS → retrying with HTTP: {fallback}")
                url = fallback
                continue
            raise

        # Detect JS redirect (DDoS protection page)
        ct = r.headers.get("Content-Type", "")
        is_json = "application/json" in ct or (r.text.strip().startswith("{"))
        is_xml  = "xml" in ct or (r.text.strip().startswith("<?xml") or r.text.strip().startswith("<법") or r.text.strip().startswith("<자치"))
        if is_json or is_xml:
            return r

        if r.status_code == 200 and "<script>" in r.text:
            # Parse: {o:'...', t:'...', h:'...'} and reassemble t+h+o
            m = re.search(r"\{o:'([^']*)',t:'([^']*)',h:'([^']*)'\}", r.text)
            if m:
                o, t, h = m.group(1), m.group(2), m.group(3)
                redirect_path = t + h + o
                redirect_url = HTTP_ROOT + redirect_path
                print(f"  [JS-REDIRECT] Detected. Following to: {redirect_url[:100]}")
                r2 = session.get(redirect_url, timeout=15)
                print(f"  [JS-REDIRECT] Status={r2.status_code}, CT={r2.headers.get('Content-Type','')}")
                return r2
            else:
                print(f"  [WARN] HTML response but no JS redirect pattern found for {label}")
                print(f"  Response snippet: {r.text[:300]}")

        return r
    return r  # fallback (should not reach)


# ─────────────────────────────────────────────
# Test A: 법령 목록 검색 (JSON)
# ─────────────────────────────────────────────
print("=" * 60)
print("[A] 법령 목록 검색 (JSON) — lawSearch.do HTTPS")
print("=" * 60)

params_a = {
    "OC": OC,
    "target": "law",
    "type": "JSON",
    "query": "지방자치법",
    "display": 3,
    "page": 1,
}

r_a = smart_get(f"{HTTPS_BASE}/lawSearch.do", params_a, "lawSearch")
print(f"Status     : {r_a.status_code}")
print(f"Encoding   : {r_a.encoding}")
print(f"Content-Type: {r_a.headers.get('Content-Type', 'N/A')}")
print(f"\n--- Raw text (first 1500 chars) ---")
print(r_a.text[:1500])

data_a = None
try:
    data_a = r_a.json()
    print(f"\n--- Top-level keys ---")
    print(list(data_a.keys()))
    for k, v in data_a.items():
        if isinstance(v, dict):
            print(f"  {k}: {list(v.keys())}")
        else:
            print(f"  {k}: {type(v).__name__} = {str(v)[:100]}")
except Exception as e:
    print(f"\n[FAIL] JSON parse failed: {e}")

# ─────────────────────────────────────────────
# Test B: 법령 전문 조회 (XML)
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("[B] 법령 전문 조회 (XML) — lawService.do")
print("=" * 60)

mst_to_use = None
detail_link = None

if data_a:
    try:
        law_list = data_a["LawSearch"]["law"]
        if isinstance(law_list, list) and law_list:
            first = law_list[0]
            print(f"First item fields : {list(first.keys())}")
            print(f"First item values : {first}")
            # Find MST
            for candidate in ["법령일련번호", "mst", "MST", "lsId"]:
                if candidate in first:
                    mst_to_use = first[candidate]
                    print(f"\n-> MST field='{candidate}', value={mst_to_use}")
                    break
            # Find detail_link
            for candidate in ["법령상세링크", "detailLink", "detail_link"]:
                if candidate in first:
                    detail_link = first[candidate]
                    print(f"-> detail_link field='{candidate}', value={detail_link}")
                    break
        else:
            print(f"[WARN] 'law' key is not a list: {type(law_list)}, value={law_list}")
    except KeyError as e:
        print(f"[FAIL] Unexpected JSON structure, missing key: {e}")
        print(f"  Actual structure: {data_a}")

if mst_to_use:
    # Try HTTPS first, smart_get will fallback to HTTP on ConnectionReset
    params_b = {"OC": OC, "target": "law", "type": "XML", "MST": mst_to_use}
    r_b = smart_get(f"{HTTPS_BASE}/lawService.do", params_b, "lawService")

    print(f"\nStatus     : {r_b.status_code}")
    print(f"Encoding   : {r_b.encoding}")
    print(f"Content-Type: {r_b.headers.get('Content-Type', 'N/A')}")
    print(f"\n--- Raw XML (first 2000 chars) ---")
    for enc in ["utf-8", "euc-kr", "cp949"]:
        try:
            decoded = r_b.content.decode(enc)
            print(f"(decoded as {enc})")
            break
        except UnicodeDecodeError:
            decoded = None
    if decoded:
        print(decoded[:2000])
    else:
        print(f"[WARN] Could not decode content. Raw bytes[:200]: {r_b.content[:200]}")
else:
    print("[SKIP] No MST available.")

print("\n[Done] Step 1 complete.")
