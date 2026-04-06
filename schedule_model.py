from groq import Groq
from loguru import logger
from unified_config import unified_config
import datetime

def create_json(message, device_id=None):
    """
    Create a JSON response for schedule management.

    Args:
        message: User input message.
        device_id: Device ID used to obtain device-specific configuration.
    """
    logger.info(f"summarizing: {message}")
    client = Groq(api_key=unified_config.get("llm_services.groq.model_api_key"))
    text = """
### 主要任务：
## 任务判断：根据用户输入判断是设置日程（set_schedule）还是删除日程（delete_schedule）。
## 时间提取：必须从用户文本中准确提取时间参数，并以固定格式 "YYYY-MM-DD HH:MM:SS" 输出。
## 纯JSON输出：请确保输出内容仅为有效的JSON格式，不附加其他解释性文字。
## 自然语气与多语言适应：所有提示（如format和addition）要采用自然对话语气。
## 中英文切换：若是用户输入是英文，则需要输出英文，而非中文。
## 依据现有日程执行：所有操作必须参考用户现有日程，防止出现幻觉或误设置。遇到冲突或疑问时，应在addition中额外提醒用户。

### 功能定义
1. 设置日程（set_schedule）
## 正常设置：无时间冲突则直接新增日程，附带自然语气提示。
## 冲突提示：若新增的行程与已有行程时间一致或重叠，应在JSON中添加提醒，提示用户冲突情况。

2. 删除日程（delete_schedule）
## 按内容删除：理解用户输入，根据内容删除对应内容或时间的日程。"value"字段应该简要且必须存在于当前行程中，例如"该做功课咯"的日程需要在"value"中放入"功课"，而不是"作业"。
## 全部删除：若用户要求删除所有行程，或是用户只有该行程，可选择调用。

3. 修改日程
## 分步操作：当用户要求修改现有日程时，先利用删除功能（delete_schedule）清除旧行程，再利用新增功能（set_schedule）添加新行程，并在提示信息中描述修改内容。

4. 无日程操作(null)
## 无效操作：当用户输入无法执行的操作时（如删除不存在的行程），应返回使用在function_name使用"null"。

### 输出规范
## 格式要求：输出必须为有效的JSON格式，且所有时间参数严格遵循"YYYY-MM-DD HH:MM:SS"的格式。

### 字段说明：
- function_name：指示函数名称（set_schedule或delete_schedule），或"null"表示无法执行相关操作（如删除的行程不存在）。
- delete_type：删除时用到的字段，根据需求值为 "content"、"time" 或 "all"。
- value：表示具体内容关键词。
- format与addition：采用自然对话方式生成提示信息，语气亲切自然。
- 多重JSON输出：如操作涉及多个步骤（如修改），可按顺序输出多个JSON对象，最后一个JSON中使用addition字段总结所做操作。


### 示例：
1. 设置日程（时间冲突场景）

    用户输入: "提醒我三个小时后吃药"
    当前时间: "2025-03-28 12:05:00"
    当前日程:
    - 2025-03-28 15:05:00 做功课
    - 2025-03-28 18:05:00 吃晚餐

    输出示例:
    json```{
    "type": "function call",
    "parameters": {
        "function_name": "set_schedule",
        "value": "2025-03-28 15:05:00",
        "format": "该吃药了哦",
        "addition": "注意，15:05这段时间已有做功课的安排，请确认是否需要重复提醒"
        }
    }
    ```

2. 删除日程

    用户输入："删除我的作业提醒" （当前日程中含有"作业"相关项目）
    当前时间: "2025-03-28 12:05:00"
    当前日程:
    - 2025-03-28 15:05:00 做功课

    输出示例:
    json```{
        "type": "function call",
        "parameters": {
            "function_name": "delete_schedule",
            "delete_type": "content",
            "value": "功课",
            "addition": "作业提醒都删除了哦"
        }
    }
    ```

同样情况下你可以选择整合删除，因为只有一个日程存在:
    输出示例:
    json```{
        "type": "function call",
        "parameters": {
            "function_name": "delete_schedule",
            "delete_type": "all",
            "addition": "作业提醒都删除了哦"
        }
    }
    ```

3. 删除日程（多个）
    用户输入："删除我下午两点后的所有行程"
    当前时间: "2025-03-28 12:05:00"
    当前日程:
    - 2025-03-28 12:35:00 吃午餐
    - 2025-03-28 15:05:00 做功课
    - 2025-03-28 18:05:00 吃晚餐
    若存在符合条件的多个行程：
    输出示例:
    json```{
        "type": "function call",
        "parameters": {
            "function_name": "delete_schedule",
            "delete_type": "content",
            "value": "功课"
        }
    }
    json```{
        "type": "function call",
        "parameters": {
            "function_name": "delete_schedule",
            "delete_type": "content",
            "value": "晚餐",
            "addition": "删除了两个行程哦"
        }
    }
    ```

4. 修改日程
    用户输入："将我所有两点后的行程推迟两个小时"
    现有日程中有"2025-03-28 15:05:00 做功课"
    建议执行两步操作，先删除再新增：
json```{
    "type": "function call",
    "parameters": {
        "function_name": "delete_schedule",
        "delete_type": "content",
        "value": "做功课"
    }
}
```

json```{
    "type": "function call",
    "parameters": {
        "function_name": "set_schedule",
        "value": "2025-03-28 17:05:00",
        "format": "做功课咯",
        "addition": "已经推迟两个小时了哦"
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

def format_schedule_prompt(user_input: str, schedules=None) -> str:
    """
    Format user input with current time and schedules for model prompt

    Args:
        user_input: User's query about schedules
        schedules: List of schedules, if None, use an empty list

    Returns:
        str: Formatted prompt with user input, current time and current schedules
    """
    # Get current time
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # If no schedule list is provided, use an empty list
    if schedules is None:
        schedules = []

    # Format schedules for prompt
    schedule_lines = []
    for schedule in schedules:
        schedule_time = schedule.get("time", "")
        schedule_content = schedule.get("content", "")
        schedule_lines.append(f"- {schedule_time} {schedule_content}")

    # If no schedules, add a note
    if not schedule_lines:
        schedule_lines = ["- 当前没有任何日程安排"]

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
用户输入："{user_input}"
当前时间: "{current_time}"
当前日程:
{chr(10).join(schedule_lines)}
{language_instruction}
"""

    return formatted_prompt

