from dotenv import load_dotenv
load_dotenv()

import socket
import threading
from threading import Lock
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, session, flash, send_from_directory, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
import logging
import os
import secrets
import sys
import time
import json

from database import login_required
from loguru import logger
from event_system import event_system
from if_schedule import ScheduleHandler

import resend
import psutil

# logger.remove()

logger.add(
    "Log/Server_System_Log/system.log",
    rotation="1 week",
    level="DEBUG",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}:{function}:{line}</cyan> - {message}"
)

# Import database modules
from database import auth_bp

# Import UDP device manager
from udp_device_manager import UDPDeviceManager

from database_admin import admin_bp

# Import unified configuration manager
from unified_config import (
    unified_config, get_config, set_config,
    get_device_details, set_device_details, update_device_details, ensure_device_details
)

# Get Resend API key
resend_api_key = get_config("email.resend_api_key", "")
resend.api_key = resend_api_key

# Configure ports and message identifiers
UDP_DISCOVER_PORT = 50000      # UDP broadcast listening port
SOCKETIO_PORT = 5000           # SocketIO service port
DISCOVER_REQUEST = b"DISCOVER_SERVER_REQUEST"
DISCOVER_RESPONSE = b"DISCOVER_SERVER_RESPONSE_" + str(SOCKETIO_PORT).encode()

# Flask application initialization
app = Flask(__name__)
# Get SECRET_KEY from unified_config, generate a random key if not set
secret_key = get_config('server.secret_key', '')
if not secret_key:
    secret_key = secrets.token_hex(32)
    # Save generated key to configuration
    set_config('server.secret_key', secret_key)
app.config['SECRET_KEY'] = secret_key
app.config.update(
    SESSION_COOKIE_SECURE=False,  # Allow cookie transmission via HTTP (common in development)
    SESSION_COOKIE_HTTPONLY=True,  # Prevent JavaScript access to cookies for enhanced security
    SESSION_COOKIE_SAMESITE='Lax',  # Restrict third-party requests from carrying cookies
    DEBUG=False  # Disable debug mode
)

# Initialize SocketIO with debug mode disabled
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', debug=False)

# Import unified configuration manager
from unified_config import (
    get_device_details, set_device_details, update_device_details,
    ensure_device_details, get_config, set_config
)

logger.info("Imported constant configuration manager")

# Change chat_histories to store by (user_id, device_id) tuple
chat_histories = {}  # Keyed by (user_id, device_id) tuple
chat_histories_lock = Lock()

# Import constant configuration manager (remove duplicate import)
# from const_config import const_config  # Already imported above

# Create UDP device manager - reference dev_control.py
# Check if running in main process to avoid double initialization in Flask debug mode
is_main_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug

udp_device_manager = UDPDeviceManager(
    config={
        "udp_port": 8884,
        "discovery_port": 50000,
        "mqtt_broker": "broker.emqx.io",
        "mqtt_port": 1883,
        "mqtt_username": None,
        "mqtt_password": None,
        "mqtt_client_id": f"smart_877_server_{int(time.time())}_{id(threading.current_thread())}",  # Use client ID with timestamp and thread ID to ensure uniqueness
        "session_timeout": 3600.0,  # Increase session timeout to 1 hour to avoid devices being cleaned up too quickly
        "debug": True  # Enable debug mode
    },
    server_chat_histories=chat_histories,  # Pass chat_histories from server.py
    server_chat_histories_lock=chat_histories_lock  # Pass chat_histories_lock from server.py
)

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)  # Register admin blueprint

# Initialize database module after importing and initializing auth_bp
from database import init_database_module
# Database module now uses unified configuration manager, no longer needs global variables
init_database_module(socketio)

# In server.py


# logging.basicConfig(level=logging.DEBUG)
# logger = logging.getLogger(__name__)

# ------------------------ Auto Registration and Device Discovery ------------------------
@socketio.on('connect')
def handle_connect():
    print("Client connected via SocketIO")
    emit('server_response', {'data': 'Welcome to SocketIO service'})

# Device registration now uses UDP, no longer uses WebSocket
# This function has been removed, device registration logic moved to UDP discovery response function

@socketio.on('initial_config')
def handle_initial_config(data):
    device_id = data.get('device_id')
    config_changes = data.get('config')
    if not device_id or not config_changes:
        emit('update_config_result', {'status': 'error', 'message': 'Missing device_id or config'})
        return

    # Check if device exists in unified configuration manager
    device_details = get_device_details(device_id)
    if not device_details:
        emit('update_config_result', {'status': 'error', 'message': 'Device not found'})
        return

    # If device configuration doesn't have system.user_id, set to default_user_id
    if 'system' not in config_changes or 'user_id' not in config_changes.get('system', {}) or config_changes.get('system', {}).get('user_id') == "default_user_id":
        if 'system' not in config_changes:
            config_changes['system'] = {}
        config_changes['system']['user_id'] = "default_user_id"
        logger.info(f"Set default user ID for device {device_id}: default_user_id")



    # Load existing file configuration first
    file_config = load_device_config(device_id)

    # New device configuration has higher priority, overrides file configuration
    merged_config = deep_update(file_config.copy(), config_changes)

    # Configuration has been saved to unified configuration manager via save_device_config

    # Also save to file
    save_device_config(device_id, merged_config)

    # Get device's sid to determine message source
    device_sid = get_device_details(device_id, 'sid')
    if request.sid == device_sid:
        # Initial configuration report from device side, broadcast to other (control page) clients
        socketio.emit('config_update', {'device_id': device_id, **merged_config}, skip_sid=request.sid)
        emit('update_config_result', {'status': 'success', 'message': 'Initial configuration broadcasted'})
    else:
        # If not from device side, forward directly to target device
        if device_sid:
            socketio.emit('update_config', merged_config, to=device_sid)
        emit('update_config_result', {'status': 'success'})


def load_device_config(device_id):
    """Load device configuration from file - using unified configuration manager"""
    try:
        # Ensure device configuration file exists
        unified_config.ensure_device_config(device_id)

        # Load entire device configuration file directly
        file_path = unified_config._get_config_file_path("device", device_id)
        config = unified_config._load_config_file(file_path)

        # Check if configuration is complete, supplement from default configuration if incomplete
        if config and ('devices' not in config or not isinstance(config.get('devices'), dict)):
            logger.warning(f"Device {device_id} configuration incomplete, supplementing from default configuration")

            # Load default configuration
            default_config_path = os.path.join("config", "default_setting.json")
            if os.path.exists(default_config_path):
                with open(default_config_path, 'r', encoding='utf-8') as f:
                    default_config = json.load(f)

                # Merge configurations, preserve existing configuration, supplement missing fields
                def deep_merge_config(existing, default):
                    """Deep merge configuration, preserve existing values, only supplement missing fields"""
                    if not isinstance(existing, dict) or not isinstance(default, dict):
                        return existing if existing is not None else default

                    result = existing.copy()
                    for key, value in default.items():
                        if key not in result:
                            # Missing field, use default value
                            result[key] = value
                        elif isinstance(result[key], dict) and isinstance(value, dict):
                            # Both are dictionaries, merge recursively
                            result[key] = deep_merge_config(result[key], value)
                        # If existing configuration already has this field and is not a dictionary, preserve existing value
                    return result

                # Use deep merge, especially protect TTS and LLM configurations
                config = deep_merge_config(config, default_config)

                # Update device ID
                if 'system' in config:
                    config['system']['device_id'] = device_id

                # Save updated configuration
                unified_config._save_config_file(file_path, config)
                logger.info(f"Supplemented complete configuration for device {device_id}")

        return config if config else {}
    except Exception as e:
        logger.error(f"Failed to load device configuration: {str(e)}")
        return {}

def get_device_personalized_name(device_id):
    """Get personalized name from device configuration, return device ID if none - using unified_config"""
    try:
        # Use unified_config to get personalized name
        name = unified_config.get("device_role_personalization.name", device_id=device_id, config_type="device")

        logger.info(f"Device {device_id} personalized name read: name={name}")

        if name and name.strip():
            logger.info(f"Device {device_id} using personalized name: {name.strip()}")
            return name.strip()
        else:
            logger.info(f"Device {device_id} has no personalized name, using device ID")
    except Exception as e:
        logger.error(f"Failed to get personalized name for device {device_id}: {e}")

    # If no personalized name, return device ID
    return device_id

def get_device_ip_from_config(device_id, default_ip):
    """Get IP address from device configuration, return default IP if none - using unified_config"""
    try:
        # Use unified_config to get IP address
        ip = unified_config.get("settings.ip", device_id=device_id, config_type="device")

        if ip and ip.strip():
            return ip.strip()
    except Exception as e:
        logger.error(f"Failed to get IP configuration for device {device_id}: {e}")

    # If no IP configured, return default IP
    return default_ip

def save_device_config(device_id, config_data):
    """Save device configuration to file - using unified configuration manager"""
    if not config_data:
        logger.warning(f"Attempting to save empty configuration: {device_id}")
        return False

    try:
        # Ensure device configuration file exists
        unified_config.ensure_device_config(device_id)

        # Save entire device configuration
        file_path = unified_config._get_config_file_path("device", device_id)
        unified_config._save_config_file(file_path, config_data)

        logger.info(f"Saved configuration for device {device_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to save device configuration: {str(e)}")
        return False

def load_device_details(device_id):
    """Load device details from file - using unified configuration manager"""
    try:
        # Ensure device details file exists
        ensure_device_details(device_id)

        # Get device details
        details = get_device_details(device_id)
        if details:
            logger.info(f"Loaded details for device {device_id}")
            return details
        return {}
    except Exception as e:
        logger.error(f"Failed to load device details: {str(e)}")
        return {}

def save_device_details(device_id, details_data=None):
    """Save device details to file - using unified configuration manager"""
    # If details_data not provided, get from unified configuration manager
    if details_data is None:
        details_data = get_device_details(device_id)
        if not details_data:
            logger.warning(f"Attempting to save non-existent device details: {device_id}")
            return False

    if not details_data:
        logger.warning(f"Attempting to save empty device details: {device_id}")
        return False

    try:
        # Ensure device details file exists
        ensure_device_details(device_id)

        # Remove sensitive or temporary fields that should not be saved
        save_data = details_data.copy()
        exclude_fields = ['sid', 'password']

        # Use unified configuration manager's batch update functionality
        success = update_device_details(device_id, save_data, exclude_fields)

        if success:
            logger.info(f"Saved details for device {device_id}")
        return success
    except Exception as e:
        logger.error(f"Failed to save device details: {str(e)}")
        return False

def save_all_device_details():
    """Save all device details and set status to offline - using unified configuration manager"""
    # Get all device IDs from device_configs directory
    if os.path.exists("device_configs"):
        for device_dir in os.listdir("device_configs"):
            device_path = os.path.join("device_configs", device_dir)
            if os.path.isdir(device_path):
                device_id = device_dir
                # Set device to offline status
                set_device_details(device_id, 'status', 'offline')
                logger.debug(f"Set device {device_id} to offline status")

    logger.info("Set all devices to offline status and saved details")


@socketio.on('request_current_config')
def handle_request_current_config(data=None):
     # If data is None, use empty dictionary
     if data is None:
         data = {}
     device_id = data.get('device_id')

     # Use unified configuration manager to get device configuration
     config = load_device_config(device_id)

     # Add debug logs
     logger.info(f"Request current configuration for device {device_id}")
     logger.debug(f"Configuration for device {device_id}: {config}")

     # Ensure device configuration contains devices field
     if 'devices' not in config:
         config['devices'] = {}
         logger.warning(f"Device {device_id} configuration missing devices field, added empty dictionary")

     # Send configuration
     emit('current_config', config)

@socketio.on('delete_device')
def handle_delete_device(data):
    """Handle delete device request

    Data format example:
    {
        "device_id": "mixue001",
        "device_type": "lighting",
        "target_device_id": "main_room_light"
    }
    """
    device_id = data.get('device_id')
    device_type = data.get('device_type')
    target_device_id = data.get('target_device_id')

    if not device_id or not device_type or not target_device_id:
        emit('delete_device_result', {'status': 'error', 'message': 'Missing required parameters'})
        return

    logger.info(f"Received delete device request: device_id={device_id}, device_type={device_type}, target_device_id={target_device_id}")

    # Verify user has permission to access the device
    user_id = session.get('user_id')
    if not user_id:
        emit('delete_device_result', {'status': 'error', 'message': 'User not logged in'})
        return

    # Check device access permission
    if not check_device_access(user_id, device_id):
        emit('delete_device_result', {'status': 'error', 'message': 'No permission to access this device'})
        return

    try:
        # Get current device configuration
        current_config = load_device_config(device_id)
        if not current_config:
            emit('delete_device_result', {'status': 'error', 'message': 'Device configuration does not exist'})
            return

        # Check if device type and target device exist
        if 'devices' not in current_config:
            emit('delete_device_result', {'status': 'error', 'message': 'Device configuration missing devices field'})
            return

        if device_type not in current_config['devices']:
            emit('delete_device_result', {'status': 'error', 'message': f'Device type {device_type} does not exist'})
            return

        if target_device_id not in current_config['devices'][device_type]:
            emit('delete_device_result', {'status': 'error', 'message': f'Target device {target_device_id} does not exist'})
            return

        # Delete target device
        del current_config['devices'][device_type][target_device_id]

        # If no devices left under device type, delete the type
        if not current_config['devices'][device_type]:
            del current_config['devices'][device_type]

        # Save to file
        save_device_config(device_id, current_config)

        # # Ensure configuration file is immediately written to disk
        # try:
        #     import os
        #     os.fsync(open(os.path.join("device_configs", device_id, "new_settings.json"), 'a').fileno())
        #     logger.info(f"Forced write device {device_id} configuration to disk")
        # except Exception as sync_error:
        #     logger.warning(f"Error forcing configuration file write: {str(sync_error)}")

        # Publish updated configuration via MQTT
        udp_device_manager.publish_device_config_to_mqtt(device_id)

        # If device service exists, notify device service to reload device configuration
        if hasattr(udp_device_manager, 'device_services') and device_id in udp_device_manager.device_services:
            device_service = udp_device_manager.device_services[device_id]
            if hasattr(device_service, 'devManager') and device_service.devManager:
                logger.info(f"Notify device {device_id} device manager to reload configuration")
                device_service.devManager.reload_devices_from_config()

                # Ensure device manager clears cache of deleted device
                if hasattr(device_service.devManager, 'devices'):
                    device_key = f"{device_type}.{target_device_id}"
                    if device_key in device_service.devManager.devices:
                        logger.info(f"Clear device from device manager cache: {device_key}")
                        del device_service.devManager.devices[device_key]

        # Return success result
        emit('delete_device_result', {'status': 'success', 'message': f'Successfully deleted device {target_device_id}'})
        logger.info(f"Successfully deleted device {device_id} {device_type}.{target_device_id}")

    except Exception as e:
        logger.error(f"Error deleting device: {str(e)}")
        emit('delete_device_result', {'status': 'error', 'message': f'Error deleting device: {str(e)}'})
        return

