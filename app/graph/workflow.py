import sqlite3
from functools import partial

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from app.core.config import settings
from app.core.llm import get_llm
from app.db.mock_db import MockGraphDB
from app.db.neo4j_db import Neo4jGraphDB  # uncomment after pipeline load
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
# Compiled graph singleton
# ---------------------------------------------------------------------------
_graph_app = None
_memory: SqliteSaver | None = None


def create_workflow():
    """
    Assemble and compile the LangGraph ordinance-drafting workflow.

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

    Note: graph_retriever runs BEFORE article_planner so similar-ordinance provision
    examples are available throughout the entire article interview phase.

    Returns:
        (compiled_app, memory_saver) tuple
    """
    llm = get_llm()

    # Switch to Neo4jGraphDB after running pipeline/scripts/initial_load.py:
    db = Neo4jGraphDB(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    #db = MockGraphDB()

    builder: StateGraph = StateGraph(OrdinanceBuilderState)

    # Register nodes (inject dependencies via partial)
    builder.add_node("intent_analyzer", partial(intent_analyzer_node, llm=llm))
    builder.add_node("interviewer", interviewer_node)                         # no LLM
    builder.add_node("article_planner", article_planner_node)                 # no LLM
    builder.add_node("article_interviewer", article_interviewer_node)         # no LLM
    builder.add_node("graph_retriever", partial(graph_retriever_node, db=db)) # no LLM
    builder.add_node("drafting_agent", partial(drafting_agent_node, llm=llm))
    builder.add_node("draft_reviewer", partial(draft_reviewer_node, llm=llm))
    builder.add_node("legal_checker", partial(legal_checker_node, llm=llm))

    # Entry point routing:
    # - legal_review_requested → legal_checker (user submitted their own draft)
    # - draft_review           → draft_reviewer (AI-assisted revision loop)
    # - article_interviewing   → article_interviewer (per-article Q&A in progress)
    # - otherwise              → intent_analyzer (normal interview flow)
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

    # Conditional branch: missing fields → interview, otherwise → graph_retriever
    builder.add_conditional_edges(
        "intent_analyzer",
        route_after_intent_analysis,
        {
            "interviewer": "interviewer",
            "graph_retriever": "graph_retriever",
        },
    )

    # Interviewer suspends execution until the next user message arrives
    builder.add_edge("interviewer", END)

    # graph_retriever runs before article_planner so examples are ready for the interview.
    # article_queue is None → first run, start article interview
    # otherwise (interview done or max_turns) → go straight to drafting
    builder.add_conditional_edges(
        "graph_retriever",
        route_after_graph_retriever,
        {
            "article_planner": "article_planner",
            "drafting_agent": "drafting_agent",
        },
    )

    # Article planner asks the first article question, then suspends
    builder.add_edge("article_planner", END)

    # Article interviewer: more articles → END, all done → drafting_agent directly
    # (graph_retriever already ran before article_planner)
    builder.add_conditional_edges(
        "article_interviewer",
        route_after_article_interview,
        {
            "end": END,
            "drafting_agent": "drafting_agent",
        },
    )

    # Draft → suspend (await user review)
    builder.add_edge("drafting_agent", END)

    # Draft reviewer: confirm → legal check, revise → show updated draft
    builder.add_conditional_edges(
        "draft_reviewer",
        route_after_draft_review,
        {
            "legal_checker": "legal_checker",
            "end": END,
        },
    )

    # Legal check always ends the turn; user decides to re-check or finalize
    builder.add_edge("legal_checker", END)

    conn = sqlite3.connect(settings.CHECKPOINT_DB_PATH, check_same_thread=False)
    memory = SqliteSaver(conn)
    compiled = builder.compile(checkpointer=memory)
    return compiled, memory


def get_graph():
    """Return the singleton compiled graph, initializing it if needed."""
    global _graph_app, _memory
    if _graph_app is None:
        _graph_app, _memory = create_workflow()
    return _graph_app
