import json
import os
import datetime
from loguru import logger
from pathlib import Path
import re
from chat_saver import ChatSaver
from unified_config import get_config

chat_saver = ChatSaver()

class ScheduleHandler:
    def __init__(self, user_id=None, device_id=None):
        """
        Initialize schedule handler

        Args:
            user_id: User ID, if None, retrieve from unified_config
            device_id: Device ID, if None, retrieve from unified_config
        """
        # Retrieve device ID, raise error if not provided
        if device_id is None:
            raise ValueError("ScheduleHandler requires the device_id parameter")

        self.device_id = device_id
        self.user_id = user_id if user_id is not None else get_config("system.user_id", None, device_id=self.device_id)

        # Ensure user_id is not None, use default value if None
        self.user_id = self.user_id if self.user_id is not None else "default_user_id"

        # Initialize the chat saver and pass the device id
        self.chat_saver = ChatSaver(device_id=self.device_id)

    # Add new time parsing function
    def parse_time_string(self, time_str):
        """Parse time string in format '2025-04-01 10:00:00'"""
        try:
            # Directly use datetime to parse standard format
            target_dt = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            return target_dt
        except Exception as e:
            logger.error(f"Error parsing time format: {e}")
            logger.error(f"Input time string: {time_str}")
            logger.error(f"Expected format: YYYY-MM-DD HH:MM:SS")
            return None

    # 获取日程目录路径
    def get_schedule_dir(self):
        """
        Retrieve schedule directory path specific to user device

        Returns:
            str: Schedule directory path
        """
        if self.user_id and self.device_id:
            # Use user device-specific directory
            return os.path.join("user", self.user_id, self.device_id, "schedule")
        else:
            # Use global directory (backward compatibility)
            return "schedule"

    # 获取日程数据文件路径
    def get_schedule_data_path(self):
        """
        Retrieve schedule data file path specific to user device

        Returns:
            str: Schedule data file path
        """
        return os.path.join(self.get_schedule_dir(), "schedule.data")

    # 获取日程日志文件路径
    def get_schedule_log_path(self):
        """
        Retrieve schedule log file path specific to user device

        Returns:
            str: Schedule log file path
        """
        return os.path.join(self.get_schedule_dir(), "log.txt")

    # Ensure directory exists
    def ensure_dir_exists(self, dir_path):
        """
        Ensure directory exists

        Args:
            dir_path: Directory path
        """
        Path(dir_path).mkdir(parents=True, exist_ok=True)

    # Parse schedule information
    def parse_schedule(self, schedule_data):
        """Parse schedule info, extract time and broadcast content from JSON"""
        if schedule_data["type"] != "function call" or schedule_data["parameters"]["function_name"] != "set_schedule":
            return None

        try:
            # Parse time string to datetime object
            time_str = schedule_data["parameters"]["value"]
            schedule_time = self.parse_time_string(time_str)
            if not schedule_time:
                return None

            # Get broadcast content
            content = schedule_data["parameters"]["format"]

            # Also capture the addition field if present
            addition = schedule_data["parameters"].get("addition", "")

            return {
                "time": schedule_time.strftime("%Y-%m-%d %H:%M:%S"),
                "content": content,
                "addition": addition,  # Store addition field
                "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            logger.error(f"Error parsing schedule: {e}")
            return None

    # Save schedule to file
    def save_schedule(self, schedule_item):
        """
        Save schedule to user device-specific schedule file

        Args:
            schedule_item: Schedule item

        Returns:
            bool: Whether saving was successful
        """
        # Retrieve schedule directory and file paths
        schedule_dir = self.get_schedule_dir()
        schedule_data_path = self.get_schedule_data_path()
        schedule_log_path = self.get_schedule_log_path()

        # Ensure directory exists
        self.ensure_dir_exists(schedule_dir)

        # Load current active schedules
        current_schedules = self.load_schedules()
        current_schedules.append(schedule_item)

        # Filter out expired schedules, but leave a 30-second buffer for short-term reminders
        now = datetime.datetime.now()
        buffer_time = now - datetime.timedelta(seconds=30)
        active_schedules = [s for s in current_schedules if datetime.datetime.strptime(s["time"], "%Y-%m-%d %H:%M:%S") > buffer_time]

        # Save to schedule data file
        with open(schedule_data_path, "w", encoding="utf-8") as f:
            json.dump(active_schedules, f, ensure_ascii=False, default=str)

        logger.debug(f"Saved {len(active_schedules)} schedules to {schedule_data_path}")

        # Record to log file
        log_entry = (
            f"time      : {schedule_item['time']}\n"
            f"content   : {schedule_item['content']}\n"
            f"created_at: {schedule_item['created_at']}\n"
            f"{'='*50}\n"
        )

        try:
            with open(schedule_log_path, "a", encoding="utf-8") as f:
                f.write(log_entry)
            logger.success(f"[schedule] Recorded to log: {schedule_item['content']}")
        except Exception as e:
            logger.error(f"Failed to write to log: {e}")

        return True

    # Load schedules from file
    def load_schedules(self):
        """
        Load all active schedules from user device-specific schedule file

        Returns:
            list: Schedule list
        """
        schedule_data_path = self.get_schedule_data_path()

        if not os.path.exists(schedule_data_path):
            logger.debug(f"Schedule file does not exist: {schedule_data_path}")
            return []

        try:
            with open(schedule_data_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:  # Check if file is empty
                    logger.info(f"Schedule file exists but is empty: {schedule_data_path}")
                    return []
                schedules = json.loads(content)  # Use json.loads instead of json.load
            logger.debug(f"Loaded {len(schedules)} schedules from {schedule_data_path}")
            return schedules
        except json.JSONDecodeError as je:
            logger.error(f"Error parsing schedule file JSON: {je}")
            logger.info("Returning empty schedule list and creating backup of corrupted file")
            # Create backup and new empty file
            if os.path.exists(schedule_data_path):
                import shutil
                import time
                backup_name = f"{schedule_data_path}.bak.{int(time.time())}"
                shutil.copy2(schedule_data_path, backup_name)

                # Ensure directory exists
                self.ensure_dir_exists(os.path.dirname(schedule_data_path))

                with open(schedule_data_path, "w", encoding="utf-8") as f:
                    f.write("[]")  # Write an empty array as valid JSON
            return []
        except Exception as e:
            logger.error(f"Error loading schedules: {e}")
            return []

    # Main function for setting schedule
    def set_schedule(self, schedule_data):
        """Main function to handle setting schedule"""
        schedule_item = self.parse_schedule(schedule_data)
        if not schedule_item:
            return "Invalid schedule data format"

        success = self.save_schedule(schedule_item)
        if success:
            # self.chat_saver.save_chat_history(f"[System] set schedule: {schedule_item['content']}, time: {schedule_item['time']}")

            # Prioritize returning the addition field if it exists
            if schedule_item.get("addition"):
                return schedule_item["addition"]
            else:
                return f"Successfully set schedule: {schedule_item['content']}, time: {schedule_item['time']}"

        else:
            return "Error saving schedule"

    # Modify parse_delete_request function to support addition field
    def parse_delete_request(self, delete_data):
        """Parse delete schedule request, support multiple deletion methods"""
        if delete_data["type"] != "function call" or delete_data["parameters"]["function_name"] != "delete_schedule":
            return None

        try:
            delete_type = delete_data["parameters"].get("delete_type", "content")
            value = delete_data["parameters"].get("value", "")
            addition = delete_data["parameters"].get("addition", "")  # Retrieve addition field

            return {
                "delete_type": delete_type,  # content, time, index, all
                "value": value,
                "addition": addition,  # Save addition field
                "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            logger.error(f"Error parsing delete schedule request: {e}")
            return None

    # Modify delete_schedule function to support addition field
    def delete_schedule(self, delete_data):
        """Delete schedule based on conditions"""
        delete_request = self.parse_delete_request(delete_data)
        if not delete_request:
            return "Invalid delete request format"

        # Load all current schedules
        current_schedules = self.load_schedules()
        if not current_schedules:
            return "No schedules currently exist"

        # Backup original schedule count
        original_count = len(current_schedules)
        delete_type = delete_request["delete_type"]
        value = delete_request["value"]
        addition = delete_request.get("addition", "")  # Retrieve addition field

        # Delete schedules based on different conditions
        if delete_type == "all":
            # Delete all schedules
            new_schedules = []
            deleted_count = original_count
            deleted_info = "All schedules deleted"
        elif delete_type == "index":
            # Delete by index
            try:
                index = int(value) - 1  # Convert to 0-based index
                if 0 <= index < len(current_schedules):
                    deleted_info = f"Deleted schedule: {current_schedules[index]['content']}"
                    del current_schedules[index]
                    new_schedules = current_schedules
                    deleted_count = 1
                else:
                    return f"Index out of range, valid range: 1-{len(current_schedules)}"
            except ValueError:
                return "Invalid index value"
        elif delete_type == "content":
            # Delete by content keyword
            new_schedules = [s for s in current_schedules if value.lower() not in s["content"].lower()]
            deleted_count = original_count - len(new_schedules)
            deleted_info = f"Deleted {deleted_count} schedules containing keyword '{value}'"
        elif delete_type == "time":
            # Delete by time
            try:
                # Parse time
                target_time = self.parse_time_string(value)
                if not target_time:
                    return "Invalid time format"

                time_str = target_time.strftime("%Y-%m-%d %H:%M:%S")
                new_schedules = [s for s in current_schedules if s["time"] != time_str]
                deleted_count = original_count - len(new_schedules)
                deleted_info = f"Deleted {deleted_count} schedules at time {time_str}"
            except Exception as e:
                logger.error(f"Error parsing time: {e}")
                return "Failed to parse time format"
        else:
            return f"Unsupported delete type: {delete_type}"

        # If no schedules were deleted
        if deleted_count == 0:
            return "No schedules found matching conditions"

        # Retrieve schedule file path
        schedule_data_path = self.get_schedule_data_path()
        schedule_log_path = self.get_schedule_log_path()

        # Ensure directory exists
        self.ensure_dir_exists(os.path.dirname(schedule_data_path))

        # Save updated schedules
        with open(schedule_data_path, "w", encoding="utf-8") as f:
            json.dump(new_schedules, f, ensure_ascii=False, default=str)

        logger.debug(f"Saved {len(new_schedules)} schedules to {schedule_data_path}")

        # Record delete operation to log
        log_entry = (
            f"Operation  : Delete schedule\n"
            f"Delete type: {delete_type}\n"
            f"Value      : {value}\n"
            f"Count      : {deleted_count}\n"
            f"Time       : {delete_request['created_at']}\n"
            f"{'='*50}\n"
        )

        try:
            with open(schedule_log_path, "a", encoding="utf-8") as f:
                f.write(log_entry)
            logger.success(f"[schedule] Delete operation recorded: {deleted_info}")
        except Exception as e:
            logger.error(f"Failed to write to log: {e}")

        # self.chat_saver.save_chat_history(f"[System] delete schedule: {deleted_info}")
        # Prefer returning addition field content (if exists)
        if addition:
            return addition
        else:
            return deleted_info

    # Modify process_response function to pass addition field in two function calls
    def process_response(self, ai_response: str | dict) -> str:
        """Process AI response based on function type - handles multiple JSON objects"""
        try:
            responses = []

            # Handle string input - this could contain multiple JSON objects
            if isinstance(ai_response, str):
                # Parse all JSON objects in the response
                json_pattern = r"```json\s*([\s\S]*?)\s*```"
                all_json_matches = re.findall(json_pattern, ai_response)

                if all_json_matches:
                    # Process each JSON match
                    for json_match in all_json_matches:
                        try:
                            json_obj = json.loads(json_match.strip())
                            responses.append(json_obj)
                        except json.JSONDecodeError as e:
                            logger.error(f"Error parsing JSON match: {e}")
                            continue
                else:
                    # Try to parse the entire string as a single JSON object
                    try:
                        json_obj = json.loads(ai_response.strip())
                        responses.append(json_obj)
                    except json.JSONDecodeError:
                        return "Invalid JSON format"
            else:
                # If it's already a dict, just use it
                responses.append(ai_response)

            # Execute all operations, but only plan to return the result from the last one
            last_response = None

            for i, response in enumerate(responses):
                # Check if it's a function call
                if response.get("type") != "function call":
                    continue

                # Get parameters
                parameters = response.get("parameters", {})
                function_name = parameters.get("function_name")

                if not function_name:
                    continue

                # Execute the operations
                if function_name == "set_schedule":
                    result = self.set_schedule({
                        "type": "function call",
                        "parameters": {
                            "function_name": function_name,
                            "value": parameters.get("value", ""),
                            "format": parameters.get("format", ""),
                            "addition": parameters.get("addition", "")
                        }
                    })

                    # Only store the result if this is the last operation
                    if i == len(responses) - 1:
                        last_response = result

                elif function_name == "delete_schedule":
                    result = self.delete_schedule({
                        "type": "function call",
                        "parameters": {
                            "function_name": function_name,
                            "delete_type": parameters.get("delete_type", ""),
                            "value": parameters.get("value", ""),
                            "addition": parameters.get("addition", "")
                        }
                    })

                    # Only store the result if this is the last operation
                    if i == len(responses) - 1:
                        last_response = result

                elif function_name == "null":
                    if i == len(responses) - 1:
                        last_response = parameters.get("addition", "No schedules matching the criteria were found")

            # Return the result from the last operation
            if last_response:
                return last_response

            # Default message if no operations were executed
            return "Operation completed" if not any('\u4e00' <= char <= '\u9fff' for char in str(ai_response)) else "操作已完成"

        except Exception as e:
            logger.error(f"Error processing response: {str(e)}")
            return f"Error processing response: {str(e)}"

    def check_schedule_query(self, query: str) -> bool:
        """
        Check if the query is related to schedule management (set, delete, or modify schedules)

        This function detects if a user query is related to schedule management by checking
        for specific keywords at the beginning of the query.

        Args:
            query: User's query text

        Returns:
            bool: True if the query is schedule-related, False otherwise
        """
        # Remove leading/trailing spaces
        clean_query = query.strip()

        # Define schedule-related keywords (both Chinese and English)
        schedule_keywords = {
            'chinese': [
                '提醒', '记得', '设置', '安排', '添加', '新建',  # Set schedule
                '删除', '取消', '移除', '清除',                 # Delete schedule
                '修改', '更改', '调整', '改变', '推迟', '提前'  # Modify schedule
            ],
            'english': [
                'remind', 'remember', 'set', 'schedule', 'add', 'create', 'new',  # Set schedule
                'delete', 'cancel', 'remove', 'clear',                           # Delete schedule
                'modify', 'change', 'adjust', 'alter', 'postpone', 'move',        # Modify schedule
                'i need a reminder',
                'can you remind me',
                'would you remind me',
                'please remind me',
                'need to remember',
                'appointment',
                'meeting at',
                'schedule a'
            ]
        }

        # Check if query starts with any of the keywords
        has_chinese = any('\u4e00' <= char <= '\u9fff' for char in clean_query)
        keywords = schedule_keywords['chinese'] if has_chinese else schedule_keywords['english']

        # Check if the query starts with any of the schedule keywords
        for keyword in keywords:
            if clean_query.lower().startswith(keyword.lower()):
                return True

        return False

    def check_view_schedule_query(self, query: str) -> bool:
        """
        Check if the query is asking to view/list current schedules

        This function detects if a user query is requesting to view existing schedules
        by checking for exact matches with predefined patterns in both Chinese and English.

        Args:
            query: User's query text

        Returns:
            bool: True if the query is about viewing schedules, False otherwise
        """
        # Remove leading/trailing spaces and convert to lowercase for comparison
        clean_query = query.strip().lower()

        # Define exact phrases for viewing schedules (both Chinese and English)
        view_schedule_patterns = {
            'chinese': [
                '有什么日程',
                '查看日程',
                '查看我的日程',
                '显示日程',
                '显示我的日程',
                '列出日程', '列出我的日程', '日程列表', '我的日程列表', '我有什么日程',
                '我今天有什么安排', '我明天有什么安排', '今天的安排', '明天的安排',
                '我的行程', '显示行程', '查看行程', '行程列表', '我的行程表',
                '我接下来有什么安排', '接下来的安排', '待办事项', '我的待办事项',
                '今天要做什么', '明天要做什么', '我的日程安排', '日程安排',
                '我有哪些日程', '有哪些日程', '今日安排', '计划表', '我的计划表'
            ],
            'english': [
                'view schedules', 'view my schedules', 'show schedules', 'show my schedules',
                'list schedules', 'list my schedules', 'my schedule list', 'what is my schedule',
                'what are my schedules', 'schedule list', 'show my calendar', 'view my calendar',
                'my appointments', 'show my appointments', 'list my appointments',
                'what appointments do i have', 'what do i have scheduled',
                'what is on my calendar', 'show my agenda', 'view my agenda', 'my agenda',
                'my to-do list', 'show my to-do list', 'what do i need to do',
                'what events do i have', 'my events', 'upcoming events',
                'my schedule', 'upcoming schedule', 'current schedule'
            ]
        }

        # Check if query exactly matches any of the patterns
        has_chinese = any('\u4e00' <= char <= '\u9fff' for char in clean_query)
        patterns = view_schedule_patterns['chinese'] if has_chinese else view_schedule_patterns['english']

        # Check for exact matches
        return clean_query in [pattern.lower() for pattern in patterns]

    def view_schedules(self, query: str) -> str:
        """
        Format and return the list of current schedules for user viewing

        Returns:
            str: Formatted schedules list or appropriate message if no schedules exist
        """
        schedules = self.load_schedules()
        if not schedules:
            return "No schedules currently exist" if not any('\u4e00' <= char <= '\u9fff' for char in query) else "当前没有任何日程安排"

        # Sort schedules by time
        schedules.sort(key=lambda x: x["time"])

        # Determine language for response
        has_chinese = any('\u4e00' <= char <= '\u9fff' for char in query)

        if has_chinese:
            result = "当前日程安排：\n"
            for i, schedule in enumerate(schedules, 1):
                schedule_time = datetime.datetime.strptime(schedule["time"], "%Y-%m-%d %H:%M:%S")
                # Format date differently if it's today or tomorrow
                today = datetime.datetime.now().date()
                schedule_date = schedule_time.date()

                if schedule_date == today:
                    date_str = "今天"
                elif schedule_date == today + datetime.timedelta(days=1):
                    date_str = "明天"
                else:
                    date_str = schedule_time.strftime("%Y年%m月%d日")

                time_str = schedule_time.strftime("%H:%M")
                result += f"{i}. {date_str} {time_str} - {schedule['content']}\n"
        else:
            result = "Current schedules:\n"
            for i, schedule in enumerate(schedules, 1):
                schedule_time = datetime.datetime.strptime(schedule["time"], "%Y-%m-%d %H:%M:%S")
                # Format date differently if it's today or tomorrow
                today = datetime.datetime.now().date()
                schedule_date = schedule_time.date()

                if schedule_date == today:
                    date_str = "Today"
                elif schedule_date == today + datetime.timedelta(days=1):
                    date_str = "Tomorrow"
                else:
                    date_str = schedule_time.strftime("%Y-%m-%d")

                time_str = schedule_time.strftime("%H:%M")
                result += f"{i}. {date_str} at {time_str} - {schedule['content']}\n"

        # Save to chat history
        # self.chat_saver.save_chat_history("[System] viewed schedules")

        return result

    def process_schedule_query(self, query: str) -> tuple[str, bool]:
        """
        Process schedule-related queries and generate appropriate responses

        Args:
            query: User's query text

        Returns:
            tuple: (Response message from schedule model, Boolean indicating if query was handled)
        """
        # Check if the query is asking to view schedules
        if self.check_view_schedule_query(query):
            return self.view_schedules(query), True

        # Check if the query is related to other schedule management
        if self.check_schedule_query(query):
            try:
                # Import schedule_model within the method to avoid circular imports
                import schedule_model

                # Load current schedules
                schedules = self.load_schedules()

                # Use schedule model to generate JSON response, directly passing the schedule list
                response = schedule_model.create_schedule_json(
                    query,
                    schedules=schedules
                )

                # Process the response and execute corresponding operations
                result = self.process_response(response)

                return result, True
            except Exception as e:
                logger.error(f"Error processing schedule query: {str(e)}")
                # Return error message and indicate the query was handled (even if there was an error)
                has_chinese = any('\u4e00' <= char <= '\u9fff' for char in query)
                if has_chinese:
                    return f"抱歉，处理您的日程请求时出错: {str(e)}", True
                else:
                    return f"Sorry, there was an error processing your schedule request: {str(e)}", True

        # Not a schedule query
        return "", False

    # Get all schedules (for display)
    def list_schedules(self):
        """Return formatted list of all schedules for display"""
        schedules = self.load_schedules()
        if not schedules:
            return "No schedules currently exist"

        result = "Current schedule list:\n"
        for i, schedule in enumerate(schedules, 1):
            schedule_time = datetime.datetime.strptime(schedule["time"], "%Y-%m-%d %H:%M:%S")
            formatted_time = schedule_time.strftime("%Y-%m-%d %H:%M")
            result += f"{i}. {formatted_time} - {schedule['content']}\n"

        return result



# Test code update
if __name__ == "__main__":
    print("\n=== Schedule Management System Test ===\n")

    # Create ScheduleHandler instance
    schedule_handler = ScheduleHandler(user_id="test_user", device_id="test_device")

    print(schedule_handler.list_schedules())
    # 测试查询列表
    test_queries = [
    #     # 1. 添加日程测试 (中文)
        "提醒我明天晚上7点开会",

    #     # 2. 添加日程测试 (英文)
        # "Remind me to take medicine at 12pm tomorrow",
        # "view schedules",
    #     # 3. 日程测试 (中文)
    #     "提醒我两个小时后睡觉",

    #     # # 4. 删除日程测试 (英文)
    #     # "Cancel my appointment tomorrow",

    #     # # 5. 修改日程测试 (中文)
    #     # "修改我下午的会议时间到晚上7点",

    #     # # 6. 修改日程测试 (英文)
    #     # "Change my evening meeting to 8pm",

    #     # # 7. 查看日程测试 (中文)
    #     # "查看我的日程",

    #     # # 8. 查看日程测试 (英文)
    #     # "What is my schedule today",

    #     # # 9. 不包含关键词但属于日程管理的测试 (隐式添加)
    #     # "我需要在晚上8点给妈妈打电话",

    #     # # 10. 不相关查询测试 (不应触发日程功能)
    #     # "今天天气怎么样"
    ]

    # Execute tests
    for i, query in enumerate(test_queries, 1):
        print(f"\nTest {i}: '{query}'")
        print("-" * 30)

        response, handled = schedule_handler.process_schedule_query(query)
        print(f"Query handled: {'Yes' if handled else 'No'}")
        if handled:
            print(f"Response result: \n{response}")
        else:
            print("Query was not processed by the schedule system")

    print(schedule_handler.list_schedules())

    print("\n=== Test Completed ===")