@socketio.on('request_available_services')
def handle_request_available_services():
    """Handle client request for available services and models"""
    # Extract available services and models for STT, TTS and LLM from const_config
    available_services = {
        'STT': {},
        'TTS': {},
        'LLM': {}
    }

    # logger.info("===== Start processing available services request =====")
    # logger.info(f"Complete configuration: {json.dumps(const_config.config, ensure_ascii=False, indent=2)}")

    # Extract STT services - read from constant configuration
    stt_config = unified_config.get('STT', {}, config_type="const")
    # logger.info(f"STT configuration: {json.dumps(stt_config, ensure_ascii=False, indent=2)}")

    if stt_config:
        stt_services = []
        for service_name in stt_config:
            stt_services.append(service_name)
            # logger.info(f"Add STT service: {service_name}")
        available_services['STT']['services'] = stt_services
        # logger.info(f"All STT services: {stt_services}")

    # Extract TTS services and models - read from constant configuration
    tts_config = unified_config.get('TTS', {}, config_type="const")
    # logger.info(f"TTS configuration: {json.dumps(tts_config, ensure_ascii=False, indent=2)}")

    if tts_config:
        tts_services = {}
        enabled_tts_services = []

        # First check which services are enabled
        for key, value in tts_config.items():
            # logger.info(f"Check TTS configuration item: {key} = {value}")
            if key.startswith('use_') and value is True:
                # Extract 'azure' from 'use_azure'
                service_name = key[4:]
                enabled_tts_services.append(service_name)
                # logger.info(f"TTS service {service_name} enabled (via use_ flag)")

        # If no explicit enable flags, assume all services with model_id are enabled
        if not any(key.startswith('use_') for key in tts_config):
            logger.info("No use_ flags found, checking services with model_id")
            for service_name, service_config in tts_config.items():
                if isinstance(service_config, dict) and 'model_id' in service_config:
                    enabled_tts_services.append(service_name)
                    # logger.info(f"TTS service {service_name} enabled (default, via model_id)")

        # logger.info(f"Enabled TTS services list: {enabled_tts_services}")

        # Extract models for enabled services
        for service_name in enabled_tts_services:
            # Create service configuration object
            tts_services[service_name] = {}

            if service_name == "sovits":
                # Create default configuration for sovits
                service_languages = {
                    "zh-CN": [
                        {
                            "id": "gpt_sovits_default",
                            "name": "Customize voice"
                        }
                    ]
                }
                tts_services[service_name]['languages'] = service_languages
            else:
                # Get models from TTS.{service_name}.languages
                service_languages_path = f"TTS.{service_name}.languages"
                service_languages = unified_config.get(service_languages_path, {}, config_type="const")

                if service_languages:
                    tts_services[service_name]['languages'] = service_languages
                    # logger.info(f"TTS service {service_name} supported languages: {list(service_languages.keys())}")

        available_services['TTS']['services'] = tts_services
        available_services['TTS']['enabled_services'] = enabled_tts_services
        # logger.info(f"TTS service final structure: {json.dumps(available_services['TTS'], ensure_ascii=False, indent=2)}")

    # Extract LLM services and models - read from constant configuration
    llm_config = unified_config.get('LLM', {}, config_type="const")
    # logger.info(f"LLM configuration: {json.dumps(llm_config, ensure_ascii=False, indent=2)}")

    if llm_config:
        llm_services = {}
        enabled_llm_services = []

        # Check which services are enabled
        for key, value in llm_config.items():
            # logger.info(f"Check LLM configuration item: {key} = {value}")
            if key.startswith('use_') and value is True:
                # Extract 'openai' from 'use_openai'
                service_name = key[4:]
                enabled_llm_services.append(service_name)
                # logger.info(f"LLM service {service_name} enabled (via use_ flag)")
            elif key.startswith('use_') and value is False:
                service_name = key[4:]
                # logger.info(f"LLM service {service_name} disabled (via use_ flag)")

        # If no explicit enable flags, assume all services with model_id are enabled
        if not enabled_llm_services:
            # logger.info("No enabled LLM services found, checking services with model_id")
            for service_name, service_config in llm_config.items():
                if not service_name.startswith('use_') and isinstance(service_config, dict) and 'model_id' in service_config:
                    enabled_llm_services.append(service_name)
                    logger.info(f"LLM service {service_name} enabled (default, via model_id)")

        # logger.info(f"Enabled LLM services list: {enabled_llm_services}")

        # Extract models for each enabled service
        for service_name in enabled_llm_services:
            model_id_path = f"LLM.{service_name}.model_id"
            # logger.info(f"Get model ID: {model_id_path}")
            model_id = unified_config.get(model_id_path, [], config_type="const")
            # logger.info(f"Model ID: {json.dumps(model_id, ensure_ascii=False)}")

            if isinstance(model_id, list) and model_id:
                # Check if it's new format (object list containing id and name)
                if isinstance(model_id[0], dict) and 'id' in model_id[0]:
                    # New format, keep complete object list
                    llm_services[service_name] = model_id
                    # logger.info(f"LLM service {service_name} models (new format): {[model.get('name', model.get('id', 'unknown')) for model in model_id]}")
                else:
                    # Old format, convert to ID-only list
                    llm_services[service_name] = model_id
                    # logger.info(f"LLM service {service_name} models (old format): {model_id}")

        available_services['LLM']['services'] = llm_services
        available_services['LLM']['enabled_services'] = enabled_llm_services
        # logger.info(f"LLM service final structure: {json.dumps(available_services['LLM'], ensure_ascii=False, indent=2)}")

    # Final result
    # logger.info(f"Final available services structure: {json.dumps(available_services, ensure_ascii=False, indent=2)}")

    # Send available services and model information to client
    emit('available_services', available_services)
    logger.info(f"Sent available services and model information to client: TTS services={available_services['TTS'].get('enabled_services', [])}, LLM services={available_services['LLM'].get('enabled_services', [])}")
    logger.info("===== Processing available services request completed =====")


@socketio.on('disconnect')
def handle_disconnect():
    print("Client disconnected from SocketIO")

    # In UDP+MQTT architecture, device status is controlled by MQTT messages
    # Here only handle web interface client disconnection, do not modify device status

    # Can add some logging
    logger.info(f"WebSocket client disconnected: {request.sid}")

    # If needed, can handle web interface client cleanup here
    # For example, remove client from rooms, etc.

# Device status change callback function
def on_device_status_changed(device_id, status, is_new):
    """Device status change callback function"""
    logger.info(f"Device {device_id} status changed: {status}, is new device: {is_new}")


    # Update device record - using unified configuration manager
    current_details = get_device_details(device_id)
    if current_details:
        # Device exists, update status
        set_device_details(device_id, 'status', status)
    else:
        # Get device IP and other information
        device_info = udp_device_manager.get_device_status(device_id)
        if device_info:
            # Create basic device record
            # Get user_id, replace empty string with None
            user_id = device_info.get('user_id')
            if user_id == '':
                user_id = None

            new_device_details = {
                'ip': device_info.get('ip', 'unknown'),
                'status': status,
                'authenticated': True,
                'user_id': user_id,  # Get user_id from device_info, empty string replaced with None
                'device_id': device_id
            }

            # Copy other possible existing fields
            for field in ['model', 'password']:
                if field in device_info:
                    new_device_details[field] = device_info.get(field)

            # Save to unified configuration manager
            update_device_details(device_id, new_device_details, exclude_fields=['sid', 'password'])

    # Prepare broadcast data (consistent with handle_device_update)
    broadcast_data = {
        'id': device_id,
        'online': status == 'online',  # Set dynamically based on status
        'is_new': is_new  # Keep is_new field
    }

    # Add other non-sensitive fields - get from unified configuration manager
    device_details = get_device_details(device_id)
    if device_details:
        for key, value in device_details.items():
            if key not in ['password', 'sid', 'authenticated'] and key != 'device_id':
                broadcast_data[key] = value

    # Only broadcast online devices or meaningful status changes
    # Check if device should be broadcasted
    should_broadcast = False

    # If device is online, always broadcast
    if status == 'online':
        should_broadcast = True

    # If device has user_id and is status change (from online to offline), also broadcast
    elif status == 'offline':
        device_user_id = device_details.get('user_id') if device_details else None
        if device_user_id:  # Only broadcast when bound user device goes offline
            should_broadcast = True

    # Only send when broadcast is needed
    if should_broadcast:
        socketio.emit('device_update', broadcast_data)
        logger.info(f"Broadcasted device {device_id} status update: {status}")
    else:
        logger.debug(f"Skipped broadcasting device {device_id} status update: {status} (offline device with no user binding)")

    # If it's a new device, get device configuration
    if is_new and status == 'online':
        # Check if device configuration already exists
        existing_config = load_device_config(device_id)
        if not existing_config:
            service = udp_device_manager.get_device_service(device_id)
            if service:
                # Get device configuration
                device_config = service.get_config()
                if device_config:
                    # Save device configuration
                    save_device_config(device_id, device_config)
                    # Broadcast device configuration
                    socketio.emit('config_update', {'device_id': device_id, **device_config})


# Device configuration change callback function
def on_device_config_changed(device_id, device_config):
    """Device configuration change callback function"""
    logger.info(f"Device {device_id} configuration changed")

    # Save device configuration
    save_device_config(device_id, device_config)

    # Broadcast device configuration update
    socketio.emit('config_update', {'device_id': device_id, **device_config})

    # Publish device configuration via MQTT
    udp_device_manager.publish_device_config_to_mqtt(device_id)

    logger.info(f"Broadcasted configuration update for device {device_id}")

# Set device status change callback
udp_device_manager.set_device_status_callback(on_device_status_changed)

# Set device configuration change callback
udp_device_manager.set_device_config_callback(on_device_config_changed)

# Load all device details
def load_all_device_details():
    """Load all device details"""
    # Check device_configs directory
    if os.path.exists("device_configs"):
        # Traverse all device directories
        for device_dir in os.listdir("device_configs"):
            device_path = os.path.join("device_configs", device_dir)
            if os.path.isdir(device_path):
                # Load device details
                device_id = device_dir

                # Check if device configuration file exists
                config_path = os.path.join(device_path, "new_settings.json")
                if not os.path.exists(config_path):
                    logger.warning(f"Device {device_id} configuration file does not exist, skipping load")
                    continue

                # Check if device configuration file is valid
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        device_config = json.load(f)

                    # Check if device configuration contains devices field and is not empty
                    if 'devices' not in device_config or not device_config['devices']:
                        logger.info(f"Device {device_id} has no associated sub-devices, but still loading basic information")
                except Exception as e:
                    logger.error(f"Error reading configuration file for device {device_id}: {str(e)}")
                    continue

                details = load_device_details(device_id)
                if details:
                    # Set device to offline status
                    details['status'] = 'offline'
                    details['sid'] = None

                    # Sync directly to unified configuration manager
                    update_device_details(device_id, details, exclude_fields=['sid', 'password'])

                    logger.info(f"Loaded details for device {device_id}")

# Load all device details
load_all_device_details()

# Add specialized device list loading function for admin page
def load_admin_devices_list():
    """
    Load list of all devices for admin page use.
    Returns device list containing device ID, online status, IP address and owner information, etc.
    """
    admin_devices = []

    # First collect all known device IDs
    all_device_ids = set()

    # Get device IDs from unified configuration manager
    if os.path.exists("device_configs"):
        for device_dir in os.listdir("device_configs"):
            device_path = os.path.join("device_configs", device_dir)
            if os.path.isdir(device_path):
                all_device_ids.add(device_dir)

    # Get device IDs from UDP device manager
    udp_devices = udp_device_manager.get_all_devices()
    for device_id in udp_devices:
        all_device_ids.add(device_id)

    # Get device IDs from device configuration directory
    if os.path.exists("device_configs"):
        for device_dir in os.listdir("device_configs"):
            device_path = os.path.join("device_configs", device_dir)
            if os.path.isdir(device_path):
                all_device_ids.add(device_dir)

    # Process each device, get detailed information
    for device_id in all_device_ids:
        try:
            device_info = {}

            # Basic information: device ID
            device_info['id'] = device_id

            # Get more information from unified configuration manager
            device_details = get_device_details(device_id)
            if device_details:
                device_info['ip'] = device_details.get('ip', 'unknown')
                device_info['model'] = device_details.get('model', '')
                device_info['user_id'] = device_details.get('user_id', '')
                # Check if device is online via WebSocket (sid exists)
                online_by_sid = device_details.get('sid') is not None
            else:
                device_info['ip'] = 'unknown'
                device_info['model'] = ''
                device_info['user_id'] = ''
                online_by_sid = False

            # Get more information from UDP device manager
            udp_devices = udp_device_manager.get_all_devices()
            if device_id in udp_devices:
                udp_device = udp_devices[device_id]
                # If global device dictionary doesn't have this information, get from UDP device manager
                if device_info['ip'] == 'unknown':
                    device_info['ip'] = udp_device.get('ip', 'unknown')
                if not device_info['model']:
                    device_info['model'] = udp_device.get('model', '')
                if not device_info['user_id']:
                    device_info['user_id'] = udp_device.get('user_id', '')

                # Determine if device is online based on UDP device manager
                online_by_udp = udp_device.get('status', 'offline') == 'online'
            else:
                online_by_udp = False

            # Determine device online status: online if either method shows online
            device_info['online'] = online_by_sid or online_by_udp

            # Find device owner
            owner_id = None
            if device_info['user_id']:
                # If device already has user_id, use it directly
                owner_id = device_info['user_id']
            else:
                # Otherwise query from database
                owner_id = find_device_owner(device_id)

            device_info['owner_id'] = owner_id

            # Get owner username
            owner_username = None
            if owner_id:
                from database import UserManager
                owner_user = UserManager.get_user_by_id(owner_id)
                if owner_user:
                    owner_username = owner_user.get('username')

            device_info['owner_username'] = owner_username

            # Add to device list
            admin_devices.append(device_info)

        except Exception as e:
            logger.error(f"Error getting information for device {device_id}: {str(e)}")
            # Add basic information
            admin_devices.append({
                'id': device_id,
                'ip': 'error',
                'online': False,
                'owner_id': None,
                'owner_username': None,
                'error': str(e)
            })

    # Sort by device ID alphabetically
    admin_devices.sort(key=lambda x: x['id'])

    return admin_devices

# Only initialize UDP device manager in main process to avoid double initialization in Flask debug mode
if is_main_process:
    logger.info("Initialize UDP device manager in main process")
    udp_device_manager.initialize()
else:
    logger.info("Skip UDP device manager initialization in auxiliary process")

# Register socketio's handle_new_chat_message function to event system
# Here we need to ensure using the correct function reference
# Since handle_new_chat_message is defined later, we need to register after initialization is complete

# ------------------------ Device Discovery and Connection Handling ------------------------
@socketio.on('request_discovery')
def handle_request_discovery():
    logger.info("Discovery request received. Broadcasting discovery_request.")
    # Broadcast to all connected clients
    socketio.emit('discovery_request', {})

