from tools.tools import tools
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage, SystemMessage, BaseMessage
from typing import TypedDict, List, Annotated
from langchain_groq import ChatGroq
import os


class OverallState(TypedDict):
    user_input: str
    messages: List[BaseMessage]
    goal_achieved: bool


llm = ChatGroq(
    model="llama-3.1-8b-instant",
    temperature=0,
    groq_api_key = "yum yum" # it's the free api key so it is pretty useless but anyways
).bind_tools(tools)

def agent(state: OverallState) -> OverallState:
    print("in agent")
    messages = state["messages"]
    if messages and isinstance(messages[-1], ToolMessage):
        return state
    system_content = (
        "You are a robot assistant"
        "To move forward, set all 4 motors (top_left, top_right, bottom_left, bottom_right) to 'forward'. "
        "Speed is 0-255 (default 200). Time is in seconds. "
        "To rotate 90 degrees, use speed 100 for 1.7 seconds and move motors on opposing sides in oppoisite directions, tank style"
        "If the goal is achieved, respond with 'DONE'."
    )

    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=system_content)] + messages

    if messages and isinstance(messages[-1], (AIMessage, SystemMessage)):
        messages.append(HumanMessage(content=state["user_input"]))

    try:
        ai_msg = llm.invoke(messages)
    except Exception as e:
        ai_msg = AIMessage(f"My brain disconnected {str(e)}")

    return {"messages": messages + [ai_msg]}

def tools_executor(state: OverallState) -> OverallState:
    print("in tools")
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
    print("in check")
    messages = state["messages"]
    user_goal = state["user_input"]

    last_msg = messages[-1]
    if isinstance(last_msg, AIMessage) and not last_msg.tool_calls:
        if "DONE" in last_msg.content:
            return {"goal_achieved": True}

    system_prompt = (
        f"You are a supervisor. The user asked for '{user_goal}'"
        "Review the conversation and establish whether the user's request has been satisfied."
        "If the user's request has been fully satisfied, respond YES"
        "If more actions are needed, respond NO."
    )

    if any(isinstance(message, ToolMessage) for message in messages):
        print("yes")
    else:
        print("amnesia")

    response = llm.invoke([SystemMessage(content=system_prompt)] + messages[-4:])

    return {"goal_achieved": "YES" in response.content.strip().upper()}
