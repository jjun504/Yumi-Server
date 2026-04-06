import sounddevice as sd
import numpy as np
import wave
from unified_config import unified_config
import os
from loguru import logger
import time
import sys

# Add the directory where server.py is located to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from event_system import event_system

flag = 0

# Original play function - directly play audio using sounddevice
# Commented out but kept the original implementation for recovery if needed

# def play(filename, volume=int(config.get("audio_settings.general_volume"))/100, samplerate=None):
#     global flag
#     if flag == 1:
#         return
#     flag = 1

#     try:
#         _, ext = os.path.splitext(filename)

#         # If file is WAV format
#         if ext.lower() == ".wav":
#             with wave.open(filename, 'rb') as wf:
#                 # Get original WAV file parameters
#                 file_samplerate = wf.getframerate()
#                 channels = wf.getnchannels()
#                 sampwidth = wf.getsampwidth()

#                 # Read audio data
#                 samples = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)

#                 # If stereo, ensure channels are handled correctly
#                 if channels == 2:
#                     samples = samples.reshape(-1, 2)

#         # If file is PCM format
#         elif ext.lower() == ".raw":
#             # Default PCM parameters: 16-bit, 16kHz, mono
#             file_samplerate = 16000 if samplerate is None else samplerate
#             channels = 1

#             # Read PCM file
#             with open(filename, 'rb') as pcm_file:
#                 pcm_data = pcm_file.read()

#             # Convert to numpy array (assuming 16-bit PCM)
#             samples = np.frombuffer(pcm_data, dtype=np.int16)

#             # Log debug information
#             logger.debug(f"PCM file size: {len(pcm_data)} bytes")
#             logger.debug(f"PCM sample count: {len(samples)}")
#             logger.debug(f"PCM duration: {len(samples)/file_samplerate:.2f} seconds")

#         # If file is raw PCM format
#         elif ext.lower() == ".pcm":
#             samples = np.fromfile(filename, dtype=np.int16)
#             file_samplerate = 24000 if samplerate is None else samplerate
#             channels = 1  # Assume mono
#         else:
#             raise ValueError(f"Unsupported file type: {ext}")

#         # Use original file sample rate unless specifically specified
#         actual_samplerate = file_samplerate if samplerate is None else samplerate

#         # Add a short silence segment to the end of the audio to prevent truncation
#         silence_samples = np.zeros(int(actual_samplerate * 0.2), dtype=np.int16)  # 200ms silence
#         if len(samples.shape) > 1 and samples.shape[1] == 2:  # Stereo
#             silence_shape = (len(silence_samples), 2)
#             silence_samples = np.zeros(silence_shape, dtype=np.int16)

#         # Concatenate original audio and silence segment
#         samples_with_padding = np.concatenate((samples, silence_samples))

#         # Calculate actual playback duration (seconds)
#         duration = len(samples_with_padding) / actual_samplerate

#         # Adjust volume (ensure no overflow)
#         normalized_samples = samples_with_padding.astype(np.float32) / np.iinfo(np.int16).max
#         volume_adjusted = (normalized_samples * volume * np.iinfo(np.int16).max).astype(np.int16)

#         # Play audio
#         logger.debug(f"Playing audio file {filename}")
#         logger.debug(f"Original sample rate: {file_samplerate}Hz")
#         logger.debug(f"Actual playback sample rate: {actual_samplerate}Hz")
#         logger.debug(f"Number of channels: {channels}")
#         logger.debug(f"Volume: {volume}")
#         logger.debug(f"Duration with padding: {duration:.2f}s")

#         # 使用阻塞模式播放
#         sd.play(volume_adjusted, samplerate=actual_samplerate, blocking=False)

#         # 计算实际需要等待的时间
#         wait_time = duration + 0.1  # 加上额外的100ms安全边界

#         # 手动等待播放完成，并确保最后的音频被播放
#         start_time = time.time()
#         while sd.get_stream().active and (time.time() - start_time) < wait_time:
#             time.sleep(0.01)  # 短暂睡眠，减少CPU使用

#         # 确保播放完全结束
#         sd.stop()

#     except Exception as e:
#         logger.error(f"Error playing {filename}: {e}")
#     finally:
#         flag = 0


