import os
import json
from datetime import datetime
from loguru import logger
from event_system import event_system


class ChatSaver:

    def __init__(self, log_dir: str = "Log/Chat_History", device_id: str = "device01"):
        # Make sure the base directory exists

        os.makedirs(log_dir, exist_ok=True)

        # Create a text subdirectory

        text_dir = os.path.join(log_dir, "text")
        os.makedirs(text_dir, exist_ok=True)

        # Set the log file path to chat history.json in the text subdirectory
        self.log_file = os.path.join(text_dir, "chat_history.json")
        self.device_id = device_id
        self._initialize_json_file()
        self.send_message_callback = None  # Callback function, used to send messages to the server


        logger.debug(f"Chat history will be saved to: {self.log_file}")

        # Get user id from configuration, if not, use the default value
        try:
            from unified_config import unified_config
            self.user_id = unified_config.get("system.user_id", "user001", device_id=device_id)
        except:
            self.user_id = "user001"
            logger.warning("Unable to get user_id from configuration, using default value: user001")

    # How to set the callback function

    def set_send_message_callback(self, callback_function):
        """Set the callback function for sending messages"""
        self.send_message_callback = callback_function
        logger.debug("Message sending callback function has been set")


    def _initialize_json_file(self):
        """Ensure the JSON file exists, create an empty array if not"""
        # Make sure the directory exists

        log_dir = os.path.dirname(self.log_file)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
            logger.debug(f"Created log directory: {log_dir}")

        # Make sure the file exists

        if not os.path.exists(self.log_file):
            with open(self.log_file, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=4)
            logger.debug(f"Created new chat history file: {self.log_file}")

    def sanitize_text(self, text):
        if not text:
            return ""

        if isinstance(text, str):
            try:
                return text.encode('utf-8', errors='ignore').decode('utf-8')
            except:
                return text.encode('ascii', errors='ignore').decode('ascii')

        try:
            return str(text)
        except:
            return ""

    def save_chat_history(self, message, sender="user", message_type="text", audio_path=None):
        """
        Save chat messages to JSON file

        Arguments:
        - message: Message content
        - sender: Sender, can be "user" or "assistant"
        - message_type: Message type, such as "text", "music", "schedule", "device_control", etc.
        - audio_path: Optional, audio file path (only valid for text messages)
        """

        sanitized_message = self.sanitize_text(message) if isinstance(message, str) else message
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Get the latest user id from the configuration every time you save it

        try:
            from unified_config import unified_config
            user_id = unified_config.get("system.user_id", "user001", device_id=self.device_id)
            # If the user id changes, update the instance variable

            if user_id != self.user_id:
                logger.info(f"User ID updated: {self.user_id} -> {user_id}")
                self.user_id = user_id
        except:
            # If it is not possible to get from the configuration, use the user id in the instance variable

            user_id = self.user_id
            logger.debug(f"Using user_id from instance variable: {user_id}")

        # Process audio file paths

        remote_audio_path = ""
        if audio_path:
            # Check whether it is a relative path (starting with user/)

            if audio_path.startswith("user/"):
                # Use the relative path directly, which will be used when the audio is displayed on the front end
                remote_audio_path = audio_path
                logger.debug(f"Using relative audio path: {remote_audio_path}")
            elif os.path.exists(audio_path):
                # Set the remote storage path, which will be used when the front-end displays audio

                remote_audio_path = audio_path
                logger.debug(f"Using absolute audio path: {remote_audio_path}")
            else:
                logger.warning(f"Audio file does not exist: {audio_path}")

        # Create a new message entry

        entry = {
            "id": self.device_id,
            "user_id": user_id,
            "sender": sender,
            "timestamp": timestamp,
            "message": self._create_message_object(sanitized_message, message_type, remote_audio_path)
        }

        try:
            # Send chat messages to the server

            self.send_message_to_server(entry)
            # Read existing data
            # chat_history = []
            # if os.path.exists(self.log_file) and os.path.getsize(self.log_file) > 0:
            #     with open(self.log_file, "r", encoding="utf-8") as f:
            #         try:
            #             chat_history = json.load(f)
            #         except json.JSONDecodeError:
            #             logger.error(f"JSON file format error, will be recreated")
            #             chat_history = []


            # # Add a new entry
            # chat_history.append(entry)

            # # write back file
            # with open(self.log_file, "w", encoding="utf-8") as f:
            #     json.dump(chat_history, f, ensure_ascii=False, indent=4)



            # logger.debug(f"Chat history saved to {self.log_file}")
        except Exception as e:
            logger.error(f"Error sending chat content: {e}")

    def send_message_to_server(self, message_data):
        """Try to send messages to the server, using the event system"""
        try:
            # Record details before sending

            logger.info(f"Preparing to send message via event system: device_id={message_data.get('id')}")
            logger.debug(f"Complete message data: {message_data}")

            # Build event data

            event_data = {
                'device_id': message_data.get('id'),
                'message': message_data
            }

            # Send messages using event system

            logger.info("Calling event_system.emit('new_chat_message', event_data)")
            result = event_system.emit('new_chat_message', event_data)

            # Record the sending result

            logger.info(f"Event system sending result: {result}")

            # If there is no processor or processing fails, try using the callback function
            # if not result and self.send_message_callback:
            #     logger.debug("The event system has no processor or the processing failed, try to use the callback function")
            #     return self.send_message_callback({
            #         'device_id': message_data.get('id'),
            #         'message': message_data
            #     })


            return result
        except Exception as e:
            logger.error(f"Failed to send message to server: {e}")
            logger.exception("Detailed error information:")
            return False

    def _create_message_object(self, message, message_type="text", audio_path=None):
        """Create message object based on message type"""
        if message_type == "text":
            return {
                "type": "text",
                "content": message,
                "audio_path": audio_path if audio_path else ""
            }
        elif message_type == "music" and isinstance(message, dict):
            return {
                "type": "music",
                "content": message.get("title", ""),
                "source": message.get("url", ""),
                "author": message.get("author", ""),
                "author_id": message.get("id", ""),
                "thumbnail": message.get("thumbnail", ""),
                "view_count": str(message.get("view_count", ""))
            }
        elif message_type == "web_search" and isinstance(message, dict):
            return {
                "type": "web_search",
                "content": message.get("result", ""),
                "source": message.get("url", "")
            }
        elif message_type == "schedule":
            return {
                "type": message_type,
                "content": "Schedule Changed"
            }
        elif message_type == "device_control":
            return {
                "type": message_type,
                "content": "Device Status Changed"
            }
        elif message_type in ["exit"]:
            return {
                "type": message_type,
                "content": message
            }
        else:
            # Default

            return {
                "type": message_type,
                "content": message
            }

    def save_dict_data(self, prefix: str, data: dict, message_type="music"):
        """
        Save dictionary data, such as song information

        Arguments:
        - prefix: Prefix description
        - data: Dictionary data
        - message_type: Message type, such as "music", "web_search", etc.
        """
        if not data or not isinstance(data, dict):
            return

        # Create a new dictionary for logging, clean up all string values

        clean_data = {}
        for key, value in data.items():
            if isinstance(value, str):
                clean_data[key] = self.sanitize_text(value)
            else:
                clean_data[key] = value

        # Save prefix message

        self.save_chat_history(prefix, sender="assistant", message_type="text")

        # Save the actual data

        self.save_chat_history(clean_data, sender="assistant", message_type=message_type)

    def read_chat_history(self, count=10):
        """Read the most recent chat history records"""
        try:
            if not os.path.exists(self.log_file):
                return []

            with open(self.log_file, "r", encoding="utf-8") as f:
                history = json.load(f)

            # Return to the last few records

            return history[-count:] if count < len(history) else history
        except Exception as e:
            logger.error(f"Error reading chat history: {e}")
            return []


if __name__ == "__main__":
    chat_saver = ChatSaver()

    # Test basic chat history
    chat_saver.save_chat_history("Hello, how have you been recently?", sender="user")
    chat_saver.save_chat_history("I'm doing great, thank you for asking!", sender="assistant")

    # Test text with special characters
    chat_saver.save_chat_history("こんにちは，你好，안녕하세요!", sender="user")

    # Test dictionary data (such as song information)

    song_info = {
        "title": "Beautiful Day - Your Smile",
        "url": "https://www.youtube.com/watch?v=abcdefg",
        "author": "Zhang San & Li Si",
        "id": "abcdefg",
        "thumbnail": "https://i.ytimg.com/vi/abcdefg/hq720.jpg",
        "view_count": 1234567
    }

    # Save song information
    chat_saver.save_chat_history("Playing Beautiful Day - Your Smile for you", sender="assistant")
    chat_saver.save_chat_history(song_info, sender="assistant", message_type="music")

    # Demonstrate other types of messages
    chat_saver.save_chat_history("Schedule Changed", sender="assistant", message_type="schedule")
    chat_saver.save_chat_history("main_room_light = True", sender="assistant", message_type="device_control")