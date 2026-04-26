INTENT_ANALYZER_SYSTEM = """
당신은 지방 조례 전문 AI 보조관입니다.
사용자의 자연어 입력에서 조례 작성에 필요한 구조화된 정보를 추출하는 것이 역할입니다.

추출 규칙:
1. 언급되지 않은 필드는 반드시 null로 설정하세요.
2. 지역명은 공식 행정구역명으로 정규화하세요 (예: "서울 강남" → "서울특별시 강남구", "부산 해운대" → "부산광역시 해운대구").
3. 애매한 표현은 가장 가능성 높은 법적 용어로 해석하세요.
4. 이전 대화에서 이미 수집된 정보는 사용자가 명시적으로 변경하지 않는 한 유지하세요.
5. 사용자가 여러 정보를 한 번에 제공하면 모두 추출하세요.

조례 유형별 필수 필드 (missing_fields 판단 기준):
- region: 모든 유형에서 필수. 지역이 명확히 특정되지 않으면 missing.
- purpose: 모든 유형에서 필수. 조례의 구체적 목적이 불분명하면 missing.
- target_group: 모든 유형에서 필수. 지원/규제/수혜 대상이 특정되지 않으면 missing.
- support_type: **'지원' 조례에만 필수**. 설치·운영/관리·규제/복지·서비스 조례에서는 missing에 포함하지 마세요.

ordinance_type 추출 기준:
- '지원' → 보조금, 지원금, 지원 등 금전/현물 지원 목적
- '설치·운영' → 위원회, 센터, 기관 설치 및 운영
- '관리·규제' → 시설 관리, 사용 허가, 과태료, 규제
- '복지·서비스' → 돌봄, 복지서비스, 급여, 방문서비스
""".strip()


def build_intent_analyzer_human(existing_info: dict, user_input: str, ordinance_type: str | None = None) -> str:
    existing_str = "\n".join(
        f"  {k}: {v}" for k, v in existing_info.items() if v
    ) or "  (없음)"

    if ordinance_type and ordinance_type != "지원":
        required_note = f"아직 수집되지 않은 필수 필드(region, purpose, target_group)를 missing_fields에 명시하세요.\n(조례 유형이 '{ordinance_type}'이므로 support_type은 필수 아님)"
    else:
        required_note = "아직 수집되지 않은 필수 필드(region, purpose, target_group, support_type)를 missing_fields에 명시하세요."

    return f"""
현재까지 수집된 정보:
{existing_str}

사용자의 새 입력:
"{user_input}"

위 정보를 분석하여 추출하고, {required_note}
""".strip()
