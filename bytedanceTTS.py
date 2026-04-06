import asyncio
import json
import uuid
import threading
import time  # Ensure time module is imported
import numpy as np
import sounddevice as sd
from websockets.exceptions import ConnectionClosed

from unified_config import unified_config
import aiofiles
import websocket
import websockets
from websockets.asyncio.client import ClientConnection
# from play import play  # No longer use play directly, use event system instead
import os
import sys
from loguru import logger
# https://www.volcengine.com/docs/6561/1329505#%E7%A4%BA%E4%BE%8Bsamples

# Add server.py directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import event system
from event_system import event_system

PROTOCOL_VERSION = 0b0001
DEFAULT_HEADER_SIZE = 0b0001

# Message Type:
FULL_CLIENT_REQUEST = 0b0001
AUDIO_ONLY_RESPONSE = 0b1011
FULL_SERVER_RESPONSE = 0b1001
ERROR_INFORMATION = 0b1111

# Message Type Specific Flags
MsgTypeFlagNoSeq = 0b0000  # Non-terminal packet with no sequence
MsgTypeFlagPositiveSeq = 0b1  # Non-terminal packet with sequence > 0
MsgTypeFlagLastNoSeq = 0b10  # last packetba with no sequence
MsgTypeFlagNegativeSeq = 0b11  # Payload contains event number (int32)
MsgTypeFlagWithEvent = 0b100
# Message Serialization
NO_SERIALIZATION = 0b0000
JSON = 0b0001
# Message Compression
COMPRESSION_NO = 0b0000
COMPRESSION_GZIP = 0b0001

EVENT_NONE = 0
EVENT_Start_Connection = 1

EVENT_FinishConnection = 2

EVENT_ConnectionStarted = 50  # Connection established successfully

EVENT_ConnectionFailed = 51  # Connection failed (possibly unable to pass authentication)

EVENT_ConnectionFinished = 52  # Connection ended

# Upstream Session events
EVENT_StartSession = 100

EVENT_FinishSession = 102
# Downstream Session events
EVENT_SessionStarted = 150
EVENT_SessionFinished = 152

EVENT_SessionFailed = 153

# Upstream general events
EVENT_TaskRequest = 200

# Downstream TTS events
EVENT_TTSSentenceStart = 350

EVENT_TTSSentenceEnd = 351

EVENT_TTSResponse = 352


class Header:
    def __init__(self,
                 protocol_version=PROTOCOL_VERSION,
                 header_size=DEFAULT_HEADER_SIZE,
                 message_type: int = 0,
                 message_type_specific_flags: int = 0,
                 serial_method: int = NO_SERIALIZATION,
                 compression_type: int = COMPRESSION_NO,
                 reserved_data=0):
        self.header_size = header_size
        self.protocol_version = protocol_version
        self.message_type = message_type
        self.message_type_specific_flags = message_type_specific_flags
        self.serial_method = serial_method
        self.compression_type = compression_type
        self.reserved_data = reserved_data

    def as_bytes(self) -> bytes:
        return bytes([
            (self.protocol_version << 4) | self.header_size,
            (self.message_type << 4) | self.message_type_specific_flags,
            (self.serial_method << 4) | self.compression_type,
            self.reserved_data
        ])


class Optional:
    def __init__(self, event: int = EVENT_NONE, sessionId: str = None, sequence: int = None):
        self.event = event
        self.sessionId = sessionId
        self.errorCode: int = 0
        self.connectionId: str | None = None
        self.response_meta_json: str | None = None
        self.sequence = sequence

    # Convert to byte sequence
    def as_bytes(self) -> bytes:
        option_bytes = bytearray()
        if self.event != EVENT_NONE:
            option_bytes.extend(self.event.to_bytes(4, "big", signed=True))
        if self.sessionId is not None:
            session_id_bytes = str.encode(self.sessionId)
            size = len(session_id_bytes).to_bytes(4, "big", signed=True)
            option_bytes.extend(size)
            option_bytes.extend(session_id_bytes)
        if self.sequence is not None:
            option_bytes.extend(self.sequence.to_bytes(4, "big", signed=True))
        return option_bytes


class Response:
    def __init__(self, header: Header, optional: Optional):
        self.optional = optional
        self.header = header
        self.payload: bytes | None = None

    def __str__(self):
        return super().__str__()


# Send event
async def send_event(ws: websocket, header: bytes, optional: bytes | None = None,
                     payload: bytes = None):
    full_client_request = bytearray(header)
    if optional is not None:
        full_client_request.extend(optional)
    if payload is not None:
        payload_size = len(payload).to_bytes(4, 'big', signed=True)
        full_client_request.extend(payload_size)
        full_client_request.extend(payload)
    await ws.send(full_client_request)


# Read string content from res array segment
def read_res_content(res: bytes, offset: int):
    content_size = int.from_bytes(res[offset: offset + 4])
    offset += 4
    content = str(res[offset: offset + content_size])
    offset += content_size
    return content, offset


