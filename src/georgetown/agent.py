from tools.tools import tools
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage, SystemMessage, BaseMessage
from typing import TypedDict, List, Annotated, Union
from pydantic import BaseModel, Field
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
    success_criteria: str

class RobotPlan(BaseModel):
    task: str = Field(description="The high-level goal (e.g.: 'Find obstacle')")
    move: str = Field(description="The immediate logical step (e.g.: 'Move forward 100 speed for 2s')")
    reasoning: str = Field(description="Why you are doing this")
    success_criteria: str = Field(description="Explicitly state what counts as success. E.g.: 'Tool must be called with time=10. Speed parameter is optional/flexible.'")

llm = ChatGroq(
    model="llama-3.1-8b-instant",
    temperature=0,
    groq_api_key = ""
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
        "2. If an obstacle is detected (sensor says 'Too close' or move says 'Refused'), you can enter AVOIDANCE MODE if it is in accordance to what the user wants:"
        "   - ROTATE (90 deg)"
        "   - MOVE FORWARD (short distance to clear the object)"
        "   - ROTATE BACK (to original heading)"
        "   - CONTINUE UNTIL YOU HAVE MOVED PAST IT."
        "3. IT IS HIGHLY RECOMMENDED TO MOVE AT SLOW SPEEDS, like 80, 100 or 125 if the user does not mention anything about speed. Only for rotations you should do high speeds (150-200)."
    )

    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=system_content)] + messages

    if messages and isinstance(messages[-1], AIMessage) and state["current_task"] is None:
        messages.append(HumanMessage(content=state["user_input"]))

    if messages and isinstance(messages[-1], SystemMessage) and "advice" in messages[-1].content.lower():
        evaluator_advice = f"SUPERVISOR ADVICE: {messages[-1].content}. FOLLOW THIS IMMEDIATELY."
    else:
        evaluator_advice = ""

    planner_content = (
        "Analyze the situation. You must not start every task from the beginning. Look at the progress you've made in the provided data"
        "Decide the next immediate move based on the user's goal and safety rules"
        "Output your current plan"
    )

    track_message = (
        f"Don't forget that the goal is {state['user_input']}." 
        f"Currently you are working on {state['current_task'] if state['current_task'] else 'you must define what you will work on first'}." 
        f"Your moves until here have been: {state['moves'] if state['moves'] else "None yet"}."
        f"The outputs of your tools have been: {state['tool_outputs'] if state['tool_outputs'] else "None yet"}. Keep that in mind"
        f"{evaluator_advice}"
    )
    planner_message = SystemMessage(content=f"{system_content}\n{planner_content}\n{track_message}")

    planner = llm.bind_tools(tools).with_structured_output(RobotPlan) # it's good to let the planner know about the tools, it won't call them because with_structured_output acts as a mandotory tool
    executioner = llm.bind_tools(tools)


    # first invoke
    try:
        plan: RobotPlan = planner.invoke([planner_message])
        print(f"move: {plan.move}")
        print(f"task: {plan.task}")
    except Exception as e:
        print(f"Something went wrong {e}")
        ai_msg = AIMessage(f"My brain disconnected {str(e)}")
    

    executioner_instructions = f"""
    Execute the following plan using ONLY ONE tool.
    Task: {plan.task}
    Move logic: {plan.move}
    """

    # second invoke
    try:
        ai_msg = executioner.invoke([SystemMessage(content=system_content)] + [HumanMessage(content=executioner_instructions)])
    except Exception as e:
        ai_msg = AIMessage(content="Something broke")
        print("In the exceptio of the second invoke")

    # instead of doing what I do below I should probably define a helper function to only add unique tasks, something like tasks: Annotated[List[str], add_unique_task]

    existing_tasks = state.get("tasks", [])
    last_task = existing_tasks[-1] if existing_tasks else None
    current_task_clean = plan.task.strip().lower()
    last_task_clean = last_task.strip().lower() if last_task else ""
    if current_task_clean != last_task_clean:
        tasks_update = [plan.task] 
    else:
        tasks_update = []
    print(f"success_criteria: {plan.success_criteria}")
    return {
        "messages": messages + [ai_msg],
        "current_task": plan.task,
        "tasks": tasks_update,
        "current_move": plan.move,
        "moves": [plan.move],
        "success_criteria": plan.success_criteria
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

        tool_messages.append(ToolMessage(
            content = str(tool_output),
            tool_call_id=tool_call["id"]
        ))
        #tool_messages.append(str(tool_output))


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
    success_criteria = state["success_criteria"]
    
    prompt = (
        "You are a supervisor, a robot is controlled by a Large Language Model, and has commanded it."
        f"The user asked for '{prompt}'. Review the following conversation and outputs to establish if the user's request has been satisfied"
        f"The robot as done the following moves '{moves}'"
        f"The robot has had the following tool outputs '{tool_outputs}'"
        f"Up until now, the tasks have been established as being the following: '{tasks}'"
        f"If the user's request has been fully satisfied, you must respond with YES."
        f"If the user's request has not been fully satisfied respond with a very very short advice of what still must be done."
        f"This has been defined as success criteria {success_criteria}."
        "For unspecified user conditions the llm has complete and utter liberty to choose whatever it sees fit, especially during intermediate tasks, where the goal might be vague."
        "You are a binary judge."
        "Your ONLY job is to compare the Robot's action against the PLANNER'S success_criteria."
        "INSTRUCTIONS:\n"
        "1. Compare the 'Moves made so far' against the 'User Goal'.\n"
        "2. IGNORE the planner's specific task names. Look at the PHYSICAL ACTIONS (moves).\n"
        "3. If the robot has completed the necessary actions for the goal, respond 'YES'.\n"
        "4. If the robot is partly done (e.g., moved but hasn't rotated yet), provide a short advice on the NEXT STEP only.\n"
        "5. Be lenient. If the motors moved and no errors occurred, assume success."
        "6. Make sure to validate data. You can do this by suggesting as advice, to get the sensory data/distance to ensure success."
    )

    response = llm.invoke(prompt)
    print(response.content)
    if "yes" in response.content.lower():
        return { "completed": True, "current_task": None }

    return { "messages": messages + [SystemMessage(content = response.content)]}


def generate_witty_response(state: OverallState) -> OverallState:
    print("in witty respone")
    messages = state["messages"]
    user_goal = state["user_input"]
    tool_outputs = state["tool_outputs"]
    tasks = state["tasks"]
    
    system_prompt = (
        "You are a witty agent in control of a robot"
        f"The user has asked for this {str(user_goal)}"
        f"You have delivered, you called the apropriate tools with the following tool outputs {str(tool_outputs)}"
        f"You broke down the request into tasks {str(tasks)}"
        "You must generate a short witty response to communicate your success to the user."
    )

    response = llm.invoke(system_prompt)

    return {"messages": messages + [AIMessage(content=response.content)]}




