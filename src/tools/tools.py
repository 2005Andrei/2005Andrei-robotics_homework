from langchain.tools import tool
from langchain_core.tools import StructuredTool
import requests
from pydantic import BaseModel, Field
from typing import Literal


url = "http://192.168.1.106:8000"
headers = {'Content-Type': 'application/json'}

class MotorCommand(BaseModel):
    """Command for a single motor"""
    direction: str = Field(..., description="Direction of movement: 'forward', or 'backward'")
    speed: int = Field(..., description="Speed of motor: 20-255", ge=50, le=255)
    time: float = Field(..., description="Duration in seconds")

class MotorPayload(BaseModel):
    top_left: MotorCommand
    top_right: MotorCommand
    bottom_right: MotorCommand
    bottom_left: MotorCommand
    eval: Literal["forward", "backward", "rotate"] = Field(..., description="The type of movement being executed.")

def _move_motors(top_left: MotorCommand, top_right: MotorCommand, bottom_right: MotorCommand, bottom_left: MotorCommand, eval: str) -> str:
    """Internal function to send motor commands to the robot."""
    print("Got called\n")
    payload = MotorPayload(
        top_left=top_left,
        top_right=top_right,
        bottom_right=bottom_right,
        bottom_left=bottom_left,
        eval=eval
    )
    payload_dict = payload.model_dump()
    try:
        response = requests.post(f"{url}/motors", json=payload_dict, headers=headers, timeout=5)
        response.raise_for_status()

        data = response.json()
        if data.get("status") == "busy":
            return "Failed: robot is busy rn (fucking your girlfriend)"
        
        print("Command accepted. Waiting for robot to finish")

        while True:
            print("in here")
            time.sleep(2)
            try:
                print("over here")
                status = requests.get(f"{url}/", timeout=5)
                st_data = status.json()

                if st_data.get("status") == "idle" and st_data.get("result") != "":
                    print("Job theoretically finished")
                    break
                else:
                    print("Robot is still moving")
            except Exception as e:
                print(f"Couldn't check status: {e}")

        print("suka blyat")

        return "The robot completed the movement"
    except requests.exceptions.ReadTimeout:
        return "Timeout exception happened"
    except Exception as e:
        return f"Unexpected {str(e)}"

move_motors = StructuredTool.from_function(
    func=_move_motors,
    name="move_motors",
    description="Moves the robot's motors.",
    args_schema=MotorPayload,
    handle_tool_error=True
)


tools = [move_motors]
