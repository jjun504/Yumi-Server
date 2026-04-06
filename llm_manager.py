from loguru import logger
import unified_config
from unified_config import get_config
# Import all possible LLM engines
from groqapi import GroqChatModule
from chatgptAPI import OpenaiChatModule
from deepseekapi import DeepSeekChatModule
# Additional LLM engines can be added in the future, such as:
# from gemini import GeminiChatModule
# from gpt4free import GPT4FreeModule

# No longer using a global LLM manager; each device service instance has its own LLM manager

class LLMManager:
    """
    LLM Service Manager for managing and switching between different LLM services
    """
    def __init__(self, service_name=None, tts_manager=None, device_id=None):
        """
        Initialize the LLM Manager

        Args:
            service_name: Name of the LLM service, e.g., "groq", "openai", "deepseek", etc.
            tts_manager: TTS Manager instance for LLM services requiring TTS
            device_id: Device ID for fetching device-specific configurations
        """

        self.device_id = device_id

        # Get the list of available LLM services
        self.available_services = self._get_available_services()

        # If not specified, read from configuration
        if service_name is None:
            service_name = get_config("LLM.active_service", "groq", device_id=device_id).lower()

        # Validate service availability; use default service if unavailable
        if service_name not in self.available_services:
            logger.warning(f"Service {service_name} is unavailable, attempting to use default service")
            if "groq" in self.available_services:
                service_name = "groq"
            elif len(self.available_services) > 0:
                service_name = self.available_services[0]
            else:
                logger.error("No available LLM services")
                raise ValueError("No available LLM services")

        self.service_name = service_name
        self.tts_manager = tts_manager
        self.llm_instance = None
        self.model_id = self._get_model_id_for_service(service_name)

        # Initialize the LLM instance
        self._init_llm_instance()

    def _get_available_services(self):
        """
        Get the list of available LLM services

        Returns:
            List of available LLM services
        """

        available_services = []

        # Check which services are enabled - read from constant configuration
        if get_config("llm_services.use_groq", True):
            available_services.append("groq")

        if get_config("llm_services.use_openai", False):
            available_services.append("openai")

        if get_config("llm_services.use_deepseek", False):
            available_services.append("deepseek")

        # If no explicit enable flags, assume all services with API keys are enabled
        if not available_services:
            if get_config("llm_services.groq.api_key"):
                available_services.append("groq")

            if get_config("llm_services.openai.api_key"):
                available_services.append("openai")

            if get_config("llm_services.deepseek.api_key"):
                available_services.append("deepseek")

        logger.info(f"Available LLM services: {available_services}")
        return available_services

    def _get_model_id_for_service(self, service_name):
        """
        Get the model ID for the specified service

        Args:
            service_name: Name of the service

        Returns:
            Model ID
        """

        # Get the current selected model ID from device configuration
        model_id = get_config("LLM.model_id", None, device_id=self.device_id)

        # If no model ID in device configuration, get default model ID from constant configuration
        if not model_id:
            # Get the model list from constant configuration
            admin_models = get_config(f"llm_services.{service_name}.models", [])

            # If there is a model list, use the first model
            if admin_models and isinstance(admin_models, list):
                if isinstance(admin_models[0], dict) and "id" in admin_models[0]:
                    # New format, containing id and name objects
                    model_id = admin_models[0]["id"]
                else:
                    # Old format, directly use model ID
                    model_id = admin_models[0]

        logger.info(f"Service {service_name} uses model: {model_id}")
        return model_id

    def _validate_model_id(self, service_name, model_id):
        """
        Validate whether the model ID is available

        Args:
            service_name: Name of the service
            model_id: Model ID

        Returns:
            If the model is available, return the model ID; otherwise, return the default model ID
        """

        # Get the model list from constant configuration
        admin_models = get_config(f"llm_services.{service_name}.models", [])

        # Check whether the model ID is in the administrator-configured model list
        if admin_models and isinstance(admin_models, list):
            # Check whether it is the new format (list of objects containing id and name)
            if admin_models and isinstance(admin_models[0], dict) and "id" in admin_models[0]:
                # New format, check whether id matches
                valid_model_ids = [model["id"] for model in admin_models]
                if model_id in valid_model_ids:
                    return model_id
                else:
                    logger.warning(f"Model {model_id} is unavailable, using default model")
                    return admin_models[0]["id"]
            else:
                # Old format, directly check model ID
                if model_id in admin_models:
                    return model_id
                else:
                    logger.warning(f"Model {model_id} is unavailable, using default model")
                    return admin_models[0]

        # If no available models, return the original model ID
        return model_id

    def _init_llm_instance(self):
        """
        Initialize the corresponding LLM instance based on the service name
        """
        logger.info(f"Initializing LLM service: {self.service_name}")

        # Validate whether the model ID is available
        self.model_id = self._validate_model_id(self.service_name, self.model_id)

        # No longer update the model ID in the configuration to avoid overwriting user settings

        # Create the corresponding LLM instance based on the service name
        if "groq" in self.service_name.lower():
            self.llm_instance = GroqChatModule(device_id=self.device_id)
            logger.debug("Groq LLM initialization complete")
        elif "openai" in self.service_name.lower() or "gpt" in self.service_name.lower():
            if self.tts_manager is None:
                logger.error("OpenAI LLM requires a TTS manager, but none was provided")
                raise ValueError("OpenAI LLM requires a TTS manager")

            self.llm_instance = OpenaiChatModule(self.tts_manager, device_id=self.device_id)
            logger.debug("OpenAI LLM initialization complete")
        elif "deepseek" in self.service_name.lower():
            if self.tts_manager is None:
                logger.error("DeepSeek LLM requires a TTS manager, but none was provided")
                raise ValueError("DeepSeek LLM requires a TTS manager")

            self.llm_instance = DeepSeekChatModule(self.tts_manager, device_id=self.device_id)
            logger.debug("DeepSeek LLM initialization complete")
        # elif "gemini" in self.service_name.lower():
        #     self.llm_instance = GeminiChatModule(self.tts_manager)
        #     logger.debug("Gemini LLM initialization complete")
        # elif "gpt4free" in self.service_name.lower():
        #     self.llm_instance = GPT4FreeModule(self.tts_manager)
        #     logger.debug("GPT4Free LLM initialization complete")
        else:
            logger.warning(f"Unknown LLM service: {self.service_name}, using default Groq LLM")
            self.llm_instance = GroqChatModule(device_id=self.device_id)

    def switch_service(self, service_name, model_id=None):
        """
        Switch LLM service

        Args:
            service_name: LLM service name, such as "groq", "openai", "deepseek", etc.
            model_id: Model ID, if not specified, use the default model

        Returns:
            The LLM instance after the switch
        """
        # Check service availability
        if service_name not in self.available_services:
            logger.warning(f"Service {service_name} is unavailable, cannot switch")
            return self.llm_instance

        # Save the conversation history of the current LLM service
        if self.llm_instance is not None:
            try:
                self.llm_instance.save()
                logger.info(f"Saved the conversation history of the current LLM service")
            except Exception as e:
                logger.warning(f"Failed to save the conversation history of the current LLM service: {e}")

        # Update service name
        self.service_name = service_name

        # If model ID is specified, use the specified model ID
        if model_id:
            self.model_id = model_id
        else:
            # Otherwise, get the default model ID for the service
            self.model_id = self._get_model_id_for_service(service_name)

        # No longer update the active service in the configuration to avoid overwriting user settings
        # config.set("LLM.active_service", service_name)

        # Initialize the new LLM instance
        self._init_llm_instance()

        return self.llm_instance

    def update_model(self, model_id):
        """
        Update the model of the current service

        Args:
            model_id: New model ID

        Returns:
            The updated LLM instance
        """
        # Validate whether the model ID is available
        validated_model_id = self._validate_model_id(self.service_name, model_id)

        # If the model ID has changed, update the configuration and reinitialize the LLM instance
        if validated_model_id != self.model_id:
            # Save the conversation history of the current LLM service
            if self.llm_instance is not None:
                try:
                    self.llm_instance.save()
                    logger.info(f"Saved the conversation history of the current LLM service")
                except Exception as e:
                    logger.warning(f"Failed to save the conversation history of the current LLM service: {e}")

            # Update the model ID
            self.model_id = validated_model_id

            # No longer update the model ID in the configuration to avoid overwriting user settings
            # config.set("LLM.model_id", validated_model_id)

            # Reinitialize the LLM instance
            self._init_llm_instance()

        return self.llm_instance

    def refresh_available_services(self):
        """
        Refresh the list of available LLM services

        If the current service is no longer available, switch to an available service

        Returns:
            If the service changes, return the new LLM instance; otherwise, return the current instance
        """
        # Get the latest available services
        new_available_services = self._get_available_services()

        # If the available services list has changed
        if set(new_available_services) != set(self.available_services):
            logger.info(f"The list of available LLM services has been updated: {new_available_services}")
            self.available_services = new_available_services

            # If the current service is no longer available, switch to an available service
            if self.service_name not in new_available_services:
                logger.warning(f"The current service {self.service_name} is no longer available, attempting to switch to an available service")

                # Select a new service
                if "groq" in new_available_services:
                    new_service = "groq"
                elif len(new_available_services) > 0:
                    new_service = new_available_services[0]
                else:
                    logger.error("No available LLM services")
                    return self.llm_instance

                # Switch to the new service
                return self.switch_service(new_service)

        # Validate whether the current model is still available
        current_model_id = self.model_id
        validated_model_id = self._validate_model_id(self.service_name, current_model_id)

        # If the model ID has changed, update the model
        if validated_model_id != current_model_id:
            logger.warning(f"The current model {current_model_id} is no longer available, switching to {validated_model_id}")
            return self.update_model(validated_model_id)

        return self.llm_instance

    def ask(self, user_input):
        """
        Send user input to the current LLM service and get a response

        Args:
            user_input: The text input from the user

        Returns:
            The response from the LLM service
        """
        if self.llm_instance is None:
            logger.error("LLM instance not initialized")
            return "LLM service not initialized, unable to process request"

        return self.llm_instance.ask(user_input)

    def refresh_system_prompt(self):
        """
        Refresh the system prompt of the current LLM instance
        Used to reload personality and other settings after configuration changes
        """
        if self.llm_instance is None:
            logger.warning("LLM instance not initialized, unable to refresh system prompt")
            return False

        try:
            # Check if the LLM instance has the refresh_system_prompt method
            if hasattr(self.llm_instance, 'refresh_system_prompt'):
                self.llm_instance.refresh_system_prompt()
                logger.info(f"Refreshed the system prompt of {self.service_name} LLM")
                return True
            else:
                logger.warning(f"{self.service_name} LLM does not support refreshing system prompt")
                return False
        except Exception as e:
            logger.error(f"Failed to refresh the system prompt of {self.service_name} LLM: {e}")
            return False

    def ask_web(self, web_content):
        """
        Send web content to the current LLM service and get a response

        Args:
            web_content: The content of the web page

        Returns:
            The response from the LLM service
        """
        if self.llm_instance is None:
            logger.error("LLM instance not initialized")
            return "LLM service not initialized, unable to process request"

        return self.llm_instance.ask_web(web_content)

    def save(self, save_path=None):
        """
        Save the conversation history of the current LLM service

        Args:
            save_path: Optional save path, if provided, passed to the LLM instance
        """
        if self.llm_instance is not None:
            self.llm_instance.save(save_path)

    def read(self, load_path=None):
        """
        Read the conversation history of the current LLM service

        Args:
            load_path: Optional load path, if provided, passed to the LLM instance
        """
        if self.llm_instance is not None:
            self.llm_instance.read(load_path)

