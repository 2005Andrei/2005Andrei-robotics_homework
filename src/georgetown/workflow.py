from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph, START, END
from .agent import agent, tools_executor, check_goal, OverallState
from langchain_core.messages import AIMessage, ToolMessage



workflow = StateGraph(OverallState)
workflow.add_node("agent", agent)
workflow.add_node("tools", tools_executor)
workflow.add_node("check_goal", check_goal)

def route_after_agent(state: OverallState):
    last_msg = state["messages"][-1]
    if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
        return "tools"
    if isinstance(last_msg, ToolMessage):
        return "check_goal"
    return "check_goal"

def route_after_check(state: OverallState):
    if state.get("goal_achieved", False):
        return END
    return "agent"

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", route_after_agent)
workflow.add_edge("tools", "agent")
workflow.add_conditional_edges("check_goal", route_after_check)
