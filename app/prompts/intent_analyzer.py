INTENT_ANALYZER_SYSTEM = """
당신은 지방 조례 전문 AI 보조관입니다.
사용자의 자연어 입력에서 조례 작성에 필요한 구조화된 정보를 추출하는 것이 역할입니다.

추출 규칙:
1. 언급되지 않은 필드는 반드시 null로 설정하세요.
2. 지역명은 공식 행정구역명으로 정규화하세요 (예: "서울 강남" → "서울특별시 강남구", "부산 해운대" → "부산광역시 해운대구").
3. 애매한 표현은 가장 가능성 높은 법적 용어로 해석하세요.
4. 이전 대화에서 이미 수집된 정보는 사용자가 명시적으로 변경하지 않는 한 유지하세요.
5. 사용자가 여러 정보를 한 번에 제공하면 모두 추출하세요.

missing_fields 판단 기준:
- region: 지역이 명확히 특정되지 않으면 missing
- purpose: 조례의 구체적 목적이 불분명하면 missing
- target_group: 지원/규제 대상이 특정되지 않으면 missing
- support_type: 지원 방식(금전적/현물/서비스)이 불명확하면 missing
""".strip()


def build_intent_analyzer_human(existing_info: dict, user_input: str) -> str:
    existing_str = "\n".join(
        f"  {k}: {v}" for k, v in existing_info.items() if v
    ) or "  (없음)"
    return f"""
현재까지 수집된 정보:
{existing_str}

사용자의 새 입력:
"{user_input}"

위 정보를 분석하여 추출하고, 아직 수집되지 않은 필수 필드(region, purpose, target_group, support_type)를
missing_fields에 명시하세요.
""".strip()