# Create a function to initialize an LLM manager instance
def init_llm_manager(service_name=None, tts_manager=None, device_id=None):
    """
    Create a new LLM manager instance

    Args:
        service_name: Name of the LLM service, e.g., "groq", "openai", "deepseek", etc.
        tts_manager: TTS manager instance for LLM services requiring TTS
        device_id: Device ID for fetching device-specific configurations

    Returns:
        Newly created LLM manager instance
    """
    return LLMManager(service_name, tts_manager, device_id)

# Test code
if __name__ == "__main__":
    # Test LLM service that does not require TTS
    llm_manager = LLMManager("groq")
    response = llm_manager.ask("Hello, please introduce yourself")
    print(f"Groq Response: {response}")

    # Test LLM service that requires TTS (requires initializing TTS manager first)
    try:
        USE_AZURE = get_config("TTS.use_azure", False)
        USE_VOLCANO = get_config("TTS.use_bytedance", False)

        tts_manager = None
        if USE_AZURE:
            from queue import Queue
            from azureTTS import TTSManager
            tts_manager = TTSManager(Queue())
        elif USE_VOLCANO:
            from bytedanceTTS import TTSManager
            tts_manager = TTSManager()

        if tts_manager:
            llm_manager.switch_service("openai")
            response = llm_manager.ask("Hello, please introduce yourself")
            print(f"OpenAI Response: {response}")

            # Create another independent LLM instance
            print("Creating another independent LLM instance")
            another_llm_manager = LLMManager("groq")
            response = another_llm_manager.ask("Who are you?")
            print(f"Response from another LLM instance: {response}")
    except Exception as e:
        print(f"Failed to test LLM service requiring TTS: {e}")