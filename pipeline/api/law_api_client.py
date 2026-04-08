"""
National Law Information Center (국가법령정보센터) Open API client.

Docs: https://www.law.go.kr/LSW/openApi.do
API key registration: https://www.law.go.kr/LSW/openApiInfo.do
"""

import time
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

import requests

from pipeline.config import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal data models (API response → Python)
# ---------------------------------------------------------------------------

@dataclass
class StatuteSummary:
    """Statute metadata returned by the list search endpoint."""
    mst: str               # 법령MST (unique ID)
    title: str             # 법령명
    category: str          # 법령구분명 (법률 / 대통령령 / 부령 등)
    promulgation_date: str # 공포일자 (YYYYMMDD)
    enforcement_date: str  # 시행일자 (YYYYMMDD) ← change detection key
    detail_link: str = ""  # 법령상세링크 (server-provided URL, used for full-text retrieval)


@dataclass
class SubItemRaw:
    """목(SubItem) parsed from a <목> XML element."""
    seq: int
    content_text: str


@dataclass
class ItemRaw:
    """호(Item) parsed from a <호> XML element."""
    seq: int
    content_text: str
    subitems: list[SubItemRaw] = field(default_factory=list)


@dataclass
class ParagraphRaw:
    """항(Paragraph) parsed from a <항> XML element."""
    seq: int
    content_text: str
    items: list[ItemRaw] = field(default_factory=list)


@dataclass
class ProvisionRaw:
    """Individual article (조문) from a statute's full text response."""
    article_no: str        # 조문번호 (예: "제1조")
    article_title: str     # 조문제목 (예: "(목적)")
    content_text: str      # 조문내용 (full text including sub-clauses, flattened)
    is_penalty_clause: bool
    paragraphs: list[ParagraphRaw] = field(default_factory=list)  # structured sub-clauses


@dataclass
class StatuteFull:
    """Full statute with all provisions."""
    mst: str
    title: str
    category: str
    promulgation_date: str
    enforcement_date: str
    provisions: list[ProvisionRaw]


@dataclass
class OrdinanceSummary:
    """Ordinance (자치법규) metadata from list search."""
    mst: str
    title: str
    region_name: str       # 지자체기관명 (JSON field; XML tag is 자치단체명)
    enforcement_date: str
    detail_link: str = ""  # 자치법규상세링크 (server-provided URL)


@dataclass
class OrdinanceFull:
    """Full ordinance with all articles."""
    mst: str
    title: str
    region_name: str
    enforcement_date: str
    provisions: list[ProvisionRaw]


@dataclass
class LegalTermSummary:
    """법령용어 metadata from list search (lawSearch.do?target=lstrmAI)."""
    lstrm_id: str
    term_name: str   # 법령용어명
    mst: str         # MST extracted from 조문간관계링크 — used for detail lookup


@dataclass
class LegalTermDetail:
    """법령용어 detail including definition (lawService.do?target=lstrm)."""
    lstrm_id: str
    term_name: str   # lstrm_name_ko
    hanja: str       # lstrm_name_hanja (한자 표기, synonyms 용도)
    definition: str  # 법령용어정의
    source: str      # 출처 (법령명)


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

_PENALTY_KEYWORDS = ("벌금", "과태료", "징역", "과징금", "벌칙")


def _xt(el: ET.Element, tag: str) -> str:
    """Return the text of a child element, or '' if not found."""
    child = el.find(tag)
    return (child.text or "").strip() if child is not None else ""



