import tiktoken
from loguru import logger
import chat_setup

def num_tokens_from_string(string: str, encoding_name: str) -> int:
    """Returns the number of tokens in a text string."""
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    logger.info(f"num_tokens: {num_tokens}")
    return num_tokens

def num_tokens_from_messages(messages, model="gpt-4o-mini"):
    """Return the number of tokens used by a list of messages."""
    try:
        encoding = tiktoken.get_encoding("o200k_base")  # using fixed encoding
    except KeyError:
        print("Warning: Using o200k_base encoding.")
        encoding = tiktoken.get_encoding("cl100k_base")
    
    tokens_per_message = 3
    tokens_per_name = 1
    
    num_tokens = 0
    for message in messages:
        num_tokens += tokens_per_message
        for key, value in message.items():
            num_tokens += len(encoding.encode(value))
            if key == "name":
                num_tokens += tokens_per_name
    num_tokens += 3
    return num_tokens

# test string tokens
# num_tokens_from_string("hey how are you today?", "o200k_base")

# test messages tokens
# example_messages = [chat_setup.choose_system_chat(True)]
# example_messages.append({"role": "user", "content": "hello"})
# print(f"{num_tokens_from_messages(example_messages)} prompt tokens counted by num_tokens_from_messages().")


# example_messages = [
#     {
#         "role": "system",
#         "content": "You are a helpful, pattern-following assistant that translates corporate jargon into plain English.",
#     },
#     {
#         "role": "system",
#         "name": "example_user",
#         "content": "New synergies will help drive top-line growth.",
#     },
#     {
#         "role": "system",
#         "name": "example_assistant",
#         "content": "Things working well together will increase revenue.",
#     },
#     {
#         "role": "system",
#         "name": "example_user",
#         "content": "Let's circle back when we have more bandwidth to touch base on opportunities for increased leverage.",
#     },
#     {
#         "role": "system",
#         "name": "example_assistant",
#         "content": "Let's talk later when we're less busy about how to do better.",
#     },
#     {
#         "role": "user",
#         "content": "This late pivot means we don't have time to boil the ocean for the client deliverable.",
#     },
# ]

# # example_messages = example_messages[:-2] # delete last two messages
# # print(example_messages)