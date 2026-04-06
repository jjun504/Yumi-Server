from openai import OpenAI, APIError
import unified_config
from unified_config import get_config
import chat_setup
import os
import pickle
import json
import tokenizer
import summary
from loguru import logger


class DeepSeekChatModule:
    def __init__(self, tts_manager=None, device_id=None):
        self.device_id = device_id  # Device ID for configuration management
        self.tts_manager = tts_manager
        self.client = OpenAI(api_key=get_config("llm_services.deepseek.api_key"), base_url="https://api.deepseek.com")
        self.messages = []  # Removed global variable, using instance variable
        self.init_system("")
        self.MAX_TOKENS_LIMITS = get_config("LLM.summary_tokens", 3000, device_id=device_id)
        self.last_messages_num = get_config("LLM.last_messages_num", 2, device_id=device_id)

        self.read()

    def init_system(self, summary=""):
        self.messages = []
        self.messages.append(chat_setup.choose_system_chat(False, device_id=self.device_id))
        if summary != "":
            self.messages.append({"role": "system", "content": summary})

    def refresh_system_prompt(self):
        """
        Refresh system prompt to reload personality settings after configuration changes.
        Retain existing conversation history, only update the system prompt.
        """
        if not self.messages:
            # If no messages exist, directly initialize
            self.init_system("")
            return

        # Save non-system messages
        non_system_messages = [msg for msg in self.messages if msg['role'] != 'system']

        # Reinitialize system prompt
        new_system_prompt = chat_setup.choose_system_chat(False, device_id=self.device_id)

        # Rebuild message list: new system prompt + possible summary + conversation history
        self.messages = [new_system_prompt]

        # If the first non-system message is a summary (role is system), retain it
        if non_system_messages and non_system_messages[0]['role'] == 'system':
            self.messages.append(non_system_messages[0])
            # Add remaining conversation messages
            self.messages.extend(non_system_messages[1:])
        else:
            # Add all conversation messages
            self.messages.extend(non_system_messages)

        logger.info("System prompt refreshed, retaining existing conversation history")

    def chat_request_stream(self):
        """Synchronous streaming request method"""
        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",  # Use lightweight model for faster response
                messages=self.messages,  # Conversation history
                stream=True,  # Enable streaming response
                max_tokens=get_config("LLM.max_tokens", 256, device_id=self.device_id),  # Limit generation length for faster response
                temperature=get_config("LLM.temperature", 1, device_id=self.device_id),  # Lower value for higher determinism
                top_p=1,  # Higher value to maintain diversity
                frequency_penalty=0.2,  # Slight penalty for repetitive content
                presence_penalty=0.1,  # Slight penalty for new content
                n=1,  # Generate only one reply
                response_format={"type": "text"}  # Ensure plain text response
            )

            collected_messages = []

            # Process streaming response
            for chunk in response:
                if hasattr(chunk.choices[0].delta, 'content') and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    print(content, end='', flush=True)
                    collected_messages.append(content)

            full_reply = ''.join(collected_messages)
            print('\n')  # Add newline to separate text and audio playback info

            # Update session history and token management
            self.messages.append({"role": "assistant", "content": full_reply})
            self._handle_token_limits()

            return full_reply

        except Exception as e:
            logger.error(f"Stream error: {str(e)}")
            return ""

    def _handle_token_limits(self):
        """Helper method to handle token limits"""
        token_usage = tokenizer.num_tokens_from_messages(self.messages)
        logger.debug(f"token_usage: {token_usage}")

        # Retrieve configuration parameters in real-time
        max_tokens_limit = get_config("LLM.summary_tokens", 3000, device_id=self.device_id)
        last_messages_num = get_config("LLM.last_messages_num", 2, device_id=self.device_id)

        if token_usage > max_tokens_limit:
            # Remove system message
            logger.debug(f"token_usage > {max_tokens_limit}, summarizing...")
            messages_without_system = self.messages[1:]

            # Separate messages to summarize and keep the last messages
            # Note: last_messages_num refers to conversation rounds, each round includes user+assistant, so multiply by 2
            total_last_messages = last_messages_num * 2
            messages_to_summarize = messages_without_system[:-total_last_messages]
            last_messages = messages_without_system[-total_last_messages:]

            # Generate summary
            if messages_to_summarize:
                logger.debug(f"summarizing messages: {messages_to_summarize}")
                chat_summary = summary.summarize(messages_to_summarize)
            else:
                logger.debug("no messages to summarize")
                chat_summary = ""

            # Reinitialize system with summary and last messages
            self.init_system(chat_summary)
            self.messages.extend(last_messages)

        self.save()

    def ask(self, user_input):
        """Synchronous version of ask method, compatible with both TTS types"""
        self.messages.append({"role": "user", "content": user_input})
        logger.debug(f"messages sent to model: \n {self.messages}")

        # No longer use asyncio.run, directly use synchronous method
        return self.chat_request_stream()

    def ask_web(self, user_input):
        """ask method to handle web search results"""
        self.messages.append({"role": "function", "name": "web_search", "content": user_input})
        logger.debug(f"messages sent to model: \n {self.messages}")

        # Use synchronous method
        return self.chat_request_stream()

    def save(self, save_path=None):
        """
        Save current conversation history to file

        Args:
            save_path: Optional path to save the conversation history.
                      If None, constructs path based on user_id and device_id:
                      user/{user_id}/{device_id}/chat_history/message.json
        """
        # When saving, only save summary + last_message_num conversations
        # self.messages structure: [system_prompt, summary(optional), user, assistant, user, assistant, ...]
        messages_copy = []
        if self.messages:
            # Skip the first system message (initial prompt)
            messages_without_prompt = self.messages[1:]

            # If there are messages, ensure only summary + last_message_num conversations are retained
            if messages_without_prompt:
                # Find all non-system messages (user and assistant conversations)
                non_system_messages = [msg for msg in messages_without_prompt if msg['role'] != 'system']

                # Retrieve last_message_num configuration in real-time
                last_messages_num = get_config("LLM.last_messages_num", 2, device_id=self.device_id)
                # Get the last last_message_num rounds of conversation
                total_last_messages = last_messages_num * 2  # Each round includes user+assistant
                if len(non_system_messages) >= total_last_messages:
                    last_conversations = non_system_messages[-total_last_messages:]
                else:
                    last_conversations = non_system_messages

                # Construct messages to save: summary + last conversations
                # If there is a summary (second system message), add it
                summary_messages = [msg for msg in messages_without_prompt if msg['role'] == 'system']
                if summary_messages:
                    messages_copy.append(summary_messages[0])  # Only retain the first summary

                # Add the last conversations
                messages_copy.extend(last_conversations)

        # If no save path is provided, construct path based on user ID and device ID
        if not save_path:
            # Retrieve user ID and device ID from configuration
            user_id = get_config("system.user_id", device_id=self.device_id)
            device_id = get_config("system.device_id", device_id=self.device_id)

            # Ensure user ID and device ID are not None, use default values if None
            user_id = user_id if user_id is not None else "default_user_id"
            device_id = device_id if device_id is not None else "default_device_id"

            # Construct save path
            base_dir = os.getcwd()
            chat_history_dir = os.path.join(base_dir, 'user', user_id, device_id, 'chat_history')
            file_path = os.path.join(chat_history_dir, "message.json")
        else:
            file_path = save_path

        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        try:
            # Save in JSON format for easier viewing and editing
            with open(file_path, 'w', encoding='utf-8') as f:
                # Convert messages to serializable format
                serializable_messages = []
                for msg in messages_copy:
                    # Copy message to avoid modifying the original object
                    msg_copy = msg.copy()
                    # Ensure content is a string
                    if 'content' in msg_copy and msg_copy['content'] is not None:
                        msg_copy['content'] = str(msg_copy['content'])
                    serializable_messages.append(msg_copy)

                json.dump(serializable_messages, f, ensure_ascii=False, indent=2)

            logger.success(f"[DeepSeek] Conversation history saved to {file_path}")
        except Exception as e:
            logger.error(f"Error saving conversation history to {file_path}: {str(e)}")

    def read(self, load_path=None):
        """
        Load conversation history from file

        Args:
            load_path: Optional path to load the conversation history from.
                      If None, constructs path based on user_id and device_id:
                      user/{user_id}/{device_id}/chat_history/message.json
                      and falls back to 'message.data' for backward compatibility.
        """
        # If no load path is provided, construct path based on user ID and device ID
        if not load_path:
            # Retrieve user ID and device ID from configuration
            user_id = get_config("system.user_id", device_id=self.device_id)
            device_id = get_config("system.device_id", device_id=self.device_id)

            # Ensure user ID and device ID are not None, use default values if None
            user_id = user_id if user_id is not None else "default_user_id"
            device_id = device_id if device_id is not None else "default_device_id"

            # Construct load path
            base_dir = os.getcwd()
            chat_history_dir = os.path.join(base_dir, 'user', user_id, device_id, 'chat_history')
            file_path = os.path.join(chat_history_dir, "message.json")
        else:
            file_path = load_path

        # First attempt to load JSON format history
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    read_messages = json.load(f)
                    # Read message structure: [summary(optional), user, assistant, user, assistant, ...]
                    # Rebuild as: [system_prompt, summary(optional), user, assistant, user, assistant, ...]

                    # Reinitialize, first add system prompt
                    user_id = get_config("system.user_id", "default_user_id", device_id=self.device_id)
                    self.init_system("")  # This sets the initial system prompt

                    # Add read messages
                    if read_messages:
                        # If the first message is a system message, it is a summary
                        if read_messages[0]['role'] == 'system':
                            # Add summary as the second system message
                            self.messages.append(read_messages[0])
                            # Add remaining messages
                            self.messages.extend(read_messages[1:])
                        else:
                            # No summary, directly add all messages
                            self.messages.extend(read_messages)

                logger.success(f"[DeepSeek] Conversation history loaded from {file_path}")
                return
            except json.JSONDecodeError:
                logger.warning(f"JSON conversation history file {file_path} is corrupted, initializing new conversation.")
                self.init_system("")
            except Exception as e:
                logger.error(f"Error loading conversation history from {file_path}: {str(e)}")
                self.init_system("")

        # Backward compatibility: attempt to load old pickle format history
        elif os.path.exists('message.data'):
            try:
                with open('message.data', 'rb') as f:
                    read_messages = pickle.load(f)
                    self.messages.extend(read_messages)
                logger.success(f"[DeepSeek] Conversation history loaded from message.data (legacy format)")

                # Convert to new format and save
                # If a load path is provided, use it to save; otherwise use default path
                self.save(load_path)  # This uses load_path or constructs default path
                logger.info(f"Converted legacy conversation history to new format")
            except EOFError:
                logger.warning("Legacy conversation history file empty or corrupted, initializing new conversation.")
                self.init_system("")
            except Exception as e:
                logger.error(f"Error loading legacy conversation history: {str(e)}")
                self.init_system("")
        else:
            logger.warning("No saved conversation history found, initializing new conversation.")


if __name__ == '__main__':
    import syslog

    # Initialize chat module
    deepseekchatmodule = DeepSeekChatModule()
    deepseekchatmodule.read()

    # Run synchronously (use synchronous interface regardless of TTS type)
    while True:
        user_input = input("Please enter: ")
        if user_input == "exit":
            break
        deepseekchatmodule.ask(user_input)
    deepseekchatmodule.save()