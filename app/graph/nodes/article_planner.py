from langchain_core.messages import AIMessage

from app.graph.nodes._article_examples import find_article_examples, format_examples_block
from app.graph.state import OrdinanceBuilderState

# Per-article question templates
ARTICLE_TEMPLATES: dict[str, dict] = {
    # ── 지원 조례 (기존) ─────────────────────────────────────────────────────
    "목적": {
        "title": "목적 조항 (제1조)",
        "question": (
            "이 조례가 달성하고자 하는 **목적**을 작성해 주세요.\n\n"
            "  • 무엇을 지원/규제하는 조례인지\n"
            "  • 궁극적으로 실현하고자 하는 공익적 가치\n\n"
            "  예시: '청년의 창업 활동을 지원하고 지역 경제 활성화에 이바지함을 목적으로 한다.'"
        ),
    },
    "정의": {
        "title": "정의 조항 (제2조)",
        "question": (
            "이 조례에서 사용하는 **핵심 용어의 정의**를 작성해 주세요.\n\n"
            "  • 대상자 정의 (예: '청년'이란 만 19세 이상 39세 이하인 사람을 말한다.)\n"
            "  • 기타 주요 용어\n\n"
            "  여러 용어는 각각 입력해 주세요.  건너뛰려면 **'기본값'** 이라고 입력하세요."
        ),
    },
    "지원대상": {
        "title": "지원 대상 및 자격 조항",
        "question": (
            "지원 대상의 **자격 요건**을 구체적으로 작성해 주세요.\n\n"
            "  • 필수 요건 (거주지, 연령, 사업 기간 등)\n"
            "  • 지원 제외 대상 (해당 시)\n\n"
            "  예시: '공고일 기준 해당 지역에 6개월 이상 주소를 둔 만 19~39세 청년'"
        ),
    },
    "지원내용": {
        "title": "지원 내용 조항",
        "question": (
            "구체적인 **지원 내용**을 작성해 주세요.\n\n"
            "  • 지원 항목 (예: 창업 초기비용, 임대료, 교육비 등)\n"
            "  • 지원 방식 (현금, 현물, 바우처, 이용권 등)\n\n"
            "  예시: '예산 범위 내에서 창업 공간 임대료의 50% 이내를 보조금으로 지급한다.'"
        ),
    },
    "지원금액": {
        "title": "지원 금액 및 기준 조항",
        "question": (
            "지원 금액 및 **산정 기준**을 작성해 주세요.\n\n"
            "  • 1인당 지원 한도 금액\n"
            "  • 지원 기간 (예: 최대 2년)\n"
            "  • 지원 비율 (예: 총비용의 70% 이내)\n\n"
            "  건너뛰려면 **'기본값'** 이라고 입력하세요."
        ),
    },
    "신청방법": {
        "title": "신청 방법 및 절차 조항",
        "question": (
            "신청 절차 및 **제출 서류**를 작성해 주세요.\n\n"
            "  • 신청 기관 (예: 구청 경제과)\n"
            "  • 신청 방법 (방문 / 온라인 / 우편)\n"
            "  • 필요 서류 목록\n\n"
            "  건너뛰려면 **'기본값'** 이라고 입력하세요."
        ),
    },
    "심사선정": {
        "title": "심사 및 선정 조항",
        "question": (
            "심사 및 선정 방법을 작성해 주세요.\n\n"
            "  • 심사 기관 또는 위원회 구성\n"
            "  • 심사 기준 (배점 등)\n"
            "  • 결과 통보 방법\n\n"
            "  건너뛰려면 **'기본값'** 이라고 입력하세요."
        ),
    },
    "환수제재": {
        "title": "환수 및 제재 조항",
        "question": (
            "지원금 **환수 및 제재** 조건을 작성해 주세요.\n\n"
            "  • 환수 사유 (허위 신청, 목적 외 사용 등)\n"
            "  • 환수 비율 또는 금액\n"
            "  • 지원 제한 기간 등 추가 제재\n\n"
            "  건너뛰려면 **'기본값'** 이라고 입력하세요."
        ),
    },
    "위임": {
        "title": "위임 조항",
        "question": (
            "**세부 사항 위임** 규정을 작성해 주세요.\n\n"
            "  예시: '이 조례의 시행에 필요한 사항은 규칙으로 정한다.'\n\n"
            "  건너뛰려면 **'기본값'** 이라고 입력하세요."
        ),
    },
    # ── 설치·운영 조례 (신규) ─────────────────────────────────────────────────
    "설치": {
        "title": "설치 조항",
        "question": (
            "위원회·자문단·심의회의 **설치 근거와 명칭**을 작성해 주세요.\n\n"
            "  • 기관 명칭 (예: '○○청년정책위원회')\n"
            "  • 설치 목적 및 소속\n\n"
            "  예시: '청년 정책의 심의·자문을 위하여 시장 소속으로 ○○청년정책위원회를 둔다.'\n\n"
            "  건너뛰려면 **'기본값'** 이라고 입력하세요."
        ),
    },
    "구성": {
        "title": "구성 조항",
        "question": (
            "위원회의 **구성 및 위원 자격**을 작성해 주세요.\n\n"
            "  • 위원 정수 (예: 위원장 포함 9명 이내)\n"
            "  • 위원 임기 (예: 2년, 1회 연임 가능)\n"
            "  • 위원 자격 (전문가, 공무원, 주민 대표 등)\n\n"
            "  건너뛰려면 **'기본값'** 이라고 입력하세요."
        ),
    },
    "직무": {
        "title": "직무 조항",
        "question": (
            "위원장 및 위원의 **직무와 권한**을 작성해 주세요.\n\n"
            "  • 위원장 역할 (회의 소집·주재 등)\n"
            "  • 심의·의결 사항 목록\n\n"
            "  건너뛰려면 **'기본값'** 이라고 입력하세요."
        ),
    },
    "운영": {
        "title": "운영 조항",
        "question": (
            "위원회의 **운영 방식**을 작성해 주세요.\n\n"
            "  • 정기회의 주기 (예: 반기 1회)\n"
            "  • 임시회의 소집 요건\n"
            "  • 의결 정족수 (예: 재적 과반수 출석, 출석 과반수 의결)\n\n"
            "  건너뛰려면 **'기본값'** 이라고 입력하세요."
        ),
    },
    "간사": {
        "title": "간사 조항",
        "question": (
            "위원회 사무를 처리할 **간사**에 대해 작성해 주세요.\n\n"
            "  • 간사 지정 방법 (예: 담당 부서 소속 공무원 중 위원장이 지정)\n"
            "  • 간사의 역할 (회의록 작성, 자료 준비 등)\n\n"
            "  건너뛰려면 **'기본값'** 이라고 입력하세요."
        ),
    },
    # ── 관리·규제 조례 (신규) ─────────────────────────────────────────────────
    "적용범위": {
        "title": "적용 범위 조항",
        "question": (
            "이 조례의 **적용 대상과 범위**를 작성해 주세요.\n\n"
            "  • 적용되는 시설·장소·행위의 범위\n"
            "  • 적용 제외 사항 (해당 시)\n\n"
            "  예시: '이 조례는 ○○시가 설치·운영하는 공공체육시설에 적용한다.'\n\n"
            "  건너뛰려면 **'기본값'** 이라고 입력하세요."
        ),
    },
    "관리책임": {
        "title": "관리 책임 조항",
        "question": (
            "시설·대상의 **관리 주체와 책임**을 작성해 주세요.\n\n"
            "  • 관리 주체 (시장, 위탁 기관 등)\n"
            "  • 위탁 관리 시 위탁 절차\n"
            "  • 관리 기본 원칙\n\n"
            "  건너뛰려면 **'기본값'** 이라고 입력하세요."
        ),
    },
    "사용허가": {
        "title": "사용 허가 조항",
        "question": (
            "시설 사용 **허가 절차 및 조건**을 작성해 주세요.\n\n"
            "  • 허가 신청 방법 및 제출 서류\n"
            "  • 허가 기간 및 갱신 가능 여부\n"
            "  • 허가 취소·제한 사유\n\n"
            "  건너뛰려면 **'기본값'** 이라고 입력하세요."
        ),
    },
    "사용료": {
        "title": "사용료 조항",
        "question": (
            "시설 **사용료 산정 기준과 징수 방법**을 작성해 주세요.\n\n"
            "  • 요금 기준 (시간제, 일제, 월제 등)\n"
            "  • 감면 대상 및 감면율\n"
            "  • 사용료 반환 조건\n\n"
            "  건너뛰려면 **'기본값'** 이라고 입력하세요."
        ),
    },
    "위반제재": {
        "title": "위반 및 제재 조항",
        "question": (
            "위반 행위에 대한 **제재 기준**을 작성해 주세요.\n\n"
            "  • 과태료 상한액 (예: 100만원 이하)\n"
            "  • 허가 취소·사용 제한 사유\n"
            "  • 원상복구 명령 등 행정 조치\n\n"
            "  건너뛰려면 **'기본값'** 이라고 입력하세요."
        ),
    },
    # ── 복지·서비스 조례 (신규) ───────────────────────────────────────────────
    "서비스내용": {
        "title": "서비스 내용 조항",
        "question": (
            "제공할 **복지 서비스의 내용**을 구체적으로 작성해 주세요.\n\n"
            "  • 서비스 종류 (방문 돌봄, 의료비 지원, 식사 제공 등)\n"
            "  • 서비스 제공 기준 및 횟수\n\n"
            "  예시: '주 3회 이상 방문 돌봄 서비스 및 월 10만원 이내 의료비 지원'\n\n"
            "  건너뛰려면 **'기본값'** 이라고 입력하세요."
        ),
    },
    "제공기관": {
        "title": "서비스 제공 기관 조항",
        "question": (
            "서비스를 **제공하는 기관과 지정 절차**를 작성해 주세요.\n\n"
            "  • 제공 기관 유형 (공공기관, 민간 위탁 기관 등)\n"
            "  • 지정·위탁 기준 및 절차\n"
            "  • 지도·감독 방법\n\n"
            "  건너뛰려면 **'기본값'** 이라고 입력하세요."
        ),
    },
    "신청접수": {
        "title": "신청 및 접수 조항",
        "question": (
            "서비스 **신청 및 접수 절차**를 작성해 주세요.\n\n"
            "  • 신청 자격 확인 방법\n"
            "  • 접수 채널 (방문, 온라인, 전화 등)\n"
            "  • 신청 서류 목록\n\n"
            "  건너뛰려면 **'기본값'** 이라고 입력하세요."
        ),
    },
    "비용": {
        "title": "비용 및 본인부담 조항",
        "question": (
            "서비스 **이용 비용과 본인부담 기준**을 작성해 주세요.\n\n"
            "  • 무료 제공 여부 또는 본인부담 방식 (정액, 소득 연동 등)\n"
            "  • 감면 대상 (기초생활수급자, 장애인 등)\n\n"
            "  건너뛰려면 **'기본값'** 이라고 입력하세요."
        ),
    },
}

