# python library
import os
import time
import threading
from loguru import logger

# from modules
from unified_config import get_config, set_config
from play import play
from chat_process import ChatProcess
from if_exit import ExitHandler
from if_time import TimeHandler
from if_weather import WeatherHandler
from if_schedule import ScheduleHandler
from if_device_control import DeviceControlHandler
from if_web import WebHandler
from threading import Lock
from groqapi import GroqChatModule
from if_music import MusicHandler
from play import play


class PreChatState:
    """
    State management class for managing all chat-related state variables
    """

    def __init__(self, device_id=None):
        self.device_id = device_id  # Device ID for configuration management
        self.lock = Lock()
        self.flag = 1  # Whether the system can run
        self.next = False  # Whether the conversation can continue
        self.chat_processing = False  # Whether the conversation is being processed
        self.chat_status = 0  # Conversation status
        self.t3 = None  # Wake word detection thread
        self.text_enable = False  # Website text activity detection
        self.manual_enable = False  # Manual recognition (pv and button)
        self.text = ''  # Text content
        self.times = 0  # Counter
        self.interrupted = False  # Whether it was interrupted

        # External component references
        self.chat_saver = None
        self.tts_manager = None  # This variable will be passed from outside
        self.chatmodule = None
        self.chat_process = None
        self.llm_manager = None  # LLM manager instance

    def reset_flags(self):
        """
        Reset all state flags
        """
        set_config("state_flags.chat_active", False, device_id=self.device_id)
        set_config("state_flags.llm_active", False, device_id=self.device_id)
        set_config("state_flags.notification_active", False, device_id=self.device_id)
        set_config("state_flags.mqtt_message_active", False, device_id=self.device_id)


