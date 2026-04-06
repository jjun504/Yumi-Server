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
