#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fast Audio Resampling Module

Specifically designed for GPT-SoVITS real-time resampling from 32kHz to 24kHz.
Uses scipy.signal.resample_poly for high-speed resampling.
"""

import io
import numpy as np
import soundfile as sf
import scipy.signal
from typing import Optional
from loguru import logger

class FastResampler:
    """Fast audio resampler"""

    def __init__(self, source_sr=32000, target_sr=24000):
        """
        Initialize the fast resampler

        Args:
            source_sr (int): Source sample rate, default is 32000Hz (GPT-SoVITS)
            target_sr (int): Target sample rate, default is 24000Hz (system standard)
        """
        self.source_sr = source_sr
        self.target_sr = target_sr

        # Precompute resampling parameters
        from math import gcd
        common_divisor = gcd(source_sr, target_sr)
        self.up_factor = target_sr // common_divisor
        self.down_factor = source_sr // common_divisor

        logger.info(f"Fast resampler initialized: {source_sr}Hz -> {target_sr}Hz")
        logger.debug(f"Resampling parameters: upsample={self.up_factor}, downsample={self.down_factor}")

    def resample_audio_data(self, audio_data: np.ndarray) -> np.ndarray:
        """
        Fast resample audio data

        Args:
            audio_data (np.ndarray): Input audio data

        Returns:
            np.ndarray: Resampled audio data
        """
        if self.source_sr == self.target_sr:
            return audio_data

        # Use scipy for fast resampling
        resampled = scipy.signal.resample_poly(
            audio_data,
            self.up_factor,
            self.down_factor
        )

        return resampled.astype(audio_data.dtype)

    def resample_wav_chunk(self, wav_chunk: bytes) -> Optional[bytes]:
        """
        Resample WAV audio chunk

        Args:
            wav_chunk (bytes): Audio data in WAV format

        Returns:
            bytes: Resampled WAV data, returns None on failure
        """
        try:
            # Read audio from memory
            audio_io = io.BytesIO(wav_chunk)
            audio_data, detected_sr = sf.read(audio_io)

            # Verify sample rate
            if detected_sr != self.source_sr:
                logger.warning(f"Detected sample rate {detected_sr}Hz does not match expected {self.source_sr}Hz")
                # Dynamically adjust resampling parameters
                from math import gcd
                common_divisor = gcd(detected_sr, self.target_sr)
                up_factor = self.target_sr // common_divisor
                down_factor = detected_sr // common_divisor

                resampled_audio = scipy.signal.resample_poly(
                    audio_data, up_factor, down_factor
                )
            else:
                # Use precomputed parameters
                resampled_audio = self.resample_audio_data(audio_data)

            # Write back to WAV format
            output_io = io.BytesIO()
            sf.write(output_io, resampled_audio, self.target_sr, format='WAV')
            output_io.seek(0)

            return output_io.read()

        except Exception as e:
            logger.error(f"WAV resampling failed: {e}")
            return None

    def resample_pcm_chunk(self, pcm_chunk: bytes, sample_width=2, channels=1) -> Optional[bytes]:
        """
        Resample PCM audio chunk

        Args:
            pcm_chunk (bytes): PCM audio data
            sample_width (int): Sample width (bytes)
            channels (int): Number of channels

        Returns:
            bytes: Resampled PCM data, returns None on failure
        """
        try:
            # Convert PCM to numpy array
            if sample_width == 2:
                dtype = np.int16
                max_val = 32767
            elif sample_width == 4:
                dtype = np.int32
                max_val = 2147483647
            else:
                dtype = np.int16
                max_val = 32767

            # Parse PCM data
            audio_array = np.frombuffer(pcm_chunk, dtype=dtype)

            # Handle multi-channel (convert to mono)
            if channels > 1:
                audio_array = audio_array.reshape(-1, channels)
                audio_array = np.mean(audio_array, axis=1)

            # Normalize to [-1, 1]
            audio_float = audio_array.astype(np.float32) / max_val

            # Fast resampling
            resampled_audio = self.resample_audio_data(audio_float)

            # Convert back to integer format
            resampled_int = (resampled_audio * max_val).astype(dtype)

            return resampled_int.tobytes()

        except Exception as e:
            logger.error(f"PCM resampling failed: {e}")
            return None

# Global resampler instance
_global_resampler = None

def get_resampler(source_sr=32000, target_sr=24000) -> FastResampler:
    """
    Get global resampler instance

    Args:
        source_sr (int): Source sample rate
        target_sr (int): Target sample rate

    Returns:
        FastResampler: Resampler instance
    """
    global _global_resampler

    if (_global_resampler is None or
        _global_resampler.source_sr != source_sr or
        _global_resampler.target_sr != target_sr):
        _global_resampler = FastResampler(source_sr, target_sr)

    return _global_resampler

def resample_gpt_sovits_audio(audio_data: bytes, format_type='wav') -> Optional[bytes]:
    """
    Convenient function for resampling GPT-SoVITS audio

    Args:
        audio_data (bytes): Audio data output from GPT-SoVITS
        format_type (str): Audio format ('wav' or 'pcm')

    Returns:
        bytes: Resampled audio data, returns None on failure
    """
    resampler = get_resampler(32000, 24000)

    if format_type.lower() == 'wav':
        return resampler.resample_wav_chunk(audio_data)
    elif format_type.lower() == 'pcm':
        return resampler.resample_pcm_chunk(audio_data)
    else:
        logger.error(f"Unsupported audio format: {format_type}")
        return None