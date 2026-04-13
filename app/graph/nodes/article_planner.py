from langchain_core.messages import AIMessage

from app.graph.nodes._article_examples import find_article_examples, format_examples_block
from app.graph.state import OrdinanceBuilderState

# Per-article question templates
ARTICLE_TEMPLATES: dict[str, dict] = {
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
}

# Default article order used for most support-type ordinances
DEFAULT_ARTICLE_ORDER = [
    "목적", "정의", "지원대상", "지원내용",
    "지원금액", "신청방법", "심사선정", "환수제재", "위임",
]


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

    # Tailor the article list to the support type
    if support_type and any(kw in support_type for kw in ["컨설팅", "교육", "멘토링", "상담"]):
        article_order = ["목적", "정의", "지원대상", "지원내용", "신청방법", "위임"]
    elif support_type and "시설" in support_type:
        article_order = ["목적", "정의", "지원대상", "지원내용", "신청방법", "심사선정", "환수제재", "위임"]
    else:
        article_order = list(DEFAULT_ARTICLE_ORDER)

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
