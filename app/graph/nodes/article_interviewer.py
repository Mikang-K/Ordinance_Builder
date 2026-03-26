from langchain_core.messages import AIMessage, HumanMessage

from app.graph.nodes._article_examples import find_article_examples, format_examples_block
from app.graph.nodes.article_planner import ARTICLE_TEMPLATES, DEFAULT_ARTICLE_ORDER
from app.graph.state import OrdinanceBuilderState

# Keywords the user can type to skip an article (AI will fill it automatically)
_SKIP_KEYWORDS = {"기본값", "기본값 사용", "skip", "스킵", "넘기기", "다음", "자동"}


def article_interviewer_node(state: OrdinanceBuilderState) -> dict:
    """
    Node: Article Interviewer  (deterministic, no LLM)

    1. Stores (or skips) the user's answer for the current article.
    2. Advances to the next article in the queue.
       - More articles remain → ask the next question → END (await user)
       - All articles done   → set stage='article_complete' (conditional edge
                               will immediately route to graph_retriever)

    Input  State: user_input, current_article_key, article_queue, article_contents
    Output State: article_contents, article_queue, current_article_key,
                  current_stage, response_to_user, messages
    """
    user_input: str = (state.get("user_input") or "").strip()
    current_key: str = state.get("current_article_key") or ""
    article_queue: list[str] = list(state.get("article_queue") or [])
    article_contents: dict = dict(state.get("article_contents") or {})

    messages: list = [HumanMessage(content=user_input)]

    # Persist the user's answer; None signals "use AI default"
    if current_key:
        is_skip = user_input.lower() in _SKIP_KEYWORDS
        article_contents[current_key] = None if is_skip else user_input

    current_title = ARTICLE_TEMPLATES.get(current_key, {}).get("title", current_key)
    saved_label = "AI 자동 생성으로 설정" if article_contents.get(current_key) is None else "저장 완료"
    filled_count = len(article_contents)
    total = filled_count + len(article_queue)

    # ── All articles filled ───────────────────────────────────────────────────
    if not article_queue:
        user_provided = sum(1 for v in article_contents.values() if v is not None)
        ai_filled = filled_count - user_provided
        summary_lines = [
            f"  • {k}: {'직접 입력' if v is not None else 'AI 자동 생성'}"
            for k, v in article_contents.items()
        ]
        completion_msg = (
            f"✓ **{current_title}** {saved_label}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"모든 조항 입력이 완료되었습니다! ✅\n\n"
            f"  직접 입력: {user_provided}개 / AI 자동 생성: {ai_filled}개\n\n"
            + "\n".join(summary_lines)
            + "\n\n관련 법령을 검색하고 조례 초안을 생성합니다..."
        )
        messages.append(AIMessage(content=completion_msg))
        return {
            "current_stage": "article_complete",
            "article_queue": [],
            "current_article_key": None,
            "article_contents": article_contents,
            "response_to_user": completion_msg,
            "messages": messages,
        }

    # ── Ask about the next article ────────────────────────────────────────────
    next_key = article_queue[0]
    remaining = article_queue[1:]
    next_template = ARTICLE_TEMPLATES.get(next_key, {})
    next_title = next_template.get("title", next_key)
    next_question = next_template.get("question", f"{next_key}에 대해 설명해 주세요.")

    # Find matching provision examples from similar ordinances
    article_examples: list[dict] = list(state.get("article_examples") or [])
    examples_block = format_examples_block(
        find_article_examples(next_key, article_examples)
    )

    response = (
        f"✓ **{current_title}** {saved_label}\n\n"
        f"━━━ **{filled_count + 1} / {total}** ━━━\n\n"
        f"**[{next_title}]**\n\n"
        f"{next_question}"
        f"{examples_block}"
    )
    messages.append(AIMessage(content=response))

    return {
        "current_stage": "article_interviewing",
        "article_queue": remaining,
        "current_article_key": next_key,
        "article_contents": article_contents,
        "response_to_user": response,
        "messages": messages,
    }
