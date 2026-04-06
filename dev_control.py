import paho.mqtt.client as mqtt
import time
import threading
import os
from threading import Event
from loguru import logger
from unified_config import unified_config

class MQTTDevClient:
    def __init__(self, broker="broker.emqx.io", port=1883,
                 username=None, password=None, client_id=None, device_id=None):
        # If no client ID is provided, generate a unique ID
        if client_id is None:
            client_id = f"smart_assistant_87_{int(time.time())}_{id(threading.current_thread())}"
        # Basic configuration parameters
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.client_id = client_id
        self.client = None

        # Device ID and configuration path
        self.device_id = device_id
        if device_id:
            # If a device ID is provided, use the device-specific configuration path
            self.config_path = os.path.join("device_configs", device_id, "new_settings.json")
            logger.info(f"MQTT client will use device-specific configuration: {self.config_path}")
        else:
            logger.warning(f"MQTT client startup failed")

        # Device state management
        self.devices = {}
        self.dev_status = {}  # Initialized from config
        self.dev_ack_received = {}
        self.is_connected = False
        self.load_devices_from_config()
        self.initialize()

        # Immediately check and clean up deleted devices after startup
        # threading.Timer(2.0, self._check_deleted_devices).start()

    def _check_deleted_devices(self):
        """Check and clean up deleted devices"""
        try:
            logger.info("Checking for deleted devices that need cleanup...")

            # Get the current list of devices in memory
            current_devices = set(self.devices.keys())
            config_devices = set()

            # Retrieve device configuration
            for category in ["lighting", "climate"]:
                category_devices = unified_config.get(f"devices.{category}", {}, device_id=self.device_id)
                for device_id in category_devices.keys():
                    config_devices.add(device_id)

            # Identify deleted devices
            deleted_devices = current_devices - config_devices
            if deleted_devices:
                logger.info(f"Found deleted devices: {', '.join(deleted_devices)}, cleaning up...")
                self.reload_devices_from_config()
            else:
                logger.info("No deleted devices found for cleanup")

            # Force reload regardless of whether devices were deleted, ensuring synchronization
            logger.info("Forcing device configuration reload to ensure synchronization...")
            self.reload_devices_from_config()
        except Exception as e:
            logger.error(f"Error while checking deleted devices: {e}")

    def get_mqtt_client(self):
        """
        Retrieve the MQTT client instance

        Returns:
            MQTTDevClient: Current MQTT client instance
        """
        # Ensure the client is initialized
        if self.client is None:
            self.initialize()
        return self

    def add_device(self, device_name, device_type=None, sub_topics=None, pub_topic=None, initial_status=None):
        """Add device configuration"""
        # Set default device type
        if device_type is None:
            device_type = "output"

        # Set default topics based on device type
        if pub_topic is None or sub_topics is None:
            base_topic = f"smart187/yumi_esp32s_{device_name}"
            if device_type == "input":
                # Input devices: subscribe to data topics, publish ACK topics
                if pub_topic is None:
                    pub_topic = f"{base_topic}/ack"  # Publish ACK to the device
                if sub_topics is None:
                    sub_topics = [f"{base_topic}/control"]  # Subscribe to the device's data topics
            else:
                # Output devices: publish control topics, subscribe to ACK topics
                if pub_topic is None:
                    pub_topic = f"{base_topic}/control"  # Publish control commands
                if sub_topics is None:
                    sub_topics = [f"{base_topic}/ack"]  # Subscribe to the device's ACK

        self.devices[device_name] = {
            "type": device_type,
            "sub_topic": sub_topics,
            "pub_topic": pub_topic
        }

        # If no initial status is provided, attempt to retrieve it from unified_config
        if initial_status is None:
            # Attempt to retrieve the status from device configuration
            devices_config = unified_config.get("devices", {}, device_id=self.device_id)
            for category in devices_config:
                if device_name in devices_config.get(category, {}):
                    initial_status = unified_config.get(f"devices.{category}.{device_name}.state", False, device_id=self.device_id)
                    # If the status is None, force set it to False and update the configuration
                    if initial_status is None:
                        initial_status = False
                        unified_config.set(f"devices.{category}.{device_name}.state", False, device_id=self.device_id)
                        logger.warning(f"Device {device_name} initial status was None, forced to False")
                    break
            else:
                # If not found in device configuration, set to default value False
                initial_status = False

        # Ensure initial_status is not None
        if initial_status is None:
            initial_status = False

        self.dev_status[device_name] = initial_status
        self.dev_ack_received[device_name] = Event()

    def initialize(self):
        """Initialize MQTT client and connection"""
        # Create client instance - using paho-mqtt 1.x
        self.client = mqtt.Client(self.client_id)
        logger.info(f"Initializing MQTT client {self.client_id}")

        # Set username and password (if provided)
        if self.username and self.password:
            self.client.username_pw_set(self.username, self.password)

        # Specify callback functions
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        self.client.on_publish = self.on_publish

        try:
            # Establish connection
            logger.info(f"Connecting to {self.broker}:{self.port}...")
            self.client.connect(self.broker, self.port, 60)

            # Start network loop
            self.client.loop_start()

            # Wait for connection to establish (maximum wait time: 5 seconds)
            import time
            connection_timeout = 5
            start_time = time.time()
            while not self.is_connected and (time.time() - start_time) < connection_timeout:
                time.sleep(0.1)

            if self.is_connected:
                logger.info(f"MQTT client {self.client_id} connected successfully")
            else:
                logger.warning(f"MQTT client {self.client_id} connection timed out, but will continue attempting in the background")

            # Start device status monitoring thread
            threading.Thread(target=self.monitor_dev_status, daemon=True).start()

            # Note: unified_config does not have a register_callback method; configuration change detection is implemented via polling in monitor_dev_status

            return True
        except Exception as e:
            logger.error(f"Failed to connect to MQTT server: {e}")
            return False

    # Deleted on_config_change method because unified_config does not have register_callback mechanism
    # Configuration change detection is now implemented through polling of monitor_dev_status method

    def on_connect(self, client, _userdata, _flags, rc):
        """Connection success callback"""
        self.is_connected = True
        logger.info(f"Connected to MQTT broker with result code {rc}")

        # Subscribe to all device topics
        for dev_name, dev_data in self.devices.items():
            for topic in dev_data['sub_topic']:
                client.subscribe(topic)
                logger.info(f"Subscribed to {topic}")

    def on_message(self, client, _userdata, msg):
        """Message received callback"""
        try:
            payload = msg.payload.decode()
            logger.info(f"Received message on {msg.topic}: {payload}")

            # Process received message
            for dev_name, dev_data in self.devices.items():
                if msg.topic in dev_data['sub_topic']:
                    # If it is an acknowledgment message (ACK)
                    if msg.topic.endswith('ack'):
                        # Process synchronization message
                        if payload.startswith('sync'):
                            sync_value = payload.split(":")[1]
                            if sync_value in ["True", "False"]:
                                sync_value = sync_value == "True"

                            # Update device status
                            # Find the category the device belongs to
                            device_updated = False
                            for category in ["lighting", "climate"]:
                                # Check if the device exists in this category
                                if unified_config.get(f"devices.{category}.{dev_name}", None, device_id=self.device_id) is not None:
                                    # Update device status using unified_config
                                    unified_config.set(f"devices.{category}.{dev_name}.state", sync_value, device_id=self.device_id)
                                    logger.info(f"Synced status of {dev_name} to {sync_value}")
                                    device_updated = True
                                    break

                            if not device_updated:
                                logger.warning(f"Device {dev_name} not found in any category for sync update")
                        else:
                            # Mark acknowledgment received
                            self.dev_ack_received[dev_name].set()
                            logger.info(f"ACK received from {dev_name}")
                    # Input device message processing
                    else:
                        sensor_value = payload
                        # Update device status
                        # Find the category the device belongs to
                        device_updated = False
                        input_device_category = None
                        for category in ["lighting", "climate"]:
                            # Check if the device exists in this category
                            if unified_config.get(f"devices.{category}.{dev_name}", None, device_id=self.device_id) is not None:
                                # Update device status using unified_config
                                unified_config.set(f"devices.{category}.{dev_name}.state", sensor_value, device_id=self.device_id)
                                device_updated = True
                                input_device_category = category
                                logger.info(f"Updated input device {dev_name} state to {sensor_value}")
                                break

                        if not device_updated:
                            logger.warning(f"Device {dev_name} not found in any category for sensor update")
                        else:
                            # Process connected_outputs synchronization
                            self._sync_connected_outputs(dev_name, input_device_category, sensor_value)

                        # Send acknowledgment
                        if dev_data.get('pub_topic'):
                            self.client.publish(dev_data['pub_topic'], f"ACK:{sensor_value}")
                            logger.info(f"Published ACK:{sensor_value} to {dev_data['pub_topic']}")
                    break
        except Exception as e:
            logger.error(f"Error processing message: {e}")

    def _sync_connected_outputs(self, input_device_name, input_device_category, sensor_value):
        """
        Synchronize the connected outputs of an input device.

        Args:
            input_device_name: Name of the input device.
            input_device_category: Category of the input device.
            sensor_value: Sensor value.
        """
        try:
            # Retrieve the connected outputs configuration for the input device
            connected_outputs = unified_config.get(
                f"devices.{input_device_category}.{input_device_name}.connected_outputs",
                [],
                device_id=self.device_id
            )

            if not connected_outputs:
                logger.debug(f"Input device {input_device_name} has no connected outputs")
                return

            # Requirements:
            # - If target_state is true: output device state matches input device state.
            # - If target_state is false: output device state is opposite to input device state.
            # Synchronization occurs only when the input device state changes.

            # Convert sensor value to a boolean
            if isinstance(sensor_value, str):
                if sensor_value.lower() in ['true', '1', 'on', 'yes']:
                    input_state = True
                elif sensor_value.lower() in ['false', '0', 'off', 'no']:
                    input_state = False
                else:
                    # For other string values, such as "No rain", determine based on specific cases
                    input_state = sensor_value not in ['No rain', 'Dry', 'Off', 'Closed']
            else:
                input_state = bool(sensor_value)

            logger.info(f"Input device {input_device_name} state changed to {sensor_value} (bool: {input_state}), syncing {len(connected_outputs)} connected outputs")

            # Synchronize all connected output devices
            for output_device in connected_outputs:
                output_type = output_device.get('type')
                output_id = output_device.get('id')
                target_state_when_true = output_device.get('target_state', True)  # Default to True for backward compatibility

                if not output_type or not output_id:
                    logger.warning(f"Invalid connected output device: {output_device}")
                    continue

                # Calculate the actual target state based on input state and target_state configuration
                if target_state_when_true:
                    # If target_state is true, output device state matches input device state
                    target_output_state = input_state
                else:
                    # If target_state is false, output device state is opposite to input device state
                    target_output_state = not input_state

                logger.info(f"Syncing output {output_type}.{output_id}: input={input_state}, target_state={target_state_when_true}, final_target={target_output_state} ({'same' if target_state_when_true else 'opposite'} as input)")

                # Check if the output device exists
                output_device_config = unified_config.get(
                    f"devices.{output_type}.{output_id}",
                    None,
                    device_id=self.device_id
                )

                if output_device_config is None:
                    logger.warning(f"Connected output device {output_type}.{output_id} not found in config")
                    continue

                # Retrieve the current state of the output device
                current_output_state = unified_config.get(
                    f"devices.{output_type}.{output_id}.state",
                    False,
                    device_id=self.device_id
                )

                # Update the state if it needs to change
                if current_output_state != target_output_state:
                    # Update the state in the configuration
                    unified_config.set(
                        f"devices.{output_type}.{output_id}.state",
                        target_output_state,
                        device_id=self.device_id
                    )

                    logger.info(f"Synced connected output {output_type}.{output_id} from {current_output_state} to {target_output_state}")

                    # Send MQTT command to the output device (whether or not it is in the current client)
                    if output_id in self.devices and self.devices[output_id]['type'] == 'output':
                        pub_topic = self.devices[output_id].get('pub_topic')
                        if pub_topic:
                            # Send control command using string format of boolean value
                            command_value = "True" if target_output_state else "False"
                            self.client.publish(pub_topic, command_value, retain=True)
                            logger.info(f"Published control command {command_value} to {pub_topic} for synced output {output_id}")
                        else:
                            logger.warning(f"No pub_topic found for output device {output_id}")
                    else:
                        logger.warning(f"Output device {output_id} not found in MQTT client devices or not an output device")
                else:
                    logger.debug(f"Connected output {output_type}.{output_id} already at target state {target_output_state}")

        except Exception as e:
            logger.error(f"Error syncing connected outputs for {input_device_name}: {e}")

    def publish(self, device_name, message, qos=1, retain=False, callback=None):
        """
        Publish a message to the specified device topic.

        Args:
            device_name: Name of the device.
            message: Message to be sent.
            qos: QoS level.
            retain: Whether to retain the message.
            callback: Callback function after publishing, receives success status as a parameter.

        Returns:
            bool: Whether the message was successfully published.
        """
        if not self.client or not self.is_connected:
            logger.error("Client not initialized or not connected")
            if callback:
                callback(False)
            return False

        if device_name not in self.devices:
            logger.error(f"Unknown device: {device_name}")
            if callback:
                callback(False)
            return False

        pub_topic = self.devices[device_name].get('pub_topic')
        if not pub_topic:
            logger.error(f"No publish topic configured for {device_name}")
            if callback:
                callback(False)
            return False

        # Record the current device state for later verification of successful update
        current_device_state = None

        # Find the category of the device
        for category in ["lighting", "climate"]:
            if unified_config.get(f"devices.{category}.{device_name}", None, device_id=self.device_id) is not None:
                current_device_state = unified_config.get(f"devices.{category}.{device_name}.state", False, device_id=self.device_id)
                break

        # Publish the message
        result = self.client.publish(pub_topic, payload=message, qos=qos, retain=retain)
        success = result.is_published()

        if success:
            logger.info(f"Message published to {pub_topic}: {message}")

            # If the message is a boolean state switch command ("True" or "False"), set a timer to check if the state was actually updated
            if message in ["True", "False"]:
                expected_state = message == "True"

                # Define the check function
                def check_state_update():
                    updated_state = None

                    # Find the category of the device
                    for category in ["lighting", "climate"]:
                        if unified_config.get(f"devices.{category}.{device_name}", None, device_id=self.device_id) is not None:
                            updated_state = unified_config.get(f"devices.{category}.{device_name}.state", None, device_id=self.device_id)
                            break

                    # Check if the state has been updated to the expected value
                    if updated_state == expected_state:
                        logger.info(f"Device {device_name} state successfully updated to {expected_state}")
                        if callback:
                            callback(True)
                    else:
                        logger.warning(f"Device {device_name} state update failed, expected: {expected_state}, actual: {updated_state}")
                        if callback:
                            callback(False)

                # Start a timer to check the state after 5 seconds
                threading.Timer(5.0, check_state_update).start()
            elif callback:
                callback(True)
        else:
            logger.error(f"Failed to publish message to {pub_topic}")
            if callback:
                callback(False)

        return success

    def monitor_dev_status(self):
        """
        Monitor device status changes and handle them.
        """
        # Initialize local device status records
        local_dev_status = {}

        # Initialize device statuses
        for dev_name in self.devices:
            # Attempt to retrieve the status from the device configuration
            device_found = False
            for category in ["lighting", "climate"]:  # Device categories
                # First check if the device exists in this category
                device_exists = unified_config.get(f"devices.{category}.{dev_name}", None, device_id=self.device_id)
                if device_exists is not None:
                    device_found = True
                    # Retrieve the device status
                    device_state = unified_config.get(f"devices.{category}.{dev_name}.state", False, device_id=self.device_id)
                    # If the status is None, force it to False and update the configuration
                    if device_state is None:
                        device_state = False
                        unified_config.set(f"devices.{category}.{dev_name}.state", False, device_id=self.device_id)
                        logger.warning(f"Device {dev_name} status was None during monitoring initialization, forced to False")
                    local_dev_status[dev_name] = device_state
                    break

            if not device_found:
                # If not found in the device configuration, use the current status
                local_dev_status[dev_name] = self.dev_status.get(dev_name, False)

        while True:
            # Create a copy of the current device list to avoid dictionary modification during iteration
            current_devices = dict(self.devices)

            # Clean up statuses of deleted devices from local_dev_status
            devices_to_remove = []
            for dev_name in local_dev_status:
                if dev_name not in current_devices:
                    devices_to_remove.append(dev_name)

            for dev_name in devices_to_remove:
                del local_dev_status[dev_name]
                logger.debug(f"Removed deleted device from local_dev_status: {dev_name}")

            for dev_name, dev_data in current_devices.items():
                if dev_data['type'] == 'output':
                    # Attempt to retrieve the current status from the device configuration
                    current_status = None
                    device_found_in_config = False

                    # Check each device category
                    for category in ["lighting", "climate"]:
                        # First check if the device exists in this category
                        device_exists = unified_config.get(f"devices.{category}.{dev_name}", None, device_id=self.device_id)
                        if device_exists is not None:
                            device_found_in_config = True
                            # Retrieve the device status
                            state_value = unified_config.get(f"devices.{category}.{dev_name}.state", False, device_id=self.device_id)
                            # logger.debug(f"Device {dev_name} status read from config: {state_value} (category: {category})")
                            # If the status is None or null, force it to False
                            if state_value is None:
                                state_value = False
                                # Immediately update the configuration to ensure no None values exist in the config file
                                unified_config.set(f"devices.{category}.{dev_name}.state", False, device_id=self.device_id)
                                logger.warning(f"Device {dev_name} status was None, forced to False")
                            current_status = bool(state_value)  # Ensure it is a boolean value
                            break

                    # Skip monitoring if the device is not in the configuration file (to avoid rewriting deleted devices)
                    if not device_found_in_config:
                        logger.debug(f"Device {dev_name} not in configuration file, skipping monitoring")
                        continue

                    # Ensure current_status is not None
                    if current_status is None:
                        current_status = bool(self.dev_status.get(dev_name, False))

                    # Check if the status has changed
                    if current_status != local_dev_status.get(dev_name):
                        logger.info(f"Device {dev_name} status change detected: {local_dev_status.get(dev_name)} -> {current_status}")
                        # Record the previous status for rollback
                        previous_status = local_dev_status.get(dev_name)

                        # Publish the new status
                        if dev_data.get('pub_topic'):
                            self.client.publish(dev_data['pub_topic'], str(current_status), retain=True)
                            logger.info(f"Published {current_status} to {dev_data['pub_topic']}")

                            # Wait for device response or timeout
                            if not self.dev_ack_received[dev_name].wait(5):
                                logger.warning(f"No ACK received from {dev_name}, resetting status")
                                # If no acknowledgment is received, rollback the status to the previous state
                                logger.warning(f"Device {dev_name} unresponsive, rolling back status from {current_status} to {previous_status}")

                                # Rollback the status in the configuration
                                for category in ["lighting", "climate"]:
                                    if unified_config.get(f"devices.{category}.{dev_name}", None, device_id=self.device_id) is not None:
                                        unified_config.set(f"devices.{category}.{dev_name}.state", previous_status, device_id=self.device_id)
                                        logger.info(f"Rolled back device {dev_name} status to {previous_status}")
                                        break

                                # Update the local status record to the rolled-back status
                                local_dev_status[dev_name] = previous_status
                            else:
                                # Confirm the status change and update the local record
                                local_dev_status[dev_name] = current_status
                                self.dev_ack_received[dev_name].clear()
            time.sleep(1)

    def on_publish(self, _client, _userdata, mid):
        """
        Callback for message publishing completion.

        Args:
            _client: MQTT client instance.
            _userdata: User data passed to the callback.
            mid: Message ID of the published message.
        """
        logger.debug(f"Message ID {mid} has been published")

    def on_disconnect(self, _client, _userdata, rc):
        """
        Callback for MQTT client disconnection.

        Args:
            _client: MQTT client instance.
            _userdata: User data passed to the callback.
            rc: Result code indicating the reason for disconnection.
        """
        self.is_connected = False
        logger.info(f"Disconnected with result code {rc}")

    def disconnect(self):
        """
        Disconnect the MQTT client.
        """
        if self.client and self.is_connected:
            self.client.disconnect()
            self.client.loop_stop()
            logger.info("MQTT client disconnected")

    def reload_devices_from_config(self):
        """
        Reload device configurations to dynamically add new devices and remove deleted devices.
        """
        # Get the current list of devices to check for new and deleted devices
        current_devices = set(self.devices.keys())
        config_devices = set()  # Will store all device IDs from the configuration file

        # Log the configuration file being used
        logger.debug(f"Reloading device configurations: {self.config_path}")

        # Iterate through all device categories
        for category in ["lighting", "climate"]:
            category_devices = unified_config.get(f"devices.{category}", {}, device_id=self.device_id)
            if not category_devices:
                continue

            for device_id, device_info in category_devices.items():
                # Add to the set of configuration devices
                config_devices.add(device_id)

                # Skip if the device already exists
                if device_id in self.devices:
                    continue

                # Retrieve device information
                device_state = device_info.get("state", False)
                # If the state is None, force it to False and update the configuration
                if device_state is None:
                    device_state = False
                    unified_config.set(f"devices.{category}.{device_id}.state", False, device_id=self.device_id)
                    logger.warning(f"Device {device_id} had a None state during reload, forced to False")
                device_type = device_info.get("control_type", "output")
                mqtt_topic = device_info.get("mqtt_topic", f"smart187/yumi_esp32s_{device_id}/control")

                # Construct MQTT topics based on device type
                if device_type == "input":
                    # Input devices: subscribe to data topics, publish ACK topics
                    pub_topic = f"{mqtt_topic.rsplit('/', 1)[0]}/ack"  # Publish ACK to the device
                    sub_topics = [mqtt_topic]  # Subscribe to the device's data topic
                else:
                    # Output devices: publish control topics, subscribe to ACK topics
                    pub_topic = mqtt_topic  # Publish control commands
                    sub_topics = [f"{mqtt_topic.rsplit('/', 1)[0]}/ack"]  # Subscribe to the device's ACK

                # Add the device
                self.add_device(
                    device_name=device_id,
                    device_type=device_type,
                    sub_topics=sub_topics,
                    pub_topic=pub_topic,
                    initial_status=device_state
                )

                # If connected, subscribe to the new device's topics
                if self.is_connected and self.client:
                    for topic in sub_topics:
                        self.client.subscribe(topic)
                        logger.info(f"Subscribed to {topic} for new device {device_id}")

                logger.info(f"Added new device from config: {device_id} ({device_type}) with status {device_state}")

        # Check for newly added devices
        new_devices = config_devices - current_devices
        if new_devices:
            logger.info(f"Added {len(new_devices)} new devices: {', '.join(new_devices)}")

        # Check for deleted devices
        deleted_devices = current_devices - config_devices
        if deleted_devices:
            for device_id in deleted_devices:
                # Unsubscribe from topics
                if self.is_connected and self.client:
                    for topic in self.devices[device_id].get('sub_topic', []):
                        self.client.unsubscribe(topic)
                        logger.info(f"Unsubscribed from {topic} for deleted device {device_id}")

                # Remove from the device list
                del self.devices[device_id]
                if device_id in self.dev_status:
                    del self.dev_status[device_id]
                if device_id in self.dev_ack_received:
                    del self.dev_ack_received[device_id]

                logger.info(f"Removed deleted device: {device_id}")

            logger.info(f"Removed {len(deleted_devices)} deleted devices: {', '.join(deleted_devices)}")

        if not new_devices and not deleted_devices:
            logger.info("No devices were added or removed")

    def load_devices_from_config(self):
        """
        Load device configurations from the config file.
        """
        # Log the configuration file being used
        logger.debug(f"Loading devices from config: {self.config_path}")

        # Iterate through all device categories
        for category in ["lighting", "climate"]:
            category_devices = unified_config.get(f"devices.{category}", {}, device_id=self.device_id)
            if not category_devices:
                continue

            for device_id, device_info in category_devices.items():
                # Retrieve device information
                device_state = device_info.get("state", False)
                # If the state is None, force it to False and update the configuration
                if device_state is None:
                    device_state = False
                    unified_config.set(f"devices.{category}.{device_id}.state", False, device_id=self.device_id)
                    logger.warning(f"Device {device_id} had a None state during load, forced to False")
                device_type = device_info.get("control_type", "output")
                mqtt_topic = device_info.get("mqtt_topic", f"smart187/yumi_esp32s_{device_id}/control")

                # Construct MQTT topics based on device type
                if device_type == "input":
                    # Input devices: subscribe to data topics, publish ACK topics
                    pub_topic = f"{mqtt_topic.rsplit('/', 1)[0]}/ack"  # Publish ACK to the device
                    sub_topics = [mqtt_topic]  # Subscribe to the device's data topic
                else:
                    # Output devices: publish control topics, subscribe to ACK topics
                    pub_topic = mqtt_topic  # Publish control commands
                    sub_topics = [f"{mqtt_topic.rsplit('/', 1)[0]}/ack"]  # Subscribe to the device's ACK

                # Add the device
                self.add_device(
                    device_name=device_id,
                    device_type=device_type,
                    sub_topics=sub_topics,
                    pub_topic=pub_topic,
                    initial_status=device_state
                )

                logger.info(f"Loaded device from config: {device_id} ({device_type}) with status {device_state}")


