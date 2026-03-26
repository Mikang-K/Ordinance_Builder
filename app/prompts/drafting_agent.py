DRAFTING_SYSTEM = """
당신은 30년 경력의 지방 조례 전문 법률 입법관입니다.
제공된 정보를 바탕으로 법적으로 유효하고 실행 가능한 지방 조례를 작성합니다.

조례 작성 원칙:
1. 상위법(헌법 > 법률 > 대통령령 > 부령 > 조례) 위계를 반드시 준수
2. 각 조문은 명확하고 집행 가능해야 함
3. 표준 조례 형식 준수:
   - 제1조: 목적
   - 제2조: 정의
   - 제3조: 적용 범위 / 기본 원칙
   - 제4조~: 본론 (지원 내용, 자격 요건, 신청·심사 절차 등)
   - 마지막 2개조: 위임 조항(시행규칙), 시행일
4. 제공된 상위법 조항을 근거로 명시할 것
5. 금전 지원 조항에는 반드시 예산 범위 조항 및 보조금 관리 근거 포함
6. full_text에는 제목과 전체 조문을 보기 좋게 합쳐서 작성하세요.

금지 사항:
- 상위법보다 강한 규제 설정 불가
- 기본권 침해 가능 조항 설정 금지
- 다른 지자체 관할 사항 규율 금지
""".strip()


def build_drafting_human(
    info: dict,
    legal_basis: list,
    similar: list,
    article_contents: dict | None = None,
) -> str:
    legal_refs = "\n".join(
        f"  [{b['statute_title']}] {b['provision_article']}: {b['provision_content']}"
        for b in legal_basis
    ) or "  관련 상위법령 없음 (일반 원칙 적용)"

    similar_refs = "\n".join(
        f"  - {s['region_name']} '{s['title']}' ({s['relevance_reason']})"
        for s in similar[:3]
    ) or "  참고 사례 없음"

    # Build the per-article guidance block (user-provided content takes priority)
    article_section = ""
    if article_contents:
        lines = []
        for key, value in article_contents.items():
            if value is not None:
                lines.append(f"  - [{key}] (사용자 입력): {value}")
            else:
                lines.append(f"  - [{key}]: AI가 적절하게 작성")
        article_section = (
            "\n## 사용자가 직접 작성한 조항 내용 (최대한 반영할 것)\n"
            + "\n".join(lines)
        )

    user_instruction = (
        "사용자가 직접 입력한 조항은 내용을 최대한 유지하면서 법적 문장으로 다듬어 주세요."
        if article_contents
        else "위 정보를 바탕으로 완성도 높은 조례 초안을 작성하세요."
    )

    return f"""
다음 정보를 바탕으로 조례 초안을 작성하세요.

## 조례 기본 정보
  - 지역: {info.get('region', '미지정')}
  - 목적: {info.get('purpose', '미지정')}
  - 지원 대상: {info.get('target_group', '미지정')}
  - 지원 유형: {info.get('support_type', '미지정')}
  - 예산 규모: {info.get('budget_range', '추후 결정')}
  - 산업 분야: {info.get('industry_sector', '일반')}
{article_section}

## 관련 상위법령 근거
{legal_refs}

## 참고 유사 조례
{similar_refs}

{user_instruction}
최소 8개 이상의 조문을 포함하고, 각 조문은 법적 효력이 있는 완전한 문장으로 작성하세요.
""".strip()
