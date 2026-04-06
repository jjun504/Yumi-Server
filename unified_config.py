import json
import os
import threading
from datetime import datetime
from loguru import logger
from typing import Any, Dict, Optional, Union
import copy


class UnifiedConfigManager:
    """
    Unified Configuration Manager - The single configuration access point for the entire system.

    Supported configuration types:
    1. Constant configuration (const) - API keys, service configurations, etc.
    2. Device configuration (device) - Device-specific runtime configurations.
    3. User configuration (user) - User personalized configurations.
    4. System configuration (system) - Global system configurations.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Single instance mode to ensure the global unique configuration manager"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
            
        self._initialized = True
        self._config_cache = {}
        self._cache_lock = threading.RLock()
        
        # Configuration file path definitions
        self.paths = {
            'const': 'config/const_settings.json',
            'system': 'config/system_settings.json',
            'device_template': 'config/default_setting.json',
            'device_dir': 'device_configs',
            'user_dir': 'user'
        }

        # Device details file path patterns
        self.device_details_patterns = [
            "status", "last_seen", "authenticated", "ip", "device_id",
            "model", "user_id", "online", "sid"
        ]
        
        # Ensure necessary directories exist
        self._ensure_directories()
        
        # Initialize default configurations
        self._init_default_configs()
        
        logger.info("Unified Configuration Manager initialization complete")
    
    def _ensure_directories(self):
        """Ensure all necessary directories exist"""
        directories = [
            'config',
            'device_configs', 
            'user'
        ]
        
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
    
    def _init_default_configs(self):
        """Initialize default configuration files"""
        # Constant configuration default values
        default_const_config = {
            "wake_word": {
                "windows_enable": False,
                "pi_enable": True,
                "windows_api_key": "",
                "pi_api_key": ""
            },
            "STT": {
                "azure": {
                    "api_key": "",
                    "region": "southeastasia"
                }
            },
            "speech_services": {
                "azure_tts": {
                    "api_key": "",
                    "region": "southeastasia"
                },
                "bytedance_tts": {
                    "app_id": "",
                    "token": ""
                },
                "gpt_sovits": {
                    "base_url": "http://127.0.0.1:9880"
                }
            },
            "llm_services": {
                "use_openai": False,
                "use_deepseek": False,
                "use_groq": True,
                "use_gpt4f": False,
                "use_gemini": False,
                "openai": {
                    "api_key": ""
                },
                "deepseek": {
                    "api_key": ""
                },
                "groq": {
                    "api_key": "",
                    "model_api_key": "",
                    "intent_model_api_key": ""
                },
                "gemini": {
                    "api_key": ""
                }
            },
            "web_search": {
                "tavily_api_key": ""
            },
            "weather": {
                "openweather_api_key": "",
                "local_country": "MY"
            },
            "music_player": {
                "enabled": True,
                "spotify": {
                    "api_key": ""
                },
                "youtube": {
                    "api_key": "",
                    "channel_id": ""
                }
            },
            "TTS": {
                "use_azure": True,
                "use_bytedance": True,
                "use_sovits": True,
                "languages": {
                    "zh-CN": {
                        "azure": ["zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural"],
                        "bytedance": ["zh_female_wanwanxiaohe_moon_bigtts", "ICL_zh_female_chengshujiejie_tob"],
                        "sovits": ["Customize voice"]
                    },
                    "en-US": {
                        "azure": ["en-US-JennyNeural", "en-US-AriaNeural"],
                        "bytedance": ["en_female_samc_bigtts"],
                        "sovits": ["Customize voice"]
                    }
                }
            }
        }
        
        # System configuration default values
        default_system_config = {
            "server": {
                "host": "0.0.0.0",
                "port": 5000,
                "debug": False
            },
            "database": {
                "host": "localhost",
                "user": "root",
                "password": "",
                "database": "smart_assistant",
                "charset": "utf8mb4"
            },
            "mqtt": {
                "broker": "broker.emqx.io",
                "port": 1883,
                "username": None,
                "password": None,
                "topic_prefix": "smart0337187"
            },
            "udp": {
                "port": 8884,
                "discovery_port": 50000,
                "session_timeout": 3600.0
            }
        }
        
        # Create default configuration files (if not exist)
        self._create_default_file(self.paths['const'], default_const_config)
        self._create_default_file(self.paths['system'], default_system_config)
    
    def _create_default_file(self, file_path: str, default_config: dict):
        """Create default configuration file"""
        if not os.path.exists(file_path):
            try:
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(default_config, f, ensure_ascii=False, indent=4)
                logger.info(f"Created default configuration file: {file_path}")
            except Exception as e:
                logger.error(f"Failed to create default configuration file {file_path}: {e}")

    def _determine_config_type(self, path: str, device_id: Optional[str] = None,
                              user_id: Optional[str] = None) -> str:
        """
        Automatically determine the configuration type based on the path

        Args:
            path: Configuration path, such as "system.device_id"
            device_id: Device ID
            user_id: User ID

        Returns:
            str: Configuration type ("const", "device", "user", "system")
        """
        # Constant configuration path patterns - These configurations are stored in config/const_settings.json
        const_patterns = [
            "wake_word.windows_api_key", "wake_word.pi_api_key",
            "STT.azure", "speech_services", "llm_services",
            "web_search", "weather.openweather_api_key", "weather.local_country",
            "music_player.spotify", "music_player.youtube",
            "TTS.use_", "TTS.languages",
            "server.secret_key", "server.debug", "server.host", "server.port",
            "email", "oss", "versions"
        ]

        # User configuration path patterns - These configurations are stored in user/{user_id}/{device_id}/config.json
        user_patterns = [
            # Removed user_personalization and device_role_personalization, they are now stored in device configuration
        ]

        # System configuration path patterns - These configurations are stored in config/system_settings.json
        system_patterns = [
            "database", "mqtt.broker", "mqtt.port", "mqtt.username", "mqtt.password",
            "udp.port", "udp.discovery_port", "udp.session_timeout"
        ]

        # Device configuration path patterns - These configurations are stored in device_configs/{device_id}/new_settings.json
        device_patterns = [
            "system.device_id", "system.password", "system.user_id", "system.boot_time",
            "system.model", "system.version", "system.language", "system.status", "system.log_level",
            "wake_word.enabled", "STT.enabled", "STT.active_service", "STT.language",
            "TTS.enabled", "TTS.active_service", "TTS.model_id", "TTS.azure.model_id", "TTS.bytedance.model_id", "TTS.sovits.model_id", "TTS.sovits.base_url",
            "LLM.enabled", "LLM.active_service", "LLM.model_id", "LLM.temperature", "LLM.max_tokens",
            "music.enabled", "music.resume_play", "music.tts_notify",
            "time_notify", "schedule_notify", "weather.enabled", "weather.location",
            "state_flags", "audio_settings", "interaction", "devices",
            "mqtt.client_id_prefix", "mqtt.topic_prefix",
            "user_personalization", "device_role_personalization"
        ]

        # Check if it is a constant configuration
        for pattern in const_patterns:
            if path.startswith(pattern):
                return "const"

        # Check if it is a user configuration (requires user_id)
        for pattern in user_patterns:
            if path.startswith(pattern):
                if user_id:
                    return "user"
                else:
                    raise ValueError(f"User configuration path '{path}' requires user_id parameter")

        # Check if it is a system configuration
        for pattern in system_patterns:
            if path.startswith(pattern):
                return "system"

        # Check if it is a device configuration
        for pattern in device_patterns:
            if path.startswith(pattern):
                if device_id:
                    return "device"
                else:
                    raise ValueError(f"Device configuration path '{path}' requires device_id parameter")

        # Check if it is a device details configuration (details.json)
        for pattern in self.device_details_patterns:
            if path == pattern or path.startswith(f"{pattern}."):
                if device_id:
                    return "device_details"
                else:
                    raise ValueError(f"Device details path '{path}' requires device_id parameter")

        # If no explicit pattern is matched, determine based on parameters
        if user_id and device_id:
            return "user"
        elif device_id:
            return "device"
        else:
            # Default to constant configuration, but give a warning
            logger.warning(f"Unable to determine configuration type, path: {path}, defaulting to constant configuration")
            return "const"

    def _get_config_file_path(self, config_type: str, device_id: Optional[str] = None,
                             user_id: Optional[str] = None) -> str:
        """
        Get configuration file path

        Args:
            config_type: Configuration type
            device_id: Device ID
            user_id: User ID

        Returns:
            str: Configuration file path
        """
        if config_type == "const":
            return self.paths['const']
        elif config_type == "system":
            return self.paths['system']
        elif config_type == "device":
            if not device_id:
                raise ValueError("Device configuration requires device_id")
            return os.path.join(self.paths['device_dir'], device_id, "new_settings.json")
        elif config_type == "device_details":
            if not device_id:
                raise ValueError("Device details require device_id")
            return os.path.join(self.paths['device_dir'], device_id, "details.json")
        elif config_type == "user":
            if not user_id or not device_id:
                raise ValueError("User configuration requires user_id and device_id")
            return os.path.join(self.paths['user_dir'], user_id, device_id, "config.json")
        else:
            raise ValueError(f"Unsupported configuration type: {config_type}")

    def _load_config_file(self, file_path: str) -> dict:
        """
        Load configuration file

        Args:
            file_path: Configuration file path

        Returns:
            dict: Configuration data
        """
        cache_key = file_path

        with self._cache_lock:
            # Check cache
            if cache_key in self._config_cache:
                cached_data, cached_time = self._config_cache[cache_key]
                # Check if the file has been modified
                if os.path.exists(file_path):
                    file_mtime = os.path.getmtime(file_path)
                    if file_mtime <= cached_time:
                        return copy.deepcopy(cached_data)

            # Load file
            try:
                if os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        config_data = json.load(f)

                    # Update cache
                    self._config_cache[cache_key] = (
                        copy.deepcopy(config_data),
                        os.path.getmtime(file_path)
                    )

                    return config_data
                else:
                    logger.warning(f"Configuration file does not exist: {file_path}")
                    return {}

            except Exception as e:
                logger.error(f"Failed to load configuration file {file_path}: {e}")
                return {}

    def _save_config_file(self, file_path: str, config_data: dict):
        """
        Save configuration file

        Args:
            file_path: Configuration file path
            config_data: Configuration data
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            # Save file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)

            # Update cache
            with self._cache_lock:
                self._config_cache[file_path] = (
                    copy.deepcopy(config_data),
                    os.path.getmtime(file_path)
                )

            # logger.debug(f"Configuration file saved: {file_path}")

        except Exception as e:
            logger.error(f"Failed to save configuration file {file_path}: {e}")
            raise

    def _get_nested_value(self, data: dict, path: str, default: Any = None) -> Any:
        """
        Get value from nested dictionary

        Args:
            data: Data dictionary
            path: Path, such as "system.device_id"
            default: Default value

        Returns:
            Any: Configuration value
        """
        keys = path.split('.')
        current = data

        try:
            for key in keys:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    return default
            return current
        except Exception:
            return default

    def _set_nested_value(self, data: dict, path: str, value: Any) -> dict:
        """
        Set value in nested dictionary

        Args:
            data: Data dictionary
            path: Path, such as "system.device_id"
            value: Value to set

        Returns:
            dict: Updated data dictionary
        """
        keys = path.split('.')
        current = data

        # Create nested structure
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            elif not isinstance(current[key], dict):
                current[key] = {}
            current = current[key]

        # Set final value
        current[keys[-1]] = value
        return data

    def get(self, path: str, default: Any = None, device_id: Optional[str] = None,
            user_id: Optional[str] = None, config_type: Optional[str] = None) -> Any:
        """
        Unified configuration retrieval interface

        Args:
            path: Configuration path, such as "system.device_id" or "llm_services.groq.api_key"
            default: Default value
            device_id: Device ID (for device-specific configurations)
            user_id: User ID (for user-specific configurations)
            config_type: Force specify configuration type ("const", "device", "user", "system")

        Returns:
            Any: Configuration value

        Examples:
            # Get constant configuration
            api_key = config.get("llm_services.groq.api_key")

            # Get device configuration
            device_name = config.get("system.device_id", device_id="mixue001")

            # Get personalized configuration (now stored in device configuration)
            user_name = config.get("user_personalization.name", device_id="mixue001")
        """
        try:
            # Determine configuration type
            if config_type is None:
                config_type = self._determine_config_type(path, device_id, user_id)

            # Get configuration file path
            file_path = self._get_config_file_path(config_type, device_id, user_id)

            # Load configuration data
            config_data = self._load_config_file(file_path)

            # Get nested value
            value = self._get_nested_value(config_data, path, default)

            # logger.debug(f"Get configuration: {path} = {value} (Type: {config_type}, File: {file_path})")
            return value

        except Exception as e:
            logger.error(f"Failed to get configuration {path}: {e}")
            return default

    def set(self, path: str, value: Any, device_id: Optional[str] = None,
            user_id: Optional[str] = None, config_type: Optional[str] = None) -> bool:
        """
        Unified configuration setting interface

        Args:
            path: Configuration path, such as "system.device_id"
            value: Value to set
            device_id: Device ID (for device-specific configurations)
            user_id: User ID (for user-specific configurations)
            config_type: Force specify configuration type ("const", "device", "user", "system")

        Returns:
            bool: Whether the setting was successful

        Examples:
            # Set constant configuration
            config.set("llm_services.groq.api_key", "new_api_key")

            # Set device configuration
            config.set("system.device_id", "mixue001", device_id="mixue001")

            # Set personalized configuration (now stored in device configuration)
            config.set("user_personalization.name", "张三", device_id="mixue001")
        """
        try:
            # Determine configuration type
            if config_type is None:
                config_type = self._determine_config_type(path, device_id, user_id)

            # Get configuration file path
            file_path = self._get_config_file_path(config_type, device_id, user_id)

            # Load existing configuration data
            config_data = self._load_config_file(file_path)

            # Set nested value
            updated_data = self._set_nested_value(config_data, path, value)

            # Save configuration file
            self._save_config_file(file_path, updated_data)

            # logger.debug(f"Set configuration: {path} = {value} (Type: {config_type}, File: {file_path})")
            return True

        except Exception as e:
            logger.error(f"Failed to set configuration {path}: {e}")
            return False

    def get_section(self, section: str, device_id: Optional[str] = None,
                   user_id: Optional[str] = None, config_type: Optional[str] = None) -> dict:
        """
        Get entire configuration section

        Args:
            section: Section name, such as "system", "TTS"
            device_id: Device ID
            user_id: User ID
            config_type: Configuration type

        Returns:
            dict: Section data
        """
        return self.get(section, {}, device_id, user_id, config_type)

    def update_section(self, section: str, data: dict, device_id: Optional[str] = None,
                      user_id: Optional[str] = None, config_type: Optional[str] = None) -> bool:
        """
        Update entire configuration section

        Args:
            section: Section name
            data: New configuration data
            device_id: Device ID
            user_id: User ID
            config_type: Configuration type

        Returns:
            bool: Whether the update was successful
        """
        return self.set(section, data, device_id, user_id, config_type)

    def ensure_device_config(self, device_id: str) -> bool:
        """
        Ensure device configuration file exists, create from template if not

        Args:
            device_id: Device ID

        Returns:
            bool: Whether successfully ensured configuration exists
        """
        try:
            device_config_path = self._get_config_file_path("device", device_id)

            if not os.path.exists(device_config_path):
                # Create device configuration from template
                template_path = self.paths['device_template']
                if os.path.exists(template_path):
                    template_config = self._load_config_file(template_path)
                else:
                    # Use default device configuration
                    template_config = {
                        "system": {
                            "device_id": device_id,
                            "password": "654321",
                            "user_id": None,
                            "boot_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "model": "raspberry_pi",
                            "version": "1.0.0",
                            "language": "chinese",
                            "status": "offline",
                            "log_level": "DEBUG"
                        },
                        "wake_word": {"enabled": True},
                        "STT": {
                            "enabled": True,
                            "active_service": "azure",
                            "language": "zh-CN"
                        },
                        "TTS": {
                            "enabled": True,
                            "active_service": "bytedance",
                            "model_id": "ICL_zh_female_chengshujiejie_tob",
                            "language": "zh-CN",
                            "azure": {
                                "model_id": "zh-CN-XiaoxiaoNeural"
                            },
                            "bytedance": {
                                "model_id": "ICL_zh_female_chengshujiejie_tob"
                            },
                            "sovits": {
                                "model_id": "Customize voice",
                                "base_url": "http://127.0.0.1:9880"
                            }
                        },
                        "LLM": {
                            "enabled": True,
                            "active_service": "groq",
                            "model_id": "meta-llama/llama-4-scout-17b-16e-instruct",
                            "temperature": 0.9,
                            "max_tokens": 128,
                            "summary_tokens": 3000,
                            "last_messages_num": 2,
                            "openai": {
                                "model_id": "gpt-4o-mini"
                            },
                            "deepseek": {
                                "model_id": "deepseek-chat"
                            },
                            "groq": {
                                "model_id": "meta-llama/llama-4-scout-17b-16e-instruct"
                            }
                        },
                        "music": {
                            "enabled": True,
                            "resume_play": True,
                            "tts_notify": True
                        },
                        "audio_settings": {
                            "general_volume": 70,
                            "music_volume": 50,
                            "notification_volume": 70
                        },
                        "state_flags": {
                            "chat_active": True,
                            "notification_active": False,
                            "mqtt_message_active": False,
                            "recording_active": False,
                            "stt_active": False,
                            "llm_active": False,
                            "tts_active": False
                        }
                    }

                # Update device ID
                if "system" in template_config:
                    template_config["system"]["device_id"] = device_id

                # Save device configuration
                self._save_config_file(device_config_path, template_config)
                logger.info(f"Configuration file created for device {device_id}")

            return True

        except Exception as e:
            logger.error(f"Ensure device configuration failed {device_id}: {e}")
            return False

    def ensure_user_config(self, user_id: str, device_id: str) -> bool:
        """
        Ensure user configuration file exists

        Args:
            user_id: User ID
            device_id: Device ID

        Returns:
            bool: Whether successfully ensured configuration exists
        """
        try:
            user_config_path = self._get_config_file_path("user", device_id, user_id)

            if not os.path.exists(user_config_path):
                # Create default user configuration
                default_user_config = {
                    "user_personalization": {
                        "name": "",
                        "age": "",
                        "hobbies": [],
                        "region": "",
                        "profile": ""
                    },
                    "device_role_personalization": {
                        "name": "",
                        "age": "",
                        "relationship": "",
                        "personality": "",
                        "background": ""
                    }
                }

                self._save_config_file(user_config_path, default_user_config)
                logger.info(f"Configuration file created for user {user_id} device {device_id}")

            return True

        except Exception as e:
            logger.error(f"Ensure user configuration failed {user_id}/{device_id}: {e}")
            return False

    def clear_cache(self, file_path: Optional[str] = None):
        """
        Clear configuration cache

        Args:
            file_path: Optional, specify the file path to clear. If None, clear all cache
        """
        with self._cache_lock:
            if file_path:
                if file_path in self._config_cache:
                    del self._config_cache[file_path]
                    logger.info(f"Configuration cache cleared: {file_path}")
            else:
                self._config_cache.clear()
                logger.info("Configuration cache cleared")

    def reload_config(self, config_type: Optional[str] = None,
                     device_id: Optional[str] = None, user_id: Optional[str] = None):
        """
        Reload configuration file

        Args:
            config_type: Configuration type, None means reload all
            device_id: Device ID
            user_id: User ID
        """
        if config_type is None:
            self.clear_cache()
        else:
            try:
                file_path = self._get_config_file_path(config_type, device_id, user_id)
                with self._cache_lock:
                    if file_path in self._config_cache:
                        del self._config_cache[file_path]
                logger.info(f"Configuration reloaded: {config_type}")
            except Exception as e:
                logger.error(f"Failed to reload configuration: {e}")

    def validate_config_access(self, path: str, device_id: Optional[str] = None,
                              user_id: Optional[str] = None) -> tuple[bool, str]:
        """
        Validate configuration access

        Args:
            path: Configuration path
            device_id: Device ID
            user_id: User ID

        Returns:
            tuple[bool, str]: (Is valid, Error message)
        """
        try:
            config_type = self._determine_config_type(path, device_id, user_id)

            # Validate necessary parameters
            if config_type == "device" and not device_id:
                return False, f"Device configuration path '{path}' requires device_id parameter"

            if config_type == "user" and (not user_id or not device_id):
                return False, f"User configuration path '{path}' requires user_id and device_id parameters"

            # Validate configuration file path
            file_path = self._get_config_file_path(config_type, device_id, user_id)

            return True, f"Configuration access valid: {path} -> {config_type} -> {file_path}"

        except Exception as e:
            return False, f"Configuration access validation failed: {e}"

    def get_config_info(self, path: str, device_id: Optional[str] = None,
                       user_id: Optional[str] = None) -> dict:
        """
        Get configuration information (for debugging)

        Args:
            path: Configuration path
            device_id: Device ID
            user_id: User ID

        Returns:
            dict: Configuration information
        """
        try:
            config_type = self._determine_config_type(path, device_id, user_id)
            file_path = self._get_config_file_path(config_type, device_id, user_id)
            file_exists = os.path.exists(file_path)

            return {
                "path": path,
                "config_type": config_type,
                "file_path": file_path,
                "file_exists": file_exists,
                "device_id": device_id,
                "user_id": user_id,
                "cached": file_path in self._config_cache
            }
        except Exception as e:
            return {
                "path": path,
                "error": str(e),
                "device_id": device_id,
                "user_id": user_id
            }


