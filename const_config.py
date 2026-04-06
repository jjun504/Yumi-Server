import json
import os
from datetime import datetime
from loguru import logger
import copy
from typing import Any, Dict

# 配置文件路径
CONFIG_FILE_PATH = "config/const_settings.json"

# 确保配置目录存在
os.makedirs(os.path.dirname(CONFIG_FILE_PATH), exist_ok=True)

# 默认配置
DEFAULT_CONFIG = {
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
    "TTS": {
        "use_azure": True,
        "use_bytedance": True,
        "use_sovits": False,
        "azure": {
            "api_key": "",
            "region": "southeastasia",
            "languages": {
                "zh-CN": [
                    {
                        "id": "zh-CN-XiaoxiaoNeural",
                        "name": "晓晓 (女声)"
                    },
                    {
                        "id": "zh-CN-YunxiNeural",
                        "name": "云希 (男声)"
                    }
                ],
                "en-US": [
                    {
                        "id": "en-US-GuyNeural",
                        "name": "Guy (Male)"
                    },
                    {
                        "id": "en-US-AriaNeural",
                        "name": "Aria (Female)"
                    }
                ]
            }
        },
        "bytedance": {
            "app_id": "",
            "token": "",
            "languages": {
                "zh-CN": [
                    {
                        "id": "zh_female_wanwanxiaohe_moon_bigtts",
                        "name": "婉婉小荷 (女声)"
                    }
                ]
            }
        }
    },
    "LLM": {
        "use_openai": True,
        "use_deepseek": False,
        "use_groq": True,
        "openai": {
            "api_key": "",
            "model_id": [
                {
                    "id": "gpt-4o-mini",
                    "name": "GPT-4o Mini"
                }
            ]
        },
        "deepseek": {
            "api_key": "",
            "model_id": [
                {
                    "id": "deepseek-chat",
                    "name": "Deepseek Chat"
                }
            ]
        },
        "groq": {
            "api_key": "",
            "model_api_key": "",
            "intent_model_api_key": "",
            "model_id": [
                {
                    "id": "llama-3.3-70b-versatile",
                    "name": "Llama 3.3 70B"
                }
            ]
        }
    },
    "web_search": {
        "tavily_api_key": ""
    },
    "weather": {
        "api_key": "",
        "location": ""
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
    "server": {
        "secret_key": "",
        "debug": False,
        "host": "0.0.0.0",
        "port": 5000
    },
    "email": {
        "resend_api_key": "",
        "email_from": "Yumi <noreply@resend.dev>",
        "otp_length": 6,
        "otp_expire_seconds": 300
    },
    "oss": {
        "access_key_id": "",
        "access_key_secret": "",
        "endpoint": "",
        "bucket_name": "",
        "bucket_url": ""
    },
    "versions": {
        "server_url": "",
        "token": ""
    }
}


class ConstConfigManager:
    """
    常量配置管理器类，用于管理系统常量配置

    提供了简单的接口来获取和设置配置项，支持多级路径访问
    例如：const_config.get("speech_services.azure_tts.api_key")
    """

    def __init__(self, default_config: Dict[str, Any] = None):
        """
        初始化配置管理器

        Args:
            default_config: 默认配置，如果不提供则使用 DEFAULT_CONFIG
        """
        self.config = copy.deepcopy(default_config or DEFAULT_CONFIG)
        self.callbacks = []  # 回调函数列表

        # 初始化时尝试读取配置
        self.read()

    def save(self) -> bool:
        """
        保存当前配置到文件

        Returns:
            bool: 保存是否成功
        """
        try:
            # 保存到文件
            with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)

            logger.success(f"常量配置已成功保存到 {CONFIG_FILE_PATH}")
            return True
        except Exception as e:
            logger.error(f"保存常量配置失败: {e}")
            return False

    def read(self) -> bool:
        """
        从文件读取配置

        Returns:
            bool: 读取是否成功
        """
        if not os.path.exists(CONFIG_FILE_PATH):
            logger.warning(f"常量配置文件 {CONFIG_FILE_PATH} 不存在，将使用默认配置")
            # 首次运行时保存默认配置
            self.save()
            return False

        try:
            with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)

            # 递归更新配置
            self._update_config_recursive(self.config, loaded_config)

            logger.success(f"成功从 {CONFIG_FILE_PATH} 加载常量配置")
            return True
        except Exception as e:
            logger.error(f"读取常量配置失败: {e}，将使用默认配置")
            return False

    def _update_config_recursive(self, target: Dict[str, Any], source: Dict[str, Any]) -> None:
        """
        递归更新配置

        Args:
            target: 目标配置
            source: 源配置
        """
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                # 如果两者都是字典，递归更新
                self._update_config_recursive(target[key], value)
            else:
                # 否则直接替换
                target[key] = copy.deepcopy(value)

    def get(self, path: str, default: Any = None) -> Any:
        """
        获取配置项

        支持使用点号分隔的路径，例如 "speech_services.azure_tts.api_key"

        Args:
            path: 配置项路径
            default: 如果配置项不存在，返回的默认值

        Returns:
            配置项的值，如果不存在则返回默认值
        """
        parts = path.split('.')
        current = self.config

        try:
            for part in parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return default
            return current
        except Exception as e:
            logger.error(f"获取常量配置项 {path} 失败: {e}")
            return default

    def set(self, path: str, value: Any) -> bool:
        """
        设置配置项

        支持使用点号分隔的路径，例如 "speech_services.azure_tts.api_key"

        Args:
            path: 配置项路径
            value: 要设置的值

        Returns:
            bool: 设置是否成功
        """
        parts = path.split('.')
        current = self.config

        try:
            # 遍历路径直到倒数第二个部分
            for i, part in enumerate(parts[:-1]):
                if part not in current:
                    # 如果路径不存在，创建一个新的字典
                    current[part] = {}
                elif not isinstance(current[part], dict):
                    # 如果路径存在但不是字典，替换为字典
                    current[part] = {}

                current = current[part]

            # 设置最后一个部分的值
            last_part = parts[-1]
            if last_part in current and current[last_part] == value:
                # 值没有变化，不需要更新
                return True

            # 更新值
            current[last_part] = value

            # 记录变更
            self._log_change(path, value)

            # 触发回调
            self._trigger_callbacks({path: value})

            # 自动保存配置
            self.save()

            return True
        except Exception as e:
            logger.error(f"设置常量配置项 {path} 失败: {e}")
            return False

    def _log_change(self, path: str, value: Any) -> None:
        """
        记录配置变更

        Args:
            path: 配置项路径
            value: 新值
        """
        logger.success(f"[const_config] {path} = {value}")

    def register_callback(self, callback) -> None:
        """
        注册回调函数

        当配置变更时，会调用回调函数

        Args:
            callback: 回调函数，接受一个参数 changed_params
        """
        self.callbacks.append(callback)

    def _trigger_callbacks(self, changed_params: Dict[str, Any]) -> None:
        """
        触发所有回调函数

        Args:
            changed_params: 变更的参数
        """
        for callback in self.callbacks:
            try:
                callback(changed_params)
            except Exception as e:
                logger.error(f"触发回调函数失败: {e}")

    # 兼容旧版本的方法 - 直接访问常量
    def __getattr__(self, name):
        """
        兼容旧版本的访问方式，允许直接通过属性访问常量

        例如：const_config.PICOVOICE_API_KEY

        Args:
            name: 属性名

        Returns:
            属性值
        """
        # 定义旧常量名到新路径的映射
        attr_mapping = {
            # Wake Word
            "PICOVOICE_ENABLE": "wake_word.windows_enable",
            "WINDOWS_ENABLE": "wake_word.windows_enable",
            "PI_ENABLE": "wake_word.pi_enable",
            "PICOVOICE_API_KEY": "wake_word.windows_api_key",
            "PI_PICOVOICE_API_KEY": "wake_word.pi_api_key",

            # Speech Services
            "STT_API_KEY": "STT.azure.api_key",
            "STT_REGION": "STT.azure.region",
            "TTS_STREAM_API_KEY": "TTS.azure.api_key",
            "TTS_STREAM_REGION": "TTS.azure.region",
            "VOLCANO_TTS_APP_ID": "TTS.bytedance.app_id",
            "VOLCANO_TTS_TOKEN": "TTS.bytedance.token",

            # Web Search
            "TAVILY_API_KEY": "web_search.tavily_api_key",

            # LLM Services
            "USE_OPENAI": "LLM.use_openai",
            "USE_DEEPSEEK": "LLM.use_deepseek",
            "USE_GROQ": "LLM.use_groq",
            "USE_GPT4F": "LLM.use_gpt4f",
            "USE_GEMINI": "LLM.use_gemini",
            "OPENAI_API_KEY": "LLM.openai.api_key",
            "DEEPSEEK_API_KEY": "LLM.deepseek.api_key",
            "GROQ_API_KEY": "llm_services.groq.api_key",
            "GROQ_MODEL_API_KEY": "llm_services.groq.model_api_key",
            "GROQ_INTENT_MODEL_API_KEY": "llm_services.groq.intent_model_api_key",
            "LANGCHAIN_API_KEY": "LLM.langchain.api_key",
            "GEMINI_API_KEY": "LLM.gemini.api_key",

            # Weather
            "OPEN_WEATHER_API_KEY": "weather.api_key",
            "LOCAL_COUNTRY": "weather.location",

            # Music Player
            "MUSIC_PLAYER_ENABLE": "music_player.enabled",
            "SPOTIFY_API_KEY": "music_player.spotify.api_key",
            "YOUTUBE_API_KEY": "music_player.youtube.api_key",
            "YOUTUBE_CHANNEL_ID": "music_player.youtube.channel_id",

            # TTS Services
            "USE_AZURE": "TTS.use_azure",
            "USE_BYTEDANCE": "TTS.use_bytedance",
            "USE_SOVITS": "TTS.use_sovits",

            # Server Configuration
            "SECRET_KEY": "server.secret_key",
            "SERVER_DEBUG": "server.debug",
            "SERVER_HOST": "server.host",
            "SERVER_PORT": "server.port",

            # Email Configuration
            "RESEND_API_KEY": "email.resend_api_key",
            "EMAIL_FROM": "email.email_from",
            "OTP_LENGTH": "email.otp_length",
            "OTP_EXPIRE_SECONDS": "email.otp_expire_seconds",

            # OSS Configuration
            "OSS_ACCESS_KEY_ID": "oss.access_key_id",
            "OSS_ACCESS_KEY_SECRET": "oss.access_key_secret",
            "OSS_ENDPOINT": "oss.endpoint",
            "OSS_BUCKET_NAME": "oss.bucket_name",
            "OSS_BUCKET_URL": "oss.bucket_url",

            # Versions Configuration
            "VERSIONS_SERVER_URL": "versions.server_url",
            "VERSIONS_TOKEN": "versions.token"
        }

        if name in attr_mapping:
            return self.get(attr_mapping[name])

        # 如果没有找到映射，尝试在配置中直接查找
        for section in self.config:
            if name.lower() in section.lower():
                for key in self.config[section]:
                    if name.lower() == key.lower():
                        return self.config[section][key]

        # 如果仍然没有找到，抛出属性错误
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")


