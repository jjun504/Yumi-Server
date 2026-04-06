import threading
import time
import os
from datetime import datetime
from loguru import logger
from threading import Lock

# Importing the Unified Configuration Manager
import unified_config
from unified_config import get_config, set_config, get_device_details

# Import function module
from prechat import PreChat

from dev_control import MQTTDevClient
from time_notify import TimeNotifier
from schedule_notify import ScheduleNotifier
from if_weather import WeatherHandler
from chat_saver import ChatSaver
from if_music import MusicHandler

# Import tts manager
from tts_manager import init_tts_manager

class DeviceService:
    """
    Device Service Class - Provides dedicated services for each connected device.
    """

    def __init__(self, device_id, server_callback=None):
        """
        Initialize the device service.

        Args:
            device_id: Device ID.
            server_callback: Callback function for sending messages to the server
        """
        self.device_id = device_id
        self.server_callback = server_callback
        self.running = False
        self.threads = []
        self.chat_lock = Lock()
        self.pending_messages = []
        self.stt_processor = None

        # Set up device-specific log processors

        self._setup_device_logger()

        # Device-specific configuration -completely use unified_config

        try:
            # Make sure the device details exist

            unified_config.ensure_device_details(device_id)

            # Initialize the basic configuration of the device (if not exists)

            if not get_config("system.device_id", device_id=device_id):
                set_config("system.device_id", device_id, device_id=device_id)
                set_config("system.boot_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), device_id=device_id)
                set_config("TTS.active_service", "Bytedance TTS", device_id=device_id)
                logger.info(f"Default configuration initialized for device {device_id}")
            else:
                logger.info(f"Configuration already exists for device {device_id}")

        except Exception as e:
            logger.error(f"Failed to initialize device configuration: {e}")
            # Set up basic configuration

            set_config("system.device_id", device_id, device_id=device_id)
            set_config("system.boot_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), device_id=device_id)

        # Initialize the tts service

        self.active_tts_service = get_config("TTS.active_service", "bytedance", device_id=device_id)

        # Ensure that service names are comparative and initialized in lowercase

        tts_service_lower = self.active_tts_service.lower()

        # Standardized service name

        if "azure" in tts_service_lower:
            self.active_tts_service = "azure"
        elif "bytedance" in tts_service_lower or "volcano" in tts_service_lower:
            self.active_tts_service = "bytedance"

        logger.debug(f"正在初始化TTS服务: {self.active_tts_service}")

        # Initialize the tts manager and pass the device id

        self.tts_manager = init_tts_manager(self.active_tts_service.lower(), device_id=self.device_id)
        logger.debug(f"TTS manager initialized, current service: {self.tts_manager.service_name}, model: {self.tts_manager.model_id}")

        # Initialize the chat saver



        # Get user id

        user_id = get_config("system.user_id", "default_user_id", device_id=device_id)

        # Make sure that the user id is not none, if none, use the default value

        user_id = user_id if user_id is not None else "default_user_id"

        # Ensure that the user device directory exists -correct the path and use the current working directory as the benchmark

        base_dir = os.getcwd()
        user_device_dir = os.path.join(base_dir, 'user', user_id, device_id)
        os.makedirs(user_device_dir, exist_ok=True)

        # Create a chat saver, using device-specific log directories

        chat_log_dir = os.path.join(user_device_dir, "chat_history")
        os.makedirs(chat_log_dir, exist_ok=True)

        # Make sure the text and audio subdirectories exist

        text_dir = os.path.join(chat_log_dir, "text")
        audio_dir = os.path.join(chat_log_dir, "audio")
        os.makedirs(text_dir, exist_ok=True)
        os.makedirs(audio_dir, exist_ok=True)

        # Initialize the chat saver

        self.chat_saver = ChatSaver(log_dir=chat_log_dir, device_id=device_id)
        logger.debug(f"Chat saver initialized, using directory: {chat_log_dir}, text saved in: {text_dir}, audio saved in: {audio_dir}")

        self.prechatManager = PreChat(device_id=self.device_id)
        self.musicManager = MusicHandler(device_id=self.device_id)

        self.timeManager = TimeNotifier(device_id=self.device_id)

        # Initialize the schedule notifier, pass the user id and device id

        user_id = get_config("system.user_id", "default_user_id", device_id=self.device_id)
        user_id = user_id if user_id is not None else "default_user_id"
        self.scheduleManager = ScheduleNotifier(user_id=user_id, device_id=self.device_id)

        self.weatherManager = WeatherHandler(device_id=self.device_id)

        # Create an independent MQTT client instance for each device
        # Use device ID as part of client ID to ensure uniqueness

        client_id = f"smart_assistant_87_{self.device_id}_{int(time.time())}"
        # Pass the device id so that the mqtt client uses device-specific configuration

        self.devManager = MQTTDevClient(client_id=client_id, device_id=self.device_id)

        # Update startup time

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Device service startup time: {current_time}")
        set_config("system.boot_time", current_time, device_id=self.device_id)

        # Initialize the stt stream bridge processor

        self._init_stt_processor()

    def start(self):
        """
        Start the device service.
        """
        if self.running:
            logger.warning(f"Service for device {self.device_id} is already running")
            return False

        # Initialize the stt stream bridge processor

        if not hasattr(self, 'stt_processor') or self.stt_processor is None:
            logger.info(f"Initializing STT stream bridge processor for device {self.device_id}")
            if not self._init_stt_processor():
                logger.error(f"Failed to initialize STT stream bridge processor for device {self.device_id}")
                return False

        self.running = True
        logger.info(f"Service started for device {self.device_id}")

        # Start background tasks

        self._start_background_tasks()

        return True

    def stop(self):
        """
        Stop the device service.
        """
        if not self.running:
            logger.warning(f"Service for device {self.device_id} is not running")
            return False

        self.running = False
        logger.info(f"Service stopped for device {self.device_id}")

        # Stop stt stream bridge processor

        if hasattr(self, 'stt_processor') and self.stt_processor is not None:
            self.stt_processor.stop()
            self.stt_processor = None

        # The configuration has been automatically saved through unified config without manual saving

        logger.debug(f"Device {self.device_id} stopped, configuration managed by unified_config")

        # Wait for the thread to end

        for thread in self.threads:
            if thread.is_alive():
                thread.join(timeout=2.0)

        # Clean up device-specific log processors

        self._cleanup_device_logger()

        logger.info(f"Service for device {self.device_id} has been stopped")
        return True

    def _setup_device_logger(self):
        """
        Set up device-specific log processors.
        """
        try:
            # Make sure the device configuration directory exists

            config_dir = os.path.join("device_configs", self.device_id)
            os.makedirs(config_dir, exist_ok=True)

            # Device-specific log file path

            log_file = os.path.join(config_dir, "system.log")

            # Adding device-specific log processors

            self.logger_id = logger.add(
                log_file,
                rotation="1 week",
                level="DEBUG",
                format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}:{function}:{line}</cyan> - {message}"
            )

            logger.info(f"Log processor set up for device {self.device_id}, log file: {log_file}")
        except Exception as e:
            logger.error(f"Error setting up log processor for device {self.device_id}: {e}")
            self.logger_id = None

    def _cleanup_device_logger(self):
        """
        Clean up device-specific log processors.
        """
        try:
            if hasattr(self, 'logger_id') and self.logger_id is not None:
                logger.remove(self.logger_id)
                logger.info(f"Log processor removed for device {self.device_id}")
                self.logger_id = None
        except Exception as e:
            logger.error(f"Error cleaning up log processor for device {self.device_id}: {e}")

    def _start_background_tasks(self):
        """
        Start background tasks.
        """
        # Create a wrapper function and run the function directly (the config context is no longer required)

        def run_in_context(func, *args, **kwargs):
            return func(*args, **kwargs)



        # Chat Service

        t1 = threading.Thread(target=run_in_context, args=(self.prechatManager.start_chat, self.tts_manager, self.chat_saver), daemon=True)
        t1.start()
        self.threads.append(t1)
        logger.debug('Chat Service thread started')

        # Music processing services

        t2 = threading.Thread(target=run_in_context, args=(self.music_work_thread,), daemon=True)
        t2.start()
        self.threads.append(t2)
        logger.debug('Music Handler thread started')

        # Wait for the llm manager to initialize

        max_wait = 10  # Wait up to 10 seconds

        wait_count = 0
        while not hasattr(self.prechatManager, 'llm_manager') or self.prechatManager.llm_manager is None:
            time.sleep(0.5)
            wait_count += 1
            if wait_count >= max_wait * 2:
                logger.warning("Timeout waiting for LLM manager initialization")
                break



        # Time Notification Service

        t3 = threading.Thread(target=run_in_context, args=(self.timeManager.work, self.chat_saver), daemon=True)
        t3.start()
        self.threads.append(t3)
        logger.debug('Time Notify thread started')

        # Schedule Notification Service -Pass TTS Manager and Chat Saver directly when starting thread

        t4 = threading.Thread(target=run_in_context, args=(self.scheduleManager.work, self.tts_manager, self.chat_saver), daemon=True)
        t4.start()
        self.threads.append(t4)
        logger.debug('Schedule thread started')

        # Weather update service

        t5 = threading.Thread(target=run_in_context, args=(self.weatherManager.start_weather_update_thread,), daemon=True)
        t5.start()
        self.threads.append(t5)
        logger.debug('Weather update thread started')

        # Device Control Service -No separate thread is required, because MQTTDevClient has started the network loop at initialization
        # Just make sure the MQTT client is initialized

        if self.devManager and hasattr(self.devManager, 'client') and self.devManager.client:
            logger.debug('Device Control service is already running')
        else:
            # If the client is not initialized, initialize it

            self.devManager.initialize()
            logger.debug('Device Control service initialized')

    def send_chat_message(self, message_data):
        """
        Send chat records to the server.

        Args:
            message_data: Message data, e.g.,
            {
                "sender": "user",  # or "assistant"
                "timestamp": "2025-04-18 10:30:00",
                "message": {
                    "type": "text",
                    "content": "Hello, what time is it now?",
                    "audio_path": "/path/to/audio/file.pcm"  # Optional
                }
            }

        Returns:
            bool: Whether the message was successfully sent.
        """
        # Check if the callback function exists
        if not self.server_callback:
            logger.warning(f"Device {self.device_id} attempted to send chat records but no callback function was set")
            with self.chat_lock:
                self.pending_messages.append(message_data)
            return False

        # Retrieve the user ID, use default if not available
        user_id = message_data.get("user_id")
        if user_id is None:
            user_id = get_config("system.user_id", "default_user_id", device_id=self.device_id)
            if user_id is None:
                user_id = "default_user_id"

        # Construct the complete message
        full_message = {
            "id": self.device_id,
            "user_id": user_id,
            "sender": message_data["sender"],
            "timestamp": message_data["timestamp"],
            "message": message_data["message"]
        }

        # Send the message
        try:
            # Call the callback function
            success = self.server_callback("new_chat_message", {
                'device_id': self.device_id,
                'message': full_message
            })

            if success:
                logger.info(f"Chat message sent: {message_data['message'].get('content', '')[:30]}...")
                return True
            else:
                logger.warning("Message sending failed")
                with self.chat_lock:
                    self.pending_messages.append(message_data)
                return False

        except Exception as e:
            logger.error(f"Failed to send chat message: {str(e)}")
            with self.chat_lock:
                self.pending_messages.append(message_data)
            return False

    def handle_config_update(self, config_data):
        """
        Process configuration updates

        Args:
            config_data: Configuration data

        Returns:
            bool: Whether processing was successful
        """
        try:
            logger.info(f"Received configuration update: {config_data}")

            # Check if only the interaction.command has been updated

            is_only_interaction_command = False
            if len(config_data) == 1 and "interaction" in config_data and "command" in config_data.get("interaction", {}):
                is_only_interaction_command = True
                logger.debug("Only interaction.command updated, skipping TTS service switch check")

            # Get the user id bound to the device

            device_user_id = get_device_details(self.device_id, 'user_id')

            # Only the user configuration type is processed, and other configurations are handled uniformly by server.py

            def update_user_config_only(data, prefix=""):
                for key, value in data.items():
                    config_path = f"{prefix}.{key}" if prefix else key
                    if isinstance(value, dict):
                        update_user_config_only(value, config_path)
                    else:
                        # Only handle user configuration types

                        user_config_patterns = ["user_personalization", "device_role_personalization"]
                        is_user_config = any(config_path.startswith(pattern) for pattern in user_config_patterns)

                        if is_user_config and device_user_id:
                            # Personalized configuration is now stored in the device configuration, and the user id parameter is not required.

                            set_config(config_path, value, device_id=self.device_id)
                            logger.debug(f"Updated personalized configuration: {config_path} = {value}")

                            # Check whether the llm system prompt word needs to be refreshed

                            personality_related_configs = [
                                "device_role_personalization.name",
                                "device_role_personalization.age",
                                "device_role_personalization.relationship",
                                "device_role_personalization.personality",
                                "device_role_personalization.background",
                                "user_personalization.name",
                                "user_personalization.age",
                                "user_personalization.hobbies",
                                "user_personalization.region",
                                "user_personalization.profile"
                            ]

                            if config_path in personality_related_configs:
                                self._refresh_llm_system_prompt()
                                logger.info(f"LLM system prompt refreshed due to personality-related configuration update: {config_path}")

            # Only update the user configuration, the device configuration is handled uniformly by server.py's handle update config

            update_user_config_only(config_data)

            # Handle user id updates

            if "system" in config_data and "user_id" in config_data["system"]:
                new_user_id = config_data["system"]["user_id"]
                logger.info(f"User ID for device {self.device_id} updated to: {new_user_id}")

                # Update the chat saver directory

                if hasattr(self, 'chat_saver'):
                    # Get a new chat history directory

                    base_dir = os.getcwd()

                    # Handle the case where the value is none and use the default user id

                    user_id_to_use = new_user_id if new_user_id is not None else "default_user_id"
                    user_device_dir = os.path.join(base_dir, 'user', user_id_to_use, self.device_id)
                    os.makedirs(user_device_dir, exist_ok=True)

                    # Create a new chat saver, using device-specific log directory

                    chat_log_dir = os.path.join(user_device_dir, "chat_history")
                    os.makedirs(chat_log_dir, exist_ok=True)

                    # Make sure the text subdirectory exists

                    text_dir = os.path.join(chat_log_dir, "text")
                    os.makedirs(text_dir, exist_ok=True)

                    # Update the chat saver's log directory

                    self.chat_saver.log_file = os.path.join(text_dir, "chat_history.json")
                    self.chat_saver._initialize_json_file()

                    logger.info(f"Chat saver log directory updated: {text_dir}")

            # The configuration has been automatically saved through unified config


            # If not only the interaction.command is updated, check if the tts service needs to be switched

            if not is_only_interaction_command:
                new_tts_service = get_config("TTS.active_service", "bytedance", device_id=self.device_id)

                # Ensure that service names are comparative in lowercase

                new_tts_service_lower = new_tts_service.lower()

                # Standardized service name

                if "azure" in new_tts_service_lower:
                    new_tts_service = "azure"
                    new_tts_service_lower = "azure"
                elif "bytedance" in new_tts_service_lower or "volcano" in new_tts_service_lower:
                    new_tts_service = "bytedance"
                    new_tts_service_lower = "bytedance"

                current_tts_service_lower = self.active_tts_service.lower()

                if new_tts_service_lower != current_tts_service_lower:
                    logger.info(f"Switching TTS service: {self.active_tts_service} -> {new_tts_service}")
                    self.active_tts_service = new_tts_service

                    # Get the current model id

                    model_id = get_config("TTS.model_id", None, device_id=self.device_id)

                    try:
                        # Refresh the available service list

                        self.tts_manager.refresh_available_services()

                        # Switch TTS service -Use lowercase service name

                        self.tts_manager.switch_service(new_tts_service_lower, model_id)

                        logger.info(f"Successfully switched TTS service to {new_tts_service}, using model {self.tts_manager.model_id}")

                        # Note: The configuration file will not be updated here, just switch services in memory

                    except Exception as e:
                        logger.error(f"Failed to switch TTS service: {e}")
                else:
                    # Check whether the model id needs to be updated

                    model_id = get_config("TTS.model_id", None, device_id=self.device_id)
                    if model_id and model_id != self.tts_manager.model_id:
                        logger.info(f"Updating TTS model: {self.tts_manager.model_id} -> {model_id}")

                        try:
                            # Update the model

                            self.tts_manager.update_model(model_id)

                            logger.info(f"Successfully updated TTS model to {model_id}")

                            # Note: The configuration file will not be updated here, but the model will be updated in memory.

                        except Exception as e:
                            logger.error(f"Failed to update TTS model: {e}")

            # Check if LLM service needs to be switched -Again, only executed if not update interaction.command

            if not is_only_interaction_command and hasattr(self.prechatManager, 'chatmodule') and self.prechatManager.chatmodule is not None:
                    # Get the current llm service and model

                    current_llm_service = get_config("LLM.active_service", "groq", device_id=self.device_id)

                    # Check if there is an llm manager

                    if hasattr(self.prechatManager, 'llm_manager') and self.prechatManager.llm_manager is not None:
                        llm_manager = self.prechatManager.llm_manager

                        # Refresh the available service list

                        llm_manager.refresh_available_services()

                        # If the current service is inconsistent with the configuration, switch the service

                        if llm_manager.service_name != current_llm_service:
                            logger.info(f"Switching LLM service: {llm_manager.service_name} -> {current_llm_service}")

                            # Get the current model ID
                            model_id = get_config("LLM.model_id", None, device_id=self.device_id)

                            try:
                                # Save the current LLM service message history
                                try:
                                    # Get the user ID
                                    user_id = get_config("system.user_id", "default_user_id", device_id=self.device_id)
                                    # Ensure the user ID is not None
                                    user_id = user_id if user_id is not None else "default_user_id"

                                    # Construct the message history file path
                                    base_dir = os.getcwd()
                                    chat_history_dir = os.path.join(base_dir, 'user', user_id, self.device_id, 'chat_history')
                                    os.makedirs(chat_history_dir, exist_ok=True)

                                    # All LLM services share the same message history file
                                    message_file = os.path.join(chat_history_dir, "message.json")

                                    # Save the current message history
                                    llm_manager.save(message_file)
                                    logger.debug(f"Message history saved to {message_file}")
                                except Exception as e:
                                    logger.error(f"Failed to save current LLM service message history: {e}")

                                # Switch LLM service
                                new_llm_instance = llm_manager.switch_service(current_llm_service, model_id)

                                # Update chatmodule
                                self.prechatManager.chatmodule = new_llm_instance

                                # Load message history
                                try:
                                    # Load message history
                                    llm_manager.read(message_file)
                                    logger.debug(f"Message history loaded from {message_file}")
                                except Exception as e:
                                    logger.error(f"Failed to load message history: {e}")

                                logger.info(f"Successfully switched LLM service to {current_llm_service}, using model {model_id}")

                                # Note: This does not update the configuration file, only switches the service in memory
                            except Exception as e:
                                logger.error(f"Failed to switch LLM service: {e}")

                        else:
                            # Check if the model ID needs to be updated
                            model_id = get_config("LLM.model_id", None, device_id=self.device_id)
                            if model_id and model_id != llm_manager.model_id:
                                logger.info(f"Updating LLM model: {llm_manager.model_id} -> {model_id}")

                                try:
                                    # Save the current LLM service message history
                                    try:
                                        # get user ID
                                        user_id = get_config("system.user_id", "default_user_id", device_id=self.device_id)
                                        # Ensure that the user ID is not None.
                                        user_id = user_id if user_id is not None else "default_user_id"

                                        # Build message history file path
                                        base_dir = os.getcwd()
                                        chat_history_dir = os.path.join(base_dir, 'user', user_id, self.device_id, 'chat_history')
                                        os.makedirs(chat_history_dir, exist_ok=True)

                                        # All LLM services share the same message history file.
                                        message_file = os.path.join(chat_history_dir, "message.json")

                                        # Save current message history
                                        llm_manager.save(message_file)
                                        logger.debug(f"Saved {llm_manager.service_name} message history to {message_file}")
                                    except Exception as e:
                                        logger.error(f"Failed to save LLM service message history: {e}")

                                    # Update the model
                                    new_llm_instance = llm_manager.update_model(model_id)

                                    # Update chatmodule
                                    self.prechatManager.chatmodule = new_llm_instance

                                    # Load message history
                                    try:
                                        # Load message history
                                        llm_manager.read(message_file)
                                        logger.debug(f"Loaded {llm_manager.service_name} message history from {message_file}")
                                    except Exception as e:
                                        logger.error(f"Failed to load LLM service message history: {e}")

                                    logger.info(f"Successfully updated LLM model to {model_id}")

                                    # Note: This does not update the configuration file, only updates the model in memory
                                except Exception as e:
                                    logger.error(f"Failed to update LLM model: {e}")
                    else:
                        logger.warning("LLM manager not found, unable to switch LLM service")

            return True

        except Exception as e:
            logger.error(f"Handling configuration update failures: {str(e)}")
            return False





    def send_pending_messages(self):
        """Send pending messages."""
        if not self.server_callback:
            logger.warning(f"Device {self.device_id} attempted to send pending messages but no callback function is set.")
            return False

        # Retrieve pending messages
        temp_messages = []
        with self.chat_lock:
            if self.pending_messages:
                logger.info(f"Attempting to send {len(self.pending_messages)} pending messages.")
                temp_messages = self.pending_messages.copy()
                self.pending_messages.clear()

        # Send messages
        success_count = 0
        for message in temp_messages:
            if self.send_chat_message(message):
                success_count += 1

        if temp_messages:
            logger.info(f"Successfully sent {success_count}/{len(temp_messages)} pending messages.")

        return success_count == len(temp_messages)

    def set_server_callback(self, callback):
        """
        Set server callback function.

        Args:
            callback: Callback function for sending messages to the server.

        Returns:
            None
        """
        self.server_callback = callback

        # Attempt to send pending messages
        if self.pending_messages:
            self.send_pending_messages()

    def handle_audio_data(self, seq_num, encoded_data):
        """
        Handle audio data

        Args:
            seq_num: Sequence number
            encoded_data: Encoded audio data

        Returns:
            bool: Whether the processing was successful
        """
        try:
            # Get the STT language setting from the current device configuration
            current_language = get_config("STT.language", "zh-CN", device_id=self.device_id)

            # Check if the STT stream bridge processor has been initialized
            if not hasattr(self, 'stt_processor') or self.stt_processor is None:
                # Initialize the STT stream bridge processor
                self._init_stt_processor()
            # If the STT processor is initialized but the language setting differs from the current configuration, update the language setting
            elif hasattr(self.stt_processor, 'language') and self.stt_processor.language != current_language and current_language:
                # Update the language setting of the STT processor
                old_language = self.stt_processor.language
                self.stt_processor.language = current_language

                # Update the language setting of Azure SpeechConfig
                if hasattr(self.stt_processor, 'speech_config'):
                    self.stt_processor.speech_config.speech_recognition_language = current_language
                    logger.info(f"Updated STT language setting for device {self.device_id}: {old_language} -> {current_language}")

            # Pass the audio data directly to the STT stream bridge processor
            success = self.stt_processor.process_audio_frame(self.device_id, seq_num, encoded_data)

            if not success:
                logger.warning(f"Device {self.device_id} failed to process audio frame {seq_num}")

            return success

        except Exception as e:
            logger.error(f"Failed to process audio data: {e}")
            return False

    def _init_stt_processor(self):
        """Initialize the STT stream bridge processor"""
        try:
            from stt_stream_bridge_processor import STTStreamBridgeProcessor

            # Check if Azure STT configuration exists
            api_key = get_config("STT.azure.api_key")
            region = get_config("STT.azure.region")

            if not api_key or not region:
                logger.error(f"Azure STT configuration missing: API key={'missing' if not api_key else 'set'}, region={'missing' if not region else region}")
                logger.error("Please set the correct STT.azure.api_key and STT.azure.region in config/const_settings.json")
                return False

            logger.info(f"Azure STT configuration: API key={api_key[:5]}..., region={region}")

            # Get the language setting specific to the device
            language = get_config("STT.language", "zh-CN", device_id=self.device_id)
            logger.debug(f"Retrieved STT language setting for device {self.device_id}: {language}")

            # Create the STT stream bridge processor
            self.stt_processor = STTStreamBridgeProcessor(
                udp_port=0,  # Set to 0 to indicate no UDP port listening
                mqtt_broker="broker.emqx.io",
                mqtt_port=1883,
                language=language,
                save_audio=False,
                auto_process=True,
                realtime_mode=True
            )

            # Set the callback function
            self.stt_processor.set_recognition_callback(self._handle_stt_result)

            # Initialize the processor (without starting UDP listening)
            self.stt_processor.initialize_without_udp()

            logger.info(f"STT stream bridge processor initialized for device {self.device_id}, language setting: {language}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize STT stream bridge processor: {e}")
            self.stt_processor = None
            return False

    def _handle_stt_result(self, device_id, text, is_final=False, audio_path=None):
        """
        Handle STT recognition results

        Args:
            device_id: Device ID parameter (if None, use self.device_id instead)
            text: Recognized text
            is_final: Whether it is the final result
            audio_path: Audio file path (optional)
        """
        # Use the correct device ID
        if device_id is None or device_id == "_":
            device_id = self.device_id

        if not is_final:
            # Intermediate results can be used for real-time display
            logger.debug(f"STT intermediate result: {text}")
            return

        # Final results, directly passed to prechat2 for processing
        logger.info(f"STT final result: {text}")

        # Set the recognized text in the configuration
        set_config("interaction.command", text, device_id=self.device_id)

        # Save chat history (including audio path)
        if text and len(text.strip()) > 0:
            self.chat_saver.save_chat_history(text, sender="user", message_type="text", audio_path=audio_path)

    def get_config(self):
        """
        Get current configuration - Load complete configuration from unified_config

        Returns:
            dict: Current complete configuration
        """
        try:
            # Use unified_config instance to directly load the complete device configuration file
            # Avoid circular import issues
            from unified_config import unified_config as uc_instance
            device_config_path = uc_instance._get_config_file_path("device", self.device_id)
            config_data = uc_instance._load_config_file(device_config_path)

            if not config_data:
                logger.warning(f"Device {self.device_id} configuration is empty, returning basic configuration structure")
                # If configuration is empty, return basic configuration structure
                config_data = {
                    "system": {
                        "device_id": self.device_id,
                        "user_id": "default_user_id",
                        "boot_time": ""
                    },
                    "TTS": {
                        "active_service": "bytedance",
                        "model_id": None
                    },
                    "LLM": {
                        "active_service": "groq",
                        "model_id": None
                    }
                }

            return config_data
        except Exception as e:
            logger.error(f"Failed to get device configuration: {e}")
            # Return basic configuration structure as fallback
            return {
                "system": {
                    "device_id": self.device_id,
                    "user_id": "default_user_id",
                    "boot_time": ""
                }
            }

    def music_work_thread(self):
        """Music processing work thread"""
        import time
        logger.info(f"Device {self.device_id} music processing thread started")

        last_command_data = None  # Record the last sent command to avoid duplicate sending
        mqtt_retry_count = 0  # MQTT retry counter
        max_mqtt_retries = 3  # Maximum retry count

        # Volume monitoring related variables
        last_volume = None  # Record the last checked volume value
        volume_check_interval = 0  # Volume check interval counter
        volume_check_frequency = 10  # Check volume every 10 cycles (approximately 1 second)

        while self.running:
            try:
                # Check if the volume configuration has changed
                volume_check_interval += 1
                if volume_check_interval >= volume_check_frequency:
                    volume_check_interval = 0  # Reset counter
                    self._check_volume_config_change(last_volume)
                    # Update last_volume to the current volume
                    from unified_config import get_config
                    last_volume = get_config("audio_settings.music_volume", 50, device_id=self.device_id)

                # Check if there are music commands to execute
                if hasattr(self.prechatManager, 'music_handler') and self.prechatManager.music_handler:
                    execution_data = self.prechatManager.music_handler.prepare_music_execution()

                    if execution_data.get("status") == "ready" and execution_data.get("command_data"):
                        command_data = execution_data["command_data"]

                        # Check if the command is the same as the last sent command to avoid duplicate sending
                        if command_data != last_command_data:
                            # Send MQTT command
                            if hasattr(self, 'devManager') and self.devManager:
                                try:
                                    # Check MQTT connection status
                                    if not hasattr(self.devManager, 'is_connected') or not self.devManager.is_connected:
                                        logger.warning(f"[Music] MQTT not connected, waiting for connection establishment...")
                                        # Wait for a while to allow MQTT connection establishment
                                        time.sleep(2.0)
                                        continue

                                    # Use devManager's MQTT client to send the command
                                    success = self._send_mqtt_music_command(command_data)
                                    if success:
                                        logger.info(f"[Music] Successfully sent MQTT command: {command_data.get('type')}")

                                        # For volume adjustment commands, ensure the configuration is synchronized
                                        if command_data.get('type') == 'set_volume':
                                            self._ensure_volume_config_sync(command_data.get('volume'))

                                        last_command_data = command_data  # Record the sent command
                                        mqtt_retry_count = 0  # Reset retry counter
                                    else:
                                        mqtt_retry_count += 1
                                        logger.error(f"[Music] Failed to send MQTT command: {command_data.get('type')} (Retry {mqtt_retry_count}/{max_mqtt_retries})")

                                        # Skip the command if the maximum retry count is reached
                                        if mqtt_retry_count >= max_mqtt_retries:
                                            logger.error(f"[Music] Maximum retry count reached, skipping command: {command_data.get('type')}")
                                            last_command_data = command_data  # Mark as processed to avoid infinite retries
                                            mqtt_retry_count = 0
                                        else:
                                            # Wait for a while before retrying
                                            time.sleep(1.0)
                                            continue

                                except Exception as e:
                                    logger.error(f"[Music] Error occurred while sending MQTT command: {e}")
                                    mqtt_retry_count += 1
                                    if mqtt_retry_count >= max_mqtt_retries:
                                        logger.error(f"[Music] Maximum retry count reached, skipping command")
                                        last_command_data = command_data
                                        mqtt_retry_count = 0
                            else:
                                logger.warning(f"[Music] MQTT device manager not initialized")
                        else:
                            # Command is the same, skip sending
                            pass

                # Short sleep to avoid high CPU usage
                time.sleep(0.1)

            except Exception as e:
                logger.error(f"Music processing thread error: {e}")
                time.sleep(1.0)

        logger.info(f"Device {self.device_id} music processing thread ended")

    def _send_mqtt_music_command(self, command_data):
        """发送MQTT音乐命令

        Args:
            command_data: 命令数据字典

        Returns:
            bool: 是否发送成功
        """
        try:
            # 首先尝试使用设备服务自己的MQTT客户端
            if self.devManager and hasattr(self.devManager, 'client') and hasattr(self.devManager, 'is_connected'):
                if self.devManager.is_connected and self.devManager.client:
                    return self._publish_mqtt_message(self.devManager.client, command_data, "设备服务MQTT客户端")
                else:
                    logger.debug("[Music] 设备服务MQTT客户端未连接，尝试使用UDP设备管理器的MQTT客户端")

            # 如果设备服务的MQTT客户端不可用，尝试使用UDP设备管理器的MQTT客户端
            try:
                # 使用event_system获取UDP设备管理器的MQTT客户端状态，避免直接导入server模块
                from event_system import event_system
                result = event_system.emit('device_info_request', {
                    'request_type': 'get_mqtt_client_status'
                })

                if isinstance(result, dict) and result.get('success') and result.get('data', {}).get('mqtt_available'):
                    # 通过event_system发送MQTT消息
                    mqtt_result = event_system.emit('device_info_request', {
                        'request_type': 'send_mqtt_message',
                        'topic': topic,
                        'message': command_data
                    })

                    if isinstance(mqtt_result, dict) and mqtt_result.get('success'):
                        logger.debug("[Music] 通过UDP设备管理器MQTT客户端发送音乐命令成功")
                        return True
                    else:
                        logger.debug("[Music] 通过UDP设备管理器MQTT客户端发送音乐命令失败")
                else:
                    logger.debug("[Music] UDP设备管理器MQTT客户端不可用")
            except Exception as e:
                logger.debug(f"[Music] 通过event_system获取UDP设备管理器MQTT客户端失败: {e}")

            logger.error("[Music] 所有MQTT客户端都不可用，无法发送音乐命令")
            return False

        except Exception as e:
            logger.error(f"[Music] 发送MQTT音乐命令时出错: {e}")
            return False

    def _publish_mqtt_message(self, mqtt_client, command_data, client_name):
        """使用指定的MQTT客户端发布消息

        Args:
            mqtt_client: MQTT客户端实例
            command_data: 命令数据字典
            client_name: 客户端名称（用于日志）

        Returns:
            bool: 是否发送成功
        """
        try:
            # 构建MQTT主题
            topic = f"smart0337187/server/command/{self.device_id}"

            # 发送命令
            import json
            message = json.dumps(command_data)
            result = mqtt_client.publish(topic, message, qos=1)

            if result.rc == 0:
                logger.debug(f"[Music] 使用{client_name}成功发送MQTT命令到主题 {topic}: {message}")
                return True
            else:
                logger.error(f"[Music] 使用{client_name}发送MQTT命令失败，返回码: {result.rc}")
                # 根据错误码提供更详细的错误信息
                error_messages = {
                    1: "协议版本不支持",
                    2: "客户端ID无效",
                    3: "服务器不可用",
                    4: "连接被拒绝 - 可能是用户名或密码错误，或客户端未正确连接",
                    5: "未授权"
                }
                error_msg = error_messages.get(result.rc, f"未知错误码: {result.rc}")
                logger.error(f"[Music] MQTT错误码{result.rc}: {error_msg}")
                return False

        except Exception as e:
            logger.error(f"[Music] 使用{client_name}发布MQTT消息时出错: {e}")
            return False

    def _ensure_volume_config_sync(self, volume):
        """确保音量配置已同步到设备配置文件

        Args:
            volume: 音量值 (0-100)
        """
        try:
            from unified_config import get_config, set_config

            # 检查当前配置中的音量值
            current_volume = get_config("audio_settings.music_volume", 50, device_id=self.device_id)

            if current_volume != volume:
                # 如果配置中的音量与MQTT命令中的音量不一致，更新配置
                logger.warning(f"[Music] 检测到音量配置不一致，当前配置: {current_volume}, MQTT命令: {volume}")
                success = set_config("audio_settings.music_volume", volume, device_id=self.device_id)
                if success:
                    logger.info(f"[Music] 已同步音量配置: {volume} (设备: {self.device_id})")
                else:
                    logger.error(f"[Music] 同步音量配置失败 (设备: {self.device_id})")
            else:
                logger.debug(f"[Music] 音量配置已同步: {volume} (设备: {self.device_id})")

        except Exception as e:
            logger.error(f"[Music] 检查音量配置同步时出错: {e}")

    def _check_volume_config_change(self, last_volume):
        """Check if the volume configuration has changed, and send MQTT command if changed

        Args:
            last_volume: Last checked volume value
        """
        try:
            from unified_config import get_config

            # Get the current volume value from the configuration
            current_volume = get_config("audio_settings.music_volume", 50, device_id=self.device_id)

            # If the volume has changed and is not in the initialization state
            if last_volume is not None and current_volume != last_volume:
                logger.info(f"[Music] Detected volume configuration change: {last_volume} -> {current_volume} (Device: {self.device_id})")

                # Construct volume adjustment command data, format same as in if_music.py
                volume_command_data = {
                    "type": "set_volume",
                    "volume": current_volume
                }

                # Send MQTT command to pi_client
                success = self._send_mqtt_music_command(volume_command_data)
                if success:
                    logger.info(f"[Music] Successfully sent volume configuration change MQTT command: {current_volume}")
                else:
                    logger.error(f"[Music] Failed to send volume configuration change MQTT command: {current_volume}")

        except Exception as e:
            logger.error(f"[Music] Error occurred while checking volume configuration change: {e}")

    def _refresh_llm_system_prompt(self):
        """
        Refresh LLM system prompt
        Called when personality-related configuration is updated
        """
        try:
            # Check if there is an LLM manager
            if hasattr(self.prechatManager, 'llm_manager') and self.prechatManager.llm_manager is not None:
                success = self.prechatManager.llm_manager.refresh_system_prompt()
                if success:
                    logger.info(f"Device {self.device_id} LLM system prompt refreshed successfully")
                else:
                    logger.warning(f"Device {self.device_id} LLM system prompt refresh failed")
            else:
                logger.debug(f"Device {self.device_id} does not have an LLM manager, skipping system prompt refresh")
        except Exception as e:
            logger.error(f"Error refreshing LLM system prompt for device {self.device_id}: {e}")