from datetime import datetime
from mysql.connector import Error
import mysql.connector

from flask import Blueprint, request, redirect, url_for, flash, render_template, session, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from loguru import logger
import re
import os
import time
import random


# Import the unified OTP manager
from otp_manager import otp_manager, OTPType
from unified_config import get_config, get_device_details

# Global Variables - Remove devices-related global variables, use unified_config
socketio = None

# Blueprint Initialization
# Create blueprint for authentication routes with '/auth' prefix
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# Database Configuration - Get database configuration from unified_config
def get_db_config():
    """Get database configuration from unified_config"""
    return {
        'host': get_config('database.host', 'localhost'),
        'user': get_config('database.user', 'root'),
        'password': get_config('database.password', ''),
        'database': get_config('database.database', 'smart_assistant'),
        'charset': get_config('database.charset', 'utf8mb4'),
        'collation': 'utf8mb4_unicode_ci'
    }

# Keep DB_CONFIG for backward compatibility
DB_CONFIG = get_db_config()

# Module Initialization
def init_database_module(socketio_instance):
    """Initialize database module by setting global variable references

    Args:
        socketio_instance: The SocketIO instance for websocket communication
    """
    global socketio
    socketio = socketio_instance

# User Management Class
class UserManager:
    """Handles all user-related database operations and authentication"""

    @staticmethod
    def generate_next_user_id():
        """Generate the next available user ID in format 'user001', 'user002', etc.

        Returns:
            str: Next available user ID
        """
        conn = UserManager.get_connection()
        if not conn:
            return None

        try:
            cursor = conn.cursor(dictionary=True)
            # Query current maximum user ID
            cursor.execute("SELECT user_id FROM users ORDER BY user_id DESC LIMIT 1")
            result = cursor.fetchone()

            if not result:
                # If no users exist, return first ID
                return "user001"

            last_id = result['user_id']
            # Extract numeric part
            if last_id.startswith('user'):
                num_part = last_id[4:]
                # Ensure it's numeric
                if num_part.isdigit():
                    # Increment number and maintain leading zeros
                    next_num = int(num_part) + 1
                    next_id = f"user{next_num:03d}"
                    return next_id

            # If abnormal situation occurs, use timestamp and random number to generate unique ID
            timestamp = int(time.time())
            random_part = random.randint(1, 999)
            return f"user{random_part:03d}"

        except Error as e:
            print(f"Generate user ID error: {str(e)}")
            # Use backup plan when error occurs
            timestamp = int(time.time()) % 1000
            return f"user{timestamp:03d}"
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    @staticmethod
    def validate_password_strength(password):
        """Validate password strength to ensure it meets security requirements

        Requirements:
        - At least 8 characters in length
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one special character
        - At least one number

        Args:
            password: The password to validate

        Returns:
            tuple: (is_valid, error_messages_list)
        """
        errors = []

        # Check password length
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")

        # Check for at least one uppercase letter
        if not re.search(r'[A-Z]', password):
            errors.append("Password must contain at least one uppercase letter")

        # Check for at least one lowercase letter
        if not re.search(r'[a-z]', password):
            errors.append("Password must contain at least one lowercase letter")

        # Check for at least one number
        if not re.search(r'[0-9]', password):
            errors.append("Password must contain at least one number")

        # Check for at least one special character
        if not re.search(r'[!@#$%^&*()_+\-=\[\]{};:\'",.<>/?\\|]', password):
            errors.append("Password must contain at least one special character")

        return (len(errors) == 0, errors)

    @staticmethod
    def get_connection():
        """Establish connection to the MySQL database

        Returns:
            connection: MySQL connection object or None if connection fails
        """
        try:
            db_config = get_db_config()
            conn = mysql.connector.connect(**db_config)
            print("connect database successfull")
            return conn
        except Error as e:
            print(f"Falied to connect databse: {str(e)}")
            flash(f'Database connection error: {str(e)}', 'error')
            return None

    @staticmethod
    def validate_user_input(username, email, password, confirm_password):
        """Validate user input for registration

        Args:
            username: User's chosen username
            email: User's email address
            password: User's password
            confirm_password: Password confirmation

        Returns:
            list: List of validation error messages (empty if all valid)
        """
        errors = []
        if len(username) < 3:
            errors.append('Username must be at least 3 characters')
        if not re.match(r'^[\w.@+-]+$', username):
            errors.append('Username can only contain letters, numbers and @/./+/-/_')
        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            errors.append('Invalid email format')
        if len(password) < 8:
            errors.append('Password must be at least 8 characters')
        if password != confirm_password:
            errors.append('Passwords do not match')
        return errors

    @staticmethod
    def create_user(username, email, password):
        """Create a new user in the database

        Args:
            username: New user's username
            email: New user's email
            password: New user's password (will be hashed)

        Returns:
            str: User ID of created user, or None if creation failed
        """
        conn = UserManager.get_connection()
        if not conn:
            return None

        try:
            # Generate next available user ID
            user_id = UserManager.generate_next_user_id()
            if not user_id:
                print("Unable to generate user ID")
                return None

            cursor = conn.cursor(dictionary=True)
            hashed_pw = generate_password_hash(password)
            cursor.execute(
                """INSERT INTO users
                (user_id, user_username, user_email, user_password, create_at, user_status)
                VALUES (%s, %s, %s, %s, %s, %s)""",
                (user_id, username, email, hashed_pw, datetime.now(), "enable")
            )
            conn.commit()
            return user_id
        except Error as e:
            conn.rollback()
            flash(f'Registration error: {str(e)}', 'error')
            return None
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    @staticmethod
    def authenticate_user(email, password):
        """Authenticate a user with email and password

        Args:
            email: User's email address
            password: User's password

        Returns:
            dict: User data if authentication successful, None otherwise
        """
        conn = UserManager.get_connection()
        if not conn:
            return None

        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """SELECT user_id, user_username, user_password, user_email, user_status
                FROM users WHERE user_email = %s""",
                (email,)
            )
            user = cursor.fetchone()

            if user and check_password_hash(user['user_password'], password):
                # Check if user account is enabled
                if user.get('user_status') != 'enable':
                    print(f"User login attempt denied: account status is {user.get('user_status')}")
                    return None
                return user
            return None
        except Error as e:
            print(f"Authentication failed: {str(e)}")
            return None
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    @staticmethod
    def verify_user(email, password):
        """Verify user credentials using email

        Args:
            email: User's email
            password: User's password

        Returns:
            bool: True if credentials are valid, False otherwise
        """
        user = UserManager.authenticate_user(email, password)
        return user is not None

    @staticmethod
    def get_user(username):
        """Get user information by username (replacement for user_db.get_user)

        Args:
            username: Username to lookup

        Returns:
            dict: User information including associated devices
        """
        conn = UserManager.get_connection()
        if not conn:
            return None

        cursor = None
        try:
            cursor = conn.cursor(dictionary=True, buffered=True)
            # Get user basic information
            cursor.execute(
                """SELECT user_id, user_username, user_email
                FROM users WHERE user_username = %s""",
                (username,)
            )
            user = cursor.fetchone()

            if not user:
                return None

            # Close the first cursor and create a new one for the second query
            cursor.close()
            cursor = conn.cursor(dictionary=True, buffered=True)

            # Get user's associated devices from user_model table
            cursor.execute(
                """SELECT model_id FROM user_model
                WHERE user_id = %s""",
                (user['user_id'],)
            )
            devices = [row['model_id'] for row in cursor.fetchall()]

            # Build complete user info
            user_info = {
                'username': user['user_username'],
                'email': user.get('user_email', ''),
                'devices': devices
            }

            return user_info
        except Error as e:
            print(f"Get user info error: {str(e)}")
            return None
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    @staticmethod
    def get_user_by_id(user_id):
        """Get user information by user ID

        Args:
            user_id: The user ID to lookup

        Returns:
            dict: User data if found, None otherwise
        """
        conn = UserManager.get_connection()
        if not conn:
            return None

        cursor = None
        try:
            cursor = conn.cursor(dictionary=True, buffered=True)
            cursor.execute(
                """SELECT user_id, user_username, user_email
                FROM users WHERE user_id = %s""",
                (user_id,)
            )
            user = cursor.fetchone()

            if not user:
                print(f"User ID not found: {user_id}")
                return None

            # Close the first cursor and create a new one for the second query
            cursor.close()
            cursor = conn.cursor(dictionary=True, buffered=True)

            # Get user's associated devices from user_model table
            cursor.execute(
                """SELECT model_id FROM user_model
                WHERE user_id = %s""",
                (user_id,)
            )
            devices = [row['model_id'] for row in cursor.fetchall()]

            # Build complete user info
            user_info = {
                'username': user['user_username'],
                'email': user.get('user_email', ''),
                'devices': devices,
                'user_id': user['user_id']
            }

            return user_info
        except Error as e:
            print(f"Get user error: {str(e)}")
            flash(f'Database error: {str(e)}', 'error')
            return None
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    @staticmethod
    def add_user(username, password, email=''):
        """Add a new user (replacement for user_db.add_user)

        Args:
            username: New user's username
            password: New user's password
            email: New user's email (optional)

        Returns:
            tuple: (success_bool, message_string, user_id)
        """
        conn = UserManager.get_connection()
        if not conn:
            return False, "Unable to connect to database", None

        try:
            # Check if user already exists
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """SELECT user_id FROM users WHERE user_username = %s""",
                (username,)
            )
            if cursor.fetchone():
                return False, "Username already exists", None

            # Generate next available user ID
            user_id = UserManager.generate_next_user_id()
            if not user_id:
                return False, "Unable to generate user ID", None

            # Create new user
            hashed_pw = generate_password_hash(password)
            cursor.execute(
                """INSERT INTO users
                (user_id, user_username, user_email, user_password, create_at)
                VALUES (%s, %s, %s, %s, %s)""",
                (user_id, username, email, hashed_pw, datetime.now())
            )
            conn.commit()
            return True, "User created successfully", user_id
        except Error as e:
            conn.rollback()
            print(f"Add user error: {str(e)}")
            return False, f"Failed to add user: {str(e)}", None
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    @staticmethod
    def check_device_access(username_or_id, device_id):
        """Check if user has permission to access a device (replacement for user_db.check_device_access)

        Args:
            username_or_id: Username or user_id to check
            device_id: Device ID to check access for

        Returns:
            bool: True if user has access to the device, False otherwise
        """
        conn = UserManager.get_connection()
        if not conn:
            print("Unable to connect to database, failed to check device access permissions")
            return False

        try:
            cursor = conn.cursor(dictionary=True)

            # Determine if input is username or user ID
            if isinstance(username_or_id, str) and username_or_id.startswith('user'):
                # Handle as user ID
                cursor.execute(
                    """SELECT id FROM user_model
                    WHERE user_id = %s AND model_id = %s""",
                    (username_or_id, device_id)
                )
            else:
                # Handle as username
                cursor.execute(
                    """SELECT um.id FROM user_model um
                    JOIN users u ON um.user_id = u.user_id
                    WHERE u.user_username = %s AND um.model_id = %s""",
                    (username_or_id, device_id)
                )

            result = cursor.fetchone()
            print(f"Check user {username_or_id} access to device {device_id}: {'Has access' if result else 'No access'}")
            return result is not None
        except Error as e:
            print(f"Error checking device access: {str(e)}")
            return False
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    @staticmethod
    def get_statistics():
        """Get homepage statistics

        Returns:
            dict: Contains user count, activated device count and other statistics
        """
        conn = UserManager.get_connection()
        if not conn:
            print("Unable to connect to database, failed to get statistics")
            return None

        cursor = None
        try:
            cursor = conn.cursor(dictionary=True, buffered=True)

            # Get total user count
            cursor.execute("SELECT COUNT(*) as total FROM users")
            total_users = cursor.fetchone()['total']

            # Close the first cursor and create a new one for the second query
            cursor.close()
            cursor = conn.cursor(dictionary=True, buffered=True)

            # Get activated Yumi count (record count in user_model table)
            cursor.execute("SELECT COUNT(*) as total FROM user_model")
            activated_yumis = cursor.fetchone()['total']

            return {
                'active_users': total_users,
                'activated_yumis': activated_yumis,
                'response_time': 5  # Fixed response time
            }
        except Error as e:
            print(f"Get statistics error: {str(e)}")
            return None
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    @staticmethod
    def update_user_profile(user_id, username=None, email=None, password=None, phone=None, avatar_path=None):
        """Update user profile information

        Args:
            user_id: ID of user to update
            username: New username (optional)
            email: New email (optional)
            password: New password (optional)
            phone: New phone number (optional)
            avatar_path: Path to uploaded avatar image (optional)

        Returns:
            bool: True if update successful, False otherwise
        """
        conn = UserManager.get_connection()
        if not conn:
            print("connect database failed")
            return False

        try:
            cursor = conn.cursor()
            updates = []
            params = []

            # Prepare updates for each field if provided
            if password:
                hashed_pw = generate_password_hash(password)
                updates.append("user_password = %s")
                params.append(hashed_pw)

            if username:
                updates.append("user_username = %s")
                params.append(username)

            if email:
                updates.append("user_email = %s")
                params.append(email)

            if phone is not None:  # Allow empty string to clear phone number
                updates.append("user_tel = %s")
                params.append(phone)

            if avatar_path is not None:
                updates.append("user_avatar = %s")
                params.append(avatar_path)

            if not updates:
                print("not giver update data")
                return False

            params.append(user_id)
            update_query = f"UPDATE users SET {', '.join(updates)} WHERE user_id = %s"

            print(f"Executing SQL: {update_query}")  # Debug
            print(f"Parameters: {params}")  # Debug

            cursor.execute(update_query, params)
            conn.commit()

            print(f"Affected rows: {cursor.rowcount}")  # Debug
            if cursor.rowcount == 0:
                print("No rows updated")  # Debug
                return False

            print("Update successful")  # Debug
            return True
        except Error as e:
            conn.rollback()
            print(f"Update error: {str(e)}")  # Debug
            flash(f'Update error: {str(e)}', 'error')
            return False
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

