from functools import partial

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph

from app.core.config import settings
from app.core.llm import get_llm
from app.db.neo4j_db import Neo4jGraphDB
from app.graph.edges.conditions import (
    route_after_intent_analysis,
    route_after_graph_retriever,
    route_after_article_interview,
    route_after_draft_review,
    route_at_start,
)
from app.graph.nodes.article_interviewer import article_interviewer_node
from app.graph.nodes.article_planner import article_planner_node
from app.graph.nodes.draft_reviewer import draft_reviewer_node
from app.graph.nodes.drafting_agent import drafting_agent_node
from app.graph.nodes.graph_retriever import graph_retriever_node
from app.graph.nodes.intent_analyzer import intent_analyzer_node
from app.graph.nodes.interviewer import interviewer_node
from app.graph.nodes.legal_checker import legal_checker_node
from app.graph.state import OrdinanceBuilderState

# ---------------------------------------------------------------------------
# Compiled graph singleton — set by main.py lifespan after checkpointer init
# ---------------------------------------------------------------------------
_graph_app = None
_db_instance = None


def set_graph(compiled_graph) -> None:
    """lifespan 훅에서 AsyncPostgresSaver 초기화 후 호출."""
    global _graph_app
    _graph_app = compiled_graph


def get_graph():
    """컴파일된 그래프 싱글톤 반환."""
    return _graph_app


def get_db():
    """Neo4jGraphDB 싱글톤 반환 (QA 엔드포인트용 읽기 전용 접근)."""
    return _db_instance


def create_workflow(checkpointer: AsyncPostgresSaver):
    """
    LangGraph 조례 초안 생성 워크플로우를 조립하고 컴파일합니다.
    checkpointer는 main.py lifespan에서 초기화된 AsyncPostgresSaver를 주입받습니다.

    Graph topology:
        START ──[legal_review_requested]──→ legal_checker ──→ END
          │   [draft_review]──────────────→ draft_reviewer ──[confirm]──→ legal_checker
          │                                                  [revise]───→ END
          ↓ [otherwise]
        intent_analyzer ──[missing?]──→ interviewer ──→ END (await next user turn)
          ↓ [all collected / max_turns]
        graph_retriever ──[article_queue is None]──→ article_planner ──→ END
          │             [otherwise]──────────────→ drafting_agent ──→ END
          ↓
        article_interviewer ──[more articles]──→ END
                            ──[article_complete]──→ drafting_agent ──→ END

        legal_checker ──→ END  (user decides: re-check or finalize via /finalize)
    """
    # 노드별 역할에 최적화된 LLM 배정
    # intent_analyzer : Gemini 2.5 Pro  — 한국어 구조화 추출
    # drafting_agent  : Claude Opus 4.6 — 장문 법적 문서 작성
    # draft_reviewer  : Claude Opus 4.6 — 초안 수정 생성
    # legal_checker   : GPT-4o          — 비판적 법률 분석
    intent_llm   = get_llm(settings.LLM_INTENT)
    drafting_llm = get_llm(settings.LLM_DRAFTING)
    reviewer_llm = get_llm(settings.LLM_REVIEWER)
    legal_llm    = get_llm(settings.LLM_LEGAL)

    global _db_instance
    db = Neo4jGraphDB(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    _db_instance = db

    builder: StateGraph = StateGraph(OrdinanceBuilderState)

    # Register nodes (inject dependencies via partial)
    builder.add_node("intent_analyzer", partial(intent_analyzer_node, llm=intent_llm))
    builder.add_node("interviewer", interviewer_node)
    builder.add_node("article_planner", article_planner_node)
    builder.add_node("article_interviewer", article_interviewer_node)
    builder.add_node("graph_retriever", partial(graph_retriever_node, db=db))
    builder.add_node("drafting_agent", partial(drafting_agent_node, llm=drafting_llm))
    builder.add_node("draft_reviewer", partial(draft_reviewer_node, llm=reviewer_llm))
    builder.add_node("legal_checker", partial(legal_checker_node, llm=legal_llm))

    builder.add_conditional_edges(
        START,
        route_at_start,
        {
            "intent_analyzer": "intent_analyzer",
            "draft_reviewer": "draft_reviewer",
            "legal_checker": "legal_checker",
            "article_interviewer": "article_interviewer",
        },
    )

    builder.add_conditional_edges(
        "intent_analyzer",
        route_after_intent_analysis,
        {
            "interviewer": "interviewer",
            "graph_retriever": "graph_retriever",
        },
    )

    builder.add_edge("interviewer", END)

    builder.add_conditional_edges(
        "graph_retriever",
        route_after_graph_retriever,
        {
            "article_planner": "article_planner",
            "drafting_agent": "drafting_agent",
        },
    )

    builder.add_edge("article_planner", END)

    builder.add_conditional_edges(
        "article_interviewer",
        route_after_article_interview,
        {
            "end": END,
            "drafting_agent": "drafting_agent",
        },
    )

    builder.add_edge("drafting_agent", END)

    builder.add_conditional_edges(
        "draft_reviewer",
        route_after_draft_review,
        {
            "legal_checker": "legal_checker",
            "end": END,
        },
    )

    builder.add_edge("legal_checker", END)

    return builder.compile(checkpointer=checkpointer)
