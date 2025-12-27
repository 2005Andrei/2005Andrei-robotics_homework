from tools.tools import tools
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage, SystemMessage, BaseMessage
from typing import TypedDict, List, Annotated
from langchain_groq import ChatGroq
import os


class OverallState(TypedDict):
    mode: str
    goal: str
    user_input: str
    messages: List[BaseMessage]
    goal_achieved: bool


llm = ChatGroq(
    model="llama-3.1-8b-instant",
    temperature=0,
    groq_api_key = "yup"
).bind_tools(tools)

def agent(state: OverallState) -> OverallState:
    # the state comes in with user input
    messages = state["messages"]

 
    if state["mode"] == "user":
        if not messages or not isinstance(messages[-1], HumanMessage):
            messages.append(HumanMessage(content=state["user_input"]))
        system_content = "You are a robot assistant. To move forward, set all 4 motors (top_left, top_right, bottom_left, bottom_right) to 'forward', speed 200, whatever time you consider."

    else:
        if not messages:
            system_content = f"You are an autonomous robot agent. Your goal is {state['goal']}. You must use provided tools to accomplish it. When the goal is fully achieved, include 'DONE' in your response"
        else:
            system_content = messages[0].content if isinstance(messages[0], SystemMessage) else ""


    if not any(isinstance(m, SystemMessage) for m in messages):
        messages = [SystemMessage(content=system_content)] + messages

    try:
        ai_msg = llm.invoke(messages)
    except Exception as e:
        error_text = str(e)
        if "tool call validation failed" in error_text or "400" in error_text:
            ai_msg = AIMessage(content="You bastard, I cannot execute that command. The parameters provided (like speed) were outside the allowed limits (max 255). Please try again you dirty boy")
        else:
            ai_msg = AIMessage(content=f"An unexpected error occurred: {error_text}")

    print(f"DEBUG - AI Response: {ai_msg.content}")
    print(f"DEBUG - Tool Calls: {ai_msg.tool_calls}")

    return {"messages": messages + [ai_msg]}

def tools_executor(state: OverallState) -> OverallState:
    messages = state["messages"]
    ai_msg = messages[-1]

    if not isinstance(ai_msg, AIMessage):
        return state

    tool_messages = []

    for tool_call in ai_msg.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        selected_tool = next((t for t in tools if t.name == tool_name), None)

        if selected_tool:
            try:
                tool_output = selected_tool.invoke(tool_args)
            except Exception as e:
                tool_output = f"Tool execution error: {str(e)}"
                print(tool_output)
        else:
            tool_output = f"Tool '{tool_name}' not found"

        tool_messages.append(ToolMessage(
            content = str(tool_output),
            tool_call_id=tool_call["id"]
        ))


    return {"messages": messages + tool_messages}


def check_goal(state: OverallState) -> OverallState:
    if state["mode"] == "user":
        return {"goal_achieved": True}

    messages = state["messages"]
    check_messages = [SystemMessage(content=f"Goal: {state['goal']}. Based on the conversation history, is the goal achieved? Respond only with 'YES' or 'NO'.")] + messages
    response = llm.invoke(check_messages).content.strip().upper()
    goal_achieved = "YES" in response
    return {"goal_achieved": goal_achieved}