# Read payload
def read_res_payload(res: bytes, offset: int):
    payload_size = int.from_bytes(res[offset: offset + 4])
    offset += 4
    payload = res[offset: offset + payload_size]
    offset += payload_size
    return payload, offset


# Parse response result
def parser_response(res) -> Response:
    if isinstance(res, str):
        raise RuntimeError(res)
    response = Response(Header(), Optional())
    # Parse result
    # header
    header = response.header
    num = 0b00001111
    header.protocol_version = res[0] >> 4 & num
    header.header_size = res[0] & 0x0f
    header.message_type = (res[1] >> 4) & num
    header.message_type_specific_flags = res[1] & 0x0f
    header.serial_method = res[2] >> num
    header.compression_type = res[2] & 0x0f
    header.reserved_data = res[3]
    #
    offset = 4
    optional = response.optional
    if header.message_type == FULL_SERVER_RESPONSE or AUDIO_ONLY_RESPONSE:
        # read event
        if header.message_type_specific_flags == MsgTypeFlagWithEvent:
            optional.event = int.from_bytes(res[offset:8])
            offset += 4
            if optional.event == EVENT_NONE:
                return response
            # read connectionId
            elif optional.event == EVENT_ConnectionStarted:
                optional.connectionId, offset = read_res_content(res, offset)
            elif optional.event == EVENT_ConnectionFailed:
                optional.response_meta_json, offset = read_res_content(res, offset)
            elif (optional.event == EVENT_SessionStarted
                  or optional.event == EVENT_SessionFailed
                  or optional.event == EVENT_SessionFinished):
                optional.sessionId, offset = read_res_content(res, offset)
                optional.response_meta_json, offset = read_res_content(res, offset)
            else:
                optional.sessionId, offset = read_res_content(res, offset)
                response.payload, offset = read_res_payload(res, offset)

    elif header.message_type == ERROR_INFORMATION:
        optional.errorCode = int.from_bytes(res[offset:offset + 4], "big", signed=True)
        offset += 4
        response.payload, offset = read_res_payload(res, offset)
    return response


async def run_demo(appId: str, token: str, speaker: str, text: str, output_path: str):
    ws_header = {
        "X-Api-App-Key": appId,
        "X-Api-Access-Key": token,
        "X-Api-Resource-Id": 'volc.service_type.10029',
        "X-Api-Connect-Id": uuid.uuid4(),
    }
    url = 'wss://openspeech.bytedance.com/api/v3/tts/bidirection'
    # websocket.create_connection(url,ws_header) as ws

    async with websockets.connect(url, additional_headers=ws_header, max_size=1000000000) as ws:
        await start_connection(ws)
        res = parser_response(await ws.recv())
        print_response(res, 'start_connection res:')
        if res.optional.event != EVENT_ConnectionStarted:
            raise RuntimeError("start connection failed")

        session_id = uuid.uuid4().__str__().replace('-', '')
        await start_session(ws, speaker, session_id)
        res = parser_response(await ws.recv())
        print_response(res, 'start_session res:')
        if res.optional.event != EVENT_SessionStarted:
            raise RuntimeError('start session failed!')

        # Send text
        await send_text(ws, speaker, text, session_id)
        await finish_session(ws, session_id)
        async with aiofiles.open(output_path, mode="wb") as output_file:
            while True:
                res = parser_response(await ws.recv())
                print_response(res, 'send_text res:')
                if res.optional.event == EVENT_TTSResponse and res.header.message_type == AUDIO_ONLY_RESPONSE:
                    await output_file.write(res.payload)
                elif res.optional.event in [EVENT_TTSSentenceStart, EVENT_TTSSentenceEnd]:
                    continue
                else:
                    break
        await finish_connection(ws)
        res = parser_response(await ws.recv())
        print_response(res, 'finish_connection res:')
        print('===> Exit program')


def print_response(res, tag: str):
    print(f'===>{tag} header:{res.header.__dict__}')
    print(f'===>{tag} optional:{res.optional.__dict__}')


def get_payload_bytes(uid='1234', event=EVENT_NONE, text='', speaker='ICL_zh_female_chengshujiejie_tob', audio_format="pcm",
                      audio_sample_rate=24000):
    """Generate general TTS request payload"""
    return str.encode(json.dumps(
        {
            "user": {"uid": uid},
            "event": event,
            "namespace": "BidirectionalTTS",
            "req_params": {
            "text": text,
            "speaker": speaker,
            "audio_params": {
                "format": audio_format,
                "sample_rate": audio_sample_rate,
                "speech_rate": 0,
                "additions": {
                    "disable_markdown_filter": True,
                }
            }
        }
    }
    ))

def get_pcm_payload_bytes(uid='1234', event=EVENT_NONE, text='', speaker='ICL_zh_female_chengshujiejie_tob', audio_sample_rate=24000):
    """Generate PCM format TTS request payload"""
    return str.encode(json.dumps(
        {
            "user": {"uid": uid},
            "event": event,
            "namespace": "BidirectionalTTS",
            "req_params": {
            "text": text,
            "speaker": speaker,
            "audio_params": {
                "format": "pcm",
                "sample_rate": audio_sample_rate,
                "speech_rate": 0,
                "additions": {
                    "disable_markdown_filter": True,
                }
            }
        }
    }
    ))

