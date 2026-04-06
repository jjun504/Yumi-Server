#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STT Stream Bridge Processor - Integrates UDP bridging and streaming speech recognition functionality
Receives audio streams from pi_client_optimized.py and performs real-time speech recognition
"""

import os
import sys
import time
import wave
import socket
import threading
import queue
import json
import re
import opuslib
import numpy as np
from datetime import datetime
from collections import defaultdict, deque
import azure.cognitiveservices.speech as speechsdk
import paho.mqtt.client as mqtt
from unified_config import get_config
import unified_config
from loguru import logger

# Configure logging
logger.add("logs/stt_stream_bridge_processor.log", rotation="10 MB", level="INFO")

class RealTimeStreamingSession:
    """Real-time streaming session class for immediate processing of audio frames without waiting for session end"""

    def __init__(self, device_id, speech_config, sequence_start=0):
        self.device_id = device_id
        self.sequence_start = sequence_start
        self.last_sequence = sequence_start - 1
        self.session_id = f"{device_id}_{int(time.time())}"
        self.missing_sequences = set()
        self.last_activity = time.time()
        self.is_active = True
        self.processed = False

        # Result tracking
        self.recognized_text = []
        self.interim_results = []
        self.final_result = ""

        # Audio data tracking for debugging
        self.total_audio_bytes_pushed = 0
        self.frame_count = 0

        # Silence detection parameters
        self.silence_detection_enabled = True
        self.silence_threshold = 300  # Silence energy threshold
        self.consecutive_silence_frames = 0  # Consecutive silence frames
        self.speech_detected = False  # Whether speech is detected
        self.silence_start_time = None  # Silence start time

        # Distinguish between initial silence and post-speech silence
        self.initial_silence_frames = 60  # Initial silence frame threshold (about 2.25 seconds)
        self.speech_silence_frames = 30   # Post-speech silence frame threshold (about 0.75 seconds)

        # Audio data buffer - Used to save PCM files
        self.audio_data_buffer = bytearray()
        self.start_time = datetime.now()
        self.timestamp_str = self.start_time.strftime("%Y%m%d_%H%M%S")

        # Create audio stream configuration with explicit format
        # Azure STT expects 16kHz, 16-bit, mono PCM
        audio_format = speechsdk.audio.AudioStreamFormat(
            samples_per_second=16000,
            bits_per_sample=16,
            channels=1
        )
        self.push_stream = speechsdk.audio.PushAudioInputStream(stream_format=audio_format)
        audio_config = speechsdk.audio.AudioConfig(stream=self.push_stream)

        logger.info(f"Session {self.session_id} Audio format: 16kHz, 16-bit, mono PCM")

        # Set more speech recognition options - Optimize parameters for faster response
        speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_InitialSilenceTimeoutMs, "30000")  # Reduce initial silence timeout
        speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs, "500")       # Reduce end silence timeout
        speech_config.set_property(speechsdk.PropertyId.Speech_SegmentationSilenceTimeoutMs, "500")               # Reduce segmentation silence timeout
        speech_config.enable_audio_logging()  # Enable audio logging

        # Log Azure STT configuration for debugging
        logger.info(f"Session {self.session_id} Azure STT config - Language: {speech_config.speech_recognition_language}")
        logger.info(f"Session {self.session_id} Azure STT config - Region: {speech_config.region}")
        logger.info(f"Session {self.session_id} Azure STT config - API Key: {speech_config.subscription_key[:5]}...")

        # Create speech recognizer
        try:
            self.speech_recognizer = speechsdk.SpeechRecognizer(
                speech_config=speech_config,
                audio_config=audio_config
            )
            logger.info(f"Session {self.session_id} Azure Speech Recognizer created successfully")
        except Exception as e:
            logger.error(f"Session {self.session_id} Failed to create Azure Speech Recognizer: {e}")
            raise

        # Recognition status
        self.is_recognizing = False

        # Audio decoder
        self.decoder = opuslib.Decoder(16000, 1)

        # Callback functions
        self.on_interim_result = None
        self.on_final_result = None

        # Set up event handlers
        self._setup_recognizer()

        # Start recognition immediately
        self.start_recognition()

        logger.info(f"Created real-time session {self.session_id}, starting sequence number: {sequence_start}")



    def _setup_recognizer(self):
        """Set up recognizer event handlers"""
        try:
            # Recognition result handling
            self.speech_recognizer.recognized.connect(self._on_recognized)
            self.speech_recognizer.recognizing.connect(self._on_recognizing)

            # Session event handling
            self.speech_recognizer.session_started.connect(self._on_session_started)
            self.speech_recognizer.session_stopped.connect(self._on_session_stopped)

            # Error handling
            self.speech_recognizer.canceled.connect(self._on_canceled)

            logger.debug(f"Session {self.session_id} recognizer event handlers set up")
        except Exception as e:
            logger.error(f"Error setting up recognizer event handlers: {e}")

    def _on_recognized(self, evt):
        """Final recognition result handling"""
        try:
            logger.debug(f"Session {self.session_id} _on_recognized called with reason: {evt.result.reason}")

            if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
                text = evt.result.text

                # Ignore if text is empty
                if not text:
                    logger.debug(f"Session {self.session_id} recognized empty text, ignoring")
                    return

                logger.success(f"Session {self.session_id} recognition result: {text}")

                # Save result
                self.recognized_text.append(text)

                # Publish final result
                if self.on_final_result:
                    self.on_final_result(self.device_id, text, True)
            elif evt.result.reason == speechsdk.ResultReason.NoMatch:
                logger.warning(f"Session {self.session_id} no speech could be recognized")
            elif evt.result.reason == speechsdk.ResultReason.Canceled:
                logger.warning(f"Session {self.session_id} recognition was canceled")
            else:
                logger.warning(f"Session {self.session_id} unexpected recognition reason: {evt.result.reason}")
        except Exception as e:
            logger.error(f"Error processing final recognition result: {e}")

    def _on_recognizing(self, evt):
        """Intermediate recognition result handling - Real-time publishing"""
        try:
            logger.debug(f"Session {self.session_id} _on_recognizing called with reason: {evt.result.reason}")

            if evt.result.reason == speechsdk.ResultReason.RecognizingSpeech:
                text = evt.result.text

                # Ignore if text is empty or too short
                if not text or len(text) < 2:
                    logger.debug(f"Session {self.session_id} recognizing text too short or empty: '{text}'")
                    return

                logger.debug(f"Session {self.session_id} recognizing: {text}")

                # Save interim result
                self.interim_results.append(text)

                # Publish interim result
                if self.on_interim_result:
                    self.on_interim_result(self.device_id, text, False)
            else:
                logger.debug(f"Session {self.session_id} unexpected recognizing reason: {evt.result.reason}")
        except Exception as e:
            logger.error(f"Error processing interim recognition result: {e}")

    def _on_session_started(self, evt):
        """Session start event handling"""
        logger.info(f"Session {self.session_id} recognition started")
        self.is_recognizing = True

    def _on_session_stopped(self, evt):
        """Session end event handling"""
        logger.info(f"Session {self.session_id} recognition ended")
        self.is_recognizing = False
        self.final_result = " ".join(self.recognized_text)

    def _on_canceled(self, evt):
        """Cancellation event handling"""
        try:
            reason_text = str(evt.reason) if hasattr(evt, 'reason') else "Unknown reason"
            logger.warning(f"Session {self.session_id} recognition canceled: {reason_text}")
            self.is_recognizing = False

            if hasattr(evt, 'reason') and evt.reason == speechsdk.CancellationReason.Error:
                error_details = str(evt.error_details) if hasattr(evt, 'error_details') else "Unknown error"
                logger.error(f"Azure STT Error details: {error_details}")

                # Log additional debugging information
                if hasattr(evt, 'result') and hasattr(evt.result, 'properties'):
                    properties = evt.result.properties
                    for key in properties:
                        logger.error(f"Azure STT Property {key}: {properties[key]}")
            elif hasattr(evt, 'reason'):
                logger.warning(f"Azure STT canceled for reason: {evt.reason}")

        except Exception as e:
            logger.error(f"Error processing cancellation event: {e}")
            self.is_recognizing = False

    def start_recognition(self):
        """Start streaming recognition"""
        if self.is_recognizing:
            logger.warning(f"Session {self.session_id} is already recognizing")
            return

        # Start continuous recognition
        try:
            self.speech_recognizer.start_continuous_recognition_async()
            logger.info(f"Session {self.session_id} started streaming recognition")

            # Add a small delay to ensure recognition is fully started
            import time
            time.sleep(0.1)

        except Exception as e:
            logger.error(f"Session {self.session_id} failed to start recognition: {e}")

    def stop_recognition(self):
        """Stop streaming recognition"""
        if not self.is_recognizing:
            logger.warning(f"Session {self.session_id} is not recognizing")
            return

        # Stop continuous recognition
        self.speech_recognizer.stop_continuous_recognition_async()
        logger.info(f"Session {self.session_id} stopped streaming recognition")

        # Wait for recognition to complete, but with a shorter timeout
        timeout = 1.0  # Wait at most 1 second
        start_time = time.time()
        while self.is_recognizing and time.time() - start_time < timeout:
            time.sleep(0.05)  # Reduce wait interval to improve response speed

    def process_frame(self, sequence_number, encoded_data):
        """Real-time process a single audio frame"""
        try:
            # Update activity time
            self.last_activity = time.time()

            # Check if it's a new sequence number
            if sequence_number <= self.last_sequence:
                logger.debug(f"Session {self.session_id} duplicate sequence number: {sequence_number}")
                return False

            # Check for missing sequence numbers
            if sequence_number > self.last_sequence + 1:
                for seq in range(self.last_sequence + 1, sequence_number):
                    self.missing_sequences.add(seq)
                    logger.debug(f"Session {self.session_id} missing sequence number: {seq}")

            # Update last sequence number
            self.last_sequence = sequence_number

            # Validate and decode audio frame
            decoded_data = self._validate_and_decode_frame(sequence_number, encoded_data)

            # Check if decoding was successful
            if not decoded_data:
                return False

            # Silence detection (if enabled)
            if hasattr(self, 'silence_detection_enabled') and self.silence_detection_enabled:
                # Calculate audio energy
                energy = self._calculate_energy(decoded_data)

                # Detect if there is speech
                if energy >= self.silence_threshold:  # Silence threshold
                    # Speech detected
                    if not hasattr(self, 'speech_detected') or not self.speech_detected:
                        self.speech_detected = True
                        logger.debug(f"Session {self.session_id} speech detected, energy: {energy:.2f}")

                    # Reset silence count
                    self.consecutive_silence_frames = 0
                    self.silence_start_time = None
                else:
                    # Silence detected
                    if not hasattr(self, 'consecutive_silence_frames'):
                        self.consecutive_silence_frames = 0

                    self.consecutive_silence_frames += 1

                    # Select different silence thresholds based on whether speech has been detected
                    if hasattr(self, 'speech_detected') and self.speech_detected:
                        # Speech detected, use shorter silence threshold
                        silence_frames_threshold = self.speech_silence_frames
                        threshold_name = "speech_silence_frames"
                    else:
                        # No speech detected, use longer initial silence threshold
                        silence_frames_threshold = self.initial_silence_frames
                        threshold_name = "initial_silence_frames"

                    # Check if exceeded silence threshold
                    if self.consecutive_silence_frames > silence_frames_threshold:
                        logger.info(f"Session {self.session_id} detected consecutive silence {self.consecutive_silence_frames} frames, exceeding {threshold_name} ({silence_frames_threshold} frames)")

                        # If speech has been detected, stop recognition immediately
                        if hasattr(self, 'speech_detected') and self.speech_detected and not self.processed:
                            logger.info(f"Session {self.session_id} speech detected, ending session immediately")
                            self.processed = True

                            # Stop recognition
                            self.stop_recognition()

                            # Get final result
                            final_result = self.finalize()

                            # If there is a result, publish it
                            if final_result and self.on_final_result:
                                self.on_final_result(self.device_id, final_result, True)

                            logger.success(f"Session {self.session_id} quick processing complete, final result: {final_result}")

                            # Immediately perform partial resource cleanup to reduce memory pressure
                            try:
                                # Close stream and set to None
                                if self.push_stream:
                                    self.push_stream.close()
                                    self.push_stream = None

                                # Release recognizer resources
                                self.speech_recognizer = None

                                # Mark as partially cleaned resources
                                self.partially_cleaned = True

                                logger.debug(f"Session {self.session_id} partial resource cleanup performed")
                            except Exception as e:
                                logger.error(f"Error during partial resource cleanup: {e}")
                        # If no speech has been detected, just mark as processed and let the session monitoring thread handle it
                        elif (not hasattr(self, 'speech_detected') or not self.speech_detected) and not self.processed:
                            logger.info(f"Session {self.session_id} initial silence too long, marked as processed")
                            self.processed = True

            # Add decoded audio data to buffer
            self.audio_data_buffer.extend(decoded_data)

            # Push to stream - Check if stream is still valid before writing
            if self.push_stream is not None:
                try:
                    # Log audio data details for debugging (only for first few frames)
                    if sequence_number <= 5:
                        audio_array = np.frombuffer(decoded_data, dtype=np.int16)
                        logger.info(f"Session {self.session_id} Frame {sequence_number} audio details: "
                                  f"size={len(decoded_data)} bytes, samples={len(audio_array)}, "
                                  f"min={np.min(audio_array)}, max={np.max(audio_array)}, "
                                  f"mean={np.mean(audio_array):.2f}")

                    self.push_stream.write(decoded_data)
                    self.total_audio_bytes_pushed += len(decoded_data)
                    self.frame_count += 1

                    # Log progress every 50 frames
                    if self.frame_count % 50 == 0:
                        logger.info(f"Session {self.session_id} pushed {self.frame_count} frames, "
                                  f"total {self.total_audio_bytes_pushed} bytes to Azure STT")

                    logger.debug(f"Pushed frame {sequence_number} to stream, size: {len(decoded_data)} bytes")
                except Exception as e:
                    logger.warning(f"Failed to write frame {sequence_number} to stream: {e}")
                    # Stream might be closed, mark as processed to prevent further writes
                    if not self.processed:
                        logger.info(f"Session {self.session_id} stream closed, marking as processed")
                        self.processed = True
                    return False
            else:
                logger.debug(f"Session {self.session_id} stream is None, skipping frame {sequence_number}")
                # If stream is None but session is not processed, mark as processed
                if not self.processed:
                    logger.info(f"Session {self.session_id} stream is None, marking as processed")
                    self.processed = True
                return False

            return True

        except Exception as e:
            logger.error(f"Error processing frame {sequence_number}: {e}")
            return False

    def _calculate_energy(self, audio_data):
        """Calculate the energy of audio data"""
        try:
            # Convert byte data to short integer array
            as_ints = np.frombuffer(audio_data, dtype=np.int16)

            # Check for valid data
            if len(as_ints) == 0:
                return 0.0

            # Use float64 to avoid overflow, and ensure values are positive
            squared = np.square(as_ints.astype(np.float64))
            mean_squared = np.mean(squared)

            # Prevent negative or zero values
            if mean_squared <= 0:
                return 0.0

            # Calculate root mean square energy
            return np.sqrt(mean_squared)

        except Exception as e:
            logger.error(f"Error calculating energy: {e}")
            return 0.0

    def _validate_and_decode_frame(self, sequence_number, encoded_data):
        """Validate and decode audio frame, handling possible errors"""
        try:
            # Basic validation
            if not encoded_data or len(encoded_data) == 0:
                logger.warning(f"Frame {sequence_number} data is empty")
                return None

            # Try to decode
            try:
                # Use try-except to catch decoding errors
                decoded_data = self.decoder.decode(encoded_data, 960)
                return decoded_data
            except Exception as e:
                # If decoding fails, try to reset the decoder
                logger.warning(f"Decoding frame {sequence_number} failed: {e}, trying to reset decoder")
                self.decoder = opuslib.Decoder(16000, 1)  # Recreate decoder

                # Try decoding again
                try:
                    decoded_data = self.decoder.decode(encoded_data, 960)
                    return decoded_data
                except:
                    # If it still fails, give up on this frame
                    logger.error(f"Cannot decode frame {sequence_number} even after resetting decoder")
                    return None
        except Exception as e:
            logger.error(f"Error validating frame {sequence_number}: {e}")
            return None

    def is_inactive(self, timeout=2.0):
        """Check if the session is inactive (no new frames for more than timeout seconds)"""
        return time.time() - self.last_activity > timeout

    def finalize(self):
        """Complete session processing and return final result"""
        self.processed = True
        self.final_result = " ".join(self.recognized_text)

        # Report missing sequence numbers
        if self.missing_sequences:
            logger.warning(f"Session {self.session_id} has {len(self.missing_sequences)} missing sequence numbers")

        return self.final_result

    def save_frames_to_wav(self, output_dir="combined_recordings"):
        """Save audio frames as WAV files (for debugging)"""
        try:
            # Ensure output directory exists
            os.makedirs(output_dir, exist_ok=True)

            # If there is no audio data, return None
            if not self.audio_data_buffer:
                logger.warning(f"Session {self.session_id} has no audio data to save")
                return None

            # Create WAV file path
            wav_path = os.path.join(output_dir, f"{self.device_id}_{self.timestamp_str}.wav")

            # Save as WAV file - Using the same audio parameters as in pi_client_optimized.py
            with wave.open(wav_path, 'wb') as wf:
                wf.setnchannels(1)  # Mono
                wf.setsampwidth(2)  # 16-bit = 2 bytes
                wf.setframerate(16000)  # Sample rate 16kHz
                wf.writeframes(self.audio_data_buffer)

            logger.info(f"Saved WAV audio file: {wav_path} (16000Hz, 16-bit, Mono)")
            return wav_path

        except Exception as e:
            logger.error(f"Error saving WAV file: {e}")
            return None

    def save_frames_to_pcm(self, user_id, output_base_dir=None):
        """Save audio frames as PCM files

        Args:
            user_id: User ID
            output_base_dir: Output base directory, if None use the user directory under the current working directory

        Returns:
            str: PCM file path, returns None if saving fails
        """
        try:
            # If there is no audio data, return None
            if not self.audio_data_buffer:
                logger.warning(f"Session {self.session_id} has no audio data to save")
                return None

            # If output base directory is not specified, use the user directory under the current working directory
            if output_base_dir is None:
                output_base_dir = os.path.join(os.getcwd(), "user")

            # Create output directory path: user/{user_id}/{device_id}/chat_history/audio/
            output_dir = os.path.join(output_base_dir, user_id, self.device_id, "chat_history", "audio")
            os.makedirs(output_dir, exist_ok=True)

            # Create PCM file path
            pcm_path = os.path.join(output_dir, f"{self.timestamp_str}.pcm")

            # Save as PCM file - Directly save raw PCM data
            # Note: The PCM data saved here is 16000Hz sample rate, 16-bit, Mono
            # Consistent with the configuration in pi_client_optimized.py:
            # "audio_sample_rate": 16000, "audio_channels": 1, "audio_format": "int16"
            with open(pcm_path, 'wb') as f:
                f.write(self.audio_data_buffer)

            logger.info(f"Saved PCM audio file: {pcm_path} (16000Hz, 16-bit, Mono)")
            return pcm_path

        except Exception as e:
            logger.error(f"Error saving PCM file: {e}")
            return None

    def cleanup(self):
        """Clean up resources"""
        try:
            # Log session statistics before cleanup
            duration = time.time() - self.last_activity if hasattr(self, 'last_activity') else 0
            logger.info(f"Session {self.session_id} statistics: "
                       f"frames={getattr(self, 'frame_count', 0)}, "
                       f"audio_bytes={getattr(self, 'total_audio_bytes_pushed', 0)}, "
                       f"duration={duration:.2f}s, "
                       f"recognized_texts={len(self.recognized_text)}")

            # Ensure recognition has stopped
            if hasattr(self, 'is_recognizing') and self.is_recognizing:
                self.stop_recognition()

            # Close stream
            if hasattr(self, 'push_stream') and self.push_stream:
                try:
                    self.push_stream.close()
                except Exception as e:
                    logger.error(f"Error closing push stream: {e}")
                self.push_stream = None

            # Release decoder resources
            if hasattr(self, 'decoder') and self.decoder:
                self.decoder = None

            # Release recognizer resources
            if hasattr(self, 'speech_recognizer') and self.speech_recognizer:
                self.speech_recognizer = None

            # Mark as fully cleaned
            self.partially_cleaned = True

            # Release other resources
            self.recognized_text = []
            self.interim_results = []

            logger.debug(f"Session {self.session_id} resources fully cleaned")
            return True

        except Exception as e:
            logger.error(f"Error cleaning up session {self.session_id} resources: {e}")
            return False

class STTStreamBridgeProcessor:
    """STT Stream Bridge Processor - Integrates UDP bridging and streaming speech recognition functionality"""

    def __init__(self, udp_port=8884, mqtt_broker="broker.emqx.io", mqtt_port=1883,
                 language=None, save_audio=False, auto_process=True,
                 realtime_mode=True, session_timeout=20.0):
        """
        Initialize STT Stream Bridge Processor

        Args:
            udp_port: UDP listening port
            mqtt_broker: MQTT broker address
            mqtt_port: MQTT broker port
            language: Speech recognition language, if None, fetch from config
            save_audio: Whether to save audio files
            auto_process: Whether to automatically process new sessions
            realtime_mode: Whether to use real-time mode (process frames immediately)
            session_timeout: Session timeout duration (seconds)
        """
        self.udp_port = udp_port
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.language = language or get_config("speech_services.azure_stt.default_language", "zh-CN")
        self.save_audio = save_audio
        self.auto_process = auto_process
        self.realtime_mode = realtime_mode
        self.session_timeout = session_timeout

        # Ensure output directory exists
        if self.save_audio:
            os.makedirs("combined_recordings", exist_ok=True)

        # Initialize Azure STT
        self.api_key = get_config("STT.azure.api_key")
        self.region = get_config("STT.azure.region")

        # Check if configuration is valid
        if not self.api_key or not self.region:
            error_msg = f"Invalid Azure STT configuration: API key={'missing' if not self.api_key else 'set'}, region={'missing' if not self.region else self.region}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info(f"Azure STT configuration: API key={self.api_key[:5]}..., region={self.region}")

        try:
            self.speech_config = speechsdk.SpeechConfig(subscription=self.api_key, region=self.region)
        except Exception as e:
            logger.error(f"Failed to create Azure SpeechConfig: {e}")
            raise
        self.speech_config.speech_recognition_language = self.language
        self.speech_config.set_profanity(speechsdk.ProfanityOption.Masked)

        # Set more advanced options - optimize parameters for faster response
        self.speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_InitialSilenceTimeoutMs, "3000")  # Reduce initial silence timeout
        self.speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs, "500")       # Reduce end silence timeout
        self.speech_config.set_property(speechsdk.PropertyId.Speech_SegmentationSilenceTimeoutMs, "500")               # Reduce segmentation silence timeout

        # Enable detailed logging
        self.speech_config.set_property(speechsdk.PropertyId.Speech_LogFilename, "logs/azure_speech.log")
        self.speech_config.enable_audio_logging()

        # Session management
        self.sessions = {}  # Device ID -> RealTimeStreamingSession
        self.lock = threading.Lock()

        # UDP socket
        self.udp_socket = None

        # MQTT client
        self.mqtt_client = mqtt.Client(f"stt_bridge_{int(time.time())}")
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message

        # Control flags
        self.running = False
        self.udp_thread = None
        self.session_monitor_thread = None

        # Callback function
        self.on_recognition_result = None

        logger.info(f"STT Stream Bridge Processor initialized, UDP port: {udp_port}, MQTT broker: {mqtt_broker}:{mqtt_port}")

    def set_recognition_callback(self, callback):
        """Set recognition result callback function"""
        self.on_recognition_result = callback
        logger.info("Recognition result callback function set")

    def initialize_without_udp(self):
        """Initialize processor without starting UDP listening"""
        if self.running:
            logger.warning("Processor is already running")
            return False

        # Set running flag
        self.running = True

        # Reset statistics
        self.stats = {
            "frames_processed": 0,
            "sessions_created": 0,
            "sessions_completed": 0,
            "decoding_errors": 0
        }

        # Explicitly set UDP socket to None to avoid misuse
        self.udp_socket = None

        # Connect to MQTT broker
        try:
            self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port, 60)
            self.mqtt_client.loop_start()
            logger.info(f"Connected to MQTT broker {self.mqtt_broker}:{self.mqtt_port}")
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            self.running = False
            return False

        # Start session monitoring thread
        self.session_monitor_thread = threading.Thread(target=self._session_monitor)
        self.session_monitor_thread.daemon = True
        self.session_monitor_thread.start()

        # Publish online status
        self.mqtt_client.publish("bridge/status", json.dumps({
            "status": "online",
            "realtime_mode": self.realtime_mode,
            "timestamp": time.time()
        }), retain=True)

        logger.info(f"STT Stream Bridge Processor initialized - {'real-time processing' if self.realtime_mode else 'batch processing'} mode (no UDP)")
        return True

    def start(self):
        """Start processor"""
        if self.running:
            logger.warning("Processor is already running")
            return False

        # Set running flag
        self.running = True

        # Reset statistics
        self.stats = {
            "frames_processed": 0,
            "sessions_created": 0,
            "sessions_completed": 0,
            "decoding_errors": 0
        }

        # Initialize UDP socket
        try:
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.bind(('0.0.0.0', self.udp_port))
            # Set receive buffer size to improve performance
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 262144)  # 256KB
            logger.info(f"UDP socket bound to port {self.udp_port}")
        except Exception as e:
            logger.error(f"Failed to initialize UDP socket: {e}")
            self.running = False
            return False

        # Connect to MQTT broker
        try:
            self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port, 60)
            self.mqtt_client.loop_start()
            logger.info(f"Connected to MQTT broker {self.mqtt_broker}:{self.mqtt_port}")
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            self.udp_socket.close()
            self.running = False
            return False

        # Start UDP listening thread
        self.udp_thread = threading.Thread(target=self._udp_listener)
        self.udp_thread.daemon = True
        self.udp_thread.start()

        # Start session monitoring thread
        self.session_monitor_thread = threading.Thread(target=self._session_monitor)
        self.session_monitor_thread.daemon = True
        self.session_monitor_thread.start()

        # Publish online status
        self.mqtt_client.publish("bridge/status", json.dumps({
            "status": "online",
            "udp_port": self.udp_port,
            "realtime_mode": self.realtime_mode,
            "timestamp": time.time()
        }), retain=True)

        logger.info(f"STT Stream Bridge Processor started - {'real-time processing' if self.realtime_mode else 'batch processing'} mode")
        return True

    def stop(self):
        """Stop processor"""
        if not self.running:
            logger.warning("Processor is not running")
            return

        # Set running flag to False
        self.running = False

        # Wait for threads to finish
        if self.udp_thread and self.udp_thread.is_alive():
            self.udp_thread.join(timeout=2.0)

        if self.session_monitor_thread and self.session_monitor_thread.is_alive():
            self.session_monitor_thread.join(timeout=2.0)

        # Close UDP socket
        if self.udp_socket:
            try:
                self.udp_socket.close()
                self.udp_socket = None
            except:
                pass

        # Stop MQTT client
        try:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        except:
            pass

        # Clean up all sessions
        with self.lock:
            for session in self.sessions.values():
                session.cleanup()
            self.sessions.clear()

        logger.info("STT Stream Bridge Processor stopped")

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        logger.info(f"MQTT connected, result code: {rc}")

        # Subscribe to command topics
        client.subscribe("device/+/command")

        # Publish online status
        client.publish("bridge/status", json.dumps({
            "status": "online",
            "udp_port": self.udp_port
        }))

    def _on_mqtt_message(self, client, userdata, msg):
        """MQTT message callback"""
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode())

            # Handle device commands
            if topic.startswith("device/") and topic.endswith("/command"):
                device_id = topic.split("/")[1]
                self._handle_device_command(device_id, payload)

        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")

    def _handle_device_command(self, device_id, command):
        """Handle device commands"""
        cmd_type = command.get("type")

        if cmd_type == "start_record":
            logger.info(f"Received start recording command, device: {device_id}")
            # Add processing logic here if needed

        elif cmd_type == "stop_record":
            logger.info(f"Received stop recording command, device: {device_id}")
            # Add processing logic here if needed

        elif cmd_type == "process_session":
            logger.info(f"Received process session command, device: {device_id}")
            with self.lock:
                if device_id in self.sessions:
                    session = self.sessions[device_id]
                    # Mark session as inactive to trigger processing
                    session.last_update_time = 0

    def _udp_listener(self):
        """UDP listener thread - real-time processing mode"""
        logger.info("UDP listener thread started (real-time processing mode)")

        while self.running:
            try:
                # Receive UDP data
                data, addr = self.udp_socket.recvfrom(2048)

                # Parse data packet
                if len(data) < 6:  # At least 4 bytes for sequence number + 2 bytes for length
                    logger.warning(f"Received invalid data packet, length: {len(data)}")
                    continue

                # Extract sequence number and data length
                seq_num = int.from_bytes(data[:4], byteorder='big')
                data_len = int.from_bytes(data[4:6], byteorder='big')

                # Check if data length matches
                if len(data) < 6 + data_len:
                    logger.warning(f"Data packet length mismatch, expected: {6 + data_len}, actual: {len(data)}")
                    continue

                # Extract encoded data
                encoded_data = data[6:6+data_len]

                # Get device ID (use IP address as temporary ID)
                device_id = f"device_{addr[0]}"

                # Real-time processing of audio frames
                self._process_audio_frame_realtime(device_id, seq_num, encoded_data)

            except Exception as e:
                if self.running:  # Log errors only during normal operation
                    logger.error(f"Error processing UDP data: {e}")
                    time.sleep(0.1)  # Avoid excessive CPU usage in error scenarios

        logger.info("UDP listener thread ended")

    def process_audio_frame(self, device_id, seq_num, encoded_data):
        """
        Directly process audio frames

        Args:
            device_id: Device ID
            seq_num: Sequence number
            encoded_data: Encoded audio data

        Returns:
            bool: Whether processing was successful
        """
        try:
            return self._process_audio_frame_realtime(device_id, seq_num, encoded_data)
        except Exception as e:
            logger.error(f"Error processing audio frame: {e}")
            return False

    def _process_audio_frame_realtime(self, device_id, seq_num, encoded_data):
        """Real-time processing of audio frames - process immediately instead of batch processing"""
        try:
            with self.lock:
                # Check if device session exists
                if device_id not in self.sessions:
                    # Get device-specific language settings
                    device_language = self.language  # Default to current language setting
                    try:
                        # Use unified_config to fetch device-specific STT language settings
                        device_language = get_config("STT.language", self.language, device_id=device_id)
                        logger.debug(f"Fetched STT language setting from device config: {device_language}")
                    except Exception as e:
                        logger.error(f"Error fetching device language setting: {e}")

                    # Update speech_config if device language differs from current language
                    if device_language != self.speech_config.speech_recognition_language:
                        logger.info(f"Updating language setting for device {device_id}: {self.speech_config.speech_recognition_language} -> {device_language}")
                        self.speech_config.speech_recognition_language = device_language

                    # Create new real-time session
                    logger.info(f"Creating new real-time session for device {device_id}, initial sequence number: {seq_num}, language: {device_language}")
                    session = RealTimeStreamingSession(
                        device_id=device_id,
                        speech_config=self.speech_config,
                        sequence_start=seq_num
                    )

                    # Set result callback functions
                    session.on_interim_result = self._handle_interim_result
                    session.on_final_result = self._handle_final_result

                    # Add session to session list
                    self.sessions[device_id] = session
                else:
                    # Get existing session
                    session = self.sessions[device_id]

            # Real-time frame processing (execute outside lock to improve concurrency performance)
            success = session.process_frame(seq_num, encoded_data)

            if not success:
                logger.warning(f"Device {device_id} frame {seq_num} processing failed")

        except Exception as e:
            logger.error(f"Error processing audio frame {seq_num}: {e}")
            return False

        return True

    def _handle_interim_result(self, device_id, text, is_final):
        """Handle interim recognition results"""
        try:
            # Update logs (reduce log volume, print at most 50 characters)
            truncated_text = text[:50] + ("..." if len(text) > 50 else "")
            logger.debug(f"Device {device_id} interim recognition result: {truncated_text}")

            # Publish interim results to MQTT
            self.mqtt_client.publish(f"device/{device_id}/stt_interim", json.dumps({
                "text": text,
                "timestamp": time.time(),
                "is_final": is_final
            }))

            # Invoke callback function (if any)
            if self.on_recognition_result:
                try:
                    self.on_recognition_result(device_id, text, is_final=False)
                except TypeError as e:
                    # Compatibility with older callback functions (do not accept is_final parameter)
                    logger.warning(f"Callback function does not support is_final parameter: {e}")
                    self.on_recognition_result(device_id, text)

        except Exception as e:
            logger.error(f"Error handling interim recognition result: {e}")

    def _handle_final_result(self, device_id, text, is_final):
        """Handle final recognition results"""
        try:
            logger.success(f"Device {device_id} final recognition result: {text}")

            # Get session object
            session = None
            with self.lock:
                if device_id in self.sessions:
                    session = self.sessions[device_id]

            # If session does not exist, return directly
            if not session:
                logger.warning(f"Session for device {device_id} does not exist, unable to save audio")
                return

            # Get user ID
            user_id = "default_user_id"
            try:
                # Use unified_config to fetch device-specific user ID
                user_id = get_config("system.user_id", "default_user_id", device_id=device_id)
                logger.debug(f"Fetched user ID from config: {user_id}")
            except Exception as e:
                logger.error(f"Error fetching user ID: {e}")

            # Save PCM file
            pcm_path = session.save_frames_to_pcm(user_id)

            # Publish final results to MQTT
            result_data = {
                "text": text,
                "timestamp": time.time(),
                "is_final": is_final
            }

            # If audio file was saved, add to results
            if pcm_path:
                result_data["audio_path"] = pcm_path

            self.mqtt_client.publish(f"device/{device_id}/stt_result", json.dumps(result_data))

            # Invoke callback function (if any)
            if self.on_recognition_result:
                try:
                    # Pass audio path to callback function
                    if pcm_path:
                        self.on_recognition_result(device_id, text, is_final=True, audio_path=pcm_path)
                    else:
                        self.on_recognition_result(device_id, text, is_final=True)
                except TypeError as e:
                    # Compatibility with older callback functions (do not accept is_final or audio_path parameters)
                    logger.warning(f"Callback function does not support all parameters: {e}")
                    try:
                        self.on_recognition_result(device_id, text)
                    except Exception as e2:
                        logger.error(f"Error invoking callback function: {e2}")

        except Exception as e:
            logger.error(f"Error processing final recognition result: {e}")

    def _session_monitor(self):
        """Session monitoring thread - clean up inactive sessions"""
        logger.info("Session monitoring thread started")

        # Session count and memory monitoring
        session_count = 0
        last_cleanup_time = time.time()

        while self.running:
            try:
                # Find inactive sessions
                sessions_to_finalize = []
                processed_sessions = []

                with self.lock:
                    current_time = time.time()
                    session_count = len(self.sessions)

                    # Log session count
                    if session_count > 0 and session_count % 10 == 0:
                        logger.info(f"Current active session count: {session_count}")

                    for device_id, session in list(self.sessions.items()):
                        # Check if session is inactive
                        inactivity_time = current_time - session.last_activity

                        # Processed sessions: clean up immediately
                        if session.processed:
                            # If more than 1 second has passed, clean up immediately
                            if inactivity_time > 1.0:
                                processed_sessions.append((device_id, session))
                        # Unprocessed sessions: stop recognition and get results after 2 seconds of inactivity
                        elif inactivity_time > 2.0:
                            sessions_to_finalize.append((device_id, session))

                # Emergency cleanup: if session count is too high, force cleanup of all processed sessions
                if session_count > 50 or (current_time - last_cleanup_time > 60):
                    logger.warning(f"Performing emergency cleanup, current session count: {session_count}")
                    with self.lock:
                        for device_id, session in list(self.sessions.items()):
                            if session.processed and device_id not in [d for d, _ in processed_sessions]:
                                processed_sessions.append((device_id, session))
                    last_cleanup_time = current_time

                # Quick processing: stop recognition and get results
                for device_id, session in sessions_to_finalize:
                    inactivity_time = time.time() - session.last_activity
                    logger.info(f"Quickly processing inactive session: {session.session_id}, inactivity time: {inactivity_time:.1f} seconds")

                    # Stop recognition
                    session.stop_recognition()

                    # Get final result
                    final_result = session.finalize()

                    if final_result:
                        logger.success(f"Session {session.session_id} final recognition result: {final_result}")

                        # Publish final result
                        try:
                            self.mqtt_client.publish(f"device/{device_id}/stt_final", json.dumps({
                                "text": final_result,
                                "timestamp": time.time(),
                                "session_id": session.session_id
                            }))
                        except Exception as e:
                            logger.error(f"Failed to publish final result: {e}")

                    # Mark as processed but do not clean up resources yet
                    session.processed = True

                    # Immediately add to cleanup list
                    processed_sessions.append((device_id, session))

                # Clean up processed sessions
                for device_id, session in processed_sessions:
                    try:
                        # Check if partial cleanup has been performed
                        if not hasattr(session, 'partially_cleaned') or not session.partially_cleaned:
                            # Clean up resources
                            session.cleanup()

                        # Remove from session list
                        with self.lock:
                            if device_id in self.sessions and self.sessions[device_id] == session:
                                del self.sessions[device_id]
                                logger.info(f"Session {session.session_id} fully cleaned up")
                    except Exception as e:
                        logger.error(f"Error cleaning up session {session.session_id}: {e}")

                # Short sleep
                time.sleep(0.2)  # Further reduce sleep time to improve responsiveness

            except Exception as e:
                logger.error(f"Session monitoring thread error: {e}")
                time.sleep(0.2)

        logger.info("Session monitoring thread ended")

    def _process_inactive_session(self, device_id, session):
        """Process inactive session"""
        try:
            logger.info(f"Processing inactive session: {session.session_id}")

            # Stop recognition
            session.stop_recognition()

            # Get final result
            final_result = session.finalize()

            # Get user ID
            user_id = "default_user_id"
            try:
                # Use unified_config to fetch device-specific user ID
                user_id = get_config("system.user_id", "default_user_id", device_id=device_id)
                logger.debug(f"Fetched user ID from config: {user_id}")
            except Exception as e:
                logger.error(f"Error fetching user ID: {e}")

            # Save PCM file
            pcm_path = None
            if hasattr(session, 'audio_data_buffer') and session.audio_data_buffer:
                pcm_path = session.save_frames_to_pcm(user_id)

            # Process result
            if final_result:
                logger.success(f"Session {session.session_id} final recognition result: {final_result}")

                # Publish final result
                try:
                    result_data = {
                        "text": final_result,
                        "timestamp": time.time(),
                        "session_id": session.session_id
                    }

                    # If audio file was saved, add to result
                    if pcm_path:
                        result_data["audio_path"] = pcm_path

                    self.mqtt_client.publish(f"device/{device_id}/stt_final", json.dumps(result_data))
                except Exception as e:
                    logger.error(f"Failed to publish final result: {e}")

                # Invoke callback function (if any)
                if self.on_recognition_result:
                    try:
                        # Pass audio path to callback function
                        if pcm_path:
                            self.on_recognition_result(device_id, final_result, is_final=True, audio_path=pcm_path)
                        else:
                            self.on_recognition_result(device_id, final_result, is_final=True)
                    except TypeError as e:
                        # Compatibility with older callback functions (do not accept is_final or audio_path parameters)
                        logger.warning(f"Callback function does not support all parameters: {e}")
                        try:
                            self.on_recognition_result(device_id, final_result)
                        except Exception as e2:
                            logger.error(f"Error invoking callback function: {e2}")
            else:
                logger.warning(f"Session {session.session_id} did not recognize any speech")

            # Clean up resources
            session.cleanup()

            # Remove from session list
            with self.lock:
                if device_id in self.sessions and self.sessions[device_id] == session:
                    del self.sessions[device_id]

        except Exception as e:
            logger.error(f"Error processing inactive session: {e}")

    def process_all_sessions(self):
        """Process all sessions (one-time)"""
        logger.info("Starting to process all sessions")

        # Get all sessions
        with self.lock:
            sessions_to_process = [(device_id, session) for device_id, session in self.sessions.items()
                                  if not session.processed]

        # Process sessions
        for device_id, session in sessions_to_process:
            self._process_inactive_session(device_id, session)

        logger.info("All sessions processed")

    def cleanup(self):
        """Clean up resources"""
        logger.info("Cleaning up resources...")

        # Stop processor
        self.stop()

        logger.info("Resource cleanup complete")

# Example callback function
def on_recognition_result(device_id, text, is_final=False):
    """Recognition result callback function

    Args:
        device_id: Device ID
        text: Recognized text
        is_final: Whether it is the final result
    """
    logger.info(f"Device {device_id} {'final' if is_final else 'interim'} recognition result: {text}")
    # Custom processing logic can be added here, such as:
    # 1. Sending results to a chat system
    # 2. Saving to a database
    # 3. Triggering other actions

def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(description="STT Stream Bridge Processor")
    parser.add_argument("--udp-port", type=int, default=8884, help="UDP listening port")
    parser.add_argument("--mqtt-broker", default="broker.emqx.io", help="MQTT broker address")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--language", default="zh-CN", help="Speech recognition language")
    parser.add_argument("--save-audio", action="store_true", help="Save audio files")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--batch-mode", action="store_true", help="Use batch processing mode instead of real-time mode")
    parser.add_argument("--session-timeout", type=float, default=15.0, help="Session timeout duration (seconds)")

    # Create log directory
    os.makedirs("logs", exist_ok=True)

    # Parse arguments
    args = parser.parse_args()

    # Set log level
    if args.debug:
        logger.remove()
        logger.add("logs/stt_stream_bridge_processor.log", rotation="10 MB", level="DEBUG")
        logger.add(sys.stderr, level="DEBUG")
        logger.debug("Debug mode enabled")

    # Create processor - default to real-time mode
    processor = STTStreamBridgeProcessor(
        udp_port=args.udp_port,
        mqtt_broker=args.mqtt_broker,
        mqtt_port=args.mqtt_port,
        language=args.language,
        save_audio=args.save_audio,
        realtime_mode=not args.batch_mode,  # Use real-time mode unless batch processing is explicitly specified
        session_timeout=args.session_timeout
    )

    # Set callback function
    processor.set_recognition_callback(on_recognition_result)

    try:
        # Start processor
        if not processor.start():
            logger.error("Failed to start processor")
            return

        # Output help information
        print("\n" + "="*60)
        print(f"STT Stream Bridge Processor started - {'Batch' if args.batch_mode else 'Real-time'} mode")
        print(f"UDP port: {args.udp_port}, MQTT broker: {args.mqtt_broker}:{args.mqtt_port}")
        print(f"Language: {args.language}, Session timeout: {args.session_timeout} seconds")
        print("="*60)
        print("Press Ctrl+C to exit")

        # Wait for interruption
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("Interrupt signal received, exiting...")
    finally:
        processor.cleanup()

if __name__ == "__main__":
    main()