@socketio.on('device_update')
def handle_device_update(data):
    """
    Handle device information update.
    Receive all information sent by device, update devices dictionary, and broadcast to all clients.
    Also save device details to file.

    Data format example:
    {
        "device_id": "rasp1",
        "ip": "192.168.1.100",
        "password": "password123",
        "model": "raspberry_pi_4",
        "status": "online"
    }
    """
    device_id = data.get('device_id')
    if not device_id:
        emit('device_update_result', {'status': 'error', 'message': 'Missing device_id'})
        return

    # Remove fields that should not be directly updated
    excluded_fields = ['sid', 'authenticated']
    update_data = {k: v for k, v in data.items() if k not in excluded_fields}

    # Log updated fields (excluding password)
    log_data = {k: v for k, v in update_data.items() if k != 'password'}
    logger.info(f"Device update request: {device_id}, updated fields: {log_data}")

    # Ensure device exists in unified configuration manager
    ensure_device_details(device_id)

    # Update all provided fields of the device
    for key, value in update_data.items():
        if key != 'device_id':  # Don't update device_id field
            # Special handling for user_id field, replace empty string with None
            if key == 'user_id' and value == '':
                set_device_details(device_id, key, None)
            else:
                set_device_details(device_id, key, value)

    # Save device details to file
    save_device_details(device_id)

    # Prepare broadcast data (excluding sensitive information like password)
    broadcast_data = {
        'id': device_id,
        'online': True  # If update received, device should be online
    }

    # Add other non-sensitive fields - get from unified configuration manager
    device_details = get_device_details(device_id)
    if device_details:
        for key, value in device_details.items():
            if key not in ['password', 'sid', 'authenticated'] and key != 'device_id':
                broadcast_data[key] = value

    # Broadcast device update
    socketio.emit('device_update', broadcast_data)
    logger.info(f"Broadcasted update information for device {device_id}")

    # Return success response
    emit('device_update_result', {'status': 'success'})

