import os
import json
from datetime import datetime
from mysql.connector import Error

from flask import Blueprint, request, redirect, url_for, flash, render_template, session, jsonify, send_file
from functools import wraps
from loguru import logger

# Reuse database configuration from database.py
from database import UserManager

# Import event system for UDP device manager communication
from event_system import event_system
from unified_config import (
    unified_config, get_device_details, ensure_device_details,
    update_device_details
)

# Blueprint Initialization
# Create a blueprint for admin routes with the prefix '/admin'
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# System log file path definitions
# Use paths relative to the project root directory instead of relying on specific drive paths (e.g., C drive)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # yumi-server directory
DEVICE_CONFIG_PATH = os.path.join(BASE_DIR, 'device_configs')  # Updated path: yumi-server/device_configs
DEVICE_LOG_BASE_PATH = os.path.join(BASE_DIR, 'device_log')  # Retain old path for compatibility

# Log handling helper function
def get_device_log_path(device_id, log_file='system.log'):
    """
    Construct the path for device log files, flexibly based on the current project structure

    Args:
        device_id: Device ID
        log_file: Log file name, default is system.log

    Returns:
        dict: Contains the log directory and the full path of the log file
    """
    # First, try the new path: yumi-server/device_configs/{device_id}/system.log
    log_dir = os.path.join(DEVICE_CONFIG_PATH, device_id)
    log_file_path = os.path.join(log_dir, log_file)

    # If the new path does not exist, try the old path
    if not os.path.exists(log_file_path):
        # Attempt to find it under yumi-server/device_log
        log_dir = os.path.join(DEVICE_LOG_BASE_PATH, device_id)
        log_file_path = os.path.join(log_dir, log_file)

        # If it still does not exist, try finding it under the device_log directory in the project root
        if not os.path.exists(log_file_path):
            parent_dir = os.path.dirname(BASE_DIR)  # Project root directory
            log_dir = os.path.join(parent_dir, 'device_log', device_id)
            log_file_path = os.path.join(log_dir, log_file)

    logger.debug(f"Calculated log directory path: {log_dir}")
    logger.debug(f"Calculated log file path: {log_file_path}")

    return {
        'log_dir': log_dir,
        'log_file': log_file_path
    }