# Factory function to create an MQTT client instance

def create_mqtt_client(broker="broker.emqx.io", port=1883, username=None, password=None, client_id=None, device_id=None):
    """
    Create a new MQTT client instance.

    Args:
        broker: Address of the MQTT broker.
        port: Port of the MQTT broker.
        username: MQTT username.
        password: MQTT password.
        client_id: MQTT client ID.
        device_id: Device ID to determine which configuration file to use.

    Returns:
        MQTTDevClient: Newly created MQTT client instance.
    """
    # Generate a unique client ID if not provided
    if client_id is None:
        client_id = f"smart_assistant_87_{int(time.time())}_{id(threading.current_thread())}"
    return MQTTDevClient(broker=broker, port=port,
                        username=username, password=password,
                        client_id=client_id, device_id=device_id)


# Example usage
if __name__ == "__main__":
    # Create an MQTT client
    mqtt_client = create_mqtt_client(
        broker="broker.emqx.io",
        port=1883,
        # username="emqx_user",  # Uncomment if authentication is required
        # password="emqx_password",
        device_id="test_device"  # Specify the device ID to use device-specific configurations
    )

    # Manually add a device (if not in the configuration)
    mqtt_client.add_device(
        device_name="light",
        device_type="output",
        sub_topics=["light/ack"],
        pub_topic="light/control",
        initial_status=False
    )

    # Example of sending a message
    mqtt_client.publish("light", "ON")

    # Or control a device from the configuration
    if "main_room_light" in mqtt_client.devices:
        mqtt_client.publish("main_room_light", "ON")

    # Keep the program running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Program terminated by user")
        mqtt_client.disconnect()