"""
Step 4: Ordinance List + Full Text Parsing
Purpose: Verify ordinance search JSON keys and XML structure (differs from statute).
Run: python pipeline_test/step4_ordinance.py
"""
import os
import re
import sys
import json
import requests
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

load_dotenv()

OC = os.environ.get("LAW_API_KEY", "")
if not OC:
    print("[ERROR] LAW_API_KEY not set.")
    sys.exit(1)

HTTPS_BASE = "https://www.law.go.kr/DRF"
HTTP_ROOT  = "http://www.law.go.kr"

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; LawApiTest/1.0)"})


def smart_get(url: str, params: dict) -> requests.Response:
    """HTTPS → HTTP fallback, JS redirect tracking."""
    for attempt in range(2):
        try:
            r = session.get(url, params=params, timeout=15)
        except (requests.exceptions.ConnectionError, ConnectionResetError):
            if attempt == 0 and url.startswith("https://"):
                url = url.replace("https://", "http://")
                continue
            raise

        ct = r.headers.get("Content-Type", "")
        is_data = (
            "application/json" in ct or "xml" in ct
            or r.text.strip().startswith(("{", "<?xml", "<법", "<자치"))
        )
        if is_data:
            return r

        # DDoS JS redirect detection
        if r.status_code == 200 and "<script>" in r.text:
            m = re.search(r"\{o:'([^']*)',t:'([^']*)',h:'([^']*)'\}", r.text)
            if m:
                redirect_url = HTTP_ROOT + m.group(2) + m.group(3) + m.group(1)
                print(f"  [JS-REDIRECT] Detected. Following to: {redirect_url[:100]}")
                return session.get(redirect_url, timeout=15)
            else:
                print(f"  [WARN] HTML response but no JS redirect pattern found")
                print(f"  Response snippet: {r.text[:300]}")

        return r
    return r  # fallback (should not reach)


# ─────────────────────────────────────────────
# 4A: Ordinance list search (JSON)
# ─────────────────────────────────────────────
print("=" * 60)
print("[4A] Ordinance list search (target=ordin, JSON)")
print("=" * 60)

r = smart_get(f"{HTTPS_BASE}/lawSearch.do", {
    "OC": OC, "target": "ordin", "type": "JSON",
    "query": "청년", "display": 3, "page": 1,
})
data = r.json()
print(json.dumps(data, ensure_ascii=False, indent=2)[:2500])

# Pipeline expects:
# data["OrdinSearch"]["law"] → list  (NOTE: differs from statute's "LawSearch"/"law")
# item["자치법규일련번호"] → MST
# item["자치법규명"]       → title
# item["지자체기관명"]     → region_name  (NOTE: NOT "자치단체명")
# item["시행일자"]         → enforcement_date
# item["자치법규상세링크"]  → detail_link
print("\n" + "=" * 60)
print("[4A2] Validate ordinance JSON fields")
print("=" * 60)

EXPECTED_ORDIN_FIELDS = {
    "자치법규일련번호": "mst",
    "자치법규명": "title",
    "지자체기관명": "region_name",
    "시행일자": "enforcement_date",
    "자치법규상세링크": "detail_link",
}

mst = None
detail_link = None
try:
    items = data["OrdinSearch"]["law"]
    if isinstance(items, list) and items:
        first = items[0]
        print(f"All fields in first ordinance item:")
        for k, v in first.items():
            print(f"  {k!r}: {str(v)[:60]}")
        print()
        for field, label in EXPECTED_ORDIN_FIELDS.items():
            if field in first:
                print(f"  [OK] '{field}' ({label}) = {str(first[field])[:60]}")
                if label == "mst":
                    mst = first[field]
                if label == "detail_link":
                    detail_link = first[field]
            else:
                print(f"  [MISSING] '{field}' ({label}) not found")
    else:
        print(f"[WARN] 'ordin' is {type(items).__name__}: {items}")
except (KeyError, TypeError) as e:
    print(f"[FAIL] Key path error: {e}")

# ─────────────────────────────────────────────
# 4B: Ordinance full text (XML)
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("[4B] Ordinance full text XML (target=ordin)")
print("=" * 60)

if not mst:
    print("[SKIP] No MST found from search")
    sys.exit(0)

# Try detail_link transform first (detail_link is a relative path, prepend HTTP_ROOT)
raw_content = None
if detail_link:
    full_link = (HTTP_ROOT + detail_link) if detail_link.startswith("/") else detail_link
    xml_url = full_link.replace("type=HTML", "type=XML").replace("type=html", "type=XML")
    if xml_url != full_link:
        print(f"Trying transformed detail_link: {xml_url}")
        try:
            rr = smart_get(xml_url, {})
            if rr.status_code == 200 and "<" in rr.text:
                raw_content = rr.content
                print("[OK] Got response via detail_link")
        except Exception as e:
            print(f"[WARN] detail_link failed: {e}")

if raw_content is None:
    print(f"Trying lawService.do with MST={mst}")
    rr = smart_get(f"{HTTPS_BASE}/lawService.do", {
        "OC": OC, "target": "ordin", "type": "XML", "MST": mst,
    })
    print(f"Status: {rr.status_code}")
    raw_content = rr.content

# Decode
for enc in ["utf-8", "euc-kr", "cp949"]:
    try:
        decoded = raw_content.decode(enc)
        print(f"[OK] Decoded as {enc}")
        break
    except UnicodeDecodeError:
        decoded = None

if decoded:
    print(decoded[:2000])

# ─────────────────────────────────────────────
# 4C: All XML tags + pipeline's expected tags
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("[4C] All unique tags + expected tag check")
print("=" * 60)

try:
    root = ET.fromstring(raw_content)
    tags = sorted(set(el.tag for el in root.iter()))
    print("Unique tags in ordinance XML:")
    for tag in tags:
        print(f"  {tag!r}")
except ET.ParseError as e:
    print(f"[ERROR] XML parse error: {e}")
    sys.exit(1)

# Pipeline expects for ordinance (law_api_client.py):
# root tag: "자치법규" (differs from "법령")
EXPECTED_TAGS_ORDIN = [
    "자치법규",       # root tag (differs from statute's "법령")
    "기본정보",
    "자치법규명",     # title (differs from "법령명한글")
    "자치단체명",     # region
    "시행일자",
    "조문단위",
    "조문번호",
    "조문제목",
    "조문내용",
    "항",
    "항내용",
]

print()
for tag in EXPECTED_TAGS_ORDIN:
    found = root.find(f".//{tag}")
    if found is not None:
        sample = (found.text or "")[:50].strip()
        print(f"  [OK] <{tag}> found — sample: {sample!r}")
    else:
        print(f"  [MISSING] <{tag}> NOT found")

# ─────────────────────────────────────────────
# 4D: Compare statute vs ordinance XML structure
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("[4D] Root tag name")
print("=" * 60)
print(f"Root tag: {root.tag!r}")
print("  (Pipeline expects '법령' for statutes, '자치법규' for ordinances)")

print("\n[Done] Step 4 complete.")
