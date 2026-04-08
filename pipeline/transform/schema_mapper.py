"""
Maps raw API response objects to the Neo4j node property dicts
defined in the Graph Schema (CLAUDE.md §4) and OWL ontology (ordinance.rdf).

Node schemas:
  Statute   → id, title, category, enforcement_date, promulgation_date, last_synced
  Provision → id, article_no, article_title, content_text, is_penalty_clause
  Ordinance → id, region_name, title, enforcement_date, last_updated
  Paragraph → id, provision_id, seq, content_text  (OWL: 항)
  Item      → id, paragraph_id, seq, content_text  (OWL: 호)
  SubItem   → id, item_id, seq, content_text        (OWL: 목)

All dates are normalized to YYYY-MM-DD (API returns YYYYMMDD).
"""

from dataclasses import dataclass

from pipeline.api.law_api_client import (
    LegalTermDetail,
    OrdinanceFull,
    ParagraphRaw,
    ProvisionRaw,
    StatuteFull,
)


@dataclass
class StatuteNode:
    id: str
    title: str
    category: str
    enforcement_date: str
    promulgation_date: str


@dataclass
class ProvisionNode:
    id: str            # "{statute_mst}_{article_no}"
    statute_id: str
    article_no: str
    article_title: str
    content_text: str
    is_penalty_clause: bool


@dataclass
class OrdinanceNode:
    id: str
    title: str
    region_name: str
    enforcement_date: str


@dataclass
class ParagraphNode:
    """OWL: 항 (Paragraph) — child of Provision."""
    id: str            # "{provision_id}_para_{seq}"
    provision_id: str
    seq: int
    content_text: str


@dataclass
class ItemNode:
    """OWL: 호 (Item) — child of Paragraph."""
    id: str            # "{paragraph_id}_item_{seq}"
    paragraph_id: str
    seq: int
    content_text: str


@dataclass
class SubItemNode:
    """OWL: 목 (SubItem) — child of Item."""
    id: str            # "{item_id}_sub_{seq}"
    item_id: str
    seq: int
    content_text: str


@dataclass
class LegalTermNode:
    """OWL: 법적개념 (LegalTerm) node."""
    term_name: str       # unique key (UNIQUE constraint in Neo4j)
    definition: str      # 법령용어정의
    synonyms: list[str]  # 한자 표기 등 (비어있을 수 있음)


def _normalize_date(raw: str) -> str:
    """Convert YYYYMMDD → YYYY-MM-DD. Returns raw string if format is unexpected."""
    raw = raw.strip()
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return raw


def _provision_id(statute_mst: str, article_no: str) -> str:
    """Generate a stable unique ID for a provision node."""
    safe_article = article_no.replace(" ", "_").replace("/", "_")
    return f"{statute_mst}__{safe_article}"


def _build_sub_structure(
    provision_id: str,
    paragraphs: list[ParagraphRaw],
) -> tuple[list[ParagraphNode], list[ItemNode], list[SubItemNode]]:
    """
    Convert ParagraphRaw hierarchy into flat lists of ParagraphNode / ItemNode / SubItemNode.
    IDs follow the pattern:
      Paragraph: {provision_id}_para_{seq}
      Item:      {paragraph_id}_item_{seq}
      SubItem:   {item_id}_sub_{seq}
    """
    para_nodes: list[ParagraphNode] = []
    item_nodes: list[ItemNode] = []
    subitem_nodes: list[SubItemNode] = []

    for p in paragraphs:
        para_id = f"{provision_id}_para_{p.seq}"
        para_nodes.append(ParagraphNode(
            id=para_id,
            provision_id=provision_id,
            seq=p.seq,
            content_text=p.content_text,
        ))
        for it in p.items:
            item_id = f"{para_id}_item_{it.seq}"
            item_nodes.append(ItemNode(
                id=item_id,
                paragraph_id=para_id,
                seq=it.seq,
                content_text=it.content_text,
            ))
            for si in it.subitems:
                subitem_nodes.append(SubItemNode(
                    id=f"{item_id}_sub_{si.seq}",
                    item_id=item_id,
                    seq=si.seq,
                    content_text=si.content_text,
                ))

    return para_nodes, item_nodes, subitem_nodes


# ---------------------------------------------------------------------------
# Public mapper functions
# ---------------------------------------------------------------------------