# Admin permission decorator
def admin_required(f):
    """Decorator to ensure that only administrators can access specific routes

    If not an administrator, redirect to the login page
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('role') == 'admin':
            flash('Administrator privileges required', 'error')
            return redirect(url_for('auth.login_page'))
        return f(*args, **kwargs)
    return decorated_function

# Local implementations of server functions to avoid circular imports
def find_device_owner(device_id):
    """Query which user owns this device_id device from database.

    Returns user ID (format 'user001') instead of username
    """
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

def deep_merge_config(config, default_config):
    """Deep merge configuration with default configuration"""
    if not isinstance(config, dict) or not isinstance(default_config, dict):
        return config if config is not None else default_config

    result = default_config.copy()
    for key, value in config.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_config(value, result[key])
        else:
            result[key] = value
    return result

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
            default_config_path = os.path.join(BASE_DIR, 'config', 'default_setting.json')
            if os.path.exists(default_config_path):
                try:
                    with open(default_config_path, 'r', encoding='utf-8') as f:
                        default_config = json.load(f)

                    # Use deep merge, especially protect TTS and LLM configurations
                    config = deep_merge_config(config, default_config)

                    # Update device ID
                    if 'system' in config:
                        config['system']['device_id'] = device_id

                    # Save updated configuration
                    unified_config._save_config_file(file_path, config)
                    logger.info(f"Supplemented complete configuration for device {device_id}")
                except Exception as e:
                    logger.error(f"Failed to load default configuration: {str(e)}")

        return config if config else {}
    except Exception as e:
        logger.error(f"Failed to load device configuration: {str(e)}")
        return {}

def get_udp_devices_via_event():
    """Get all devices from UDP device manager via event system"""
    try:
        # Send device info request via event system
        result = event_system.emit('device_info_request', {
            'request_type': 'get_all_devices'
        })

        # Check if we got a valid response
        if isinstance(result, dict) and result.get('success'):
            return result.get('data', {})
        else:
            logger.warning(f"Failed to get UDP devices via event system: {result}")
            return {}
    except Exception as e:
        logger.error(f"Failed to get UDP devices via event system: {str(e)}")
        return {}

# Admin functionality class
class AdminManager:
    """Handles all database operations related to administrators"""

    @staticmethod
    def get_all_users(page=1, limit=10, search_term=None):
        """
        Retrieve a list of all users, supporting pagination and search

        Args:
            page: Current page number (starting from 1)
            limit: Number of items per page
            search_term: Search keyword (username, email, or ID)

        Returns:
            dict: Contains the user list and pagination information
        """
        conn = UserManager.get_connection()
        if not conn:
            logger.error("Database connection failed")
            return None

        cursor = None
        try:
            cursor = conn.cursor(dictionary=True, buffered=True)

            # Calculate total number of users (for pagination)
            count_query = "SELECT COUNT(*) as total FROM users"
            count_params = []

            # If there is a search condition, add a WHERE clause
            if search_term:
                count_query += """ WHERE user_id LIKE %s
                               OR user_username LIKE %s
                               OR user_email LIKE %s"""
                search_pattern = f"%{search_term}%"
                count_params = [search_pattern, search_pattern, search_pattern]

            cursor.execute(count_query, count_params)
            total = cursor.fetchone()['total']

            # Close the first cursor and create a new one for the second query
            cursor.close()
            cursor = conn.cursor(dictionary=True, buffered=True)

            # Main query - Retrieve user list (remove last_login field)
            query = """SELECT user_id, user_username, user_email, user_status,
                    user_tel, user_avatar, create_at
                    FROM users"""

            params = []

            # Add search condition
            if search_term:
                query += """ WHERE user_id LIKE %s
                         OR user_username LIKE %s
                         OR user_email LIKE %s"""
                search_pattern = f"%{search_term}%"
                params = [search_pattern, search_pattern, search_pattern]

            # Add pagination
            offset = (page - 1) * limit
            query += " ORDER BY user_id LIMIT %s OFFSET %s"
            params.extend([limit, offset])

            logger.debug(f"Executing SQL: {query}, Parameters: {params}")
            cursor.execute(query, params)
            users = cursor.fetchall()
            logger.debug(f"Retrieved {len(users)} users")

            # Calculate total pages
            total_pages = (total + limit - 1) // limit

            return {
                'users': users,
                'pagination': {
                    'current_page': page,
                    'total_pages': total_pages,
                    'total_records': total,
                    'limit': limit
                }
            }
        except Error as e:
            logger.error(f"Failed to retrieve user list: {str(e)}")
            return None
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    @staticmethod
    def get_user_details(user_id):
        """
        Retrieve detailed information about a user

        Args:
            user_id: User ID

        Returns:
            dict: Detailed user information
        """
        # Ensure user_id is of the correct type - attempt to convert to integer, as the database may expect integer IDs
        try:
            numeric_user_id = int(user_id)
        except (ValueError, TypeError):
            # If unable to convert to integer, keep the original value
            numeric_user_id = user_id

        logger.debug(f"Retrieving user details, user_id: {user_id}, processed ID: {numeric_user_id}, type: {type(numeric_user_id)}")

        conn = UserManager.get_connection()
        if not conn:
            logger.error("Database connection failed")
            return None

        cursor = None
        try:
            cursor = conn.cursor(dictionary=True, buffered=True)

            # Retrieve basic user information (remove last_login field)
            query = """SELECT user_id, user_username, user_email, user_tel,
                    user_avatar, user_status, create_at
                    FROM users WHERE user_id = %s"""

            logger.debug(f"Executing SQL: {query}, Parameters: ({numeric_user_id},)")
            cursor.execute(query, (numeric_user_id,))
            user = cursor.fetchone()

            if not user:
                logger.warning(f"User ID not found: {numeric_user_id}")
                return None

            logger.debug(f"User found: {user}")

            # Close the first cursor and create a new one for the second query
            cursor.close()
            cursor = conn.cursor(dictionary=True, buffered=True)

            # Retrieve user's device information
            cursor.execute(
                """SELECT model_id FROM user_model
                WHERE user_id = %s""",
                (numeric_user_id,)
            )
            devices = [row['model_id'] for row in cursor.fetchall()]
            logger.debug(f"Found {len(devices)} devices")

            # Add device information to the user object
            user['devices'] = devices

            return user
        except Error as e:
            logger.error(f"Failed to retrieve user details: {str(e)}")
            return None
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    @staticmethod
    def update_user_status(user_id, status):
        """Update the status of a user (enable/disable)

        Args:
            user_id: User ID
            status: New status ('enable' or 'disable')

        Returns:
            bool: Whether the operation was successful
        """
        # Ensure user_id is a string type
        user_id = str(user_id)
        logger.debug(f"Updating user status, user_id: {user_id}, New status: {status}")

        if status not in ['enable', 'disable']:
            logger.warning(f"Invalid status value: {status}")
            return False

        conn = UserManager.get_connection()
        if not conn:
            logger.error("Database connection failed")
            return False

        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET user_status = %s WHERE user_id = %s",
                (status, user_id)
            )
            conn.commit()

            success = cursor.rowcount > 0
            logger.debug(f"Status update result: {success}, Affected rows: {cursor.rowcount}")
            return success
        except Error as e:
            conn.rollback()
            logger.error(f"Failed to update user status: {str(e)}")
            return False
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    @staticmethod
    def update_user_info(user_id, username=None, email=None, phone=None):
        """Update user information (admin operation)

        Args:
            user_id: User ID
            username: New username (optional)
            email: New email (optional)
            phone: New phone number (optional)

        Returns:
            bool: Whether the operation was successful
        """
        # Ensure user_id is a string type
        user_id = str(user_id)
        logger.debug(f"Updating user information, user_id: {user_id}, username: {username}, email: {email}, phone: {phone}")

        conn = UserManager.get_connection()
        if not conn:
            logger.error("Database connection failed")
            return False, "Unable to connect to the database"

        cursor = None
        try:
            cursor = conn.cursor(buffered=True)

            # First, check if the user exists
            cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
            if not cursor.fetchone():
                logger.warning(f"User ID not found: {user_id}")
                return False, "User does not exist"

            updates = []
            params = []

            # Check if the username is already taken
            if username:
                cursor.close()
                cursor = conn.cursor(buffered=True)
                cursor.execute(
                    "SELECT user_id FROM users WHERE user_username = %s AND user_id != %s",
                    (username, user_id)
                )
                if cursor.fetchone():
                    logger.warning(f"Username already taken: {username}")
                    return False, "Username is already taken"

                updates.append("user_username = %s")
                params.append(username)

            # Check if the email is already in use
            if email:
                cursor.close()
                cursor = conn.cursor(buffered=True)
                cursor.execute(
                    "SELECT user_id FROM users WHERE user_email = %s AND user_id != %s",
                    (email, user_id)
                )
                if cursor.fetchone():
                    logger.warning(f"Email already in use: {email}")
                    return False, "Email is already in use"

                updates.append("user_email = %s")
                params.append(email)

            # Update phone number
            if phone is not None:  # Allow empty string to clear phone number
                updates.append("user_tel = %s")
                params.append(phone)

            if not updates:
                logger.warning("No information provided to update")
                return False, "No information provided to update"

            # Add user ID to the parameters list
            params.append(user_id)

            # Build the update SQL query
            update_query = f"UPDATE users SET {', '.join(updates)} WHERE user_id = %s"
            logger.debug(f"Executing SQL: {update_query}, Parameters: {params}")

            # Execute the update
            cursor.execute(update_query, params)
            conn.commit()

            if cursor.rowcount > 0:
                logger.info(f"User information updated successfully, user_id: {user_id}")
                return True, "User information updated successfully"
            else:
                logger.warning(f"No rows updated, user_id: {user_id}")
                return False, "User not found or information unchanged"

        except Error as e:
            conn.rollback()
            logger.error(f"Failed to update user information: {str(e)}")
            return False, f"Failed to update user information: {str(e)}"
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    @staticmethod
    def get_user_stats():
        """Retrieve user statistics data

        Returns:
            dict: Contains various user statistics
        """
        conn = UserManager.get_connection()
        if not conn:
            logger.error("Database connection failed")
            return None

        cursor = None
        try:
            cursor = conn.cursor(dictionary=True, buffered=True)

            # Get total number of users
            cursor.execute("SELECT COUNT(*) as total FROM users")
            total_users = cursor.fetchone()['total']

            # Close and recreate cursor for next query
            cursor.close()
            cursor = conn.cursor(dictionary=True, buffered=True)

            # Get number of active users
            cursor.execute("SELECT COUNT(*) as active FROM users WHERE user_status = 'enable'")
            active_users = cursor.fetchone()['active']

            # Close and recreate cursor for next query
            cursor.close()
            cursor = conn.cursor(dictionary=True, buffered=True)

            # Get number of inactive users
            cursor.execute("SELECT COUNT(*) as inactive FROM users WHERE user_status = 'disable'")
            inactive_users = cursor.fetchone()['inactive']

            # Close and recreate cursor for next query
            cursor.close()
            cursor = conn.cursor(dictionary=True, buffered=True)

            # Get number of administrators
            cursor.execute("SELECT COUNT(*) as admin_count FROM admin")
            admin_users = cursor.fetchone()['admin_count']

            stats = {
                'total_users': total_users,
                'active_users': active_users,
                'inactive_users': inactive_users,
                'admin_users': admin_users
            }

            logger.debug(f"User statistics: {stats}")
            return stats
        except Error as e:
            logger.error(f"Failed to retrieve user statistics data: {str(e)}")
            return None
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

# Admin routes
@admin_bp.route('/theme_demo')
@admin_required
def theme_demo():
    """Theme demo page"""
    return render_template('theme_demo.html')

@admin_bp.route('/users')
@admin_required
def manage_users():
    """Display the user management page (protected route)"""
    # Directly redirect to the existing management page template
    return redirect(url_for('admin_manage_users'))

# API endpoint - Get all users
@admin_bp.route('/api/users')
@admin_required
def api_get_users():
    """API endpoint to get all users

    Supports pagination and search
    """
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    search = request.args.get('search', None)

    logger.debug(f"Retrieving user list, Page: {page}, Limit: {limit}, Search: {search}")
    result = AdminManager.get_all_users(page, limit, search)
    if not result:
        logger.warning("Failed to retrieve user list")
        return jsonify({'success': False, 'message': 'Failed to retrieve user list'})

    logger.debug(f"Successfully retrieved user list, Total records: {len(result['users'])}")
    return jsonify({'success': True, 'data': result})

# API endpoint - Get user details
@admin_bp.route('/api/users/<user_id>')
@admin_required
def api_get_user(user_id):
    """Get detailed information about a single user"""
    logger.debug(f"Retrieving user details, user_id: {user_id}")
    user = AdminManager.get_user_details(user_id)
    if not user:
        logger.warning(f"User ID not found: {user_id}")
        return jsonify({'success': False, 'message': 'User does not exist'})

    logger.debug(f"Successfully retrieved user details: {user}")
    return jsonify({'success': True, 'data': user})

# API endpoint - Update user information
@admin_bp.route('/api/users/<user_id>/update', methods=['POST'])
@admin_required
def api_update_user_info(user_id):
    """Update user information (admin operation)"""
    logger.debug(f"Updating user information, user_id: {user_id}")
    data = request.json

    if not data:
        logger.warning("Invalid request data")
        return jsonify({'success': False, 'message': 'Invalid request data'})

    logger.debug(f"Request data: {data}")
    username = data.get('username')
    email = data.get('email')
    phone = data.get('phone')

    success, message = AdminManager.update_user_info(
        user_id,
        username=username,
        email=email,
        phone=phone
    )

    if success:
        logger.info(f"User information updated successfully, user_id: {user_id}")
        return jsonify({'success': True, 'message': message})
    else:
        logger.warning(f"Failed to update user information, user_id: {user_id}, Reason: {message}")
        return jsonify({'success': False, 'message': message})

# API endpoint - Enable/Disable user
@admin_bp.route('/api/users/<user_id>/status', methods=['POST'])
@admin_required
def api_update_user_status(user_id):
    """Update user status"""
    logger.debug(f"Updating user status, user_id: {user_id}")
    data = request.json
    if not data:
        logger.warning("Invalid request data")
        return jsonify({'success': False, 'message': 'Invalid request data'})

    status = data.get('status')
    logger.debug(f"New status: {status}")

    if status not in ['enable', 'disable']:
        logger.warning(f"Invalid status value: {status}")
        return jsonify({'success': False, 'message': 'Invalid status value'})

    success = AdminManager.update_user_status(user_id, status)
    if success:
        logger.info(f"User status updated successfully, user_id: {user_id}, New status: {status}")
        return jsonify({'success': True, 'message': f'User status updated to {status}'})
    else:
        logger.warning(f"Failed to update user status, user_id: {user_id}")
        return jsonify({'success': False, 'message': 'Failed to update user status'})

# API endpoint - Get user statistics data
@admin_bp.route('/api/stats/users')
@admin_required
def api_get_user_stats():
    """Retrieve user statistics data"""
    logger.debug("Retrieving user statistics data")
    stats = AdminManager.get_user_stats()
    if stats:
        logger.debug(f"User statistics data: {stats}")
        return jsonify({'success': True, 'data': stats})
    else:
        logger.warning("Failed to retrieve user statistics data")
        return jsonify({'success': False, 'message': 'Failed to retrieve statistics data'})

# API endpoint - Get all devices
@admin_bp.route('/api/devices')
@admin_required
def api_get_devices():
    """API endpoint to get all devices

    Retrieve all devices from udp_device_manager via event system and return to the frontend
    """
    logger.debug(f"Retrieving all device list")

    device_list = []
    try:
        # Get devices via event system to avoid direct import
        udp_devices = get_udp_devices_via_event()
        for device_id, device_info in udp_devices.items():
            # Remove sensitive information
            device_data = {
                'id': device_id,
                'status': device_info.get('status', 'unknown'),
                'ip': device_info.get('ip', 'unknown'),
                'model': device_info.get('model', 'unknown'),
                'online': device_info.get('status') == 'online'
            }
            device_list.append(device_data)
    except Exception as e:
        logger.error(f"Failed to retrieve device list from UDP device manager: {e}")

    logger.debug(f"Found {len(device_list)} devices")
    return jsonify({'success': True, 'data': device_list})

# API endpoint - Get all devices (with full information)
@admin_bp.route('/api/all_devices')
@admin_required
def api_get_all_devices():
    """Get all devices directly from udp_device_manager and device configuration folder

    Specifically designed for the admin interface, returning all devices and their detailed information
    """
    logger.debug(f"Admin requested all device list")

    device_list = []

    # 1. First, retrieve devices from udp_device_manager via event system
    try:
        udp_devices = get_udp_devices_via_event()
        for device_id, device_info in udp_devices.items():
            # Determine device online status
            online = device_info.get('status', 'offline') == 'online'

            # Create a device object with necessary information
            device_data = {
                'id': device_id,
                'status': device_info.get('status', 'unknown'),
                'ip': device_info.get('ip', 'unknown'),
                'model': device_info.get('model', 'unknown'),
                'online': online,
                'authenticated': device_info.get('authenticated', False)
            }
            device_list.append(device_data)
    except Exception as e:
        logger.error(f"Failed to retrieve device list from UDP device manager: {e}")

    # 2. Check device_configs folder, add devices that may not be in devices dictionary
    config_dir = os.path.join(BASE_DIR, 'device_configs')
    if os.path.exists(config_dir) and os.path.isdir(config_dir):
        for folder_name in os.listdir(config_dir):
            folder_path = os.path.join(config_dir, folder_name)
            if os.path.isdir(folder_path):
                # Check if this device is already in the list
                device_exists = any(device['id'] == folder_name for device in device_list)

                if not device_exists:
                    # Attempt to load information from details.json
                    details_path = os.path.join(folder_path, 'details.json')
                    device_info = {}

                    if os.path.exists(details_path):
                        try:
                            with open(details_path, 'r', encoding='utf-8') as f:
                                device_info = json.load(f)
                        except Exception as e:
                            logger.error(f"Failed to read device details file: {str(e)}")

                    # Add device to the list
                    device_data = {
                        'id': folder_name,
                        'status': device_info.get('status', 'offline'),
                        'ip': device_info.get('ip', 'unknown'),
                        'model': device_info.get('model', 'unknown'),
                        'online': False,  # Default offline
                        'authenticated': device_info.get('authenticated', False)
                    }
                    device_list.append(device_data)

    # 3. For each device, find owner information
    for device in device_list:
        device_id = device['id']

        # Query device owner from the database
        owner_id = find_device_owner(device_id)
        device['owner_id'] = owner_id

        # If owner is found, get the owner's username
        if owner_id:
            owner_user = UserManager.get_user_by_id(owner_id)
            if owner_user:
                device['owner_username'] = owner_user.get('username')
                logger.debug(f"Device {device_id} owner is {owner_id} ({owner_user.get('username')})")
            else:
                logger.debug(f"Device {device_id} owner is {owner_id}, but user information not found")
        else:
            logger.debug(f"Device {device_id} has no owner")

            # If owner not found in the database, try to get from device configuration
            try:
                config_path = os.path.join(config_dir, device_id, "new_settings.json")
                if os.path.exists(config_path):
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        system_user_id = config.get('system', {}).get('user_id')
                        if system_user_id:
                            device['owner_id'] = system_user_id
                            logger.debug(f"Found device {device_id} owner from config file: {system_user_id}")

                            # Get the owner's username
                            owner_user = UserManager.get_user_by_id(system_user_id)
                            if owner_user:
                                device['owner_username'] = owner_user.get('username')
            except Exception as e:
                logger.error(f"Failed to read device {device_id} configuration file: {str(e)}")

    logger.debug(f"Returning {len(device_list)} devices to admin")
    return jsonify({'success': True, 'data': device_list})

# API endpoint - Get device details
@admin_bp.route('/api/device_details/<device_id>')
@admin_required
def api_get_device_details(device_id):
    """Get detailed information of a specified device, using load_device_details function in server.py

    Args:
        device_id: Device ID

    Returns:
        JSON: Response containing device detailed information
    """
    logger.debug(f"Retrieving details of device {device_id}")

    try:
        # Get device detailed information using local implementation
        details = load_device_details(device_id)

        # If details are empty, try to get basic information from udp_device_manager via event system
        if not details:
            try:
                udp_devices = get_udp_devices_via_event()
                if device_id in udp_devices:
                    details = udp_devices.get(device_id, {})
            except Exception as e:
                logger.error(f"Failed to retrieve device information from UDP device manager: {e}")

        # Get device configuration information (including user_id)
        config = load_device_config(device_id)

        # If configuration is not empty, merge it into details
        if config:
            # If details are empty, initialize as empty dictionary
            if not details:
                details = {}
            # Add configuration to details
            details['system'] = config.get('system', {})
            logger.debug(f"Loaded configuration information for device {device_id}")
            logger.debug(f"Device {device_id} user_id: {config.get('system', {}).get('user_id')}")

        # If details are still empty, return error
        if not details:
            logger.warning(f"Device {device_id} detailed information not found")
            return jsonify({
                'success': False,
                'message': f'Detailed information for device {device_id} not found'
            })

        # Find device owner
        owner_id = find_device_owner(device_id)

        # Add owner ID to details
        details['owner_id'] = owner_id

        # If owner is found, get the owner's username
        if owner_id:
            owner_user = UserManager.get_user_by_id(owner_id)
            if owner_user:
                details['owner_username'] = owner_user.get('username')
                logger.debug(f"Device {device_id} owner is {owner_id} ({owner_user.get('username')})")
        else:
            # If owner not found in the database, try to get from device configuration
            try:
                config_dir = os.path.join(BASE_DIR, 'device_configs')
                config_path = os.path.join(config_dir, device_id, "new_settings.json")
                if os.path.exists(config_path):
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        system_user_id = config.get('system', {}).get('user_id')
                        if system_user_id:
                            details['owner_id'] = system_user_id
                            logger.debug(f"Found device {device_id} owner from config file: {system_user_id}")

                            # Get the owner's username
                            owner_user = UserManager.get_user_by_id(system_user_id)
                            if owner_user:
                                details['owner_username'] = owner_user.get('username')
            except Exception as e:
                logger.error(f"Failed to read device {device_id} configuration file: {str(e)}")

        logger.debug(f"Device {device_id} details: {details}")

        return jsonify({
            'success': True,
            'details': details
        })

    except Exception as e:
        logger.error(f"Error retrieving device detailed information: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Failed to retrieve device detailed information: {str(e)}'
        })

# API endpoint - Get complete device configuration information
@admin_bp.route('/api/device_full_config/<device_id>')
@admin_required
def api_get_device_full_config(device_id):
    """Get complete device configuration information (from new_settings.json)

    Args:
        device_id: Device ID

    Returns:
        JSON: Device complete configuration information
    """
    logger.info(f"Admin requested complete configuration information for device {device_id}")

    try:
        # Check if device configuration file exists
        config_dir = os.path.join(BASE_DIR, 'device_configs')
        config_path = os.path.join(config_dir, device_id, "new_settings.json")

        if not os.path.exists(config_path):
            logger.warning(f"Configuration file for device {device_id} not found")
            return jsonify({
                'success': False,
                'message': f'Configuration file for device {device_id} not found'
            })

        # Read configuration file
        try:
            logger.info(f"Start reading configuration file for device {device_id}: {config_path}")
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            logger.info(f"Successfully read configuration file for device {device_id}, Size: {len(json.dumps(config))} bytes")

            # Find device owner
            owner_id = config.get('system', {}).get('user_id')
            logger.info(f"Owner ID for device {device_id} from configuration file: {owner_id}")

            if not owner_id:
                # If owner information is not in the configuration file, try to get from the database
                owner_id = find_device_owner(device_id)
                logger.info(f"Owner ID for device {device_id} from database: {owner_id}")

            # If owner is found, get the owner's username
            owner_username = None
            if owner_id:
                owner_user = UserManager.get_user_by_id(owner_id)
                if owner_user:
                    owner_username = owner_user.get('username')
                    logger.info(f"Owner username for device {device_id}: {owner_username}")

            # Add owner information to the configuration
            if owner_id:
                config['owner'] = {
                    'user_id': owner_id,
                    'username': owner_username
                }
                logger.info(f"Owner information added to configuration of device {device_id}")

            logger.info(f"Successfully processed configuration file for device {device_id}")

            return jsonify({
                'success': True,
                'config': config
            })
        except Exception as e:
            error_msg = f"Failed to read configuration file for device {device_id}: {str(e)}"
            logger.error(error_msg)
            logger.exception("Detailed error information:")
            return jsonify({
                'success': False,
                'message': error_msg
            })
    except Exception as e:
        error_msg = f"Failed to retrieve complete configuration information for device {device_id}: {str(e)}"
        logger.error(error_msg)
        logger.exception("Detailed error information:")
        return jsonify({
            'success': False,
            'message': error_msg
        })

# Model management page route
@admin_bp.route('/manage_model')
@admin_required
def manage_model():
    """Display the model management page"""
    logger.info("Accessing model management page")
    return render_template('admin_manage_model.html', admin_username=session.get('admin_username'))

# System log viewing page route
@admin_bp.route('/view_log')
@admin_required
def view_log():
    """System log viewing page

    Display the system log viewing interface, allowing viewing and filtering of device logs
    """
    print("Accessing system log viewing page")
    logger.info("Accessing system log viewing page")
    return render_template('admin_view_log.html', admin_username=session.get('admin_username'))

# API endpoint - Get device log
@admin_bp.route('/get_system_log', methods=['POST'])
def get_system_log():
    """Retrieve device system log content

    Find the corresponding log file based on device ID and return the content
    """
    try:
        data = request.json or {}
        device_id = data.get('device', '')

        if not device_id:
            return jsonify({'success': False, 'message': 'Missing device ID'})

        logger.info(f"Retrieving system log for device {device_id}")

        # Build log file path
        paths = get_device_log_path(device_id)
        log_dir = paths['log_dir']
        log_file = paths['log_file']

        # Check if log directory exists
        if not os.path.exists(log_dir):
            # Attempt to create directory
            try:
                os.makedirs(log_dir)
                logger.info(f"Created device log directory: {log_dir}")
            except Exception as e:
                logger.error(f"Failed to create device log directory: {str(e)}")
                return jsonify({'success': False, 'message': f'Log directory for device {device_id} does not exist and could not be created'})

        # If log file does not exist, return empty log
        if not os.path.exists(log_file):
            logger.warning(f"System log file for device {device_id} does not exist: {log_file}")
            return jsonify({
                'success': True,
                'log_data': [],
                'total_lines': 0,
                'device': device_id,
                'message': f'System log file for device {device_id} does not exist'
            })

        # Read log file content
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            log_lines = f.readlines()

        # Remove trailing newline characters
        log_lines = [line.rstrip() for line in log_lines]

        logger.info(f"Successfully retrieved system log for device {device_id}, Total lines: {len(log_lines)}")

        return jsonify({
            'success': True,
            'log_data': log_lines,
            'total_lines': len(log_lines),
            'device': device_id
        })

    except Exception as e:
        logger.error(f"Error retrieving system log: {str(e)}")
        return jsonify({'success': False, 'message': f'Failed to retrieve system log: {str(e)}'})

# API endpoint - Download complete system log
@admin_bp.route('/download_system_log')
def download_system_log():
    """Provide download of the complete system log file

    Find the corresponding log file based on device ID and provide it for download
    """
    try:
        device_id = request.args.get('device', '')
        if not device_id:
            flash("Missing device ID parameter", "error")
            return redirect(url_for('admin.view_log'))

        logger.info(f"Downloading system log for device {device_id}")

        # Build log file path
        paths = get_device_log_path(device_id)
        log_file = paths['log_file']

        if not os.path.exists(log_file):
            logger.warning(f"System log file for device {device_id} does not exist: {log_file}")
            flash(f"System log file for device {device_id} does not exist", "warning")
            return redirect(url_for('admin.view_log'))

        # Generate timestamp for file name
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        download_name = f"system_log_{device_id}_{timestamp}.log"

        logger.info(f"Providing download of system log file for device {device_id}: {download_name}")

        return send_file(
            log_file,
            as_attachment=True,
            download_name=download_name,
            mimetype='text/plain'
        )

    except Exception as e:
        logger.error(f"Error downloading system log: {str(e)}")
        flash(f"Failed to download system log: {str(e)}", "error")
        return redirect(url_for('admin.view_log'))