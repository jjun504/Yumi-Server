"""
Unified OTP Management System
Handles all OTP-related issues, including:
1. Unified OTP generation and verification
2. Secure OTP storage (hashing)
3. Rate limiting
4. Automatic cleanup of expired OTPs
5. Audit logging
6. Thread safety
7. Email sending retry mechanism
"""

import hashlib
import threading
import time
import random
import string
import os
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass
from enum import Enum
import resend
from loguru import logger
import json
from datetime import datetime


class OTPType(Enum):
    """OTP Type Enumeration"""
    REGISTRATION = "registration"
    PASSWORD_RESET = "password_reset"
    LOGIN_VERIFICATION = "login_verification"


@dataclass
class OTPRecord:
    """OTP Record Data Class"""
    otp_hash: str
    timestamp: float
    attempts: int
    otp_type: OTPType
    email: str
    max_attempts: int = 3


class RateLimiter:
    """
    Rate Limiter
    """
    
    def __init__(self, max_attempts: int = 5, window_seconds: int = 3600):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.attempts: Dict[str, List[float]] = {}
        self.lock = threading.Lock()
    
    def is_allowed(self, identifier: str) -> Tuple[bool, Optional[str]]:
        """
        Check if operation is allowed
        """
        with self.lock:
            current_time = time.time()
            if identifier not in self.attempts:
                self.attempts[identifier] = []
            
            # Clean up expired attempt records
            self.attempts[identifier] = [
                attempt_time for attempt_time in self.attempts[identifier]
                if current_time - attempt_time < self.window_seconds
            ]
            
            # Check if limit exceeded
            if len(self.attempts[identifier]) >= self.max_attempts:
                remaining_time = int(self.window_seconds - (current_time - self.attempts[identifier][0]))
                return False, f"Too many attempts. Please try again in {remaining_time} seconds"
            
            # Record new attempt
            self.attempts[identifier].append(current_time)
            return True, None
    
    def reset(self, identifier: str):
        """
        Reset rate limit for a specific identifier
        """
        with self.lock:
            self.attempts.pop(identifier, None)


