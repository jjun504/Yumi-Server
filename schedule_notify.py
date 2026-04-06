import time
import threading
import datetime
import json
import os
from loguru import logger
from unified_config import unified_config
from if_schedule import ScheduleHandler
from play import play


class ScheduleNotifier:
    def __init__(self, tts_manager=None, chat_saver=None, user_id=None, device_id=None):
        """
        Initialize the schedule notifier

        Args:
            tts_manager: TTS manager instance
            chat_saver: Chat history saver instance
            user_id: User ID, if None, retrieve from config
            device_id: Device ID, if None, retrieve from config
        """
        self.chat_saver = chat_saver
        self.tts_manager = tts_manager
        self.monitor_thread = None

        # Retrieve user ID and device ID
        self.device_id = device_id if device_id is not None else unified_config.get("system.device_id")
        self.user_id = user_id if user_id is not None else unified_config.get("system.user_id")

        # Ensure user_id is not None, use default value if None
        self.user_id = self.user_id if self.user_id is not None else "default_user_id"

        logger.debug(f"Schedule notifier initialized, User ID: {self.user_id}, Device ID: {self.device_id}")

    def notify(self, message, speak=True, max_wait_time=30):
        """
        Schedule notification function, waits for conditions to be met or timeout

        Args:
            message: Message content to notify
            speak: Whether to use voice notification
            max_wait_time: Maximum wait time (seconds)

        Returns:
            bool: Whether the notification was successful
        """
        logger.debug(f"Schedule notification: {message}")

        # Add waiting logic
        wait_start_time = time.time()
        wait_time = 0

        while True:
            # Retrieve current state
            current_chat_enable = unified_config.get("state_flags.chat_active", device_id=self.device_id)
            current_notify_enable = unified_config.get("state_flags.notification_active", device_id=self.device_id)

            # Check if notification conditions are met
            if current_chat_enable is False and current_notify_enable is False:
                # Conditions met, save original state and proceed
                original_chat_enable = current_chat_enable
                original_notify_enable = current_notify_enable
                break

            # Check if timeout occurred
            wait_time = time.time() - wait_start_time
            if wait_time >= max_wait_time:
                logger.error(f"Waiting for notification conditions timed out ({max_wait_time} seconds): chat_enable={current_chat_enable}, notify_enable={current_notify_enable}")
                return False

            # Briefly wait before checking again
            logger.debug(f"Waiting for notification conditions ({wait_time:.1f} seconds): chat_enable={current_chat_enable}, notify_enable={current_notify_enable}")
            time.sleep(1)

        # Conditions met, start notification process
        logger.debug(f"Ready to start notification, waited {wait_time:.1f} seconds")

        # Only play if TTS notification is enabled and conditions are met
        if speak:
            unified_config.set("state_flags.chat_active", True, device_id=self.device_id)  # Pause chat functionality
            unified_config.set("state_flags.notification_active", True, device_id=self.device_id)  # Enable notification mode
            try:
                # Use device ID from instance
                device_id = self.device_id

                # Decide playback method based on device ID
                if device_id:
                    logger.info(f"Sending schedule notification sound to device via event system: {device_id}")
                    play("sound/schedule_notification.wav", device_id=device_id)
                else:
                    logger.info("Playing schedule notification sound locally")
                    play("sound/schedule_notification.wav")

                timestamp = time.strftime('%Y%m%d_%H%M%S', time.localtime())

                # Ensure audio directory exists - use the same path structure as prechat.py
                base_dir = os.getcwd()
                audio_dir = os.path.join(base_dir, 'user', self.user_id, device_id, 'chat_history', 'audio')
                os.makedirs(audio_dir, exist_ok=True)

                # Generate audio filename and path
                audio_filename = f"{timestamp}.pcm"
                audio_path = os.path.join(audio_dir, audio_filename)

                # Use TTS to generate audio and save to correct path
                if device_id:
                    # If device ID exists, pass it to TTS for event system transmission
                    self.tts_manager.text_to_speech(message, save_to_file=audio_path, device_id=device_id)
                else:
                    # Local playback
                    self.tts_manager.text_to_speech(message, save_to_file=audio_path)

                # Save chat history using relative path (consistent with prechat.py)
                if self.chat_saver:
                    relative_audio_path = f"user/{self.user_id}/{device_id}/chat_history/audio/{audio_filename}"
                    self.chat_saver.save_chat_history(message, sender="assistant", audio_path=relative_audio_path)
                    logger.debug(f"Schedule notification audio saved to: {audio_path}")
                    logger.debug(f"Relative audio path: {relative_audio_path}")

                logger.debug(f"Schedule notification has been {'sent to device ' + device_id if device_id else 'played locally'}")
            except Exception as e:
                logger.error(f"TTS playback error: {str(e)}")
                return False
            finally:
                # Restore original configuration state
                time.sleep(1)  # Give TTS some time to complete
                unified_config.set("state_flags.chat_active", original_chat_enable, device_id=self.device_id)
                unified_config.set("state_flags.notification_active", original_notify_enable, device_id=self.device_id)
                logger.debug("Original configuration state restored")

        return True

    # Get schedule file path
    def get_schedule_data_path(self):
        """
        Retrieve the schedule data file path specific to the user device

        Returns:
            str: Schedule data file path
        """
        if self.user_id and self.device_id:
            # Use user device-specific directory
            return os.path.join("user", self.user_id, self.device_id, "schedule", "schedule.data")
        else:
            # Use global directory (backward compatibility)
            return "schedule/schedule.data"

    # Ensure directory exists
    def ensure_dir_exists(self, dir_path):
        """
        Ensure the directory exists

        Args:
            dir_path: Directory path
        """
        os.makedirs(dir_path, exist_ok=True)

    # Check if schedules are due and notify
    def check_and_announce_schedules(self):
        """Check if there are due schedules and notify"""
        # First check if schedule notification is enabled
        schedule_notify_enabled = unified_config.get("schedule_notify.enabled", True, device_id=self.device_id)

        # Create ScheduleHandler instance and load schedules
        schedule_handler = ScheduleHandler(user_id=self.user_id, device_id=self.device_id)
        schedules = schedule_handler.load_schedules()
        now = datetime.datetime.now()
        updated = False

        remaining_schedules = []
        for schedule in schedules:
            schedule_time = datetime.datetime.strptime(schedule["time"], "%Y-%m-%d %H:%M:%S")

            # If schedule time has arrived or passed
            if schedule_time <= now:
                # Only announce if schedule notification is enabled
                if schedule_notify_enabled:
                    logger.debug(f"Starting schedule notification: {schedule['content']}")
                    self.notify(schedule['content'])
                else:
                    logger.debug(f"Schedule notification disabled, skipping announcement: {schedule['content']}")
                # Remove expired schedules regardless of announcement
                updated = True
            else:
                remaining_schedules.append(schedule)

        # If schedules were notified (removed), update the file
        if updated:
            # Get schedule file path
            schedule_data_path = self.get_schedule_data_path()

            # Ensure directory exists
            self.ensure_dir_exists(os.path.dirname(schedule_data_path))

            # Save updated schedules
            with open(schedule_data_path, "w", encoding="utf-8") as f:
                json.dump(remaining_schedules, f, ensure_ascii=False, default=str)

            logger.debug(f"Updated schedule file: {schedule_data_path}, remaining {len(remaining_schedules)} schedules")

        return updated

    # Monitoring thread function
    def work(self, tts_manager=None, chat_saver=None):
        """
        Continuous schedule checking thread function

        Args:
            tts_manager: TTS manager instance, if provided, overrides class instance
            chat_saver: Chat history saver instance, if provided, overrides class instance
        """
        # Update instance variables if parameters are provided
        if tts_manager is not None:
            self.tts_manager = tts_manager
        if chat_saver is not None:
            self.chat_saver = chat_saver

        logger.info("[Schedule] Schedule monitoring successfully started")
        while True:
            try:
                self.check_and_announce_schedules()
                # Check every minute
                time.sleep(60)
            except Exception as e:
                logger.error(f"Schedule checking thread error: {e}")
                time.sleep(60)  # Wait and continue even if an error occurs

    # Start monitoring thread
    def start_work(self):
        """Start schedule monitoring thread"""
        self.monitor_thread = threading.Thread(target=self.work, daemon=True)
        self.monitor_thread.start()
        logger.info("Schedule monitoring service started")
        return self.monitor_thread

    def set_chat_saver(self, chat_saver):
        """Set chat history saver"""
        self.chat_saver = chat_saver

    def set_tts_manager(self, tts_manager):
        """Set TTS manager"""
        self.tts_manager = tts_manager


