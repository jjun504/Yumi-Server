# pip install openai
from groq import Groq
from unified_config import unified_config
import re
import chat_setup
import os
from loguru import logger
import time
import json

class FunctionModel:
    def __init__(self, device_id=None):
        """
        Initialize the Function Model

        Args:
            device_id: Device ID for retrieving device-specific configurations
        """
        self.device_id = device_id
        self.client = Groq(api_key=unified_config.get("llm_services.groq.api_key"))
        self.system_prompt = chat_setup.choose_system_chat(True, device_id=device_id)  # True indicates using function system prompt

        # Ensure correct log configuration
        logger.add("function_model.log", rotation="10 MB", level="DEBUG")
        logger.info("[Initialize][FunctionModel] Pure detection mode initialized")

    def process_function_call(self, user_input):
        """
        Lightweight function call detection - does not save history, does not manage tokens, only focuses on current detection
        """
        # Build message list
        messages = [self.system_prompt]

        messages.append({"role": "user", "content": user_input})

        # Log full input
        logger.debug("==== Function Detection Input ====")
        logger.debug(f"{user_input}")

        # Start timing
        start_time = time.time()

        try:
            response = self.client.chat.completions.create(
                model="gemma2-9b-it",
                messages=messages,
                max_tokens=256,
                temperature=0.1,
                top_p=0.1,
                stream=False,
            )

            full_reply = response.choices[0].message.content

            # Log response time and result
            elapsed_time = time.time() - start_time
            logger.info(f"Function detection completed, time: {elapsed_time:.3f} seconds")
            logger.debug("==== Function Detection Output ====")
            logger.debug(full_reply)
            return full_reply

        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"Function detection failed, time: {elapsed_time:.3f} seconds, error: {str(e)}")
            return ""



# Test code
if __name__ == '__main__':
    import json

    def test_function_model():
        """Test various functionalities of FunctionModel"""
        print("=" * 60)
        print("FunctionModel Test Start")
        print("=" * 60)

        # Initialize Function Model
        try:
            function_model = FunctionModel()
            print("✅ FunctionModel initialized successfully")
        except Exception as e:
            print(f"❌ FunctionModel initialization failed: {e}")
            return

        # Test cases
        test_cases = [
            {
                "name": "Music Playback Test",
                "user_input": "I want to listen to Jay Chou's songs",
                "first_response": "Okay, I'll play Jay Chou's music for you"
            },
            {
                "name": "Weather Query Test",
                "user_input": "What's the weather like tomorrow?",
                "first_response": "Let me check the weather for tomorrow"
            },
            {
                "name": "Web Search Test",
                "user_input": "Help me search for the latest tech news",
                "first_response": "I'll search for the latest tech news for you"
            },
            {
                "name": "Device Control Test",
                "user_input": "Help me turn on the light",
                "first_response": "Okay, I'll turn on the light for you"
            },
            {
                "name": "Schedule Management Test",
                "user_input": "Remind me to attend a meeting at 9 AM tomorrow",
                "first_response": "Okay, I'll set a reminder for your meeting at 9 AM tomorrow"
            },
            {
                "name": "Casual Conversation Test",
                "user_input": "Hello, how's your mood today?",
                "first_response": "Hello! I'm feeling great today, thank you for asking"
            }
        ]

        # Execute tests
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n📋 Test {i}: {test_case['name']}")
            print(f"User Input: {test_case['user_input']}")
            print(f"LLM Response: {test_case['first_response']}")

            try:
                # Call Function Model - Combine user input and LLM response
                combined_input = f"User Input: {test_case['user_input']}\nLLM Response: {test_case['first_response']}"
                result = function_model.process_function_call(combined_input)

                print("Function Model Response:")
                print("-" * 40)
                print(result)
                print("-" * 40)

                # Attempt to parse JSON response
                if result.strip():
                    try:
                        # Extract JSON part
                        json_pattern = r"```json\s*([\s\S]*?)\s*```"
                        json_match = re.search(json_pattern, result)

                        if json_match:
                            json_str = json_match.group(1).strip()
                        else:
                            json_str = result.strip()

                        parsed_json = json.loads(json_str)
                        print("✅ JSON parsed successfully:")
                        print(f"   Function Type: {parsed_json.get('type', 'N/A')}")
                        if 'parameters' in parsed_json:
                            print(f"   Function Name: {parsed_json['parameters'].get('function_name', 'N/A')}")
                            if 'query' in parsed_json['parameters']:
                                print(f"   Query Content: {parsed_json['parameters']['query']}")
                            if 'song_name' in parsed_json['parameters']:
                                print(f"   Song Name: {parsed_json['parameters']['song_name']}")
                    except json.JSONDecodeError as e:
                        print(f"⚠️  JSON parsing failed: {e}")
                        print("   This might be a casual conversation, no function call needed")
                else:
                    print("ℹ️  Empty result returned, might be a casual conversation")

            except Exception as e:
                print(f"❌ Test failed: {e}")

            print()

        print("=" * 60)
        print("FunctionModel Test Completed")
        print("=" * 60)

    def interactive_test():
        """Interactive test mode"""
        print("\n🔧 Entering interactive test mode")
        print("Type 'exit' to quit, type 'auto' to run automatic tests")

        function_model = FunctionModel()

        while True:
            print("\n" + "-" * 50)
            user_input = input("👤 User Input: ").strip()

            if user_input.lower() == "exit":
                print("👋 Exiting interactive test")
                break
            elif user_input.lower() == "auto":
                test_function_model()
                continue
            elif not user_input:
                print("⚠️  Please enter valid content")
                continue

            first_response = input("🤖 LLM Response: ").strip()
            if not first_response:
                print("⚠️  Please enter LLM response")
                continue

            try:
                # Combine input
                combined_input = f"User Input: {user_input}\nLLM Response: {first_response}"
                result = function_model.process_function_call(combined_input)
                print("\n🔍 Function Model Response:")
                print("=" * 40)
                print(result if result else "No function call needed")
                print("=" * 40)
            except Exception as e:
                print(f"❌ Processing failed: {e}")

    # Main test entry
    print("FunctionModel Test Tool")
    print("1. Automatic Test (auto)")
    print("2. Interactive Test (interactive)")

    mode = input("Select test mode (auto/interactive): ").strip().lower()

    if mode == "auto" or mode == "1":
        test_function_model()
    elif mode == "interactive" or mode == "2":
        interactive_test()
    else:
        print("Defaulting to automatic test...")
        test_function_model()