def get_mp3_payload_bytes(uid='1234', event=EVENT_NONE, text='', speaker='ICL_zh_female_chengshujiejie_tob', audio_sample_rate=24000):
    """Generate MP3 format TTS request payload"""
    return str.encode(json.dumps(
        {
            "user": {"uid": uid},
            "event": event,
            "namespace": "BidirectionalTTS",
            "req_params": {
            "text": text,
            "speaker": speaker,
            "audio_params": {
                "format": "mp3",
                "sample_rate": audio_sample_rate,
                "speech_rate": 0,
                "additions": {
                    "disable_markdown_filter": True,
                }
            }
        }
    }
    ))

async def start_connection(websocket):
    header = Header(message_type=FULL_CLIENT_REQUEST, message_type_specific_flags=MsgTypeFlagWithEvent).as_bytes()
    optional = Optional(event=EVENT_Start_Connection).as_bytes()
    payload = str.encode("{}")
    return await send_event(websocket, header, optional, payload)


async def start_session(websocket, speaker, session_id):
    header = Header(message_type=FULL_CLIENT_REQUEST,
                    message_type_specific_flags=MsgTypeFlagWithEvent,
                    serial_method=JSON
                    ).as_bytes()
    optional = Optional(event=EVENT_StartSession, sessionId=session_id).as_bytes()
    payload = get_payload_bytes(event=EVENT_StartSession, speaker=speaker)
    return await send_event(websocket, header, optional, payload)


async def send_text(ws: ClientConnection, speaker: str, text: str, session_id,
                   audio_format="mp3", audio_sample_rate=24000):
    header = Header(message_type=FULL_CLIENT_REQUEST,
                    message_type_specific_flags=MsgTypeFlagWithEvent,
                    serial_method=JSON).as_bytes()
    optional = Optional(event=EVENT_TaskRequest, sessionId=session_id).as_bytes()
    payload = get_payload_bytes(event=EVENT_TaskRequest, text=text, speaker=speaker,
                               audio_format=audio_format, audio_sample_rate=audio_sample_rate)

    print(f"Sending text-to-speech request: format={audio_format}, sample_rate={audio_sample_rate}Hz")
    return await send_event(ws, header, optional, payload)


async def send_pcm_text(ws: ClientConnection, speaker: str, text: str, session_id,
                   audio_sample_rate=24000):
    header = Header(message_type=FULL_CLIENT_REQUEST,
                    message_type_specific_flags=MsgTypeFlagWithEvent,
                    serial_method=JSON).as_bytes()
    optional = Optional(event=EVENT_TaskRequest, sessionId=session_id).as_bytes()
    payload = get_pcm_payload_bytes(event=EVENT_TaskRequest, text=text, speaker=speaker,
                               audio_sample_rate=audio_sample_rate)

    print(f"Sending text-to-speech request: sample_rate={audio_sample_rate}Hz")
    return await send_event(ws, header, optional, payload)

async def send_mp3_text(ws: ClientConnection, speaker: str, text: str, session_id,
                   audio_sample_rate=24000):
    header = Header(message_type=FULL_CLIENT_REQUEST,
                    message_type_specific_flags=MsgTypeFlagWithEvent,
                    serial_method=JSON).as_bytes()
    optional = Optional(event=EVENT_TaskRequest, sessionId=session_id).as_bytes()
    payload = get_mp3_payload_bytes(event=EVENT_TaskRequest, text=text, speaker=speaker,
                               audio_sample_rate=audio_sample_rate)

    print(f"Sending text-to-speech request: sample_rate={audio_sample_rate}Hz")
    return await send_event(ws, header, optional, payload)


async def finish_session(ws, session_id):
    header = Header(message_type=FULL_CLIENT_REQUEST,
                    message_type_specific_flags=MsgTypeFlagWithEvent,
                    serial_method=JSON
                    ).as_bytes()
    optional = Optional(event=EVENT_FinishSession, sessionId=session_id).as_bytes()
    payload = str.encode('{}')
    return await send_event(ws, header, optional, payload)


async def finish_connection(ws):
    header = Header(message_type=FULL_CLIENT_REQUEST,
                    message_type_specific_flags=MsgTypeFlagWithEvent,
                    serial_method=JSON
                    ).as_bytes()
    optional = Optional(event=EVENT_FinishConnection).as_bytes()
    payload = str.encode('{}')
    return await send_event(ws, header, optional, payload)