# When this file is run directly, start the monitoring thread
if __name__ == "__main__":
    import sys

    # Select TTS backend based on configuration
    use_azure = unified_config.get("TTS.use_azure", True)
    use_bytedance = unified_config.get("TTS.use_bytedance", False)

    if use_azure:
        from azureTTS import TTSManager
        tts_manager = TTSManager()
        logger.info("Using Azure TTS backend")
    elif use_bytedance:
        from bytedanceTTS import TTSManager
        tts_manager = TTSManager()
        logger.info("Using Bytedance TTS backend")
    else:
        logger.error("TTS backend not enabled - neither Azure nor Bytedance")
        sys.exit(1)

    # Retrieve user ID and device ID
    device_id = unified_config.get("system.device_id")
    user_id = unified_config.get("system.user_id")
    user_id = user_id if user_id is not None else "default_user_id"

    logger.info(f"Starting schedule monitoring service... User ID: {user_id}, Device ID: {device_id}")

    # Create schedule notifier instance, pass user ID and device ID
    schedule_notifier = ScheduleNotifier(
        tts_manager=tts_manager,
        user_id=user_id,
        device_id=device_id
    )

    # Create ScheduleHandler instance and ensure schedule directory exists
    schedule_handler = ScheduleHandler(user_id=user_id, device_id=device_id)
    schedule_dir = schedule_handler.get_schedule_dir()
    os.makedirs(schedule_dir, exist_ok=True)
    logger.info(f"Created user device schedule directory: {schedule_dir}")

    # Start monitoring thread
    monitor_thread = schedule_notifier.start_work()

    try:
        # Keep main thread running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Schedule monitoring service stopped")