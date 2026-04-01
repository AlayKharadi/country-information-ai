"""
LangGraph agent graph definition.

The graph is compiled once at module import time and reused for every request.
Compilation resolves the graph structure, validates edges, and wires up the
async runtime. It's expensive and should never happen per-request.

Graph shape:

  [START]
     ↓
  intent_extraction
     ↓
  [conditional router]
     ├── is_valid: false ──→ decline ──→ [END]
     └── is_valid: true  ──→ api_call ──→ answer_synthesis ──→ [END]
"""

from langgraph.graph import END, START, StateGraph

from .models import AgentState
from .nodes import (
    answer_synthesis_node,
    api_call_node,
    decline_node,
    intent_extraction_node,
)


def _route_after_intent(state: AgentState) -> str:
    """
    Conditional edge function: decide which branch to take after intent extraction.

    Returns the name of the next node as a string. LangGraph uses the returned
    value as a key in the edge map to resolve the actual destination node.
    """
    if state.get("intent") and state["intent"].is_valid:
        return "api_call"
    return "decline"


def _build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("intent_extraction", intent_extraction_node)
    graph.add_node("api_call", api_call_node)
    graph.add_node("answer_synthesis", answer_synthesis_node)
    graph.add_node("decline", decline_node)

    graph.add_edge(START, "intent_extraction")

    graph.add_conditional_edges(
        "intent_extraction",
        _route_after_intent,
        {"api_call": "api_call", "decline": "decline"},
    )

    graph.add_edge("api_call", "answer_synthesis")
    graph.add_edge("answer_synthesis", END)
    graph.add_edge("decline", END)

    return graph


# Module-level compiled agent: import and call `agent.ainvoke(...)` directly.
agent = _build_graph().compile()
