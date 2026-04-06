from loguru import logger

# Import all possible TTS engines
try:
    from bytedanceTTS import TTSManager as BytedanceTTSManager
except ImportError:
    BytedanceTTSManager = None
    logger.warning("Failed to import BytedanceTTS module")

try:
    from azureTTS import TTSManager as AzureTTSManager
except ImportError:
    AzureTTSManager = None
    logger.warning("Failed to import AzureTTS module")

try:
    from gpt_sovits_tts import TTSManager as GPTSoVITSTTSManager
except ImportError:
    GPTSoVITSTTSManager = None
    logger.warning("Failed to import GPT-SoVITS TTS module")

# Import event system for sending TTS reset signals
try:
    from event_system import event_system
except ImportError:
    event_system = None
    logger.warning("Failed to import event_system module")

# No longer using a global TTS manager; each device service instance has its own TTS manager

class TTSManager:
    """
    TTS service manager for managing and switching between different TTS services
    """
    def __init__(self, service_name=None, device_id=None):
        """
        Initialize the TTS manager

        Args:
            service_name: Name of the TTS service, e.g., "bytedance", "azure", etc.
            device_id: Device ID for reading device-specific configurations
        """
        from unified_config import unified_config

        # Store device ID
        self.device_id = device_id

        # Get the list of available TTS services
        self.available_services = self._get_available_services()

        # Dictionary to store all TTS service instances
        self.tts_instances = {}

        # Dictionary to store model IDs for each service
        self.service_model_ids = {}

        # Default to using raw PCM
        self.use_raw_pcm = True

        # If not specified, read from configuration
        if service_name is None:
            if self.device_id:
                service_name = unified_config.get("TTS.active_service", "bytedance", device_id=self.device_id)
            else:
                # Use constant configuration if no device_id
                service_name = unified_config.get("TTS.active_service", "bytedance")
            if service_name:
                service_name = service_name.lower()

        # Validate service availability; use default service if unavailable
        if service_name not in self.available_services:
            logger.warning(f"Service {service_name} is unavailable, attempting to use default service")
            if "bytedance" in self.available_services:
                service_name = "bytedance"
            elif "azure" in self.available_services:
                service_name = "azure"
            elif len(self.available_services) > 0:
                service_name = self.available_services[0]
            else:
                logger.error("No available TTS services")
                raise ValueError("No available TTS services")

        # Set the current service name
        self.service_name = service_name

        # Initialize all available TTS services
        logger.info("Initializing all available TTS services...")
        for service in self.available_services:
            # Get the model ID for the service
            model_id = self._get_model_id_for_service(service)
            self.service_model_ids[service] = model_id

            # Initialize the TTS instance for the service
            self._init_service_instance(service)

        # Set the currently active TTS instance
        self.tts_instance = self.tts_instances.get(self.service_name)
        self.model_id = self.service_model_ids.get(self.service_name)

        # If the current service instance initialization fails, attempt to use other available services
        if self.tts_instance is None and self.tts_instances:
            logger.warning(f"Current service {self.service_name} initialization failed, attempting to use other available services")
            self.service_name = next(iter(self.tts_instances.keys()))
            self.tts_instance = self.tts_instances[self.service_name]
            self.model_id = self.service_model_ids[self.service_name]

        # If no services are available, raise an exception
        if self.tts_instance is None:
            logger.error("No available TTS services")
            raise ValueError("No available TTS services")

    def _get_available_services(self):
        """
        Get the list of available TTS services

        Returns:
            List of available TTS services
        """
        from unified_config import unified_config

        available_services = []

        # Check which services are enabled - read from constant configuration
        if unified_config.get("TTS.use_bytedance", True) and BytedanceTTSManager is not None:
            available_services.append("bytedance")

        if unified_config.get("TTS.use_azure", False) and AzureTTSManager is not None:
            available_services.append("azure")

        if unified_config.get("TTS.use_sovits", False) and GPTSoVITSTTSManager is not None:
            available_services.append("sovits")

        logger.info(f"Available TTS services: {available_services}")
        return available_services

    def _get_model_id_for_service(self, service_name):
        """
        Get the model ID for the specified service

        Args:
            service_name: Service name

        Returns:
            Model ID
        """
        from unified_config import unified_config

        # Special handling for GPT-SoVITS: directly return the fixed model ID
        if "gpt_sovits" in service_name.lower() or "sovits" in service_name.lower():
            logger.info(f"Service {service_name} uses fixed model: Customize voice")
            return "Customize voice"

        # Get the current language setting
        if self.device_id:
            language = unified_config.get("system.language", "zh-CN", device_id=self.device_id)
            # First, try to get the service-specific model ID from the device configuration
            service_specific_model = unified_config.get(f"TTS.{service_name}.model_id", None, device_id=self.device_id)
        else:
            # Use constant configuration if no device_id
            language = unified_config.get("system.language", "zh-CN")
            service_specific_model = None

        if service_specific_model:
            # Validate if the service-specific model ID is in the available model list for the service
            if self._is_model_available_for_service(service_name, service_specific_model, language):
                logger.info(f"Service {service_name} uses service-specific model: {service_specific_model}")
                return service_specific_model

        # If no service-specific model ID, or the model is unavailable, get the default model ID from constant configuration
        # Get the language-specific model list from constant configuration
        admin_models = unified_config.get(f"TTS.{service_name}.languages.{language}", [])

        # If no language-specific model found, try to get the model for the first available language
        if not admin_models:
            languages = unified_config.get(f"TTS.{service_name}.languages", {})
            if languages and isinstance(languages, dict):
                for _, models in languages.items():
                    if models:
                        admin_models = models
                        break

        # If there is a model list, use the first model
        model_id = None
        if admin_models and isinstance(admin_models, list):
            if isinstance(admin_models[0], dict) and "id" in admin_models[0]:
                # New format, containing id and name objects
                model_id = admin_models[0]["id"]
            else:
                # Old format, directly use the model ID
                model_id = admin_models[0]

        # For backward compatibility, if model ID is still not found, try to get it from the old path
        if not model_id:
            admin_models = unified_config.get(f"TTS.{service_name}.model_id", [])
            if admin_models and isinstance(admin_models, list):
                if isinstance(admin_models[0], dict) and "id" in admin_models[0]:
                    model_id = admin_models[0]["id"]
                else:
                    model_id = admin_models[0]

        # If model ID is still not found, try to get it from the general TTS.model_id, but only if the model is available for the current service
        if not model_id and self.device_id:
            general_model_id = unified_config.get("TTS.model_id", None, device_id=self.device_id)
            if general_model_id and self._is_model_available_for_service(service_name, general_model_id, language):
                model_id = general_model_id

        logger.info(f"Service {service_name} uses model: {model_id}")
        return model_id

    def _is_model_available_for_service(self, service_name, model_id, language):
        """
        Check if the model ID is in the available model list for the specified service

        Args:
            service_name: Service name
            model_id: Model ID
            language: Language

        Returns:
            bool: Returns True if the model is available, otherwise returns False
        """
        from unified_config import unified_config

        # Special handling for GPT-SoVITS: only accept the "Customize voice" model
        if "gpt_sovits" in service_name.lower() or "sovits" in service_name.lower():
            return model_id == "Customize voice"

        # Get the language-specific model list from constant configuration
        admin_models = unified_config.get(f"TTS.{service_name}.languages.{language}", [])

        # If no language-specific model found, try to find the model in all languages
        if not admin_models:
            languages = unified_config.get(f"TTS.{service_name}.languages", {})
            if languages and isinstance(languages, dict):
                # Search the model list for all languages
                for _, models in languages.items():
                    if models:
                        # If a matching model ID is found in a language, return True
                        for model in models:
                            if isinstance(model, dict) and model.get("id") == model_id:
                                return True
                            elif isinstance(model, str) and model == model_id:
                                return True

        # If model list is still not found, try to get it from the old path
        if not admin_models:
            admin_models = unified_config.get(f"TTS.{service_name}.model_id", [])

        # Check if the model ID is in the admin-configured model list
        if admin_models and isinstance(admin_models, list):
            # Check if it's the new format (list of objects containing id and name)
            if admin_models and isinstance(admin_models[0], dict) and "id" in admin_models[0]:
                # New format, check if id matches
                valid_model_ids = [model["id"] for model in admin_models]
                return model_id in valid_model_ids
            else:
                # Old format, directly check the model ID
                return model_id in admin_models

        return False

    def _validate_model_id(self, service_name, model_id):
        """
        Validate if the model ID is available

        Args:
            service_name: Service name
            model_id: Model ID

        Returns:
            Returns the model ID if available; otherwise, returns the default model ID
        """
        from unified_config import unified_config

        # Special handling for GPT-SoVITS: always return "Customize voice"
        if "gpt_sovits" in service_name.lower() or "sovits" in service_name.lower():
            return "Customize voice"

        # Get the current language
        if self.device_id:
            language = unified_config.get("system.language", "zh-CN", device_id=self.device_id)
        else:
            # Use constant configuration if no device_id
            language = unified_config.get("system.language", "zh-CN")

        # Use the new validation method to check if the model is available
        if self._is_model_available_for_service(service_name, model_id, language):
            return model_id

        # If the model is unavailable, get the default model
        logger.warning(f"Model {model_id} is unavailable, using default model")

        # Get the language-specific model list from constant configuration
        admin_models = unified_config.get(f"TTS.{service_name}.languages.{language}", [])

        # If no language-specific model found, try to get the model for the first available language
        if not admin_models:
            languages = unified_config.get(f"TTS.{service_name}.languages", {})
            if languages and isinstance(languages, dict):
                for _, models in languages.items():
                    if models:
                        admin_models = models
                        break

        # If model list is still not found, try to get it from the old path
        if not admin_models:
            admin_models = unified_config.get(f"TTS.{service_name}.model_id", [])

        # Return the first available model
        if admin_models and isinstance(admin_models, list):
            if isinstance(admin_models[0], dict) and "id" in admin_models[0]:
                # New format, return the id of the first model
                return admin_models[0]["id"]
            else:
                # Old format, directly return the first model
                return admin_models[0]

        # If no model is available, return the original model ID
        return model_id

    def _init_service_instance(self, service_name):
        """
        Initialize the TTS instance for the specified service

        Args:
            service_name: Service name

        Returns:
            Initialized TTS instance, returns None if initialization fails
        """
        # If the service instance already exists, return it directly
        if service_name in self.tts_instances and self.tts_instances[service_name] is not None:
            return self.tts_instances[service_name]

        logger.info(f"Initializing TTS service: {service_name}")

        # Get the model ID for the service
        model_id = self.service_model_ids.get(service_name)
        if not model_id:
            model_id = self._get_model_id_for_service(service_name)
            self.service_model_ids[service_name] = model_id

        # Validate if the model ID is available
        model_id = self._validate_model_id(service_name, model_id)
        self.service_model_ids[service_name] = model_id

        # No longer update the model ID in the configuration to avoid overwriting user settings
        # if service_name == self.service_name:
        #     config.set("TTS.model_id", model_id)

        # Create the corresponding TTS instance based on the service name
        tts_instance = None
        try:
            if "bytedance" in service_name.lower() or "volcano" in service_name.lower():
                if BytedanceTTSManager is None:
                    logger.error("BytedanceTTS module not imported")
                    return None
                tts_instance = BytedanceTTSManager(device_id=self.device_id)
                # Set PCM transmission mode
                if hasattr(tts_instance, 'use_raw_pcm'):
                    tts_instance.use_raw_pcm = self.use_raw_pcm
                logger.debug(f"Bytedance TTS initialization complete, PCM transmission mode: {'Raw PCM' if self.use_raw_pcm else 'Opus encoding'}")
            elif "azure" in service_name.lower() or "microsoft" in service_name.lower():
                if AzureTTSManager is None:
                    logger.error("AzureTTS module not imported")
                    return None
                tts_instance = AzureTTSManager(device_id=self.device_id)
                # Set PCM transmission mode
                if hasattr(tts_instance, 'use_raw_pcm'):
                    tts_instance.use_raw_pcm = self.use_raw_pcm
                logger.debug(f"Azure TTS initialization complete, PCM transmission mode: {'Raw PCM' if self.use_raw_pcm else 'Opus encoding'}")
            elif "gpt_sovits" in service_name.lower() or "sovits" in service_name.lower():
                if GPTSoVITSTTSManager is None:
                    logger.error("GPT-SoVITS TTS module not imported")
                    return None
                tts_instance = GPTSoVITSTTSManager(device_id=self.device_id)
                # Set PCM transmission mode
                if hasattr(tts_instance, 'use_raw_pcm'):
                    tts_instance.use_raw_pcm = self.use_raw_pcm
                logger.debug(f"GPT-SoVITS TTS initialization complete, PCM transmission mode: {'Raw PCM' if self.use_raw_pcm else 'Opus encoding'}")
            else:
                logger.warning(f"Unknown TTS service: {service_name}")
                return None

            # Store the TTS instance
            self.tts_instances[service_name] = tts_instance
            return tts_instance

        except Exception as e:
            logger.error(f"Failed to initialize TTS service {service_name}: {e}")
            return None

    def _init_tts_instance(self):
        """
        Initialize the TTS instance for the current service (for backward compatibility)
        """
        # Call the new initialization method
        self.tts_instance = self._init_service_instance(self.service_name)

        # If initialization fails, attempt to use other available services
        if self.tts_instance is None:
            logger.warning(f"Failed to initialize current service {self.service_name}, attempting to use other available services")
            for service in self.available_services:
                if service != self.service_name:
                    self.tts_instance = self._init_service_instance(service)
                    if self.tts_instance is not None:
                        self.service_name = service
                        self.model_id = self.service_model_ids[service]
                        break

        # If no services are available, raise an exception
        if self.tts_instance is None:
            logger.error("No available TTS services")
            raise ValueError("No available TTS services")

    def switch_service(self, service_name, model_id=None):
        """
        Switch the TTS service

        Args:
            service_name: TTS service name, e.g., "bytedance", "azure", etc.
            model_id: Model ID, if not specified, use the saved model ID

        Returns:
            Switched TTS instance
        """
        # Check service availability
        if service_name not in self.available_services:
            logger.warning(f"Service {service_name} is unavailable, cannot switch")
            return self.tts_instance

        # If the service to switch to is the same as the current service, do not switch
        if service_name.lower() == self.service_name.lower():
            logger.info(f"Already using {service_name} service, no need to switch")

            # Update the model if a new model ID is specified
            if model_id and model_id != self.model_id:
                return self.update_model(model_id)

            return self.tts_instance

        # Stop the current TTS service
        if self.tts_instance is not None:
            try:
                self.tts_instance.stop_tts()
                logger.info(f"Stopped current TTS service")
            except Exception as e:
                logger.warning(f"Failed to stop current TTS service: {e}")

        # Update the service name
        self.service_name = service_name

        # If a new model ID is specified, update the model ID
        if model_id:
            # Validate if the model ID is available
            validated_model_id = self._validate_model_id(service_name, model_id)
            self.service_model_ids[service_name] = validated_model_id
            self.model_id = validated_model_id

            # No longer update the model ID in the configuration to avoid overwriting user settings
            # config.set("TTS.model_id", validated_model_id)
        else:
            # Use the saved model ID
            self.model_id = self.service_model_ids.get(service_name)
            if not self.model_id:
                # If no saved model ID, get the default model ID
                self.model_id = self._get_model_id_for_service(service_name)
                self.service_model_ids[service_name] = self.model_id

        # No longer update the active service in the configuration to avoid overwriting user settings
        # config.set("TTS.active_service", service_name)

        # Check if the service instance is initialized
        if service_name in self.tts_instances and self.tts_instances[service_name] is not None:
            # Use the initialized service instance directly
            self.tts_instance = self.tts_instances[service_name]
            logger.info(f"Switched to initialized TTS service: {service_name}")
        else:
            # Initialize the new service instance
            logger.info(f"Initializing new TTS service: {service_name}")
            self.tts_instance = self._init_service_instance(service_name)

            # If initialization fails, attempt to use other available services
            if self.tts_instance is None:
                logger.warning(f"Failed to initialize service {service_name}, attempting to use other available services")
                for service in self.available_services:
                    if service != service_name and service in self.tts_instances and self.tts_instances[service] is not None:
                        self.service_name = service
                        self.tts_instance = self.tts_instances[service]
                        self.model_id = self.service_model_ids[service]
                        logger.info(f"Switched to backup TTS service: {service}")
                        break

        return self.tts_instance

    def update_model(self, model_id):
        """
        Update the model for the current service

        Args:
            model_id: New model ID

        Returns:
            Updated TTS instance
        """
        # Validate if the model ID is available
        validated_model_id = self._validate_model_id(self.service_name, model_id)

        # If the model ID changes, update the configuration
        if validated_model_id != self.model_id:
            # Stop the current TTS service
            if self.tts_instance is not None:
                try:
                    self.tts_instance.stop_tts()
                    logger.info(f"Stopped current TTS service")
                except Exception as e:
                    logger.warning(f"Failed to stop current TTS service: {e}")

            # Update the model ID
            self.model_id = validated_model_id
            self.service_model_ids[self.service_name] = validated_model_id

            # No longer update the model ID in the configuration to avoid overwriting user settings
            # config.set("TTS.model_id", validated_model_id)

            logger.info(f"Updated TTS model ID: {validated_model_id}")

        return self.tts_instance

    def refresh_available_services(self):
        """
        Refresh the list of available TTS services

        If the current service is no longer available, switch to an available service
        Also initializes any newly added services

        Returns:
            If the service changes, returns the new TTS instance; otherwise, returns the current instance
        """
        # Get the latest list of available services
        new_available_services = self._get_available_services()

        # If the available services list changes
        if set(new_available_services) != set(self.available_services):
            logger.info(f"Available TTS services list updated: {new_available_services}")

            # Check for newly added services
            added_services = [s for s in new_available_services if s not in self.available_services]
            if added_services:
                logger.info(f"Newly added TTS services found: {added_services}")
                # Initialize the newly added services
                for service in added_services:
                    if service not in self.tts_instances or self.tts_instances[service] is None:
                        logger.info(f"Initializing newly added TTS service: {service}")
                        model_id = self._get_model_id_for_service(service)
                        self.service_model_ids[service] = model_id
                        self._init_service_instance(service)

            # Update the available services list
            self.available_services = new_available_services

            # If the current service is no longer available, switch to an available service
            if self.service_name not in new_available_services:
                logger.warning(f"Current service {self.service_name} is no longer available, attempting to switch to an available service")

                # Preferably select an already initialized service
                new_service = None
                for service in new_available_services:
                    if service in self.tts_instances and self.tts_instances[service] is not None:
                        new_service = service
                        break

                # If no initialized service, select a new service
                if new_service is None:
                    if "bytedance" in new_available_services:
                        new_service = "bytedance"
                    elif "azure" in new_available_services:
                        new_service = "azure"
                    elif len(new_available_services) > 0:
                        new_service = new_available_services[0]
                    else:
                        logger.error("No available TTS services")
                        return self.tts_instance

                # Switch to the new service
                return self.switch_service(new_service)

        return self.tts_instance

    def text_to_speech(self, text, device_id=None, save_to_file=True):
        """
        Convert text to speech

        Args:
            text: The text to be converted to speech
            device_id: Target device ID, if provided, sends audio to the specific device via event system
            save_to_file: Whether to save the audio file, True indicates using the default path, string indicates custom path

        Returns:
            Whether playback was successful
        """
        if self.tts_instance is None:
            logger.error("TTS instance not initialized")
            return False

        # Check if service needs to be refreshed
        self.refresh_available_services()

        # If device ID is provided, send reset signal
        if device_id and event_system is not None:
            try:
                event_system.emit('tts_reset', {
                    'device_id': device_id
                })
                logger.debug(f"Sent TTS reset signal to device: {device_id}")
            except Exception as e:
                logger.warning(f"Failed to send TTS reset signal: {e}")

        # Call different methods based on the TTS service
        try:
            if "bytedance" in self.service_name.lower() or "volcano" in self.service_name.lower():
                # Check if speaker parameter is available
                if hasattr(self.tts_instance, 'text_to_speech') and 'speaker' in self.tts_instance.text_to_speech.__code__.co_varnames:
                    return self.tts_instance.text_to_speech(
                        text=text,
                        speaker=self.model_id,
                        save_to_file=save_to_file,
                        device_id=device_id,
                        use_raw_pcm=self.use_raw_pcm
                    )
                else:
                    # Try using generic parameters
                    return self.tts_instance.text_to_speech(
                        text=text,
                        save_to_file=save_to_file,
                        device_id=device_id
                    )
            elif "azure" in self.service_name.lower() or "microsoft" in self.service_name.lower():
                # Azure TTS may have different parameters
                return self.tts_instance.text_to_speech(
                    text=text,
                    save_to_file=save_to_file,
                    device_id=device_id,
                    use_raw_pcm=self.use_raw_pcm
                )
            elif "gpt_sovits" in self.service_name.lower() or "sovits" in self.service_name.lower():
                # GPT-SoVITS TTS uses synchronous interface
                return self.tts_instance.text_to_speech_sync(
                    text=text,
                    device_id=device_id,
                    save_to_file=save_to_file
                )
            else:
                # Try generic calling
                if hasattr(self.tts_instance, 'text_to_speech'):
                    # Check parameters
                    params = {}
                    if 'text' in self.tts_instance.text_to_speech.__code__.co_varnames:
                        params['text'] = text
                    if 'device_id' in self.tts_instance.text_to_speech.__code__.co_varnames:
                        params['device_id'] = device_id
                    if 'save_to_file' in self.tts_instance.text_to_speech.__code__.co_varnames:
                        params['save_to_file'] = save_to_file
                    if 'use_raw_pcm' in self.tts_instance.text_to_speech.__code__.co_varnames:
                        params['use_raw_pcm'] = self.use_raw_pcm
                    if 'speaker' in self.tts_instance.text_to_speech.__code__.co_varnames:
                        params['speaker'] = self.model_id

                    return self.tts_instance.text_to_speech(**params)
                else:
                    logger.error(f"TTS instance does not have text_to_speech method")
                    return False
        except Exception as e:
            logger.error(f"TTS conversion failed: {e}")
            return False

    def stop_tts(self):
        """
        Stop the current TTS playback
        """
        if self.tts_instance is not None:
            try:
                self.tts_instance.stop_tts()
                logger.debug("TTS playback stopped")
                return True
            except Exception as e:
                logger.warning(f"Failed to stop TTS playback: {e}")
                return False
        return False

    def set_use_raw_pcm(self, use_raw_pcm):
        """
        Set whether to use raw PCM transmission

        Args:
            use_raw_pcm: Whether to use raw PCM transmission
        """
        self.use_raw_pcm = use_raw_pcm
        if self.tts_instance is not None and hasattr(self.tts_instance, 'use_raw_pcm'):
            self.tts_instance.use_raw_pcm = use_raw_pcm
            logger.debug(f"Set TTS audio transmission mode: {'Raw PCM' if use_raw_pcm else 'Opus encoding'}")