# Default article order used for support-type ordinances
DEFAULT_ARTICLE_ORDER = [
    "목적", "정의", "지원대상", "지원내용",
    "지원금액", "신청방법", "심사선정", "환수제재", "위임",
]

# Article order for non-support ordinance types
TYPE_ARTICLE_ORDER: dict[str, list[str]] = {
    "설치·운영": ["목적", "정의", "설치", "구성", "직무", "운영", "간사", "위임"],
    "관리·규제": ["목적", "정의", "적용범위", "관리책임", "사용허가", "사용료", "위반제재", "위임"],
    "복지·서비스": ["목적", "정의", "지원대상", "서비스내용", "제공기관", "신청접수", "비용", "위임"],
}


def _legacy_order(support_type: str) -> list[str]:
    """Return article order based on support_type keywords (backward compat)."""
    if support_type and any(kw in support_type for kw in ["컨설팅", "교육", "멘토링", "상담"]):
        return ["목적", "정의", "지원대상", "지원내용", "신청방법", "위임"]
    if support_type and "시설" in support_type:
        return ["목적", "정의", "지원대상", "지원내용", "신청방법", "심사선정", "환수제재", "위임"]
    return list(DEFAULT_ARTICLE_ORDER)


def article_planner_node(state: OrdinanceBuilderState) -> dict:
    """
    Node: Article Planner  (deterministic, no LLM)

    Initializes the per-article interview queue based on ordinance type,
    then asks the user about the first article.

    Input  State: ordinance_info
    Output State: article_queue, current_article_key, article_contents,
                  current_stage, response_to_user, messages
    """
    ordinance_info = state.get("ordinance_info") or {}
    support_type: str = ordinance_info.get("support_type", "")
    region: str = ordinance_info.get("region", "해당 지역")
    purpose: str = ordinance_info.get("purpose", "")
    ordinance_type: str = state.get("ordinance_type") or ""

    # Tailor the article list to the ordinance type (new) or support type (legacy)
    if ordinance_type and ordinance_type in TYPE_ARTICLE_ORDER:
        article_order = list(TYPE_ARTICLE_ORDER[ordinance_type])
    else:
        article_order = _legacy_order(support_type)

    first_key = article_order[0]
    remaining = article_order[1:]
    template = ARTICLE_TEMPLATES[first_key]
    total = len(article_order)

    intro = (
        f"기본 정보 수집이 완료되었습니다!\n\n"
        f"이제 **{region} {purpose} 조례**의 상세 조항 내용을 입력할 차례입니다.\n"
        f"팝업된 모달 창에서 아래 가이드라인을 참고하여 각 조항을 작성해 주세요.\n"
        f"(입력하기 어려운 항목은 '기본값' 버튼을 누르면 AI가 자동으로 채워드립니다.)\n\n"
        f"━━━ **조항 작성 가이드라인** ━━━\n\n"
    )

    for i, key in enumerate(article_order, 1):
        template = ARTICLE_TEMPLATES[key]
        intro += f"**[{i}] {template['title']}**\n{template['question']}\n\n"

    # Surface examples from similar ordinances for the first article
    article_examples: list[dict] = list(state.get("article_examples") or [])
    first_examples = find_article_examples(first_key, article_examples)
    if first_examples:
        intro += f"━━━ **참고: 첫 번째 조항({ARTICLE_TEMPLATES[first_key]['title']}) 유사 사례** ━━━\n{format_examples_block(first_examples)}"

    return {
        "current_stage": "article_interviewing",
        "article_queue": remaining,
        "current_article_key": first_key,
        "article_contents": {},
        "response_to_user": intro,
        "messages": [AIMessage(content=intro)],
    }
