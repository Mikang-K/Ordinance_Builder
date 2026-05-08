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
    superior_provisions: list | None = None,
    penalty_chain: list | None = None,
    hierarchy_chain: list | None = None,    # SWRL Rule 2 위계 전이성
    conflict_chain: list | None = None,     # SWRL Rule 3 충돌 연쇄
    penalty_extension: list | None = None,  # SWRL Rule 4 벌칙 범위 확장
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

    # OWL: 우위에_있다 (SUPERIOR_TO) — hierarchically superior statute provisions
    superior_section = ""
    if superior_provisions:
        lines = [
            f"  [{p['statute_title']} ({p.get('statute_category', '')})] "
            f"{p['provision_article']}: {p['provision_content'][:300]}"
            for p in superior_provisions
        ]
        superior_section = "\n\n## 위계 상위 법령 조항 (SUPERIOR_TO)\n" + "\n".join(lines)

    # OWL: 제재하다 (PENALIZES) — penalty clause coverage
    penalty_section = ""
    if penalty_chain:
        lines = [
            f"  벌칙 {p['penalty_article']} → 대상 {p['target_article']}: "
            f"{p['target_content'][:200]}"
            for p in penalty_chain
        ]
        penalty_section = "\n\n## 벌칙 조항 연결 관계 (PENALIZES)\n" + "\n".join(lines)

    # SWRL Rule 2 — 위계 전이성 (get_hierarchy_chain)
    hierarchy_section = ""
    if hierarchy_chain:
        lines = [
            f"  [depth={h['depth']}] {h['statute_title']} ({h.get('statute_category', '')}) "
            f"→ {h['ordinance_title']}"
            for h in hierarchy_chain
        ]
        hierarchy_section = "\n\n## 위계 체계 (SWRL Rule 2 — 위계 전이성)\n" + "\n".join(lines)

    # SWRL Rule 3 — 충돌 연쇄 (get_conflict_chain)
    conflict_section = ""
    if conflict_chain:
        lines = [
            f"  [{c['conflict_term']}] 상위법 {c['statute_article']} ↔ 조례 {c['ordinance_article']}: "
            f"{c['statute_content'][:150]}"
            for c in conflict_chain
        ]
        conflict_section = "\n\n## 동일 용어 충돌 위험 (SWRL Rule 3 — 충돌 연쇄)\n" + "\n".join(lines)

    # SWRL Rule 4 — 벌칙 범위 확장 (get_penalty_extension)
    penalty_ext_section = ""
    if penalty_extension:
        lines = [
            f"  제재 {p['src_article']} → 간접제재 {p['ext_article']}: "
            f"{p.get('ext_content', '')[:150]}"
            for p in penalty_extension
        ]
        penalty_ext_section = "\n\n## 간접 제재 범위 (SWRL Rule 4 — 벌칙 범위 확장)\n" + "\n".join(lines)

    return f"""
## 검토 대상 조례 초안
{draft_text}

## 관련 상위법령 조항
{legal_refs}{terms_section}{superior_section}{penalty_section}{hierarchy_section}{conflict_section}{penalty_ext_section}

위 조례 초안을 상위법령과 대조하여 법률 정합성을 검토하세요.
특히 보조금 지급 조항과 벌칙 조항의 법적 근거를 집중 확인하세요.
SUPERIOR_TO 조항이 제공된 경우 위계 준수 여부를 추가 검토하세요.
PENALIZES 연결 관계가 제공된 경우 벌칙 적용 범위의 적정성을 검토하세요.
위계 체계가 제공된 경우 상위 법령 위계 전체의 규율 범위와 위임 한계를 검토하세요.
동일 용어 충돌이 제공된 경우 상위법·조례 간 용어 정의 충돌 가능성을 검토하세요.
간접 제재 범위가 제공된 경우 다단계 벌칙 체계의 적정성과 비례원칙 준수 여부를 검토하세요.
overall_assessment에는 조례 전체에 대한 종합 평가를 간결하게 작성하세요.
""".strip()