# Authentication Decorators
def login_required(f):
    """Decorator to protect routes that require login

    Redirects to login page if user is not authenticated
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login_page'))
        return f(*args, **kwargs)
    return decorated_function

# Authentication Routes
@auth_bp.route('/login', methods=['GET', 'POST'])
def login_page():
    """Handle user login

    On GET: Display login form
    On POST: Process login form submission and authenticate user with email
    For regular users: Authenticate using user_email and password from users table
    For admin users: Authenticate using admin_username and password from admin table
    """
    next_page = request.args.get('next', url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        # First try to authenticate as a regular user
        user = UserManager.authenticate_user(email, password)
        if user:
            # Store user_id in session (now in string format, like 'user001')
            session['user_id'] = user['user_id']
            session['role'] = 'user'

            # Update user_id configuration to connected clients
            user_info = UserManager.get_user(user['user_username'])
            if user_info and 'devices' in user_info:
                for device_id in user_info['devices']:
                    # Use unified config manager to get device details
                    device_details = get_device_details(device_id)
                    if device_details and device_details.get('sid'):
                        # Update device configuration
                        update_data = {'user_id': user['user_username']}
                        socketio.emit('update_config', update_data, to=device_details['sid'])
                        logger.info(f"Updated user ID to {user['user_username']} for device {device_id}")

            # Login success, return login page with success status and redirect URL
            return render_template('login.html', next=next_page, login_success=True, redirect_url=next_page)
        else:
            # If not authenticated as user, try to authenticate as admin
            conn = UserManager.get_connection()
            if conn:
                try:
                    cursor = conn.cursor(dictionary=True)
                    cursor.execute(
                        """SELECT * FROM admin
                        WHERE admin_username = %s AND admin_password = %s""",
                        (email, password)
                    )
                    admin_user = cursor.fetchone()
                    if admin_user:
                        # Store admin info in session
                        session['admin_id'] = admin_user.get('admin_id', admin_user.get('id'))
                        session['admin_username'] = admin_user['admin_username']
                        session['role'] = 'admin'

                        logger.info(f"Admin user logged in: {admin_user['admin_username']}")

                        # Redirect to admin page
                        admin_redirect = url_for('admin_main_page')
                        return render_template('login.html', next=next_page, login_success=True, redirect_url=admin_redirect)
                except Exception as e:
                    logger.error(f"Error checking admin status: {str(e)}")
                finally:
                    if conn and conn.is_connected():
                        cursor.close()
                        conn.close()

            # If we reach here, neither user nor admin authentication succeeded
            return render_template('login.html', next=next_page, login_error=True)

    return render_template('login.html', next=next_page)

# OTP functions are now handled by the unified OTP manager

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Handle user registration

    On GET: Display registration form
    On POST: Process registration form and initiate OTP verification
    """
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()  # Changed from confirm-password to confirm_password

        errors = UserManager.validate_user_input(username, email, password, confirm_password)
        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('register.html')

        # Check if the data exists to prevent duplicated entries
        conn = UserManager.get_connection()
        if conn:
            try:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    "SELECT user_id FROM users WHERE user_username = %s OR user_email = %s",
                    (username, email)
                )
                if cursor.fetchone():
                    flash('Username or email already exists', 'error')
                    return render_template('register.html')
            finally:
                if conn and conn.is_connected():
                    cursor.close()
                    conn.close()

        # Store registration info in session for after verification
        session['pending_username'] = username
        session['pending_email'] = email
        session['pending_password'] = password

        # Generate and send OTP using the unified OTP manager
        success, error_msg = otp_manager.generate_and_send_otp(email, OTPType.REGISTRATION)

        if success:
            flash('Verification code has been sent to your email', 'success')
            return redirect(url_for('auth.verify_otp'))
        else:
            flash(f'Failed to send verification code: {error_msg}', 'error')
            return render_template('register.html')

    return render_template('register.html')

