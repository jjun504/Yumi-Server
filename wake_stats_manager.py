#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Voice Wake-Up Statistics Manager
Responsible for recording and tracking voice wake-up counts
"""

import os
import threading
import time
from datetime import datetime
from loguru import logger

class WakeStatsManager:
    """Voice Wake-Up Statistics Manager"""
    
    def __init__(self, stats_file_path="config/wake_stats.txt"):
        """
        Initialize the statistics manager
        
        Args:
            stats_file_path: Path to the statistics file
        """
        self.stats_file_path = stats_file_path
        self.lock = threading.Lock()
        
        # Ensure the configuration directory exists
        os.makedirs(os.path.dirname(stats_file_path), exist_ok=True)
        
        # If the file does not exist, create it and initialize to 0
        if not os.path.exists(stats_file_path):
            self._write_count(0)
            logger.info(f"Created voice wake-up statistics file: {stats_file_path}")
    
    def _read_count(self):
        """
        Read the current wake-up count
        
        Returns:
            int: Current wake-up count
        """
        try:
            with open(self.stats_file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    return int(content)
                else:
                    return 0
        except (FileNotFoundError, ValueError) as e:
            logger.warning(f"Failed to read wake-up statistics file: {e}")
            return 0
    
    def _write_count(self, count):
        """
        Write the wake-up count
        
        Args:
            count: The count to write
        """
        try:
            with open(self.stats_file_path, 'w', encoding='utf-8') as f:
                f.write(str(count))
        except Exception as e:
            logger.error(f"Failed to write wake-up statistics file: {e}")
    
    def increment_wake_count(self, device_id=None):
        """
        Increment the wake-up count
        
        Args:
            device_id: Device ID (optional, for logging purposes)
        """
        with self.lock:
            current_count = self._read_count()
            new_count = current_count + 1
            self._write_count(new_count)
            
            # Log the update
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            device_info = f" (Device: {device_id})" if device_id else ""
            logger.info(f"Voice wake-up statistics updated{device_info}: {current_count} -> {new_count} [{timestamp}]")
            
            return new_count
    
    def get_wake_count(self):
        """
        Get the current wake-up count
        
        Returns:
            int: Current wake-up count
        """
        with self.lock:
            return self._read_count()
    
    def reset_count(self):
        """
        Reset the wake-up count to 0
        
        Returns:
            bool: Whether the reset was successful
        """
        with self.lock:
            try:
                self._write_count(0)
                logger.info("Voice wake-up statistics have been reset to 0")
                return True
            except Exception as e:
                logger.error(f"Failed to reset wake-up statistics: {e}")
                return False

# Create a global instance
wake_stats_manager = WakeStatsManager()