def find_device_owner(device_id):
    """Query which user owns this device_id device from database.

    Returns user ID (format 'user001') instead of username
    """
    from database import UserManager
    conn = UserManager.get_connection()
    if not conn:
        logger.error("Unable to connect to database")
        return None

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT user_id FROM user_model
            WHERE model_id = %s LIMIT 1""",
            (device_id,)
        )
        result = cursor.fetchone()

        if result:
            # Return user ID directly, no longer query username
            return result['user_id']
        return None
    except Exception as e:
        logger.error(f"Error finding device owner: {str(e)}")
        return None
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def bind_device_to_user(user_id, device_id):
    """Bind device to user, add record to user_model table

    Args:
        user_id: User ID (format 'user001') or username
        device_id: Device ID

    Returns:
        bool: Returns True if binding successful, False if failed
    """
    # Import database management class
    from database import UserManager

    logger.info(f"Attempting to bind device {device_id} to user {user_id}")

    conn = UserManager.get_connection()
    if not conn:
        logger.error(f"Unable to connect to database, failed to bind device {device_id} to user {user_id}")
        return False

    try:
        cursor = conn.cursor(dictionary=True)

        # Determine user ID
        user_id_to_use = user_id

        # If passed value is username instead of user ID, query corresponding user ID
        if not (isinstance(user_id, str) and user_id.startswith('user')):
            # Assume it's username, query corresponding user ID
            cursor.execute("SELECT user_id FROM users WHERE user_username = %s", (user_id,))
            user_result = cursor.fetchone()

            if not user_result:
                logger.warning(f"Cannot find user with username {user_id}, unable to bind device")
                return False

            user_id_to_use = user_result['user_id']
            logger.debug(f"Found user {user_id}, user ID is {user_id_to_use}")

        # Confirm user ID exists
        cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id_to_use,))
        if not cursor.fetchone():
            logger.warning(f"User with ID {user_id_to_use} does not exist in database")
            return False

        # Check if same binding relationship already exists
        cursor.execute(
            """SELECT id FROM user_model
            WHERE user_id = %s AND model_id = %s""",
            (user_id_to_use, device_id)
        )

        if cursor.fetchone():
            logger.info(f"Device {device_id} already bound to user ID {user_id_to_use}, no need to repeat")
            return True  # Already bound, consider as success

        # Check if table structure exists
        try:
            cursor.execute("DESCRIBE user_model")
            fields = [field['Field'] for field in cursor.fetchall()]
            logger.debug(f"user_model table fields: {fields}")
        except Exception as schema_error:
            logger.error(f"Failed to check user_model table structure: {str(schema_error)}")

        # Add new binding relationship
        insert_query = """INSERT INTO user_model (user_id, model_id)
                         VALUES (%s, %s)"""
        logger.debug(f"Execute SQL: {insert_query} parameters: ({user_id_to_use}, {device_id})")

        cursor.execute(insert_query, (user_id_to_use, device_id))

        conn.commit()
        logger.info(f"Successfully bound device {device_id} to user ID {user_id_to_use}")

        # After successful binding, update user_id in device information and configuration file
        try:
            # 1. Update user_id in device information
            set_device_details(device_id, 'user_id', user_id_to_use)
            logger.info(f"Set user_id in device {device_id} information to {user_id_to_use}")
            # Save device details to file
            save_device_details(device_id)

            # 2. Update user_id in device configuration file (using unified_config)
            success = unified_config.set("system.user_id", user_id_to_use, device_id=device_id)
            if success:
                logger.info(f"Set user_id in device {device_id} configuration file to {user_id_to_use}")

                # Send partial configuration update to client via MQTT
                try:
                    udp_device_manager.send_partial_config(device_id, "system.user_id", user_id_to_use)
                    logger.info(f"Sent user_id update to {user_id_to_use} to device {device_id} via MQTT")
                except Exception as mqtt_error:
                    logger.error(f"Error sending configuration update to device {device_id}: {str(mqtt_error)}")
            else:
                logger.error(f"Failed to update user_id in device {device_id} configuration file using unified_config")
        except Exception as config_error:
            logger.error(f"Error updating user_id in device {device_id} configuration file: {str(config_error)}")
            # Continue execution, don't interrupt entire binding process due to configuration update failure

        return True

    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Error binding device to user: {str(e)}", exc_info=True)
        return False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def unbind_device_from_user(user_id, device_id):
    """Unbind device from user relationship in user_model table, and set user_id to None in device configuration and information

    Args:
        user_id: User ID (format 'user001') or username
        device_id: Device ID

    Returns:
        bool: Returns True if unbinding successful, False if failed
    """
    # Import database management class
    from database import UserManager

    logger.info(f"Attempting to unbind device {device_id} from user {user_id}")

    conn = UserManager.get_connection()
    if not conn:
        logger.error(f"Unable to connect to database, failed to unbind device {device_id} from user {user_id}")
        return False

    try:
        cursor = conn.cursor(dictionary=True)

        # Determine user ID
        user_id_to_use = user_id

        # If passed value is username instead of user ID, query corresponding user ID
        if not (isinstance(user_id, str) and user_id.startswith('user')):
            # Assume it's username, query corresponding user ID
            cursor.execute("SELECT user_id FROM users WHERE user_username = %s", (user_id,))
            user_result = cursor.fetchone()

            if not user_result:
                logger.warning(f"Cannot find user with username {user_id}, unable to unbind device")
                return False

            user_id_to_use = user_result['user_id']
            logger.debug(f"Found user {user_id}, user ID is {user_id_to_use}")

        # Check if binding relationship exists
        cursor.execute(
            """SELECT id FROM user_model
            WHERE user_id = %s AND model_id = %s""",
            (user_id_to_use, device_id)
        )

        if not cursor.fetchone():
            logger.info(f"Device {device_id} not bound to user ID {user_id_to_use}, no need to unbind")
            return True  # No binding exists, consider as success

        # Execute unbind operation (delete record)
        delete_query = """DELETE FROM user_model
                        WHERE user_id = %s AND model_id = %s"""
        logger.debug(f"Execute SQL: {delete_query} parameters: ({user_id_to_use}, {device_id})")

        cursor.execute(delete_query, (user_id_to_use, device_id))

        conn.commit()
        logger.info(f"Successfully unbound device {device_id} from user ID {user_id_to_use}")

        # 1. Update user_id to None in device information
        set_device_details(device_id, 'user_id', None)
        logger.info(f"Set user_id to None in device {device_id} information")
        # Save device details to file
        save_device_details(device_id)

        # 2. Update user_id to None in device configuration file (using unified_config)
        try:
            success = unified_config.set("system.user_id", None, device_id=device_id)
            if success:
                logger.info(f"Set user_id to None in device {device_id} configuration file")

                # Send partial configuration update to client via MQTT
                try:
                    udp_device_manager.send_partial_config(device_id, "system.user_id", None)
                    logger.info(f"Sent user_id update to None to device {device_id} via MQTT")
                except Exception as mqtt_error:
                    logger.error(f"Error sending configuration update to device {device_id}: {str(mqtt_error)}")
            else:
                logger.error(f"Failed to update user_id in device {device_id} configuration file using unified_config")
        except Exception as config_error:
            logger.error(f"Error updating user_id in device {device_id} configuration file: {str(config_error)}")
            # Continue execution, don't interrupt entire unbinding process due to configuration update failure

        return True

    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Error unbinding device from user: {str(e)}", exc_info=True)
        return False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def check_device_access(username_or_id, device_id):
    """Check if user has permission to access device (using database instead of original JSON implementation)

    Args:
        username_or_id: Username or user ID (format 'user001')
        device_id: Device ID

    Returns:
        bool: True if user has permission to access device, False otherwise
    """
    # Import database management class
    from database import UserManager

    conn = UserManager.get_connection()
    if not conn:
        logger.error("Unable to connect to database")
        return False

    try:
        cursor = conn.cursor(dictionary=True)

        # Determine user ID
        user_id_to_use = username_or_id

        # If passed value is username instead of user ID, query corresponding user ID
        if not (isinstance(username_or_id, str) and username_or_id.startswith('user')):
            # Assume it's username, query corresponding user ID
            cursor.execute("SELECT user_id FROM users WHERE user_username = %s", (username_or_id,))
            user_result = cursor.fetchone()

            if not user_result:
                logger.warning(f"Cannot find user with username {username_or_id}")
                return False

            user_id_to_use = user_result['user_id']
            logger.debug(f"Found user {username_or_id}, user ID is {user_id_to_use}")

        # Query user_model table to check if corresponding relationship exists
        cursor.execute(
            """SELECT id FROM user_model
            WHERE user_id = %s AND model_id = %s""",
            (user_id_to_use, device_id)
        )

        if cursor.fetchone():
            return True

        # If not found in database, return False
        return False

    except Exception as e:
        logger.error(f"Error checking device access permission: {str(e)}")
        # Return False on error
        return False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


@socketio.on('attempt_connection')
def handle_connection_attempt(data):
    device_id = data.get('device_id')
    input_password = data.get('password')
    if not device_id or not input_password:
        emit('connection_result', {'success': False, 'message': 'Missing device id or password.'})
        return


    # 1. Check if device exists in system
    device_info = get_device_details(device_id)
    if not device_info:
        emit('connection_result', {'success': False, 'message': 'Device not found'})
        return

    # 2. Check if password is correct
    if input_password != device_info.get('password'):
        emit('connection_result', {'success': False, 'message': 'Invalid password'})
        return

    # Get current logged in user via session or other means
    current_user_id = session.get('user_id', 'user001')

    # Query if this device is already bound
    owner_id = find_device_owner(device_id)

    # If device is already bound to another user, deny access
    if owner_id and owner_id != current_user_id:
        # Get owner's username (for logging)
        owner_username = None
        try:
            from database import UserManager
            owner_user = UserManager.get_user_by_id(owner_id)
            if owner_user:
                owner_username = owner_user.get('username')
        except Exception as e:
            logger.error(f"Failed to get device owner username: {str(e)}")

        emit('connection_result', {'success': False, 'message': 'Device already bound to another user'})
        logger.warning(f"User {current_user_id} attempted to access device {device_id} already bound to user {owner_id}({owner_username})")
        return

    # If device is not bound, create new binding relationship
    if not owner_id:
        logger.info(f"Device {device_id} not bound, binding to current user {current_user_id}")
        bind_success = bind_device_to_user(current_user_id, device_id)
        if not bind_success:
            logger.error(f"Failed to bind device {device_id} to user {current_user_id}")
            emit('connection_result', {'success': False, 'message': 'Device binding failed, please try again later'})
            return
        logger.info(f"Successfully bound device {device_id} to user {current_user_id}")

    # Device verification successful, set to authenticated state
    set_device_details(device_id, 'authenticated', True)
    set_device_details(device_id, 'sid', request.sid)

    # Return success result, including redirect URL
    emit('connection_result', {
        'success': True,
        'redirect': f'/control?device_id={device_id}',
        'device_ip': device_info.get('ip')
    })
    logger.info(f"User {current_user_id} successfully connected to device {device_id}")


# # ------------------------ Configuration Update Handling ------------------------
def deep_update(target_dict, update_dict):
    """
    Recursively update nested dictionary structure, ensuring all levels of dictionaries are properly merged
    """
    if not isinstance(target_dict, dict) or not isinstance(update_dict, dict):
        logger.warning(f"deep_update received non-dictionary parameters: target_dict type={type(target_dict)}, update_dict type={type(update_dict)}")
        if isinstance(update_dict, dict):
            return update_dict.copy()  # If target is not dict but update is dict, return copy of update
        return target_dict  # Otherwise keep target unchanged

    # Create copy of target dictionary to avoid directly modifying original dictionary
    result = target_dict.copy()

    for key, value in update_dict.items():
        # If key exists in both dictionaries and both values are dictionaries, merge recursively
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_update(result[key], value)
        else:
            # Otherwise directly replace/add value
            result[key] = value

    return result


@socketio.on('update_config')
def handle_update_config(data):
    """
    Handle configuration update messages. Logic:
      - If message comes from device side (i.e. request.sid == target sid), it means device side called config.register_callback(on_config_change)
        —— In this case server broadcasts update to other clients except sender (control pages etc.).
      - If message is not from target device, forward to target device.
    Data format example:
      { "device_id": "rasp1", "config": { "general_volume": 50, "hw_started": true } }
    """
    device_id = data.get('device_id')
    config_changes = data.get('config')
    if not device_id or not config_changes:
        emit('update_config_result', {'status': 'error', 'message': 'Missing device_id or config'})
        return

    # Check if device exists
    device_details = get_device_details(device_id)
    if not device_details:
        emit('update_config_result', {'status': 'error', 'message': 'Device not found'})
        return

    # Handle dotted parameter names - convert them to nested structure
    processed_config = {}
    for key, value in config_changes.items():
        if '.' in key:
            # Handle dot-separated paths like 'interaction.command'
            parts = key.split('.')
            current = processed_config

            # Create nested structure
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]

            # Set final value
            current[parts[-1]] = value
        else:
            # Set regular key-value directly
            processed_config[key] = value

    # Special handling: if initialization configuration contains user personalization info, also set weather.location
    if 'user_personalization' in processed_config and 'region' in processed_config.get('user_personalization', {}):
        region = processed_config['user_personalization']['region']
        if region:
            # Ensure weather configuration exists
            if 'weather' not in processed_config:
                processed_config['weather'] = {}
            # Set weather.location to user's region
            processed_config['weather']['location'] = region
            logger.info(f"Automatically set weather.location to user region: {region}")

    # Update configuration to unified configuration manager
    current_config = load_device_config(device_id)
    if current_config:
        # Log configuration before update
        logger.debug(f"Configuration before update: {current_config}")
        logger.debug(f"Configuration to merge: {processed_config}")

        # Execute deep update and save returned new dictionary
        merged_config = deep_update(current_config, processed_config)

        # Log configuration after update
        logger.debug(f"Configuration after update: {merged_config}")
    else:
        merged_config = processed_config
        logger.debug(f"Create new configuration: {merged_config}")

    # Special handling: if updating system.password, also update password in device_details
    if 'system' in processed_config and 'password' in processed_config.get('system', {}):
        new_password = processed_config['system']['password']
        set_device_details(device_id, 'password', new_password)
        logger.info(f"Synchronized update of device {device_id} details password")

    # Save merged configuration
    save_device_config(device_id, merged_config)
    logger.info(f"Saved complete configuration for device {device_id} to file")

    # Publish complete configuration via MQTT
    # udp_device_manager.publish_device_config_to_mqtt(device_id)
    device_sid = get_device_details(device_id, 'sid')
    if request.sid == device_sid:
        # If reported from device side, broadcast to control pages
        current_config = load_device_config(device_id)
        socketio.emit('config_update', {'device_id': device_id, **current_config}, skip_sid=request.sid)
        emit('update_config_result', {'status': 'success'})
    else:
        # If update request from control page, forward to target device
        if device_sid:
            socketio.emit('update_config', processed_config, to=device_sid)

        # Also update device service configuration
        service = udp_device_manager.get_device_service(device_id)
        if service:
            logger.debug("Update device service configuration")
            success = service.handle_config_update(processed_config)
            if success:
                logger.info(f"Updated configuration for device {device_id} service")
            else:
                logger.warning(f"Failed to update configuration for device {device_id} service")

            # Check if contains specific configuration items that need to be sent via MQTT
            mqtt_config_keys = {
                "system.password": "system.password",
                "system.user_id": "system.user_id",
                "wake_word.enabled": "wake_word.enabled",
                "audio_settings.general_volume": "audio_settings.general_volume",
                "audio_settings.music_volume": "audio_settings.music_volume",
                "audio_settings.notification_volume": "audio_settings.notification_volume"
            }

            # Flatten processed configuration to dot-separated format to check if contains configuration items to send
            flat_config = {}

            def flatten_dict(d, prefix=""):
                for k, v in d.items():
                    if isinstance(v, dict):
                        flatten_dict(v, f"{prefix}{k}.")
                    else:
                        flat_config[f"{prefix}{k}"] = v

            flatten_dict(processed_config)

            # Check and send configuration items that need to be sent via MQTT
            for key, value in flat_config.items():
                if key in mqtt_config_keys:
                    logger.info(f"Send partial configuration update via MQTT: {key} = {value}")
                    udp_device_manager.send_partial_config(device_id, key, value)

        emit('update_config_result', {'status': 'success'})

# def save_all_device_configs():
#     """Save all device configurations"""
#     for device_id, config in device_configs.items():
#         save_device_config(device_id, config)
#     logger.info("Saved all device configurations")

# # Modify exit handler to save both chat history and device configurations
# def save_all_data():
#     save_all_chat_histories()
#     save_all_device_configs()
#     logger.info("Saved all data")

# # Update exit registration function
# atexit.register(save_all_data)


# ------------------------ Chat History Event Handlers ------------------------
chat_message_handler = None

def register_chat_message_handler(handler):
    """Register chat message handler and also register to event system"""
    global chat_message_handler
    chat_message_handler = handler

    # Also register to event system
    event_system.register('new_chat_message', handler)

    logger.info("Registered chat message handler to global variable and event system")

@socketio.on('new_chat_message')
def handle_new_chat_message(data):
    logger.info(f"Received chat message via socketio or event system: {data}")
    logger.info(f"Data type: {type(data)}")
    device_id = data.get('device_id')
    message = data.get('message')

    # Add more logs for debugging
    logger.info(f"Device ID: {device_id}, Message type: {type(message)}")

    # Rewrite audio paths
    if isinstance(message, dict) and 'message' in message and isinstance(message['message'], dict) and message['message'].get('type') == 'text':
        msg_content = message['message']
        if 'audio_path' in msg_content and msg_content['audio_path']:
            old_path = msg_content['audio_path']
            filename = os.path.basename(old_path)
            new_path = f"/api/audio/{device_id}/{filename}"
            msg_content['audio_path'] = new_path
            logger.info(f"Rewrote audio path: {old_path} -> {new_path}")

    if not device_id or not message:
        logger.error("Missing device_id or message")
        return {'status': 'error', 'message': 'Missing device ID or message content'}

    # Validate device
    device_details = get_device_details(device_id)
    if not device_details:
        logger.error(f"Device not found: {device_id}")
        return {'status': 'error', 'message': 'Device not found'}

    # Get user_id from message, prioritize user_id in message
    # Check if in request context, if not, don't use session
    try:
        from flask import has_request_context
        if has_request_context():
            # In request context, can use session
            user_id = message.get('user_id', session.get('user_id', "user001"))
        else:
            # Not in request context, only use user_id from message or default value
            user_id = message.get('user_id', "user001")
    except Exception as e:
        # If any error occurs, use user_id from message or default value
        user_id = message.get('user_id', "user001")
        logger.warning(f"Error getting user ID, using default value: {e}")

    logger.info(f"Using user ID: {user_id} to process message for device {device_id}")

    # Return success immediately to avoid client waiting
    response = {'status': 'success'}

    # Put message processing in background thread, pass user_id
    def process_message(user_id_param):
        try:
            logger.info(f"Start processing message: user {user_id_param}, device {device_id}")

            # Rewrite audio paths
            if 'message' in message and isinstance(message['message'], dict) and message['message'].get('type') == 'text':
                msg_content = message['message']
                if 'audio_path' in msg_content and msg_content['audio_path']:
                    old_path = msg_content['audio_path']
                    filename = os.path.basename(old_path)
                    new_path = f"/api/audio/{device_id}/{filename}"
                    msg_content['audio_path'] = new_path
                    logger.info(f"Rewrote audio path: {old_path} -> {new_path}")

            # Use passed parameter, no longer access session
            try:
                ensure_chat_directories(user_id_param, device_id)
            except Exception as e:
                logger.error(f"Error ensuring chat directories exist: {e}")
                # Continue execution, don't interrupt entire processing due to directory creation failure

            # Add message to memory, ensure user ID is saved in message
            message['user_id'] = user_id_param  # Ensure message contains user ID

            try:
                with chat_histories_lock:
                    logger.info(f"Adding message to chat history for user: {user_id_param}, device: {device_id}")

                    # Use (user_id, device_id) as key
                    if (user_id_param, device_id) not in chat_histories:
                        logger.info(f"Creating new chat history for user: {user_id_param}, device: {device_id}")
                        try:
                            messages = load_chat_history_by_user_id(device_id, user_id_param)
                            chat_histories[(user_id_param, device_id)] = {
                                'messages': messages,
                                'last_saved': time.time()
                            }
                            logger.info(f"Loaded {len(messages)} historical messages")
                        except Exception as e:
                            logger.error(f"Error loading chat history: {e}")
                            # If loading fails, create empty history record
                            chat_histories[(user_id_param, device_id)] = {
                                'messages': [],
                                'last_saved': time.time()
                            }

                    # Prevent duplicate addition of same message
                    message_id = message.get('timestamp', '') + message.get('sender', '') + str(hash(str(message.get('message', {}))))
                    existing_ids = [m.get('timestamp', '') + m.get('sender', '') for m in chat_histories[(user_id_param, device_id)]['messages']]

                    if message_id not in existing_ids:
                        logger.info(f"Adding new message from {message.get('sender')}")
                        chat_histories[(user_id_param, device_id)]['messages'].append(message)
                        logger.info(f"Message added, total count: {len(chat_histories[(user_id_param, device_id)]['messages'])}")
                    else:
                        logger.info(f"Duplicate message detected, skipping")
            except Exception as e:
                logger.error(f"Error processing chat history: {e}", exc_info=True)

            # Broadcast new message to all clients viewing this device's chat page
            try:
                room_name = f"device_{device_id}"
                logger.info(f"Broadcasting message to room: {room_name}, user_id: {user_id_param}")

                # Check if socketio is available
                if socketio and hasattr(socketio, 'emit'):
                    socketio.emit('chat_update', {
                        'device_id': device_id,
                        'message': message,
                        'user_id': user_id_param  # Include user ID so client can filter
                    }, room=room_name)
                    logger.info("Message broadcast complete")
                else:
                    logger.warning("socketio not available, cannot broadcast message")
            except Exception as e:
                logger.error(f"Error broadcasting message: {e}", exc_info=True)

            # Check if need to save - pass user ID
            try:
                save_chat_history_by_user_id(device_id, user_id_param)
                logger.info(f"Immediately save chat history after message processing: user {user_id_param}, device {device_id}")
            except Exception as e:
                logger.error(f"Error saving chat history: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}", exc_info=True)

    # Start background thread to process message, pass user_id
    threading.Thread(target=lambda: process_message(user_id), daemon=True).start()

    # Return success response immediately, don't wait for processing to complete
    return response

# Chat history save function that doesn't depend on session
def save_chat_history_by_user_id(device_id, user_id):
    """Save chat history to file (receive user ID as parameter to avoid accessing session in thread)"""
    logger.info(f"Start saving chat history: user {user_id}, device {device_id}")

    try:
        with chat_histories_lock:
            if (user_id, device_id) not in chat_histories:
                logger.warning(f"Attempting to save non-existent chat history: user {user_id}, device {device_id}")
                return

            messages = chat_histories[(user_id, device_id)]['messages']
            if not messages:
                logger.warning(f"Chat history is empty, not saving: user {user_id}, device {device_id}")
                return
    except Exception as e:
        logger.error(f"Error getting chat history: {e}")
        return

    # Check if user has permission to access the device
    try:
        # Check device access permission
        has_access = check_device_access(user_id, device_id)
        if not has_access:
            logger.warning(f"User {user_id} attempting to save chat history for unauthorized device {device_id}")
            # For calls through event system, we might want to continue saving as this might be internal system call
            # So here we don't return directly, but log warning
    except Exception as e:
        logger.error(f"Error checking device access permission: {e}")
        # Continue execution, don't interrupt saving due to permission check failure

    try:
        # Ensure directory exists
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'user'))
        user_dir = os.path.abspath(os.path.join(base_dir, user_id))
        device_dir = os.path.abspath(os.path.join(user_dir, device_id))
        chat_dir = os.path.abspath(os.path.join(device_dir, 'chat_history', 'text'))

        os.makedirs(chat_dir, exist_ok=True)

        chat_file = os.path.abspath(os.path.join(chat_dir, 'chat_history.json'))

        # Write to file
        with open(chat_file, 'w', encoding='utf-8') as f:
            json.dump(messages, f, ensure_ascii=False, indent=4)

        logger.info(f"Saved chat history for user {user_id} device {device_id}, total {len(messages)} messages")
        return True
    except Exception as e:
        logger.error(f"Failed to save chat history: {str(e)}")
        logger.exception("Detailed error information:")
        return False


# Chat history loading function that doesn't depend on session
def load_chat_history_by_user_id(device_id, user_id):
    """Load chat history from file (receive user ID as parameter to avoid accessing session in thread)"""
    logger.info(f"Start loading chat history: user {user_id}, device {device_id}")

    # Check if user has permission to access the device
    try:
        # Check device access permission
        has_access = check_device_access(user_id, device_id)
        if not has_access:
            logger.warning(f"User {user_id} attempting to load chat history for unauthorized device {device_id}")
            # For calls through event system, we might want to continue loading as this might be internal system call
            # So here we don't return empty list directly, but log warning
    except Exception as e:
        logger.error(f"Error checking device access permission: {e}")
        # Continue execution, don't interrupt loading due to permission check failure

    # Ensure directory structure exists
    try:
        ensure_chat_directories(user_id, device_id)
    except Exception as e:
        logger.error(f"Error ensuring chat directories exist: {e}")
        # Continue execution, try to load file

    try:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'user'))
        user_dir = os.path.abspath(os.path.join(base_dir, user_id))
        device_dir = os.path.abspath(os.path.join(user_dir, device_id))
        chat_file = os.path.abspath(os.path.join(device_dir, 'chat_history', 'text', 'chat_history.json'))

        if os.path.exists(chat_file):
            with open(chat_file, 'r', encoding='utf-8') as f:
                messages = json.load(f)
                logger.info(f"Loaded chat history for user {user_id} device {device_id}, total {len(messages)} messages")
                return messages
        else:
            logger.info(f"Chat history file does not exist: {chat_file}, returning empty list")
            return []
    except Exception as e:
        logger.error(f"Failed to load chat history: {str(e)}")
        logger.exception("Detailed error information:")
        return []

# Join device "room" to receive chat updates for that device
@socketio.on('join_device_room')
def on_join_device_room(data):
    user_id = data.get('user_id') or session.get('user_id')
    device_id = data.get('device_id')
    if device_id and user_id:
        # Use user-specific room name, containing user ID and device ID
        room_name = f"device_{device_id}"
        join_room(room_name)
        logger.info(f"Client joined device room: {room_name}, sid: {request.sid}, user_id: {user_id}")
        emit('status', {'msg': f'Joined room for device {device_id}', 'user_id': user_id})

        # Try to load and send current summary
        try:
            # Build message.json path
            message_path = os.path.join('user', user_id, device_id, 'chat_history', 'message.json')
            if os.path.exists(message_path):
                with open(message_path, 'r', encoding='utf-8') as f:
                    messages = json.load(f)
                    # Extract summary (first message)
                    summary = messages[0]['content'] if messages and messages[0]['role'] == 'system' else ""
                    # Send summary to client
                    emit('summary_update', {
                        'device_id': device_id,
                        'user_id': user_id,
                        'summary': summary
                    })
                    logger.debug(f"Sent initial summary to client: device_id={device_id}, user_id={user_id}")
        except Exception as e:
            logger.warning(f"Failed to load and send initial summary: {str(e)}")

# Handle summary update events
@socketio.on('summary_update')
def handle_summary_update(data):
    """Handle summary update events, broadcast updates to all clients in related device room"""
    device_id = data.get('device_id')
    user_id = data.get('user_id')
    summary = data.get('summary', '')

    if not device_id or not user_id:
        logger.warning(f"Received incomplete summary update: {data}")
        return

    logger.info(f"Received summary update: device_id={device_id}, user_id={user_id}")

    # Broadcast to all clients in device room
    room_name = f"device_{device_id}"
    socketio.emit('summary_update', {
        'device_id': device_id,
        'user_id': user_id,
        'summary': summary
    }, room=room_name)
    logger.debug(f"Broadcasted summary update: device_id={device_id}, user_id={user_id}")

@socketio.on('leave_device_room')
def on_leave_device_room(data):
    user_id = data.get('user_id') or session.get('user_id')
    device_id = data.get('device_id')
    if device_id and user_id:
        # Use user-specific room name, containing user ID and device ID
        room_name = f"device_{device_id}"
        leave_room(room_name)
        logger.info(f"Client left device room: {room_name}, sid: {request.sid}, user_id: {user_id}")
        emit('status', {'msg': f'Left room for device {device_id}', 'user_id': user_id})

        # Ensure chat history for this user exists in memory
        with chat_histories_lock:
            if (user_id, device_id) not in chat_histories:
                chat_histories[(user_id, device_id)] = {
                    'messages': load_chat_history_by_user_id(device_id, user_id),
                    'last_saved': time.time()
                }
                logger.info(f"Loaded chat history for user {user_id} device {device_id}")
    else:
        logger.warning(f"Client tried to leave room but didn't provide necessary parameters, device_id: {device_id}, user_id: {user_id}, sid: {request.sid}")

# Periodically save chat history
def maybe_save_chat_history(device_id):
    try:
        # Get user ID from session
        from flask import has_request_context
        if has_request_context():
            user_id = session.get('user_id', "user001")  # Default value for compatibility with old code
        else:
            # Not in request context, cannot access session
            logger.warning("Not in request context, cannot save chat history")
            return

        with chat_histories_lock:
            # Use (user_id, device_id) as key
            if (user_id, device_id) in chat_histories:
                # Save chat history directly
                save_chat_history_by_user_id(device_id, user_id)
    except Exception as e:
        logger.error(f"Error saving chat history: {str(e)}")
        # Continue execution, don't interrupt program due to save failure

# Save chat history to file - compatible with old code
def save_chat_history(device_id):
    try:
        # Get user ID from session
        from flask import has_request_context
        if has_request_context():
            user_id = session.get('user_id', "user001")  # Default value for compatibility with old code
        else:
            # Not in request context, cannot access session
            logger.warning("Not in request context, cannot save chat history")
            return False

        # Call new save function
        return save_chat_history_by_user_id(device_id, user_id)
    except Exception as e:
        logger.error(f"Error saving chat history: {str(e)}")
        return False

# Load chat history from file - compatible with old code
def load_chat_history(device_id):
    try:
        # Get user ID from session
        from flask import has_request_context
        if has_request_context():
            user_id = session.get('user_id', "user001")  # Default value for compatibility with old code
        else:
            # Not in request context, cannot access session
            logger.warning("Not in request context, cannot load chat history")
            return []

        # Call new load function
        return load_chat_history_by_user_id(device_id, user_id)
    except Exception as e:
        logger.error(f"Error loading chat history: {str(e)}")
        return []

def ensure_chat_directories(user_id, device_id):
    """Ensure directory structure required for chat history exists"""
    logger.info(f"Ensure chat directories exist: user {user_id}, device {device_id}")

    if not user_id or not device_id:
        logger.error(f"Invalid user ID or device ID: user_id={user_id}, device_id={device_id}")
        return False

    try:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'user'))
        user_dir = os.path.abspath(os.path.join(base_dir, user_id))
        device_dir = os.path.abspath(os.path.join(user_dir, device_id))
        chat_text_dir = os.path.abspath(os.path.join(device_dir, 'chat_history', 'text'))
        chat_audio_dir = os.path.abspath(os.path.join(device_dir, 'chat_history', 'audio'))

        # Create all required directories
        os.makedirs(chat_text_dir, exist_ok=True)
        os.makedirs(chat_audio_dir, exist_ok=True)
        logger.info(f"Created chat history directories: {chat_text_dir} and {chat_audio_dir}")
        return True
    except Exception as e:
        logger.error(f"Failed to create chat history directories: {str(e)}")
        logger.exception("Detailed error information:")
        return False

# Save all chat histories on exit
def save_all_chat_histories():
    with chat_histories_lock:
        for (user_id, device_id) in chat_histories:
            save_chat_history_by_user_id(device_id, user_id)
    logger.info("Saved all users' device chat histories")

# Register exit handler
import atexit
atexit.register(save_all_chat_histories)


# ------------------------ Device Discovery and Connection Handling ------------------------
@socketio.on('trigger_discovery')
def handle_trigger_discovery():
    """Trigger UDP broadcast for device discovery"""
    logger.info("Received device discovery request, triggering UDP broadcast")

    # Return success response immediately to avoid client waiting
    emit('discovery_triggered', {'status': 'success'})

    # Call UDP device manager's broadcast method
    try:
        # If UDP device manager has broadcast method, call it directly
        # No longer use background thread to avoid thread safety issues
        if hasattr(udp_device_manager, 'broadcast_server_info'):
            try:
                udp_device_manager.broadcast_server_info()
                logger.info("UDP broadcast sent successfully")
            except Exception as e:
                logger.error(f"Error sending UDP broadcast: {str(e)}")
                logger.exception("Detailed error information:")
        else:
            # If no broadcast method, use default UDP discovery mechanism
            logger.warning("UDP device manager has no broadcast_server_info method, using default discovery mechanism")

            try:
                import socket
                import json

                # Create broadcast socket
                broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

                # Get local IP
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    s.connect(('8.8.8.8', 80))
                    server_ip = s.getsockname()[0]
                except Exception:
                    server_ip = '127.0.0.1'
                finally:
                    s.close()

                # Create broadcast message
                message = {
                    "server_ip": server_ip,
                    "udp_port": 8884,  # Default UDP port
                    "mqtt_broker": "broker.emqx.io",  # Default MQTT broker
                    "mqtt_port": 1883,  # Default MQTT port
                    "timestamp": time.time()
                }

                # Send broadcast
                broadcast_socket.sendto(
                    json.dumps(message).encode(),
                    ('<broadcast>', 50000)  # Default discovery port
                )

                logger.info(f"Sent default UDP broadcast: {message}")

            except Exception as e:
                logger.error(f"Error sending default UDP broadcast: {str(e)}")
                logger.exception("Detailed error information:")
            finally:
                if 'broadcast_socket' in locals():
                    broadcast_socket.close()
    except Exception as e:
        logger.error(f"Error triggering device discovery: {str(e)}")
        logger.exception("Detailed error information:")

@socketio.on('request_device_info')
def handle_request_device_info(data):
    """
    Request detailed information for specific device.

    Data format example:
    {
        "device_id": "rasp1"
    }

    Return format example:
    {
        "status": "success",
        "device_info": {
            "id": "rasp1",
            "ip": "192.168.1.100",
            "model": "raspberry_pi_4",
            "status": "online",
            "online": true
        }
    }
    """
    device_id = data.get('device_id')
    if not device_id:
        emit('device_info_result', {'status': 'error', 'message': 'Missing device_id'})
        return

    logger.info(f"Received device info request: {device_id}")

    # Verify user has permission to access the device
    user_id = session.get('user_id')
    if not user_id:
        emit('device_info_result', {'status': 'error', 'message': 'User not logged in'})
        return

    # Check device access permission directly using user ID
    if not check_device_access(user_id, device_id):
        emit('device_info_result', {'status': 'error', 'message': 'No permission to access this device'})
        return

    # Get device information
    device_details = get_device_details(device_id)
    if not device_details:
        emit('device_info_result', {'status': 'error', 'message': 'Device not found'})
        return

    # Prepare return data (excluding sensitive information)
    device_info = {
        'id': device_id
    }

    # Add other non-sensitive fields
    for key, value in device_details.items():
        if key not in ['password', 'sid', 'authenticated']:
            device_info[key] = value

    # Add online status
    online = False
    udp_devices = udp_device_manager.get_all_devices()
    if device_id in udp_devices:
        # Use device status from UDP device manager
        online = udp_devices[device_id].get('status', 'offline') == 'online'
    else:
        # Use WebSocket connection status
        online = device_details.get('sid') is not None

    device_info['online'] = online

    # Return device information
    emit('device_info_result', {
        'status': 'success',
        'device_info': device_info
    })
    logger.info(f"Returned information for device {device_id}")

@socketio.on('request_devices_list')
def handle_request_devices_list():
    """Return list of currently known devices, including user-accessible devices and newly discovered devices"""
    logger.info("Received device list request")

    try:
        user_id = session.get('user_id')
        if not user_id:
            logger.warning("User not logged in, returning empty device list")
            emit('devices_list', {'devices': []})
            return

        # Get user information - use user ID directly
        from database import UserManager
        user_info = UserManager.get_user_by_id(user_id)
        if not user_info:
            logger.warning(f"User {user_id} does not exist, returning empty device list")
            emit('devices_list', {'devices': []})
            return

        # Ensure user has devices field
        user_devices = user_info.get('devices', [])
        if not isinstance(user_devices, list):
            logger.warning(f"User {user_id} devices field is not a list, using empty list")
            user_devices = []

        # Build device list
        device_list = []

        try:
            # 1. First add devices already associated with user
            for device_id in user_devices:
                try:
                    # Check if device exists in unified configuration manager
                    device_details = get_device_details(device_id)

                    # If device not in unified configuration manager but exists in UDP device manager, add to unified configuration manager
                    udp_devices = udp_device_manager.get_all_devices()
                    if not device_details and device_id in udp_devices:
                        udp_device = udp_devices[device_id]
                        # Set device details to unified configuration manager
                        set_device_details(device_id, 'ip', udp_device.get('ip', 'unknown'))
                        set_device_details(device_id, 'authenticated', True)
                        set_device_details(device_id, 'sid', None)
                        set_device_details(device_id, 'user_id', user_id)
                        device_details = get_device_details(device_id)
                        logger.info(f"Added device {device_id} from UDP device manager to unified configuration manager")

                    if device_details:
                        # Check if device is online
                        online = False
                        # Get all devices from UDP device manager
                        udp_devices = udp_device_manager.get_all_devices()
                        if device_id in udp_devices:
                            # Use device status from UDP device manager
                            online = udp_devices[device_id].get('status', 'offline') == 'online'
                        else:
                            # Use WebSocket connection status
                            online = device_details.get('sid') is not None

                        # Get device personalized name and IP configuration
                        personalized_name = get_device_personalized_name(device_id)
                        device_ip = get_device_ip_from_config(device_id, device_details.get('ip', 'unknown'))

                        device_list.append({
                            'id': device_id,
                            'name': personalized_name,  # Use personalized name
                            'ip': device_ip,  # Use IP from configuration or default IP
                            'online': online,
                            'model': device_details.get('model', ''),
                            'status': device_details.get('status', 'unknown'),
                            'user_id': device_details.get('user_id', user_id),  # Use user_id from device or default to current user
                            'owned': True  # Mark as user-owned device
                        })
                    else:
                        # Device doesn't exist, but still add to list, mark as offline
                        logger.warning(f"Device {device_id} does not exist in unified configuration manager or UDP device manager")
                        # Even if device is offline, try to get personalized name
                        personalized_name = get_device_personalized_name(device_id)

                        device_list.append({
                            'id': device_id,
                            'name': personalized_name,  # Use personalized name
                            'ip': 'unknown',
                            'online': False,
                            'owned': True  # Mark as user-owned device
                        })
                except Exception as e:
                    logger.error(f"Error processing user device {device_id}: {str(e)}")
                    logger.exception("Detailed error information:")
                    continue  # Continue processing next device

            # 2. Add all online devices not associated with any user (new devices)
            # Get all devices from unified configuration manager
            if os.path.exists("device_configs"):
                for device_dir in os.listdir("device_configs"):
                    device_path = os.path.join("device_configs", device_dir)
                    if os.path.isdir(device_path):
                        device_id = device_dir
                        try:
                            # Skip devices already added to list (user's own devices)
                            if device_id in user_devices:
                                continue

                            device_details = get_device_details(device_id)
                            if device_details:
                                # Check if device has user_id field
                                device_user_id = device_details.get('user_id')

                                # If device has no user_id, user_id is None or empty string, consider as new device
                                if device_user_id is None or device_user_id == "":
                                    # Check if device is online
                                    online = False
                                    udp_devices = udp_device_manager.get_all_devices()
                                    if device_id in udp_devices:
                                        online = udp_devices[device_id].get('status', 'offline') == 'online'
                                    else:
                                        online = device_details.get('sid') is not None

                                    # Additional check: ensure device status is actually online
                                    device_status = device_details.get('status', 'offline')
                                    if device_status != 'online':
                                        online = False

                                    # Check device last active time (only show devices active within last 5 minutes)
                                    import time
                                    last_seen = device_details.get('last_seen', 0)
                                    current_time = time.time()
                                    if current_time - last_seen > 300:  # 5 minutes = 300 seconds
                                        online = False

                                    # Only add online new devices
                                    if online:
                                        # Get device personalized name and IP configuration
                                        personalized_name = get_device_personalized_name(device_id)
                                        device_ip = get_device_ip_from_config(device_id, device_details.get('ip', 'unknown'))

                                        device_list.append({
                                            'id': device_id,
                                            'name': personalized_name,  # Use personalized name
                                            'ip': device_ip,  # Use IP from configuration or default IP
                                            'online': online,
                                            'model': device_details.get('model', ''),
                                            'status': device_details.get('status', 'unknown'),
                                            'owned': False  # Mark as unowned device
                                        })
                                # If device already has user_id but not current user, skip and don't display
                                # If device has user_id, check if it's current user's device (may exist in database but not in user_devices list)
                                elif device_user_id == user_id:
                                    # Check if device is online
                                    online = False
                                    udp_devices = udp_device_manager.get_all_devices()
                                    if device_id in udp_devices:
                                        online = udp_devices[device_id].get('status', 'offline') == 'online'
                                    else:
                                        online = device_details.get('sid') is not None

                                    # Additional check: ensure device status is actually online
                                    device_status = device_details.get('status', 'offline')
                                    if device_status != 'online':
                                        online = False

                                    # Get device personalized name and IP configuration
                                    personalized_name = get_device_personalized_name(device_id)
                                    device_ip = get_device_ip_from_config(device_id, device_details.get('ip', 'unknown'))

                                    device_list.append({
                                        'id': device_id,
                                        'name': personalized_name,  # Use personalized name
                                        'ip': device_ip,  # Use IP from configuration or default IP
                                        'online': online,
                                        'model': device_details.get('model', ''),
                                        'status': device_details.get('status', 'unknown'),
                                        'user_id': device_user_id,
                                        'owned': True  # Mark as user-owned device
                                    })
                        except Exception as e:
                            logger.error(f"Error processing device {device_id}: {str(e)}")
                            logger.exception("Detailed error information:")
                            continue  # Continue processing next device

            # 3. Add all online devices from UDP device manager that are not in unified configuration manager
            udp_devices = udp_device_manager.get_all_devices()
            for device_id, udp_device in udp_devices.items():
                try:
                    # Skip devices already added to list
                    device_details = get_device_details(device_id)
                    if device_details:
                        continue

                    # Check if device is online
                    online = udp_device.get('status', 'offline') == 'online'

                    # Check device last active time (only show devices active within last 5 minutes)
                    import time
                    last_seen = udp_device.get('last_seen', 0)
                    current_time = time.time()
                    if current_time - last_seen > 300:  # 5 minutes = 300 seconds
                        online = False

                    # Only add online devices
                    if online:
                        # Check if device has user_id field
                        device_user_id = udp_device.get('user_id')

                        # If device has no user_id, user_id is None or empty string, consider as new device
                        if device_user_id is None or device_user_id == "":
                            # Get device personalized name and IP configuration
                            personalized_name = get_device_personalized_name(device_id)
                            device_ip = get_device_ip_from_config(device_id, udp_device.get('ip', 'unknown'))

                            device_list.append({
                                'id': device_id,
                                'name': personalized_name,  # Use personalized name
                                'ip': device_ip,  # Use IP from configuration or default IP
                                'online': online,
                                'model': udp_device.get('model', ''),
                                'status': udp_device.get('status', 'unknown'),
                                'owned': False  # Mark as unowned device
                            })
                        # If device has user_id, check if it's current user's device
                        elif device_user_id == user_id:
                            # Get device personalized name and IP configuration
                            personalized_name = get_device_personalized_name(device_id)
                            device_ip = get_device_ip_from_config(device_id, udp_device.get('ip', 'unknown'))

                            device_list.append({
                                'id': device_id,
                                'name': personalized_name,  # Use personalized name
                                'ip': device_ip,  # Use IP from configuration or default IP
                                'online': online,
                                'model': udp_device.get('model', ''),
                                'status': udp_device.get('status', 'unknown'),
                                'user_id': device_user_id,
                                'owned': True  # Mark as user-owned device
                            })
                        # If device already has user_id but not current user, skip and don't display
                except Exception as e:
                    logger.error(f"Error processing UDP device {device_id}: {str(e)}")
                    logger.exception("Detailed error information:")
                    continue  # Continue processing next device
        except Exception as e:
            logger.error(f"Error building device list: {str(e)}")
            logger.exception("Detailed error information:")
            # If error occurs, return empty list
            emit('devices_list', {'devices': []})
            return

        logger.info(f"Returning device list: {len(device_list)} devices")
        emit('devices_list', {'devices': device_list})
    except Exception as e:
        logger.error(f"Error processing device list request: {str(e)}")
        logger.exception("Detailed error information:")
        # If error occurs, return empty list
        emit('devices_list', {'devices': []})

@socketio.on('connect_device')
def handle_connect_device(data):
    """Handle device connection request"""
    device_id = data.get('device_id')
    password = data.get('password')

    if not device_id:
        emit('connection_result', {'success': False, 'message': 'Device ID cannot be empty'})
        return

    logger.info(f"Received device connection request: {device_id}")

    # Verify device exists
    device_details = get_device_details(device_id)
    if not device_details:
        emit('connection_result', {'success': False, 'message': 'Device not found'})
        return

    # Verify device is online
    online = False
    udp_devices = udp_device_manager.get_all_devices()
    if device_id in udp_devices:
        # Use device status from UDP device manager
        online = udp_devices[device_id].get('status', 'offline') == 'online'
    else:
        # Use WebSocket connection status
        online = device_details.get('sid') is not None

    if not online:
        emit('connection_result', {'success': False, 'message': 'Device is offline'})
        return

    # Verify password
    if device_details.get('password') and device_details.get('password') != password:
        emit('connection_result', {'success': False, 'message': 'Password Failed'})
        return

    # Update device authentication status
    set_device_details(device_id, 'authenticated', True)

    # Associate user with device
    user_id = session.get('user_id')
    if user_id:
        success = bind_device_to_user(user_id, device_id)
        if not success:
            logger.warning(f"Failed to add device {device_id} to user {user_id}")
            # Even if adding device to user fails, we still allow connection, just log warning
        else:
            logger.info(f"Successfully bound device {device_id} to user {user_id}")
    else:
        logger.warning(f"User not logged in, cannot add device {device_id} to user")

    # Return success result
    emit('connection_result', {
        'success': True,
        'message': 'Connection successful',
        'redirect': url_for('control_panel', device_id=device_id)
    })



# ------------------------ Page Routes ------------------------
@app.route('/')
def index():
    # Change default homepage to user homepage - using redesigned page
    return render_template('user_main_page.html')

# Add new route for device discovery page
@app.route('/discovery')
@login_required  # Add login requirement
def discovery_model():
    return render_template('discovery_model.html')

@app.route('/debug_devices')
@login_required  # Add login requirement
def debug_devices():
    return render_template('debug_devices.html')

@app.route('/about_us')
def about_us():
    return render_template('about_us.html')

@app.route('/faq')
def faq():
    return render_template('faq.html')

@app.route('/terms_of_use')
def terms_of_use():
    return render_template('terms_of_use.html')

@app.route('/privacy_policy')
def privacy_policy():
    return render_template('privacy_policy.html')

# @app.route('/test_socket_data.html')
# def test_socket_data():
#     """Test Socket data page"""
#     with open('test_socket_data.html', 'r', encoding='utf-8') as f:
#         return f.read()

@app.route('/settings/<device_id>')
def settings_page(device_id):
    """Device settings page"""
    return render_template('settings_page.html', device_id=device_id)

@app.route('/api/devices')
def get_devices():
    """Get list of all authenticated devices"""
    authenticated_devices = []

    # Get all devices from unified configuration manager
    if os.path.exists("device_configs"):
        for device_dir in os.listdir("device_configs"):
            device_path = os.path.join("device_configs", device_dir)
            if os.path.isdir(device_path):
                device_id = device_dir
                device_details = get_device_details(device_id)
                if device_details and device_details.get('authenticated', False):
                    authenticated_devices.append({
                        'id': device_id,
                        'ip': device_details.get('ip', 'unknown')
                    })

    return {
        'status': 'success',
        'devices': authenticated_devices
    }

@app.route('/api/statistics')
def get_statistics():
    """Get homepage statistics data"""
    try:
        from database import UserManager
        from wake_stats_manager import wake_stats_manager

        # Get database statistics data
        stats = UserManager.get_statistics()
        if not stats:
            return {
                'status': 'error',
                'message': 'Failed to get statistics data'
            }

        # Get voice wake count
        wake_count = wake_stats_manager.get_wake_count()

        # Combine statistics data
        result = {
            'status': 'success',
            'data': {
                'active_users': stats['active_users'],
                'times_awakened': wake_count,
                'response_time': stats['response_time'],
                'activated_yumis': stats['activated_yumis']
            }
        }

        logger.info(f"Statistics data: {result['data']}")
        return result

    except Exception as e:
        logger.error(f"Error getting statistics data: {e}")
        return {
            'status': 'error',
            'message': f'Failed to get statistics data: {str(e)}'
        }

@app.route('/api/admin/dashboard-stats')
def get_admin_dashboard_stats():
    """Get admin dashboard statistics data"""
    # Check if user is logged in as admin
    if session.get('role') != 'admin':
        return jsonify({
            'status': 'error',
            'message': 'Insufficient permissions'
        }), 403

    try:
        from database import UserManager
        from database_admin import AdminManager
        from wake_stats_manager import wake_stats_manager

        # Get total registered users
        user_stats = AdminManager.get_user_stats()
        registered_users = user_stats['total_users'] if user_stats else 0

        # Get total models (from user_model table)
        conn = UserManager.get_connection()
        total_models = 0
        if conn:
            try:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT COUNT(DISTINCT model_id) as total FROM user_model")
                result = cursor.fetchone()
                total_models = result['total'] if result else 0
            except Exception as e:
                logger.error(f"Failed to get total models: {e}")
            finally:
                if conn and conn.is_connected():
                    cursor.close()
                    conn.close()

        # Get online device count (Active Models)
        active_models = 0
        try:
            if udp_device_manager:
                all_devices = udp_device_manager.get_all_devices()
                # Count devices with online status
                active_models = sum(1 for device in all_devices.values()
                                  if device.get('status') == 'online')
        except Exception as e:
            logger.error(f"Failed to get online device count: {e}")

        # Get total interactions (wake count)
        total_interactions = wake_stats_manager.get_wake_count()

        # Combine statistics data
        result = {
            'status': 'success',
            'data': {
                'registered_users': registered_users,
                'total_models': total_models,
                'active_models': active_models,
                'total_interactions': total_interactions
            }
        }

        logger.info(f"Admin dashboard statistics data: {result['data']}")
        return jsonify(result)

    except Exception as e:
        logger.error(f"Error getting admin dashboard statistics data: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Failed to get statistics data: {str(e)}'
        }), 500


@app.route('/api/user/devices')
@login_required
def get_user_devices():
    """Get list of devices accessible to current logged-in user"""
    user_id = session.get('user_id')
    if not user_id:
        return {'status': 'error', 'message': 'Not logged in'}, 401

    # Get user-accessible devices
    from database import UserManager
    user_info = UserManager.get_user_by_id(user_id)
    if not user_info or 'devices' not in user_info:
        return {'status': 'error', 'message': 'No device access permission'}, 403

    authorized_devices = []
    for device_id in user_info['devices']:
        device_details = get_device_details(device_id)
        if device_details:
            # Get device personalized name and IP configuration
            personalized_name = get_device_personalized_name(device_id)
            device_ip = get_device_ip_from_config(device_id, device_details.get('ip', 'unknown'))

            authorized_devices.append({
                'id': device_id,
                'name': personalized_name,  # Use personalized name
                'ip': device_ip,  # Use IP from configuration
                'online': device_details.get('sid') is not None
            })

    return {'status': 'success', 'devices': authorized_devices}


@app.route('/control')
@login_required  # Add login requirement
def control_panel():
    device_id = request.args.get('device_id')
    view = request.args.get('view')

    if not device_id:
        # If device_id not passed, redirect back to discovery page
        return redirect(url_for('index'))

    # Verify user has access permission to this device
    user_id = session.get('user_id')
    if not check_device_access(user_id, device_id):
        flash('You do not have permission to access this device', 'error')
        return redirect(url_for('index'))

    device_details = get_device_details(device_id)

    if not device_details or not device_details.get('authenticated'):
        return redirect(url_for('index'))

    # Check if device is initialized
    is_initialized = False
    try:
        # Try to read device configuration file
        config_path = os.path.join("device_configs", device_id, "new_settings.json")
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # Check system.initialized field
                is_initialized = config.get("system", {}).get("initialized", False)
                logger.info(f"Device {device_id} initialization status: {is_initialized}")
    except Exception as e:
        logger.error(f"Error reading device {device_id} configuration file: {e}")
        # If error occurs, default to not initialized
        is_initialized = False

    # Select different templates based on view parameter
    if view == 'chat':
        # Get device personalized name for chat page title
        device_name = get_device_personalized_name(device_id)
        return render_template('chat_page.html',
                              device_ip=device_details.get('ip', ''),
                              device_id=device_id,
                              device_name=device_name)
    elif view == 'settings':
        return render_template('settings_page.html', device_ip=device_details.get('ip', ''), device_id=device_id, user_id=user_id)
    else:
        # Default display control panel, pass initialization status
        return render_template('control_panel.html',
                              device_ip=device_details.get('ip', ''),
                              device_id=device_id,
                              is_initialized=is_initialized,
                              user_id=user_id)

@app.route('/chat_page')
def chat_page_redirect():
    """Redirect to chat page with device ID"""
    # Try to find first authenticated device
    authenticated_device = None

    # Get all devices from unified configuration manager
    if os.path.exists("device_configs"):
        for device_dir in os.listdir("device_configs"):
            device_path = os.path.join("device_configs", device_dir)
            if os.path.isdir(device_path):
                device_id = device_dir
                device_details = get_device_details(device_id)
                if device_details and device_details.get('authenticated', False):
                    authenticated_device = (device_id, device_details)
                    break

    if authenticated_device:
        return redirect(url_for('control_panel', device_id=authenticated_device[0], view='chat'))
    else:
        # If no authenticated device, redirect to discovery page
        return redirect(url_for('index'))



# Add to page routes section
@app.route('/chat_page/<device_id>')
def chat_page_legacy(device_id):
    """Backward compatibility: redirect old format URL to new format"""
    return redirect(url_for('control_panel', device_id=device_id, view='chat'))



@app.route('/api/chat_history/<device_id>')
@login_required  # Add login requirement
def get_chat_history(device_id):
    """Get chat history between current logged-in user and specific device"""
    logger.info(f"Request chat history for device {device_id}")

    # Get user ID from session
    user_id = session.get('user_id')
    if not user_id:
        return {'status': 'error', 'message': 'Please log in first'}, 403

    # Verify user has access permission to this device
    if not check_device_access(user_id, device_id):
        return {'status': 'error', 'message': 'You do not have permission to access this device'}, 403

    # Verify user has access permission to this device
    device_details = get_device_details(device_id)
    if not device_details:
        return {'status': 'error', 'message': 'Device not found'}, 404

    try:
        # First check if chat history for this device exists in memory
        chat_history = None
        source = 'file'  # Default source is file

        with chat_histories_lock:
            # Check chat history using (user_id, device_id) as key
            if (user_id, device_id) in chat_histories:
                # If data exists in memory, prioritize memory data
                logger.info(f"Get chat history for user {user_id} device {device_id} from memory, total {len(chat_histories[(user_id, device_id)]['messages'])} messages")
                chat_history = chat_histories[(user_id, device_id)]['messages'][:]  # Create copy
                source = 'memory'

                # Convert audio paths to API paths
                for item in chat_history:
                    if 'message' in item and isinstance(item['message'], dict):
                        if 'audio_path' in item['message'] and item['message']['audio_path']:
                            # Extract filename from original path
                            original_path = item['message']['audio_path']
                            filename = os.path.basename(original_path)
                            # Replace with new API path
                            new_path = f"/api/audio/{device_id}/{filename}"
                            logger.info(f"API path conversion: {original_path} -> {new_path}")
                            item['message']['audio_path'] = new_path

        # After leaving with statement block, lock is released, safe to call
        if chat_history is not None:
            # Only save when data exists in memory
            save_chat_history_by_user_id(device_id, user_id)
            return {'status': 'success', 'data': chat_history, 'source': source}

        # If no data in memory, read from file
        return {'status': 'success', 'data': load_chat_history_by_user_id(device_id, user_id)}

    except Exception as e:
        logger.error(f"Failed to read chat history: {str(e)}")
        return {'status': 'error', 'message': 'Failed to read chat history'}, 500


from flask import send_file  # Add to file top import section

@app.route('/api/schedules/<device_id>')
@login_required
def get_device_schedules(device_id):
    """Get schedule data for specified device"""
    logger.info(f"Request schedule data for device {device_id}")

    # Get user ID from session
    user_id = session.get('user_id')
    if not user_id:
        return {'status': 'error', 'message': 'Please log in first'}, 403

    # Verify user has access permission to this device
    if not check_device_access(user_id, device_id):
        return {'status': 'error', 'message': 'You do not have permission to access this device'}, 403

    # Verify device exists
    device_details = get_device_details(device_id)
    if not device_details:
        return {'status': 'error', 'message': 'Device not found'}, 404

    try:
        # Use ScheduleHandler to load schedule data
        schedule_handler = ScheduleHandler(user_id=user_id, device_id=device_id)
        schedules = schedule_handler.load_schedules()

        # Sort by time
        schedules.sort(key=lambda x: x["time"])

        logger.info(f"Successfully loaded schedule data for device {device_id}, total {len(schedules)} items")
        return {'status': 'success', 'schedules': schedules}

    except Exception as e:
        logger.error(f"Failed to load schedule data for device {device_id}: {str(e)}")
        return {'status': 'error', 'message': f'Failed to load schedule data: {str(e)}'}, 500

@app.route('/read_file')
@login_required
def read_file():
    """Read file content, mainly for reading message.json"""
    # Get file path
    file_path = request.args.get('path')
    if not file_path:
        return jsonify({'error': 'File path not provided'}), 400

    # Security check: ensure path contains user ID to prevent unauthorized access
    user_id = session['user_id']
    if f'user/{user_id}/' not in file_path and f'user\\{user_id}\\' not in file_path:
        return jsonify({'error': 'No permission to access this file'}), 403

    try:
        # Read file content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = json.load(f)
        return jsonify(content)
    except FileNotFoundError:
        return jsonify({'error': 'File not found'}), 404
    except json.JSONDecodeError:
        return jsonify({'error': 'File format error'}), 400
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {str(e)}")
        return jsonify({'error': f'Error reading file: {str(e)}'}), 500

@app.route('/api/audio/<device_id>/<filename>')
@login_required  # Add login requirement
def get_audio_file(device_id, filename):
    """Provide access to chat audio files"""
    # Get user ID from session
    user_id = session.get('user_id')
    if not user_id:
        return "Please log in first", 403

    # Verify user has access permission to this device
    if not check_device_access(user_id, device_id):
        return "You do not have permission to access audio files for this device", 403

    try:
        # Safely build file path to avoid path traversal
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'user'))
        user_dir = os.path.abspath(os.path.join(base_dir, user_id))
        device_dir = os.path.abspath(os.path.join(user_dir, device_id))
        audio_dir = os.path.abspath(os.path.join(device_dir, 'chat_history', 'audio'))
        audio_file = os.path.abspath(os.path.join(audio_dir, filename))

        # Security check: ensure file is within expected directory and filename has no potentially dangerous characters
        if not audio_file.startswith(base_dir) or '..' in filename or '/' in filename:
            logger.error(f"Attempted to access illegal path: {audio_file}")
            return "Access denied", 403

        # Check if file exists
        if not os.path.exists(audio_file) or not os.path.isfile(audio_file):
            logger.error(f"Audio file not found: {audio_file}")
            return "File not found", 404

        # Return file (PCM format)
        return send_file(audio_file, mimetype='audio/pcm')
    except Exception as e:
        logger.error(f"Failed to serve audio file: {str(e)}")
        return "Error serving audio file", 500


# Add static file access route, especially for avatar files
@app.route('/static/<path:filename>')
def serve_static(filename):
    """Provide static file access, mainly for uploaded files like avatars"""
    # Get the directory where this script is located (yumi-server directory)Add commentMore actions
    current_dir = os.path.dirname(os.path.abspath(__file__))
    static_folder = os.path.join(current_dir, 'static')
    file_path = os.path.join(static_folder, filename)
    print(f"Accessing static file: {file_path}")
    if os.path.exists(file_path):
        return send_file(file_path)
    else:
        print(f"File not found: {file_path}")
        return "File not found", 404

# Add dedicated route to handle avatar paths - provide alternative access method
@app.route('/avatar/<user_id>/<path:filename>')
def serve_avatar(user_id, filename):
    """Dedicated user avatar access"""
    # URL decode the filename to handle spaces and special characters
    import urllib.parse
    filename = urllib.parse.unquote(filename)

    # Get the directory where this script is located (yumi-server directory)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    static_folder = os.path.join(current_dir, 'static')
    avatar_dir = os.path.join(static_folder, 'avatars', str(user_id))

    # Try to find the file directly
    avatar_path = os.path.join(avatar_dir, filename)
    print(f"Accessing avatar file: {avatar_path}")

    if os.path.exists(avatar_path):
        return send_file(avatar_path)
    else:
        # If not found, try listing the directory to see if there's a filename that matches
        # (in case of encoding issues)
        try:
            if os.path.exists(avatar_dir):
                for file in os.listdir(avatar_dir):
                    if filename in file or file in filename:
                        alt_path = os.path.join(avatar_dir, file)
                        print(f"Found alternative file: {alt_path}")
                        return send_file(alt_path)
        except Exception as e:
            logger.error(f"Error finding alternative file: {str(e)}")

        print(f"Avatar file not found: {avatar_path}")
        return "Avatar not found", 404

# Added admin routes
@app.route('/admin')
@app.route('/admin_main_page')  # Keep this for backward compatibility
def admin_main_page():
    """Display admin main page - only accessible to admins"""
    # Check if the user is logged in as admin
    if session.get('role') != 'admin':
        flash('You do not have permission to access this page', 'error')
        return redirect(url_for('auth.login_page'))

    return render_template('admin_main_page.html', admin_username=session.get('admin_username'))

@app.route('/admin/manage_users')
def admin_manage_users():
    """Display admin user management page - only accessible to admins"""
    # Check if the user is logged in as admin
    if session.get('role') != 'admin':
        flash('You do not have permission to access this page', 'error')
        return redirect(url_for('auth.login_page'))

    return render_template('admin_manage_user.html', admin_username=session.get('admin_username'))

@app.route('/admin/modify_config')
def admin_modify_config():
    try:
        # Use unified_config to get complete constant configuration
        config_data = unified_config._load_config_file(unified_config.paths['const'])

        if not config_data:
            flash("Unable to get configuration data", "error")
            logger.error("Unable to get configuration data")
            config_data = {}

        logger.debug(f"Retrieved configuration data structure: {list(config_data.keys()) if config_data else 'None'}")

    except Exception as e:
        flash(f"Error occurred while getting configuration data: {str(e)}", "error")
        logger.error(f"Failed to get configuration data: {e}")
        config_data = {}

    return render_template('admin_modify_config.html', config=config_data)

@app.route('/admin/save_config', methods=['POST'])
def admin_save_config():
    """Save configuration settings using const_config"""
    # Check if user is logged in as admin
    if session.get('role') != 'admin':
        return jsonify({
            'success': False,
            'message': 'You do not have permission to perform this operation'
        })

    try:
        # Process form data
        form_data = request.form

        # Process each form field
        for key, value in form_data.items():
            # Process model data in hidden fields
            if key.startswith('model_data_'):
                try:
                    model_data = json.loads(value)
                    path = model_data.get('path')

                    # Check if it's TTS service languages field
                    if 'languages' in model_data:
                        languages = model_data.get('languages', {})
                        if path and languages:
                            # Use unified_config.set to set languages object
                            set_config(path, languages)
                        continue

                    models = model_data.get('models', [])

                    if path and models:
                        # Use unified_config.set to set model array
                        set_config(path, models)
                except json.JSONDecodeError:
                    logger.error(f"Error parsing model data: {value}")
                continue

            if '.' in key:  # Process nested keys (e.g. "TTS.use_azure")
                # Convert checkbox values to boolean
                if value == 'on':
                    value = True
                elif value == '':
                    # Empty string for checkbox means unchecked
                    value = False

                # Try to preserve original data type
                if key.endswith('.api_key') or key.endswith('.token'):
                    # API keys and tokens should be strings
                    value = str(value)
                elif key.endswith('.enable') or key.startswith('use_'):
                    # Enable flags should be boolean
                    value = bool(value)
                elif key.endswith('.port') or key.endswith('_port'):
                    # Ports should be integers
                    try:
                        value = int(value)
                    except (ValueError, TypeError):
                        # If conversion fails, keep as string
                        pass

                # Use unified_config.set to set value
                set_config(key, value)
            else:
                # Process top-level keys
                set_config(key, value)

        # Process unchecked checkboxes (they won't be submitted in form)
        # List of all possible checkbox fields
        checkbox_fields = [
            'TTS.use_azure', 'TTS.use_bytedance',
            'LLM.use_openai', 'LLM.use_deepseek', 'LLM.use_groq',
            'music_player.enabled'
        ]

        for field in checkbox_fields:
            if field not in form_data:
                set_config(field, False)

        # Configuration automatically saved to file
        logger.debug("Configuration automatically saved to file")

        logger.info("Admin configuration saved successfully")

        return jsonify({
            'success': True,
            'message': 'Configuration saved successfully'
        })

    except Exception as e:
        error_message = f"Error saving configuration: {str(e)}"
        logger.error(error_message)
        return jsonify({
            'success': False,
            'message': error_message
        })

@app.route('/admin/reset_config')
def admin_reset_config():
    """Reset configuration to default values"""
    # Check if user is logged in as admin
    if session.get('role') != 'admin':
        return jsonify({
            'success': False,
            'message': 'You do not have permission to perform this operation'
        })

    try:
        # Create backup of current configuration
        backup_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f'config/const_settings_backup_{backup_time}.json'

        # Ensure backup directory exists
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)

        # Copy current configuration to backup
        with open('config/const_settings.json', 'r', encoding='utf-8') as src:
            with open(backup_path, 'w', encoding='utf-8') as dst:
                dst.write(src.read())

        # Reinitialize configuration using unified_config's default configuration reset functionality
        from unified_config import unified_config

        # Reset configuration to default values
        unified_config.reset_to_defaults()

        # Reload configuration to unified_config
        # Note: unified_config will automatically reload configuration from file
        logger.info("Configuration reset, unified_config will automatically reload")

        logger.info(f"Admin configuration reset to default values. Backup saved to {backup_path}")

        return jsonify({
            'success': True,
            'message': 'Configuration reset to default values. Your previous configuration has been backed up.'
        })

    except Exception as e:
        error_message = f"Error resetting configuration: {str(e)}"
        logger.error(error_message)
        return jsonify({
            'success': False,
            'message': error_message
        })

@app.route('/api/unbind_device/<device_id>', methods=['POST'])
@login_required
def handle_unbind_device(device_id):
    """Handle user request to unbind device"""
    # Get current logged-in user
    user_id = session.get('user_id')
    if not user_id:
        logger.error("No logged-in user detected when attempting to unbind device")
        return jsonify({'success': False, 'message': 'Please log in first'}), 401

    logger.info(f"User {user_id} requests to unbind device {device_id}")

    # Check device access permission directly using user ID
    # First check if user has permission to access the device
    has_access = check_device_access(user_id, device_id)
    if not has_access:
        logger.warning(f"User {user_id} attempted to unbind device {device_id} without permission")
        return jsonify({'success': False, 'message': 'You do not have permission to unbind this device'}), 403

    # Execute unbind operation
    success = unbind_device_from_user(user_id, device_id)

    if success:
        logger.info(f"Successfully unbound device {device_id} from user {user_id}")
        return jsonify({'success': True, 'message': 'Device unbound successfully'})
    else:
        logger.error(f"Failed to unbind device {device_id} from user {user_id}")
        return jsonify({'success': False, 'message': 'Device unbind failed, please try again later'}), 500

@app.route('/api/system/resources')
def get_system_resources():
    """Get system resource usage including CPU, memory and disk"""
    try:
        # Get CPU information
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count(logical=True)

        # Get memory information
        memory = psutil.virtual_memory()

        # Get disk information
        disk = psutil.disk_usage('/')

        # Format size
        def format_bytes(bytes):
            """Convert bytes to human-readable format"""
            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                if bytes < 1024:
                    return f"{bytes:.2f} {unit}"
                bytes /= 1024
            return f"{bytes:.2f} PB"

        # Build response data
        resources = {
            'cpu': {
                'usage': cpu_percent,
                'cores': cpu_count
            },
            'memory': {
                'total': format_bytes(memory.total),
                'available': format_bytes(memory.available),
                'used': format_bytes(memory.used),
                'percent': memory.percent
            },
            'disk': {
                'total': format_bytes(disk.total),
                'used': format_bytes(disk.used),
                'free': format_bytes(disk.free),
                'percent': disk.percent
            }
        }

        return jsonify(resources)
    except Exception as e:
        logger.error(f"Failed to get system resource information: {str(e)}")
        return jsonify({'error': str(e)}), 500


# # Add TTS audio sending function
# def send_tts_audio(device_id, audio_data, use_raw_pcm=None):
#     """
#     Send TTS audio data to device via UDP