# Create a global unified configuration manager instance
unified_config = UnifiedConfigManager()


# Backward-compatible convenience functions
def get_config(path: str, default: Any = None, device_id: Optional[str] = None,
               user_id: Optional[str] = None) -> Any:
    """Convenient configuration retrieval function"""
    return unified_config.get(path, default, device_id, user_id)


def set_config(path: str, value: Any, device_id: Optional[str] = None,
               user_id: Optional[str] = None) -> bool:
    """Convenient configuration setting function"""
    return unified_config.set(path, value, device_id, user_id)


def validate_config(path: str, device_id: Optional[str] = None,
                   user_id: Optional[str] = None) -> tuple[bool, str]:
    """Validate configuration access"""
    return unified_config.validate_config_access(path, device_id, user_id)


def debug_config(path: str, device_id: Optional[str] = None,
                user_id: Optional[str] = None) -> dict:
    """Debug configuration information"""
    return unified_config.get_config_info(path, device_id, user_id)


# Specialized functions for device details management
def get_device_details(device_id: str, field: Optional[str] = None, default: Any = None) -> Any:
    """
    Retrieve device details

    Args:
        device_id: Device ID
        field: Specific field name, such as "status", "ip", "user_id", etc. If None, return all details
        default: Default value

    Returns:
        Any: Device details

    Examples:
        # Retrieve device status
        status = get_device_details("mixue001", "status")

        # Retrieve device IP
        ip = get_device_details("mixue001", "ip")

        # Retrieve all device details
        details = get_device_details("mixue001")
    """
    if field:
        return unified_config.get(field, default, device_id=device_id, config_type="device_details")
    else:
        # Retrieve the entire device details file
        file_path = unified_config._get_config_file_path("device_details", device_id)
        return unified_config._load_config_file(file_path)

