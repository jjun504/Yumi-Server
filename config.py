import json
import os
from datetime import datetime
from loguru import logger
import copy
from typing import Any, Dict

# 默认配置文件路径
DEFAULT_CONFIG_FILE_PATH = "config/new_settings.json"

# 当前配置文件路径（可以动态更改）
CONFIG_FILE_PATH = DEFAULT_CONFIG_FILE_PATH

# 配置文件生命周期控制
DISABLED_CONFIG_FILES = {
    "config/new_settings.json",  # 禁用这个文件的自动创建和保存
}

# 注释掉自动创建配置目录的代码，避免不必要的 config/new_settings.json 文件生成
# os.makedirs(os.path.dirname(DEFAULT_CONFIG_FILE_PATH), exist_ok=True)

# 线程本地存储，用于存储每个线程的配置文件路径
import threading
_thread_local = threading.local()

def get_current_config_path():
    """获取当前线程的配置文件路径"""
    if not hasattr(_thread_local, 'config_file_path'):
        _thread_local.config_file_path = CONFIG_FILE_PATH
    return _thread_local.config_file_path

def set_current_config_path(path):
    """设置当前线程的配置文件路径"""
    _thread_local.config_file_path = path

# 上下文管理器，用于临时设置配置文件路径
from contextlib import contextmanager

@contextmanager
def config_context(path):
    """临时设置配置文件路径的上下文管理器

    Args:
        path: 临时使用的配置文件路径

    Yields:
        None: 只是作为上下文管理器使用
    """
    # 保存当前的配置文件路径
    old_path = get_current_config_path()

    try:
        # 设置新的配置文件路径
        set_current_config_path(path)
        # 确保目录存在
        os.makedirs(os.path.dirname(path), exist_ok=True)

        # 进入with代码块
        yield
    finally:
        # 无论with代码块是否发生异常，都会执行这里的代码
        # 恢复原来的配置文件路径
        set_current_config_path(old_path)

# 默认配置
DEFAULT_CONFIG = {
    "system": {
        "device_id": "b6e2b80d-219e-403a-b792-1caa41168a56",
        "password": "654321",
        "user_id": "default_user_id",
        "boot_time": "0000-00-00 00:00:00",
        "model": "raspberry_pi",
        "version": "1.0.0",
        "language": "chinese",
        "status": "offline",
        "log_level": "DEBUG",
        "last_update": None
    },
    "wake_word": {
        "enabled": True
    },
    "STT": {
        "enabled": True,
        "active_service": "Microsoft Azure Speech Services",
        "language": "zh-CN"
    },
    "TTS": {
        "enabled": True,
        "active_service": "Bytedance TTS",
        "model_id": "ICL_zh_female_chengshujiejie_tob"
    },
    "LLM": {
        "enabled": True,
        "active_service": "Groq",
        "model_id": "llama-3.3-70b-versatile",
        "temperature": 0.7,
        "max_tokens": 1024
    },
    "music": {
        "enabled": True,
        "resume_play": True,
        "tts_notify": True
    },
    "time_notify": {
        "enabled": True,
        "interval": 60
    },
    "schedule_notify": {
        "enabled": True,
        "interval": 300
    },
    "weather": {
        "enabled": True,
        "location": "Ayer Keroh",
        "last_updated": "",
        "interval": 3600,
        "days": []
    },
    "state_flags": {
        "chat_active": True,
        "notification_active": False,
        "mqtt_message_active": False,
        "recording_active": False,
        "stt_active": False,
        "llm_active": False,
        "tts_active": False
    },
    "audio_settings": {
        "general_volume": 70,
        "music_volume": 50,
        "notification_volume": 70
    },
    "interaction": {
        "command": "",
        "answer": "小夕已上线，有什么可以帮您的吗？"
    },
    "devices": {
        "lighting": {},
        "climate": {},
        "media": {}
    },
    "user_personalization": {
        "name": "俊旭",
        "age": 20,
        "hobbies": ["画画", "看小说"],
        "region": "Ayer Keroh",
        "profile": ""
    },
    "device_role_personalization": {
        "name": "彩花",
        "age": 26,
        "relationship": "姐姐",
        "personality": "温柔，体贴",
        "background": ""
    }
}


