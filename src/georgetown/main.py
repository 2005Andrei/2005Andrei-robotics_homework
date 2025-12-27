from .workflow import workflow, OverallState

def main():
    george = workflow.compile()

    conversation = []

    while True:
        mode = "user" # going to be some user input shi
        if mode == "exit":
            break
        elif mode == "user":
            user_input = str(input("Enter: "))
            initial_state: OverallState = {
                "mode": mode,
                "goal": "",
                "user_input": user_input,
                "messages": conversation[-4],
                "goal_achieved": False
            }
        elif mode == "autonomous":
            print("Not fucking yet go to hell bitch")
        else:
            print("Something broke. Fuck you")

        result = george.invoke(initial_state)
        history.append(result["messages"])

        if isinstance(histry[-1], AIMessage):
            print(f"history[-1]\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt as e:
        print("\nexiting...")
