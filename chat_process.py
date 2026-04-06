import json
import re
from loguru import logger
from function_model import FunctionModel
import time
import intent_model
import device_model
import schedule_model
import unified_config
from unified_config import get_config, set_config

class ChatProcess:
    def __init__(self, chat_module, device_id=None):
        self.device_id = device_id  # Device ID, used for configuration management
        self.module = chat_module
        self.function_module = FunctionModel(device_id=device_id)
        self.llm_manager = None  # LLM manager instance, will be set in set_handlers method

        # Initialize handler references, will be set in set_handlers method
        self.weather_handler = None
        self.schedule_handler = None
        self.web_handler = None
        self.music_handler = None
        self.device_control_handler = None
        self.chat_saver = None

        if self.function_module:
            logger.info("[Initialize][ChatProcess] Two-stage model processing enabled (text-only mode)")
        else:
            logger.info("[Initialize][ChatProcess] Single-stage processing only")

    def set_handlers(self, prechat):
        """Get various handler objects from prechat instance"""
        self.weather_handler = prechat.weather_handler
        self.schedule_handler = prechat.schedule_handler
        self.web_handler = prechat.web_handler
        self.music_handler = prechat.music_handler
        self.device_control_handler = prechat.device_control_handler
        self.chat_saver = prechat.state.chat_saver

        # Get LLM manager
        if hasattr(prechat, 'llm_manager') and prechat.llm_manager is not None:
            self.llm_manager = prechat.llm_manager
            logger.debug("LLM manager retrieved from prechat")
        else:
            logger.warning("Failed to retrieve LLM manager from prechat")

    def send(self, user_input):
        # Check if LLM service needs to be updated
        self._check_llm_service()

        # Stage one: Use inference model to generate user intent
        first_reply = intent_model.send(user_input, device_id=self.device_id)
        first_reply_json = None

        # Handle str -> JSON
        if isinstance(first_reply, str):
            # First remove all ```json and ``` tags
            json_pattern = r"```json\s*([\s\S]*?)\s*```"
            json_match = re.search(json_pattern, first_reply)

            if json_match:
                # If json code block is found, only process its content
                json_str = json_match.group(1).strip()
            else:
                # If no code block tags, process the entire string directly
                json_str = first_reply.strip()

            try:
                first_reply_json = json.loads(json_str)
            except json.JSONDecodeError:
                logger.warning("⚠️ JSON parsing failed, attempting to extract reasoning")
                logger.warning(f"json_str: {json_str}")

                # Try to extract reasoning from the malformed JSON
                extracted_reasoning = self._extract_reasoning_from_malformed_json(json_str)

                # Create default JSON with extracted reasoning if available
                first_reply_json = {
                    "intents": [],
                    "reasoning": extracted_reasoning if extracted_reasoning else "Unable to correctly reason about user thoughts"
                }
        else:
            # Return default values to match expected return format (4 values)
            logger.warning("⚠️ Intent model returned non-string response")
            default_json = {
                "intents": [],
                "reasoning": "Unable to correctly reason about user thoughts"
            }
            return user_input, default_json, "I'm sorry, there was an issue processing your request. Could you please try again?", False

        # Stage two: Use chat model to generate reply
        # Extract original user input from formatted input for language detection
        original_user_input = ""
        if "用户输入:" in user_input:
            # Extract text after "User input:" and before next line
            lines = user_input.split('\n')
            for line in lines:
                if line.startswith("用户输入:"):
                    original_user_input = line.replace("用户输入:", "").strip()
                    break
        else:
            original_user_input = user_input

        # Detect language in original user input only
        has_chinese = any('\u4e00' <= char <= '\u9fff' for char in original_user_input)

        # Add language-specific instruction
        language_instruction = ""
        if has_chinese:
            language_instruction = "请用中文与用户对话，控制在两句内。"
        else:
            language_instruction = "Please use English to chat with the user, within two sentences."
        reasoning = first_reply_json.get("reasoning", "")

        second_stage_prompt = f"""
{user_input}用户意图: {reasoning}
{language_instruction}
"""

        logger.debug(f"Second stage prompt: \n{second_stage_prompt}")
        second_reply = self.module.ask(second_stage_prompt)
        logger.debug(f"Second stage reply generated: {second_reply}")

        function_call_handled = self.function_call_checking(first_reply_json)
        return user_input, first_reply_json, second_reply, function_call_handled

    def _extract_reasoning_from_malformed_json(self, json_str):
        """
        Extract reasoning content from malformed JSON string

        Args:
            json_str: The malformed JSON string

        Returns:
            str: Extracted reasoning content or None if not found
        """
        try:
            # Try to extract reasoning using regex that handles escaped quotes
            # This pattern matches: "reasoning":"content" where content can contain escaped quotes
            reasoning_pattern = r'"reasoning"\s*:\s*"((?:[^"\\]|\\.)*)"\s*[,}]'
            reasoning_match = re.search(reasoning_pattern, json_str)

            if reasoning_match:
                reasoning_content = reasoning_match.group(1)
                # Unescape common escape sequences
                reasoning_content = reasoning_content.replace('\\"', '"').replace('\\\\', '\\')
                logger.info(f"✅ Successfully extracted reasoning: {reasoning_content}")
                return reasoning_content

            # Fallback: simpler pattern for basic cases
            reasoning_pattern_simple = r'"reasoning"\s*:\s*"([^"]*)"'
            reasoning_match_simple = re.search(reasoning_pattern_simple, json_str)

            if reasoning_match_simple:
                reasoning_content = reasoning_match_simple.group(1)
                logger.info(f"✅ Successfully extracted reasoning (simple pattern): {reasoning_content}")
                return reasoning_content

            logger.warning("⚠️ Could not extract reasoning from malformed JSON")
            return None

        except Exception as e:
            logger.error(f"❌ Error extracting reasoning: {e}")
            return None

    def _check_llm_service(self):
        """Check if LLM service needs to be updated"""
        # If there is no LLM manager, it cannot be updated
        if not self.llm_manager:
            return

        # Get the currently active LLM service from the configuration
        active_service = get_config("LLM.active_service", device_id=self.device_id)

        # If the current service is inconsistent with the configuration, switch services
        if active_service and self.llm_manager.service_name != active_service:
            logger.info(f"Detected LLM service change: {self.llm_manager.service_name} -> {active_service}")

            try:
                # Refresh the list of available services
                self.llm_manager.refresh_available_services()

                # Get the current model ID
                model_id = get_config("LLM.model_id", None, device_id=self.device_id)

                # Switch LLM service
                new_llm_instance = self.llm_manager.switch_service(active_service, model_id)

                # Update module
                self.module = new_llm_instance

                logger.info(f"Successfully switched LLM service to {active_service}, using model {model_id}")

                # Note: This will not update the configuration file, only switch services in memory
            except Exception as e:
                logger.error(f"Failed to switch LLM service: {e}")
        else:
            # Check if the model ID needs to be updated
            model_id = get_config("LLM.model_id", None, device_id=self.device_id)
            if model_id and model_id != self.llm_manager.model_id:
                logger.info(f"Detected LLM model change: {self.llm_manager.model_id} -> {model_id}")

                try:
                    # Update model
                    new_llm_instance = self.llm_manager.update_model(model_id)

                    # Update module
                    self.module = new_llm_instance

                    logger.info(f"Successfully updated LLM model to {model_id}")

                    # Note: This will not update the configuration file, only update the model in memory
                except Exception as e:
                    logger.error(f"Failed to update LLM model: {e}")

    def function_call_checking(self, first_reply_json):
        # Check if second stage processing is needed -- confidence value == 1
        if first_reply_json.get("intents") and first_reply_json["intents"] and first_reply_json["intents"][0].get("confidence") == 1:
            # Function triggering is disabled for intentmodel confidence value == 1
            logger.info("Function triggering disabled: intentmodel confidence value equals 1, skipping function model processing")
            return False
        return False

    def function_call_processing(self, user_input, first_reply_json, second_reply):
        """Object-oriented processing of function calls"""
        # Record the start time of processing
        start_time = time.time()

        # Ensure handlers are set
        if not self.device_control_handler or not self.schedule_handler or not self.weather_handler or not self.web_handler or not self.music_handler:
            logger.error("Handlers not properly set, unable to execute function call")
            return "Handlers not properly set, unable to execute function call"

        function_module = first_reply_json.get("intents")[0].get("module", "No module provided")
        combined_message = f"{user_input}\nUser intent: {first_reply_json['reasoning']}\nModel response: {second_reply}"

        result = None

        # Device control processing
        if function_module == "device control":
            module_response = device_model.create_device_json(combined_message)
            logger.info(f"Device control processing completed, time taken: {time.time() - start_time:.3f}s")
            result = self.device_control_handler.process_device_response(module_response)

        # Schedule processing
        elif function_module == "schedule":
            # Get the current schedule list from schedule_handler
            schedules = self.schedule_handler.load_schedules()
            # Pass the schedule list to the create_schedule_json function
            module_response = schedule_model.create_schedule_json(combined_message, schedules=schedules)
            result = self.schedule_handler.set_schedule(module_response)

        # Unified function LLM processing
        elif function_module in ["weather", "web search", "music"]:
            module_response = self.function_module.process_function_call(combined_message)
            if isinstance(module_response, str):
                json_pattern = r"```json\s*([\s\S]*?)\s*```"
                json_match = re.search(json_pattern, module_response)

                if json_match:
                    # If a JSON code block is found, only process its content
                    json_str = json_match.group(1).strip()
                else:
                    # If no code block tags, process the entire string directly
                    json_str = module_response.strip()
                try:
                    module_reply_json = json.loads(json_str)
                except json.JSONDecodeError:
                    logger.warning("⚠️ JSON parsing failed")
                    return "JSON format error"

                # Call the corresponding handler based on the function name
                function_name = module_reply_json.get("parameters", {}).get("function_name")

                if function_name == "play_single_song":
                    logger.debug("Executing music operation")
                    result = self.music_handler.process_music_response(module_reply_json)
                elif function_name == "web_search":
                    logger.debug("Executing web search operation")
                    search_query = module_reply_json.get("parameters", {}).get("query", "")
                    result = self.web_handler.check_web_query(search_query)[0]
                elif function_name == "get_weather":
                    logger.debug("Executing weather operation")
                    result = self.weather_handler.check_weather_query(user_input)
            else:
                logger.warning("Module response is not in string format")
                result = "Module response format error"
        else:
            return ""
        # Record the completion time of function processing
        logger.info(f"Function processing completed, total time taken: {time.time() - start_time:.3f}s")
        return result