@auth_bp.route('/verify_otp', methods=['GET', 'POST'])
def verify_otp():
    """Handle OTP verification during registration process

    On GET: Display OTP verification form
    On POST: Validate OTP and complete registration if valid
    """
    if request.method == 'POST':
        # Get submitted OTP (merged 6 digits)
        input_otp = request.form.get('otp')
        email = session.get('pending_email')
        username = session.get('pending_username')
        password = session.get('pending_password')

        # Check if this is an AJAX request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        # Check if session data exists
        if not email:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Session expired, please register again'}), 400
            else:
                flash('Session expired, please register again', 'error')
                return redirect(url_for('auth.register'))

        # Verify OTP using the unified OTP manager
        success, error_msg = otp_manager.verify_otp(email, input_otp, OTPType.REGISTRATION)

        if success:
            if email and username and password:
                # Register user
                user_id = UserManager.create_user(username, email, password)
                if user_id:
                    # Clear temporary data from session
                    session.pop('pending_email', None)
                    session.pop('pending_username', None)
                    session.pop('pending_password', None)

                    # Store user ID in session
                    session['user_id'] = user_id

                    if is_ajax:
                        return jsonify({'success': True, 'message': 'Verification successful', 'redirect': url_for('auth.success', email=email, user_id=user_id)})
                    else:
                        return render_template('success.html', email=email, user_id=user_id)
                else:
                    if is_ajax:
                        return jsonify({'success': False, 'message': 'Failed to create user, please try again'}), 500
                    else:
                        flash('Failed to create user, please try again', 'error')
                        return redirect(url_for('auth.register'))
            else:
                if is_ajax:
                    return jsonify({'success': False, 'message': 'Registration information incomplete, please register again'}), 400
                else:
                    flash('Registration information incomplete, please register again', 'error')
                    return redirect(url_for('auth.register'))
        else:
            if is_ajax:
                return jsonify({'success': False, 'message': error_msg or 'Verification code is incorrect, please try again'}), 400
            else:
                flash(error_msg or 'Verification code is incorrect, please try again', 'error')
                return render_template('verify_otp.html')

    # Ensure there's a pending email to verify, otherwise redirect to registration
    if 'pending_email' not in session:
        flash('Please fill in registration information first', 'warning')
        return redirect(url_for('auth.register'))

    return render_template('verify_otp.html')