# 创建单例
const_config = ConstConfigManager(DEFAULT_CONFIG)

# 为了兼容旧代码，将常量暴露为模块级变量
PICOVOICE_ENABLE = const_config.PICOVOICE_ENABLE
WINDOWS_ENABLE = const_config.WINDOWS_ENABLE
PI_ENABLE = const_config.PI_ENABLE
PICOVOICE_API_KEY = const_config.PICOVOICE_API_KEY
PI_PICOVOICE_API_KEY = const_config.PI_PICOVOICE_API_KEY

STT_API_KEY = const_config.STT_API_KEY
STT_REGION = const_config.STT_REGION
TTS_STREAM_API_KEY = const_config.TTS_STREAM_API_KEY
TTS_STREAM_REGION = const_config.TTS_STREAM_REGION
VOLCANO_TTS_APP_ID = const_config.VOLCANO_TTS_APP_ID
VOLCANO_TTS_TOKEN = const_config.VOLCANO_TTS_TOKEN

TAVILY_API_KEY = const_config.TAVILY_API_KEY

USE_OPENAI = const_config.USE_OPENAI
USE_DEEPSEEK = const_config.USE_DEEPSEEK
USE_GROQ = const_config.USE_GROQ
USE_GPT4F = const_config.USE_GPT4F
USE_GEMINI = const_config.USE_GEMINI
OPENAI_API_KEY = const_config.OPENAI_API_KEY
DEEPSEEK_API_KEY = const_config.DEEPSEEK_API_KEY
GROQ_API_KEY = const_config.GROQ_API_KEY
GROQ_MODEL_API_KEY = const_config.GROQ_MODEL_API_KEY
GROQ_INTENT_MODEL_API_KEY = const_config.GROQ_INTENT_MODEL_API_KEY
LANGCHAIN_API_KEY = const_config.LANGCHAIN_API_KEY
GEMINI_API_KEY = const_config.GEMINI_API_KEY