#     Args:
#         device_id: Device ID
#         audio_data: PCM audio data generated by TTS
#         use_raw_pcm: Whether to use raw PCM transmission, determined by bytedanceTTS.py

#     Returns:
#         bool: Whether successfully sent
#     """
#     try:
#         logger.info(f"Preparing to send TTS audio to device {device_id} via UDP")

#         # Check if device exists
#         with devices_lock:
#             if device_id not in devices:
#                 logger.warning(f"Device {device_id} does not exist, cannot send TTS audio")
#                 return False

#             # Check if device is online
#             device_online = False
#             if device_id in udp_device_manager.devices:
#                 device_online = udp_device_manager.devices[device_id].get('status', 'offline') == 'online'

#             if not device_online:
#                 logger.warning(f"Device {device_id} is offline, cannot send TTS audio")
#                 return False

#         # Use UDP device manager to send audio, directly pass use_raw_pcm parameter provided by bytedanceTTS.py
#         success = udp_device_manager.send_tts_audio(device_id, audio_data, use_raw_pcm)

#         if success:
#             pcm_mode = "Raw PCM" if use_raw_pcm else "Opus encoded"
#             logger.info(f"Successfully sent TTS audio to device {device_id} via UDP, using {pcm_mode}")
#         else:
#             logger.warning(f"Failed to send TTS audio to device {device_id} via UDP")

