import device_model
from loguru import logger
from unified_config import unified_config

class DeviceControlHandler:
    def __init__(self, device_id=None):
        """
        Initialise device control processor

        Args:
            device_id: Device ID, used to obtain device-specific configuration
        """
        self.device_id = device_id

    def check_device_query(self, query: str) -> tuple[str, bool]:
        """
        Check if the query is requesting device control and perform the action if needed

        This function detects if a user query is requesting to control devices
        by checking for exact matches with predefined patterns in both Chinese and English.

        Args:
            query: User's query text

        Returns:
            tuple: (Response message from device control, Boolean indicating if query was handled)
        """
        # Remove leading/trailing spaces and convert to lowercase for comparison
        clean_query = query.strip().lower()

        # Define exact phrases for device control (both Chinese and English)
        device_control_patterns = {
            'chinese': [
                '打开灯', '关闭灯', '开灯', '关灯',
                '打开风扇', '关闭风扇', '开风扇', '关风扇',
                '打开电视', '关闭电视', '开电视', '关电视',
                '打开空调', '关闭空调', '开空调', '关空调',
                '调高音量', '调低音量', '音量调高', '音量调低',
                '打开电灯', '关闭电灯', '开电灯', '关电灯',
                '把灯打开', '把灯关上', '把灯关闭', '把灯打开',
                '帮我开灯', '帮我关灯', '请开灯', '请关灯',
                '帮我开风扇', '帮我关风扇', '请开风扇', '请关风扇',
                '帮我开灯和风扇', '帮我关灯和风扇',
                '打开设备', '关闭设备', '控制设备', '设备状态'
            ],
            'english': [
                'turn on the light', 'turn off the light', 'switch on the light', 'switch off the light',
                'turn on the fan', 'turn off the fan', 'switch on the fan', 'switch off the fan',
                'turn on the ac', 'turn off the ac', 'switch on the ac', 'switch off the ac',
                'increase the volume', 'decrease the volume', 'turn up the volume', 'turn down the volume',
                'turn the lights on', 'turn the lights off', 'switch the lights on', 'switch the lights off',
                'help me turn on the light', 'help me turn off the light', 'please turn on the light', 'please turn off the light',
                'help me turn on the fan', 'help me turn off the fan', 'please turn on the fan', 'please turn off the fan',
                'control devices', 'device status', 'show device status', 'list devices'
            ]
        }

        # Detect language and get appropriate patterns
        has_chinese = any('\u4e00' <= char <= '\u9fff' for char in clean_query)
        patterns = device_control_patterns['chinese'] if has_chinese else device_control_patterns['english']

        # Check if query exactly matches any of the patterns
        for pattern in patterns:
            if clean_query == pattern.lower():
                try:
                    # Process device control via device_model
                    response = device_model.create_device_json(query, device_id=self.device_id)
                    return self.process_device_response(response), True
                except Exception as e:
                    error_msg = f"Error processing device control request: {str(e)}" if not has_chinese else f"处理设备控制请求时出错：{str(e)}"
                    logger.error(f"Error in device control: {str(e)}")
                    return error_msg, True

        # Not a device control query
        return "", False

    def process_device_response(self, response: str) -> str:
        """
        Process device control response from the model - handles multiple JSON objects

        Args:
            response: JSON response from device_model, may contain multiple commands

        Returns:
            str: Formatted response message for user
        """
        try:
            responses = []

            # Parse JSON response
            import json
            import re

            # Handle string input - this could contain multiple JSON objects
            if isinstance(response, str):
                # Parse all JSON objects in the response
                json_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
                all_json_matches = re.findall(json_pattern, response)

                if all_json_matches:
                    # Process each JSON match
                    for json_match in all_json_matches:
                        try:
                            # Check and fix JSON format
                            json_str = json_match.strip()
                            if not json_str.startswith('{'):
                                json_str = '{' + json_str
                            if not json_str.endswith('}'):
                                json_str = json_str + '}'

                            json_obj = json.loads(json_str)
                            responses.append(json_obj)
                        except json.JSONDecodeError as e:
                            logger.error(f"Error parsing JSON match: {e}")
                            continue
                else:
                    # Try to parse the entire string as a single JSON object
                    try:
                        json_obj = json.loads(response)
                        responses.append(json_obj)
                    except json.JSONDecodeError:
                        return "Invalid JSON format"
            else:
                # If it's already a dict, just use it
                responses.append(response)

            # Execute all operations, but only return the result from the last one
            last_response = None
            last_addition = None

            for i, response_json in enumerate(responses):
                # Check if it's a device control
                if response_json.get("type") != "device control":
                    continue

                # Get parameters
                parameters = response_json.get("parameters", {})
                device = parameters.get("device")
                action = parameters.get("action")
                addition = parameters.get("addition", "")

                # Store addition for the last operation
                if i == len(responses) - 1:
                    last_addition = addition

                # If device is null, no matching device was found
                if device == "null" or not device:
                    last_response = "Sorry, I couldn't find the device you want to control." if not any('\u4e00' <= char <= '\u9fff' for char in str(response_json)) else "对不起，我找不到您想控制的设备。"
                    continue

                # Apply device control
                try:
                    # Prepare the command in the required format
                    commands = [{"device": device, "action": action}]

                    # Convert values in commands according to parameter types
                    commands = self.convert_command_values(commands)

                    # Execute the commands
                    self.execute_commands(commands)

                    # Store the result, but continue processing if there are more
                    last_response = f"Device controlled: {device}" if not any('\u4e00' <= char <= '\u9fff' for char in str(response_json)) else f"已控制设备: {device}"
                except Exception as e:
                    logger.error(f"Device control error: {str(e)}")
                    last_response = f"Error controlling device: {str(e)}" if not any('\u4e00' <= char <= '\u9fff' for char in str(response_json)) else f"设备控制出错：{str(e)}"

            # Return the addition from the last operation if available
            if last_addition:
                return last_addition

            # Otherwise return the last operational result
            if last_response:
                return last_response

            # Fallback if no valid operations were found
            return "Device control operation completed" if not any('\u4e00' <= char <= '\u9fff' for char in str(response)) else "设备控制操作已完成"

        except Exception as e:
            logger.error(f"Error processing device response: {str(e)}")
            return f"Error processing device response: {str(e)}"

    def convert_command_values(self, commands):
        """
        Convert value types according to device data_type to avoid "False" becoming a string

        Args:
            commands: List of device control commands

        Returns:
            list: Commands with proper value types
        """
        for cmd in commands:
            device_id = cmd.get("device")
            action = cmd.get("action")  # action may be a bool value

            # Find the device in the devices configuration
            device_info = self.find_device_by_id(device_id)

            if device_info:
                # Get the data type from the device configuration
                expected_type = device_info.get("data_type", "bool")
                cmd["action"] = self.convert_value_type(action, expected_type)  # Convert type

        return commands

    def find_device_by_id(self, device_id):
        """
        Find a device by its ID in the devices configuration

        Args:
            device_id: The device ID to find

        Returns:
            dict: The device configuration, or None if not found
        """
        # Search through all device categories
        devices_config = unified_config.get("devices", {}, device_id=self.device_id)
        for category in devices_config:
            category_devices = devices_config.get(category, {})
            if device_id in category_devices:
                return category_devices[device_id]

        return None

    def convert_value_type(self, value, expected_type):
        """
        Convert data type according to parameter format

        Args:
            value: The value to convert
            expected_type: Target data type

        Returns:
            The value converted to the expected type
        """
        if expected_type == "bool":
            if isinstance(value, str):
                return value.lower() == "true"  # "True" → True, "False" → False
            return bool(value)
        elif expected_type == "int":
            return int(value)
        elif expected_type == "float":
            return float(value)
        elif expected_type == "string":
            return str(value)
        return value  # Return original value by default

    def execute_commands(self, commands):
        """
        Execute control commands sequentially

        Args:
            commands: List of device control commands
        """
        logger.debug(f"Executing control commands: {commands}")
        for cmd in commands:
            device_id = cmd.get("device")
            action = cmd.get("action")

            if not device_id or action is None:  # Check if action exists, including False
                logger.warning(f"⚠️ Invalid command: {cmd}")
                continue

            # Find the device in the configuration
            device_info = self.find_device_by_id(device_id)
            if not device_info:
                logger.warning(f"⚠️ Device not found: {device_id}")
                continue

            # Find the category of the device
            device_category = self.find_device_category(device_id)
            if not device_category:
                logger.warning(f"⚠️ Device category not found for: {device_id}")
                continue

            # Execute the actual device control
            logger.debug(f"Setting device state: {device_category}.{device_id} = {action}")
            unified_config.set(f"devices.{device_category}.{device_id}.state", action, device_id=self.device_id)
            # self.chat_saver.save_chat_history(f"[System] device control: {device_id} = {action}")

    def find_device_category(self, device_id):
        """
        Find the category of a device by its ID

        Args:
            device_id: The device ID to find

        Returns:
            str: The device category, or None if not found
        """
        devices_config = unified_config.get("devices", {}, device_id=self.device_id)
        for category in devices_config:
            category_devices = devices_config.get(category, {})
            if device_id in category_devices:
                return category

        return None

if __name__ == '__main__':
    # Example usage
    device_handler = DeviceControlHandler()
    query = "帮我开灯"
    response, handled = device_handler.check_device_query(query)
    if handled:
        print(f"Response: {response}")
    else:
        print("Not a device control query.")