class TTSManager:
    """ByteDance TTS service manager - optimized version, streaming playback, supports long connections"""

    def __init__(self, device_id=None):
        """Initialize TTS manager

        Args:
            device_id: Device ID for getting device-specific configuration
        """
        self.device_id = device_id
        # Get configuration, prioritize constant configuration
        try:
            self.app_id = unified_config.get("TTS.bytedance.app_id")
            self.token = unified_config.get("TTS.bytedance.token")
        except Exception as e:
            logger.warning(f"Failed to get ByteDance TTS configuration, using default values: {e}")
            self.app_id = "8581367480"  # Default app_id
            self.token = "cZTrpLa61HltZ12xfWLmFOZAEKhFo3-b"  # Default token
        self.ws = None
        self.connected = False
        self.is_warmed_up = False
        self.audio_queue = None
        self.playback_active = False
        self.playback_finished = None
        self.current_device_id = None  # Store current device ID for sending audio
        self.chunk_size = 7680
        self.buffer = bytearray()

        # Audio transmission format control - centrally decide whether to use raw PCM
        # Default is True, meaning use raw PCM instead of Opus encoding
        self.use_raw_pcm = True

        # Long connection related
        self.ws_connection = None  # Persistent connection
        self.connection_lock = asyncio.Lock()  # Initialize lock directly
        self.last_used_time = 0  # Record last usage time

        # Use single event loop and thread
        self.event_loop = asyncio.new_event_loop()
        self.loop_thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self.loop_thread.start()

        # Warm up in main event loop
        asyncio.run_coroutine_threadsafe(self._warmup_connection(), self.event_loop)
        logger.info("TTS manager initialization complete, warmup started in background")

        # No longer use AudioSender, completely rely on event_system to send audio
        logger.info("TTS manager will completely use event_system to send audio")

    def filter_text_for_tts(self, text):
        """
        Filter special symbols in text that are not TTS-friendly

        Args:
            text: Original text

        Returns:
            str: Filtered text
        """
        if not text:
            return ""

        # Create replacement rules list (symbol, replacement content)
        replacements = [
            ('**', ''),  # Remove bold symbols
            ('*', ''),   # Remove asterisks
            ('_', ''),   # Remove underscores
            ('`', ''),   # Remove backticks
            ('>', ''),   # Remove quote symbols
            ('#', ''),  # Replace hash symbols
            ('$', ''), # Replace dollar symbols
            ('---', ''),  # Remove divider lines
            ('```', ''),  # Remove code blocks
        ]

        # Apply replacement rules
        filtered_text = text
        for old, new in replacements:
            filtered_text = filtered_text.replace(old, new)

        # Remove consecutive multiple spaces
        filtered_text = ' '.join(filtered_text.split())

        return filtered_text


    async def _ensure_connection_lock(self):
        """Ensure lock is initialized"""
        if self.connection_lock is None:
            self.connection_lock = asyncio.Lock()
        return self.connection_lock

    async def _ensure_connection(self):
        """Ensure long connection is valid, auto-reconnect"""
        lock = await self._ensure_connection_lock()
        async with lock:
            # Check connection status - fix closed attribute check
            if self.ws_connection:
                try:
                    # Use ping_timeout=1.0 to quickly check if connection is still available
                    pong_waiter = await self.ws_connection.ping()
                    await asyncio.wait_for(pong_waiter, timeout=1.0)

                    # Check heartbeat (send keep-alive every 5 minutes)
                    if time.time() - self.last_used_time > 300:
                        logger.debug("Sending heartbeat to keep connection active")
                        await self._send_heartbeat()
                    return True
                except (asyncio.TimeoutError, ConnectionClosed, Exception) as e:
                    logger.warning(f"Connection check failed: {e}")
                    self.ws_connection = None
                    # Continue to execute new connection creation code

            try:
                # Create new connection
                logger.info("Establishing new WebSocket long connection")
                self.ws_connection = await self.create_connection()
                if self.ws_connection:
                    self.last_used_time = time.time()
                    logger.info("WebSocket long connection established successfully")
                    return True
                logger.error("WebSocket long connection establishment failed")
                return False
            except Exception as e:
                logger.error(f"Connection rebuild failed: {e}")
                return False

    async def _send_heartbeat(self):
        """Send standard WebSocket ping as heartbeat"""
        try:
            pong_waiter = await self.ws_connection.ping()
            await asyncio.wait_for(pong_waiter, timeout=2.0)
            self.last_used_time = time.time()
            logger.debug("WebSocket ping heartbeat sent successfully")
            return True
        except Exception as e:
            logger.warning(f"Heartbeat sending failed: {e}")
            # Heartbeat failed, mark connection needs rebuild
            self.ws_connection = None
            return False

    def _warmup_in_thread(self):
        """Execute warmup in separate thread"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._warmup_connection())
            # Don't close loop: loop.close()
            self.event_loop = loop  # Save loop for later use
        except Exception as e:
            logger.warning(f"TTS warmup thread error: {e}")

    async def _warmup_connection(self):
        """Warm up WebSocket connection and maintain as long connection"""
        try:
            logger.info("Warming up TTS connection...")
            # Use long connection mechanism
            if await self._ensure_connection():
                # Use existing connection
                ws = self.ws_connection

                # Start session
                session_id = uuid.uuid4().__str__().replace('-', '')
                speaker = 'zh_female_wanwanxiaohe_moon_bigtts'

                await start_session(ws, speaker, session_id)
                res = parser_response(await ws.recv())

                if res.optional.event != EVENT_SessionStarted:
                    logger.warning("Warmup session start failed")
                    return

                # Send a very short text for warmup
                await send_text(ws, speaker, "预热", session_id)
                await finish_session(ws, session_id)

                # Receive and discard responses
                try:
                    while True:
                        res = parser_response(await asyncio.wait_for(ws.recv(), timeout=2.0))
                        if res.optional.event not in [EVENT_TTSSentenceStart, EVENT_TTSSentenceEnd, EVENT_TTSResponse]:
                            break
                except Exception as e:
                    logger.debug(f"Warmup response reception completed: {e}")

                # Note: Don't close connection, maintain long connection
                self.is_warmed_up = True
                self.last_used_time = time.time()
                logger.info("TTS connection warmup completed, connection remains active")
            else:
                logger.warning("Warmup connection creation failed")
        except Exception as e:
            logger.warning(f"TTS connection warmup failed: {e}")
            self.ws_connection = None  # Ensure connection reference is cleared on failure

    async def text_to_stream(self, text, device_id=None, speaker=None, save_to_file=True):
        """
        Optimized streaming TTS with highest playback priority

        Args:
            text: Text to convert to speech
            device_id: Target device ID, if provided, send audio to specific device via event system
            speaker: Voice synthesis model ID
            save_to_file: Whether to save audio file, True means use default path, string means custom path
        """
        # If no speaker provided, get default value from configuration
        if speaker is None:
            if self.device_id:
                speaker = unified_config.get("TTS.model_id", "ICL_zh_female_chengshujiejie_tob", device_id=self.device_id)
            else:
                # If no device_id, use constant configuration
                try:
                    speaker = unified_config.get("TTS.model_id", "ICL_zh_female_chengshujiejie_tob")
                except Exception as e:
                    logger.warning(f"Failed to get TTS model ID, using default value: {e}")
                    speaker = "ICL_zh_female_chengshujiejie_tob"

        # Filter special symbols
        filtered_text = self.filter_text_for_tts(text)
        logger.info(f"Original text: {text[:30]}...")
        logger.info(f"Filtered text: {filtered_text[:30]}...")

        # Completely reset state
        self.buffer = bytearray()
        self.current_device_id = device_id
        self.playback_active = False

        # Reset queue and events first, ensure no state from last time
        if self.audio_queue:
            while not self.audio_queue.empty():
                self.audio_queue.get_nowait()
        self.audio_queue = asyncio.Queue()
        self.playback_finished = asyncio.Event()
        self.playback_active = True

        # When sending to device ID, clear possible audio buffer
        if device_id:
            # Send reset signal
            event_system.emit('tts_reset', {
                'device_id': device_id
            })
            logger.debug(f"Sending reset signal to device: {device_id}")

        # Prepare file information (if need to save to file)
        save_path = None
        if save_to_file:
            if isinstance(save_to_file, str):
                save_path = save_to_file
            else:
                timestamp = int(time.time())
                save_path = f"sound/volcano/ans_{timestamp}.pcm"

        # Establish connection in parallel
        connection_task = asyncio.create_task(self._ensure_connection())

        collected_audio_data = []

        try:
            # Wait for connection completion
            connection_ready = await connection_task
            if not connection_ready:
                logger.error("Unable to establish TTS service connection")
                self.playback_active = False
                await self.audio_queue.put(None)
                return False

            ws = self.ws_connection
            self.last_used_time = time.time()

            # Start session
            session_id = uuid.uuid4().__str__().replace('-', '')
            await start_session(ws, speaker, session_id)
            res = parser_response(await ws.recv())

            if res.optional.event != EVENT_SessionStarted:
                logger.error("TTS session start failed")
                self.playback_active = False
                await self.audio_queue.put(None)
                return False

            # Send text request
            logger.info(f"Requesting speech synthesis: '{filtered_text[:20]}...'")
            await send_pcm_text(ws, speaker, filtered_text, session_id)
            await finish_session(ws, session_id)

            # Receive data in real time
            audio_chunks = 0
            tts_completed = False
            start_time = time.time()

            # Receive audio data
            while not tts_completed:
                try:
                    res = parser_response(await asyncio.wait_for(ws.recv(), timeout=5.0))

                    if res.optional.event == EVENT_TTSResponse and res.header.message_type == AUDIO_ONLY_RESPONSE:
                        if res.payload and len(res.payload) > 0:
                            # Put payload into buffer first
                            self.buffer.extend(res.payload)

                            # Collect audio data for file saving
                            if save_to_file:
                                collected_audio_data.append(res.payload.copy() if isinstance(res.payload, bytearray) else res.payload)

                            # Send as soon as there's enough for one chunk
                            while len(self.buffer) >= self.chunk_size:
                                chunk = self.buffer[:self.chunk_size]
                                self.buffer = self.buffer[self.chunk_size:]
                                await self.audio_queue.put(bytes(chunk))

                                # Send audio through event system
                                if device_id:
                                    event_system.emit('tts_audio_ready', {
                                        'device_id': device_id,
                                        'audio_data': bytes(chunk),
                                        'use_raw_pcm': self.use_raw_pcm
                                    })
                                    # logger.debug(f"Sending TTS audio to device via event system: {device_id}")
                                else:
                                    # If no device ID, log warning
                                    logger.warning("No device_id provided, unable to send TTS audio")

                                audio_chunks += 1

                    elif res.optional.event in [EVENT_SessionFinished, EVENT_ConnectionFinished]:
                        logger.debug("TTS session ended")
                        tts_completed = True
                    elif res.optional.event not in [EVENT_TTSSentenceStart, EVENT_TTSSentenceEnd]:
                        logger.debug(f"Received non-audio event: {res.optional.event}")
                        tts_completed = True
                except asyncio.TimeoutError:
                    logger.warning("Waiting for TTS response timeout")
                    tts_completed = True
                except ConnectionClosed:
                    logger.warning("TTS service connection closed")
                    self.ws_connection = None
                    tts_completed = True
                except Exception as e:
                    logger.error(f"Audio stream reception error: {e}")
                    tts_completed = True

            # Calculate processing delay
            processing_time = time.time() - start_time
            logger.debug(f"Total audio acquisition time: {processing_time:.3f} seconds")

        except Exception as e:
            logger.error(f"Streaming TTS processing error: {e}")
            return False
        finally:
            # When loop ends, send the remaining part once more
            if self.buffer:
                leftover = bytes(self.buffer)
                await self.audio_queue.put(leftover)
                if device_id:
                    event_system.emit('tts_audio_ready', {
                        'device_id': device_id,
                        'audio_data': leftover,
                        'use_raw_pcm': self.use_raw_pcm
                    })
                    logger.debug(f"Sending last remaining audio data: {len(leftover)} bytes")
                else:
                    logger.warning(f"No device_id provided, unable to send last remaining audio data: {len(leftover)} bytes")
                self.buffer.clear()

            # Send end signal
            await self.audio_queue.put(None)

            # Send TTS completion event, let client know audio transmission is complete
            if device_id:
                event_system.emit('tts_completed', {
                    'device_id': device_id
                })
                logger.debug(f"Sending TTS completion signal to device: {device_id}")

            # File saving
            if save_to_file and collected_audio_data and save_path:
                # Synchronous file writing
                self._save_audio_file_sync(collected_audio_data, save_path)

            # Other cleanup logic
            self.playback_active = False
            self.playback_finished.set()

            if audio_chunks == 0:
                logger.warning("No audio data received")
                return False

            logger.info(f"Successfully processed {audio_chunks} audio data blocks, waiting for playback completion...")

            # Update connection last usage time
            self.last_used_time = time.time()

            return True

    def _save_audio_file_sync(self, audio_chunks, file_path):
        """Synchronously save audio file in separate thread"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)

            # Write file
            with open(file_path, 'wb') as f:
                for chunk in audio_chunks:
                    if isinstance(chunk, bytes):
                        f.write(chunk)
                    elif isinstance(chunk, bytearray):
                        f.write(bytes(chunk))

            logger.info(f"Audio successfully saved to: {file_path}")
        except Exception as e:
            logger.error(f"Failed to save audio file: {e}")

    def _run_event_loop(self):
        """Thread function to run event loop"""
        asyncio.set_event_loop(self.event_loop)
        self.event_loop.run_forever()

    # Update text_to_speech method, enable file saving by default
    def text_to_speech(self, text, speaker=None, save_to_file=True, device_id=None, use_raw_pcm=None):
        """
        Synchronous version of TTS method, convenient for calling from non-async environment
        Save audio to file by default

        Args:
            text: Text content to play
            speaker: Voice speaker
            save_to_file: Whether to save audio file, True uses automatic filename, string means specified file path
            device_id: Device ID for sending audio via UDP
            use_raw_pcm: Whether to use raw PCM transmission, if None use class setting

        Returns:
            bool: Whether playback was successful
        """
        # If no speaker provided, get default value from configuration
        if speaker is None:
            if self.device_id:
                speaker = unified_config.get("TTS.model_id", "ICL_zh_female_chengshujiejie_tob", device_id=self.device_id)
            else:
                # If no device_id, use constant configuration
                try:
                    speaker = unified_config.get("TTS.model_id", "ICL_zh_female_chengshujiejie_tob")
                except Exception as e:
                    logger.warning(f"Failed to get TTS model ID, using default value: {e}")
                    speaker = "ICL_zh_female_chengshujiejie_tob"

        # Filter special symbols
        filtered_text = self.filter_text_for_tts(text)
        logger.info(f"Playing text: {filtered_text[:30]}...")

        # Save device ID
        self.current_device_id = device_id

        # If use_raw_pcm parameter provided, temporarily update PCM transmission mode
        original_pcm_mode = self.use_raw_pcm
        if use_raw_pcm is not None:
            # Temporarily change PCM mode
            self.use_raw_pcm = use_raw_pcm
            logger.debug(f"Temporarily set PCM transmission mode: {'Raw PCM' if use_raw_pcm else 'Opus encoding'}")

        if device_id:
            logger.info(f"Will send TTS audio to device via event system: {device_id}, using {'Raw PCM' if self.use_raw_pcm else 'Opus encoding'}")

        try:
            future = asyncio.run_coroutine_threadsafe(
                self.text_to_stream(filtered_text, device_id, speaker, save_to_file),
                self.event_loop
            )

            # Wait for result, timeout 60 seconds
            result = future.result(60)
            return result
        except Exception as e:
            logger.error(f"Synchronous TTS call failed: {e}")
            return False
        finally:
            # If PCM mode was temporarily changed, restore original setting
            if use_raw_pcm is not None and self.use_raw_pcm != original_pcm_mode:
                self.use_raw_pcm = original_pcm_mode
                logger.debug(f"Restored PCM transmission mode: {'Raw PCM' if original_pcm_mode else 'Opus encoding'}")

    def stop_tts(self):
        """Stop currently playing TTS audio"""
        logger.info("Stopping TTS playback...")

        # Stop flag, notify playback coroutine to stop
        self.playback_active = False

        # Clear audio queue and put termination signal
        if self.audio_queue:
            # Use run_coroutine_threadsafe to ensure execution in event loop
            future = asyncio.run_coroutine_threadsafe(
                self._clear_audio_queue(),
                self.event_loop
            )
            try:
                # Wait for queue clearing operation to complete, set timeout to prevent blocking
                future.result(3.0)
                logger.info("TTS playback stopped")
                return True
            except Exception as e:
                logger.error(f"Failed to stop TTS playback: {e}")
                return False
        return True

    async def _clear_audio_queue(self):
        """Clear audio queue and send termination signal"""
        if self.audio_queue:
            # Clear all items in queue
            while not self.audio_queue.empty():
                try:
                    self.audio_queue.get_nowait()
                except:
                    pass

            # Send termination signal
            await self.audio_queue.put(None)

            # If playback finished event exists, set it as completed
            if self.playback_finished and not self.playback_finished.is_set():
                self.playback_finished.set()

    async def disconnect(self, ws=None):
        """Disconnect WebSocket connection (only for explicitly closing long connection)"""
        if ws or self.ws_connection:
            try:
                target_ws = ws or self.ws_connection
                await finish_connection(target_ws)
                await target_ws.recv()
                await target_ws.close()
                if target_ws == self.ws_connection:
                    self.ws_connection = None
                logger.info("WebSocket connection disconnected")
            except:
                pass

    async def create_connection(self):
        """Create new WebSocket connection"""
        ws_header = {
            "X-Api-App-Key": self.app_id,
            "X-Api-Access-Key": self.token,
            "X-Api-Resource-Id": 'volc.service_type.10029',
            "X-Api-Connect-Id": str(uuid.uuid4()),
        }
        url = 'wss://openspeech.bytedance.com/api/v3/tts/bidirection'

        try:
            ws = await websockets.connect(url, additional_headers=ws_header, max_size=1000000000)
            # Initialize connection
            await start_connection(ws)
            res = parser_response(await ws.recv())

            if res.optional.event != EVENT_ConnectionStarted:
                print("Connection failed")
                await ws.close()
                return None

            return ws

        except Exception as e:
            print(f"Connection error: {e}")
            return None

    async def _play_audio_stream(self):
        """Independent coroutine for real-time audio stream playback, enhanced version"""
        self.playback_active = True
        playback_ended = False
        buffer_data = []  # Buffer for smooth playback
        total_audio_bytes = 0  # Statistics for total audio data
        audio_blocks_played = 0  # Statistics for actual played data blocks

        try:
            # Try to actively close and reopen audio device
            sd.stop()

            # Check audio device first
            default_output = sd.query_devices(kind='output')
            logger.debug(f"Default output device: {default_output['name']}")

            # Create audio output stream, explicitly specify parameters for safety
            with sd.OutputStream(samplerate=24000, channels=1, dtype='int16',
                                 blocksize=1024, latency='low', device=None) as stream:
                logger.debug("Audio output stream created successfully, ready to play")
                buffer_size = 3  # Reduce buffer count to improve response speed

                # Fill buffer first
                while len(buffer_data) < buffer_size and self.playback_active:
                    try:
                        pcm_data = await asyncio.wait_for(self.audio_queue.get(), timeout=0.5)
                        if pcm_data is None:  # Termination signal
                            playback_ended = True
                            break
                        buffer_data.append(pcm_data)
                        total_audio_bytes += len(pcm_data)
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        logger.error(f"Buffer filling error: {e}")
                        break

                # If buffer has data, start playback
                if buffer_data and not playback_ended:
                    buffer_size_kb = sum(len(data) for data in buffer_data) / 1024
                    logger.debug(f"Starting playback, buffer size: {len(buffer_data)} blocks, {buffer_size_kb:.2f}KB")

                # Main playback loop
                while self.playback_active and not playback_ended:
                    # Play data in buffer
                    while buffer_data and self.playback_active:
                        pcm_data = buffer_data.pop(0)
                        # Check data validity
                        if not pcm_data or len(pcm_data) < 10:
                            logger.warning(f"Skipping invalid data block: {len(pcm_data)} bytes")
                            continue

                        # Convert data and confirm correct shape
                        audio_data = np.frombuffer(pcm_data, dtype=np.int16)
                        if len(audio_data) == 0:
                            logger.warning("Audio data is empty after conversion")
                            continue

                        # Check audio validity
                        max_amplitude = np.max(np.abs(audio_data))
                        if max_amplitude < 10:  # If audio amplitude is too low
                            logger.warning(f"Audio amplitude too low: {max_amplitude}")

                        # Write to audio stream
                        try:
                            stream.write(audio_data)
                            audio_blocks_played += 1
                        except Exception as e:
                            logger.error(f"Audio playback error: {e}")

                        # Simultaneously try to get more data to fill buffer
                        try:
                            while len(buffer_data) < buffer_size and self.playback_active:
                                new_data = await asyncio.wait_for(self.audio_queue.get(), timeout=0.01)
                                if new_data is None:  # Termination signal
                                    playback_ended = True
                                    break
                                buffer_data.append(new_data)
                                total_audio_bytes += len(new_data)
                        except asyncio.TimeoutError:
                            # Timeout means no new data temporarily, continue playing buffer data
                            pass
                        except Exception as e:
                            logger.error(f"Playback loop error: {e}")
                            playback_ended = True
                            break

                    # Buffer empty, try to get more data
                    if not playback_ended and self.playback_active:
                        try:
                            pcm_data = await asyncio.wait_for(self.audio_queue.get(), timeout=1.0)
                            if pcm_data is None:  # Termination signal
                                logger.debug("Received playback termination signal")
                                playback_ended = True
                            else:
                                buffer_data.append(pcm_data)
                                total_audio_bytes += len(pcm_data)
                        except asyncio.TimeoutError:
                            # No data for over 1 second, consider playback ended
                            logger.debug("Audio queue timeout, playback ended")
                            playback_ended = True
                        except Exception as e:
                            logger.error(f"Audio acquisition error: {e}")
                            playback_ended = True

            # Statistics after playback ends
            if audio_blocks_played > 0:
                logger.info(f"Audio playback completed: played {audio_blocks_played} data blocks, total {total_audio_bytes/1024:.2f}KB")
            else:
                logger.warning("No audio data played")

        except Exception as e:
            logger.error(f"Audio stream creation error: {e}")
        finally:
            self.playback_active = False
            logger.debug("Audio playback thread ended")
            # Set playback completion event
            self.playback_finished.set()