if __name__ == "__main__":
    # Test code - for demonstration only, actual usage should retrieve handlers from prechat
    from if_weather import WeatherHandler
    from if_schedule import ScheduleHandler
    from if_device_control import DeviceControlHandler
    from if_web import WebHandler
    from if_music import MusicHandler
    from chat_saver import ChatSaver
    from groqapi import GroqChatModule
    from llm_manager import LLMManager, init_llm_manager

    # Initialize function model
    function_model = FunctionModel()

    # Initialize LLM manager
    llm_manager = init_llm_manager("groq")

    # Get LLM instance
    llm_instance = llm_manager.llm_instance

    # Create ChatProcess instance
    chat_process = ChatProcess(llm_instance)

    # Set LLM manager
    chat_process.llm_manager = llm_manager

    # Manually set handlers (actual application should set them via prechat.py's set_handlers method)
    chat_process.weather_handler = WeatherHandler()
    chat_process.schedule_handler = ScheduleHandler(user_id="test_user", device_id="test_device")
    chat_process.web_handler = WebHandler()
    chat_process.music_handler = MusicHandler()
    chat_process.device_control_handler = DeviceControlHandler()
    chat_process.chat_saver = ChatSaver(device_id="test_device")

    # Use handlers to process user input
    response = chat_process.send("Sister~ I want to know what events are happening in Japan recently")
    print(f"Response: {response}")

    # Test function call processing
    print("Testing function call processing...")
    test_json = {
        "intents": [
            {"module": "device control", "confidence": 1}
        ],
        "reasoning": "The user wants to control the device"
    }

    # Test switching LLM service
    print("Testing LLM service switching...")
    # Note: In actual applications, configuration should be done via unified_config
    # set_config("LLM.active_service", "groq", device_id="test_device")
    # set_config("LLM.model_id", "llama-3.3-70b-versatile", device_id="test_device")

    # Send another request, it should automatically switch services
    response = chat_process.send("Can you turn on the fan for me?")
    print(f"Response after switching service: {response}")

    # Note: In actual applications, function_call_processing should be invoked by prechat.py