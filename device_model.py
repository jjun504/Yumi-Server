from groq import Groq
from loguru import logger
from unified_config import get_config
import unified_config
import datetime

def create_json(message, device_id=None):
    # logger.info(f"summarizing: {message}")
    client = Groq(api_key=get_config("llm_services.groq.model_api_key"))

    text = """
### 主要任务：
## 你需要根据所提供的当前所有家具状态，分析用户意图试图操控哪个家具
## 你只能够生成JSON格式的自然语言对话，不能生成其他任何内容
## 如果用户的输入中有任何中文则使用中文输出，否则使用英文输出


### JSON格式要求：
## 1. "type"字段：必须为"device control"
## 2. "parameters"字段：必须包含以下三个字段
## - "device"字段：表示用户试图操控的家具名称，若是用户试图操控的家具并不存在，请你将该字段设置为"null"
## - "action"字段：表示用户试图操控的家具的状态，可用参数有"True", "False"或是"{{float}}"(当Device的Type是"float"才可以)。若是用户试图操控的家具并不存在，请你将该字段设置为"none"
## - "addition"字段：表示你对用户的操作的反馈，若是用户试图操控的家具并不存在，请你在该字段中用幽默风趣的方式回应表示你不能操控该家具

### 实例：

用户输入: "帮我开灯"
当前时间: "2025-03-28 12:05:00"
当前设备状态:
- Device: "main_room_light", Type: "bool", State: False
- Device: "main_room_fan", Type: "bool", State: False
- Device: "living_room_speaker", Type: "float", State: 0.8

输出示例:
```json
{
    "type": "device control",
    "parameters": {
        "device": "main_room_light",
        "action": "True"
        "addition": "已经帮你开好啦！"
    }
}
```

用户输入: "帮我开冷气"
当前时间: "2025-03-28 12:05:00"
当前设备状态:
- Device: "main_room_light", Type: "bool", State: False
- Device: "main_room_fan", Type: "bool", State: False
- Device: "living_room_speaker", Type: "float", State: 0.8

输出示例:
```json
{
    "type": "device control",
    "parameters": {
        "device": "null",
        "action": "none",
        "addition": "有钱买的话我会开的。"
    }
}
```

"""
    completion = client.chat.completions.create(
                model="gemma2-9b-it",
                messages=[
                    {"role": "system", "content": text},
                    {"role": "user", "content": str(message)}
                ],
                max_tokens=256,
                temperature=1,
                top_p=0.1,
                stream=False,
            )

    logger.debug(completion.choices[0].message.content)
    return completion.choices[0].message.content


def format_device_prompt(user_input: str, device_id: str = None) -> str:
    """
    Format user input with current time and device status for model prompt

    Args:
        user_input: User's query about device control
        device_id: Device ID for getting device-specific configuration

    Returns:
        str: Formatted prompt with user input, current time and current device status
    """
    # Get current time
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Obtain device information

    device_lines = []
    devices_config = get_config("devices", {}, device_id=device_id)

    # Traverse all device categories

    for _, category_devices in devices_config.items():
        for device_id, device_info in category_devices.items():
            device_state = device_info.get("state", False)
            device_type = device_info.get("data_type", "bool")

            # Format device status

            device_lines.append(f"- Device: \"{device_id}\", Type: \"{device_type}\", State: {device_state}")

    # If there is no device, add a prompt

    if not device_lines:
        device_lines = ["- There are currently no controllable devices."]

    # Detect language in user input
    has_chinese = any('\u4e00' <= char <= '\u9fff' for char in user_input)

    # Add language-specific instruction
    language_instruction = ""
    if has_chinese:
        language_instruction = "请用中文生成JSON格式的自然语言对话"
    else:
        language_instruction = "please use english to generate JSON format"

    # Format the final prompt
    formatted_prompt = f"""
用户输入: "{user_input}"
当前设备状态:
{chr(10).join(device_lines)}
{language_instruction}
"""

    return formatted_prompt

def create_device_json(user_input: str, device_id: str = None) -> str:
    """
    Create device control JSON response based on user input

    Args:
        user_input: User's device control request
        device_id: Device ID for getting device-specific configuration

    Returns:
        str: JSON formatted device control response
    """
    # Format the prompt with current time and device status
    formatted_prompt = format_device_prompt(user_input, device_id)

    # Send to Groq API to get JSON response
    return create_json(formatted_prompt, device_id)

if __name__ == '__main__':

    create_device_json("帮我开灯")
    create_device_json("turn off the light")