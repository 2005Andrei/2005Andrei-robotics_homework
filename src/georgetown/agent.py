from tools.tools import tools
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage, SystemMessage, BaseMessage
from typing import TypedDict, List, Annotated, Union
from langchain_groq import ChatGroq
import operator
import re


class OverallState(TypedDict):
    user_input: str
    messages: Annotated[List[BaseMessage], operator.add]
    completed: bool
    current_move: Union[str, None]
    current_task: Union[str, None]
    tasks: Annotated[List[str], operator.add]
    moves: Annotated[List[str], operator.add]
    tool_outputs: List[str] | None


def parse_xml(content: str):
    task_match = re.search(r"<task>(.*?)</task>", content, re.DOTALL)
    move_match = re.search(r"<move>(.*?)</move>", content, re.DOTALL)
    
    return {
        "task": task_match.group(1).strip() if task_match else "Something went wrong. You should respond with yes to exit the loop and ensure the user sees the bad message quickly.",
        "move": move_match.group(1).strip() if move_match else "Something went wrong. You should respond with yes to exit the loop and ensure the user sees the bad message quickly."
    }



llm = ChatGroq(
    model="llama-3.1-8b-instant",
    temperature=0,
    groq_api_key = "yum yum"
)

def agent(state: OverallState) -> OverallState:
    print("In agent")

    messages = state["messages"]


    system_content = (
        "You are a robot assistant navigating a physical space. "
        "To move forward, set all 4 motors to 'forward'. "
        "Speed is 40-200 (default 100). Time is in seconds. "
        "To rotate 90 degrees, use speed 150 for 1.7 seconds, tank style. "
        
        "\nPLANNING RULES:"
        "1. SEQUENCES: You CANNOT generate multiple tool calls at once."
        "2. ONLY ONE TOOL CALL."
        
        "\nSAFETY & AVOIDANCE:"
        "The robot has an internal safety system. If it hits an obstacle while moving, it will stop automatically and the tool will return 'Failed' or 'Refused'."
        "1. Do NOT move in small increments."
        "2. If an obstacle is detected (sensor says 'Too close' or move says 'Refused'), you MUST enter AVOIDANCE MODE:"
        "   - ROTATE (90 deg)"
        "   - MOVE FORWARD (short distance to clear the object)"
        "   - ROTATE BACK (to original heading)"
        "   - CONTINUE"
        "3. IT IS HIGHLY RECOMMENDED TO MOVE AT SLOW SPEEDS, like 80, 100 or 125 if the user does not mention anything about speed."
    )

    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=system_content)] + messages

    if messages and isinstance(messages[-1], AIMessage) and state["current_task"] is None:
        messages.append(HumanMessage(content=state["user_input"]))

    try:
        if state["current_task"] is not None:
            track_message = f"Currently you are working on {state['current_task']}. Don't forget that the goal is {state['user_input']}. Your moves until here have been: {state['moves']}. The outputs of your tools have been: {state['tool_outputs']}. Keep that in mind"
        else:
            track_message = ""
        current_message = """
            You have access to tools. Whenever you intend to call a tool (or answer the user), you MUST output your internal reasoning using the following XML format.

            <reasoning>
                <task>Write the high-level goal you are trying to accomplish here</task>
                <move>Write the specific immediate step or logic you are executing now</move>
            </reasoning>

            Do not add any other text outside these tags before calling your tools
        """

        systems= SystemMessage(content=current_message) if not track_message else SystemMessage(content=f"{current_message} {track_message}")

        new_llm = llm.bind_tools(tools)
        ai_msg = new_llm.invoke(messages + [systems])
    except Exception as e:
        ai_msg = AIMessage(f"My brain disconnected {str(e)}")

    parsed = parse_xml(ai_msg.content)

    print(f"this shit {ai_msg.content}")
    import sys
    sys.exit(1)

    current_task = parsed["task"]
    current_move = parsed["move"]


    # I know that duplicate tasks may get added to the list, I'll fix that if thsi doesn't work

    return {
        "messages": messages + [ai_msg],
        "current_task": current_task,
        "tasks": state["tasks"] + [current_task],
        "current_move": current_move,
        "moves": state["moves"] + [current_move]
     }


def tools_executor(state: OverallState) -> OverallState:
    print("in tools")
    print(f"working on {state['current_task']}\n")
    print(f"technically, at the moment, the list of tasks is {state['tasks']}")
    print(f"\nAt the moment, my current moves are: {state['moves']}")


    messages = state["messages"]
    ai_msg = messages[-1]

    if not isinstance(ai_msg, AIMessage):
        return state

    tool_messages = []

    keep_executing = True

    for tool_call in ai_msg.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        if not keep_executing:
            tool_messages.append(ToolMessage(
                content="Action was cancelled. One of the previous steps failed or detected an obstacle, so this step was skipped for safety.",
                tool_call_id=tool_call["id"]
            ))
            continue

        selected_tool = next((t for t in tools if t.name == tool_name), None)

        if selected_tool:
            try:
                tool_output = selected_tool.invoke(tool_args)
            except Exception as e:
                tool_output = f"Tool execution error: {str(e)}"
                print(tool_output)
        else:
            tool_output = f"Tool '{tool_name}' not found"

        keywords = [
            "failed",
            "error",
            "refused",
            "obstacle"
        ]

        if any(keyword in str(tool_output).lower() for keyword in keywords):
            print(f"Stopping at {tool_name}")
            keep_executing = False

        #tool_messages.append(ToolMessage(
        #    content = str(tool_output),
        #    tool_call_id=tool_call["id"]
        #))
        tool_messages.append(str(tool_output))


    return {
        "messages": messages + tool_messages,
        "tool_outputs": state["tool_outputs"] + [tool_messages] 
    }

def evaluator(state: OverallState) -> OverallState:
    print("Evaluating...")
    tool_outputs = state["tool_outputs"]
    moves = state["moves"]
    prompt = state["user_input"]
    tasks = state["tasks"]
    messages = state["messages"]
    
    prompt = (
        "You are a supervisor, a robot is controlled by a Large Language Model, and has commanded it."
        f"The user asked for '{prompt}'. Review the following conversation and outputs to establish if the user's request has been satisfied"
        f"The robot as done the following moves '{moves}'"
        f"The robot has had the following tool outputs '{tool_outputs}'"
        f"Up until now, the tasks have been established as being the following: '{tasks}'"
        f"If the user's request has been fully satisfied, you must respond with YES."
        f"If the user's request has not been fully satisfied respond with a very very short advice of what still must be done."
    )

    response = llm.invoke(prompt)
    print(response.content)
    if "yes" in response.content.lower():
        return { "completed": True, "current_task": None }

    return { "messages": messages + [SystemMessage(content = response.content)]}


def generate_witty_response(state: OverallState) -> OverallState:
    print("maybe yes")
    messages = state["messages"]
    user_goal = state["user_input"]
    tool_outputs = state["tool_outputs"]
    tasks = state["tasks"]
    
    system_prompt = (
        "You are a witty agent in control of a robot"
        f"The user has asked for this {user_goal}"
        f"You have delivered, you called the apropriate tools with the following tool outputs {tool_outputs}"
        f"You broke down the request into tasks {tasks}"
        "You must generate a witty response to communicate your success to the user."
    )

    response = llm.invoke(system_prompt)

    return {"messages": messages + [AIMessage(content=response)]}