OPEN_WEATHER_API_KEY = const_config.OPEN_WEATHER_API_KEY
LOCAL_COUNTRY = const_config.LOCAL_COUNTRY

MUSIC_PLAYER_ENABLE = const_config.MUSIC_PLAYER_ENABLE
SPOTIFY_API_KEY = const_config.SPOTIFY_API_KEY
YOUTUBE_API_KEY = const_config.YOUTUBE_API_KEY
YOUTUBE_CHANNEL_ID = const_config.YOUTUBE_CHANNEL_ID

# 添加 TTS 服务的使用标志，以便兼容旧代码
USE_AZURE = const_config.get('TTS.use_azure', True)  # 默认使用 Azure
USE_BYTEDANCE = const_config.get('TTS.use_bytedance', False)  # 默认不使用 ByteDance
USE_SOVITS = const_config.get('TTS.use_sovits', False)  # 默认不使用 SoVits

# 添加环境变量相关的兼容性常量
SECRET_KEY = const_config.get('server.secret_key', '')
SERVER_DEBUG = const_config.get('server.debug', False)
SERVER_HOST = const_config.get('server.host', '0.0.0.0')
SERVER_PORT = const_config.get('server.port', 5000)

RESEND_API_KEY = const_config.get('email.resend_api_key', '')
EMAIL_FROM = const_config.get('email.email_from', 'Yumi <noreply@resend.dev>')
OTP_LENGTH = const_config.get('email.otp_length', 6)
OTP_EXPIRE_SECONDS = const_config.get('email.otp_expire_seconds', 300)