class LawApiClient:
    """
    Thin HTTP wrapper around the National Law Information Center DRF API.

    All endpoints return JSON (type=JSON). Pagination is handled internally.
    A configurable delay between requests prevents rate-limit errors.
    """

    def __init__(self):
        self._base = config.law_api_base_url
        self._key = config.law_api_key
        self._delay = config.api_request_delay
        self._session = requests.Session()
        self._session.headers.update({
            # No global Accept header — set per-request to avoid conflicting with XML endpoints
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        })

    # ------------------------------------------------------------------
    # Public: Statute (법령)
    # ------------------------------------------------------------------

    def search_statutes(self, query: str) -> list[StatuteSummary]:
        """
        Search statutes by keyword. Fetches all pages automatically.

        Endpoint: lawSearch.do?target=law
        """
        results: list[StatuteSummary] = []
        page = 1

        while True:
            data = self._get("lawSearch.do", {
                "target": "law",
                "query": query,
                "display": config.api_display_count,
                "page": page,
            })

            items = self._extract_list(data, "law")
            if not items:
                break

            for item in items:
                results.append(StatuteSummary(
                    mst=str(item.get("법령일련번호", "")),
                    title=item.get("법령명한글", ""),
                    category=item.get("법령구분명", ""),
                    promulgation_date=item.get("공포일자", ""),
                    enforcement_date=item.get("시행일자", ""),
                    detail_link=item.get("법령상세링크", ""),
                ))

            if len(items) < config.api_display_count:
                break
            page += 1
            time.sleep(self._delay)

        logger.info("statute search '%s': %d results", query, len(results))
        return results

    def get_statute_full(self, mst: str, detail_link: str = "") -> StatuteFull | None:
        """
        Fetch the full text of a statute including all provisions.

        Uses the server-provided detail_link (from search result) when available:
        replaces type=HTML with type=XML to get the structured XML response.
        Falls back to constructing the URL from MST if detail_link is empty.
        """
        root = self._get_xml_by_link(detail_link) if detail_link else \
               self._get_xml("lawService.do", {"target": "law", "MST": mst})
        if root is None:
            return None

        basic = root.find("기본정보")
        if basic is None:
            logger.error("get_statute_full MST=%s: <기본정보> not found in XML", mst)
            return None

        provisions = [
            self._parse_provision_xml(p)
            for p in root.findall(".//조문단위")
        ]

        return StatuteFull(
            mst=mst,
            title=_xt(basic, "법령명_한글"),
            category=_xt(basic, "법종구분"),
            promulgation_date=_xt(basic, "공포일자"),
            enforcement_date=_xt(basic, "시행일자"),
            provisions=provisions,
        )

    # ------------------------------------------------------------------
    # Public: Ordinance / 자치법규 (조례)
    # ------------------------------------------------------------------

    def search_ordinances(self, query: str) -> list[OrdinanceSummary]:
        """
        Search ordinances (자치법규) by keyword.

        Endpoint: lawSearch.do?target=ordin
        """
        results: list[OrdinanceSummary] = []
        page = 1

        while True:
            data = self._get("lawSearch.do", {
                "target": "ordin",
                "query": query,
                "display": config.api_display_count,
                "page": page,
            })

            items = self._extract_list(data, "ordin")
            if not items:
                break

            for item in items:
                results.append(OrdinanceSummary(
                    mst=str(item.get("자치법규일련번호", item.get("자치법규MST", ""))),
                    title=item.get("자치법규명", ""),
                    region_name=item.get("지자체기관명", ""),
                    enforcement_date=item.get("시행일자", ""),
                    detail_link=item.get("자치법규상세링크", ""),
                ))

            if len(items) < config.api_display_count:
                break
            page += 1
            time.sleep(self._delay)

        logger.info("ordinance search '%s': %d results", query, len(results))
        return results

    def get_ordinance_full(self, mst: str, detail_link: str = "") -> OrdinanceFull | None:
        """
        Fetch the full text of an ordinance including all articles.

        Uses the server-provided detail_link when available.
        """
        root = self._get_xml_by_link(detail_link) if detail_link else \
               self._get_xml("lawService.do", {"target": "ordin", "MST": mst})
        if root is None:
            return None

        basic = root.find("자치법규기본정보")
        if basic is None:
            child_tags = [child.tag for child in root]
            logger.error(
                "get_ordinance_full MST=%s: <자치법규기본정보> not found in XML. "
                "Top-level tags: %s",
                mst, child_tags,
            )
            return None

        # Ordinance XML uses <조> elements (not <조문단위> used by statutes)
        provisions = [
            self._parse_ordinance_provision_xml(p)
            for p in root.findall(".//조")
            if _xt(p, "조문여부") == "Y"
        ]

        return OrdinanceFull(
            mst=mst,
            title=_xt(basic, "자치법규명"),
            region_name=_xt(basic, "자치단체명"),
            enforcement_date=_xt(basic, "시행일자"),
            provisions=provisions,
        )

    # ------------------------------------------------------------------
    # Public: Legal Terms (법령용어)
    # ------------------------------------------------------------------

    def search_legal_terms(self, query: str) -> list[LegalTermSummary]:
        """
        Search legal terms by keyword.

        Endpoint: lawSearch.do?target=lstrmAI
        Response: {"lstrmAISearch": {"법령용어": [...], "검색결과개수": "N", ...}}
        Returns: list of LegalTermSummary including MST extracted from 조문간관계링크.
        """
        results: list[LegalTermSummary] = []
        page = 1

        while True:
            data = self._get("lawSearch.do", {
                "target": "lstrmAI",
                "query": query,
                "display": config.api_display_count,
                "page": page,
            })

            search = data.get("lstrmAISearch", {})
            items = search.get("법령용어", [])
            if isinstance(items, dict):
                items = [items]

            if not items:
                break

            for item in items:
                term_name = item.get("법령용어명", "").strip()
                lstrm_id = str(item.get("id", ""))

                # Extract MST from 조문간관계링크, e.g. "…&MST=1316243"
                jo_link = item.get("조문간관계링크", "")
                mst = ""
                for part in jo_link.split("&"):
                    if part.startswith("MST="):
                        mst = part[4:]
                        break

                if term_name and mst:
                    results.append(LegalTermSummary(
                        lstrm_id=lstrm_id,
                        term_name=term_name,
                        mst=mst,
                    ))

            total = int(search.get("검색결과개수", "0") or "0")
            if len(results) >= total or len(items) < config.api_display_count:
                break
            page += 1
            time.sleep(self._delay)

        logger.info("legal_term search '%s': %d results", query, len(results))
        return results

    def get_legal_term_detail(self, mst: str) -> list[LegalTermDetail]:
        """
        Fetch legal term detail (definition, source) by MST.

        Endpoint: lawService.do?target=lstrmRltJo&MST=<mst> (XML)
        Returns the provision content (jo_content) where the term is defined.
        """
        root = self._get_xml("lawService.do", {"target": "lstrmRltJo", "MST": mst})
        if root is None:
            return []

        # Structure: <lstrmRltJoService><법령용어><법령용어명>...<연계법령><조문내용>...
        term_el = root.find("법령용어")
        if term_el is None:
            logger.warning("legal_term detail MST=%s: <법령용어> not found", mst)
            return []

        term_name = _xt(term_el, "법령용어명")
        if not term_name:
            return []

        # Take the first 연계법령 that has 조문내용
        for law_el in term_el.findall("연계법령"):
            definition = _xt(law_el, "조문내용").strip()
            source = _xt(law_el, "법령명")
            if definition:
                logger.info("legal_term detail MST=%s: '%s' from '%s'", mst, term_name, source)
                return [LegalTermDetail(
                    lstrm_id=mst,
                    term_name=term_name,
                    hanja="",
                    definition=definition,
                    source=source,
                )]

        logger.warning("legal_term detail MST=%s: no 조문내용 found", mst)
        return []

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _request(
        self, url: str, params: dict, extra_headers: dict | None = None
    ) -> requests.Response | None:
        """
        Execute a GET request with one automatic retry on ConnectionResetError.

        The law.go.kr server occasionally drops the first keep-alive connection.
        extra_headers overrides session-level headers for this request only.
        """
        for attempt in (1, 2):
            try:
                return self._session.get(
                    url, params=params, timeout=30, headers=extra_headers or {}
                )
            except requests.exceptions.ConnectionError as exc:
                if attempt == 1 and "ConnectionResetError" in str(exc):
                    logger.warning("Connection reset on attempt 1, retrying…")
                    time.sleep(1)
                    continue
                logger.error("API request failed: %s – %s", url, exc)
                return None
            except requests.RequestException as exc:
                logger.error("API request failed: %s – %s", url, exc)
                return None
        return None  # unreachable, but satisfies type checker

    def _get(self, endpoint: str, params: dict) -> dict[str, Any]:
        """Make a GET request and return parsed JSON (search endpoints only)."""
        url = f"{self._base}/{endpoint}"
        params = {**params, "OC": self._key, "type": "JSON"}
        resp = self._request(url, params, extra_headers={"Accept": "application/json"})
        if resp is None:
            return {}
        try:
            resp.raise_for_status()
            data = resp.json()
            logger.debug("API response %s: %s", endpoint, str(data)[:500])
            return data
        except Exception as exc:
            logger.error(
                "JSON parse/HTTP failed for %s. Status=%s error=%s body=%s",
                endpoint,
                getattr(resp, "status_code", "?"),
                exc,
                resp.text[:300],
            )
            return {}

    def _get_xml(self, endpoint: str, params: dict) -> ET.Element | None:
        """
        Make a GET request and return the parsed XML root element.

        The DRF API documentation shows http:// examples; HTTPS may redirect
        lawService.do to the website homepage.  We therefore force http:// here.
        """
        # Force HTTP — official API docs use http://www.law.go.kr/DRF/
        base_http = self._base.replace("https://", "http://")
        url = f"{base_http}/{endpoint}"
        params = {**params, "OC": self._key, "type": "XML"}
        safe_params = {k: ("***" if k == "OC" else v) for k, v in params.items()}
        logger.info("_get_xml → %s?%s", url, "&".join(f"{k}={v}" for k, v in safe_params.items()))
        resp = self._request(
            url, params, extra_headers={"Accept": "application/xml, text/xml, */*"}
        )
        if resp is None:
            return None
        # Log final URL to detect any redirects
        if resp.url != url.split("?")[0] + "?" + "&".join(f"{k}={v}" for k, v in params.items()):
            logger.info("_get_xml final URL: %s", resp.url)
        try:
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            logger.info("XML ok: root=<%s> provisions=%d", root.tag, len(root.findall(".//조문단위")))
            return root
        except ET.ParseError as exc:
            logger.error(
                "XML parse failed for %s. Status=%s finalURL=%s error=%s body=%s",
                endpoint,
                getattr(resp, "status_code", "?"),
                resp.url,
                exc,
                resp.text[:300],
            )
            return None
        except requests.RequestException as exc:
            logger.error("HTTP error for %s – %s", endpoint, exc)
            return None

    def _get_xml_by_link(self, detail_link: str) -> ET.Element | None:
        """
        Fetch XML using the server-provided 법령상세링크 URL.

        The search result includes the exact URL (type=HTML) the server uses to
        serve the law page.  Changing type=HTML → type=XML retrieves the same
        law in structured XML format, including all original parameters
        (OC, MST, mobileYn, efYd) that the server expects.
        """
        if not detail_link:
            return None
        # detail_link is relative: "/DRF/lawService.do?OC=...&type=HTML&..."
        xml_link = detail_link.replace("type=HTML", "type=XML")
        url = f"http://www.law.go.kr{xml_link}"
        logger.info("_get_xml_by_link → %s", url.replace(self._key, "***"))
        resp = self._request(url, {}, extra_headers={"Accept": "application/xml, text/xml, */*"})
        if resp is None:
            return None
        logger.info("_get_xml_by_link finalURL=%s status=%s", resp.url, resp.status_code)
        try:
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            logger.info("XML ok (detail_link): root=<%s> provisions=%d", root.tag, len(root.findall(".//조문단위")))
            return root
        except ET.ParseError as exc:
            logger.error(
                "XML parse failed (detail_link). status=%s finalURL=%s error=%s body=%s",
                resp.status_code, resp.url, exc, resp.text[:300],
            )
            return None

    @staticmethod
    def _extract_list(data: dict, target: str) -> list[dict]:
        """
        Extract the item list from a search response.

        Actual API response structure (confirmed by pipeline_test/step2, step4):
            Statute:  {"LawSearch":  {"law":   [...], "totalCnt": "N", ...}}
            Ordinance:{"OrdinSearch": {"law":   [...], "totalCnt": "N", ...}}

        Note: ordinance uses "OrdinSearch" as the outer key (not "LawSearch"),
        and "law" as the inner list key (not "ordin").
        """
        if target == "ordin":
            search_result = data.get("OrdinSearch", {})
            items = search_result.get("law", [])
        else:
            search_result = data.get("LawSearch", {})
            items = search_result.get(target, [])
        if isinstance(items, dict):
            items = [items]
        return items or []

    @staticmethod
    def _parse_ordinance_provision_xml(el: ET.Element) -> ProvisionRaw:
        """
        Parse a single <조> XML element (ordinance article) into a ProvisionRaw.

        Ordinance XML structure differs from statute XML:
          <조 조문번호="000100">
            <조문번호>000100</조문번호>   ← zero-padded × 100 (000100 = 제1조)
            <조제목>목적</조제목>
            <조내용>제1조(목적) ...</조내용>
          </조>
        The full text including sub-clauses is already flattened into <조내용>.
        """
        raw_no = _xt(el, "조문번호")  # e.g. "000100"
        article_title = _xt(el, "조제목")
        content_text = _xt(el, "조내용")

        try:
            article_no = f"제{int(raw_no) // 100}조"
        except (ValueError, ZeroDivisionError):
            article_no = raw_no

        is_penalty = any(kw in content_text for kw in _PENALTY_KEYWORDS)

        return ProvisionRaw(
            article_no=article_no,
            article_title=article_title,
            content_text=content_text,
            is_penalty_clause=is_penalty,
        )

    @staticmethod
    def _parse_provision_xml(el: ET.Element) -> ProvisionRaw:
        """
        Parse a single <조문단위> XML element into a ProvisionRaw.

        Preserves nested <항>/<호>/<목> structure in the paragraphs field while
        keeping content_text as a flat string for backward compatibility.
        """
        article_no = _xt(el, "조문번호")
        article_title = _xt(el, "조문제목")
        content_parts: list[str] = []
        paragraphs: list[ParagraphRaw] = []

        # <조문내용> (main body)
        if body := _xt(el, "조문내용"):
            content_parts.append(body)

        # <항> (paragraphs) — structured parsing
        for para_seq, para_el in enumerate(el.findall("항"), start=1):
            para_text = _xt(para_el, "항내용")
            items: list[ItemRaw] = []

            for item_seq, item_el in enumerate(para_el.findall("호"), start=1):
                item_text = _xt(item_el, "호내용")
                subitems: list[SubItemRaw] = []

                for sub_seq, sub_el in enumerate(item_el.findall("목"), start=1):
                    sub_text = _xt(sub_el, "목내용")
                    if sub_text:
                        subitems.append(SubItemRaw(seq=sub_seq, content_text=sub_text))
                        content_parts.append(f"    {sub_text}")

                if item_text:
                    items.append(ItemRaw(seq=item_seq, content_text=item_text, subitems=subitems))
                    content_parts.append(f"  {item_text}")

            if para_text:
                paragraphs.append(ParagraphRaw(seq=para_seq, content_text=para_text, items=items))
                content_parts.append(para_text)

        content_text = "\n".join(content_parts)
        is_penalty = any(kw in content_text for kw in _PENALTY_KEYWORDS)

        return ProvisionRaw(
            article_no=f"제{article_no}조" if article_no and not article_no.startswith("제") else article_no,
            article_title=article_title,
            content_text=content_text,
            is_penalty_clause=is_penalty,
            paragraphs=paragraphs,
        )
