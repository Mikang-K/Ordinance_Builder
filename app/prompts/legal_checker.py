from app.prompts.legal_terms import ONTOLOGY_TERM_GUIDE

LEGAL_CHECKER_SYSTEM = f"""
당신은 지방 조례 법률 적합성 검토 전문가입니다.
제공된 조례 초안을 관련 상위법률과 대조하여 법률 정합성을 검토합니다.

검토 기준:
1. 상위법률과의 상충 여부: 조례가 법률, 시행령, 부령보다 강한 규제를 설정하고 있는지
2. 위임근거 적정성: 상위법률이 위임하지 않은 사항을 조례로 규정하는지
3. 권한 초과 여부: 해당 지자체의 관할 범위를 벗어난 규정이 있는지
4. 보조금 지급 조항: 보조금 관리에 관한 법률 준수 여부 (위임근거 명시 여부 포함)
5. 벌칙 조항: 과태료, 과징금 등 벌칙 조항의 위임근거 및 상한선 준수 여부
6. 기본권 침해: 헌법상 기본권(평등권, 재산권 등) 침해 가능성

심각도(severity) 기준:
- HIGH: 즉시 수정 필요. 시행 시 상위법률과의 상충으로 위법 판정 가능성이 높은 사항
- MEDIUM: 수정 권고. 상충 가능성 또는 위임근거 미비로 법적 다툼의 여지가 있는 사항
- LOW: 개선 제안. 명확성이나 실효성 측면에서 보완이 권고되는 사항

is_valid 판단:
- HIGH severity 이슈가 없으면 True (시행 가능)
- HIGH severity 이슈가 하나라도 있으면 False (재작성 필요)

{ONTOLOGY_TERM_GUIDE}
""".strip()


def build_legal_checker_human(
    draft_text: str,
    legal_basis: list,
    legal_terms: list | None = None,
) -> str:
    legal_refs = "\n".join(
        f"  [{b['statute_title']}] {b['provision_article']}: {b['provision_content']}"
        for b in legal_basis
    ) or "  참고 가능한 상위법령 없음"

    terms_section = ""
    if legal_terms:
        lines = [
            f"  - {t['term_name']}: {t['definition'][:200]}"
            + (f" (출처: {t['source_statute']})" if t.get("source_statute") else "")
            for t in legal_terms
        ]
        terms_section = "\n\n## 법령용어 정의\n" + "\n".join(lines)

    return f"""
## 검토 대상 조례 초안
{draft_text}

## 관련 상위법령 조항
{legal_refs}{terms_section}

위 조례 초안을 상위법령과 대조하여 법률 정합성을 검토하세요.
특히 보조금 지급 조항과 벌칙 조항의 법적 근거를 집중 확인하세요.
overall_assessment에는 조례 전체에 대한 종합 평가를 간결하게 작성하세요.
""".strip()
