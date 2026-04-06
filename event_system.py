#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Event System - Used for decoupling communication between components
"""

from loguru import logger

class EventSystem:
    """
    Simple event system for decoupling communication between components
    """
    def __init__(self):
        self.handlers = {}
        logger.debug("Event system initialized")

    def register(self, event_name, handler):
        """
        Register an event handler

        Args:
            event_name: Name of the event
            handler: Handler function that receives one parameter (event data)
        """
        if event_name not in self.handlers:
            self.handlers[event_name] = []

        # Avoid duplicate registration
        if handler not in self.handlers[event_name]:
            self.handlers[event_name].append(handler)
            logger.info(f"Registered event handler: {event_name}, Handler: {handler.__name__}")
            logger.debug(f"Current event handlers: {self.handlers}")

    def unregister(self, event_name, handler=None):
        """
        Unregister an event handler

        Args:
            event_name: Name of the event
            handler: Handler function; if None, remove all handlers for the event
        """
        if event_name in self.handlers:
            if handler:
                if handler in self.handlers[event_name]:
                    self.handlers[event_name].remove(handler)
                    logger.debug(f"Removed event handler: {event_name}")
            else:
                self.handlers[event_name] = []
                logger.debug(f"Removed all event handlers: {event_name}")

    def emit(self, event_name, data):
        """
        Trigger an event

        Args:
            event_name: Name of the event
            data: Event data

        Returns:
            bool or dict: For most events returns True if at least one handler returns True.
                         For 'device_info_request' events, returns the actual data from handler.
        """
        # logger.info(f"trigger event: {event_name}")
        # logger.debug(f"Event Data: {data}")
        # logger.info(f"Currently registered event: {list(self.handlers.keys())}")


        if event_name in self.handlers and self.handlers[event_name]:
            # logger.info(f"Finish {len(self.handlers[event_name])} processors for events: {event_name}")

            results = []
            for handler in self.handlers[event_name]:
                try:
                    # logger.info(f"Call the processor: {handler.__name__}")

                    result = handler(data)
                    # logger.info(f"processor {handler.__name__} Return result: {result}")

                    results.append(result)
                except Exception as e:
                    logger.error(f"Error in event handler: {event_name}, {e}")
                    logger.exception("Detailed error information:")

            # Special handling for device_info_request events - return actual data
            if event_name == 'device_info_request' and results:
                # Return the first non-None result for device info requests
                for result in results:
                    if result is not None:
                        return result
                return {'success': False, 'message': 'No valid response from handlers'}

            # Return true if at least one processor returns true
            success = any(results) if results else False
            # logger.info(f"Event {event_name} Processing result: {success}")

            return success
        else:
            logger.warning(f"No handlers registered for event: {event_name}")
            if event_name == 'device_info_request':
                return {'success': False, 'message': 'No handlers registered'}
            return False

# Create a global instance of the event system
event_system = EventSystem()