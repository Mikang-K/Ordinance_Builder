from typing import Literal

from app.graph.state import OrdinanceBuilderState

RouteAtStart = Literal["intent_analyzer", "draft_reviewer", "legal_checker", "article_interviewer"]
RouteAfterIntent = Literal["interviewer", "graph_retriever"]
RouteAfterGraphRetriever = Literal["article_planner", "drafting_agent"]
RouteAfterArticleInterview = Literal["end", "drafting_agent"]
RouteAfterDraftReview = Literal["legal_checker", "end"]


def route_at_start(state: OrdinanceBuilderState) -> RouteAtStart:
    """
    Decide the entry node at the start of each user turn.

    - legal_review_requested: user submitted their own draft_text → skip to legal_checker
    - draft_review:           AI draft awaiting user review → draft_reviewer
    - article_interviewing:   per-article Q&A in progress → article_interviewer
    - article_complete:       all articles collected (e.g. from articles_batch) →
                              article_interviewer detects empty queue → routes to drafting_agent
    - otherwise:              begin from intent_analyzer as normal
    """
    current_stage: str = state.get("current_stage") or "intent_analysis"
    if current_stage == "legal_review_requested":
        return "legal_checker"
    if current_stage == "draft_review":
        return "draft_reviewer"
    if current_stage in ("article_interviewing", "article_complete"):
        return "article_interviewer"
    return "intent_analyzer"


def route_after_intent_analysis(state: OrdinanceBuilderState) -> RouteAfterIntent:
    """
    Decide the next node after intent_analyzer.

    Priority:
    1. Max interview turns exceeded → force proceed to graph_retriever
    2. Required fields still missing → ask more questions
    3. All basic fields collected → graph_retriever (which then routes to article_planner)
    """
    missing: list[str] = state.get("missing_fields") or []
    turn_count: int = state.get("interview_turn_count") or 0
    max_turns: int = state.get("max_interview_turns") or 5

    if turn_count >= max_turns or not missing:
        return "graph_retriever"

    return "interviewer"


def route_after_graph_retriever(state: OrdinanceBuilderState) -> RouteAfterGraphRetriever:
    """
    Decide the next node after graph_retriever.

    - article_queue is None: article interview hasn't started → article_planner
    - otherwise (interview done, or max_turns forced retrieval) → drafting_agent
    """
    # None  → article interview never initialized
    # []    → all articles collected (article_complete stage)
    # [...]  → interview still in progress (shouldn't reach here normally)
    article_queue = state.get("article_queue")
    if article_queue is None:
        return "article_planner"
    return "drafting_agent"


def route_after_article_interview(state: OrdinanceBuilderState) -> RouteAfterArticleInterview:
    """
    Decide the next node after article_interviewer.

    - More articles remain in the queue → END (await next user turn)
    - All articles done (stage='article_complete') → drafting_agent
      (graph_retriever already ran before article_planner, so skip it)
    """
    current_stage: str = state.get("current_stage") or ""
    if current_stage == "article_complete":
        return "drafting_agent"
    return "end"


def route_after_draft_review(state: OrdinanceBuilderState) -> RouteAfterDraftReview:
    """
    Decide the next node after draft_reviewer.

    - "confirm": proceed to legal validation
    - "revise":  return to END (updated draft shown to user for another review cycle)
    """
    decision: str = state.get("draft_review_decision") or "revise"
    if decision == "confirm":
        return "legal_checker"
    return "end"
