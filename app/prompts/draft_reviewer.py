"""
Prompts for the Draft Reviewer node.

Two separate prompt sets:
1. Intent classification – decide whether the user wants to confirm or revise.
2. Revision application – apply the user's requested changes to the draft.
"""

# ---------------------------------------------------------------------------
# 1. Intent classification
# ---------------------------------------------------------------------------

DRAFT_REVIEWER_SYSTEM = """
당신은 조례 초안 검토 보조 AI입니다.
사용자의 메시지가 다음 중 어느 것인지 판단하세요:

1. "confirm" - 초안을 승인하고 법률 검증을 진행하겠다는 의사
   (예: "좋아요", "진행해주세요", "확인", "검증해주세요", "완료", "다음 단계로",
        "이대로 진행", "법률 검토 부탁드립니다", "괜찮아 보여요")

2. "revise" - 초안 내용을 수정해달라는 요청
   (예: "~을 바꿔주세요", "~조를 수정해주세요", "~을 추가해주세요",
        "~이 틀렸어요", "~을 삭제해주세요", "좀 더 구체적으로 써주세요")

반드시 "confirm" 또는 "revise" 중 하나만 반환하세요.
판단이 모호한 경우 "revise"로 처리하세요.
""".strip()


def build_draft_reviewer_human(user_input: str, draft_full_text: str) -> str:
    # Provide only a preview to save tokens
    preview = draft_full_text[:500] + ("..." if len(draft_full_text) > 500 else "")
    return (
        f"현재 초안 (앞부분 미리보기):\n{preview}\n\n"
        f"사용자 메시지:\n{user_input}\n\n"
        f"이 메시지는 \"confirm\"(법률 검증 진행)인가요, \"revise\"(수정 요청)인가요?"
    )


# ---------------------------------------------------------------------------
# 2. Revision application
# ---------------------------------------------------------------------------

from app.prompts.legal_terms import ONTOLOGY_TERM_GUIDE

DRAFT_REVISION_SYSTEM = f"""
당신은 30년 경력의 지방 조례 전문 법률 입법관입니다.
기존 조례 초안에 사용자의 수정 요청을 반영하여 수정된 완성본을 반환하세요.

수정 원칙:
1. 사용자가 명시적으로 요청한 부분만 수정하고 나머지 조문은 원문 유지.
2. 법적 형식과 조문 간 일관성 유지 — 온톨로지 기반 법률 용어 규칙을 준수.
3. full_text는 수정된 전체 조문을 합쳐 완성된 텍스트로 작성.

{ONTOLOGY_TERM_GUIDE}
""".strip()


def build_draft_revision_human(
    user_request: str,
    draft_full_text: str,
    draft_articles: list[dict],
) -> str:
    articles_text = "\n\n".join(
        f"{a['article_no']} {a['title']}\n{a['content']}"
        for a in draft_articles
    )
    return (
        f"## 현재 조례 초안\n{articles_text}\n\n"
        f"## 사용자 수정 요청\n{user_request}\n\n"
        f"위 수정 사항을 반영한 새 초안을 작성하세요."
    )