class ConfigManager:
    """
    配置管理器类，用于管理系统配置

    提供了简单的接口来获取和设置配置项，支持多级路径访问
    例如：config.get("system.language") 或 config.set("audio_settings.music_volume", 80)
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

    def set_config_path(self, path: str) -> None:
        """
        设置配置文件路径

        Args:
            path: 新的配置文件路径
        """
        # 保存当前配置（如果有更改）
        self.save()

        # 更新配置文件路径
        old_path = get_current_config_path()
        set_current_config_path(path)

        # 只有在路径不在禁用列表中时才创建目录
        if path not in DISABLED_CONFIG_FILES:
            os.makedirs(os.path.dirname(path), exist_ok=True)

        logger.info(f"配置文件路径已更改: {old_path} -> {path}")

        # 读取新配置
        self.read()

    def reset_config_path(self) -> None:
        """
        重置配置文件路径为默认值
        """
        self.set_config_path(DEFAULT_CONFIG_FILE_PATH)

    def get_current_config_path(self) -> str:
        """
        获取当前配置文件路径

        Returns:
            str: 当前配置文件路径
        """
        return get_current_config_path()

    @property
    def config_context(self):
        """
        获取配置上下文管理器

        Returns:
            contextmanager: 配置上下文管理器
        """
        return config_context

    def save(self) -> bool:
        """
        保存当前配置到文件

        Returns:
            bool: 保存是否成功
        """
        try:
            # 获取当前线程的配置文件路径
            config_path = get_current_config_path()

            # 检查是否禁用了此配置文件的保存
            if config_path in DISABLED_CONFIG_FILES:
                logger.debug(f"配置文件 {config_path} 已被禁用，跳过保存")
                return True

            # 确保目录存在（只在需要保存时创建）
            os.makedirs(os.path.dirname(config_path), exist_ok=True)

            # 保存到文件
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)

            logger.success(f"配置已成功保存到 {config_path}")
            return True
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            return False

    def read(self) -> bool:
        """
        从文件读取配置

        Returns:
            bool: 读取是否成功
        """
        # 获取当前线程的配置文件路径
        config_path = get_current_config_path()

        if not os.path.exists(config_path):
            logger.warning(f"配置文件 {config_path} 不存在，将使用默认配置")
            return False

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)

            # 递归更新配置
            self._update_config_recursive(self.config, loaded_config)

            logger.success(f"成功从 {config_path} 加载配置")
            return True
        except Exception as e:
            logger.error(f"读取配置失败: {e}，将使用默认配置")
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

        支持使用点号分隔的路径，例如 "system.language"

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
            logger.error(f"获取配置项 {path} 失败: {e}")
            return default

    def set(self, path: str, value: Any) -> bool:
        """
        设置配置项

        支持使用点号分隔的路径，例如 "system.language"

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
            logger.error(f"设置配置项 {path} 失败: {e}")
            return False

    def _log_change(self, path: str, value: Any) -> None:
        """
        记录配置变更

        Args:
            path: 配置项路径
            value: 新值
        """
        logger.success(f"[config] {path} = {value}")

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

    # 设备管理 - 保留添加设备的方法，因为它有特殊的逻辑
    def add_device(self, category: str, device_id: str, name: str, state: Any = False,
                  data_type: str = "bool", control_type: str = "output",
                  mqtt_topic: str = None) -> bool:
        """
        添加设备

        Args:
            category: 设备类别，如 "lighting", "climate" 等
            device_id: 设备ID
            name: 设备名称
            state: 设备状态
            data_type: 数据类型，如 "bool", "int", "float", "str"
            control_type: 控制类型，如 "output", "input"
            mqtt_topic: MQTT主题，如果不提供则自动生成

        Returns:
            bool: 添加是否成功
        """
        try:
            # 确保设备类别存在
            if category not in self.config["devices"]:
                self.config["devices"][category] = {}

            # 生成MQTT主题（如果未提供）
            if mqtt_topic is None:
                mqtt_topic = f"smart87/yourname_esp32s_{device_id}/control"

            # 添加设备
            self.config["devices"][category][device_id] = {
                "name": name,
                "state": state,
                "data_type": data_type,
                "control_type": control_type,
                "mqtt_topic": mqtt_topic
            }

            logger.info(f"添加设备: {category}.{device_id} = {state} (类型: {data_type})")

            # 保存配置
            self.save()
            return True
        except Exception as e:
            logger.error(f"添加设备失败: {e}")
            return False

    # 天气管理 - 保留这个方法因为它有特殊的逻辑
    def set_weather(self, weather_data: Dict[str, Any]) -> bool:
        """
        设置天气信息

        Args:
            weather_data: 天气数据

        Returns:
            bool: 设置是否成功
        """
        # 更新天气数据
        current_weather = self.get("weather", {})
        current_weather.update(weather_data)

        # 设置最后更新时间
        current_weather["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return self.set("weather", current_weather)

    # 兼容旧版本的方法
    def get_old(self, key: str, default: Any = None) -> Any:
        """
        兼容旧版本的获取方法

        Args:
            key: 键名
            default: 默认值

        Returns:
            值
        """
        # 映射旧键到新路径
        key_mapping = {
            # 状态标志
            "chat_enable": "state_flags.chat_active",
            "notify_enable": "state_flags.notification_active",
            "mqtt_message": "state_flags.mqtt_message_active",
            "rec_enable": "state_flags.recording_active",

            # 系统设置
            "language": "system.language",

            # 交互
            "command": "interaction.command",
            "answer": "interaction.answer",

            # 音频设置
            "music_volume": "audio_settings.music_volume",
            "general_volume": "audio_settings.general_volume",

            # 功能开关
            "hw_started": "wake_word.hardware_started",
            "pv_wake_enable": "wake_word.enabled",
            "Noticenotify": "schedule_notify.enabled",
            "timenotify": "time_notify.enabled",
            "music_enable": "music.enabled",
            "music_resume_play": "music.resume_play",
            "music_tts_notify": "music.tts_notify",
        }

        # 检查是否是设备参数
        for category in self.config["devices"]:
            for device_id in self.config["devices"][category]:
                if key == device_id:
                    return self.get_device_state(category, device_id, default)

        # 使用映射获取值
        if key in key_mapping:
            return self.get(key_mapping[key], default)

        # 尝试直接获取
        return self.get(key, default)

    def set_old(self, **kwargs) -> None:
        """
        兼容旧版本的设置方法

        Args:
            **kwargs: 键值对
        """
        # 映射旧键到新路径
        key_mapping = {
            # 状态标志
            "chat_enable": "state_flags.chat_active",
            "notify_enable": "state_flags.notification_active",
            "mqtt_message": "state_flags.mqtt_message_active",
            "rec_enable": "state_flags.recording_active",

            # 系统设置
            "language": "system.language",

            # 交互
            "command": "interaction.command",
            "answer": "interaction.answer",

            # 音频设置
            "music_volume": "audio_settings.music_volume",
            "general_volume": "audio_settings.general_volume",

            # 功能开关
            "hw_started": "wake_word.hardware_started",
            "pv_wake_enable": "wake_word.enabled",
            "Noticenotify": "schedule_notify.enabled",
            "timenotify": "time_notify.enabled",
            "music_enable": "music.enabled",
            "music_resume_play": "music.resume_play",
            "music_tts_notify": "music.tts_notify",
        }

        for key, value in kwargs.items():
            # 特殊处理天气数据
            if key == "weather":
                self.set_weather(value)
                continue

            # 检查是否是设备参数
            device_found = False
            for category in self.config["devices"]:
                for device_id in self.config["devices"][category]:
                    if key == device_id:
                        self.set_device_state(category, device_id, value)
                        device_found = True
                        break
                if device_found:
                    break

            if device_found:
                continue

            # 使用映射设置值
            if key in key_mapping:
                self.set(key_mapping[key], value)
            else:
                # 尝试直接设置
                self.set(key, value)


# 配置文件管理工具
class ConfigFileManager:
    """配置文件生命周期管理器"""

    @staticmethod
    def disable_config_file(file_path: str):
        """禁用配置文件的自动创建和保存"""
        DISABLED_CONFIG_FILES.add(file_path)
        logger.info(f"已禁用配置文件: {file_path}")

    @staticmethod
    def enable_config_file(file_path: str):
        """启用配置文件的自动创建和保存"""
        DISABLED_CONFIG_FILES.discard(file_path)
        logger.info(f"已启用配置文件: {file_path}")

    @staticmethod
    def is_disabled(file_path: str) -> bool:
        """检查配置文件是否被禁用"""
        return file_path in DISABLED_CONFIG_FILES

    @staticmethod
    def clean_disabled_files():
        """删除所有被禁用的配置文件"""
        for file_path in DISABLED_CONFIG_FILES:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.success(f"已删除禁用的配置文件: {file_path}")
                except Exception as e:
                    logger.error(f"删除配置文件 {file_path} 失败: {e}")

    @staticmethod
    def list_disabled_files():
        """列出所有被禁用的配置文件"""
        return list(DISABLED_CONFIG_FILES)

# 创建单例
config = ConfigManager(DEFAULT_CONFIG)

if(__name__ == "__main__"):
    print(config.get("devices.lighting"))