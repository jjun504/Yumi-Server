import string
import time
import unified_config
from unified_config import get_config, set_config
from loguru import logger
import re
import json
from youtubeAPI import YouTubeAPI

class MusicHandler:
    def __init__(self, tts_manager=None, chat_saver=None, device_id=None):
        # Initialize member variables
        self.chat_saver = chat_saver
        self.interrupted_music = False
        self.search = False
        self.result = {}
        self.device_id = device_id  # Ensure device_id is set first
        self.tmp_music_volume = get_config("audio_settings.music_volume", 50, device_id=device_id)
        self.busy = False

        # Playback queue management
        self.play_queue = []  # Current playback queue
        self.current_index = 0  # Current playback index
        self.current_song = None  # Current playing song information

        # YouTube API for searching songs and getting playlists
        self.youtube_api = YouTubeAPI() if get_config("music.enabled", True, device_id=device_id) else None

    def preprocess_text(self, text: str) -> tuple[str, str]:
        """
        Preprocess text by removing punctuation, converting to lowercase, and detecting language

        Args:
            text: Input text

        Returns:
            tuple: (Processed text, Language type ('chinese' or 'english'))
        """
        # Define additional Chinese punctuation marks
        chinese_punctuation = '，。！？；：""''【】（）《》、…￥'

        # Create translation table for English and Chinese punctuation
        trans_table = str.maketrans('', '', string.punctuation + chinese_punctuation)

        # Remove all punctuation and convert to lowercase
        text = text.lower().translate(trans_table)

        # Detect language type (simple check: contains Chinese characters = Chinese)
        is_chinese = any('\u4e00' <= char <= '\u9fff' for char in text)
        lang = 'chinese' if is_chinese else 'english'

        # For Chinese text, remove all spaces
        if lang == 'chinese':
            text = text.replace(' ', '')
        else:
            # For English text, replace multiple spaces with single space
            text = ' '.join(text.split())

        return text, lang


    def check_music_query(self, query: str) -> bool:
        """
        Process all music-related queries using complete sentence matching
        """
        try:
            # Preprocess text
            processed_text, lang = self.preprocess_text(query)

            # Define complete query sentence patterns
            music_patterns = {
                'chinese': {
                    'play_song': [
                        '来一首'
                    ],
                    'play_last': [
                        "播放音乐",
                    ],
                    'pause': [
                        '暂停播放',
                    ],
                    'resume': [
                        '继续播放',
                    ],
                    'next_song': [
                        '下一首',
                    ],
                    'previous_song': [
                        '上一首',
                    ],
                    'volume_up': [
                        '声音大一点',
                    ],
                    'volume_down': [
                        '声音小一点',
                    ],
                    'toggle_autoplay': [
                        '切换自动播放',
                    ]
                },
                'english': {
                    'play_song': [
                        'play',
                        'play music',
                        'play a song',
                        'start playing',
                        'can you play',
                        'please play',
                        'i want to hear',
                        'could you play'
                    ],
                    'pause': [
                        'pause',
                        'pause the music',
                        'stop playing',
                        'stop the music',
                        'pause playback'
                    ],
                    'resume': [
                        'resume',
                        'continue',
                        'continue playing',
                        'resume playback',
                        'play again'
                    ],
                    'next_song': [
                        'next song',
                        'skip',
                        'play next',
                        'next track',
                        'skip this song'
                    ],
                    'previous_song': [
                        'previous song',
                        'go back',
                        'play previous',
                        'last song',
                        'previous track'
                    ],
                    'volume_up': [
                        'volume up',
                        'increase volume',
                        'turn it up',
                        'louder',
                        'increase the volume'
                    ],
                    'volume_down': [
                        'volume down',
                        'decrease volume',
                        'turn it down',
                        'quieter',
                        'lower the volume'
                    ],
                    'toggle_autoplay': [
                        'toggle autoplay',
                        'turn autoplay on',
                        'turn autoplay off',
                        'enable autoplay',
                        'disable autoplay'
                    ]
                }
            }

            patterns = music_patterns[lang]

            # Process music commands (complete sentence matching)
            if lang == 'chinese':
                # Play song
                if any(processed_text.startswith(pattern) for pattern in patterns['play_song']):
                    # Extract song name (part after command word)
                    for pattern in patterns['play_song']:
                        if processed_text.startswith(pattern):
                            song_name = processed_text[len(pattern):].strip()
                            if song_name:
                                self.result = {'command': 'play', 'song_name': song_name}
                                self.search = True
                                # Don't automatically set interrupted_music, let playback proceed naturally
                            else:
                                self.result = {'command': 'play_last'}
                            return True
                # Play last song
                if any(processed_text.startswith(pattern) for pattern in patterns['play_last']):
                    self.result = {'command': 'play_last'}
                    return True
                # Pause playback
                if any(processed_text.startswith(pattern) for pattern in patterns['pause']):
                    self.result = {'command': 'pause'}
                    return True

                # Resume playback
                if any(processed_text.startswith(pattern) for pattern in patterns['resume']):
                    self.result = {'command': 'resume'}
                    return True

                # Next song
                if any(processed_text.startswith(pattern) for pattern in patterns['next_song']):
                    self.result = {'command': 'next'}
                    self.interrupted_music = True
                    return True

                # Previous song
                if any(processed_text.startswith(pattern) for pattern in patterns['previous_song']):
                    self.result = {'command': 'previous'}
                    self.interrupted_music = True
                    return True

                # Increase volume
                if any(processed_text.startswith(pattern) for pattern in patterns['volume_up']):
                    self.result = {'command': 'volume_up'}
                    return True

                # Decrease volume
                if any(processed_text.startswith(pattern) for pattern in patterns['volume_down']):
                    self.result = {'command': 'volume_down'}
                    return True

                # Toggle autoplay
                if any(processed_text.startswith(pattern) for pattern in patterns['toggle_autoplay']):
                    self.result = {'command': 'toggle_autoplay'}
                    return True

            else:  # English response
                # Play song
                if any(processed_text.startswith(pattern) for pattern in patterns['play_song']):
                    for pattern in patterns['play_song']:
                        if processed_text.startswith(pattern):
                            song_name = processed_text[len(pattern):].strip()
                            if song_name:
                                self.result = {'command': 'play', 'song_name': song_name}
                                self.search = True
                                # Don't automatically set interrupted_music, let playback proceed naturally
                            else:
                                self.result = {'command': 'play_last'}
                            return True
                    self.result = {'command': 'play_last'}
                    return True

                # Other English command processing
                if any(processed_text.startswith(pattern) for pattern in patterns['pause']):
                    self.result = {'command': 'pause'}
                    return True
                if any(processed_text.startswith(pattern) for pattern in patterns['resume']):
                    self.result = {'command': 'resume'}
                    return True
                if any(processed_text.startswith(pattern) for pattern in patterns['next_song']):
                    self.result = {'command': 'next'}
                    self.interrupted_music = True
                    return True
                if any(processed_text.startswith(pattern) for pattern in patterns['previous_song']):
                    self.result = {'command': 'previous'}
                    self.interrupted_music = True
                    return True
                if any(processed_text.startswith(pattern) for pattern in patterns['volume_up']):
                    self.result = {'command': 'volume_up'}
                    return True
                if any(processed_text.startswith(pattern) for pattern in patterns['volume_down']):
                    self.result = {'command': 'volume_down'}
                    return True
                if any(processed_text.startswith(pattern) for pattern in patterns['toggle_autoplay']):
                    self.result = {'command': 'toggle_autoplay'}
                    return True

            return False
        except Exception as e:
            logger.error(f"Error processing music command: {str(e)}")
            return False


    def check_playlist_query(self, query: str) -> str:
        """
        Check if the query is exactly about listing all music playlists

        Args:
            query: User query text

        Returns:
            str: Formatted playlist string, or empty string if not an exact playlist query
        """
        try:
            # Preprocess text
            processed_text, lang = self.preprocess_text(query)

            # Define playlist query patterns - exact match mode
            playlist_patterns = {
                'chinese': [
                    '我有什么歌单',
                    '我的歌单',
                    '查看歌单',
                    '显示歌单',
                    '列出歌单',
                    '歌单列表',
                    '有哪些歌单',
                    '播放列表',
                    '查看我的歌单',
                    '显示我的歌单',
                    '列出我的歌单',
                    '我有几个歌单',
                    '我有多少个歌单',
                    '我有哪些歌单',
                    '帮我查看歌单',
                    '请列出我的歌单',
                    '请显示我的歌单',
                    '我的播放列表',
                    '我的所有歌单',
                    '我拥有的歌单'
                ],
                'english': [
                    'what playlists do i have',
                    'show my playlists',
                    'list my playlists',
                    'display my playlists',
                    'what are my playlists',
                    'my playlists',
                    'show playlists',
                    'list playlists',
                    'display playlists',
                    'my playlist list',
                    'what playlist do i have',
                    'available playlists',
                    'show available playlists',
                    'list all playlists',
                    'show all playlists',
                    'my available playlists',
                    'what music playlists do i have',
                    'show me my playlists',
                    'please show my playlists',
                    'could you show my playlists'
                ]
            }

            patterns = playlist_patterns[lang]

            # Check if query exactly matches any playlist pattern
            if processed_text in patterns:
                try:
                    # Check if YouTube API is initialized
                    if not self.youtube_api:
                        return "YouTube API not initialized" if lang == 'english' else "YouTube API未初始化"

                    # Call YouTube API to get playlists
                    playlists = self.youtube_api.get_self_playlists()

                    # Prepare reply message
                    message = ""

                    # Process results
                    if playlists:
                        # Limit to first 10 playlists
                        playlists = playlists[:10]

                        # Choose reply format based on language
                        if lang == 'chinese':
                            message = "你有以下歌单：\n"
                        else:
                            message = "You have the following playlists:\n"

                        # Add numbering and information for each playlist
                        for i, playlist in enumerate(playlists, 1):
                            if lang == 'chinese':
                                message += f"{i}. {playlist['title']}， ({playlist['item_count']} 首歌曲)。\n"
                            else:
                                message += f"{i}. {playlist['title']} ({playlist['item_count']} songs).\n"

                        # Log the information
                        logger.debug("[Music] Your playlists:")
                        logger.debug(message)

                        # Save record of this operation
                        if self.chat_saver:
                            self.chat_saver.save_chat_history("[System] retrieved playlists")

                        return message.strip()
                    else:
                        # No playlists found
                        if lang == 'chinese':
                            message = "没有找到任何歌单。"
                        else:
                            message = "No playlists found."

                        logger.info("[Music] No playlists found or error retrieving playlists")
                        return message

                except Exception as e:
                    logger.error(f"Error retrieving playlists: {str(e)}")
                    return ""

            # Not an exact playlist query match, return empty string
            return ""

        except Exception as e:
            logger.error(f"Error processing playlist query: {str(e)}")
            return ""


    def check_play_playlist_query(self, query: str) -> bool:
        """
        Check if the query is about playing a specific playlist by index

        Args:
            query: User query text

        Returns:
            bool: True if the query matches playlist play pattern and was executed, False otherwise
        """
        try:
            # Preprocess text
            processed_text, lang = self.preprocess_text(query)

            # Define playlist play patterns
            playlist_patterns = {
                'chinese': [
                    '播放第',
                    '帮我播放第',
                    '放第',
                    '帮我放第',
                    '开始播放第',
                    '请播放第',
                    '打开第',
                    '请放第',
                    '播放我第',
                ],
                'english': [
                    'play playlist',
                    'play the playlist',
                    'start playlist',
                    'open playlist',
                    'play my playlist',
                    'start my playlist'
                ]
            }

            # Check if query matches any playlist play pattern
            match_found = False
            playlist_index = -1

            if lang == 'chinese':
                for pattern in playlist_patterns['chinese']:
                    if pattern in processed_text and '歌单' in processed_text:
                        # Extract the playlist index
                        text_after_pattern = processed_text.split(pattern, 1)[1]
                        parts = text_after_pattern.split('歌单', 1)[0]
                        # Convert Chinese numbers if necessary
                        parts = parts.replace('一', '1').replace('二', '2').replace('三', '3') \
                            .replace('四', '4').replace('五', '5').replace('六', '6') \
                            .replace('七', '7').replace('八', '8').replace('九', '9') \
                            .replace('十', '10')

                        # Extract the numeric part
                        num_match = re.search(r'\d+', parts)
                        if num_match:
                            try:
                                # Convert to integer and adjust for zero-indexing
                                playlist_index = int(num_match.group()) - 1
                                match_found = True
                                break
                            except ValueError:
                                continue
            else:  # English
                # Support both numeric and text-based numbers in English
                playlist_number_patterns = [
                    r'play (?:the |my )?(\d+)(?:st|nd|rd|th)? playlist',
                    r'play (?:the |my )?playlist (\d+)',
                    r'start (?:the |my )?(\d+)(?:st|nd|rd|th)? playlist',
                    r'open (?:the |my )?(\d+)(?:st|nd|rd|th)? playlist'
                ]

                # English text number mapping
                text_numbers = {
                    'first': 1, 'one': 1,
                    'second': 2, 'two': 2,
                    'third': 3, 'three': 3,
                    'fourth': 4, 'four': 4,
                    'fifth': 5, 'five': 5,
                    'sixth': 6, 'six': 6,
                    'seventh': 7, 'seven': 7,
                    'eighth': 8, 'eight': 8,
                    'ninth': 9, 'nine': 9,
                    'tenth': 10, 'ten': 10
                }

                # First try to match numeric patterns
                for pattern in playlist_number_patterns:
                    match = re.search(pattern, processed_text)
                    if match:
                        try:
                            # Convert to integer and adjust for zero-indexing
                            playlist_index = int(match.group(1)) - 1
                            match_found = True
                            break
                        except (ValueError, IndexError):
                            continue

                # If no numeric match, try text number patterns
                if not match_found:
                    # Create patterns for text numbers
                    for text_num, value in text_numbers.items():
                        text_patterns = [
                            f'play (?:the |my )?{text_num} playlist',
                            f'play {text_num}',
                            f'start (?:the |my )?{text_num} playlist',
                            f'open (?:the |my )?{text_num} playlist'
                        ]

                        for pattern in text_patterns:
                            if re.search(pattern, processed_text):
                                playlist_index = value - 1  # Adjust for zero-indexing
                                match_found = True
                                break

                        if match_found:
                            break

            # If a valid playlist index was found, try to play it
            if match_found and playlist_index >= 0:
                try:
                    # Check if music is enabled
                    if not get_config("music.enabled", True, device_id=self.device_id):
                        logger.warning("Music playback is disabled")
                        return False

                    # Check if YouTube API is available
                    if not self.youtube_api:
                        logger.warning("YouTube API not initialized")
                        return False

                    # Get playlists and play the specified one
                    playlists = self.youtube_api.get_self_playlists()
                    if playlists and 0 <= playlist_index < len(playlists):
                        playlist_id = playlists[playlist_index]["id"]
                        songs = self.youtube_api.get_playlist_songs(playlist_id)
                        if songs:
                            # Set command to play first song of the playlist
                            youtube_url = songs[0]['url']
                            volume = get_config("audio_settings.music_volume", 50, device_id=self.device_id)
                            self.result = {
                                "command": "play",
                                "url": youtube_url,
                                "volume": volume
                            }
                            logger.info(f"[Music] Set playlist play command, index: {playlist_index}")
                            if self.chat_saver:
                                self.chat_saver.save_chat_history(f"[System] play playlist at index {playlist_index}")
                            return True
                        else:
                            logger.error("Playlist is empty")
                    else:
                        logger.error(f"Invalid playlist index: {playlist_index}")
                except Exception as e:
                    logger.error(f"Error playing playlist: {str(e)}")

            # Not a playlist play query or execution failed
            return False

        except Exception as e:
            logger.error(f"Error processing playlist play query: {str(e)}")
            return False


    def check_playlist_songs(self, query: str) -> str:
        """
        Check if the query is EXACTLY about listing songs in a specific playlist by index

        Args:
            query: User query text

        Returns:
            str: Formatted playlist songs string, or empty string if not a valid query
        """
        try:
            # Preprocess text
            processed_text, lang = self.preprocess_text(query)

            # Define playlist songs query patterns
            playlist_patterns = {
                'chinese': [
                    '第一个歌单有什么歌', '第一个歌单有什么歌曲', '第一个歌单有什么音乐', '第一个歌单有什么曲目',
                    '第二个歌单有什么歌', '第二个歌单有什么歌曲', '第二个歌单有什么音乐', '第二个歌单有什么曲目',
                    '第三个歌单有什么歌', '第三个歌单有什么歌曲', '第三个歌单有什么音乐', '第三个歌单有什么曲目',
                    '第四个歌单有什么歌', '第四个歌单有什么歌曲', '第四个歌单有什么音乐', '第四个歌单有什么曲目',
                    '第五个歌单有什么歌', '第五个歌单有什么歌曲', '第五个歌单有什么音乐', '第五个歌单有什么曲目',
                    '第六个歌单有什么歌', '第六个歌单有什么歌曲', '第六个歌单有什么音乐', '第六个歌单有什么曲目',
                    '第七个歌单有什么歌', '第七个歌单有什么歌曲', '第七个歌单有什么音乐', '第七个歌单有什么曲目',
                    '第八个歌单有什么歌', '第八个歌单有什么歌曲', '第八个歌单有什么音乐', '第八个歌单有什么曲目',
                    '第九个歌单有什么歌', '第九个歌单有什么歌曲', '第九个歌单有什么音乐', '第九个歌单有什么曲目',
                    '第十个歌单有什么歌', '第十个歌单有什么歌曲', '第十个歌单有什么音乐', '第十个歌单有什么曲目',
                    '第1个歌单有什么歌', '第1个歌单有什么歌曲', '第1个歌单有什么音乐', '第1个歌单有什么曲目',
                    '第2个歌单有什么歌', '第2个歌单有什么歌曲', '第2个歌单有什么音乐', '第2个歌单有什么曲目',
                    '第3个歌单有什么歌', '第3个歌单有什么歌曲', '第3个歌单有什么音乐', '第3个歌单有什么曲目',
                    '第4个歌单有什么歌', '第4个歌单有什么歌曲', '第4个歌单有什么音乐', '第4个歌单有什么曲目',
                    '第5个歌单有什么歌', '第5个歌单有什么歌曲', '第5个歌单有什么音乐', '第5个歌单有什么曲目',
                    '第6个歌单有什么歌', '第6个歌单有什么歌曲', '第6个歌单有什么音乐', '第6个歌单有什么曲目',
                    '第7个歌单有什么歌', '第7个歌单有什么歌曲', '第7个歌单有什么音乐', '第7个歌单有什么曲目',
                    '第8个歌单有什么歌', '第8个歌单有什么歌曲', '第8个歌单有什么音乐', '第8个歌单有什么曲目',
                    '第9个歌单有什么歌', '第9个歌单有什么歌曲', '第9个歌单有什么音乐', '第9个歌单有什么曲目',
                    '第10个歌单有什么歌', '第10个歌单有什么歌曲', '第10个歌单有什么音乐', '第10个歌单有什么曲目'
                ],
                'english': [
                    'what songs are in the first playlist', 'what songs are in first playlist',
                    'what songs are in the second playlist', 'what songs are in second playlist',
                    'what songs are in the third playlist', 'what songs are in third playlist',
                    'what songs are in the fourth playlist', 'what songs are in fourth playlist',
                    'what songs are in the fifth playlist', 'what songs are in fifth playlist',
                    'what tracks are in the first playlist', 'what tracks are in first playlist',
                    'what music is in the first playlist', 'what music is in first playlist',
                    'songs in the first playlist', 'songs in first playlist',
                    'songs in the second playlist', 'songs in second playlist',
                    'tracks in the first playlist', 'tracks in first playlist',
                    'show songs in the first playlist', 'show songs in first playlist',
                    'list songs in the first playlist', 'list songs in first playlist'
                ]
            }

            # Check if pattern matches exactly (complete sentence matching)
            match_found = False
            playlist_index = -1

            # Method 1: Exact match with predefined sentence patterns
            if processed_text in playlist_patterns[lang]:
                match_found = True

                # Extract playlist number from matched pattern
                if lang == 'chinese':
                    # Extract number from Chinese pattern
                    pattern = r'第([一二三四五六七八九十\d]+)个'
                    match = re.search(pattern, processed_text)
                    if match:
                        num_text = match.group(1)
                        # Convert Chinese numbers
                        num_text = num_text.replace('一', '1').replace('二', '2').replace('三', '3') \
                                .replace('四', '4').replace('五', '5').replace('六', '6') \
                                .replace('七', '7').replace('八', '8').replace('九', '9') \
                                .replace('十', '10')
                        playlist_index = int(num_text) - 1
                else:
                    # Extract number from English pattern
                    text_numbers = {
                        'first': 0, 'second': 1, 'third': 2, 'fourth': 3, 'fifth': 4,
                        'sixth': 5, 'seventh': 6, 'eighth': 7, 'ninth': 8, 'tenth': 9
                    }
                    for num_text, index in text_numbers.items():
                        if num_text in processed_text:
                            playlist_index = index
                            break

            # Method 2: Use stricter regex matching for specific query patterns
            if not match_found:
                if lang == 'chinese':
                    # Strict Chinese pattern: must start with "第X个歌单" and end with "什么歌/歌曲/音乐/曲目"
                    pattern = r'^第([一二三四五六七八九十\d]+)个歌单有什么(歌|歌曲|音乐|曲目)$'
                    match = re.search(pattern, processed_text)

                    if match:
                        match_found = True
                        num_text = match.group(1)
                        num_text = num_text.replace('一', '1').replace('二', '2').replace('三', '3') \
                                .replace('四', '4').replace('五', '5').replace('六', '6') \
                                .replace('七', '7').replace('八', '8').replace('九', '9') \
                                .replace('十', '10')
                        try:
                            playlist_index = int(num_text) - 1
                        except ValueError:
                            match_found = False
                else:
                    # Strict English pattern: must contain specific patterns like "what songs are in the X playlist"
                    patterns = [
                        r'^what (songs|tracks|music) are in (?:the )?(\w+) playlist$',
                        r'^(songs|tracks|music) in (?:the )?(\w+) playlist$',
                        r'^show (songs|tracks|music) in (?:the )?(\w+) playlist$',
                        r'^list (songs|tracks|music) in (?:the )?(\w+) playlist$'
                    ]

                    text_numbers = {
                        'first': 0, 'second': 1, 'third': 2, 'fourth': 3, 'fifth': 4,
                        'sixth': 5, 'seventh': 6, 'eighth': 7, 'ninth': 8, 'tenth': 9,
                        '1st': 0, '2nd': 1, '3rd': 2, '4th': 3, '5th': 4,
                        '6th': 5, '7th': 6, '8th': 7, '9th': 8, '10th': 9
                    }

                    for pattern in patterns:
                        match = re.search(pattern, processed_text)
                        if match and len(match.groups()) >= 2:
                            num_text = match.group(2)
                            if num_text in text_numbers:
                                match_found = True
                                playlist_index = text_numbers[num_text]
                                break
                            elif num_text.isdigit():
                                match_found = True
                                playlist_index = int(num_text) - 1
                                break

            # If valid playlist index found, get songs from that playlist
            if match_found and playlist_index >= 0:
                try:
                    # Check if music is enabled
                    if not get_config("music.enabled", True, device_id=self.device_id):
                        logger.warning("Music playback is disabled")
                        return "Music feature is currently disabled."

                    # Check if YouTube API is initialized
                    if not self.youtube_api:
                        return "YouTube API not initialized" if lang == 'english' else "YouTube API未初始化"

                    # Get playlists
                    playlists = self.youtube_api.get_self_playlists()
                    if not playlists:
                        return "No playlists found." if lang == 'english' else "没有找到任何歌单。"

                    if playlist_index >= len(playlists):
                        return (f"Playlist {playlist_index + 1} not found. You only have {len(playlists)} playlists."
                            if lang == 'english' else
                            f"未找到第{playlist_index + 1}个歌单。你只有{len(playlists)}个歌单。")

                    # Get songs from the specified playlist
                    playlist = playlists[playlist_index]
                    songs = self.youtube_api.get_playlist_songs(playlist['id'])

                    if not songs:
                        return (f"No songs found in playlist '{playlist['title']}'."
                            if lang == 'english' else
                            f"在歌单'{playlist['title']}'中没有找到任何歌曲。")

                    # Format response message
                    if lang == 'chinese':
                        message = f"歌单 '{playlist['title']}' 包含以下歌曲：\n"
                    else:
                        message = f"Playlist '{playlist['title']}' contains the following songs:\n"

                    # Format the songs list
                    for i, song in enumerate(songs[:15], 1):  # Limit to first 15 songs
                        message += f"{i}. {song['title']} - by {song['author']}\n"

                    # Add note if there are more songs
                    if len(songs) > 15:
                        if lang == 'chinese':
                            message += f"\n...共{len(songs)}首歌曲，仅显示前15首。"
                        else:
                            message += f"\n...{len(songs)} songs total, showing only first 15."

                    # Save this operation record
                    if self.chat_saver:
                        self.chat_saver.save_chat_history(f"[System] listed songs in playlist {playlist_index + 1}")

                    return message.strip()

                except Exception as e:
                    logger.error(f"Error retrieving playlist songs: {str(e)}")
                    return "Error retrieving playlist songs." if lang == 'english' else "获取歌单歌曲时出错。"

            # Not a playlist songs query or execution failed
            return ""

        except Exception as e:
            logger.error(f"Error processing playlist songs query: {str(e)}")
            return ""

    def process_music_query(self, query: str) -> tuple[str, bool, dict]:
        """
        Process music-related queries through all check functions

        Args:
            query: User's query text

        Returns:
            tuple: (Response message or empty string, Command result boolean, Chat history data dict)
        """
        # Reset the result dict to avoid side effects from previous calls
        self.result = {}
        chat_history_data = {}

        try:
            # 1. First check for music commands (play, pause, volume, etc.)
            music_command_match = self.check_music_query(query)
            if music_command_match:
                # For play commands, need to search song info first then generate chat history data
                command = self.result.get('command', '')
                if command == 'play' and self.result.get('song_name'):
                    # First search song and update current_song, also get recommended songs
                    song_name = self.result.get('song_name', '')
                    if self.youtube_api:
                        songs = self.youtube_api.search_song(song_name, max_results=10)
                        if songs:
                            # Update current song info and playback queue (including searched songs + recommended songs)
                            self._update_current_song_info_with_queue(songs)
                            # Update url in result to first song
                            self.result['url'] = songs[0]['url']

                # Generate chat history data
                chat_history_data = self._generate_chat_history_data()

                # Music command matched, return empty message as the command
                # will be processed by the work() thread via result variable
                return "", True, chat_history_data

            # 2. Check if query is about listing all playlists
            playlist_listing = self.check_playlist_query(query)
            if playlist_listing:
                return playlist_listing, True, {}

            # 3. Check if query is about listing songs in a specific playlist
            playlist_songs = self.check_playlist_songs(query)
            if playlist_songs:
                return playlist_songs, True, {}

            # 4. Check if query is about playing a specific playlist
            playlist_play = self.check_play_playlist_query(query)
            if playlist_play:
                # Generate chat history data
                chat_history_data = self._generate_chat_history_data()

                # The function returns bool, but the actual command will be processed
                # through the work() thread, so we return an appropriate message
                lang = self.preprocess_text(query)[1]
                message = "开始播放歌单" if lang == 'chinese' else "Starting playlist playback"
                return message, True, chat_history_data

            # No matching music functionality found
            return "", False, {}

        except Exception as e:
            logger.error(f"Error in process_music_query: {str(e)}")
            return "", False, {}

    def _generate_chat_history_data(self):
        """Generate chat history data based on current result and current_song"""
        try:
            chat_data = {
                "command": "",
                "friendly_message": "",
                "current_song": None,
                "should_save_music_details": False
            }

            # Get command information
            command = self.result.get('command', '')
            chat_data["command"] = command

            # Add debug log
            logger.debug(f"Generate chat history data - current result: {self.result}, command: '{command}'")

            # Generate user-friendly message based on command type
            if command == 'play':
                song_name = self.result.get('song_name', '')
                if self.current_song and self.current_song.get('title'):
                    song_title = self.current_song.get('title', 'Unknown song')
                    chat_data["friendly_message"] = f"Now playing：{song_title}"
                    # Have song info, mark to save detailed information
                    chat_data["current_song"] = self.current_song
                    chat_data["should_save_music_details"] = True
                    logger.debug(f"Play command - using searched song info: {song_title}")
                elif song_name:
                    chat_data["friendly_message"] = f"Now playing：{song_name}"
                    logger.debug(f"Play command - using song name: {song_name}")
                else:
                    chat_data["friendly_message"] = "Now playing music"
                    logger.debug("Play command - using default message")

            elif command == 'pause':
                chat_data["friendly_message"] = "Music paused"
            elif command == 'resume':
                chat_data["friendly_message"] = "Music resumed"
            elif command == 'next':
                chat_data["friendly_message"] = "Switching to next song"
                # If have song info, also save detailed information
                if self.current_song and isinstance(self.current_song, dict):
                    chat_data["current_song"] = self.current_song
                    chat_data["should_save_music_details"] = True
            elif command == 'previous':
                chat_data["friendly_message"] = "Switching to previous song"
                # If have song info, also save detailed information
                if self.current_song and isinstance(self.current_song, dict):
                    chat_data["current_song"] = self.current_song
                    chat_data["should_save_music_details"] = True
            elif command == 'volume_up':
                chat_data["friendly_message"] = "Volume increased"
            elif command == 'volume_down':
                chat_data["friendly_message"] = "Volume decreased"
            elif command == 'play_last':
                chat_data["friendly_message"] = "Resuming music playback"
            else:
                # If command is empty or unknown, provide more friendly default message
                if command:
                    chat_data["friendly_message"] = f"Music operation executed: {command}"
                else:
                    chat_data["friendly_message"] = "Music operation executed"

            logger.debug(f"Generated chat history data: {chat_data}")
            return chat_data

        except Exception as e:
            logger.error(f"Error generating chat history data: {e}")
            return {
                "command": "",
                "friendly_message": "Music operation executed",
                "current_song": None,
                "should_save_music_details": False
            }

    def pause_music(self):
        """Pause music playback - set pause state, actual MQTT sending handled externally"""
        try:
            self.result = {"command": "pause"}
            logger.info("[Music] Set pause command")
            return True
        except Exception as e:
            logger.error(f"Error setting pause command: {str(e)}")
            return False

    def resume_music(self):
        """Resume music playback - set resume state, actual MQTT sending handled externally"""
        try:
            self.result = {"command": "resume"}
            logger.info("[Music] Set resume command")
            return True
        except Exception as e:
            logger.error(f"Error setting resume command: {str(e)}")
            return False

    def get_music_command_data(self):
        """Get music command data for external MQTT sending

        Returns:
            dict: Dictionary containing command type and parameters, returns None if no command
        """
        if not self.result or not get_config("music.enabled", True, device_id=self.device_id):
            return None

        command = self.result.get('command')
        if not command:
            return None

        # Build MQTT command data based on command type
        if command == 'play':
            url = self.result.get('url')
            if url:
                return {
                    "type": "play_music",
                    "url": url,
                    "volume": self.tmp_music_volume
                }
        elif command == 'pause':
            return {"type": "pause_music"}
        elif command == 'resume':
            return {"type": "resume_music"}
        elif command == 'stop':
            return {"type": "stop_music"}
        elif command == 'interrupt':
            return {"type": "pause_music"}

        return None

    def prepare_music_execution(self):
        """Prepare music execution data for external calls

        Returns:
            dict: Dictionary containing execution status and command data
        """
        if self.busy:
            return {"status": "busy", "command_data": None}

        self.busy = True

        try:
            execution_data = {
                "status": "ready",
                "command_data": None,
                "interrupted_music": self.interrupted_music,
                "search": self.search,
                "chat_history": []
            }

            # Process music commands (prioritize new commands over interrupt status)
            if self.result and get_config("music.enabled", True, device_id=self.device_id):
                command = self.result.get('command')

                if command:
                    try:
                        if command == 'play':
                            # Check if there's a direct URL (from playlist or process_response)
                            url = self.result.get('url')
                            if url:
                                # Play URL directly
                                volume = self.result.get('volume', get_config("audio_settings.music_volume", 50, device_id=self.device_id))
                                execution_data["command_data"] = {
                                    "type": "play_music",
                                    "url": url,
                                    "volume": volume
                                }
                                execution_data["chat_history"].append(f"[System] play music: {url}")
                            else:
                                # Search song and get YouTube URL, also get recommended songs
                                song_name = self.result.get('song_name', '')
                                if song_name and self.search:
                                    if self.youtube_api:
                                        songs = self.youtube_api.search_song(song_name, max_results=10)
                                        if songs:
                                            youtube_url = songs[0]['url']
                                            volume = get_config("audio_settings.music_volume", 50, device_id=self.device_id)
                                            execution_data["command_data"] = {
                                                "type": "play_music",
                                                "url": youtube_url,
                                                "volume": volume
                                            }
                                            # Update current song info and playback queue (including searched songs + recommended songs)
                                            self._update_current_song_info_with_queue(songs)
                                        else:
                                            logger.error(f"Song not found: {song_name}")
                                    self.search = False
                        elif command == 'play_last':
                            execution_data["command_data"] = {"type": "resume_music"}
                        elif command == 'pause':
                            execution_data["command_data"] = {"type": "pause_music"}
                        elif command == 'resume':
                            execution_data["command_data"] = {"type": "resume_music"}
                        elif command == 'next':
                            # Play next song
                            next_song_data = self._get_next_song()
                            if next_song_data:
                                execution_data["command_data"] = next_song_data
                            else:
                                execution_data["command_data"] = {"type": "stop_music"}
                        elif command == 'previous':
                            # Play previous song
                            prev_song_data = self._get_previous_song()
                            if prev_song_data:
                                execution_data["command_data"] = prev_song_data
                            else:
                                execution_data["command_data"] = {"type": "stop_music"}
                        elif command == 'volume_up':
                            current_vol = get_config("audio_settings.music_volume", 50, device_id=self.device_id)
                            new_vol = min(100, current_vol + 10)
                            set_config("audio_settings.music_volume", new_vol, device_id=self.device_id)
                            # Send set_volume command to Pi client
                            execution_data["command_data"] = {
                                "type": "set_volume",
                                "volume": new_vol
                            }
                        elif command == 'volume_down':
                            current_vol = get_config("audio_settings.music_volume", 50, device_id=self.device_id)
                            new_vol = max(0, current_vol - 10)
                            set_config("audio_settings.music_volume", new_vol, device_id=self.device_id)
                            # Send set_volume command to Pi client
                            execution_data["command_data"] = {
                                "type": "set_volume",
                                "volume": new_vol
                            }
                        elif command == 'toggle_autoplay':
                            current = get_config("music.autoplay", True, device_id=self.device_id)
                            set_config("music.autoplay", not current, device_id=self.device_id)
                    except Exception as e:
                        logger.error(f"Error preparing music command: {str(e)}")

                # Clear result to avoid repeated execution
                self.result = {}

            # If no new music command, check if interrupt status needs handling
            elif execution_data["command_data"] is None:
                if get_config("music.enabled", True, device_id=self.device_id):
                    if self.interrupted_music:
                        execution_data["command_data"] = {"type": "pause_music"}
                        if not self.search:
                            self.interrupted_music = False
                else:
                    execution_data["command_data"] = {"type": "stop_music"}

            return execution_data

        except Exception as e:
            logger.error(f"Error preparing music execution data: {e}")
            return {"status": "error", "command_data": None}
        finally:
            self.busy = False

    # These functions are already defined as class methods above

    def process_response(self, ai_response: str | dict) -> str:
        """
        Process AI response for music playback related function calls

        Args:
            ai_response: JSON string or dictionary format response

        Returns:
            str: Processing result message
        """
        try:
            # Parse JSON string
            if isinstance(ai_response, str):
                json_pattern = r"```json\s*([\s\S]*?)\s*```"
                json_match = re.search(json_pattern, ai_response)

                if json_match:
                    json_str = json_match.group(1).strip()
                else:
                    json_str = ai_response.strip()

                try:
                    ai_response = json.loads(json_str)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON parsing error: {e}")
                    return "Invalid JSON format"

            # Validate response format
            if not isinstance(ai_response, dict):
                return "Response format error: Dictionary type required"

            if ai_response.get("type") != "function call":
                return "Response type error: Function call type required"

            # Get parameters
            parameters = ai_response.get("parameters", {})
            function_name = parameters.get("function_name")
            value = parameters.get("value", "")

            if not function_name:
                return "Missing function_name parameter"

            # Check if music player is available
            if not get_config("music.enabled", True, device_id=self.device_id):
                return "Music playback feature is not enabled"

            # Handle different music functions
            if function_name == "play_single_song":
                if not value:
                    return "Please specify the song name to play"
                try:
                    if self.youtube_api:
                        songs = self.youtube_api.search_song(value, max_results=10)
                        if songs:
                            youtube_url = songs[0]['url']
                            volume = get_config("audio_settings.music_volume", 50, device_id=self.device_id)
                            # Set play command, actual MQTT sending handled externally
                            self.result = {
                                "command": "play",
                                "url": youtube_url,
                                "volume": volume
                            }

                            # Update current song info and playback queue (including searched songs + recommended songs)
                            self._update_current_song_info_with_queue(songs)

                            return f"Now playing: {value} (with {len(songs)-1} recommended songs in queue)"
                        else:
                            return f"No songs found for: {value}"
                    return "YouTube API not initialized"
                except Exception as e:
                    logger.error(f"Error playing single song: {e}")
                    return f"Playback error: {str(e)}"

            elif function_name == "play_playlist":
                if not value:
                    return "Please specify the playlist index to play"
                try:
                    if self.youtube_api:
                        playlists = self.youtube_api.get_self_playlists()
                        playlist_index = int(value)
                        if playlists and 0 <= playlist_index < len(playlists):
                            playlist_id = playlists[playlist_index]["id"]
                            songs = self.youtube_api.get_playlist_songs(playlist_id)
                            if songs:
                                youtube_url = songs[0]['url']
                                volume = get_config("audio_settings.music_volume", 50, device_id=self.device_id)
                                # Set play command, actual MQTT sending handled externally
                                self.result = {
                                    "command": "play",
                                    "url": youtube_url,
                                    "volume": volume
                                }

                                # Update playback queue to entire playlist
                                self.play_queue = songs
                                self.current_index = 0
                                self.current_song = songs[0]
                                logger.info(f"Loaded playlist to queue, total {len(songs)} songs")

                                return f"Now playing playlist: {playlists[playlist_index]['title']}"
                            else:
                                return "Playlist is empty"
                        else:
                            return "Invalid playlist index"
                    return "YouTube API not initialized"
                except Exception as e:
                    logger.error(f"Error playing playlist: {e}")
                    return f"Playback error: {str(e)}"

            elif function_name == "pause":
                try:
                    result = self.pause_music()
                    return "Music paused" if result else "Pause failed"
                except Exception as e:
                    logger.error(f"Error pausing playback: {e}")
                    return f"Pause error: {str(e)}"

            elif function_name == "resume":
                try:
                    result = self.resume_music()
                    return "Resuming music playback" if result else "Resume failed"
                except Exception as e:
                    logger.error(f"Error resuming playback: {e}")
                    return f"Resume error: {str(e)}"

            else:
                return f"Unsupported function: {function_name}"

        except Exception as e:
            logger.error(f"Error processing music response: {str(e)}")
            return f"Processing error: {str(e)}"

    def _get_next_song(self):
        """Get playback data for next song

        Returns:
            dict: MQTT command data, returns None if no next song
        """
        try:
            # Check if there's a next song
            if self.current_index + 1 < len(self.play_queue):
                self.current_index += 1
                next_song = self.play_queue[self.current_index]
                self.current_song = next_song

                volume = get_config("audio_settings.music_volume", 50, device_id=self.device_id)
                logger.info(f"Playing next song: {next_song.get('title', 'Unknown')} ({self.current_index + 1}/{len(self.play_queue)})")
                return {
                    "type": "play_music",
                    "url": next_song['url'],
                    "volume": volume,
                    "title": next_song.get('title', 'Unknown')
                }
            else:
                # Reached end of queue, try to get more recommended songs
                if self.current_song and self.youtube_api:
                    logger.debug("Playback queue ended, trying to get more recommended songs")
                    recommended_songs = self._get_recommendations_for_song(self.current_song)
                    if recommended_songs:
                        # Add new recommended songs to end of queue
                        self.play_queue.extend(recommended_songs)
                        self.current_index += 1
                        next_song = self.play_queue[self.current_index]
                        self.current_song = next_song

                        volume = get_config("audio_settings.music_volume", 50, device_id=self.device_id)
                        logger.info(f"Got {len(recommended_songs)} new recommended songs, playing: {next_song.get('title', 'Unknown')}")
                        return {
                            "type": "play_music",
                            "url": next_song['url'],
                            "volume": volume,
                            "title": next_song.get('title', 'Unknown')
                        }
                    else:
                        logger.warning("Unable to get more recommended songs")

                logger.info("Reached end of playback queue, no more songs")
                return None

        except Exception as e:
            logger.error(f"Error getting next song: {e}")
            return None

    def _get_previous_song(self):
        """Get playback data for previous song

        Returns:
            dict: MQTT command data, returns None if no previous song
        """
        try:
            # Check if there's a previous song
            if self.current_index > 0 and self.play_queue:
                self.current_index -= 1
                prev_song = self.play_queue[self.current_index]
                self.current_song = prev_song

                volume = get_config("audio_settings.music_volume", 50, device_id=self.device_id)
                return {
                    "type": "play_music",
                    "url": prev_song['url'],
                    "volume": volume,
                    "title": prev_song.get('title', 'Unknown')
                }
            else:
                logger.info("Reached beginning of playback queue")
                return None

        except Exception as e:
            logger.error(f"Error getting previous song: {e}")
            return None

    def _update_current_song_info(self, song_info):
        """Update current playing song information

        Args:
            song_info: Song information dictionary containing title, url, author, etc.
        """
        try:
            self.current_song = song_info

            # If playback queue is empty, add current song to queue
            if not self.play_queue:
                self.play_queue = [song_info]
                self.current_index = 0
            else:
                # Check if current song is already in queue
                found = False
                for i, song in enumerate(self.play_queue):
                    if song.get('url') == song_info.get('url'):
                        self.current_index = i
                        found = True
                        break

                # If not in queue, add to beginning of queue
                if not found:
                    self.play_queue.insert(0, song_info)
                    self.current_index = 0

            logger.debug(f"Updated current song info: {song_info.get('title', 'Unknown')}")

        except Exception as e:
            logger.error(f"Error updating current song info: {e}")

    def _update_current_song_info_with_queue(self, songs_list):
        """Update current playing song info and set playback queue (used when searching songs to add recommended songs simultaneously)

        Args:
            songs_list: Song information list, first song is the searched song, rest are recommended songs
        """
        try:
            if not songs_list:
                logger.warning("Song list is empty, cannot update queue")
                return

            # Set current song as first song (searched song)
            self.current_song = songs_list[0]

            # Set playback queue to all songs
            self.play_queue = songs_list.copy()
            self.current_index = 0

            logger.info(f"Updated playback queue: current song '{self.current_song.get('title', 'Unknown')}', queue has {len(self.play_queue)} songs total")

            # Log song information in queue (for debugging)
            for i, song in enumerate(self.play_queue[:5]):  # Only log first 5 songs
                logger.debug(f"Queue {i+1}: {song.get('title', 'Unknown')} - {song.get('author', 'Unknown')}")

            if len(self.play_queue) > 5:
                logger.debug(f"... {len(self.play_queue) - 5} more songs in queue")

        except Exception as e:
            logger.error(f"Error updating song queue: {e}")

    def _get_recommendations_for_song(self, song_info):
        """Get recommended songs based on current song

        Args:
            song_info: Current song information dictionary

        Returns:
            list: Recommended songs list
        """
        try:
            if not song_info or not self.youtube_api:
                return []

            song_title = song_info.get('title', '')
            if not song_title:
                return []

            logger.debug(f"Getting recommendations based on song '{song_title}'")

            # Extract song name (remove possible artist name)
            import re
            parts = re.split(r'[-–—]', song_title, maxsplit=1)
            song_name = parts[-1].strip() if len(parts) > 1 else song_title

            # Search related songs
            recommended_songs = self.youtube_api.search_song(f"{song_name}", max_results=10)

            if recommended_songs:
                # Filter out current song
                current_url = song_info.get('url', '')
                filtered_songs = [song for song in recommended_songs if song.get('url') != current_url]

                logger.info(f"Got {len(filtered_songs)} recommended songs")
                return filtered_songs
            else:
                logger.warning("No recommended songs found")
                return []

        except Exception as e:
            logger.error(f"Error getting recommended songs: {e}")
            return []

# Test code
if __name__ == "__main__":
    # Create MusicHandler instance (test mode, no UDP device manager needed)
    music_handler = MusicHandler()

    # Test user inputs
    test_inputs = [
        "播放第一个歌单的歌曲",  # This should match play_playlist not playlist_songs
        "我有什么歌单",  # Test playlist query
        "第一个歌单有什么歌",  # Test playlist songs query
        "来一首周杰伦",  # Test single song playback
        "暂停播放",  # Test pause
        "继续播放",  # Test resume
    ]

    print("\n=== Testing Music Functions ===\n")

    # Test each function separately
    for test_input in test_inputs:
        print(f"\nTest input: '{test_input}'")

        # Test process_music_query
        response, success, chat_data = music_handler.process_music_query(test_input)
        if success:
            print(f"✅ Match successful")
            if response:
                print(f"Response: {response[:100]}...")
            else:
                print("Command processed (no response message)")
        else:
            print("❌ No function matched")

    print("\n=== Testing Complete ===")
    print("\nNote: Actual MQTT command sending needs to be tested in environment with UDP device manager")