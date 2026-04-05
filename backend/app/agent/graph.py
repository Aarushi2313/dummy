"""
agent.graph
-----------
Core state-graph initialization for the AI Reporting Agent.
This module binds the sequential NLP pipeline nodes (validate, fetch, extract,
summarize, structure) into an executable LangGraph StateGraph instance.
"""
from langgraph.graph import StateGraph
from .nodes import *

graph = StateGraph(dict)

# Define State nodes representing distinct ML operations
graph.add_node("validate", validate_context)
graph.add_node("fetch", fetch_data)
graph.add_node("extract", extract)
graph.add_node("summarize", summarize)
graph.add_node("structure", structure)

# Define Graph Edges enforcing strict execution linearity
graph.set_entry_point("validate")
graph.add_edge("validate", "fetch")
graph.add_edge("fetch", "extract")
graph.add_edge("extract", "summarize")
graph.add_edge("summarize", "structure")
graph.set_finish_point("structure")

"""
Compiled representation of the AI Agent reporting logic.
Execution flow starts at 'validate' and gracefully exits post 'structure'.
"""
reporting_graph = graph.compile()
