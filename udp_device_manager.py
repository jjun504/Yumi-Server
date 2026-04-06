#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UDP Device Manager - Responsible for managing device UDP connections and services
Integrates functionalities of server_udp_bridge.py and device_service.py
"""

import socket
import threading
import json
import time
import os
from loguru import logger
import paho.mqtt.client as mqtt
import opuslib
import numpy as np
import base64
import struct
import queue

# Import device service and configuration modules
from device_service import DeviceService
from unified_config import unified_config
from unified_config import (
    get_config, set_config, get_device_details, set_device_details,
    ensure_device_details
)
from wake_stats_manager import wake_stats_manager

class AudioSender:
    """Audio Sender - Responsible for sending TTS audio to clients via UDP"""

    def __init__(self, config=None):
        """Initialize the audio sender

        Args:
            config: Configuration dictionary containing UDP and audio settings
        """
        # Default configuration
        self.config = {
            # UDP settings
            "client_ip": "127.0.0.1",  # Pi client IP
            "client_udp_port": 8885,   # Pi client UDP receiving port

            # Audio settings
            "audio_sample_rate": 24000,
            "audio_channels": 1,
            "audio_chunk_size": 480,   # Number of samples per Opus frame
            "use_raw_pcm": True,       # Whether to use raw PCM audio transmission (without Opus encoding)

            # Transmission control
            "send_delay_factor": 0.65,  # Transmission delay factor, smaller values result in faster transmission, 0.3 is a faster setting

            # Debug settings
            "debug": False
        }

        # Update configuration
        if config:
            self.config.update(config)

        # Initialize state
        self.running = False
        self.sequence_number = 0
        self.audio_queue = queue.Queue()
        self.is_playing = False

        # Initialize Opus encoder (even if using PCM, initialize for easy switching)
        self.encoder = opuslib.Encoder(
            self.config["audio_sample_rate"],
            self.config["audio_channels"],
            opuslib.APPLICATION_AUDIO
        )

        # Set bitrate to 32kbps
        self.encoder.bitrate = 32000
        # Set complexity to 5
        self.encoder.complexity = 5

        # Initialize UDP socket
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Thread lock
        self.lock = threading.Lock()

    def start(self):
        """Start the audio sender"""
        if self.running:
            return

        self.running = True

        # Start the sending thread
        self.send_thread = threading.Thread(target=self._send_worker, daemon=True)
        self.send_thread.start()

        logger.info("Audio sender started")

    def stop(self):
        """Stop the audio sender"""
        self.running = False

        # Wait for the thread to finish
        if hasattr(self, 'send_thread') and self.send_thread.is_alive():
            self.send_thread.join(timeout=2.0)

        # Close the UDP socket
        if self.udp_socket:
            self.udp_socket.close()
            self.udp_socket = None

        logger.info("Audio sender stopped")

    def queue_audio(self, audio_data):
        """Add audio data to the queue

        Args:
            audio_data: Raw PCM audio data

        Returns:
            bool: Whether the data was successfully added to the queue
        """
        try:
            self.audio_queue.put(audio_data)
            return True
        except Exception as e:
            logger.error(f"Failed to add audio to queue: {e}")
            return False

    def _send_worker(self):
        """Sending thread worker function"""
        try:
            logger.info("Audio sending thread started")

            while self.running:
                try:
                    # Get audio data from the queue
                    audio_data = self.audio_queue.get(timeout=1.0)

                    # Process the audio data
                    self._process_audio_data(audio_data)

                    # Mark the task as done
                    self.audio_queue.task_done()

                except queue.Empty:
                    # Queue is empty, continue waiting
                    pass
                except Exception as e:
                    logger.error(f"Error processing audio data: {e}")

        except Exception as e:
            logger.error(f"Audio sending thread exception: {e}")
        finally:
            logger.info("Audio sending thread ended")

    def _process_audio_data(self, audio_data):
        """Process audio data

        Args:
            audio_data: Raw PCM audio data
        """
        try:
            # Convert byte data to NumPy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16)

            # Process in chunks
            chunk_size = self.config["audio_chunk_size"]

            # Get PCM transmission mode from configuration
            use_raw_pcm = self.config.get("use_raw_pcm", True)
            logger.debug(f"Using PCM transmission mode: {'Raw PCM' if use_raw_pcm else 'Opus encoding'}")

            if use_raw_pcm:
                # Use raw PCM transmission
                # Choose larger chunk size to reduce UDP packet count
                pcm_chunk_size = 1024  # Larger PCM chunk size

                for i in range(0, len(audio_array), pcm_chunk_size):
                    # Check if still running
                    if not self.running:
                        break

                    # Get the current chunk
                    chunk = audio_array[i:i+pcm_chunk_size]

                    # Send raw PCM data
                    self._send_audio_packet(chunk.tobytes(), is_raw_pcm=True)

                    # Short sleep to simulate real-time playback
                    delay_factor = self.config.get("send_delay_factor", 0.3)  # Get delay factor from configuration, default is 0.3
                    time.sleep(pcm_chunk_size / self.config["audio_sample_rate"] * delay_factor)
            else:
                # Use Opus encoding transmission
                for i in range(0, len(audio_array), chunk_size):
                    # Check if still running
                    if not self.running:
                        break

                    # Get the current chunk
                    chunk = audio_array[i:i+chunk_size]

                    # If chunk size is insufficient, pad with silence
                    if len(chunk) < chunk_size:
                        padding = np.zeros(chunk_size - len(chunk), dtype=np.int16)
                        chunk = np.concatenate([chunk, padding])

                    # Encode to Opus
                    encoded_data = self.encoder.encode(chunk.tobytes(), chunk_size)

                    # Send data
                    self._send_audio_packet(encoded_data, is_raw_pcm=False)

                    # Short sleep to simulate real-time playback
                    delay_factor = self.config.get("send_delay_factor", 0.3)  # Get delay factor from configuration, default is 0.3
                    time.sleep(chunk_size / self.config["audio_sample_rate"] * delay_factor)

        except Exception as e:
            logger.error(f"Error processing audio data: {e}")

    def _send_audio_packet(self, encoded_data, is_raw_pcm=False):
        """Send audio data packet

        Args:
            encoded_data: Data to send, can be Opus encoded or raw PCM
            is_raw_pcm: If True, indicates the data is raw PCM and needs special marking
        """
        try:
            with self.lock:
                # Construct UDP packet
                packet = struct.pack(">I", self.sequence_number)  # Sequence number, 4 bytes
                packet += struct.pack(">H", len(encoded_data))    # Data length, 2 bytes

                # Add marker to distinguish Opus and PCM data
                # 0 = Opus encoded data, 1 = Raw PCM data
                packet += struct.pack(">B", 1 if is_raw_pcm else 0)  # Marker, 1 byte

                packet += encoded_data                            # Audio data

                # Send packet
                self.udp_socket.sendto(packet, (self.config["client_ip"], self.config["client_udp_port"]))

                if self.config["debug"] and self.sequence_number % 100 == 0:
                    logger.debug(f"Sent audio data packet, sequence number: {self.sequence_number}, size: {len(packet)} bytes, type: {'PCM' if is_raw_pcm else 'Opus'}")

                # Increment sequence number
                self.sequence_number += 1

        except Exception as e:
            logger.error(f"Error sending UDP packet: {e}")

    def send_tts_audio(self, audio_data):
        """Send TTS audio data

        Args:
            audio_data: TTS generated PCM audio data

        Returns:
            bool: Whether the sending was successful
        """
        return self.queue_audio(audio_data)

    def send_raw_pcm(self, audio_data):
        """Directly send raw PCM data without Opus encoding

        Args:
            audio_data: Raw PCM audio data

        Returns:
            bool: Whether the sending was successful
        """
        try:
            # Ensure audio data is of bytes type
            if not isinstance(audio_data, bytes):
                logger.warning("Audio data is not of bytes type, attempting conversion")
                audio_data = bytes(audio_data)

            # Convert byte data to NumPy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16)

            # Choose larger chunk size to reduce UDP packet count
            pcm_chunk_size = 1024  # Larger PCM chunk size

            # Process in chunks
            for i in range(0, len(audio_array), pcm_chunk_size):
                # Check if still running
                if not self.running:
                    break

                # Get the current chunk
                chunk = audio_array[i:i+pcm_chunk_size]

                # Send raw PCM data
                self._send_audio_packet(chunk.tobytes(), is_raw_pcm=True)

                # Short sleep to simulate real-time playback
                delay_factor = self.config.get("send_delay_factor", 0.3)  # Get delay factor from configuration, default is 0.3
                time.sleep(pcm_chunk_size / self.config["audio_sample_rate"] * delay_factor)

            return True

        except Exception as e:
            logger.error(f"Error sending raw PCM data: {e}")
            return False

class UDPDeviceManager:
    """UDP Device Manager - Responsible for managing device UDP connections and services"""

    def __init__(self, config=None, server_chat_histories=None, server_chat_histories_lock=None):
        """Initialize UDP Device Manager

        Args:
            config: Configuration dictionary
            server_chat_histories: server.py's chat_histories dictionary
            server_chat_histories_lock: server.py's chat_histories_lock
        """
        # Record startup time for filtering old messages
        self.start_time = time.time()

        # Default configuration - Read from unified_config
        self.config = {
            # MQTT settings - Read from unified_config
            "mqtt_broker": get_config("mqtt.broker", "broker.emqx.io"),
            "mqtt_port": get_config("mqtt.port", 1883),
            "mqtt_username": get_config("mqtt.username", None),
            "mqtt_password": get_config("mqtt.password", None),
            "mqtt_client_id": f"smart_assistant_877_{int(time.time())}_{id(threading.current_thread())}",  # Use client ID with timestamp and thread ID for uniqueness

            # Topic settings - Read from unified_config
            "topic_prefix": get_config("mqtt.topic_prefix", "smart0337187"),
            "command_topic_template": "{prefix}/server/command/{device_id}",
            "audio_topic_template": "{prefix}/server/audio/{device_id}",
            "status_topic_template": "{prefix}/server/status/{device_id}",

            # UDP settings - Read from unified_config
            "udp_port": get_config("udp.port", 8884),
            "udp_response_port": 8885,

            # Discovery service settings - Read from unified_config
            "discovery_port": get_config("udp.discovery_port", 50000),
            "discovery_request": b"DISCOVER_SERVER_REQUEST",
            "discovery_response_prefix": b"DISCOVER_SERVER_RESPONSE_",

            # Session settings - Read from unified_config
            "session_timeout": get_config("udp.session_timeout", 3600.0),  # Session timeout (seconds)

            # Other settings
            "audio_save_path": "server_recordings",
            "debug": False,

            # Audio settings
            "audio_sample_rate": 24000,
            "audio_channels": 1,
            "audio_chunk_size": 480,   # Number of samples per Opus frame
            "use_raw_pcm": True,  # Read PCM switch setting from global configuration

            # Transmission control
            "send_delay_factor": 0.3  # Transmission delay factor, smaller values result in faster transmission, 0.3 is a faster setting
        }
        logger.debug(self.config["mqtt_client_id"])

        # Update configuration
        if config:
            self.config.update(config)

        # Create audio save directory
        os.makedirs(self.config["audio_save_path"], exist_ok=True)

        # Initialize MQTT client
        self.mqtt_client = None
        self.is_connected = False

        # Initialize UDP sockets
        self.udp_socket = None
        self.udp_response_socket = None


        # No longer maintain local device dictionary,统一使用unified_config管理设备信息
        self.chat_histories = server_chat_histories
        self.chat_histories_lock = server_chat_histories_lock

        self.device_services = {}  # Device ID -> DeviceService instance
        self.audio_senders = {}    # Device ID -> AudioSender instance

        # Control flags
        self.running = True
        self.udp_thread = None
        self.discovery_thread = None
        self.session_monitor_thread = None

        # Callback functions
        self.on_device_status_changed = None
        self.on_device_config_changed = None

        # Create log directory
        os.makedirs("logs", exist_ok=True)

    def initialize(self):
        """Initialize UDP Device Manager"""
        # Initialize MQTT connection
        self._setup_mqtt()

        # Initialize UDP socket
        self._setup_udp()

        # Start UDP listening thread
        self.udp_thread = threading.Thread(target=self._udp_listener, daemon=True)
        self.udp_thread.start()

        # Start discovery service thread
        self.discovery_thread = threading.Thread(target=self._discovery_service, daemon=True)
        self.discovery_thread.start()

        # Start session monitoring thread
        self.session_monitor_thread = threading.Thread(target=self._session_monitor, daemon=True)
        self.session_monitor_thread.start()

        logger.info(f"UDP Device Manager initialization complete, listening on UDP port: {self.config['udp_port']}")
        return True

    def _setup_mqtt(self):
        """Set up MQTT connection - Refer to dev_control.py"""
        # Create client instance - Using paho-mqtt 1.x
        # Use clean_session=True, do not receive old messages
        # Ensure client ID is unique
        if "mqtt_client_id" not in self.config or not self.config["mqtt_client_id"]:
            self.config["mqtt_client_id"] = f"smart_assistant_877_{int(time.time())}_{id(threading.current_thread())}"

        self.mqtt_client = mqtt.Client(self.config["mqtt_client_id"], clean_session=True)
        logger.debug(f"Initializing MQTT client {self.config['mqtt_client_id']} (clean_session=True)")

        # Set username and password (if any)
        if self.config["mqtt_username"] and self.config["mqtt_password"]:
            self.mqtt_client.username_pw_set(
                self.config["mqtt_username"],
                self.config["mqtt_password"]
            )

        # Set callback functions
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_disconnect = self._on_mqtt_disconnect
        self.mqtt_client.on_message = self._on_mqtt_message

        # Set auto-reconnect
        self.mqtt_client.reconnect_delay_set(min_delay=1, max_delay=120)

        # Maximum retry count
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                # Establish connection
                logger.debug(f"Connecting to {self.config['mqtt_broker']}:{self.config['mqtt_port']}... (Attempt {retry_count+1}/{max_retries})")
                self.mqtt_client.connect(
                    self.config["mqtt_broker"],
                    self.config["mqtt_port"],
                    60
                )

                # Start network loop
                self.mqtt_client.loop_start()
                logger.info("MQTT connection established and loop started")

                # Connection successful, break the loop
                break

            except Exception as e:
                retry_count += 1
                logger.error(f"MQTT connection failed (Attempt {retry_count}/{max_retries}): {e}")

                if retry_count < max_retries:
                    # Wait for a while before retrying
                    retry_delay = 2 ** retry_count  # Exponential backoff: 2, 4, 8... seconds
                    logger.info(f"Retrying connection in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"MQTT connection failed, reached maximum retry count ({max_retries})")
                    # After the last attempt fails, still start the loop for later auto-reconnect
                    self.mqtt_client.loop_start()

    def _setup_udp(self):
        """Set up UDP socket"""
        try:
            # Create receiving socket
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Add SO_REUSEADDR option

            # Try to bind the port
            try:
                self.udp_socket.bind(('0.0.0.0', self.config["udp_port"]))
                # Set receive buffer size to improve performance
                self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 262144)  # 256KB
                logger.debug(f"UDP receiving socket bound to port {self.config['udp_port']}")
            except OSError as e:
                if e.errno == 10048:  # Address already in use
                    logger.warning(f"Port {self.config['udp_port']} is already in use, trying backup port")
                    # Try to use backup port
                    backup_port = self.config["udp_port"] + 1
                    self.udp_socket.bind(('0.0.0.0', backup_port))
                    # Update the port in the configuration
                    self.config["udp_port"] = backup_port
                    logger.info(f"Successfully bound to backup port {backup_port}")
                else:
                    raise  # If other errors, re-raise the exception

            # Create response socket
            self.udp_response_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_response_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Add SO_REUSEADDR option
            logger.debug("UDP response socket created")

        except Exception as e:
            logger.error(f"Failed to create UDP socket: {e}")
            # Ensure set to None on failure, to avoid using uninitialized sockets
            self.udp_socket = None
            self.udp_response_socket = None

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        """MQTT connection callback - Refer to dev_control.py"""
        self.is_connected = True
        logger.info(f"Connected to MQTT broker, return code: {rc}")

        # Try to subscribe to wildcard topic
        wildcard_topic = "smart0337187/client/#"
        client.subscribe(wildcard_topic, qos=2)
        logger.debug(f"Subscribed to wildcard topic: {wildcard_topic}")

    def _on_mqtt_disconnect(self, client, userdata, rc):
        """MQTT disconnection callback"""
        logger.warning(f"Disconnected from MQTT broker, return code: {rc}")
        self.is_connected = False

        # If unexpectedly disconnected, try to reconnect
        if rc != 0:
            logger.info("MQTT connection unexpectedly disconnected, will automatically try to reconnect...")

            # Update client ID to ensure uniqueness
            new_client_id = f"smart_assistant_877_{int(time.time())}_{id(threading.current_thread())}"
            logger.info(f"Generated new client ID: {new_client_id}")

            # Update the client ID in the configuration
            self.config["mqtt_client_id"] = new_client_id

            # Client will automatically try to reconnect, as we used loop_start()
            # If manual reconnection is needed, uncomment the code below
            # try:
            #     # Stop current loop
            #     client.loop_stop()
            #     # Create new client instance
            #     self.mqtt_client = mqtt.Client(new_client_id, clean_session=True)
            #     # Set callbacks
            #     self.mqtt_client.on_connect = self._on_mqtt_connect
            #     self.mqtt_client.on_disconnect = self._on_mqtt_disconnect
            #     self.mqtt_client.on_message = self._on_mqtt_message
            #     # Reconnect
            #     self.mqtt_client.connect(self.config["mqtt_broker"], self.config["mqtt_port"], 60)
            #     self.mqtt_client.loop_start()
            #     logger.info("Attempted to reconnect to MQTT")
            # except Exception as e:
            #     logger.error(f"Reconnecting to MQTT failed: {e}")
        else:
            logger.info("MQTT connection closed normally")

    def _on_mqtt_message(self, client, userdata, msg):
        """MQTT message callback - Refer to dev_control.py"""
        try:
            payload = msg.payload.decode()
            logger.debug(f"Received message: {msg.topic}")
            logger.debug(f"Message content: {payload}")

            # Try to parse JSON
            try:
                data = json.loads(payload)
                logger.debug(f"JSON parsed successfully")

                # Check message timestamp, filter out old messages
                if "timestamp" in data:
                    timestamp = data.get("timestamp")
                    time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
                    logger.debug(f"Message timestamp: {timestamp}, Corresponding time: {time_str}")

                    # Calculate time difference
                    now = time.time()
                    diff_seconds = now - timestamp
                    diff_hours = diff_seconds / 3600
                    logger.debug(f"Time difference: {diff_seconds:.2f} seconds ({diff_hours:.2f} hours)")

                    # If message timestamp is earlier than service start time, ignore the message
                    if timestamp < self.start_time:
                        logger.warning(f"Ignoring old message: {msg.topic}, timestamp: {time_str}, service started at: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.start_time))}")
                        return
                else:
                    # If message has no timestamp, assume it's a new message
                    logger.debug(f"Message has no timestamp, assuming it's a new message: {msg.topic}")

                # Handle status topic
                if "/client/status/" in msg.topic:
                    logger.debug(f"Handling status message: {msg.topic}")
                    self._handle_status_message(msg.topic, payload)

                # Handle configuration topic
                elif "/client/config/" in msg.topic:
                    logger.debug(f"Handling configuration message: {msg.topic}")
                    self._handle_config_message(msg.topic, payload)

                # Handle client request topic
                elif "/client/request/" in msg.topic:
                    logger.debug(f"Handling client request message: {msg.topic}")
                    self._handle_client_request_message(msg.topic, payload)

                # Handle other topics
                else:
                    logger.debug(f"Received message on other topic: {msg.topic}")

            except json.JSONDecodeError:
                logger.debug("Message is not valid JSON format")

                # Even if not JSON format, try to handle the message
                # Handle status topic
                if "/client/status/" in msg.topic:
                    logger.debug(f"Handling non-JSON status message: {msg.topic}")
                    self._handle_status_message(msg.topic, payload)

                # Handle configuration topic
                elif "/client/config/" in msg.topic:
                    logger.debug(f"Handling non-JSON configuration message: {msg.topic}")
                    self._handle_config_message(msg.topic, payload)

                # Handle client request topic (non-JSON format)
                elif "/client/request/" in msg.topic:
                    logger.debug(f"Handling non-JSON client request message: {msg.topic}")
                    # For non-JSON format requests, special handling may be needed
                    self._handle_client_request_message(msg.topic, payload)

                # Handle other topics
                else:
                    logger.debug(f"Received non-JSON message on other topic: {msg.topic}")

        except Exception as e:
            logger.error(f"Error processing message: {e}")

    def _handle_config_message(self, topic, payload):
        """Handle device configuration message"""
        logger.debug(f"Starting to handle configuration message: {topic}")
        try:
            # Extract device ID from topic
            topic_device_id = topic.split('/')[-1]
            logger.debug(f"Extracted device ID from topic: {topic_device_id}")

            # Parse configuration message
            message_data = json.loads(payload)
            logger.debug(f"JSON parsed successfully, data type: {type(message_data)}")

            # Check message timestamp, filter out old messages
            if isinstance(message_data, dict) and "timestamp" in message_data:
                timestamp = message_data.get("timestamp")
                time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))

                # If message timestamp is earlier than service start time, ignore the message
                if timestamp < self.start_time:
                    logger.warning(f"Ignoring old configuration message: {topic}, device: {topic_device_id}, timestamp: {time_str}")
                    return

            # Check message format
            device_id = None
            config_data = None

            if isinstance(message_data, dict):
                if 'device_id' in message_data and 'config' in message_data:
                    # New format: {'device_id': xxx, 'config': {...}}
                    device_id = message_data['device_id']
                    config_data = message_data['config']
                    logger.debug(f"Detected new format message, device ID: {device_id}")

                    # Check timestamp in config
                    if isinstance(config_data, dict) and "timestamp" in config_data:
                        timestamp = config_data.get("timestamp")
                        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))

                        # If message timestamp is earlier than service start time, ignore the message
                        if timestamp < self.start_time:
                            logger.warning(f"Ignoring old configuration message (in config): {topic}, device: {device_id}, timestamp: {time_str}")
                            return
                else:
                    # Old format or unknown format, use device ID in topic and entire message as configuration
                    device_id = topic_device_id
                    config_data = message_data
                    logger.debug(f"Detected old format message, using device ID from topic: {device_id}")
            else:
                # Non-dictionary type, use device ID from topic
                device_id = topic_device_id
                config_data = message_data
                logger.warning(f"Message is not dictionary type, using device ID from topic: {device_id}")

            # Ensure device ID and configuration data are present
            if not device_id or not config_data:
                logger.error("Cannot determine device ID or configuration data is empty, cannot process configuration message")
                return

            logger.debug(f"Received configuration data for device {device_id}")

            # Ensure device configuration file exists
            self._ensure_device_config_exists(device_id)

            # Prepare device configuration file path
            config_dir = os.path.join("device_configs", device_id)
            config_path = os.path.join(config_dir, "new_settings.json")

            # Read existing configuration
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    current_config = json.load(f)
            except Exception as e:
                logger.error(f"Error reading device configuration file: {e}")
                current_config = {}

            # Update configuration using set-like logic
            updated_config = self._update_config_recursively(current_config, config_data)

            # Save updated configuration to file
            try:
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(updated_config, f, indent=4, ensure_ascii=False)
                logger.debug(f"Saved updated configuration for device {device_id} to {config_path}")
            except Exception as e:
                logger.error(f"Error saving configuration file: {e}")

            # Get or create device service
            service = self._get_or_create_device_service(device_id, None)

            # Update device service configuration
            if service:
                logger.debug("Updating device service configuration")
                # Directly update device service configuration object, to avoid recursive update conflict with handle_config_update
                service.device_config = updated_config
                # # Save configuration to device-specific file
                # service._save_config()
                # # Sync configuration to config module
                # service._sync_config_to_module()
                # logger.info(f"Updated configuration for device {device_id}")

                # Configuration has been saved to unified configuration manager via save_device_config
                # logger.debug(f"Saved configuration for device {device_id} via unified configuration manager")

                # Note: No longer send configuration here
                # After configuration update, the latest configuration will be sent in _get_or_create_device_service method
                # To avoid duplicate sending
            else:
                logger.warning(f"Cannot get service instance for device {device_id}")

            # Call configuration change callback (if any)
            if self.on_device_config_changed:
                self.on_device_config_changed(device_id, updated_config)

            logger.debug(f"Configuration message handling complete: {topic}")

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON format: {e}")
        except Exception as e:
            logger.error(f"Error processing configuration message: {e}")

    def _update_config_recursively(self, current_config, new_config):
        """
        Recursively update configuration, similar to set function logic

        Args:
            current_config: Current configuration
            new_config: New configuration

        Returns:
            Updated configuration
        """
        # If new configuration is not a dictionary, return new configuration directly
        if not isinstance(new_config, dict):
            return new_config

        # If current configuration is not a dictionary, create an empty dictionary
        if not isinstance(current_config, dict):
            current_config = {}

        # Recursively update configuration
        for key, value in new_config.items():
            if isinstance(value, dict) and key in current_config and isinstance(current_config[key], dict):
                # If value is a dictionary and current configuration also has the key and it's a dictionary, update recursively
                current_config[key] = self._update_config_recursively(current_config[key], value)
            else:
                # Otherwise, update directly
                current_config[key] = value

        return current_config

    def _ensure_device_config_exists(self, device_id):
        """
        Ensure device configuration file exists, create from default configuration if not

        Args:
            device_id: Device ID

        Returns:
            bool: Whether successfully ensured configuration file exists
        """
        config_dir = os.path.join("device_configs", device_id)
        os.makedirs(config_dir, exist_ok=True)
        config_path = os.path.join(config_dir, "new_settings.json")

        # Check if device configuration file exists
        if not os.path.exists(config_path):
            logger.info(f"Configuration file for device {device_id} does not exist, creating from default configuration")
            try:
                # Copy default configuration
                default_config_path = os.path.join("config", "default_setting.json")
                if os.path.exists(default_config_path):
                    with open(default_config_path, 'r', encoding='utf-8') as f:
                        default_config = json.load(f)

                    # Update device ID
                    if "system" in default_config:
                        default_config["system"]["device_id"] = device_id

                    # Save as device configuration
                    with open(config_path, 'w', encoding='utf-8') as f:
                        json.dump(default_config, f, indent=4, ensure_ascii=False)

                    logger.info(f"Created configuration file for device {device_id} from default configuration")
                    return True
                else:
                    logger.warning(f"Default configuration file does not exist: {default_config_path}")
                    # Create an empty configuration file
                    with open(config_path, 'w', encoding='utf-8') as f:
                        json.dump({}, f, indent=4, ensure_ascii=False)
                    return False
            except Exception as e:
                logger.error(f"Error creating device configuration file: {e}")
                # Create an empty configuration file
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump({}, f, indent=4, ensure_ascii=False)
                return False

        return True

    def _handle_client_request_message(self, topic, payload):
        """Handle client request message"""
        logger.debug(f"Starting to handle client request message: {topic}")
        try:
            # Extract device ID from topic
            device_id = topic.split('/')[-1]

            # Parse request message
            try:
                message = json.loads(payload)
            except json.JSONDecodeError:
                logger.warning(f"Client request message is not valid JSON format: {topic}")
                return

            # Check message timestamp, filter out old messages
            if "timestamp" in message and message["timestamp"] < self.start_time:
                logger.warning(f"Ignoring old client request message: {topic}, device: {device_id}")
                return

            # Get request type
            request_type = message.get("type")

            if request_type == "request_next_song":
                logger.info(f"Received request for next song from device {device_id}")
                self._handle_next_song_request(device_id)
            else:
                logger.warning(f"Unknown client request type: {request_type}, device: {device_id}")

        except Exception as e:
            logger.error(f"Error processing client request message: {e}")

    def _handle_next_song_request(self, device_id):
        """Handle request for next song"""
        try:
            # First check the music.resume_play setting in device configuration
            from unified_config import get_config
            resume_play_enabled = get_config("music.resume_play", False, device_id=device_id)

            if not resume_play_enabled:
                logger.info(f"Device {device_id} has music.resume_play set to false, ignoring auto-play request")
                return

            logger.debug(f"Device {device_id} has music.resume_play set to true, handling auto-play request")

            # Get device service
            service = self.device_services.get(device_id)
            if not service:
                logger.warning(f"Device {device_id} has no corresponding device service, cannot handle next song request")
                return

            # Check if device service has music handler
            if not hasattr(service, 'prechatManager') or not service.prechatManager:
                logger.warning(f"Device {device_id} has no pre-chat manager, cannot handle next song request")
                return

            if not hasattr(service.prechatManager, 'music_handler') or not service.prechatManager.music_handler:
                logger.warning(f"Device {device_id} has no music handler, cannot handle next song request")
                return

            # Get next song
            music_handler = service.prechatManager.music_handler
            next_song_data = music_handler._get_next_song()

            if next_song_data:
                # Send command to play next song
                command = {
                    "type": "play_music",
                    "url": next_song_data["url"],
                    "volume": next_song_data["volume"]
                }

                success = self.send_command(device_id, command)
                if success:
                    logger.info(f"Sent command to device {device_id} to play next song: {next_song_data.get('title', 'Unknown')}")
                else:
                    logger.error(f"Failed to send command to device {device_id} to play next song")
            else:
                logger.info(f"Device {device_id} has no more songs to play")
                # Optionally, send command to stop playback
                stop_command = {"type": "stop_music"}
                self.send_command(device_id, stop_command)

        except Exception as e:
            logger.error(f"Error handling request for device {device_id} next song: {e}")

    def _handle_status_message(self, topic, payload):
        """Handle device status message"""
        logger.debug(f"Starting to handle status message: {topic}")
        try:
            # Extract device ID from topic
            device_id = topic.split('/')[-1]

            # Parse status message
            message = json.loads(payload)

            # Check message timestamp, filter out old messages
            if "timestamp" in message and message["timestamp"] < self.start_time:
                logger.warning(f"Ignoring old status message: {topic}, device: {device_id}")
                return

            # Get status
            status = message.get("status", "unknown")

            # Statistics for voice wake-up count - When status is "recording", it indicates voice wake-up trigger
            if status == "recording":
                try:
                    wake_count = wake_stats_manager.increment_wake_count(device_id)
                    logger.info(f"Device {device_id} voice wake-up, total wake-up count: {wake_count}")
                except Exception as e:
                    logger.error(f"Failed to update voice wake-up statistics: {e}")

            # Ensure device configuration file exists
            self._ensure_device_config_exists(device_id)

            # Check if new device (never connected before) or device reconnecting
            existing_device = get_device_details(device_id)
            is_new_device = existing_device is None
            is_reconnecting_device = device_id not in self.device_services and not is_new_device

            # Prepare updated device information
            device_info = {
                "status": status,
                "last_seen": time.time(),
                "authenticated": True,  # For compatibility with devices in server.py
                "sid": None            # For compatibility with devices in server.py
            }

            # Extract all relevant fields from message (except timestamp)
            fields_to_copy = ["ip", "password", "device_id", "model", "user_id"]
            for field in fields_to_copy:
                if field in message:
                    value = message.get(field)
                    # Special handling for user_id field, replace empty string with None
                    if field == "user_id" and (value == "" or value == "default_user_id"):
                        device_info[field] = None
                    else:
                        device_info[field] = value

            # Log extracted fields
            logger.debug(f"Extracted device information from status message: {', '.join([f'{k}={v}' for k, v in device_info.items() if k != 'password'])}")

            # If existing device, save old status for comparison
            old_status = existing_device.get("status", "unknown") if existing_device else None

            # Update device information to unified configuration manager
            if is_new_device:
                # Create new device details
                for key, value in device_info.items():
                    set_device_details(device_id, key, value)
                logger.info(f"New device online: {device_id}, status: {status}")
            else:
                # Update existing device information
                for key, value in device_info.items():
                    set_device_details(device_id, key, value)
                if is_reconnecting_device:
                    logger.info(f"Device reconnected: {device_id}, status: {status}")

            # Handle status change
            status_changed = old_status != status and not is_new_device

            # Call callback (for new device or status change)
            if (is_new_device or status_changed) and self.on_device_status_changed:
                try:
                    self.on_device_status_changed(device_id, status, is_new_device)
                except Exception as e:
                    logger.error(f"Failed to call device status change callback: {e}")

            # Get current logged-in user ID
            try:
                from flask import session, has_request_context
                # Check if in request context
                if has_request_context():
                    user_id = session.get('user_id')
                else:
                    # Not in request context, use default user ID
                    user_id = None
                    logger.debug("Not in request context, cannot get user_id from session")
            except Exception as e:
                user_id = None
                logger.warning(f"Error getting user ID: {e}")

            # If user is logged in, update user_id in device configuration
            if user_id and (is_new_device or is_reconnecting_device):
                logger.info(f"Updating user_id for device {device_id} to {user_id}")

                # Read device configuration
                config_dir = os.path.join("device_configs", device_id)
                config_path = os.path.join(config_dir, "new_settings.json")

                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        device_config = json.load(f)

                    # Update user_id
                    if "system" not in device_config:
                        device_config["system"] = {}

                    # Check if it's the default user_id
                    if device_config["system"].get("user_id") == "default_user_id":
                        # Update user_id
                        device_config["system"]["user_id"] = user_id

                        # Save updated configuration
                        with open(config_path, 'w', encoding='utf-8') as f:
                            json.dump(device_config, f, indent=4, ensure_ascii=False)

                        logger.info(f"Updated user_id for device {device_id} to {user_id}")

                        # Update device service configuration
                        device_service = self.get_device_service(device_id)
                        if device_service:
                            # Update device service configuration
                            device_service.handle_config_update(device_config)
                            logger.info(f"Updated configuration for device {device_id} service")

                        # Publish updated configuration to client via MQTT
                        if self.is_connected:
                            self.publish_device_config_to_mqtt(device_id)
                    else:
                        logger.debug(f"Device {device_id} user_id is not default value, no need to update")
                except Exception as e:
                    logger.error(f"Error updating user_id for device {device_id}: {e}")

            # Create service for new or reconnecting device
            if is_new_device or is_reconnecting_device:
                self._get_or_create_device_service(device_id, message.get("ip"))

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON format: {e}")
        except Exception as e:
            logger.error(f"Error processing status message: {e}")

    # def publish_device_info_to_mqtt(self, device_id):
    #     """将设备信息通过MQTT发布给客户端"""
    #     try:
    #         if not device_id or device_id not in self.devices:
    #             logger.warning(f"尝试发布不存在的设备信息: {device_id}")
    #             return False

    #         # 检查MQTT客户端是否可用
    #         if not self.is_connected:
    #             logger.warning(f"MQTT客户端未连接，无法发布设备信息: {device_id}")
    #             return False

    #         # 构建设备信息主题
    #         device_info_topic = f"{self.config['topic_prefix']}/server/config/{device_id}"

    #         # 准备设备信息数据（不包含敏感信息）
    #         device_info = {
    #             'device_id': device_id,
    #             'status': self.devices[device_id].get('status', 'offline'),
    #             'timestamp': time.time(),
    #             'source': 'server'
    #         }

    #         # 添加其他非敏感字段
    #         for key, value in self.devices[device_id].items():
    #             if key not in ['sid', 'authenticated'] and key != 'device_id':
    #                 device_info[key] = value

    #         # 发布设备信息
    #         self.mqtt_client.publish(
    #             device_info_topic,
    #             json.dumps(device_info),
    #             qos=2
    #         )

    #         logger.info(f"已通过MQTT发布设备 {device_id} 的信息")
    #         return True
    #     except Exception as e:
    #         logger.error(f"通过MQTT发布设备信息时出错: {e}")
    #         return False



    # Publish device configuration to MQTT
    def publish_device_config_to_mqtt(self, device_id):
        """Publish device configuration to MQTT"""
        try:
            # Get device configuration from unified configuration manager
            # Since unified_config does not have a load_device_config function, we construct a basic configuration structure
            if not device_id:
                logger.warning(f"Device ID is empty, unable to publish configuration")
                return False

            # Build basic configuration structure
            full_config = {
                "system": {
                    "device_id": get_config("system.device_id", device_id, device_id=device_id),
                    "password": get_config("system.password", "", device_id=device_id),
                    "user_id": get_config("system.user_id", None, device_id=device_id),
                    "boot_time": get_config("system.boot_time", "", device_id=device_id),
                    "model": get_config("system.model", "raspberry_pi", device_id=device_id),
                    "version": get_config("system.version", "1.0.0", device_id=device_id),
                    "log_level": get_config("system.log_level", "DEBUG", device_id=device_id),
                    "status": get_config("system.status", "offline", device_id=device_id),
                    "last_update": get_config("system.last_update", None, device_id=device_id)
                },
                "wake_word": {
                    "enabled": get_config("wake_word.enabled", True, device_id=device_id)
                },
                "audio_settings": {
                    "general_volume": get_config("audio_settings.general_volume", 50, device_id=device_id),
                    "music_volume": get_config("audio_settings.music_volume", 50, device_id=device_id),
                    "notification_volume": get_config("audio_settings.notification_volume", 50, device_id=device_id)
                },
                "mqtt": {
                    "broker": get_config("mqtt.broker", "broker.emqx.io", device_id=device_id),
                    "port": get_config("mqtt.port", 1883, device_id=device_id),
                    "username": get_config("mqtt.username", None, device_id=device_id),
                    "password": get_config("mqtt.password", None, device_id=device_id),
                    "client_id_prefix": get_config("mqtt.client_id_prefix", "smart_assistant_87", device_id=device_id),
                    "topic_prefix": get_config("mqtt.topic_prefix", "smart0337187", device_id=device_id)
                }
            }

            # Build configuration topic
            config_topic = f"{self.config['topic_prefix']}/server/config/{device_id}"

            # Extract required parts from full configuration to match client format
            simplified_config = {}

            # Extract system part
            if "system" in full_config:
                simplified_config["system"] = {
                    "device_id": full_config["system"].get("device_id", ""),
                    "password": full_config["system"].get("password", ""),
                    "user_id": full_config["system"].get("user_id"),
                    "boot_time": full_config["system"].get("boot_time"),
                    "model": full_config["system"].get("model", "raspberry_pi"),
                    "version": full_config["system"].get("version", "1.0.0"),
                    "log_level": full_config["system"].get("log_level", "DEBUG"),
                    "status": full_config["system"].get("status", "offline"),
                    "last_update": full_config["system"].get("last_update")
                }

            # Extract wake_word part
            if "wake_word" in full_config:
                simplified_config["wake_word"] = {
                    "enabled": full_config["wake_word"].get("enabled", True)
                }

            # Extract audio_settings part
            if "audio_settings" in full_config:
                simplified_config["audio_settings"] = {
                    "general_volume": full_config["audio_settings"].get("general_volume", 50),
                    "music_volume": full_config["audio_settings"].get("music_volume", 50),
                    "notification_volume": full_config["audio_settings"].get("notification_volume", 50)
                }

            # Extract mqtt part
            if "mqtt" in full_config:
                simplified_config["mqtt"] = {
                    "broker": full_config["mqtt"].get("broker", "broker.emqx.io"),
                    "port": full_config["mqtt"].get("port", 1883),
                    "username": full_config["mqtt"].get("username"),
                    "password": full_config["mqtt"].get("password"),
                    "client_id_prefix": full_config["mqtt"].get("client_id_prefix", "smart_assistant_87"),
                    "topic_prefix": full_config["mqtt"].get("topic_prefix", "smart0337187")
                }

            # Prepare configuration data
            config_data = {
                'device_id': device_id,
                'config': simplified_config,
                'timestamp': time.time(),
                'source': 'server'
            }

            # Publish configuration
            self.mqtt_client.publish(
                config_topic,
                json.dumps(config_data),
                qos=2
            )

            logger.info(f"Device {device_id} configuration has been published via MQTT")
            return True
        except Exception as e:
            logger.error(f"Error occurred while publishing device configuration via MQTT: {e}")
            return False



    def _udp_listener(self):
        """UDP Listener Thread"""
        logger.info("UDP listener thread started")

        # Ensure the UDP socket is properly initialized
        if not self.udp_socket:
            logger.error("UDP socket is not initialized, unable to start listener thread")
            return

        # Set timeout to avoid infinite blocking
        self.udp_socket.settimeout(0.5)

        while self.running:
            try:
                # Receive UDP data
                data, addr = self.udp_socket.recvfrom(4096)

                # Parse header
                if len(data) < 6:
                    logger.warning(f"Received invalid UDP packet, length: {len(data)}")
                    continue

                seq_num = int.from_bytes(data[0:4], byteorder='big')
                data_len = int.from_bytes(data[4:6], byteorder='big')

                if len(data) < 6 + data_len:
                    logger.warning(f"Incomplete UDP packet, expected length: {6 + data_len}, actual length: {len(data)}")
                    continue

                # Extract encoded data
                encoded_data = data[6:6+data_len]

                # Process audio data
                self._process_audio_data(addr[0], seq_num, encoded_data)

                # Optional: Send response
                # self._send_audio_response(addr[0], seq_num)

            except socket.timeout:
                # Timeout, continue loop
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Error receiving UDP data: {e}")
                    # Short sleep to avoid high CPU usage
                    time.sleep(0.1)

        logger.debug("UDP listener thread ended")

    def _process_audio_data(self, client_ip, seq_num, encoded_data):
        """Process audio data"""
        # Find or create device
        device_id = self._get_or_create_device(client_ip)

        # Update device last activity time
        set_device_details(device_id, "last_seen", time.time())

        # Create or get device service
        service = self._get_or_create_device_service(device_id, client_ip)

        # Process audio data
        if service:
            service.handle_audio_data(seq_num, encoded_data)
        else:
            logger.warning(f"Unable to process audio data from device {device_id}, device service not found")

    def _get_or_create_device(self, client_ip):
        """Find or create a device"""
        # Search for the device in the unified configuration manager
        if os.path.exists("device_configs"):
            for device_dir in os.listdir("device_configs"):
                device_path = os.path.join("device_configs", device_dir)
                if os.path.isdir(device_path):
                    device_id = device_dir
                    device_details = get_device_details(device_id)
                    if device_details and device_details.get("ip") == client_ip:
                        logger.debug(f"Found device: {device_id}, IP: {client_ip}")
                        return device_id

        # If the device is not found, create a new device ID
        # Use the last segment of the IP address as the device ID
        device_id = f"device_{client_ip.split('.')[-1]}"
        logger.info(f"Device not found, creating new device ID: {device_id}, IP: {client_ip}")

        # Ensure the device configuration file exists
        self._ensure_device_config_exists(device_id)

        # Create device record in the unified configuration manager
        set_device_details(device_id, "ip", client_ip)
        set_device_details(device_id, "status", "online")
        set_device_details(device_id, "last_seen", time.time())
        set_device_details(device_id, "authenticated", True)
        set_device_details(device_id, "sid", None)
        set_device_details(device_id, "user_id", None)

        # Call device status change callback (if available)
        if self.on_device_status_changed:
            self.on_device_status_changed(device_id, "online", True)

        return device_id

    def _get_or_create_device_service(self, device_id, client_ip=None):
        """
        Get or create a device service

        Args:
            device_id: Device ID
            client_ip: Client IP address (optional, for logging purposes)
        """
        print(self.device_services)
        # Check if the device service exists
        if device_id in self.device_services:
            logger.debug(f"Found device service: {device_id}")
            return self.device_services[device_id]

        # Log the client IP (if provided)
        if client_ip:
            logger.debug(f"Creating service for device {device_id} (IP: {client_ip})")

            # Create device service callback function
            def server_callback(event_name, data):
                try:
                    # Send MQTT message
                    if self.is_connected:
                        topic = f"{self.config['topic_prefix']}/server/{event_name}/{device_id}"
                        self.mqtt_client.publish(topic, json.dumps(data))
                        return True
                    else:
                        logger.warning(f"MQTT not connected, unable to send message: {event_name}")
                        return False
                except Exception as e:
                    logger.error(f"Failed to send message: {e}")
                    return False

            # Create device service
            logger.info("Creating device service instance")
            try:
                service = DeviceService(device_id, server_callback)
                logger.info("Device service instance created successfully")
                self.device_services[device_id] = service

                # Create audio sender
                if client_ip:
                    self._create_audio_sender(device_id, client_ip)

                # Start the device service
                if not service.start():
                    logger.error("Failed to start device service, possibly due to STT processor initialization failure")
                    # Attempt to get more detailed error information
                    if hasattr(service, 'stt_processor') and service.stt_processor is None:
                        logger.error("STT processor initialization failed, please check Azure STT configuration")
                        logger.error("Please set the correct STT.azure.api_key and STT.azure.region in config/const_settings.json")
                    return None
            except Exception as e:
                logger.error(f"Error occurred while creating or starting device service: {e}")
                # Attempt to get more detailed error information
                if "SpeechConfig" in str(e) and "cannot construct" in str(e):
                    logger.error("Unable to construct Azure SpeechConfig, please check Azure STT configuration")
                    logger.error("Please set the correct STT.azure.api_key and STT.azure.region in config/const_settings.json")
                return None

            logger.info(f"Device service created and started for device {device_id}")

            print(self.device_services)
            # Note: The device configuration is no longer saved here to the unified configuration manager
            # The device configuration has been correctly created in _ensure_device_config_exists
            # Avoid configuration pollution and coverage issues

            logger.debug(f"设备 {device_id} 服务创建完成，配置文件已存在")

            # # 获取最新配置并发送给客户端
            # try:
            #     # 获取最新配置
            #     latest_config = service.get_config()

            #     if latest_config and self.is_connected:
            #         # 构建配置主题
            #         config_topic = f"{self.config['topic_prefix']}/server/config/{device_id}"

            #         # 确保配置中包含最新的时间戳
            #         if "system" not in latest_config:
            #             latest_config["system"] = {}
            #         latest_config["system"]["last_update"] = time.time()

            #         # 发布最新配置 - 使用与pi_client_optimized.py兼容的格式
            #         message = {
            #             "device_id": device_id,
            #             "config": latest_config,
            #             "timestamp": time.time(),
            #             "source": "server"  # 添加标记，表示这是服务器发送的消息
            #         }

            #         self.mqtt_client.publish(
            #             config_topic,
            #             json.dumps(message),
            #             qos=2
            #         )
            #         logger.info(f"已发送设备 {device_id} 的最新配置")
            # except Exception as e:
            #     logger.error(f"发送设备 {device_id} 的最新配置失败: {e}")

            return service

    def _create_audio_sender(self, device_id, client_ip):
        """Create audio sender

        Args:
            device_id: Device ID
            client_ip: Client IP address

        Returns:
            AudioSender: Created audio sender instance
        """
        try:
            # Create audio sender configuration
            sender_config = {
                "client_ip": client_ip,
                "client_udp_port": self.config["udp_response_port"],
                "audio_sample_rate": self.config["audio_sample_rate"],
                "audio_channels": self.config["audio_channels"],
                "audio_chunk_size": self.config["audio_chunk_size"],
                "use_raw_pcm": self.config["use_raw_pcm"],
                "debug": self.config["debug"]
            }

            # Create audio sender
            sender = AudioSender(sender_config)

            # Start audio sender
            sender.start()

            # Save to dictionary
            self.audio_senders[device_id] = sender

            logger.info(f"Audio sender created and started for device {device_id} (IP: {client_ip})")

            return sender

        except Exception as e:
            logger.error(f"Failed to create audio sender: {e}")
            return None

    def send_tts_audio(self, device_id, audio_data, use_raw_pcm=None):
        """Send TTS audio to device

        Args:
            device_id: Device ID
            audio_data: PCM audio data generated by TTS
            use_raw_pcm: Whether to use raw PCM transmission, determined by bytedanceTTS.py

        Returns:
            bool: Whether the audio was successfully sent
        """
        try:
            # Check if the device exists
            device_details = get_device_details(device_id)
            if not device_details:
                logger.warning(f"Device {device_id} does not exist, unable to send TTS audio")
                return False

            # Get device IP
            device_ip = device_details.get("ip")
            if not device_ip:
                logger.warning(f"Device {device_id} has no IP address, unable to send TTS audio")
                return False

            # Check if audio sender exists
            if device_id not in self.audio_senders:
                # Create audio sender
                sender = self._create_audio_sender(device_id, device_ip)
                if not sender:
                    logger.error(f"Unable to create audio sender for device {device_id}")
                    return False
            else:
                # Get existing audio sender
                sender = self.audio_senders[device_id]

            # Temporarily update sender configuration if use_raw_pcm parameter is provided
            original_setting = None
            if use_raw_pcm is not None:
                original_setting = sender.config["use_raw_pcm"]
                sender.config["use_raw_pcm"] = use_raw_pcm

            # Choose sending method based on PCM mode
            if use_raw_pcm is not None and use_raw_pcm and hasattr(sender, 'send_raw_pcm'):
                # Directly send raw PCM data
                success = sender.send_raw_pcm(audio_data)
            else:
                # Use queue (may involve Opus encoding)
                success = sender.send_tts_audio(audio_data)
                logger.debug("Audio data sent using queue_audio method")

            # Restore original settings (if temporarily changed)
            if original_setting is not None and original_setting != use_raw_pcm:
                sender.config["use_raw_pcm"] = original_setting

            if success:
                pass
            else:
                logger.warning(f"Failed to send TTS audio to device {device_id}")

            return success

        except Exception as e:
            logger.error(f"Error occurred while sending TTS audio: {e}")
            return False

    def _send_audio_response(self, client_ip, seq_num):
        """Send audio response to client"""
        if not self.udp_response_socket:
            return

        try:
            # Create response data
            response = seq_num.to_bytes(4, byteorder='big')

            # Send response
            self.udp_response_socket.sendto(response, (client_ip, self.config["udp_response_port"]))

            if seq_num % 100 == 0:
                logger.debug(f"Audio response sent to {client_ip}:{self.config['udp_response_port']}, sequence number: {seq_num}")

        except Exception as e:
            logger.error(f"Error occurred while sending UDP response: {e}")

    def _discovery_service(self):
        """Device discovery service thread"""
        logger.debug("Device discovery service thread started")

        try:
            # Create UDP socket
            discovery_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # Attempt to bind port
            try:
                discovery_socket.bind(('0.0.0.0', self.config["discovery_port"]))
                logger.debug(f"Device discovery service bound to port {self.config['discovery_port']}")
            except OSError as e:
                if e.errno == 10048:  # Port already in use
                    logger.warning(f"Discovery service port {self.config['discovery_port']} is already in use, attempting to use backup port")
                    # Attempt to use backup port
                    backup_port = self.config["discovery_port"] + 1
                    discovery_socket.bind(('0.0.0.0', backup_port))
                    # Update configuration with new port
                    self.config["discovery_port"] = backup_port
                    logger.info(f"Discovery service successfully bound to backup port {backup_port}")
                else:
                    raise

            # Set timeout to avoid blocking
            discovery_socket.settimeout(0.5)

            while self.running:
                try:
                    # Receive discovery request
                    data, addr = discovery_socket.recvfrom(1024)

                    if data == self.config["discovery_request"]:
                        logger.debug(f"Discovery request received from {addr[0]}")

                        # Send response
                        response = self.config["discovery_response_prefix"] + str(self.config["udp_port"]).encode()
                        discovery_socket.sendto(response, addr)

                        logger.debug(f"Discovery response sent to {addr[0]}")

                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        logger.error(f"Error occurred while processing discovery request: {e}")
                        time.sleep(0.1)

        except Exception as e:
            logger.error(f"Device discovery service error: {e}")
        finally:
            try:
                discovery_socket.close()
            except:
                pass

            logger.info("Device discovery service thread ended")

    def _session_monitor(self):
        """Session monitor thread - Clean up inactive device services"""
        logger.info("Session monitor thread started")

        while self.running:
            try:
                # Find inactive devices
                inactive_devices = []

                current_time = time.time()
                # Get all devices from unified configuration manager
                if os.path.exists("device_configs"):
                    for device_dir in os.listdir("device_configs"):
                        device_path = os.path.join("device_configs", device_dir)
                        if os.path.isdir(device_path):
                            device_id = device_dir
                            device_details = get_device_details(device_id)
                            if not device_details:
                                continue

                            # Special handling for certain devices, e.g., rasp1, exempt from session timeout
                            if device_id == "rasp1":
                                continue

                            # Check if the device has been inactive for a long time
                            last_seen = device_details.get("last_seen", 0)
                            if current_time - last_seen > self.config["session_timeout"]:
                                inactive_devices.append(device_id)

                # Clean up inactive devices
                for device_id in inactive_devices:
                    logger.info(f"Cleaning up inactive device: {device_id}")

                    # Stop device service
                    if device_id in self.device_services:
                        service = self.device_services[device_id]
                        service.stop()
                        del self.device_services[device_id]

                    # Stop audio sender
                    if device_id in self.audio_senders:
                        sender = self.audio_senders[device_id]
                        sender.stop()
                        del self.audio_senders[device_id]
                        logger.info(f"Audio sender for device {device_id} stopped and removed")

                    # Update device status to offline
                    set_device_details(device_id, "status", "offline")

                    # Call device status change callback (if available)
                    try:
                        if self.on_device_status_changed:
                            self.on_device_status_changed(device_id, "offline", False)
                    except Exception as e:
                        logger.error(f"Failed to call device status change callback: {e}")

                time.sleep(120.0)

            except Exception as e:
                logger.error(f"Session monitor thread error: {e}")
                time.sleep(1.0)

        logger.info("Session monitor thread ended")

    def send_command(self, device_id, command):
        """Send a command to the device"""
        if not self.is_connected:
            logger.warning("MQTT is not connected, unable to send command")
            return False

        try:
            # Build command topic
            command_topic = self.config["command_topic_template"].format(
                prefix=self.config["topic_prefix"],
                device_id=device_id
            )

            # Publish command
            result = self.mqtt_client.publish(
                command_topic,
                json.dumps(command),
                qos=2
            )

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"Command sent to device {device_id}: {command.get('type', 'unknown')}")
                return True
            else:
                logger.error(f"Failed to send command, error code: {result.rc}")
                return False

        except Exception as e:
            logger.error(f"Error occurred while sending command: {e}")
            return False

    def start_recording(self, device_id):
        """Send a start recording command to the device"""
        command = {"type": "record"}
        return self.send_command(device_id, command)

    def stop_recording(self, device_id):
        """Send a stop recording command to the device"""
        command = {"type": "stop_record"}
        return self.send_command(device_id, command)

    def play_audio(self, device_id, audio_data):
        """Send an audio playback command to the device"""
        # Encode audio data to Base64
        audio_base64 = base64.b64encode(audio_data).decode()

        command = {
            "type": "play",
            "data": audio_base64
        }

        return self.send_command(device_id, command)

    def set_server_info(self, device_id):
        """Send server information to the device"""
        # Get local IP address
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # No actual connection needed
            s.connect(('10.255.255.255', 1))
            server_ip = s.getsockname()[0]
        except Exception:
            server_ip = '127.0.0.1'
        finally:
            s.close()

        command = {
            "type": "set_server",
            "server_ip": server_ip,
            "server_port": self.config["udp_port"]
        }

        return self.send_command(device_id, command)

    def ping_device(self, device_id):
        """Send a ping command to the device"""
        command = {"type": "ping", "timestamp": time.time()}
        return self.send_command(device_id, command)

    def get_device_status(self, device_id):
        """Get the status of the device"""
        device_details = get_device_details(device_id)
        return device_details.copy() if device_details else None

    def get_all_devices(self):
        """Get all devices"""
        all_devices = {}
        if os.path.exists("device_configs"):
            for device_dir in os.listdir("device_configs"):
                device_path = os.path.join("device_configs", device_dir)
                if os.path.isdir(device_path):
                    device_id = device_dir
                    device_details = get_device_details(device_id)
                    if device_details:
                        all_devices[device_id] = device_details.copy()
        return all_devices

    def get_device_service(self, device_id):
        """Get the service of the device"""
        return self.device_services.get(device_id)

    def send_partial_config(self, device_id, config_key, new_value):
        """
        Send partial configuration updates to the device

        Args:
            device_id: Device ID
            config_key: Configuration key, e.g., "wake_word.enabled"
            new_value: New configuration value

        Returns:
            bool: Whether the update was successfully sent
        """
        try:
            if not self.is_connected:
                logger.warning(f"MQTT is not connected, unable to send configuration update: {config_key}")
                return False

            # Build configuration topic
            config_topic = f"{self.config['topic_prefix']}/server/config/{device_id}"

            # Build message
            message = {
                "device_id": device_id,
                "config": config_key,
                "new_value": new_value,
                "timestamp": time.time(),
                "source": "server"  # Add marker indicating the message is sent by the server
            }

            # Publish message
            self.mqtt_client.publish(
                config_topic,
                json.dumps(message),
                qos=2
            )

            logger.info(f"Partial configuration update sent via MQTT: {config_key} = {new_value} to device {device_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to send partial configuration update: {e}")
            return False

    def set_device_status_callback(self, callback):
        """Set the device status change callback"""
        self.on_device_status_changed = callback

    def set_device_config_callback(self, callback):
        """Set the device configuration change callback"""
        self.on_device_config_changed = callback

    def broadcast_server_info(self):
        """Broadcast server information for device discovery"""
        broadcast_socket = None
        try:
            # Create broadcast socket
            broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

            # Set timeout to avoid blocking
            broadcast_socket.settimeout(5.0)

            # Get local IP
            server_ip = '127.0.0.1'  # Default to local IP
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.settimeout(2.0)  # Set timeout
                try:
                    s.connect(('8.8.8.8', 80))
                    server_ip = s.getsockname()[0]
                    logger.debug(f"Server IP obtained: {server_ip}")
                except Exception as ip_error:
                    logger.warning(f"Unable to obtain external IP, using local IP: {str(ip_error)}")
                finally:
                    s.close()
            except Exception as socket_error:
                logger.error(f"Error occurred while creating temporary socket to obtain IP: {str(socket_error)}")

            # Create broadcast message
            message = {
                "server_ip": server_ip,
                "udp_port": self.config["udp_port"],
                "mqtt_broker": self.config["mqtt_broker"],
                "mqtt_port": self.config["mqtt_port"],
                "timestamp": time.time()
            }

            # Send broadcast
            discovery_port = self.config.get("discovery_port", 50000)
            logger.debug(f"Preparing to send broadcast to port: {discovery_port}")

            broadcast_socket.sendto(
                json.dumps(message).encode(),
                ('<broadcast>', discovery_port)
            )

            logger.info(f"Server information broadcasted: {message}")

        except socket.timeout as timeout_error:
            logger.error(f"Broadcast server information timeout: {str(timeout_error)}")
        except socket.error as socket_error:
            logger.error(f"Socket error occurred while broadcasting server information: {str(socket_error)}")
        except Exception as e:
            logger.error(f"Error occurred while broadcasting server information: {str(e)}")
            logger.exception("Detailed error information:")
        finally:
            if broadcast_socket:
                try:
                    broadcast_socket.close()
                    logger.debug("Broadcast socket closed")
                except Exception as close_error:
                    logger.error(f"Error occurred while closing broadcast socket: {str(close_error)}")

    def stop(self):
        """Stop the UDP device manager"""
        logger.info("Stopping UDP device manager...")

        # Set running flag to False
        self.running = False

        # Stop simple MQTT subscriber
        if hasattr(self, 'simple_mqtt_client') and self.simple_mqtt_client:
            try:
                self.simple_mqtt_client.loop_stop()
                self.simple_mqtt_client.disconnect()
                logger.info("Simple MQTT subscriber stopped")
            except Exception as e:
                logger.error(f"Error occurred while stopping simple MQTT subscriber: {e}")

        # Stop all audio senders
        for device_id, sender in list(self.audio_senders.items()):
            logger.info(f"Stopping audio sender for device {device_id}")
            sender.stop()

        # Stop all device services
        for device_id, service in list(self.device_services.items()):
            logger.info(f"Stopping service for device {device_id}")
            service.stop()

        # Wait for threads to finish
        if self.udp_thread and self.udp_thread.is_alive():
            self.udp_thread.join(timeout=2.0)

        if self.discovery_thread and self.discovery_thread.is_alive():
            self.discovery_thread.join(timeout=2.0)

        if self.session_monitor_thread and self.session_monitor_thread.is_alive():
            self.session_monitor_thread.join(timeout=2.0)

        # Close UDP sockets
        if self.udp_socket:
            try:
                self.udp_socket.close()
            except:
                pass

        if self.udp_response_socket:
            try:
                self.udp_response_socket.close()
            except:
                pass

        # Stop MQTT client
        if self.mqtt_client:
            try:
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
            except:
                pass

        logger.info("UDP device manager stopped")