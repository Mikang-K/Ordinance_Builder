"""
Step 3: Law Full Text XML Parsing
Purpose: Verify XML tag names used in law_api_client._parse_provision_xml() match actual API.
Run: python pipeline_test/step3_full_parse.py
"""
import os
import sys
import requests
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

load_dotenv()

OC = os.environ.get("LAW_API_KEY", "")
if not OC:
    print("[ERROR] LAW_API_KEY not set.")
    sys.exit(1)

BASE_URL = "http://www.law.go.kr/DRF"
HTTPS_BASE = "https://www.law.go.kr/DRF"
HTTP_ROOT = "http://www.law.go.kr"

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; LawApiTest/1.0)"})

def smart_get(url: str, params: dict) -> requests.Response:
    """HTTPS → HTTP fallback, JS redirect tracking."""
    import re
    for attempt in range(2):
        try:
            r = session.get(url, params=params, timeout=15)
        except (requests.exceptions.ConnectionError, ConnectionResetError):
            if attempt == 0 and url.startswith("https://"):
                url = url.replace("https://", "http://")
                continue
            raise
        ct = r.headers.get("Content-Type", "")
        is_data = ("application/json" in ct or "xml" in ct
                   or r.text.strip().startswith(("{", "<?xml")))
        if is_data:
            return r
        # DDoS JS redirect detection
        if r.status_code == 200 and "<script>" in r.text:
            m = re.search(r"\{o:'([^']*)',t:'([^']*)',h:'([^']*)'\}", r.text)
            if m:
                redirect_url = HTTP_ROOT + m.group(2) + m.group(3) + m.group(1)
                return session.get(redirect_url, timeout=15)
        return r
    return r

# ─────────────────────────────────────────────
# 3A: Get MST from list search first
# ─────────────────────────────────────────────
print("=" * 60)
print("[3A] Get MST via list search")
print("=" * 60)

r = smart_get(f"{HTTPS_BASE}/lawSearch.do", {
    "OC": OC, "target": "law", "type": "JSON",
    "query": "지방자치법", "display": 5, "page": 1,
})
data = r.json()

mst = None
detail_link = None
try:
    # Try the key path confirmed in step2
    items = data["LawSearch"]["law"]
    if isinstance(items, list) and items:
        first = items[0]
        print(f"First item: {first}")
        mst = first.get("법령일련번호") or first.get("mst")
        detail_link = first.get("법령상세링크") or first.get("detailLink")
        print(f"MST: {mst}")
        print(f"Detail link: {detail_link}")
except (KeyError, TypeError) as e:
    print(f"[WARN] Could not extract MST: {e} — using fallback")

# ─────────────────────────────────────────────
# 3B: Fetch XML via lawService.do
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("[3B] Fetch full text XML via lawService.do")
print("=" * 60)

def fetch_xml(mst_val: str, link: str = "") -> bytes:
    """Try to fetch XML, handle encoding explicitly."""
    # Option 1: via detail_link (URL transform type=HTML -> type=XML)
    # detail_link is a relative URL like /DRF/lawService.do?... → prepend HTTP_ROOT
    if link:
        if link.startswith("/"):
            link = HTTP_ROOT + link
        xml_url = link.replace("type=HTML", "type=XML").replace("type=html", "type=XML")
        if xml_url != link or "type=XML" in xml_url:
            print(f"  Trying detail_link (transformed): {xml_url}")
            try:
                r = smart_get(xml_url, {})
                if r.status_code == 200 and "<" in r.text:
                    print(f"  [OK] Got response via detail_link")
                    return r.content
            except Exception as e:
                print(f"  [WARN] detail_link request failed: {e}")

    # Option 2: via lawService.do with MST param (confirmed in step1)
    print(f"  Trying lawService.do with MST={mst_val}")
    r = smart_get(f"{HTTPS_BASE}/lawService.do", {
        "OC": OC, "target": "law", "type": "XML", "MST": mst_val,
    })
    print(f"  Status: {r.status_code}, Content-Type: {r.headers.get('Content-Type')}")
    return r.content

if mst:
    raw_content = fetch_xml(mst, detail_link or "")
else:
    print("[SKIP] No MST available, cannot fetch XML")
    sys.exit(0)

# ─────────────────────────────────────────────
# 3C: Decode and print raw XML
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("[3C] Raw XML content")
print("=" * 60)

for enc in ["utf-8", "euc-kr", "cp949"]:
    try:
        decoded = raw_content.decode(enc)
        print(f"[OK] Decoded as {enc}")
        break
    except UnicodeDecodeError:
        print(f"[FAIL] Cannot decode as {enc}")
        decoded = None

if decoded:
    print(decoded[:3000])

# ─────────────────────────────────────────────
# 3D: Parse XML and list ALL tag names
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("[3D] All unique XML tag names in document")
print("=" * 60)

try:
    root = ET.fromstring(raw_content)
    tags = sorted(set(el.tag for el in root.iter()))
    print("Unique tags:")
    for tag in tags:
        print(f"  {tag!r}")
except ET.ParseError as e:
    print(f"[ERROR] XML parse error: {e}")
    print("First 500 bytes of raw content:")
    print(raw_content[:500])
    sys.exit(1)

# ─────────────────────────────────────────────
# 3E: Validate pipeline's expected tag names
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("[3E] Validate pipeline's expected XML tags")
print("=" * 60)

# Tags used in law_api_client.py
EXPECTED_TAGS_STATUTE = [
    "법령",          # root tag
    "기본정보",       # metadata section
    "법령명한글",     # title
    "법령구분명",     # category
    "공포일자",       # promulgation date
    "시행일자",       # enforcement date
    "조문단위",       # provision unit
    "조문번호",       # article number
    "조문제목",       # article title
    "조문내용",       # article body text
    "항",            # paragraph
    "항내용",        # paragraph text
    "호",            # sub-paragraph
    "호내용",        # sub-paragraph text
]

for tag in EXPECTED_TAGS_STATUTE:
    found = root.find(f".//{tag}")
    if found is not None:
        sample = (found.text or "")[:50].strip()
        print(f"  [OK] <{tag}> found — sample: {sample!r}")
    else:
        print(f"  [MISSING] <{tag}> NOT found in document")

# ─────────────────────────────────────────────
# 3F: Show first 조문단위 in full detail
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("[3F] First provision (조문단위) full content")
print("=" * 60)

# Try both possible tag names
provision_tag = None
for candidate in ["조문단위", "조문", "Article", "article"]:
    el = root.find(f".//{candidate}")
    if el is not None:
        provision_tag = candidate
        print(f"Using tag: '{candidate}'")
        break

if provision_tag:
    first_prov = root.find(f".//{provision_tag}")
    if first_prov is not None:
        ET.indent(first_prov, space="  ")
        print(ET.tostring(first_prov, encoding="unicode")[:1500])
else:
    print("[WARN] No provision tag found")

print("\n[Done] Step 3 complete.")
print("  Check [3E] for which tags are missing → those need fixing in law_api_client.py")