OSS_ACCESS_KEY_ID = const_config.get('oss.access_key_id', '')
OSS_ACCESS_KEY_SECRET = const_config.get('oss.access_key_secret', '')
OSS_ENDPOINT = const_config.get('oss.endpoint', '')
OSS_BUCKET_NAME = const_config.get('oss.bucket_name', '')
OSS_BUCKET_URL = const_config.get('oss.bucket_url', '')

VERSIONS_SERVER_URL = const_config.get('versions.server_url', '')
VERSIONS_TOKEN = const_config.get('versions.token', '')

if __name__ == "__main__":
    # 测试代码
    print(f"PICOVOICE_API_KEY: {const_config.get('wake_word.windows_api_key')}")
    print(f"PICOVOICE_API_KEY (兼容方式): {PICOVOICE_API_KEY}")

    # 测试设置值
    const_config.set("wake_word.windows_api_key", "new_api_key")
    print(f"新的 PICOVOICE_API_KEY: {const_config.get('wake_word.windows_api_key')}")
    print(f"新的 PICOVOICE_API_KEY (兼容方式): {PICOVOICE_API_KEY}")

    # 测试 TTS 配置
    print(f"TTS.use_azure: {const_config.get('TTS.use_azure')}")
    print(f"USE_AZURE (兼容方式): {USE_AZURE}")

    # 测试 LLM 配置
    print(f"LLM.use_openai: {const_config.get('LLM.use_openai')}")
    print(f"USE_OPENAI (兼容方式): {USE_OPENAI}")