# New play function - send audio to client using event system
def play(filename, device_id=None, volume=None, samplerate=None):
    """
    Play audio file or send it to the client via the event system

    Args:
        filename: Path to the audio file
        volume: Volume level (0.0-1.0), if None, it will be fetched from the configuration
        samplerate: Sampling rate, if None, the original file sampling rate will be used
        device_id: Target device ID, if provided, the audio will be sent to the specific device via the event system
    """
    global flag
    if flag == 1:
        return
    flag = 1

    # If volume is not provided, fetch the default value from the configuration
    if volume is None:
        volume = int(unified_config.get("audio_settings.general_volume", 70, device_id=device_id)) / 100

    try:
        _, ext = os.path.splitext(filename)

        # If file is WAV format
        if ext.lower() == ".wav":
            with wave.open(filename, 'rb') as wf:
                # Get original WAV file parameters
                file_samplerate = wf.getframerate()
                channels = wf.getnchannels()

                # Read audio data
                samples = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)

                # If stereo, ensure channels are handled correctly
                if channels == 2:
                    samples = samples.reshape(-1, 2)

        # If file is PCM format
        elif ext.lower() == ".raw":
            # Default PCM parameters: 16-bit, 16kHz, mono
            file_samplerate = 16000 if samplerate is None else samplerate
            channels = 1

            # Read PCM file
            with open(filename, 'rb') as pcm_file:
                pcm_data = pcm_file.read()

            # Convert to numpy array (assuming 16-bit PCM)
            samples = np.frombuffer(pcm_data, dtype=np.int16)

            # Log debug information
            logger.debug(f"PCM file size: {len(pcm_data)} bytes")
            logger.debug(f"PCM sample count: {len(samples)}")
            logger.debug(f"PCM duration: {len(samples)/file_samplerate:.2f} seconds")

        # If file is raw PCM format
        elif ext.lower() == ".pcm":
            samples = np.fromfile(filename, dtype=np.int16)
            file_samplerate = 24000 if samplerate is None else samplerate
            channels = 1  # Assume mono
        else:
            raise ValueError(f"Unsupported file type: {ext}")

        # Use original file sample rate unless specifically specified
        actual_samplerate = file_samplerate if samplerate is None else samplerate

        # Add a short silence segment to the end of the audio to prevent truncation
        silence_samples = np.zeros(int(actual_samplerate * 0.2), dtype=np.int16)  # 200ms silence
        if len(samples.shape) > 1 and samples.shape[1] == 2:  # Stereo
            silence_shape = (len(silence_samples), 2)
            silence_samples = np.zeros(silence_shape, dtype=np.int16)

        # Concatenate original audio and silence segment
        samples_with_padding = np.concatenate((samples, silence_samples))

        # Calculate actual playback duration (seconds)
        duration = len(samples_with_padding) / actual_samplerate

        # Adjust volume (ensure no overflow)
        normalized_samples = samples_with_padding.astype(np.float32) / np.iinfo(np.int16).max
        volume_adjusted = (normalized_samples * volume * np.iinfo(np.int16).max).astype(np.int16)

        # Prepare audio data
        audio_data = volume_adjusted.tobytes()

        # Check if device ID and event system are available
        if device_id:
            # Send audio to the specific device via the event system
            logger.info(f"Sending audio to device via event system: {device_id}")

            # Use event system to send audio data
            event_system.emit('tts_audio_ready', {
                'device_id': device_id,
                'audio_data': audio_data,
                'use_raw_pcm': True  # Use raw PCM format
            })

            logger.debug(f"Audio file {filename} sent to device {device_id} via event system")
            logger.debug(f"Sample rate: {actual_samplerate}Hz, Channels: {channels}, Volume: {volume}")

        else:
            # Local audio playback
            logger.debug(f"Playing audio file locally: {filename}")
            logger.debug(f"Sample rate: {actual_samplerate}Hz, Channels: {channels}, Volume: {volume}")

            # Play in blocking mode
            sd.play(volume_adjusted, samplerate=actual_samplerate, blocking=False)

            # Calculate actual wait time
            wait_time = duration + 0.1  # Add an extra 100ms safety margin

            # Manually wait for playback to complete and ensure the final audio is played
            start_time = time.time()
            while sd.get_stream().active and (time.time() - start_time) < wait_time:
                time.sleep(0.01)  # Short sleep to reduce CPU usage

            # Ensure playback is completely finished
            sd.stop()

    except Exception as e:
        logger.error(f"Error playing {filename}: {e}")
    finally:
        flag = 0

if __name__ == "__main__":
    # Test code
    # Local playback test
    print("Local playback test...")
    play("test_output_converted.pcm", volume=0.8, samplerate=32000)

    # Event system sending test
    print("\nEvent system sending test...")
    # Send audio to the specified device via the event system
    # play("user/user001/rasp1/chat_history/audio/20250502_164656.pcm", volume=0.8, samplerate=16000, device_id="rasp1")
    print("Audio sent to device via event system: rasp1")

    # Other test files
    # play("sound/time_notify.wav")
    # play("sound/schedule_notification.wav")
    # play("sound/pvwake.wav")
    # play("sound/chatend.wav")
    # play("sound/chatnext.wav")
    # play("sound/test.pcm", samplerate=24000)
    # play("sound/end.pcm", volume=0.8, samplerate=24000)
    # play("sound/time_notify/chinese/time12.pcm", volume=0.8, samplerate=24000)
    # play("sound/volcano/ans_1743179142.pcm", volume=0.8, samplerate=24000)
    # play("sound/volcano/20250419_162033.pcm", volume=0.8, samplerate=24000)
    # play("sound/volcano/ans_1743179087.pcm", volume=0.8, samplerate=24000)