class PreChat:
    """
    Main chat processing class, encapsulating all chat-related functionalities
    """

    def __init__(self, device_id=None):
        self.device_id = device_id  # Device ID for configuration management
        self.state = PreChatState(device_id)        # Initialize various functional processing classes
        self.exit_handler = ExitHandler()
        self.time_handler = TimeHandler()
        self.weather_handler = WeatherHandler(device_id=self.device_id)

        # Get user_id from device configuration for schedule handler
        user_id = get_config("system.user_id", None, device_id=self.device_id)
        self.schedule_handler = ScheduleHandler(user_id=user_id, device_id=self.device_id)

        self.device_control_handler = DeviceControlHandler(device_id=self.device_id)
        self.web_handler = WebHandler()
        self.llm_manager = None  # LLM manager instance, initialized in start_chat
        logger.debug("Done initializing PreChat module")

    def start_chat(self, tts_manager_instance, chat_saver_instance=None):
        """
        Start chat functionality
        """
        # Set chat saver
        self.state.chat_saver = chat_saver_instance

        if self.state.chat_saver is None:
            logger.error("ChatSaver has not been initialized properly")
            return

        # Receive TTS manager passed from outside
        self.state.tts_manager = tts_manager_instance

        # Create music handler (used only for query processing, does not include MQTT sending functionality)
        self.music_handler = MusicHandler(
            tts_manager_instance,
            chat_saver_instance,
            device_id=self.device_id
        )

        # Initialize LLM service using LLM manager
        from llm_manager import init_llm_manager

        # Get the currently active LLM service from the configuration
        active_service = get_config("LLM.active_service", device_id=self.device_id)
        logger.info(f"Initializing LLM service: {active_service}")

        try:
            # Get user ID and device ID for constructing message history file path
            user_id = get_config("system.user_id", "default_user_id", device_id=self.device_id)
            device_id = get_config("system.device_id", "default_device_id", device_id=self.device_id)

            # Ensure user ID is not None
            user_id = user_id if user_id is not None else "default_user_id"

            # Construct message history file path
            base_dir = os.getcwd()
            chat_history_dir = os.path.join(base_dir, 'user', user_id, device_id, 'chat_history')
            os.makedirs(chat_history_dir, exist_ok=True)

            # All LLM services share the same message history file
            message_file = os.path.join(chat_history_dir, "message.json")

            # Initialize LLM manager
            self.llm_manager = init_llm_manager(active_service, tts_manager_instance, device_id=self.device_id)
            # Save to state for easy access by device_service
            self.state.llm_manager = self.llm_manager
            # Get LLM instance
            self.state.chatmodule = self.llm_manager.llm_instance

            # Load message history from device-specific path
            self.llm_manager.read(message_file)

            logger.debug(f"Successfully initialized LLM service: {active_service}, using model: {self.llm_manager.model_id}")
            logger.debug(f"Loaded message history from {message_file}")
        except Exception as e:
            logger.error(f"Failed to initialize LLM service: {active_service}, error: {e}")
            logger.info("Attempting to use default Groq service")
            self.state.chatmodule = GroqChatModule(device_id=self.device_id)
            self.llm_manager = None
            self.state.llm_manager = None

        # Create ChatProcess instance and pass self reference
        self.state.chat_process = ChatProcess(self.state.chatmodule, device_id=self.device_id)
        # Set handlers
        self.state.chat_process.set_handlers(self)

        # Start interaction thread
        t2 = threading.Thread(target=self.inter, daemon=True)  # Check commands from the server
        t2.start()

        # Start admin setup
        self.admin_setup()

    def activate_chat(self):
        """
        Activate chat functionality
        """
        # First get configuration information to avoid calling get_config within the lock
        chat_active = get_config("state_flags.chat_active", device_id=self.device_id)

        with self.state.lock:
            # Set different activation states based on program running status
            if self.state.chat_processing and not chat_active:  # If processing conversation and cannot start conversation
                self.state.chat_status = 3  # Error flag due to multiple wake-ups
                logger.warning('Conversation was interrupted. Return False...')
                return False

            if self.state.chat_processing and chat_active:  # If processing conversation
                self.state.chat_status = 2  # Activation during running
                # Stop sound playback (streaming) during activation
                try:
                    if self.state.tts_manager:
                        self.state.tts_manager.stop_tts()
                except Exception as e:
                    logger.error(f"Error stopping TTS playback: {e}")
                logger.warning('Conversation was interrupted. Restarting...')
            else:
                self.state.chat_status = 1  # Sleep activation
                logger.success('[Chat] Conversation was activated')

    def inter(self):
        """
        Interaction functionality, check command input
        """
        while True:
            cmd = get_config("interaction.command", device_id=self.device_id)
            if cmd != '':
                logger.debug('Find something in command')
                self.state.text = get_config("interaction.command", device_id=self.device_id)
                self.state.text_enable = True
                self.activate_chat()
                set_config("interaction.command", '', device_id=self.device_id)
                logger.info(f'[Inter] Received command: {self.state.text}')
                continue

            time.sleep(0.5)

    def admin_setup(self):
        """
        Admin setup, handle chat state and control flow
        """
        while self.state.flag == 1:
            # If chat_status is 3, the program cannot handle it, exit directly
            if self.state.chat_status == 3:
                logger.error('Error in chat, The program will exit soon')
                os._exit(0)

            if not self.state.chat_processing:
                set_config("state_flags.chat_active", False, device_id=self.device_id)

            if (not self.state.chat_processing and not get_config("state_flags.notification_active", device_id=self.device_id) and
                    (self.state.chat_status == 1 or (get_config("interaction.next_enable", device_id=self.device_id) and self.state.next is True))):

                time.sleep(0.5)
                set_config("state_flags.chat_active", True, device_id=self.device_id)
                t1 = threading.Thread(target=self.work, daemon=True)
                t1.start()
                logger.info('[Chat] start new conversation')

            # Modify program running status
            if self.state.chat_status == 2:
                # If conversation status is 2, cannot start new conversation, and conversation status is 1
                self.state.chat_processing = False
                self.state.chat_status = 1

            # Provide functionality termination capability
            if self.state.chat_status == -1:
                set_config("state_flags.chat_active", False, device_id=self.device_id)  # Add restriction
                self.state.flag = 0

            time.sleep(0.5)

    def work(self):
        """Work function to handle chat logic"""
        # First set the state to avoid calling configuration functions within the lock
        with self.state.lock:
            self.state.chat_processing = True
            self.state.chat_status = 0
            tmp_text = ''

        # Set configuration outside the lock to avoid deadlocks
        set_config("state_flags.chat_active", True, device_id=self.device_id)
        logger.debug("reach point1")

        # Voice recognition part
        with self.state.lock:
            should_do_stt = (self.state.chat_processing and
                           self.state.text_enable is False and
                           self.state.manual_enable is False)

        if should_do_stt:
            try:
                device_id = get_config("system.device_id", device_id=self.device_id)
                logger.info('[Chat] Recognizing voice...')

                with self.state.lock:
                    self.state.manual_enable = True

                # Create a separate thread to check for new commands
                stop_stt = False

                def check_command():
                    nonlocal stop_stt
                    while not stop_stt:
                        if get_config("interaction.command", device_id=self.device_id) != '':
                            # Command found, set stop flag
                            stop_stt = True
                            logger.info('[Chat] Command detected during STT, interrupting speech recognition')
                            break
                        time.sleep(0.1)

                # Start command check thread
                cmd_check_thread = threading.Thread(target=check_command, daemon=True)
                cmd_check_thread.start()

                try:
                    # Use an empty string as a replacement since STT_MANAGER is no longer used
                    tmp_text = ""
                finally:
                    stop_stt = True  # Ensure the check thread will stop

                # Check again if a command has been set
                if get_config("interaction.command", device_id=self.device_id) != '':
                    # Command exists, discard STT results
                    logger.info('[Chat] Command received during STT, discarding speech recognition result')
                    with self.state.lock:
                        self.state.text_enable = True
                        self.state.manual_enable = False

            except Exception as e:
                logger.warning(e)
                with self.state.lock:
                    self.state.next = False
                    self.state.chat_processing = False
                set_config("state_flags.chat_active", False, device_id=self.device_id)
                return None

        # Handle state updates
        with self.state.lock:
            if self.state.chat_processing:
                self.state.manual_enable = False

            # Handle text input
            if self.state.chat_processing and self.state.text_enable is False:
                self.state.text = tmp_text
                logger.debug('use SR text')
                if self.state.text != '':
                    self.state.chat_saver.save_chat_history(self.state.text, sender="user")
            else:
                logger.debug('use website text')

            if self.state.chat_processing:
                self.state.text_enable = False

            # Ensure text is not None
            if self.state.text is None:
                logger.warning("Text is None, setting to empty string")
                self.state.text = ""

        # Get configuration and play audio outside the lock
        device_id = get_config("system.device_id", device_id=self.device_id)
        play("sound/chatend.wav", device_id=device_id)
        logger.debug("reach point2")

        # Handle exit commands
        with self.state.lock:
            current_text = self.state.text
            chat_processing = self.state.chat_processing

        if chat_processing:
            # Check exit command
            if self.exit_handler.ifend(current_text) and current_text == "":
                logger.info('[Chat] Pause conversation')
                device_id = get_config("system.device_id", device_id=self.device_id)
                play("sound/end.pcm", device_id=device_id, volume=0.8, samplerate=24000)
                if current_text != '':
                    self.state.chat_saver.save_chat_history("Call me again if you need anything", sender="assistant", audio_path=f"sound/end.pcm")

                with self.state.lock:
                    self.state.next = False
                    self.state.chat_processing = False
                    self.state.reset_flags()
                return None

            # Ensure text is not None again
            if current_text is not None and self.exit_handler.ifexit(current_text):
                logger.info('[Chat] Exit conversation')
                self.state.chat_saver.save_chat_history(message="[System] End Chat", sender="assistant", message_type="exit")

                with self.state.lock:
                    self.state.flag = 0
                    self.state.next = False
                    self.state.chat_processing = False
                    self.state.reset_flags()

                # Save message history to device-specific path
                try:
                    # Get user ID and device ID
                    user_id = get_config("system.user_id", "default_user_id", device_id=self.device_id)
                    device_id = get_config("system.device_id", "default_device_id", device_id=self.device_id)

                    # Ensure user ID is not None
                    user_id = user_id if user_id is not None else "default_user_id"

                    # Construct message history file path
                    base_dir = os.getcwd()
                    chat_history_dir = os.path.join(base_dir, 'user', user_id, device_id, 'chat_history')
                    os.makedirs(chat_history_dir, exist_ok=True)

                    # All LLM services share the same message history file
                    message_file = os.path.join(chat_history_dir, "message.json")

                    # Save message history
                    if self.state.chatmodule:
                        if hasattr(self.state.chatmodule, 'save'):
                            self.state.chatmodule.save(message_file)
                            logger.debug(f"Message history saved to {message_file}")
                except Exception as e:
                    logger.error(f"Failed to save message history: {e}")

                # Note: unified_config does not need manual saving, it will save automatically
                os._exit(0)
                return None

        # Handle time queries
        if current_text is not None and (reply := self.time_handler.check_time_query(current_text)) is not None:
            self._handle_tts_response(reply)
            return None

        # Handle weather forecast queries
        if current_text is not None:
            forecast_reply, forecast_handled = self.weather_handler.check_weather_forecast_query(current_text)
            if forecast_handled:
                self._handle_tts_response(forecast_reply)
                return None

        # Handle weather queries
        if current_text is not None and (reply := self.weather_handler.check_weather_query(current_text)) is not None:
            self._handle_tts_response(reply)
            return None

        # View schedule
        schedule_handled = self.schedule_handler.check_view_schedule_query(current_text)
        if schedule_handled:
            schedule_response = self.schedule_handler.view_schedules(current_text)
            logger.debug(f'[Chat] Schedule View query handled: {schedule_response if schedule_response else "No message"}')
            if schedule_response:
                self._handle_tts_response(schedule_response)
            return None

        # Handle schedule queries
        schedule_response = None
        schedule_handled = False
        # Note: process_schedule_query method may need to be implemented in ScheduleHandler class
        # If the method does not exist, it needs to be added in if_schedule.py
        if hasattr(self.schedule_handler, 'process_schedule_query'):
            schedule_response, schedule_handled = self.schedule_handler.process_schedule_query(current_text)
            if schedule_handled:
                logger.debug(f'[Chat] Schedule query handled: {schedule_response if schedule_response else "No message"}')
                if schedule_response:
                    self._handle_tts_response(schedule_response, message_type="schedule")
                return None

        # Handle web queries
        web_response = None
        web_handled = False
        web_response, web_handled = self.web_handler.check_web_query(current_text)
        if web_handled:
            logger.debug(f'[Chat] Web query handled: {web_response if web_response else "No message"}')
            if web_response["answer"]:
                self._handle_tts_response(web_response["answer"], message_type="web_search", extra_data=web_response)
            return None

        # Handle device control queries
        dev_response = None
        dev_handled = False
        dev_response, dev_handled = self.device_control_handler.check_device_query(current_text)
        if dev_handled:
            logger.debug(f'[Chat] Device control query handled: {dev_response if dev_response else "No message"}')
            if dev_response:
                self._handle_tts_response(dev_response, message_type="device_control")
            return None

        # Handle music queries
        music_response = None
        music_handled = False
        chat_history_data = {}
        music_response, music_handled, chat_history_data = self.music_handler.process_music_query(current_text)
        if music_handled:
            logger.debug(f'[Chat] Music query handled: {music_response if music_response else "No message"}')
            if music_response:
                self._handle_tts_response(music_response, message_type="music")

            # Save chat history data returned from if_music
            self._save_music_chat_history_from_data(chat_history_data)

            # Music commands will be handled by MusicHandler.work() in device_service.py
            # This only handles query processing, not direct execution of music commands
            logger.debug("[Music] Music query processing completed, waiting for external execution of music commands")

            with self.state.lock:
                self.state.next = False
                self.state.chat_processing = False
                self.state.reset_flags()
            return None

        # Handle LLM conversation
        weather = self.weather_handler.get_current_weather()
        complete_prompt = f"""
用户输入:{current_text}
当前时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}
当前天气：{weather.get('days')[0].get('current_description_zh','晴天')}, {weather.get('days')[0].get('current_temperature','未知温度')}度
"""

        logger.debug(f"reach point3 with text: {complete_prompt}")

        with self.state.lock:
            still_processing = self.state.chat_processing

        if still_processing:
            # Set LLM active state flag
            set_config("state_flags.llm_active", True, device_id=self.device_id)

            try:
                user_input, first_reply_json, second_reply, function_call_handled = self.state.chat_process.send(complete_prompt)

                if function_call_handled:
                    # Play LLM reply first
                    self._handle_tts_response(second_reply)

                    # Directly call function processing to get return value
                    function_result = self.state.chat_process.function_call_processing(
                        user_input, first_reply_json, second_reply
                    )

                    # Check the return value of the function call, play it if not empty
                    if function_result and function_result.strip() != "":
                        logger.debug(f"Function call return result: {function_result}")

                        if self.state.tts_manager:
                            try:
                                logger.debug("Stopping the first TTS playback...")
                                self.state.tts_manager.stop_tts()
                                logger.debug("The first TTS playback has stopped")
                            except Exception as e:
                                logger.error(f"Error stopping TTS playback: {e}")

                        try:
                            # Play the result of the function call
                            logger.debug("Starting to play the function call result...")
                            self._handle_tts_response(function_result, message_type="function_result")
                        except Exception as e:
                            logger.error(f"Error playing function result TTS: {e}")
                    else:
                        logger.debug("Function call returned empty value, no additional TTS playback")
                else:
                    # If no function call, directly handle TTS response
                    self._handle_tts_response(second_reply)

                # Save conversation history, send to webpage, deepseek is streaming reply, handled in its file
                set_config("interaction.answer", second_reply, device_id=self.device_id)

                if second_reply.find('结束对话') != -1:
                    with self.state.lock:
                        self.state.next = False

            except Exception as e:
                logger.error(f'LLM error:{e}')
                with self.state.lock:
                    self.state.next = False
                    self.state.chat_processing = False
                    self.state.reset_flags()
                return None

        logger.info('[Chat] A conversation end')
        next_enable = get_config("interaction.next_enable", device_id=self.device_id)

        with self.state.lock:
            if next_enable:
                self.state.next = True
            else:
                self.state.next = False
            self.state.chat_processing = False
            self.state.reset_flags()

        return None

    def _handle_tts_response(self, reply, message_type=None, extra_data=None):
        """General method to handle TTS response"""
        if self.state.tts_manager:
            try:
                logger.debug("Stopping TTS playback...")
                self.state.tts_manager.stop_tts()
                logger.debug("TTS playback has stopped")
            except Exception as e:
                logger.error(f"Error stopping TTS playback: {e}")

            try:
                # Get user ID
                user_id = get_config("system.user_id", device_id=self.device_id)
                device_id = get_config("system.device_id", device_id=self.device_id)

                # Check necessary parameters
                if not user_id or not device_id:
                    logger.error(f"Missing necessary parameters: user_id={user_id}, device_id={device_id}")
                    return

                # Ensure audio directory exists - fix path, use deepseekAPI directory as base
                base_dir = os.getcwd()
                audio_dir = os.path.join(base_dir, 'user', user_id, device_id, 'chat_history', 'audio')
                os.makedirs(audio_dir, exist_ok=True)

                # Generate audio file name
                timestamp = time.strftime('%Y%m%d_%H%M%S', time.localtime())
                audio_filename = f"{timestamp}.pcm"
                audio_path = os.path.join(audio_dir, audio_filename)

                # Save TTS audio to user device directory
                self.state.tts_manager.text_to_speech(reply, device_id=device_id, save_to_file=audio_path)

                # Save chat history using relative path
                relative_audio_path = f"user/{user_id}/{device_id}/chat_history/audio/{audio_filename}"

                # Save different chat history based on message type
                if message_type:
                    if message_type == "web_search" and extra_data:
                        self.state.chat_saver.save_chat_history(extra_data, sender="assistant", message_type=message_type)
                    else:
                        self.state.chat_saver.save_chat_history(reply, sender="assistant", message_type=message_type)

                self.state.chat_saver.save_chat_history(reply, sender="assistant", audio_path=relative_audio_path)

                logger.debug(f"TTS audio saved to: {audio_path}")
                logger.debug(f"Relative audio path: {relative_audio_path}")
                logger.debug("TTS playback completed")
            except Exception as e:
                logger.error(f"Error during TTS playback: {e}")

        self.state.next = False
        self.state.chat_processing = False
        self.state.reset_flags()

    def chat_processing_check(self):
        """Check chat processing status"""
        while True:
            logger.debug(f'chat_processing: {self.state.chat_processing}')
            time.sleep(0.8)

    def sleep_for_if_statement(self, reply):
        """Add fixed wait time for if statement to ensure audio playback completion"""
        logger.info("Waiting for audio playback to complete...")
        # Check if text contains Chinese characters
        has_chinese = any('\u4e00' <= char <= '\u9fff' for char in reply)

        text_length = len(reply)  # Get reply text length
        if has_chinese:
            # Chinese characters approximately 0.3 seconds each
            wait_time = max(3, text_length * 0.5)
        else:
            # English characters approximately 0.15 seconds each
            wait_time = max(3, text_length * 0.2)

        time.sleep(wait_time)

    def _save_music_chat_history_from_data(self, chat_history_data):
        """Save music-related chat history using data returned from if_music"""
        try:
            logger.debug(f"Start saving music chat history, data: {chat_history_data}")

            if not self.state.chat_saver:
                logger.warning("chat_saver not initialized")
                return

            if not chat_history_data:
                logger.warning("No chat history data")
                return

            # Get friendly message
            friendly_message = chat_history_data.get("friendly_message", "")
            command = chat_history_data.get("command", "")
            current_song = chat_history_data.get("current_song")
            should_save_music_details = chat_history_data.get("should_save_music_details", False)

            logger.debug(f"Command: {command}, Friendly message: {friendly_message}")
            logger.debug(f"Song info: {current_song}, Save detailed info: {should_save_music_details}")

            # Save user-friendly text message
            if friendly_message:
                self.state.chat_saver.save_chat_history(friendly_message, sender="assistant", message_type="text")
                logger.debug(f"Text message saved: {friendly_message}")

            # Save detailed music info if needed
            if should_save_music_details and current_song and isinstance(current_song, dict):
                logger.debug(f"Preparing to save detailed music info: {current_song}")
                self.state.chat_saver.save_chat_history(current_song, sender="assistant", message_type="music")
                logger.info(f"Music info saved to chat history: {current_song.get('title', 'Unknown song')}")
            else:
                logger.debug(f"Not saving detailed music info - Should save: {should_save_music_details}, Song info exists: {bool(current_song)}")

        except Exception as e:
            logger.error(f"Error saving music chat history: {e}")
            import traceback
            logger.error(f"Error details: {traceback.format_exc()}")