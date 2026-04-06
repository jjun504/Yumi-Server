import azure.cognitiveservices.speech as speechsdk
import threading
import time
from loguru import logger
from unified_config import unified_config
# import log_saver
import wave
import os
import sys

# Add server.py directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import event system
from event_system import event_system
logger.info("Importing event_system for sending TTS audio")

class FileAndSpeakerCallback(speechsdk.audio.PushAudioOutputStreamCallback):
    def __init__(self, file_path, sample_rate=22050, device_id=None, use_raw_pcm=True):
        # Prepare WAV file header
        self.device_id = device_id  # Store device ID for sending audio

        # Store PCM transmission mode settings - default to raw PCM
        self.use_raw_pcm = use_raw_pcm
        logger.info(f"Audio transmission mode: {'Raw PCM' if self.use_raw_pcm else 'Opus encoding'}")

        # Use event_system to send audio
        logger.info(f"Using event_system to send audio to device: {device_id}, PCM mode: {'Raw PCM' if self.use_raw_pcm else 'Opus encoding'}")

        self.wf = wave.open(file_path, 'wb')
        self.wf.setnchannels(1)
        self.wf.setsampwidth(2)   # Raw16bit
        self.wf.setframerate(sample_rate)
        self.buffer = bytearray()
        self.chunk_size = 7680
        # Prepare PyAudio playback
        # self.pa = pyaudio.PyAudio()
        # self.stream = self.pa.open(format=self.pa.get_format_from_width(2),
        #                           channels=1, rate=sample_rate, output=True)

    def write(self, audio_data: memoryview) -> int:
        data = bytes(audio_data)
        # Write to file
        self.wf.writeframes(data)
        self.buffer.extend(data)
        # Playback
        # self.stream.write(data)
        while len(self.buffer) >= self.chunk_size:
            # Extract a fixed-size chunk
            chunk = bytes(self.buffer[:self.chunk_size])
            # Update buffer, remove processed part
            self.buffer = self.buffer[self.chunk_size:]

            # Use event_system to send audio
            if self.device_id:
                # Send audio via event system
                event_system.emit('tts_audio_ready', {
                    'device_id': self.device_id,
                    'audio_data': chunk,
                    'use_raw_pcm': self.use_raw_pcm
                })
            else:
                # Log warning if no device ID is provided
                logger.warning("No device_id provided, unable to send TTS audio")

            # Brief sleep to control send rate
            time.sleep(0.005)  # 5ms to control flow, adjustable as needed

        return len(audio_data)

    def close(self) -> None:
        self.wf.close()

        # Send TTS completion event
        if self.device_id:
            event_system.emit('tts_completed', {
                'device_id': self.device_id
            })
            logger.debug(f"Sent TTS completion signal to device: {self.device_id}")

        # self.stream.stop_stream()
        # self.stream.close()
        # self.pa.terminate()