@auth_bp.route('/resend_otp', methods=['POST'])
def resend_otp():
    """Handle OTP resend requests

    Resend OTP to user's email with rate limiting
    """
    email = session.get('pending_email')
    if not email:
        return jsonify({'success': False, 'message': 'No email pending verification'}), 400

    # Generate and send new OTP using the unified OTP manager
    success, error_msg = otp_manager.generate_and_send_otp(email, OTPType.REGISTRATION)

    if success:
        logger.info(f"Successfully resent OTP to {email}")
        return jsonify({'success': True, 'message': 'Verification code has been resent to your email'})
    else:
        logger.error(f"Failed to send OTP to {email}: {error_msg}")
        return jsonify({'success': False, 'message': error_msg or 'Failed to send verification code, please try again later'}), 500

@auth_bp.route('/request_otp', methods=['GET', 'POST'])
def request_otp():
    """Handle OTP request (for password reset or verification)

    On GET: Display email input form
    On POST: Send OTP to provided email if it exists
    """
    if request.method == 'POST':
        email = request.form.get('email')

        if not email or not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            flash('Please enter a valid email address', 'error')
            return redirect(url_for('auth.request_otp'))

        # Check if email exists
        conn = UserManager.get_connection()
        if conn:
            try:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT user_id FROM users WHERE user_email = %s", (email,))
                user = cursor.fetchone()

                if not user:
                    flash('This email is not registered', 'error')
                    return redirect(url_for('auth.register'))
            finally:
                if conn and conn.is_connected():
                    cursor.close()
                    conn.close()

        # Generate and send OTP using the unified OTP manager
        session['pending_email'] = email
        success, error_msg = otp_manager.generate_and_send_otp(email, OTPType.REGISTRATION)

        if success:
            flash('Verification code has been sent to your email', 'success')
            return redirect(url_for('auth.verify_otp'))
        else:
            flash(f'Failed to send verification code: {error_msg}', 'error')

    return render_template('request_otp.html')

