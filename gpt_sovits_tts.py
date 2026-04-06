"""
GPT-SoVITS TTS Manager
A GPT-SoVITS implementation compatible with the existing TTS architecture.
"""

import asyncio
import threading
import wave
import io
import os
import time
from typing import Optional
from loguru import logger
import requests

# Importing a fast resampler
try:
    from fast_resampler import get_resampler
except ImportError:
    get_resampler = None
    logger.warning("Cannot import fast_resampler module, skipping audio resampling")

# 导入事件系统
try:
    from event_system import event_system
except ImportError:
    event_system = None
    logger.warning("Cannot import event_system module")

# 导入统一配置
try:
    from unified_config import get_config
except ImportError:
    get_config = None
    logger.warning("Cannot import unified_config module")


class TTSManager:
    """
    GPT-SoVITS TTS Manager
    Compatible implementation with the existing TTS architecture.
    """

    def __init__(self, device_id=None):
        """
        Initialize GPT-SoVITS TTS Manager

        Args:
            device_id: Device ID for reading device-specific configurations
        """
        self.device_id = device_id

        # Audio configuration - Reference bytedance TTS optimization
        self.chunk_size = 7680  # Increase audio chunk size, reference bytedance TTS
        self.sample_rate = 24000  # Target sample rate (system standard)
        self.source_sample_rate = 32000  # GPT-SoVITS source sample rate
        self.use_raw_pcm = True  # Use raw PCM transmission

        # Playback state and buffer management
        self.playback_active = False
        self.current_device_id = None  # Store current device ID for sending audio
        self.buffer = bytearray()  # Audio data buffer, reference bytedance TTS
        self.audio_queue = None  # Audio queue
        self.playback_finished = None  # Playback finished event
        self.collected_audio_data = []  # Collect audio data for saving files

        # GPT-SoVITS API configuration
        self.base_url = self._get_base_url()

        # Initialize fast resampler
        self.resampler = None
        if get_resampler:
            self.resampler = get_resampler(self.source_sample_rate, self.sample_rate)
            logger.info(f"Fast resampler initialized: {self.source_sample_rate}Hz -> {self.sample_rate}Hz")
        else:
            logger.warning("Fast resampler unavailable, audio will retain original sample rate")

        # Event loop and thread
        self.event_loop = asyncio.new_event_loop()
        self.loop_thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self.loop_thread.start()

        logger.info("GPT-SoVITS TTS Manager initialized")

    def _get_base_url(self) -> str:
        """Get GPT-SoVITS service address"""
        if get_config:
            # Retrieve from device configuration
            base_url = get_config("TTS.sovits.base_url", "http://127.0.0.1:9880", device_id=self.device_id)
            return base_url
        return "http://127.0.0.1:9880"

    def _run_event_loop(self):
        """Run event loop"""
        asyncio.set_event_loop(self.event_loop)
        self.event_loop.run_forever()

    def text_to_speech_sync(self, text: str, device_id: Optional[str] = None,
                           save_to_file=True) -> bool:
        """
        Synchronous text-to-speech interface (compatible with existing TTS interface)

        Args:
            text: Text to convert
            device_id: Target device ID
            save_to_file: Whether to save the file

        Returns:
            bool: Whether successful
        """
        # Use optimized text_to_speech method
        return self.text_to_speech(text, device_id=device_id, save_to_file=save_to_file)

    async def _text_to_speech_async(self, text: str, device_id: Optional[str] = None, save_to_file=True) -> bool:
        """
        Asynchronous text-to-speech implementation - Optimized version, reference bytedance TTS buffering strategy

        Args:
            text: Text to convert
            device_id: Target device ID
            save_to_file: Whether to save the audio file

        Returns:
            bool: Whether successful
        """
        try:
            # Fully reset state, reference bytedance TTS
            self.buffer = bytearray()
            self.current_device_id = device_id
            self.playback_active = False
            self.collected_audio_data = []  # Reset audio collection

            # Reset queue and event, ensure no residual state
            if self.audio_queue:
                while not self.audio_queue.empty():
                    self.audio_queue.get_nowait()
            self.audio_queue = asyncio.Queue()
            self.playback_finished = asyncio.Event()
            self.playback_active = True

            # Send TTS reset signal
            if device_id and event_system:
                event_system.emit('tts_reset', {'device_id': device_id})
                logger.debug(f"Sent TTS reset signal to device: {device_id}")

            # Determine text language
            text_lang = self._detect_language(text)

            # Prepare API request parameters - Simplify parameters, let GPT-SoVITS server handle reference audio and other configurations
            params = {
                'text': text,
                'text_lang': text_lang,
                'media_type': 'wav',
                'streaming_mode': True,  # Enable streaming mode
            }

            # Call GPT-SoVITS API
            logger.info(f"Starting GPT-SoVITS speech synthesis: '{text[:20]}...'")
            url = f"{self.base_url}/tts"

            response = requests.get(url, params=params, stream=True)

            if response.status_code != 200:
                logger.error(f"GPT-SoVITS API request failed: {response.status_code}")
                return False

            # Process audio stream
            success = await self._process_audio_stream(response, device_id, save_to_file)

            return success

        except Exception as e:
            logger.error(f"GPT-SoVITS TTS processing error: {e}")
            return False
        finally:
            self.playback_active = False

    async def _process_audio_stream(self, response, device_id: Optional[str] = None, save_to_file=True) -> bool:
        """
        Process GPT-SoVITS returned audio stream - Optimized for streaming characteristics, intelligent buffering strategy

        Args:
            response: requests response object
            device_id: Target device ID
            save_to_file: Whether to save the audio file

        Returns:
            bool: Whether successfully processed
        """
        try:
            buffer = b''  # Buffer
            header_size = 44  # Standard WAV header size
            header_parsed = False
            total_chunks = 0

            # Audio parameters
            channels = 1
            sample_width = 2
            detected_sample_rate = self.source_sample_rate

            # Intelligent buffering: Accumulate a certain amount of data before processing, balancing real-time and efficiency
            audio_accumulator = b''  # Audio data accumulator
            accumulator_threshold = self.chunk_size * 2  # Accumulation threshold, about 2 chunks size

            for chunk in response.iter_content(chunk_size=4096):
                if not self.playback_active:
                    break

                if chunk:
                    if not header_parsed:
                        buffer += chunk
                        if len(buffer) >= header_size:
                            # Parse WAV header
                            wav_header = buffer[:header_size]
                            try:
                                wav_file = wave.open(io.BytesIO(wav_header), 'rb')
                                channels = wav_file.getnchannels()
                                sample_width = wav_file.getsampwidth()
                                detected_sample_rate = wav_file.getframerate()
                                wav_file.close()

                                logger.debug(f"Detected audio parameters: Sample rate={detected_sample_rate}Hz, Channels={channels}, Bit depth={sample_width*8}bit")

                                # If detected sample rate does not match expected, update resampler
                                if self.resampler and detected_sample_rate != self.source_sample_rate:
                                    logger.info(f"Updating resampler: {detected_sample_rate}Hz -> {self.sample_rate}Hz")
                                    self.resampler = get_resampler(detected_sample_rate, self.sample_rate)

                            except Exception as e:
                                logger.warning(f"WAV header parsing failed: {e}")

                            # Process remaining data after header
                            data = buffer[header_size:]
                            if data:
                                audio_accumulator += data

                            header_parsed = True
                            buffer = b''  # Clear buffer
                    else:
                        # Accumulate audio data
                        audio_accumulator += chunk

                    # Process and send when enough data is accumulated (intelligent buffering strategy)
                    if header_parsed and len(audio_accumulator) >= accumulator_threshold:
                        await self._process_accumulated_audio(
                            audio_accumulator, detected_sample_rate, sample_width, channels, device_id
                        )
                        total_chunks += len(audio_accumulator) // self.chunk_size
                        audio_accumulator = b''  # Clear accumulator

            # Process remaining audio data
            if header_parsed and len(audio_accumulator) > 0:
                await self._process_accumulated_audio(
                    audio_accumulator, detected_sample_rate, sample_width, channels, device_id, is_final=True
                )
                total_chunks += 1

            # Ensure remaining data in buffer is sent
            await self._flush_remaining_buffer(device_id)

            # Save audio file, reference bytedance TTS and prechat implementation
            if save_to_file and self.collected_audio_data:
                await self._save_audio_file_with_path(save_to_file)

            # Send end signal
            await self.audio_queue.put(None)

            # Send TTS completion signal
            if device_id and event_system:
                event_system.emit('tts_completed', {
                    'device_id': device_id
                })
                logger.debug(f"Sent TTS completion signal to device: {device_id}")

            # Set playback finished event
            self.playback_finished.set()

            logger.info(f"GPT-SoVITS audio stream processing completed, sent {total_chunks} audio chunks")
            return True

        except Exception as e:
            logger.error(f"Audio stream processing failed: {e}")
            return False

    async def _process_accumulated_audio(self, audio_data: bytes, source_sr: int,
                                       sample_width: int, channels: int, device_id: Optional[str] = None, is_final: bool = False):
        """
        Process accumulated audio data - Batch resampling and chunk sending

        Args:
            audio_data: Accumulated audio data
            source_sr: Source sample rate
            sample_width: Sample width
            channels: Number of channels
            device_id: Target device ID
            is_final: Whether this is the final batch of data (reserved for future extensions)
        """
        try:
            # Log whether this is the final batch of data (for debugging)
            if is_final:
                logger.debug("Processing the final batch of accumulated audio data")

            # Batch resampling processing
            if self.resampler and source_sr != self.sample_rate:
                processed_audio = await self._process_and_resample_chunk(
                    audio_data, source_sr, sample_width, channels
                )
            else:
                processed_audio = audio_data

            if processed_audio:
                # Collect audio data for saving to file
                self.collected_audio_data.append(processed_audio.copy() if isinstance(processed_audio, bytearray) else processed_audio)

                # Place processed audio data into buffer
                self.buffer.extend(processed_audio)

                # Chunk sending based on chunk_size, referencing bytedance TTS sending strategy
                while len(self.buffer) >= self.chunk_size:
                    chunk = self.buffer[:self.chunk_size]
                    self.buffer = self.buffer[self.chunk_size:]

                    # Add to audio queue
                    await self.audio_queue.put(bytes(chunk))

                    # Send audio through the event system
                    if device_id:
                        event_system.emit('tts_audio_ready', {
                            'device_id': device_id,
                            'audio_data': bytes(chunk),
                            'use_raw_pcm': self.use_raw_pcm
                        })

        except Exception as e:
            logger.error(f"Failed to process accumulated audio data: {e}")

    async def _flush_remaining_buffer(self, device_id: Optional[str] = None):
        """
        Flush remaining data in the buffer

        Args:
            device_id: Target device ID
        """
        try:
            # Send remaining data in the buffer
            if len(self.buffer) > 0:
                leftover = bytes(self.buffer)
                await self.audio_queue.put(leftover)
                if device_id:
                    event_system.emit('tts_audio_ready', {
                        'device_id': device_id,
                        'audio_data': leftover,
                        'use_raw_pcm': self.use_raw_pcm
                    })
                    logger.debug(f"Sent remaining audio data: {len(leftover)} bytes")
                self.buffer.clear()

        except Exception as e:
            logger.error(f"Failed to flush buffer: {e}")

    async def _save_audio_file_with_path(self, save_to_file):
        """
        Save audio file based on the save_to_file parameter

        Args:
            save_to_file: Save path, can be True (default save) or a specific file path string
        """
        try:
            # If save_to_file is a string, use the specified path directly
            if isinstance(save_to_file, str):
                audio_path = save_to_file
                logger.debug(f"Saving audio to specified path: {audio_path}")
            else:
                # If True, do not save (since no path is specified)
                logger.debug("save_to_file is True but no path specified, skipping audio save")
                return

            # Save audio file, referencing bytedance TTS implementation
            await self._save_audio_file_async(self.collected_audio_data, audio_path)

            logger.debug(f"GPT-SoVITS audio saved to: {audio_path}")

        except Exception as e:
            logger.error(f"Failed to save audio file: {e}")

    async def _save_audio_file_async(self, audio_chunks, file_path):
        """
        Asynchronously save audio file, referencing bytedance TTS implementation

        Args:
            audio_chunks: List of audio data chunks
            file_path: Save path
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)

            # Write file synchronously in a separate thread to avoid blocking the event loop
            def write_file():
                with open(file_path, 'wb') as f:
                    for chunk in audio_chunks:
                        if isinstance(chunk, bytes):
                            f.write(chunk)
                        elif isinstance(chunk, bytearray):
                            f.write(bytes(chunk))

            # Execute file writing in thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, write_file)

            logger.info(f"GPT-SoVITS audio successfully saved to: {file_path}")
        except Exception as e:
            logger.error(f"Failed to save GPT-SoVITS audio file: {e}")

    async def _process_and_resample_chunk(self, audio_chunk: bytes, source_sr: int,
                                         sample_width: int, channels: int) -> Optional[bytes]:
        """
        Process and resample audio chunk

        Args:
            audio_chunk: Original audio data
            source_sr: Source sample rate
            sample_width: Sample width
            channels: Number of channels

        Returns:
            bytes: Processed audio data, returns None on failure
        """
        try:
            # If no resampler or sample rate already matches, return directly
            if not self.resampler or source_sr == self.sample_rate:
                return audio_chunk

            # Use resampler to process PCM data
            resampled_chunk = self.resampler.resample_pcm_chunk(
                audio_chunk, sample_width, channels
            )

            if resampled_chunk:
                logger.debug(f"Audio chunk resampled: {len(audio_chunk)} -> {len(resampled_chunk)} bytes")
                return resampled_chunk
            else:
                logger.warning("Audio chunk resampling failed, using original data")
                return audio_chunk

        except Exception as e:
            logger.error(f"Failed to process audio chunk: {e}")
            return audio_chunk  # Return original data on failure

    async def _send_audio_chunk(self, chunk: bytes, device_id: Optional[str] = None):
        """
        Send audio chunk to the event system - Optimized version, removed unnecessary delay

        Args:
            chunk: Audio data chunk
            device_id: Target device ID
        """
        if device_id and event_system:
            event_system.emit('tts_audio_ready', {
                'device_id': device_id,
                'audio_data': chunk,
                'use_raw_pcm': self.use_raw_pcm
            })

        # Removed fixed delay, let batch processing strategy control sending rate

    def _detect_language(self, text: str) -> str:
        """
        Detect text language

        Args:
            text: Input text

        Returns:
            str: Language code
        """
        # Simple language detection logic
        # Check if it contains Chinese characters
        for char in text:
            if '\u4e00' <= char <= '\u9fff':
                return "zh"

        # Default return English
        return "en"

    def stop_tts(self):
        """Stop currently playing TTS audio - Optimized version, referencing bytedance TTS"""
        logger.info("Stopping GPT-SoVITS TTS playback...")

        # Stop flag, notify playback coroutine to stop
        self.playback_active = False

        # Clear audio queue and place termination signal
        if self.audio_queue:
            # Use run_coroutine_threadsafe to ensure execution in the event loop
            future = asyncio.run_coroutine_threadsafe(
                self._clear_audio_queue(),
                self.event_loop
            )
            try:
                # Wait for queue clearing operation to complete, set timeout to prevent blocking
                future.result(3.0)
                logger.info("GPT-SoVITS TTS playback stopped")
                return True
            except Exception as e:
                logger.error(f"Failed to stop GPT-SoVITS TTS playback: {e}")
                return False
        return True

    async def _clear_audio_queue(self):
        """Clear audio queue and send termination signal"""
        if self.audio_queue:
            # Clear all items in the queue
            while not self.audio_queue.empty():
                try:
                    self.audio_queue.get_nowait()
                except:
                    pass

            # Send termination signal
            await self.audio_queue.put(None)

            # If playback finished event exists, set it to completed
            if self.playback_finished and not self.playback_finished.is_set():
                self.playback_finished.set()

    def is_playing(self) -> bool:
        """Check if it is playing"""
        return self.playback_active

    def filter_text_for_tts(self, text):
        """
        Filter special symbols in text that are unfriendly to TTS, referencing bytedance TTS

        Args:
            text: Original text

        Returns:
            str: Filtered text
        """
        if not text:
            return ""

        # Create replacement rule list (symbol, replacement content)
        replacements = [
            ('**', ''),  # Remove bold symbols
            ('*', ''),   # Remove asterisks
            ('_', ''),   # Remove underscores
            ('`', ''),   # Remove backticks
            ('>', ''),   # Remove quote symbols
            ('#', ''),  # Replace hash symbol with description
            ('$', ''), # Replace dollar symbol
            ('---', ''),  # Remove separators
            ('```', ''),  # Remove code blocks
        ]

        # Apply replacement rules
        filtered_text = text
        for old, new in replacements:
            filtered_text = filtered_text.replace(old, new)

        # Remove consecutive multiple spaces
        filtered_text = ' '.join(filtered_text.split())

        return filtered_text

    def text_to_speech(self, text: str, speaker=None, save_to_file=True, device_id=None, use_raw_pcm=None):
        """
        Synchronous version of TTS method, convenient for calling from non-asynchronous environments, referencing bytedance TTS optimization

        Args:
            text: Text content to play
            speaker: Speaker (GPT-SoVITS does not support this yet, reserved for compatibility)
            save_to_file: Whether to save the audio file, True means default save, string means specified path
            device_id: Device ID, used to send audio through the event system
            use_raw_pcm: Whether to use raw PCM transmission, if None, use the class setting

        Returns:
            bool: Whether playback was successful
        """
        # Compatibility handling: Record unused parameters
        if speaker is not None:
            logger.debug(f"GPT-SoVITS does not support speaker parameter: {speaker}")

        # Handle save_to_file parameter
        if isinstance(save_to_file, str):
            logger.debug(f"Saving audio to specified path: {save_to_file}")
        elif save_to_file is True:
            logger.debug("Audio saving enabled (path needs to be specified)")
        elif save_to_file is False:
            logger.debug("Audio saving disabled")
        else:
            logger.debug(f"save_to_file parameter type: {type(save_to_file)}, value: {save_to_file}")

        # Filter special symbols
        filtered_text = self.filter_text_for_tts(text)
        logger.info(f"Original text: {text[:30]}...")
        logger.info(f"Filtered text: {filtered_text[:30]}...")

        # Save device ID
        self.current_device_id = device_id

        # If use_raw_pcm parameter is provided, temporarily update PCM transmission mode
        original_pcm_mode = self.use_raw_pcm
        if use_raw_pcm is not None:
            self.use_raw_pcm = use_raw_pcm
            logger.debug(f"Temporarily set PCM transmission mode: {'Raw PCM' if use_raw_pcm else 'Opus encoding'}")

        if device_id:
            logger.info(f"Sending GPT-SoVITS TTS audio to device via event system: {device_id}, using {'Raw PCM' if self.use_raw_pcm else 'Opus encoding'}")

        try:
            future = asyncio.run_coroutine_threadsafe(
                self._text_to_speech_async(filtered_text, device_id, save_to_file),
                self.event_loop
            )

            # Wait for result, timeout 60 seconds
            result = future.result(60)
            return result
        except Exception as e:
            logger.error(f"Synchronous GPT-SoVITS TTS call failed: {e}")
            return False
        finally:
            # If PCM mode was temporarily changed, restore original settings
            if use_raw_pcm is not None and self.use_raw_pcm != original_pcm_mode:
                self.use_raw_pcm = original_pcm_mode
                logger.debug(f"Restored PCM transmission mode: {'Raw PCM' if original_pcm_mode else 'Opus encoding'}")

    def get_service_name(self) -> str:
        """Get service name"""
        return "gpt_sovits"

    def get_model_id(self) -> str:
        """Get model ID"""
        return "Customize voice"

    def set_model_id(self, model_id: str):
        """Set model ID (GPT-SoVITS does not support dynamic model switching)"""
        logger.info(f"GPT-SoVITS does not support dynamic model switching: {model_id}")

    def get_available_models(self) -> list:
        """Get available model list"""
        return ["Customize voice"]

    def cleanup(self):
        """Clean up resources"""
        try:
            self.playback_active = False
            logger.info("GPT-SoVITS TTS resources cleaned up")
        except Exception as e:
            logger.error(f"Failed to clean up GPT-SoVITS TTS resources: {e}")

    def __del__(self):
        """Destructor"""
        self.cleanup()

# Compatibility alias
GPTSoVITSTTSManager = TTSManager