class TTSManager:
    def __init__(self, response_queue=None, device_id=None):
        """
        Initialize TTS component

        Args:
            response_queue: Text input queue (backward compatible, optional)
            device_id: Device ID for obtaining device-specific configuration
        """
        self.stop_event = threading.Event()
        self.response_queue = response_queue
        self.device_id = device_id
        self.region = unified_config.get("TTS.azure.region")
        self.sentence_end_chars = ['.', '!', '?', '。', '！', '？']  # Sentence end markers
        self.sentences_per_batch = 2

        # Audio transmission format control - centralized decision on raw PCM usage
        # Default is True, indicating raw PCM instead of Opus encoding
        self.use_raw_pcm = True
        logger.info(f"TTS audio transmission mode: {'Raw PCM' if self.use_raw_pcm else 'Opus encoding'}")

        # Azure TTS configuration
        self.speech_config = speechsdk.SpeechConfig(
            subscription=unified_config.get("TTS.azure.api_key"), region=unified_config.get("TTS.azure.region")
        )
        self.speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Raw24Khz16BitMonoPcm
        )
        # Obtain model ID from device configuration or constant configuration
        if device_id:
            model_id = unified_config.get("TTS.model_id", "zh-CN-XiaoxiaoNeural", device_id=device_id)
            language = unified_config.get("system.language", "zh-CN", device_id=device_id)
        else:
            # Use constant configuration if no device_id
            try:
                model_id = unified_config.get("TTS.model_id", "zh-CN-XiaoxiaoNeural")
                language = unified_config.get("system.language", "zh-CN")
            except Exception as e:
                logger.warning(f"Failed to obtain constant configuration, using default values: {e}")
                model_id = "zh-CN-XiaoxiaoNeural"
                language = "zh-CN"

        self.speech_config.speech_synthesis_voice_name = model_id
        self.audio_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=True)
        self.speech_synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=self.speech_config, audio_config=self.audio_config
        )

        # **Warm up WebSocket, avoid first request delay**
        self.speech_synthesizer.speak_ssml_async(f"""
        <speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='{language}'>
          <voice name='{model_id}'>
            <break time='100ms'/>
          </voice>
        </speak>
        """).get()

        self.preload_tts_engine()

        logger.info("TTS Manager initialized successfully")

    def filter_text_for_tts(self, text):
        """
        Filter special symbols unfriendly to TTS in text

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
            ('#', ''),  # Replace hash with Chinese description
            ('$', ''), # Replace dollar symbol
            ('---', ''),  # Remove separators
            ('```', ''),  # Remove code blocks
        ]

        # Apply replacement rules
        filtered_text = text
        for old, new in replacements:
            filtered_text = filtered_text.replace(old, new)

        # Remove consecutive spaces
        filtered_text = ' '.join(filtered_text.split())

        return filtered_text

    def text_to_speech(self, text, save_to_file=True, device_id=None, use_raw_pcm=None):
        """
        Use SSML to directly play complete text, blocking until playback is complete

        Args:
            text: Text content to play
            save_to_file: Whether to save audio file, True uses auto filename, string specifies file path
            device_id: Device ID for sending audio via UDP
            use_raw_pcm: Whether to use raw PCM transmission, if None use class settings

        Returns:
            bool: Whether playback was successful
        """
        if not text or text.strip() == "":
            logger.warning("Attempting to play empty text")
            return False

        # Temporarily update PCM transmission mode if use_raw_pcm parameter is provided
        original_pcm_mode = self.use_raw_pcm
        if use_raw_pcm is not None:
            # Temporarily change PCM mode
            self.use_raw_pcm = use_raw_pcm
            logger.debug(f"Temporarily set PCM transmission mode: {'Raw PCM' if use_raw_pcm else 'Opus encoding'}")

        # Filter special symbols
        start_time = time.time()
        filtered_text = self.filter_text_for_tts(text)

        logger.info(f"Playing text: {filtered_text[:30]}...")
        if device_id:
            logger.info(f"Sending TTS audio to device via UDP: {device_id}, using {'Raw PCM' if self.use_raw_pcm else 'Opus encoding'}")

        # Stop current playback and clear queue
        self.stop_tts()

        # Obtain language and model configuration, use constant configuration if no device_id
        if self.device_id:
            language = unified_config.get("system.language", "zh-CN", device_id=self.device_id)
            model_id = unified_config.get("TTS.model_id", "zh-CN-XiaoxiaoNeural", device_id=self.device_id)
        else:
            # Use constant configuration if no device_id
            try:
                language = unified_config.get("system.language", "zh-CN")
                model_id = unified_config.get("TTS.model_id", "zh-CN-XiaoxiaoNeural")
            except Exception as e:
                logger.warning(f"Failed to obtain constant configuration, using default values: {e}")
                language = "zh-CN"
                model_id = "zh-CN-XiaoxiaoNeural"

        # Generate SSML format text
        ssml_text = f"""
        <speak xmlns="http://www.w3.org/2001/10/synthesis"
            xmlns:mstts="http://www.w3.org/2001/mstts"
            xmlns:emo="http://www.w3.org/2009/10/emotionml"
            version="1.0" xml:lang="{language}">
            <voice name="{model_id}"
                commasilence-exact="100ms" semicolonsilence-exact="100ms" enumerationcommasilence-exact="100ms">
                <mstts:express-as style="chat-casual" styledegree="0.5">
                    <lang xml:lang="{language}">
                        <prosody rate="+23.00%" pitch="+5.00%">{filtered_text}</prosody>
                    </lang>
                </mstts:express-as><s />
            </voice>
        </speak>
        """

        try:
            # Configure audio output (file + speaker)
            if save_to_file:
                # Determine file name
                file_path = save_to_file if isinstance(save_to_file, str) else f"tts_{int(time.time())}.pcm"

                # Create dual output stream, pass device ID and PCM transmission mode
                callback = FileAndSpeakerCallback(file_path, sample_rate=24000, device_id=device_id, use_raw_pcm=self.use_raw_pcm)
                push_stream = speechsdk.audio.PushAudioOutputStream(callback)
                audio_config = speechsdk.audio.AudioOutputConfig(stream=push_stream)

                # Create temporary synthesizer
                temp_synthesizer = speechsdk.SpeechSynthesizer(
                    speech_config=self.speech_config,
                    audio_config=audio_config
                )

                # Play using temporary synthesizer
                result = temp_synthesizer.speak_ssml_async(ssml_text).get()
                callback.close()
            else:
                # Use default speaker
                result = self.speech_synthesizer.speak_ssml_async(ssml_text).get()

            # Record total delay
            total_time = time.time() - start_time
            logger.debug(f"Total TTS delay: {total_time:.2f} seconds")

            # Check playback result
            success = result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted
            if success:
                logger.debug("Speech synthesis completed")
            else:
                logger.error(f"Speech synthesis failed: {result.reason}")

            # Restore original PCM mode
            if use_raw_pcm is not None:
                self.use_raw_pcm = original_pcm_mode
                logger.debug(f"Restored PCM transmission mode: {'Raw PCM' if self.use_raw_pcm else 'Opus encoding'}")

            return success

        except Exception as e:
            logger.error(f"TTS playback error: {e}")

            # Ensure original PCM mode is restored even if an error occurs
            if use_raw_pcm is not None:
                self.use_raw_pcm = original_pcm_mode
                logger.debug(f"恢复PCM传输模式: {'原始PCM' if self.use_raw_pcm else 'Opus编码'}")

        return False

    def stop_tts(self):
        """Stop current TTS playback"""
        logger.debug('Stopping TTS playback')

        # Set stop flag
        self.stop_event.set()

        # Clear audio queue (for backward compatibility)
        if self.response_queue:
            try:
                while not self.response_queue.empty():
                    try:
                        self.response_queue.get_nowait()
                    except:
                        pass
            except Exception as e:
                logger.error(f"Error clearing queue: {e}")

        # Force stop ongoing speech synthesis
        try:
            self.speech_synthesizer.stop_speaking_async().get()
            logger.debug("Ongoing speech synthesis stopped")
        except Exception as e:
            logger.warning(f"Error stopping speech synthesis: {e}")

        # Wait briefly to ensure stop operation takes effect
        time.sleep(0.1)

        # Reset stop event for future restarts
        self.stop_event.clear()

        logger.debug("TTS successfully stopped")
        return True

    def preload_tts_engine(self):
        """
        Preheat TTS engine to reduce initial request delay
        """
        logger.info("Preheating TTS engine...")
        # Preheat several commonly used languages
        warmup_texts = [
            "你好，我是语音助手。",
            "Hello, I am a voice assistant.",  # English
            "1234567890"  # Numbers
        ]

        # Get language and model configuration, use constant configuration if no device_id
        if self.device_id:
            language = unified_config.get("system.language", "zh-CN", device_id=self.device_id)
            model_id = unified_config.get("TTS.model_id", "zh-CN-XiaoxiaoNeural", device_id=self.device_id)
        else:
            # If no device_id, use constant configuration
            language = unified_config.get("system.language", "zh-CN")
            model_id = unified_config.get("TTS.model_id", "zh-CN-XiaoxiaoNeural")

        for text in warmup_texts:
            try:
                simple_ssml = f"""
                <speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='{language}'>
                  <voice name='{model_id}'>
                    <prosody volume="-100%" rate="+100%">{text}</prosody>
                  </voice>
                </speak>
                """
                # Use low priority for preheating
                self.speech_synthesizer.speak_ssml_async(simple_ssml).get()
                logger.debug(f"Preheated text: {text}")
            except:
                pass

        logger.info("TTS engine preheating completed")
# **Test Code**
if __name__ == "__main__":
    # Test 1: Directly use the text_to_speech method, default PCM mode
    logger.info("Test 1: Directly use the text_to_speech method, default PCM mode")
    tts_manager = TTSManager()
    logger.info(f"Current PCM mode: {'Raw PCM' if tts_manager.use_raw_pcm else 'Opus encoding'}")
    tts_manager.text_to_speech("This is a test using the default PCM mode.", save_to_file="test_default_pcm.pcm")

    # Test 2: Temporarily switch to Opus mode
    logger.info("Test 2: Temporarily switch to Opus mode")
    logger.info(f"PCM mode before switching: {'Raw PCM' if tts_manager.use_raw_pcm else 'Opus encoding'}")
    tts_manager.text_to_speech("This is a test temporarily switching to Opus mode.", save_to_file="test_opus.pcm", use_raw_pcm=False)
    logger.info(f"PCM mode after switching: {'Raw PCM' if tts_manager.use_raw_pcm else 'Opus encoding'}")

    # Test 3: Globally switch PCM mode
    logger.info("Test 3: Globally switch PCM mode")
    tts_manager.use_raw_pcm = False
    logger.info(f"PCM mode after global switching: {'Raw PCM' if tts_manager.use_raw_pcm else 'Opus encoding'}")
    tts_manager.text_to_speech("This is a test globally switching to Opus mode.", save_to_file="test_global_opus.pcm")

    # Test 4: Temporarily switch back to PCM mode
    logger.info("Test 4: Temporarily switch back to PCM mode")
    logger.info(f"PCM mode before switching: {'Raw PCM' if tts_manager.use_raw_pcm else 'Opus encoding'}")
    tts_manager.text_to_speech("This is a test temporarily switching back to PCM mode.", save_to_file="test_back_to_pcm.pcm", use_raw_pcm=True)
    logger.info(f"PCM mode after switching: {'Raw PCM' if tts_manager.use_raw_pcm else 'Opus encoding'}")

    logger.info("All tests completed!")