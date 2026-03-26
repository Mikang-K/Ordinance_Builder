"""
Step 2: Law List JSON Parsing
Purpose: Verify that the JSON key paths in law_api_client.py match the actual API response.
Run: python pipeline_test/step2_list_parse.py
"""
import os
import sys
import requests
import json
from dotenv import load_dotenv

load_dotenv()

OC = os.environ.get("LAW_API_KEY", "")
if not OC:
    print("[ERROR] LAW_API_KEY not set.")
    sys.exit(1)

BASE_URL = "http://www.law.go.kr/DRF"

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; LawApiTest/1.0)"})

def search_law(query: str, page: int = 1, display: int = 5) -> dict:
    params = {
        "OC": OC,
        "target": "law",
        "type": "JSON",
        "query": query,
        "display": display,
        "page": page,
    }
    r = requests.get(f"{BASE_URL}/lawSearch.do", params=params, timeout=10)
    r.raise_for_status()
    return r.json()

# ─────────────────────────────────────────────
# 2A: Full JSON structure dump
# ─────────────────────────────────────────────
print("=" * 60)
print("[2A] Raw JSON structure (query: '지방자치법')")
print("=" * 60)

data = search_law("지방자치법", display=3)
print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])

# ─────────────────────────────────────────────
# 2B: Try current pipeline's assumed key path
#     law_api_client.py expects:
#     data["LawSearch"]["law"] → list of items
#     item["법령일련번호"] → MST
#     item["법령명한글"]  → title
#     item["법령구분"]    → category
#     item["공포일자"]    → promulgation_date
#     item["시행일자"]    → enforcement_date
#     item["법령상세링크"] → detail_link
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("[2B] Validate current pipeline's key paths")
print("=" * 60)

EXPECTED_OUTER_KEY = "LawSearch"
EXPECTED_INNER_KEY = "law"
EXPECTED_TOTAL_KEY = "totalCnt"
EXPECTED_FIELDS = {
    "법령일련번호": "mst",
    "법령명한글": "title",
    "법령구분": "category",
    "공포일자": "promulgation_date",
    "시행일자": "enforcement_date",
    "법령상세링크": "detail_link",
}

def check_key(obj, key, label):
    if key in obj:
        print(f"  [OK] '{key}' ({label}) = {str(obj[key])[:80]}")
        return True
    else:
        print(f"  [MISSING] '{key}' ({label}) not found. Available keys: {list(obj.keys())}")
        return False

# Check outer key
if EXPECTED_OUTER_KEY in data:
    print(f"[OK] Top-level key '{EXPECTED_OUTER_KEY}' exists")
    inner = data[EXPECTED_OUTER_KEY]
else:
    print(f"[FAIL] Top-level key '{EXPECTED_OUTER_KEY}' NOT found. Actual keys: {list(data.keys())}")
    inner = None

if inner is not None:
    # Check totalCnt
    check_key(inner, EXPECTED_TOTAL_KEY, "total count")

    # Check law list key
    if EXPECTED_INNER_KEY in inner:
        print(f"[OK] Inner key '{EXPECTED_INNER_KEY}' exists")
        law_list = inner[EXPECTED_INNER_KEY]
        if isinstance(law_list, list) and len(law_list) > 0:
            print(f"[OK] '{EXPECTED_INNER_KEY}' is a list with {len(law_list)} item(s)")
            first = law_list[0]
            print(f"\n  First item type: {type(first).__name__}")
            print(f"  All fields in first item:")
            for k, v in first.items():
                print(f"    {k!r}: {str(v)[:60]}")
            print(f"\n  Checking expected field names:")
            for field, label in EXPECTED_FIELDS.items():
                check_key(first, field, label)
        else:
            print(f"[WARN] '{EXPECTED_INNER_KEY}' is {type(law_list).__name__}, value: {law_list}")
    else:
        print(f"[FAIL] Inner key '{EXPECTED_INNER_KEY}' NOT found. Actual keys: {list(inner.keys())}")

# ─────────────────────────────────────────────
# 2C: Pagination check
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("[2C] Pagination check (query: '청년', display=10, page=1)")
print("=" * 60)
data2 = search_law("청년", display=10, page=1)
try:
    results = data2["LawSearch"]["law"]
    total = data2["LawSearch"].get("totalCnt", "?")
    print(f"Total: {total}, Returned on page 1: {len(results) if isinstance(results, list) else results}")
except (KeyError, TypeError) as e:
    print(f"[WARN] Key path error: {e}")
    print(json.dumps(data2, ensure_ascii=False, indent=2)[:500])

print("\n[Done] Step 2 complete.")