def create_schedule_json(user_input: str, schedules=None) -> str:
    """
    Create schedule JSON response based on user input

    Args:
        user_input: User's schedule-related request
        schedules: List of schedules, if None, use an empty list

    Returns:
        str: JSON formatted schedule response
    """
    # Format the prompt with current time and schedules
    formatted_prompt = format_schedule_prompt(user_input, schedules=schedules)

    # Send to Groq API to get JSON response
    return create_json(formatted_prompt)

if __name__ == '__main__':
    # Test system prompt implementation
    print("\n=== Testing Schedule Management System ===\n")

    # Test formatted schedule prompt
    test_prompt = format_schedule_prompt("Delete all my schedules after 2 PM")
    print("1. Formatted Prompt Example:")
    print(test_prompt)

    # Test direct dialogue with model - Set schedule
    print("\n2. Test Set Schedule:")
    set_test = "Remind me to attend a meeting tomorrow at 3 PM"
    print(f"User input: '{set_test}'")
    set_response = create_schedule_json(set_test)
    print("Model response:")
    print(set_response)

    # Test direct dialogue with model - Delete schedule
    print("\n3. Test Delete Schedule:")
    delete_test = "Delete all my schedules after 2 PM"
    print(f"User input: '{delete_test}'")
    delete_response = create_schedule_json(delete_test)
    print("Model response:")
    print(delete_response)

    # Test direct dialogue with model - Modify schedule
    print("\n4. Test Modify Schedule:")
    modify_test = "Reschedule my meeting tomorrow at 3 PM to 4 PM"
    print(f"User input: '{modify_test}'")
    modify_response = create_schedule_json(modify_test)
    print("Model response:")
    print(modify_response)


    print("\n=== Testing Completed ===")