class EmailService:
    """
    Email Sending Service
    """
    
    def __init__(self):
        # Import unified_config here to avoid circular imports
        try:
            from unified_config import get_config
            self.api_key = get_config('email.resend_api_key', '')
            self.from_email = get_config("email.email_from", "Yumi Smart Assistant <noreply@resend.dev>")
        except ImportError:
            # Fallback to environment variables if unified_config is not available
            self.api_key = os.getenv('RESEND_API_KEY', '')
            self.from_email = os.getenv("EMAIL_FROM", "Yumi Smart Assistant <noreply@resend.dev>")

        self.max_retries = 3
        self.retry_delay = 1  # 秒

        if not self.api_key or self.api_key == 'YOUR_RESEND_API_KEY':
            logger.warning("RESEND_API_KEY not configured properly - email sending will be disabled")
            self.api_key = None
        else:
            resend.api_key = self.api_key
    
    def send_otp_email(self, to_email: str, otp_code: str, otp_type: OTPType) -> Tuple[bool, Optional[str]]:
        """
        Send OTP email with retry mechanism"""

        # Check if API key is configured
        if not self.api_key:
            logger.warning(f"Email sending disabled - API key not configured. OTP for {to_email}: {otp_code}")
            return False, "Email service not configured"

        # Select email template based on OTP type
        if otp_type == OTPType.REGISTRATION:
            subject = "Your Account Verification Code"
            title = "Account Verification"
            description = "Please use the following verification code to complete your account registration:"
        elif otp_type == OTPType.PASSWORD_RESET:
            subject = "Password Reset Verification Code"
            title = "Password Reset"
            description = "Please use the following verification code to reset your password:"
        else:
            subject = "Your Verification Code"
            title = "Verification Required"
            description = "Please use the following verification code to complete your verification:"
        
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px; background-color: #fafafa;">
            <div style="text-align: center; margin-bottom: 30px;">
                <h1 style="color: #333; margin: 0; font-size: 28px;">Yumi Smart Assistant</h1>
                <div style="width: 50px; height: 3px; background: linear-gradient(90deg, #4CAF50, #2196F3); margin: 10px auto;"></div>
            </div>
            
            <div style="background-color: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <h2 style="color: #333; margin-top: 0; font-size: 24px;">{title}</h2>
                <p style="color: #666; font-size: 16px; line-height: 1.5;">{description}</p>
                
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; text-align: center; border-radius: 8px; margin: 25px 0;">
                    <div style="color: white; font-size: 32px; font-weight: bold; letter-spacing: 8px; font-family: 'Courier New', monospace;">
                        {otp_code}
                    </div>
                </div>
                
                <div style="background-color: #fff3cd; border: 1px solid #ffeaa7; border-radius: 6px; padding: 15px; margin: 20px 0;">
                    <p style="margin: 0; color: #856404; font-size: 14px;">
                        <strong>⚠️ Important:</strong> This verification code will expire in <strong>5 minutes</strong>.
                    </p>
                </div>
                
                <p style="color: #666; font-size: 14px; margin-bottom: 0;">
                    If you did not request this verification code, please ignore this email and ensure your account is secure.
                </p>
            </div>
            
            <div style="text-align: center; margin-top: 20px; color: #999; font-size: 12px;">
                <p>This is an automated message from Yumi Smart Assistant. Please do not reply to this email.</p>
            </div>
        </div>
        """
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Attempting to send OTP email to {to_email} (attempt {attempt + 1}/{self.max_retries})")
                
                response = resend.Emails.send({
                    "from": self.from_email,
                    "to": to_email,
                    "subject": subject,
                    "html": html_content
                })
                
                if response and "id" in response:
                    logger.info(f"Successfully sent OTP email to {to_email}, message ID: {response['id']}")
                    return True, None
                else:
                    logger.warning(f"Unexpected response from Resend API: {response}")
                    
            except Exception as e:
                logger.error(f"Failed to send email (attempt {attempt + 1}): {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))  # Incremental delay
        
        return False, "Failed to send email after multiple attempts"


class OTPManager:
    """
    Unified OTP Manager
    """
    
    def __init__(self, length: int = 6, expire_seconds: int = 300):
        """
        Initialize OTP Manager
        """
        self.length = length
        self.expire_seconds = expire_seconds
        self.otp_storage: Dict[str, OTPRecord] = {}
        self.lock = threading.Lock()
        self.rate_limiter = RateLimiter(max_attempts=5, window_seconds=3600)
        self.email_service = EmailService()
        
        # Start cleanup thread
        self.cleanup_thread = threading.Thread(target=self._cleanup_worker, daemon=True)
        self.cleanup_thread.start()
        
        logger.info("OTP Manager initialized successfully")
    
    def _generate_otp(self) -> str:
        """
        Generate OTP
        """
        return ''.join(random.choices(string.digits, k=self.length))
    
    def _hash_otp(self, otp: str) -> str:
        """
        Hash OTP
        """
        return hashlib.sha256(otp.encode()).hexdigest()
    
    def _get_storage_key(self, email: str, otp_type: OTPType) -> str:
        """
        Generate storage key
        """
        return f"{email}:{otp_type.value}"
    
    def _cleanup_worker(self):
        """
        Background thread for cleaning up expired OTPs
        """
        while True:
            try:
                time.sleep(60)  # Clean up every minute
                self.cleanup_expired()
            except Exception as e:
                logger.error(f"Error in cleanup worker: {e}")
    
    def cleanup_expired(self) -> int:
        """
        Clean up expired OTPs
        """
        with self.lock:
            current_time = time.time()
            expired_keys = [
                key for key, record in self.otp_storage.items()
                if current_time - record.timestamp > self.expire_seconds
            ]
            
            for key in expired_keys:
                del self.otp_storage[key]
                logger.debug(f"Cleaned up expired OTP for key: {key}")
            
            if expired_keys:
                logger.info(f"Cleaned up {len(expired_keys)} expired OTP records")
            
            return len(expired_keys)
    
    def generate_and_send_otp(self, email: str, otp_type: OTPType) -> Tuple[bool, Optional[str]]:
        """
        Generate and send OTP
        """
        
        # Check rate limit
        allowed, error_msg = self.rate_limiter.is_allowed(email)
        if not allowed:
            logger.warning(f"Rate limit exceeded for email: {email}")
            return False, error_msg
        
        # Generate OTP
        otp = self._generate_otp()
        otp_hash = self._hash_otp(otp)
        storage_key = self._get_storage_key(email, otp_type)
        
        # Store OTP record
        with self.lock:
            self.otp_storage[storage_key] = OTPRecord(
                otp_hash=otp_hash,
                timestamp=time.time(),
                attempts=0,
                otp_type=otp_type,
                email=email
            )
        
        # Send email
        success, error_msg = self.email_service.send_otp_email(email, otp, otp_type)
        
        if success:
            logger.info(f"Successfully generated and sent OTP for {email} ({otp_type.value})")
            self._log_audit_event("OTP_GENERATED", email, otp_type, True)
            return True, None
        else:
            # Clean up stored OTP on failure
            with self.lock:
                self.otp_storage.pop(storage_key, None)
            
            logger.error(f"Failed to send OTP for {email}: {error_msg}")
            self._log_audit_event("OTP_SEND_FAILED", email, otp_type, False, error_msg)
            return False, error_msg
    
    def verify_otp(self, email: str, input_otp: str, otp_type: OTPType) -> Tuple[bool, Optional[str]]:
        """
        Verify OTP
        """
        storage_key = self._get_storage_key(email, otp_type)
        
        with self.lock:
            record = self.otp_storage.get(storage_key)
            if not record:
                logger.warning(f"OTP not found for {email} ({otp_type.value})")
                self._log_audit_event("OTP_NOT_FOUND", email, otp_type, False)
                return False, "Verification code not found or expired"
            
            # Check expiration
            current_time = time.time()
            if current_time - record.timestamp > self.expire_seconds:
                del self.otp_storage[storage_key]
                logger.warning(f"OTP expired for {email} ({otp_type.value})")
                self._log_audit_event("OTP_EXPIRED", email, otp_type, False)
                return False, "Verification code has expired"
            
            # Check attempt count
            if record.attempts >= record.max_attempts:
                del self.otp_storage[storage_key]
                logger.warning(f"Too many attempts for {email} ({otp_type.value})")
                self._log_audit_event("OTP_TOO_MANY_ATTEMPTS", email, otp_type, False)
                return False, "Too many verification attempts"
            
            # Verify OTP
            input_hash = self._hash_otp(input_otp)
            if input_hash == record.otp_hash:
                # Verification successful, clean up record
                del self.otp_storage[storage_key]
                self.rate_limiter.reset(email)  # Reset rate limiter
                logger.info(f"OTP verification successful for {email} ({otp_type.value})")
                self._log_audit_event("OTP_VERIFIED", email, otp_type, True)
                return True, None
            else:
                # Verification failed, increment attempt count
                record.attempts += 1
                logger.warning(f"OTP verification failed for {email} ({otp_type.value}), attempts: {record.attempts}")
                self._log_audit_event("OTP_VERIFICATION_FAILED", email, otp_type, False)
                return False, f"Invalid verification code. {record.max_attempts - record.attempts} attempts remaining"
    
    def _log_audit_event(self, event_type: str, email: str, otp_type: OTPType, success: bool, details: str = None):
        """
        Log audit event
        """
        audit_log = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "email": email,
            "otp_type": otp_type.value,
            "success": success,
            "details": details
        }

        # Optionally write audit log to file or database
        logger.info(f"AUDIT: {json.dumps(audit_log)}")
    
    def get_stats(self) -> Dict:
        """
        Get OTP Manager statistics
        """
        with self.lock:
            stats = {
                "active_otps": len(self.otp_storage),
                "otp_types": {},
                "rate_limiter_entries": len(self.rate_limiter.attempts)
            }
            
            for record in self.otp_storage.values():
                otp_type = record.otp_type.value
                if otp_type not in stats["otp_types"]:
                    stats["otp_types"][otp_type] = 0
                stats["otp_types"][otp_type] += 1
            
            return stats


# Global OTP Manager instance
try:
    from unified_config import get_config
    otp_manager = OTPManager(
        length=get_config("email.otp_length", 6),
        expire_seconds=get_config("email.otp_expire_seconds", 300)
    )
except ImportError:
    # Fallback to environment variables if unified_config is not available
    otp_manager = OTPManager(
        length=int(os.getenv("OTP_LENGTH", 6)),
        expire_seconds=int(os.getenv("OTP_EXPIRE_SECONDS", 300))
    )