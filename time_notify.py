import time
import threading
import sys
from datetime import datetime
from loguru import logger
from unified_config import unified_config
from play import play


class TimeNotifier:
    """Time notification class for hourly announcements"""

    def __init__(self, chat_saver=None, device_id=None):
        """
        Initialise time notifier

        Args:
            chat_saver: Chat history saver instance
            device_id: Device ID, used to obtain device-specific configuration
        """
        self.chat_saver = chat_saver
        self.device_id = device_id
        self.last_hour = None
        self.running = True
        self.thread = None
        self.monitor_thread = None
        self.is_monitoring = False
        self.language_templates = {
            "chinese": {
                "morning": "morning",
                "afternoon": "afternoon",
                "evening": "evening",
                "greeting": "Good",
                "announcement": "It's {hour} o'clock in the {period}~"
            },
            "english": {
                "morning": "morning",
                "afternoon": "afternoon",
                "evening": "evening",
                "greeting": "Good",
                "announcement": "It's {hour} o'clock in the {period}~"
            },
            "malay": {
                "morning": "pagi",
                "afternoon": "tengah hari",
                "evening": "malam",
                "greeting": "Selamat",
                "announcement": "Pengumuman masa, sekarang pukul {hour} {period}"
            }
        }

    def _get_period(self, hour, language):
        templates = self.language_templates.get(language, self.language_templates["english"])

        if hour < 12:
            return templates["morning"]
        elif hour < 18:
            return templates["afternoon"]
        else:
            return templates["evening"]

    def _format_hour(self, hour, language):
        """Format the hour number"""
        if language == "chinese":
            return hour if hour <= 12 else hour - 12
        return hour

    def _get_announcement_text(self, now):
        """Generate announcement text based on language"""
        # Get language setting from config, default to English
        language = unified_config.get("system.language", "english", device_id=self.device_id).lower()

        # Get language templates
        templates = self.language_templates.get(language, self.language_templates["english"])

        # Get period and hour
        period = self._get_period(now.hour, language)
        hour = self._format_hour(now.hour, language)

        # Construct text based on language
        if language == "chinese":
            return f"{period}{templates['greeting']}, {templates['announcement'].format(period=period, hour=hour)}"
        elif language == "malay":
            return f"{templates['greeting']} {period}, {templates['announcement'].format(hour=hour, period=period)}"
        else:  # english
            return f"{templates['greeting']} {period}, {templates['announcement'].format(hour=hour, period=period)}"

    def start(self):
        """Start time notification service"""
        if self.thread and self.thread.is_alive():
            logger.warning("Time notification service is already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._time_notify_loop, daemon=True)
        self.thread.start()
        logger.debug("Time notification service started")

    def stop(self):
        """Stop time notification service"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)
        logger.debug("Time notification service stopped")

    def _time_notify_loop(self):
        """Main time notification loop"""
        while self.running:
            try:
                now = datetime.now()
                # Check if it's on the hour
                if now.minute == 0 and now.second < 10:
                    # Check if time notification is enabled
                    time_notify_enabled = unified_config.get("time_notify.enabled", False, device_id=self.device_id)
                    logger.debug(f"[TimeNotify] Device {self.device_id} hourly check: {now.hour}:{now.minute}:{now.second}, Config status: {time_notify_enabled} (Type: {type(time_notify_enabled)}), Last announced hour: {self.last_hour}")

                    if time_notify_enabled is True and self.last_hour != now.hour:
                        logger.info(f"[TimeNotify] Device {self.device_id} starting hourly announcement for {now.hour} o'clock")
                        self._announce_time(now)
                        self.last_hour = now.hour

                        # Sleep for 50 seconds to avoid repeated announcements in the same hour
                        time.sleep(50)
                    else:
                        # On the hour but no need to announce, wait longer
                        if time_notify_enabled is False:
                            logger.debug(f"[TimeNotify] Device {self.device_id} time notification disabled, skipping {now.hour} o'clock announcement")
                        elif self.last_hour == now.hour:
                            logger.debug(f"[TimeNotify] Device {self.device_id} {now.hour} o'clock already announced, skipping")
                        time.sleep(30)
                else:
                    # Calculate seconds to next minute, optimize check interval
                    seconds_to_next_minute = 60 - now.second
                    sleep_time = min(seconds_to_next_minute, 30)  # Sleep at most 30 seconds
                    time.sleep(sleep_time)

            except Exception as e:
                logger.error(f"Time notification error: {e}")
                time.sleep(5)  # Wait 5 seconds after error before continuing

    def _announce_time(self, now, max_wait_time=30):
        """Play hourly announcement using pre-recorded audio files"""
        hour = now.hour

        logger.debug(f"Starting hourly announcement for {hour} o'clock")

        # Save original configuration state
        original_chat_enable = unified_config.get("state_flags.chat_active", device_id=self.device_id)
        original_notify_enable = unified_config.get("state_flags.notification_active", device_id=self.device_id)

        # Wait for suitable announcement conditions
        wait_start_time = time.time()
        wait_time = 0

        while True:
            # Get current status
            current_chat_enable = unified_config.get("state_flags.chat_active", device_id=self.device_id)
            current_notify_enable = unified_config.get("state_flags.notification_active", device_id=self.device_id)

            # Check if announcement conditions are met
            if current_chat_enable is False and current_notify_enable is False:
                # Conditions met, save original state and continue
                original_chat_enable = current_chat_enable
                original_notify_enable = current_notify_enable
                break

            # Check if timeout occurred
            wait_time = time.time() - wait_start_time
            if wait_time >= max_wait_time:
                logger.error(f"Waiting for announcement conditions timed out ({max_wait_time} seconds): chat_enable={current_chat_enable}, notify_enable={current_notify_enable}")
                return False

            # Wait a short period before checking again
            logger.debug(f"Waiting for announcement conditions ({wait_time:.1f} seconds): chat_enable={current_chat_enable}, notify_enable={current_notify_enable}")
            time.sleep(1)

        # Conditions met, start announcement process
        logger.debug(f"Preparing to announce, waited {wait_time:.1f} seconds")

        try:
            # Set temporary state for time announcement
            if original_chat_enable is True and original_notify_enable is False:
                unified_config.set("state_flags.chat_active", True, device_id=self.device_id)  # Pause chat feature
                unified_config.set("state_flags.notification_active", True, device_id=self.device_id)  # Enable notification mode

            # Use device ID from instance
            device_id = self.device_id

            # Play time announcement
            if device_id:
                logger.info(f"Sending hourly chime to device via event system: {device_id}")
                play("sound/time_notify.wav", device_id=device_id)
            else:
                logger.info("Playing hourly chime locally")
                play("sound/time_notify.wav")

            # # Determine audio file path based on language and hour (commented out, not currently used)
            # language = unified_config.get("system.language", "chinese", device_id=self.device_id).lower()
            # # Build audio file path
            # audio_path = f"sound/time_notify/{language}/time{hour}.pcm"

            # # Check if file exists
            # if not os.path.exists(audio_path):
            #     logger.warning(f"Hourly time signal audio file does not exist: {audio_path}, trying to use default language")
            #     # If the specified language file does not exist, try to use the default Chinese version
            #     audio_path = f"sound/time_notify/chinese/time{hour}.pcm"
            #     # If the default file also does not exist
            #     if not os.path.exists(audio_path):
            #         logger.error(f"Default hourly time signal audio file also does not exist: {audio_path}")
            #         return False

            # Play audio for the hourly time signal
            logger.info(f"Play hourly chimes: {hour} o'clock")
            # If there is a chat_saver instance, save the chat history.
            if self.chat_saver:
                # Generate time notification text using multi-language templates
                announcement_text = self._get_announcement_text(now)
                self.chat_saver.save_chat_history(announcement_text, sender="assistant")
            time.sleep(0.5)

        except Exception as e:
            logger.error(f"Hourly announcement playback failed: {e}")
            return False

        finally:
            # Restore original configuration state
            time.sleep(0.5)  # Allow some time for playback to complete
            if original_chat_enable is True and original_notify_enable is False:
                unified_config.set("state_flags.chat_active", original_chat_enable, device_id=self.device_id)
                unified_config.set("state_flags.notification_active", original_notify_enable, device_id=self.device_id)
                logger.debug("Original configuration state restored")

        return True

    # Add test method
    def test_announce(self, custom_hour=None):
        """
        Immediately execute time announcement for testing

        Args:
            custom_hour: Optional, specify hour for test announcement, defaults to current hour
        """
        now = datetime.now()
        if custom_hour is not None:
            # Create a datetime object with custom hour
            now = now.replace(hour=custom_hour)

        logger.debug("Executing test announcement")
        self._announce_time(now)
        return True

    def set_chat_saver(self, chat_saver):
        """Set chat history saver"""
        self.chat_saver = chat_saver
        logger.debug("Chat saver set")

    def work(self, chat_saver=None):
        """
        Monitor time notification configuration and start/stop service accordingly

        Args:
            chat_saver: Chat history saver instance, if provided, overrides the class instance
        """
        # Update instance variable if chat_saver parameter is provided
        if chat_saver is not None:
            self.chat_saver = chat_saver

        # Avoid starting monitoring thread multiple times
        if self.is_monitoring:
            logger.warning("Time notification monitoring is already running")
            return

        self.is_monitoring = True
        logger.info("[TimeNotify] Time notification monitoring successfully started")

        is_service_running = False

        while self.is_monitoring:
            try:
                current_status = unified_config.get("time_notify.enabled", device_id=self.device_id)
                logger.debug(f"[TimeNotify] Device {self.device_id} current config status: {current_status} (Type: {type(current_status)}), Service running status: {is_service_running}")

                # Start notification service when config is True and service is not running
                if current_status is True and not is_service_running:
                    logger.info(f"[TimeNotify] Detected time notification enabled for device {self.device_id}, starting time notification")
                    self.start()
                    is_service_running = True

                # Stop notification service when config is False and service is running
                elif current_status is False and is_service_running:
                    logger.info(f"[TimeNotify] Detected time notification disabled for device {self.device_id}, stopping time notification")
                    self.stop()
                    is_service_running = False

                # Check config every 30 seconds
                time.sleep(30)

            except Exception as e:
                logger.error(f"Time notification monitoring error: {e}")
                time.sleep(5)

    def start_monitor(self, chat_saver=None):
        """
        Start time notification monitoring thread

        Args:
            chat_saver: Chat history saver instance, if provided, overrides the class instance
        """
        if chat_saver is not None:
            self.chat_saver = chat_saver

        if self.monitor_thread and self.monitor_thread.is_alive():
            logger.warning("Time notification monitoring is already running")
            return

        self.is_monitoring = True
        self.monitor_thread = threading.Thread(target=self.work, daemon=True)
        self.monitor_thread.start()
        logger.debug("Time notification monitoring started")

    def stop_monitor(self):
        """Stop time notification monitoring"""
        self.is_monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1)
        logger.debug("Time notification monitoring stopped")

    def test_time_notification(self, hour=None):
        """
        Test time notification functionality, trigger immediate notification

        Args:
            hour: Optional, specify hour for test notification, defaults to current hour
        """
        # Ensure timenotify setting is True
        original_setting = unified_config.get("time_notify.enabled", device_id=self.device_id)
        if not original_setting:
            logger.debug("Test mode: Temporarily enabling timenotify setting")
            unified_config.set("time_notify.enabled", True, device_id=self.device_id)

        # Execute test notification
        result = self.test_announce(custom_hour=hour)

        # Restore original setting
        if not original_setting:
            unified_config.set("time_notify.enabled", original_setting, device_id=self.device_id)

        return result

# When this module is run directly, start automatically
if __name__ == "__main__":
    # Check command-line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == "test":
            # Test mode: Execute time notification test immediately
            logger.info("Starting test mode")
            custom_hour = None
            if len(sys.argv) > 2:
                try:
                    custom_hour = int(sys.argv[2])
                    if not 0 <= custom_hour <= 23:
                        raise ValueError("Hour must be between 0 and 23")
                except ValueError:
                    logger.error(f"Invalid hour format: {sys.argv[2]}")
                    print("Please provide a valid hour (0-23)")
                    sys.exit(1)

            # Create TimeNotifier instance and test
            time_notifier = TimeNotifier()
            time_notifier.test_time_notification(hour=custom_hour)
            sys.exit(0)

        elif sys.argv[1] == "help":
            print("Time Notification Usage:")
            print("  Normal start: python time_notify.py")
            print("  Test current time: python time_notify.py test")
            print("  Test specific time: python time_notify.py test <hour>")
            print("  Help information: python time_notify.py help")
            sys.exit(0)

    # Normal start mode
    print("Time notification service has started")
    print("Tip: Run 'python time_notify.py test' to test the notification function immediately")

    # Create TimeNotifier instance and start monitoring
    time_notifier = TimeNotifier()
    time_notifier.start_monitor()
    logger.info("Time notification configuration monitoring has started")

    # Keep the program running
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        if unified_config.get("time_notify.enabled"):
            time_notifier.stop()
        time_notifier.stop_monitor()
        logger.info("Time notification service has stopped")