def map_statute(
    full: StatuteFull,
) -> tuple[StatuteNode, list[ProvisionNode], list[ParagraphNode], list[ItemNode], list[SubItemNode]]:
    """
    Convert a StatuteFull (from API) into:
    - one StatuteNode
    - list of ProvisionNodes (one per article)
    - list of ParagraphNodes (항, children of Provision)
    - list of ItemNodes (호, children of Paragraph)
    - list of SubItemNodes (목, children of Item)
    """
    statute_node = StatuteNode(
        id=full.mst,
        title=full.title,
        category=full.category,
        enforcement_date=_normalize_date(full.enforcement_date),
        promulgation_date=_normalize_date(full.promulgation_date),
    )

    provision_nodes: list[ProvisionNode] = []
    all_para_nodes: list[ParagraphNode] = []
    all_item_nodes: list[ItemNode] = []
    all_subitem_nodes: list[SubItemNode] = []

    for p in full.provisions:
        if not p.content_text.strip():
            continue
        prov_id = _provision_id(full.mst, p.article_no)
        provision_nodes.append(ProvisionNode(
            id=prov_id,
            statute_id=full.mst,
            article_no=p.article_no,
            article_title=p.article_title,
            content_text=p.content_text,
            is_penalty_clause=p.is_penalty_clause,
        ))
        if p.paragraphs:
            para_n, item_n, sub_n = _build_sub_structure(prov_id, p.paragraphs)
            all_para_nodes.extend(para_n)
            all_item_nodes.extend(item_n)
            all_subitem_nodes.extend(sub_n)

    return statute_node, provision_nodes, all_para_nodes, all_item_nodes, all_subitem_nodes


def map_ordinance(
    full: OrdinanceFull,
) -> tuple[OrdinanceNode, list[ProvisionNode], list[ParagraphNode], list[ItemNode], list[SubItemNode]]:
    """
    Convert an OrdinanceFull (from API) into:
    - one OrdinanceNode
    - list of ProvisionNodes (articles within the ordinance)
    - list of ParagraphNodes / ItemNodes / SubItemNodes (sub-structure)

    Note: Ordinance provisions are stored with ordinance MST as prefix
    to avoid collision with statute provision IDs.
    """
    ordinance_node = OrdinanceNode(
        id=full.mst,
        title=full.title,
        region_name=full.region_name,
        enforcement_date=_normalize_date(full.enforcement_date),
    )

    provision_nodes: list[ProvisionNode] = []
    all_para_nodes: list[ParagraphNode] = []
    all_item_nodes: list[ItemNode] = []
    all_subitem_nodes: list[SubItemNode] = []

    for p in full.provisions:
        if not p.content_text.strip():
            continue
        prov_id = _provision_id(f"ORDIN_{full.mst}", p.article_no)
        provision_nodes.append(ProvisionNode(
            id=prov_id,
            statute_id=full.mst,  # ordinance acts as the parent
            article_no=p.article_no,
            article_title=p.article_title,
            content_text=p.content_text,
            is_penalty_clause=p.is_penalty_clause,
        ))
        if p.paragraphs:
            para_n, item_n, sub_n = _build_sub_structure(prov_id, p.paragraphs)
            all_para_nodes.extend(para_n)
            all_item_nodes.extend(item_n)
            all_subitem_nodes.extend(sub_n)

    return ordinance_node, provision_nodes, all_para_nodes, all_item_nodes, all_subitem_nodes


def map_legal_term(detail: LegalTermDetail) -> LegalTermNode:
    """Convert a LegalTermDetail (from API) into a LegalTermNode for Neo4j."""
    synonyms = [detail.hanja] if detail.hanja else []
    return LegalTermNode(
        term_name=detail.term_name,
        definition=detail.definition,
        synonyms=synonyms,
    )


def extract_keywords(provisions: list[ProvisionRaw]) -> list[str]:
    """
    Extract LegalTerm keywords from provision texts for LIMITS relationship building.
    Simple approach: match against a curated keyword list.
    Can be replaced with NER/LLM-based extraction in a later phase.
    """
    LEGAL_TERMS = [
        "보조금", "지원금", "보조사업", "창업", "중소기업",
        "청년", "소상공인", "일자리", "고용", "취업",
        "지방자치단체", "조례", "규칙", "위원회",
    ]
    found: set[str] = set()
    for p in provisions:
        for term in LEGAL_TERMS:
            if term in p.content_text:
                found.add(term)
    return list(found)
