from typing import Optional

from pydantic import BaseModel


class QAOutput(BaseModel):
    """LangChain structured output for GraphRAG Q&A."""
    answer: str
    applicable_content: Optional[str] = None
    applicable_article_key: Optional[str] = None


QA_SYSTEM = """당신은 대한민국 지방자치단체 조례 초안 작성 전문 어시스턴트입니다.
아래 그래프 데이터베이스에서 검색된 법령·조례 데이터를 근거로 질문에 답변하세요.
- 인용 시 법령명과 조항 번호를 명시하세요.
- 제공된 근거 데이터에 없는 내용은 일반적인 조례 작성 원칙을 바탕으로 답변하되, 추측임을 명시하세요.
- 답변은 한국어로 작성하세요.
"""


def build_qa_human(
    question: str,
    ordinance_info: dict,
    legal_basis: list[dict],
    legal_terms: list[dict],
    article_examples: list[dict],
    current_article_key: Optional[str],
    draft_full_text: str,
) -> str:
    lines = []

    lines.append("[현재 작성 중인 조례 정보]")
    if ordinance_info:
        lines.append(f"- 지역: {ordinance_info.get('region', '미정')}")
        lines.append(f"- 목적: {ordinance_info.get('purpose', '미정')}")
        lines.append(f"- 지원 대상: {ordinance_info.get('target_group', '미정')}")
        lines.append(f"- 지원 유형: {ordinance_info.get('support_type', '미정')}")
    else:
        lines.append("(아직 기본 정보가 수집되지 않은 상태입니다)")

    if draft_full_text:
        preview = draft_full_text[:600] + ("..." if len(draft_full_text) > 600 else "")
        lines.append(f"\n[현재까지 작성된 초안 (일부)]\n{preview}")

    if legal_basis:
        lines.append("\n[관련 법령 조항 — 그래프 DB 검색 결과]")
        for lb in legal_basis[:5]:
            rel = lb.get("relation_type", "")
            title = lb.get("statute_title", "")
            article = lb.get("provision_article", "")
            content = lb.get("provision_content", "")[:200]
            lines.append(f"• [{rel}] {title} {article}: {content}")

    if legal_terms:
        lines.append("\n[관련 법률 용어 정의]")
        for lt in legal_terms[:5]:
            term = lt.get("term_name", "")
            defn = lt.get("definition", "")[:200]
            source = lt.get("source_statute", "")
            lines.append(f"• {term}: {defn} (출처: {source})")

    if article_examples and current_article_key:
        lines.append(f"\n[유사 조례 '{current_article_key}' 조항 사례]")
        for ex in article_examples:
            region = ex.get("region_name", "")
            ot = ex.get("ordinance_title", "")
            art = ex.get("article_no", "")
            ct = ex.get("content_text", "")[:300]
            lines.append(f"• {region} ({ot}, {art}): {ct}")

    if current_article_key:
        lines.append(f"\n[현재 작성 중인 조항: {current_article_key}]")

    lines.append(f"\n[질문]\n{question}")

    if current_article_key:
        lines.append(
            f"\napplicable_content는 질문이 '{current_article_key}' 조항 작성과 직접 관련될 때만 "
            "해당 조항에 바로 삽입할 수 있는 조례 텍스트를 생성하세요. 무관하면 null로 두세요."
        )

    return "\n".join(lines)


def build_qa_human_direct(
    question: str,
    legal_basis: list[dict],
    legal_terms: list[dict],
    similar_ordinances: list[dict] | None = None,
) -> str:
    """세션 컨텍스트 없이 벡터 검색 결과만으로 구성하는 QA 프롬프트 빌더."""
    lines = []

    if legal_basis:
        lines.append("[관련 법령 조항 — 벡터 유사도 검색 결과]")
        for lb in legal_basis[:5]:
            rel = lb.get("relation_type", "")
            title = lb.get("statute_title", "")
            article = lb.get("provision_article", "")
            content = lb.get("provision_content", "")[:200]
            lines.append(f"• [{rel}] {title} {article}: {content}")

    if similar_ordinances:
        lines.append("\n[유사 조례 — 벡터 유사도 검색 결과]")
        for o in similar_ordinances[:3]:
            region = o.get("region_name", "")
            title = o.get("title", "")
            reason = o.get("relevance_reason", "")
            lines.append(f"• {region} 《{title}》 — {reason}")

    if legal_terms:
        lines.append("\n[관련 법률 용어 정의]")
        for lt in legal_terms[:5]:
            term = lt.get("term_name", "")
            defn = lt.get("definition", "")[:200]
            source = lt.get("source_statute", "")
            lines.append(f"• {term}: {defn} (출처: {source})")

    if not lines:
        lines.append("(관련 법령·조례 데이터를 찾지 못했습니다. 일반 법령 지식으로 답변합니다.)")

    lines.append(f"\n[질문]\n{question}")
    lines.append("\napplicable_content와 applicable_article_key는 null로 두세요.")

    return "\n".join(lines)