@auth_bp.route('/success')
def success():
    """Display success page after successful registration"""
    email = request.args.get('email')
    user_id = request.args.get('user_id')
    return render_template('success.html', email=email, user_id=user_id)

@auth_bp.route('/logout')
def logout():
    """Handle user logout

    Clear session and redirect to login page
    """
    session.pop('user_id', None)
    return redirect(url_for('auth.login_page'))

@auth_bp.route('/user_main')
@login_required
def user_main_page():
    """Display user main page (protected route)"""
    return render_template('user_main_page.html')

@auth_bp.route('/discovery_model')
@login_required
def discovery_model():
    """Display device discovery model page (protected route)"""
    return render_template('discovery_model.html')

@auth_bp.route('/user_profile', methods=['GET', 'POST'])
@login_required
def user_profile():
    """Handle user profile viewing and editing

    On GET: Display user profile
    On POST: Process profile updates
    """
    if 'user_id' not in session:
        return redirect(url_for('auth.login_page'))

    user_id = session['user_id']

    # Get user data including phone number and avatar
    conn = UserManager.get_connection()
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """SELECT user_id, user_username, user_email, user_tel, user_avatar
                FROM users WHERE user_id = %s""",
                (user_id,)
            )
            user = cursor.fetchone()
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
    else:
        flash('Unable to connect to database', 'error')
        return redirect(url_for('index'))

    if not user:
        flash('User not found', 'error')
        return redirect(url_for('auth.login_page'))

    if request.method == 'POST':
        print("Received POST request")  # Debug
        print(f"Form data: {request.form}")  # Debug

        username = request.form.get('username', '').strip()
        # Email is no longer editable - remove email processing
        phone = request.form.get('phone', '').strip()
        current_password = request.form.get('current_password', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        # Validate Malaysian phone number format if provided
        if phone:
            import re
            # Remove any spaces or dashes
            phone_clean = re.sub(r'[\s-]', '', phone)
            # Check Malaysian phone number format: 011xxxxxxxx (11 digits) or 01xxxxxxxx (10 digits)
            if not re.match(r'^(011\d{8}|01[0-9]\d{7})$', phone_clean):
                flash('Invalid phone number format. Please use Malaysian format: 011xxxxxxxx (11 digits) or 01xxxxxxxx (10 digits)', 'error')
                return redirect(url_for('auth.user_profile'))
            phone = phone_clean  # Use cleaned phone number

        # Handle avatar upload
        avatar_path = None
        if 'avatar' in request.files and request.files['avatar'].filename:
            avatar_file = request.files['avatar']

            # Validate file type
            allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
            if '.' in avatar_file.filename and avatar_file.filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                # Access the static folder that Flask knows about
                # Get the directory where this script is located (yumi-server directory)
                current_dir = os.path.dirname(os.path.abspath(__file__))
                static_folder = os.path.join(current_dir, 'static')

                # Create directory if it doesn't exist
                avatar_dir = os.path.join(static_folder, 'avatars', str(user_id))
                os.makedirs(avatar_dir, exist_ok=True)

                # Generate unique filename
                filename = f"{int(time.time())}_{avatar_file.filename}"
                file_path = os.path.join(avatar_dir, filename)

                # Save the file
                avatar_file.save(file_path)

                # Set avatar path using the new avatar route for better reliability
                avatar_path = f"/avatar/{user_id}/{filename}"
                print(f"Saved avatar to: {file_path}, URL path: {avatar_path}")
            else:
                flash('Invalid file type. Please upload a valid image file.', 'error')

        # Handle password change
        password_updated = False
        redirect_to_security = False
        if new_password:
            redirect_to_security = True  # If password fields are filled, redirect to security section
            if not current_password:
                flash('Current password is required to change password', 'error')
                return redirect(url_for('auth.user_profile') + '?section=security')

            if new_password != confirm_password:
                flash('New passwords do not match', 'error')
                return redirect(url_for('auth.user_profile') + '?section=security')

            # Validate password strength
            is_valid, errors = UserManager.validate_password_strength(new_password)
            if not is_valid:
                flash('Password does not meet security requirements: ' + ', '.join(errors), 'error')
                return redirect(url_for('auth.user_profile') + '?section=security')

            # Verify current password
            auth_user = UserManager.authenticate_user(user['user_email'], current_password)
            if not auth_user:
                flash('Current password is incorrect', 'error')
                return redirect(url_for('auth.user_profile') + '?section=security')

            # Update password
            if UserManager.update_user_profile(user_id, password=new_password):
                password_updated = True
            else:
                flash('Failed to update password', 'error')
                return redirect(url_for('auth.user_profile') + '?section=security')

        # Update profile information
        update_data = {}
        if username and username != user['user_username']:
            update_data['username'] = username
        # Email is no longer editable - remove email update logic
        if phone != user.get('user_tel', ''):
            update_data['phone'] = phone
        if avatar_path:
            update_data['avatar_path'] = avatar_path

        if update_data:
            print(f"Updating user profile: {update_data}")  # Debug
            if UserManager.update_user_profile(
                user_id,
                username=update_data.get('username'),
                email=None,  # Email is no longer editable
                phone=update_data.get('phone'),
                avatar_path=update_data.get('avatar_path')
            ):
                if 'username' in update_data:
                    session['username'] = update_data['username']
                flash('Profile updated successfully!', 'success')
            else:
                flash('Failed to update profile', 'error')

        if password_updated:
            flash('Password updated successfully!', 'success')

        if not update_data and not password_updated:
            flash('No changes were made to your profile', 'info')

        # Redirect to appropriate section
        if redirect_to_security:
            return redirect(url_for('auth.user_profile') + '?section=security')
        else:
            return redirect(url_for('auth.user_profile'))

    return render_template('user_profile.html', user=user)



@auth_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    """Handle forgot password requests

    On GET: Display forgot password form
    On POST: Send OTP to email for password reset verification
    """
    if request.method == 'POST':
        email = request.form.get('email')

        if not email or not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            return render_template('forgot_password.html', error='Please enter a valid email address')

        # Check if email exists in database
        conn = UserManager.get_connection()
        if not conn:
            return render_template('forgot_password.html', error='System error, please try again later')

        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT user_id FROM users WHERE user_email = %s", (email,))
            user = cursor.fetchone()

            if not user:
                return render_template('forgot_password.html', error='This email is not registered')

            # Store user ID for later password reset
            session['reset_user_id'] = user['user_id']
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

        # Generate and send OTP using the unified OTP manager
        success, error_msg = otp_manager.generate_and_send_otp(email, OTPType.PASSWORD_RESET)

        if success:
            # Store email in session for verification page
            session['reset_email'] = email
            return redirect(url_for('auth.verify_reset_otp'))
        else:
            return render_template('forgot_password.html', error=f'Failed to send verification code: {error_msg}')

    return render_template('forgot_password.html')

@auth_bp.route('/verify_reset_otp', methods=['GET', 'POST'])
def verify_reset_otp():
    """Handle OTP verification for password reset

    On GET: Display OTP verification form
    On POST: Verify OTP and redirect to password reset page if valid
    """
    email = session.get('reset_email')
    if not email:
        flash('Please submit your email address first', 'error')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        input_otp = request.form.get('otp')

        # Check if this is an AJAX request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        # Verify OTP using the unified OTP manager
        success, error_msg = otp_manager.verify_otp(email, input_otp, OTPType.PASSWORD_RESET)

        if success:
            # Mark OTP as verified
            session['otp_verified'] = True
            if is_ajax:
                return jsonify({'success': True, 'message': 'Verification successful'}), 200
            else:
                return redirect(url_for('auth.reset_password'))
        else:
            if is_ajax:
                return jsonify({'success': False, 'message': error_msg or 'Verification code is incorrect, please try again'}), 400
            else:
                flash(error_msg or 'Verification code is incorrect, please try again', 'error')

    return render_template('verify_reset_otp.html', email=email)

@auth_bp.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    """Handle password reset after OTP verification

    On GET: Display password reset form
    On POST: Process password reset
    """
    # Check if user has verified OTP
    if not session.get('otp_verified'):
        flash('Please verify your email first', 'error')
        return redirect(url_for('auth.forgot_password'))

    # Get user_id from session
    user_id = session.get('reset_user_id')
    if not user_id:
        flash('Password reset session expired', 'error')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        # Validate password
        if not password or len(password) < 8:
            flash('Password must be at least 8 characters long', 'error')
            return render_template('reset_password.html')

        if password != confirm_password:
            flash('The two passwords entered do not match', 'error')
            return render_template('reset_password.html')

        # Validate password strength
        is_valid, errors = UserManager.validate_password_strength(password)
        if not is_valid:
            for error in errors:
                flash(error, 'error')
            return render_template('reset_password.html')

        # Update password
        if UserManager.update_user_profile(user_id, password=password):
            # Clear session data
            session.pop('otp_verified', None)
            session.pop('reset_user_id', None)
            session.pop('reset_email', None)

            flash('Password has been successfully reset, please login with your new password', 'success')
            return redirect(url_for('auth.login_page'))
        else:
            flash('Password reset failed, please try again', 'error')

    return render_template('reset_password.html')

@auth_bp.route('/resend_reset_otp', methods=['POST'])
def resend_reset_otp():
    """Handle OTP resend requests for password reset

    Resend OTP to user's email with rate limiting
    """
    email = session.get('reset_email')
    if not email:
        return jsonify({'success': False, 'message': 'No email pending verification'}), 400

    # Generate and send new OTP using the unified OTP manager
    success, error_msg = otp_manager.generate_and_send_otp(email, OTPType.PASSWORD_RESET)

    if success:
        logger.info(f"Successfully resent password reset OTP to {email}")
        return jsonify({'success': True, 'message': 'Verification code has been resent to your email'})
    else:
        logger.error(f"Failed to send password reset OTP to {email}: {error_msg}")
        return jsonify({'success': False, 'message': error_msg or 'Failed to send verification code, please try again later'}), 500