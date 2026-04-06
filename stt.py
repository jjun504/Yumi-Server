import time
from dotenv import load_dotenv
# pip install azure-cognitiveservices-speech
import azure.cognitiveservices.speech as speechsdk
from unified_config import unified_config
from loguru import logger
load_dotenv()


class AzureSTTModule:
    def __init__(self, device_id=None):
        """
        Initialize Azure STT module

        Args:
            device_id: Device ID for fetching device-specific configurations
        """
        self.device_id = device_id
        self.api_key = unified_config.get("STT.azure.api_key")
        self.region = unified_config.get("STT.azure.region")
        self.speech_config = speechsdk.SpeechConfig(subscription=self.api_key, region=self.region)
        
        # Set profanity filtering
        self.speech_config.set_profanity(speechsdk.ProfanityOption.Masked)
        
        self.speech_recognizer = None
        self.recognition_running = False
        logger.info("[Initialize][SpeechRecognition] Speech Recognition Module initialized successfully")

    def stop_stt(self):
        """Stop current speech recognition"""
        if self.speech_recognizer and self.recognition_running:
            logger.debug("Forcibly stopping speech recognition...")
            try:
                self.recognition_running = False  # Change flag first
                self.speech_recognizer.stop_continuous_recognition()
                
                # Wait enough time to ensure resource release
                time.sleep(0.5)
                
                # Explicitly release resources
                self.speech_recognizer = None
                
                logger.info("Speech recognition stopped and resources released")
            except Exception as e:
                logger.error(f"Error stopping speech recognition: {e}")
                # Force cleanup
                self.speech_recognizer = None

    def speech_to_text(self):
        # Recreate recognizer to ensure clean state
        language = unified_config.get("STT.language", "zh-CN", device_id=self.device_id)
        self.speech_config.speech_recognition_language = language
        
        # Apply profanity filtering settings
        self.speech_config.set_profanity(speechsdk.ProfanityOption.Masked)
        
        # Create audio configuration
        audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
        
        # Create speech recognizer
        self.speech_recognizer = speechsdk.SpeechRecognizer(
            speech_config=self.speech_config, 
            audio_config=audio_config
        )
        
        self.recognition_running = True
        
        # Set timeout parameters
        self.speech_recognizer.properties.set_property(speechsdk.PropertyId.SpeechServiceConnection_InitialSilenceTimeoutMs, "5000")
        self.speech_recognizer.properties.set_property(speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs, "600")
        self.speech_recognizer.properties.set_property(speechsdk.PropertyId.Speech_SegmentationSilenceTimeoutMs, "800")
        
        done = False
        recognized_text = []

        logger.info("[Speech Recognition] Listening...")

        def handle_result(evt):
            if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
                print()
                logger.success(f"[Speech Recognition] Final recognition result: {evt.result.text}")
                recognized_text.append(evt.result.text)
                nonlocal done
                done = True

        def handle_recognizing(evt):
            print(f"\rRecognizing: {evt.result.text}", end="", flush=True)

        def stop_cb(evt):
            logger.debug('Stopping recognition...')
            nonlocal done
            done = True

        def handle_canceled(evt):
            logger.debug(f'\nRecognition cancelled: {evt.reason}')
            if evt.reason == speechsdk.CancellationReason.Error:
                logger.error(f'Error details: {evt.error_details}')
            nonlocal done
            done = True

        # Connect event handlers
        self.speech_recognizer.recognized.connect(handle_result)
        self.speech_recognizer.recognizing.connect(handle_recognizing)
        self.speech_recognizer.session_stopped.connect(stop_cb)
        self.speech_recognizer.canceled.connect(handle_canceled)

        # Start streaming recognition
        self.speech_recognizer.start_continuous_recognition()
        while not done and self.recognition_running:
            time.sleep(0.05)

        # Stop recognition
        if self.recognition_running:
            self.speech_recognizer.stop_continuous_recognition()
            self.recognition_running = False
            
        logger.debug("Speech recognition ended")
        return " ".join(recognized_text)

    # once recognition
        # if speech_recognition_result.reason == speechsdk.ResultReason.RecognizedSpeech:
        #     print("Recognize: ", speech_recognition_result.text) # print
        #     return speech_recognition_result.text
        # elif speech_recognition_result.reason == speechsdk.ResultReason.NoMatch:
        #     print("No speech could be recognized: {}".format(speech_recognition_result.no_match_details))
        #     return None
        # elif speech_recognition_result.reason == speechsdk.ResultReason.Canceled:
        #     cancellation_details = speech_recognition_result.cancellation_details
        #     print("Speech Recognition canceled: {}".format(cancellation_details.reason))
        #     if cancellation_details.reason == speechsdk.CancellationReason.Error:
        #         print("Error details: {}".format(cancellation_details.error_details))
        #         print("Did you set the speech resource key and region values?")
        #     return None


if __name__ == "__main__":
    azure_stt_module = AzureSTTModule()
    import threading
    
    # Test 1: Start recognition in thread
    print("Test 1: Starting recognition in thread")
    recognition_thread = threading.Thread(target=azure_stt_module.speech_to_text, daemon=True)
    recognition_thread.start()
    
    # Wait 5 seconds then stop
    time.sleep(5)
    azure_stt_module.stop_stt()
    print("First recognition stopped")
    
    # Wait to ensure complete stop
    time.sleep(2)
    
    # Test 2: Direct recognition call
    print("\nTest 2: Direct recognition call")
    text = azure_stt_module.speech_to_text()
    print(f"Final recognition result: {text}")