# Modified demo_tts_manager function, removed warmup call
async def demo_tts_manager():
    # Create TTS manager
    tts = TTSManager()

    # Generate and play speech, use text_to_stream method (now supports play_audio parameter)
    import time
    time.sleep(3)
    print("\nGenerating speech...")
    tts.text_to_speech("有事情的话再叫姐姐噢。", save_to_file="sound/volcano/testing.pcm", use_raw_pcm=True)
    time.sleep(10)
    tts.text_to_speech("是不是在等姐姐呀？", save_to_file="sound/volcano/testing.pcm", use_raw_pcm=True)
    time.sleep(20)
    # time_speech = [
    #     "傍晚六点啦～今天的晚餐想吃点什么呢？让姐姐来给你推荐一下吧～",
    #     "晚上七点啦～吃饱饭了吗？要不要一起散散步，消化一下呢？",
    #     "现在是晚上八点～是不是该放松一下了呢？来，姐姐给你一个温暖的抱抱～",
    #     "晚上九点咯～这时候适合泡个热水澡，放松一下身心哦～",
    #     "晚上十点啦～快要到睡觉时间了呢～刷牙了吗？被窝暖好了吗？",
    #     "晚上十一点了哦……要不要早点休息呢？明天也要有精神才行哦～",
    # ]

    # for index, speech in enumerate(time_speech, start=3):
    #     file_path = f"sound/time_notify/chinese/time{index}.pcm"
    #     tts.text_to_speech(speech, save_to_file=file_path)
    # success = tts.text_to_speech(
    #     text="你好呀，今天有开心吗。我今天也很想你噢，每天都想见到你。",
    #     # play_audio=True  # Although this parameter is not used in new method, keep for compatibility
    # )

    # if success:
    #     print("Speech generation and playback successful!")
    # else:
    #     print("Speech generation failed")

    # Explicitly close connection before ending
    if tts.ws_connection:
        await tts.disconnect()  # Use existing disconnect method to close connection


if __name__ == "__main__":
    asyncio.run(demo_tts_manager())
    # print("\nGenerating speech...")
    # tts.text_to_speech("你好呀，今天有开心吗。我今天也很想你噢，每天都想见到你。")
    # Use same way to run demo
    # appId = VOLCANO_TTS_APP_ID
    # token = VOLCANO_TTS_TOKEN
    # speaker = 'zh_female_wanwanxiaohe_moon_bigtts'
    # text = "好久不见，今天过得怎么样？"
    # output_path = 'sound/answer.pcm'
    # asyncio.run(run_demo(appId, token, speaker, text, output_path))

    # If you want to play the generated file
    # play("sound/answer.pcm", volume=0.8, samplerate=24000)
