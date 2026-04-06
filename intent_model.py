from groq import Groq
from loguru import logger
from unified_config import unified_config
import datetime
def send(message, device_id=None):
    client = Groq(api_key=unified_config.get("llm_services.groq.intent_model_api_key"))
    text = """
【主要任务】
### 请基于用户输入和以下实时背景信息，推理用户的真实意图，并尽可能详细地描述其可能的需求及对应的操作建议。

【任务要求】
1. 本次输入中所有信息均为用户当前真实状态，数据包括：
  - 当前时间
  - 当前天气
  - 设备状态
  - 当前日程
2. 分析用户潜在需求，需涵盖以下层面：
   - 用户输入是否暗示对当前环境（例如天气、音乐）或设备（例如风扇、灯、衣架）的关注？
   - 用户是否可能基于当前信息希望进行模块调用?
   - 用户是否仅处于自然聊天阶段，无明确功能调用需求？
3. 如果用户意图涉及操作，请详细说明可能执行的具体动作（例如“查询天气”、“关闭风扇”、“调整扬声器音量”、“提醒日程事项”等），并解释推理依据。
4. 请在输出中尽可能详细地描述所有可能的意图和优先级，并标明哪项意图是最可能的。
5. 仅在用户意图明确指向功能调用时才考虑调用相关模块，否则留空。

【用户可能调用的模块】
- 音乐、家居控制、日程调整(添加、删除、修改)、天气、查询最新信息或新闻

【暗示实例】
- 「我明天想出门走走」(未来计划) - 查询天气>设置日程
- 「我担心明天会睡迟」(未来计划) - 设置日程>查询天气
- 「我觉得有点冷」(温度变化) - 查询天气>控制智能家居
- 「要下雨了」(天气变化) - 控制智能家居>查询天气
- 「我心情不太好」(情绪因素) - 安慰>播放音乐
- 「有点安静」(环境因素) - 播放音乐
- 「有点暗」(灯光需求) - 控制智能家居
- 「最近马来西亚的新闻」(现今和未来资讯查询) - 网络搜索

【严格输出 JSON Schema】
请严格按照以下格式进行输出:
```json
{
"intents":[
{"module":"{module}", "confidence": {confidence}},
{"module":"{module}", "confidence": {confidence}}
],
"reasoning":"{reasoning}"
}
```

##intents的数组中最多包含2项候选意图，按confidence降序排列
##{module}你可以输入的值分别有"music", "device control", "schedule", "weather", "web search"
##{confidence}则判定用户想调用该模块的概率
- confidence = 1.0：用户语言中含有明确命令（如“关掉风扇”）
- confidence < 1.0：用户可能含有命令，但用户没有明确表示
##重要：请确保JSON格式正确，数组最后一个元素后不要添加逗号
##请在{reasoning}中输出详细的用户意图描述，至少包含：
- 用户可能需求的摘要（例如：“用户可能在关注天气，可能觉得冷...”或“用户可能想调整设备状态，如关闭风扇...”）
- 每个意图的具体操作建议及依据，不得虚构或添加用户上下文中不存在的状态。
###对于非调用模块/闲聊的用户输入，你务必将放"intents"及"reasoning"留空。

##请确保输出内容尽可能详细和明确，帮助后续系统准确判断是否需要调用具体功能模块

【实例】
用户输入:"姐姐，今天外面好冷噢"
当前时间:"2025-04-14 21:18:15"
当前天气:"小雨"
设备状态:
- "main_room_light" : False
- "main_room_fan" : True
当前日程：
- 当前没有任何日程安排

输出：
```json
{
"intents":[
{"module":"weather", "confidence": 0.9},
{"module":"device control", "confidence": 0.7}
],
"reasoning":"用户可能关注天气变化，可能感到寒冷，同时可能有关闭家居设备（如风扇）的需求。优先级判断：当前设备状态显示风扇仍在开启，因而关闭风扇的需求可能较高。"
}
```

"""
    finetuned_user_message = process_response(message, device_id)
    completion = client.chat.completions.create(
                model="gemma2-9b-it",
                messages=[
                    {"role": "system", "content": text},
                    {"role": "user", "content": str(finetuned_user_message)}
                ],
                max_tokens=256,
                temperature=1,
                top_p=0.1,
                stream=False,
            )

    logger.debug(completion.choices[0].message.content)
    return completion.choices[0].message.content

def process_response(user_formatted_input: str, device_id: str = None) -> str:
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Retrieve device information - Fix: Ensure device_id is not None
    device_lines = []
    actual_device_id = device_id if device_id is not None else "default_device"

    # Ensure device configuration file exists
    try:
        unified_config.ensure_device_config(actual_device_id)
    except Exception as e:
        logger.warning(f"Failed to ensure device configuration: {e}")

    try:
        devices_config = unified_config.get("devices", {}, device_id=actual_device_id)

        # Iterate through all device categories
        for category, category_devices in devices_config.items():
            for device_name, device_info in category_devices.items():
                device_state = device_info.get("state", False)
                device_type = device_info.get("data_type", "bool")

                # Format device state
                device_lines.append(f"- Device: \"{device_name}\", Type: \"{device_type}\", State: {device_state}")
    except Exception as e:
        logger.warning(f"Failed to retrieve device configuration: {e}")

    # If no devices, add a note
    if not device_lines:
        device_lines = ["- 当前没有任何可控设备"]

    # Create ScheduleHandler instance and retrieve schedule information
    from if_schedule import ScheduleHandler
    schedule_handler = ScheduleHandler(device_id=actual_device_id)
    schedules = schedule_handler.load_schedules()
    schedule_lines = []
    for schedule in schedules:
        schedule_time = schedule.get("time", "")
        schedule_content = schedule.get("content", "")
        schedule_lines.append(f"- {schedule_time} {schedule_content}")

    # If no schedules, add a note
    if not schedule_lines:
        schedule_lines = ["- 当前没有任何日程安排"]

    # Extract original user input from formatted input for language detection
    original_user_input = ""
    if "用户输入:" in user_formatted_input:
        # Extract text after "用户输入:" and before next line
        lines = user_formatted_input.split('\n')
        for line in lines:
            if line.startswith("用户输入:"):
                original_user_input = line.replace("用户输入:", "").strip()
                break
    else:
        original_user_input = user_formatted_input

    # Detect language in original user input only
    has_chinese = any('\u4e00' <= char <= '\u9fff' for char in original_user_input)

    # Add language-specific instruction
    language_instruction = ""
    if has_chinese:
        language_instruction = "请用中文生成JSON格式的自然语言对话"
    else:
        language_instruction = "please use english to generate JSON format"

    message = f"""
{user_formatted_input}
设备状态:
{chr(10).join(device_lines)}
当前日程：
{chr(10).join(schedule_lines)}
{language_instruction}
"""
    logger.debug(message)
    return message

if __name__ == '__main__':
    # Test function model
    while True:
        user_input = input("User Input: ")
        if user_input == "exit":
            break
        user_formatted_input = f"""
用户输入:"{user_input}"
当前时间:"2025-04-23 21:19:15"
当前天气:"小雨"
"""
        # Call function model for processing
        response = send(user_formatted_input)
        print(f"Response: {response}")