#         return success

#     except Exception as e:
#         logger.error(f"Error sending TTS audio: {e}")
#         return False

# Function to handle TTS audio events


def handle_tts_audio_event(data):
    """Handle TTS audio events, send audio to specific device

    Args:
        data: Event data containing device_id, audio_data and use_raw_pcm

    Returns:
        bool: Whether successfully processed
    """
    device_id = data.get('device_id')
    audio_data = data.get('audio_data')
    use_raw_pcm = data.get('use_raw_pcm')

    if not device_id or not audio_data:
        logger.error("TTS audio event missing required parameters")
        return False

    # logger.info(f"Received TTS audio event, target device: {device_id}, data size: {len(audio_data)} bytes")

    # Use UDP device manager to send audio
    success = udp_device_manager.send_tts_audio(device_id, audio_data, use_raw_pcm)

    if not success:
        logger.warning(f"Failed to send TTS audio to device {device_id}")

    return success

# Handle WebSocket configuration save requests
@socketio.on('save_config')
def handle_save_config(data):
    """Handle WebSocket configuration save requests"""
    # Check if user is logged in as admin
    if session.get('role') != 'admin':
        emit('save_config_response', {
            'success': False,
            'message': 'You do not have permission to perform this operation'
        })
        return

    try:
        # Process form data
        form_data = data

        # Process each form field
        for key, value in form_data.items():
            # Process model data in hidden fields
            if key.startswith('model_data_'):
                try:
                    model_data = value  # Already parsed object
                    path = model_data.get('path')

                    # Check if it's TTS service languages field
                    if 'languages' in model_data:
                        languages = model_data.get('languages', {})
                        if path and languages:
                            # Use unified_config.set to set languages object
                            set_config(path, languages)
                        continue

                    models = model_data.get('models', [])

                    if path and models:
                        # Use unified_config.set to set model array
                        set_config(path, models)
                except Exception as e:
                    logger.error(f"Error parsing model data: {str(e)}")
                continue

            if '.' in key:  # Process nested keys (e.g. "TTS.use_azure")
                # Convert checkbox values to boolean
                if value == 'on':
                    value = True
                elif value == '':
                    # Empty string for checkbox means unchecked
                    value = False

                # Try to preserve original data type
                if key.endswith('.api_key') or key.endswith('.token'):
                    # API keys and tokens should be strings
                    value = str(value)
                elif key.endswith('.enable') or key.startswith('use_'):
                    # Enable flags should be boolean
                    value = bool(value)
                elif key.endswith('.port') or key.endswith('_port'):
                    # Ports should be integers
                    try:
                        value = int(value)
                    except (ValueError, TypeError):
                        # If conversion fails, keep as string
                        pass

                # Use unified_config.set to set value
                set_config(key, value)
            else:
                # Process top-level keys
                set_config(key, value)

        # Process unchecked checkboxes (they won't be submitted in form)
        # List of all possible checkbox fields
        checkbox_fields = [
            'TTS.use_azure', 'TTS.use_bytedance',
            'LLM.use_openai', 'LLM.use_deepseek', 'LLM.use_groq',
            'music_player.enabled'
        ]

        for field in checkbox_fields:
            if field not in form_data:
                set_config(field, False)

        # Configuration automatically saved to file
        logger.debug("Configuration automatically saved to file")

        logger.info("Admin configuration saved successfully (via WebSocket)")

        emit('save_config_response', {
            'success': True,
            'message': 'Configuration saved successfully'
        })

    except Exception as e:
        error_message = f"Error saving configuration: {str(e)}"
        logger.error(error_message)
        emit('save_config_response', {
            'success': False,
            'message': error_message
        })

