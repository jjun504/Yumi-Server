from loguru import logger

# Import all possible STT engines
from stt import AzureSTTModule
# Future STT engines can be added, such as:
# from whisper_stt import WhisperSTTModule
# from baidu_stt import BaiduSTTModule

# Global STT manager accessible by all modules
STT_MANAGER = None

def ensure_initialized():
    """Ensure STT_MANAGER is initialized"""
    global STT_MANAGER
    if STT_MANAGER is None:
        init_stt_manager()

def init_stt_manager(service_name=None, device_id=None):
    """
    Initialize STT manager

    Args:
        service_name: STT service name, e.g., "azure"、"whisper"等
        device_id: Device ID, used to get device-specific configuration

    Returns:
        Initialized STT manager instance
    """
    global STT_MANAGER
    from unified_config import unified_config

    # If not specified, read from the configuration
    if service_name is None:
        service_name = unified_config.get("STT.active_service", "azure", device_id=device_id).lower()
    
    logger.info(f"Initializing STT service: {service_name}")
    
    # Create the corresponding stt instance based on the service name
    if "azure" in service_name.lower():
        STT_MANAGER = AzureSTTModule(device_id=device_id)
        logger.debug("Azure STT initialization completed")
    # elif "whisper" in service_name.lower():
    #     STT_MANAGER = WhisperSTTModule(device_id=device_id)
    #     logger.debug("Whisper STT initialization completed")
    # elif "baidu" in service_name.lower():
    #     STT_MANAGER = BaiduSTTModule(device_id=device_id)
    #     logger.debug("Baidu STT initialization completed")
    else:
        logger.warning(f"Unknown STT service: {service_name}, using default Azure STT")
        STT_MANAGER = AzureSTTModule(device_id=device_id)
    
    return STT_MANAGER

def switch_stt_manager(service_name, device_id=None):
    """
    Switch STT service

    Args:
        service_name: STT service name, e.g., "azure"、"whisper"等
        device_id: Device ID, used to get device-specific configuration

    Returns:
        Switch to the new STT service
    """
    # Stop the current stt service first (if any)
    global STT_MANAGER
    if STT_MANAGER is not None:
        try:
            STT_MANAGER.stop_stt()
        except:
            logger.warning("Failed to stop current STT service")

    # Initialize a new stt service
    return init_stt_manager(service_name, device_id)

# Automatically call ensure initialized when importing modules. Ensure initialized is ensured to be initialized.
ensure_initialized()