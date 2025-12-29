from langgraph.graph import StateGraph, START, END
from .agent import agent, tools_executor, generate_witty_response, evaluator, OverallState



workflow = StateGraph(OverallState)
workflow.add_node("agent", agent)
workflow.add_node("tools", tools_executor)
workflow.add_node("evaluator", evaluator)
workflow.add_node("generate_witty_response", generate_witty_response)

def route_after_evaluator(state: OverallState):
    if state["completed"]:
        return "generate_witty_response"
    return "agent"


workflow.add_edge(START, "agent")
workflow.add_edge("agent", "tools")
workflow.add_edge("tools", "evaluator")
workflow.add_conditional_edges("evaluator", route_after_evaluator)
workflow.add_edge("generate_witty_response", END)