# Create a function to initialize a TTS manager instance
def init_tts_manager(service_name=None, device_id=None):
    """
    Create a new TTS manager instance

    Args:
        service_name: Name of the TTS service, e.g., "bytedance", "azure", etc.
        device_id: Device ID for reading device-specific configurations

    Returns:
        Newly created TTS manager instance
    """
    return TTSManager(service_name, device_id)

# Test code
if __name__ == "__main__":
    # Set log level
    logger.remove()
    logger.add(lambda msg: print(msg), level="DEBUG")

    # Test TTS manager
    try:
        # Create a Bytedance TTS instance
        logger.info("Creating Bytedance TTS instance")
        tts_manager = TTSManager("bytedance")

        # Play test text
        logger.info("Playing test text")
        tts_manager.text_to_speech("Hello, this is a test of Bytedance TTS.", save_to_file="sound/test_bytedance.pcm")

        # Switch to Azure
        logger.info("Switching to Azure TTS")
        tts_manager.switch_service("azure")

        # Play test text
        logger.info("Playing test text")
        tts_manager.text_to_speech("Hello, this is a test of Azure TTS.", save_to_file="sound/test_azure.wav")

        # Test refreshing services
        logger.info("Refreshing available services")
        tts_manager.refresh_available_services()

        # Test stopping playback
        logger.info("Stopping playback")
        tts_manager.stop_tts()

        # Create another independent TTS instance
        logger.info("Creating another independent TTS instance")
        another_tts_manager = TTSManager("azure")
        another_tts_manager.text_to_speech("This is another independent TTS instance.", save_to_file="sound/test_another.wav")

        logger.info("Test completed")
    except Exception as e:
        logger.error(f"Test failed: {e}")