# Handle WebSocket configuration reset requests
@socketio.on('reset_config')
def handle_reset_config():
    """Handle WebSocket configuration reset requests"""
    # Check if user is logged in as admin
    if session.get('role') != 'admin':
        emit('reset_config_response', {
            'success': False,
            'message': 'You do not have permission to perform this operation'
        })
        return

    try:
        # Create backup of current configuration
        backup_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f'config/const_settings_backup_{backup_time}.json'

        # Ensure backup directory exists
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)

        # Copy current configuration to backup
        with open('config/const_settings.json', 'r', encoding='utf-8') as src:
            with open(backup_path, 'w', encoding='utf-8') as dst:
                dst.write(src.read())

        # Reinitialize configuration using unified_config's default configuration reset functionality
        from unified_config import unified_config

        # Reset configuration to default values
        unified_config.reset_to_defaults()

        # Reload configuration to unified_config
        # Note: unified_config will automatically reload configuration from file
        logger.info("Configuration reset, unified_config will automatically reload")

        logger.info(f"Admin configuration reset to default values (via WebSocket). Backup saved to {backup_path}")

        emit('reset_config_response', {
            'success': True,
            'message': 'Configuration reset to default values. Your previous configuration has been backed up.'
        })

    except Exception as e:
        error_message = f"Error resetting configuration: {str(e)}"
        logger.error(error_message)
        emit('reset_config_response', {
            'success': False,
            'message': error_message
        })