def set_device_details(device_id: str, field: str, value: Any) -> bool:
    """
    Set device details

    Args:
        device_id: Device ID
        field: Field name
        value: Value

    Returns:
        bool: Whether the setting was successful

    Examples:
        # Set device status
        set_device_details("mixue001", "status", "online")

        # Set device IP
        set_device_details("mixue001", "ip", "192.168.1.100")

        # Set user binding
        set_device_details("mixue001", "user_id", "user001")
    """
    return unified_config.set(field, value, device_id=device_id, config_type="device_details")

def update_device_details(device_id: str, details: dict, exclude_fields: Optional[list] = None) -> bool:
    """
    Batch update device details

    Args:
        device_id: Device ID
        details: Dictionary of details to update
        exclude_fields: List of fields to exclude, such as ["sid", "password"]

    Returns:
        bool: Whether the update was successful

    Examples:
        # Batch update device information
        details = {
            "status": "online",
            "ip": "192.168.1.100",
            "last_seen": time.time()
        }
        update_device_details("mixue001", details)

        # Exclude sensitive fields
        update_device_details("mixue001", details, exclude_fields=["password", "sid"])
    """
    try:
        if exclude_fields:
            details = {k: v for k, v in details.items() if k not in exclude_fields}

        # Retrieve existing details
        current_details = get_device_details(device_id) or {}

        # Merge updates
        current_details.update(details)

        # Save the entire details
        file_path = unified_config._get_config_file_path("device_details", device_id)
        unified_config._save_config_file(file_path, current_details)

        logger.debug(f"Batch updated device details: {device_id}, fields: {list(details.keys())}")
        return True

    except Exception as e:
        logger.error(f"Failed to batch update device details {device_id}: {e}")
        return False

def ensure_device_details(device_id: str) -> bool:
    """
    Ensure the device details file exists

    Args:
        device_id: Device ID

    Returns:
        bool: Whether successfully ensured details exist
    """
    try:
        details_path = unified_config._get_config_file_path("device_details", device_id)

        if not os.path.exists(details_path):
            # Create default device details
            default_details = {
                "device_id": device_id,
                "status": "offline",
                "authenticated": False,
                "ip": "",
                "model": "raspberry_pi",
                "user_id": None,
                "last_seen": 0,
                "online": False
            }

            unified_config._save_config_file(details_path, default_details)
            logger.info(f"Details file created for device {device_id}")

        return True

    except Exception as e:
        logger.error(f"Failed to ensure device details {device_id}: {e}")
        return False