from groq import Groq
from loguru import logger
from unified_config import unified_config


def get_system_prompt():
    return """
You are a helpful assistant that summarizes conversations between the user and the assistant into a single clear English paragraph. Your goal is to capture all important information from the conversation, especially:

- User-provided facts, preferences, and constraints (e.g., name, goals, plans).
- User’s explicit and implicit questions or intentions.
- Key information or advice given by the assistant.
- Logical inferences that can be drawn from the interaction.
- Persistent or reusable context that may help in future interactions.

The summary should be written as a single coherent English paragraph, without using bullet points or formatting. Do not include metadata, timestamps, or generic phrases like “The user said”. Be specific, clear, and informative.

Always write the summary in English, even if the original conversation was in another language.

Example:
Conversation:
User: 我的名字叫张三，请记住。
Assistant: 好的，我已经记住您的名字是张三。
User: 我打算去巴黎旅游，有什么景点推荐吗？
Assistant: 我推荐埃菲尔铁塔、卢浮宫...
User: 这些景点需要提前预订门票吗？
Assistant: 是的，特别是卢浮宫，建议提前在线预订。

Summary:
The user's name is Zhang San. They are planning a trip to Paris and asked for recommendations for tourist attractions. The assistant suggested the Eiffel Tower and the Louvre Museum. The user inquired whether tickets need to be booked in advance, and the assistant advised that it is especially recommended for the Louvre Museum.
"""


def summarize(message, device_id=None):
    """
    Generate conversation summary

    Args:
        message: Message content to be summarised
        device_id: Device ID, used to obtain device-specific configuration
    """
    logger.info(f"summarizing: {message}")
    client = Groq(api_key=unified_config.get("llm_services.groq.model_api_key"))
    completion = client.chat.completions.create(
        model="gemma2-9b-it",
        messages=[
            {"role": "system", "content": get_system_prompt()},
            {"role": "user", "content": str(message)}
        ],
        max_tokens=1024,
        temperature=0.3,
    )
    result = completion.choices[0].message.content
    logger.info(result)
    return result


if __name__ == '__main__':
    content = [
        {"role": "user", "content": "你好，你叫什么?"},
        {"role": "assistant", "content": "我叫小明"},
        {"role": "user", "content": "你今年几岁?"},
        {"role": "assistant", "content": "我今年18岁"}
    ]
    summary = summarize(content)
    print(summary)