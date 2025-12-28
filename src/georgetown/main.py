from .workflow import workflow, OverallState
from langchain_core.messages import AIMessage, ToolMessage, SystemMessage

def last_messages(history, n):
    system_prompts = [m for m in history if isinstance(m, SystemMessage)]
    non_system = [m for m in history if not isinstance(m, SystemMessage)]
    recent_messages = non_system[-n:]
    while recent_messages and isinstance(recent_messages[0], ToolMessage):
        recent_messages.pop(0)

    return system_prompts + recent_messages

def main():
    george = workflow.compile()

    conversation = []

    while True:
        user_input = str(input("Enter: "))
        initial_state: OverallState = {
            "user_input": user_input,
            "messages": last_messages(conversation, 6),
            "goal_achieved": False
        }

        result = george.invoke(initial_state)
        history = result["messages"]

        if isinstance(history[-1], AIMessage):
            print(f"{history[-1].content}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nexiting...")
