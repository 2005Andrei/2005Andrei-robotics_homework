from .workflow import workflow, OverallState
from langchain_core.messages import AIMessage

def main():
    george = workflow.compile()

    history = []
    try:
        while True:
            user_input = str(input("Enter: "))
            initial_state: OverallState = {
                "user_input": user_input,
                "messages": history,
                "completed": False,
                "current_move": "",
                "current_task": "",
                "tasks": [],
                "moves": [],
                "tool_outputs": []
            }

            result = george.invoke(initial_state)
            history = result["messages"]

            if isinstance(result[-1], AIMessage):
                print(f"Here: {result[-1].content}\n")
    except KeyboardInterrupt:
        print("Exit...")


if __name__ == "__main__":
    main()