# Handle WebSocket personality reset requests
@socketio.on('reset_personality')
def handle_reset_personality(data):
    """Handle WebSocket personality reset requests"""
    logger.info(f"Received reset_personality request: {data}")

    device_id = data.get('device_id')
    if not device_id:
        logger.error("reset_personality request missing device_id parameter")
        emit('reset_personality_response', {
            'success': False,
            'message': 'Missing device_id parameter'
        })
        return

    # Verify user has permission to access the device
    user_id = session.get('user_id')
    if not user_id:
        logger.error("reset_personality request: user not logged in")
        emit('reset_personality_response', {
            'success': False,
            'message': 'User not logged in'
        })
        return

    # Check device access permission
    if not check_device_access(user_id, device_id):
        logger.error(f"reset_personality request: user {user_id} has no permission to access device {device_id}")
        emit('reset_personality_response', {
            'success': False,
            'message': 'You do not have permission to access this device'
        })
        return

    try:
        logger.info(f"Start resetting personality settings for device {device_id}, user: {user_id}")

        # 1. Clear all values in user_personalization
        user_personalization_fields = ['name', 'age', 'hobbies', 'region', 'profile']
        for field in user_personalization_fields:
            success = unified_config.set(f"user_personalization.{field}", "", device_id=device_id)
            if not success:
                logger.warning(f"Failed to clear user_personalization.{field}")

        # 2. Clear all values in device_role_personalization
        device_role_fields = ['name', 'age', 'relationship', 'personality', 'background']
        for field in device_role_fields:
            success = unified_config.set(f"device_role_personalization.{field}", "", device_id=device_id)
            if not success:
                logger.warning(f"Failed to clear device_role_personalization.{field}")

        # 3. Set system.initialized to false
        success = unified_config.set("system.initialized", False, device_id=device_id)
        if not success:
            logger.warning(f"Failed to set system.initialized to false")

        # 4. Delete content in user data folder
        success = delete_user_data(user_id, device_id)
        if not success:
            logger.warning(f"Failed to delete user data")

        # 5. Clean chat history in server memory
        try:
            with chat_histories_lock:
                if (user_id, device_id) in chat_histories:
                    del chat_histories[(user_id, device_id)]
                    logger.info(f"Cleaned chat history in memory: user {user_id}, device {device_id}")
        except Exception as e:
            logger.warning(f"Failed to clean chat history in memory: {e}")

        # 6. Reset LLM instance messages in prechat instances
        try:
            # Get device service instance from udp_device_manager
            if hasattr(udp_device_manager, 'device_services') and device_id in udp_device_manager.device_services:
                device_service = udp_device_manager.device_services[device_id]

                if device_service and hasattr(device_service, 'prechatManager') and device_service.prechatManager:
                    # Reset LLM instance messages completely
                    if hasattr(device_service.prechatManager, 'state') and device_service.prechatManager.state:
                        # Reset chatmodule messages - completely reinitialize with empty summary
                        if hasattr(device_service.prechatManager.state, 'chatmodule') and device_service.prechatManager.state.chatmodule:
                            if hasattr(device_service.prechatManager.state.chatmodule, 'init_system'):
                                device_service.prechatManager.state.chatmodule.init_system("")
                                logger.info(f"Reset LLM chatmodule messages for device {device_id}")

                        # Reset LLM manager instance messages - completely reinitialize with empty summary
                        if hasattr(device_service.prechatManager.state, 'llm_manager') and device_service.prechatManager.state.llm_manager:
                            if hasattr(device_service.prechatManager.state.llm_manager, 'llm_instance') and device_service.prechatManager.state.llm_manager.llm_instance:
                                if hasattr(device_service.prechatManager.state.llm_manager.llm_instance, 'init_system'):
                                    device_service.prechatManager.state.llm_manager.llm_instance.init_system("")
                                    logger.info(f"Reset LLM manager instance messages for device {device_id}")

                    # Also reset the main llm_manager if it exists - completely reinitialize with empty summary
                    if hasattr(device_service.prechatManager, 'llm_manager') and device_service.prechatManager.llm_manager:
                        if hasattr(device_service.prechatManager.llm_manager, 'llm_instance') and device_service.prechatManager.llm_manager.llm_instance:
                            if hasattr(device_service.prechatManager.llm_manager.llm_instance, 'init_system'):
                                device_service.prechatManager.llm_manager.llm_instance.init_system("")
                                logger.info(f"Reset main LLM manager instance messages for device {device_id}")

                    # Additionally, clear any cached messages in all LLM instances directly
                    # Clear state.chatmodule messages
                    if hasattr(device_service.prechatManager.state, 'chatmodule') and device_service.prechatManager.state.chatmodule:
                        if hasattr(device_service.prechatManager.state.chatmodule, 'messages'):
                            # Force clear the messages list and reinitialize
                            device_service.prechatManager.state.chatmodule.messages = []
                            device_service.prechatManager.state.chatmodule.init_system("")
                            logger.info(f"Force cleared and reinitialized state.chatmodule messages for device {device_id}")

                    # Clear llm_manager.llm_instance messages
                    if hasattr(device_service.prechatManager, 'llm_manager') and device_service.prechatManager.llm_manager:
                        if hasattr(device_service.prechatManager.llm_manager, 'llm_instance') and device_service.prechatManager.llm_manager.llm_instance:
                            if hasattr(device_service.prechatManager.llm_manager.llm_instance, 'messages'):
                                device_service.prechatManager.llm_manager.llm_instance.messages = []
                                device_service.prechatManager.llm_manager.llm_instance.init_system("")
                                logger.info(f"Force cleared and reinitialized llm_manager.llm_instance messages for device {device_id}")

                    # Clear state.llm_manager.llm_instance messages (if different from above)
                    if hasattr(device_service.prechatManager.state, 'llm_manager') and device_service.prechatManager.state.llm_manager:
                        if hasattr(device_service.prechatManager.state.llm_manager, 'llm_instance') and device_service.prechatManager.state.llm_manager.llm_instance:
                            if hasattr(device_service.prechatManager.state.llm_manager.llm_instance, 'messages'):
                                device_service.prechatManager.state.llm_manager.llm_instance.messages = []
                                device_service.prechatManager.state.llm_manager.llm_instance.init_system("")
                                logger.info(f"Force cleared and reinitialized state.llm_manager.llm_instance messages for device {device_id}")

                    logger.info(f"Successfully reset LLM instance messages for device {device_id}")
                else:
                    logger.warning(f"Device service for {device_id} does not have prechatManager")
            else:
                logger.warning(f"Device service for {device_id} not found in udp_device_manager")
        except Exception as e:
            logger.warning(f"Failed to reset LLM instance messages: {e}")

        logger.info(f"Successfully reset personality settings for device {device_id}")

        emit('reset_personality_response', {
            'success': True,
            'message': 'Personality settings have been completely reset. All memories and configurations have been permanently deleted.'
        })

    except Exception as e:
        error_message = f"Error resetting personality settings: {str(e)}"
        logger.error(error_message)
        emit('reset_personality_response', {
            'success': False,
            'message': f'Error resetting personality settings: {str(e)}'
        })

def delete_user_data(user_id, device_id):
    """Clear all data file content related to user and device, but preserve directory structure"""
    try:
        import json

        # Build user device data directory path
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'user'))
        user_dir = os.path.abspath(os.path.join(base_dir, user_id))
        device_dir = os.path.abspath(os.path.join(user_dir, device_id))

        if os.path.exists(device_dir):
            # Clear chat history files but preserve directory structure
            chat_history_dir = os.path.join(device_dir, 'chat_history')
            if os.path.exists(chat_history_dir):
                # Clear message.json
                message_file = os.path.join(chat_history_dir, 'message.json')
                if os.path.exists(message_file):
                    with open(message_file, 'w', encoding='utf-8') as f:
                        json.dump([], f)
                    logger.info(f"Cleared chat history file: {message_file}")

                # Clear text/chat_history.json
                text_dir = os.path.join(chat_history_dir, 'text')
                if os.path.exists(text_dir):
                    text_history_file = os.path.join(text_dir, 'chat_history.json')
                    if os.path.exists(text_history_file):
                        with open(text_history_file, 'w', encoding='utf-8') as f:
                            json.dump([], f)
                        logger.info(f"Cleared text chat history file: {text_history_file}")

                # Delete audio files but preserve audio directory
                audio_dir = os.path.join(chat_history_dir, 'audio')
                if os.path.exists(audio_dir):
                    for filename in os.listdir(audio_dir):
                        file_path = os.path.join(audio_dir, filename)
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                    logger.info(f"Cleared audio file directory: {audio_dir}")

            # Clear schedule files but preserve directory structure
            schedule_dir = os.path.join(device_dir, 'schedule')
            if os.path.exists(schedule_dir):
                # Clear schedule.data
                schedule_file = os.path.join(schedule_dir, 'schedule.data')
                if os.path.exists(schedule_file):
                    with open(schedule_file, 'w', encoding='utf-8') as f:
                        json.dump([], f)
                    logger.info(f"Cleared schedule file: {schedule_file}")

                # Clear log.txt
                log_file = os.path.join(schedule_dir, 'log.txt')
                if os.path.exists(log_file):
                    with open(log_file, 'w', encoding='utf-8') as f:
                        f.write('')
                    logger.info(f"Cleared schedule log file: {log_file}")

            logger.info(f"Cleared user data content but preserved directory structure: {device_dir}")
        else:
            logger.info(f"User data directory does not exist: {device_dir}")

        return True

    except Exception as e:
        logger.error(f"Error clearing user data: {str(e)}")
        return False

# Handle summary update events
def handle_summary_update(data):
    """Handle summary update events, broadcast updates to all clients in related device room"""
    device_id = data.get('device_id')
    user_id = data.get('user_id')
    summary = data.get('summary', '')

    if not device_id or not user_id:
        logger.warning(f"Received incomplete summary update: {data}")
        return False

    logger.info(f"Received summary update event: device_id={device_id}, user_id={user_id}")

    # Broadcast to all clients in device room
    room_name = f"device_{device_id}"
    socketio.emit('summary_update', {
        'device_id': device_id,
        'user_id': user_id,
        'summary': summary
    }, room=room_name)
    logger.debug(f"Broadcasted summary update: device_id={device_id}, user_id={user_id}")
    return True

# Device information request handler for admin panel
def handle_device_info_request(data):
    """Handle device information requests from admin panel via event system

    Args:
        data: Event data containing request_type and optional parameters

    Returns:
        dict: Device information or error message
    """
    request_type = data.get('request_type')

    try:
        if request_type == 'get_all_devices':
            # Return all devices from UDP device manager
            return {
                'success': True,
                'data': udp_device_manager.get_all_devices()
            }
        elif request_type == 'get_device_status':
            device_id = data.get('device_id')
            if not device_id:
                return {'success': False, 'message': 'Missing device_id'}

            udp_devices = udp_device_manager.get_all_devices()
            if device_id in udp_devices:
                return {
                    'success': True,
                    'data': udp_devices[device_id]
                }
            else:
                return {'success': False, 'message': 'Device not found'}
        elif request_type == 'get_mqtt_client_status':
            # 检查UDP设备管理器的MQTT客户端状态
            try:
                mqtt_available = (hasattr(udp_device_manager, 'mqtt_client') and
                                udp_device_manager.mqtt_client is not None and
                                hasattr(udp_device_manager, 'is_connected') and
                                udp_device_manager.is_connected)
                return {
                    'success': True,
                    'data': {'mqtt_available': mqtt_available}
                }
            except Exception as e:
                return {'success': False, 'message': f'Error checking MQTT status: {str(e)}'}
        elif request_type == 'send_mqtt_message':
            # 通过UDP设备管理器发送MQTT消息
            topic = data.get('topic')
            message = data.get('message')
            if not topic or not message:
                return {'success': False, 'message': 'Missing topic or message'}

            try:
                if (hasattr(udp_device_manager, 'mqtt_client') and
                    udp_device_manager.mqtt_client is not None and
                    hasattr(udp_device_manager, 'is_connected') and
                    udp_device_manager.is_connected):

                    import json
                    message_str = json.dumps(message) if isinstance(message, dict) else str(message)
                    result = udp_device_manager.mqtt_client.publish(topic, message_str)

                    if result.rc == 0:
                        return {'success': True, 'message': 'MQTT message sent successfully'}
                    else:
                        return {'success': False, 'message': f'MQTT publish failed with code: {result.rc}'}
                else:
                    return {'success': False, 'message': 'MQTT client not available'}
            except Exception as e:
                return {'success': False, 'message': f'Error sending MQTT message: {str(e)}'}
        else:
            return {'success': False, 'message': 'Unknown request type'}
    except Exception as e:
        logger.error(f"Error handling device info request: {str(e)}")
        return {'success': False, 'message': str(e)}

# Register event handlers
event_system.register('new_chat_message', handle_new_chat_message)
event_system.register('tts_audio_ready', handle_tts_audio_event)
event_system.register('summary_update', handle_summary_update)
event_system.register('device_info_request', handle_device_info_request)
logger.info("Registered event handlers to event system")

if __name__ == '__main__':
    import signal
    def signal_handler(_sig, _frame):
        # _sig and _frame parameters are standard parameters for signal handler functions, underscore prefix indicates intentional non-use
        logger.info("Received termination signal, cleaning up resources...")

        # Set all devices to offline status and save details
        save_all_device_details()

        # Save all chat histories
        save_all_chat_histories()

        # Stop UDP device manager
        udp_device_manager.stop()

        logger.info("Resource cleanup completed")
        sys.exit(0)

    # Register signal handler functions
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Register exit handler to ensure device status is saved in any case
    import atexit
    atexit.register(save_all_device_details)

    # Start server
    logger.info("Server starting, device information loaded and set to offline status")
    # Completely disable debug mode to avoid double initialization
    app.debug = False
    socketio.run(app, host="0.0.0.0", port=SOCKETIO_PORT, debug=False)
