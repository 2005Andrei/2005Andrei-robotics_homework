from langchain.tools import tool
from langchain_core.tools import StructuredTool
import requests
from pydantic import BaseModel, Field
from typing import Literal
import time

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
            return "Failed: robot is busy"
        
        print("Command accepted. Waiting for robot to finish")

        while True:
            print("in here")
            time.sleep(2)
            status = requests.get(f"{url}/", timeout=5)
            print(f"{url}/")
            st_data = status.json()
            print(st_data)
            print(f"\n{st_data.get('status')}")

            if st_data.get("status") == "idle" and st_data.get("result") != "":
                print(st_data.get('result'))
                return f"Robot worked. The result of your movement was: {st_data.get("result")}"
            else:
                print("Robot is still moving")

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

@tool
def get_sensor():
    """A function to get the distance of an object in front of the robot"""
    print("Sensor function")
    try:
        response = requests.get(f"{url}/sensor")
        res = response.json()

        if res["distance"] > 60:
            return "Clear. No object in front of the robot"
        elif res["distance"] > 15:
            return f"Clear. Object at distance of {res['distance']} cm in front of the robot. Can still move forward"
        else:
            return f"OBSTACLE DETECTED. Object is too close at distance of {res['distance']} cm away."
    except Exception as e:
        return f"Unexpected error: {e}"



@tool
def avoid_obstacle():
    """
    Navigates around obstacles using backend feedback.
    """
    history = []
    max_attempts = 3
    attempt = 0
    cleared = False
    
    SAFE_DISTANCE = 20.0 

    initial_sensor = get_sensor.invoke({})
    initial_dist = get_dist_from_string(initial_sensor)
    
    if "No object" in initial_sensor or initial_dist > SAFE_DISTANCE:
        return f"ABORT: Path is already clear. Sensor: {initial_sensor}"
    
    history.append("Detected obstacle. Starting maneuver.")

    execute_turn_left()
    left_dist = get_dist_from_string(get_sensor.invoke({}))

    execute_turn_right()
    execute_turn_right()
    right_dist = get_dist_from_string(get_sensor.invoke({}))

    execute_turn_left()

    if left_dist < 20 and right_dist < 20:
        history.append(f"Dead end detected (L:{left_dist}, R:{right_dist}). Backing up.")
        
        cmd_back = MotorCommand(direction="backward", speed=200, time=1.0)
        _move_motors(cmd_back, cmd_back, cmd_back, cmd_back, eval_mode="move_backward")
        
        return f"FAILURE: Dead end (L:{left_dist}, R:{right_dist}). Reversed 1s. History: {history}"

    side = "right" if right_dist >= left_dist else "left"
    history.append(f"Chose {side.upper()} (L:{left_dist} R:{right_dist}).")

    while attempt < max_attempts and not cleared:
        attempt += 1
        
        if side == "right": execute_turn_right()
        else: execute_turn_left()

        side_sensor = get_sensor.invoke({})
        if "OBSTACLE" in side_sensor or get_dist_from_string(side_sensor) < 20:
            if side == "right": execute_turn_left()
            else: execute_turn_right()
            return f"FAILURE: Sensor variance detected. Path looked clear but is blocked on close inspection. Aborting."

        move_res = execute_move_forward(duration=5)
        
        if "refused" in move_res.lower() or "obstacles" in move_res.lower():
            history.append(f"Strafe blocked on attempt {attempt}: {move_res}")
            if side == "right": execute_turn_left()
            else: execute_turn_right()
            return f"FAILURE: Blocked while strafing {side}. Backend msg: {move_res}. History: {history}" 
        
        history.append(f"Strafed {side} (5s).")

        if side == "right": execute_turn_left()
        else: execute_turn_right()

        check = get_sensor.invoke({})
        dist = get_dist_from_string(check)
        
        if dist > SAFE_DISTANCE:
            cleared = True
            history.append(f"Gap found (dist {dist}).")
        else:
            history.append(f"Still blocked (dist {dist}).")

    if cleared:
        pass_res = execute_move_forward(duration=3.0)
        
        if "refused" in pass_res.lower() or "obstacles" in pass_res.lower():
            history.append(f"Pass interrupted: {pass_res}")
            return f"FAILURE: Crashed while passing. Backend msg: {pass_res}. History: {history}"
            
        history.append("Moved forward 3.0s to pass.")
        return f"SUCCESS: Avoided obstacle. Moves executed: {history}"
    else:
        return f"FAILURE: Could not clear obstacle after {attempt} attempts. History: {history}"


import re

def get_dist_from_string(s, default=1000):
    numbers = re.findall(r'[-+]?\d+\.?\d*', s)
    if numbers:
        num = numbers[0]
        return float(num)
    else:
        return default


def execute_turn_left():
    print("Turning left")
    cmd_back = MotorCommand(direction="backward", speed=220, time=0.8)
    cmd_fwd = MotorCommand(direction="forward", speed=220, time=0.8)
    
    return _move_motors(
        top_left=cmd_back, top_right=cmd_fwd,
        bottom_left=cmd_back, bottom_right=cmd_fwd,
        eval="rotate"
    )

def execute_turn_right():
    print("Turning lright")
    cmd_back = MotorCommand(direction="backward", speed=220, time=0.8)
    cmd_fwd = MotorCommand(direction="forward", speed=220, time=0.8)
    
    return _move_motors(
        top_left=cmd_fwd, top_right=cmd_back,
        bottom_left=cmd_fwd, bottom_right=cmd_back,
        eval="rotate"
    )

def execute_move_forward(duration=1.0):
    print(f"DEBUG: Executing Forward for {duration}s")
    cmd = MotorCommand(direction="forward", speed=200, time=duration)
    
    return _move_motors(
        top_left=cmd, top_right=cmd,
        bottom_left=cmd, bottom_right=cmd,
        eval="forward"
    )

tools = [move_motors, get_sensor, avoid_obstacle]
