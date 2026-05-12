"""
온톨로지 기반 법률 용어 사용 원칙 (ordinance.rdf → rdflib 동적 파싱)

ordinance.rdf가 Protégé에서 수정되면 이 모듈을 재임포트하는 것만으로
ONTOLOGY_TERM_GUIDE가 자동 갱신됩니다.
"""

from pathlib import Path

from rdflib import Graph, OWL, RDFS, RDF, URIRef

_NS = "http://www.semanticweb.org/user/ontologies/2026/2/untitled-ontology-3#"


def _local(uri) -> str:
    """URI에서 온톨로지 로컬 이름만 추출."""
    return str(uri).replace(_NS, "")


def _build_from_rdf(rdf_path: Path) -> str:
    g = Graph()
    g.parse(str(rdf_path), format="xml")

    # 클래스 계층 (rdfs:subClassOf, 온톨로지 내부 URI만)
    class_lines = []
    for cls in sorted(g.subjects(RDF.type, OWL.Class)):
        name = _local(cls)
        parents = [
            _local(p)
            for p in g.objects(cls, RDFS.subClassOf)
            if _NS in str(p)
        ]
        if parents:
            class_lines.append(f"  {name} ⊂ {', '.join(parents)}")

    # 관계 속성 — domain → range
    prop_lines = []
    for prop in sorted(g.subjects(RDF.type, OWL.ObjectProperty)):
        name = _local(prop)
        domains = [_local(d) for d in g.objects(prop, RDFS.domain)]
        ranges = [_local(r) for r in g.objects(prop, RDFS.range)]
        prop_lines.append(f"  {name}({', '.join(domains)} → {', '.join(ranges)})")

    # 데이터 속성
    data_names = sorted(
        _local(p)
        for p in g.subjects(RDF.type, OWL.DatatypeProperty)
    )

    sections = []
    if class_lines:
        sections.append("[클래스 계층]\n" + "\n".join(class_lines))
    if prop_lines:
        sections.append("[관계 속성 (도메인 → 범위)]\n" + "\n".join(prop_lines))
    if data_names:
        sections.append("[데이터 속성]\n  " + ", ".join(data_names))

    return "\n\n".join(sections)


# Layer 2: RDF 구조 자체로는 표현되지 않는 해석·표기 규칙
_INTERPRETIVE_RULES = """
[법규범 위계] 헌법 > 법률 > 대통령령 > 부령 > 조례 > 규칙
  - "상위법" 대신 반드시 "상위법률" 사용
  - 조례: 지방의회 제정 / 규칙: 지방자치단체장 제정
  - "조항" 대신 "제X조", "제X항", "제X호"로 구체적으로 표기
  - 조문 본문 → "조문", 조문 표제 → "조문제목"
""".strip()

# Layer 1: ordinance.rdf 동적 파싱 (파일 없거나 파싱 실패 시 빈 문자열 fallback)
_RDF_PATH = Path(__file__).parents[2] / "ordinance.rdf"
try:
    _rdf_section = _build_from_rdf(_RDF_PATH)
except Exception:
    _rdf_section = ""

ONTOLOGY_TERM_GUIDE = f"""
## 법률 용어 사용 원칙 (OWL 온톨로지 기반)

{_INTERPRETIVE_RULES}

{_rdf_section}
""".strip()


def _build_class_hierarchy_section(g: Graph) -> str:
    """
    OWL 자치법규의 하위 클래스 목록을 추출해 intent_analyzer용 분류 가이드 반환.

    조례(지원/설치·운영/관리·규제/복지·서비스) 하위 유형이
    intent_analyzer 시스템 프롬프트에 OWL 정의 기반으로 주입됨.
    """
    lines = []
    try:
        자치법규_uri = URIRef(_NS + "자치법규")
        for cls in sorted(g.subjects(RDFS.subClassOf, 자치법규_uri)):
            name = _local(cls)
            label_ko = next(
                (str(lb) for lb in g.objects(cls, RDFS.label) if getattr(lb, "language", None) == "ko"),
                name,
            )
            comment = next(g.objects(cls, RDFS.comment), None)
            entry = f"  - {label_ko}"
            if comment:
                entry += f": {str(comment)[:80]}"
            lines.append(entry)
    except Exception:
        pass
    if not lines:
        lines = [
            "  - 지원: 보조금·지원금·현물 지원 목적",
            "  - 설치·운영: 위원회·센터 설치 및 운영",
            "  - 관리·규제: 시설 관리·사용 허가·과태료·규제",
            "  - 복지·서비스: 돌봄·복지서비스·급여·방문서비스",
        ]
    return "[조례 하위 유형 (OWL 자치법규 클래스 계층)]\n" + "\n".join(lines)


try:
    _class_section = _build_class_hierarchy_section(
        Graph().parse(str(_RDF_PATH), format="xml") if _RDF_PATH.exists() else Graph()
    )
except Exception:
    _class_section = _build_class_hierarchy_section(Graph())

ONTOLOGY_CLASS_GUIDE: str = _class_section
