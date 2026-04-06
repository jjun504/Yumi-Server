import os
import googleapiclient.discovery
import google_auth_oauthlib.flow
import google.auth.transport.requests
import pickle
from yt_dlp import YoutubeDL
from loguru import logger
import socket
import sys
import time

# logger.remove()
# import log_saver
logger.add("youtube_api_debug.log", level="DEBUG", rotation="10 MB")

class YouTubeAPI:
    SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
    
    def __init__(self, client_secret_file="youtube/client_secret.json", token_path="youtube/token.pickle"):
        """Initialize YouTube API client"""
        logger.debug("Starting YouTubeAPI initialization")
        self.client_secret_file = client_secret_file
        self.token_path = token_path
        
        # Check if client secret file exists
        if not os.path.exists(client_secret_file):
            logger.error(f"Client secret file not found: {client_secret_file}")
            raise FileNotFoundError(f"Client secret file not found: {client_secret_file}")
        
        # Check network connection
        self._check_network_connection()
        
        # Authentication
        # logger.debug("Starting authentication")
        # try:
        #     self.credentials = self._authenticate()
        #     logger.debug("Authentication completed")
        # except Exception as e:
        #     logger.error(f"Authentication failed: {str(e)}")
        #     raise
        
        # Build YouTube API client
        # try:
        #     logger.debug("Starting to build YouTube API client")
        #     self.youtube = googleapiclient.discovery.build(
        #         "youtube", "v3", 
        #         credentials=self.credentials
        #     )
        #     logger.debug("YouTube API client built successfully")
        # except Exception as e:
        #     logger.error(f"Failed to build YouTube API client: {str(e)}")
        #     raise
        logger.info("[Initialize][music] YouTube API client built successfully")


    def _check_network_connection(self):
        """Check network connection status"""
        try:
            # Try connecting to Google servers
            logger.debug("Checking connection to Google servers...")
            socket.create_connection(("www.googleapis.com", 443), timeout=5)
            logger.debug("Successfully connected to Google servers")
            return True
        except OSError as e:
            logger.warning(f"Unable to connect to Google servers: {str(e)}")
            
            # Try connecting to Baidu to check internet connectivity
            try:
                socket.create_connection(("www.baidu.com", 80), timeout=5)
                logger.debug("Can connect to Baidu but not Google")
                logger.warning("This may be due to network restrictions blocking Google services")
            except OSError:
                logger.error("Cannot connect to internet, please check network settings")
            return False

    def _authenticate(self):
        """Handle OAuth 2.0 authentication"""
        logger.debug("Starting OAuth authentication flow")
        creds = None

        # Try loading existing token
        if os.path.exists(self.token_path):
            logger.debug(f"Found existing token file: {self.token_path}")
            try:
                with open(self.token_path, "rb") as token_file:
                    creds = pickle.load(token_file)
                logger.debug("Successfully loaded existing token")
            except Exception as e:
                logger.error(f"Failed to load token: {str(e)}")

        # If no token or token expired
        if not creds:
            logger.debug("No valid token found, need to get new one")
        elif not creds.valid:
            logger.debug("Token expired, need to refresh or get new one")
            
            # Try refreshing token
            if creds.refresh_token:
                logger.debug("Attempting to refresh token...")
                try:
                    creds.refresh(google.auth.transport.requests.Request())
                    logger.debug("Token refresh successful")
                except Exception as e:
                    logger.error(f"Token refresh failed: {str(e)}")
                    creds = None

        # If no token or refresh failed, do authentication
        if not creds or not creds.valid:
            logger.debug("Need to perform full OAuth flow")
            try:
                logger.debug(f"Loading OAuth config from file: {self.client_secret_file}")
                flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                    self.client_secret_file, self.SCOPES
                )
                
                logger.warning("Starting local server for OAuth authorization, please complete login in browser")
                logger.warning("If browser doesn't open automatically, manually copy console link to authorize")
                creds = flow.run_local_server(port=8080)
                logger.debug("OAuth flow completed, authorization successful")

                # Save token
                logger.debug(f"Saving token to: {self.token_path}")
                os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
                with open(self.token_path, "wb") as token_file:
                    pickle.dump(creds, token_file)
                logger.debug("Token saved successfully")
            except Exception as e:
                logger.error(f"OAuth flow failed: {str(e)}")
                raise

        return creds

    def get_self_playlists(self, max_results=10):
        """Get current user's playlists"""
        logger.debug(f"Attempting to get personal playlists, max results: {max_results}")
        try:
            logger.debug("Building playlists.list request")
            request = self.youtube.playlists().list(
                part="snippet,contentDetails",
                mine=True,
                maxResults=max_results
            )
            
            logger.debug("Sending playlists.list request")
            start_time = time.time()
            response = request.execute()
            end_time = time.time()
            logger.debug(f"API response time: {end_time - start_time:.2f} seconds")
            
            playlists = []
            items_count = len(response.get("items", []))
            logger.debug(f"Received {items_count} playlists")
            
            for playlist in response.get("items", []):
                playlist_info = {
                    "title": playlist["snippet"]["title"],
                    "id": playlist["id"],
                    "item_count": playlist["contentDetails"]["itemCount"]
                }
                playlists.append(playlist_info)
                logger.debug("[music] Playlists available:")
                logger.debug(f"{playlists.index(playlist_info) + 1}. {playlist_info['title']}")
                
            return playlists
            
        except socket.timeout as e:
            logger.error(f"Get playlists request timeout: {str(e)}")
            return []
        except ConnectionError as e:
            logger.error(f"Get playlists connection error: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error getting playlists: {str(e)}")
            return []

    def get_playlist_songs(self, playlist_id, max_results=50):
        """Get songs from specified playlist"""
        logger.info(f"Attempting to get songs from playlist {playlist_id}, max results: {max_results}")
        try:
            logger.debug("Building playlistItems.list request")
            request = self.youtube.playlistItems().list(
                part="snippet",
                playlistId=playlist_id,
                maxResults=max_results
            )
            
            logger.debug("Sending playlistItems.list request")
            start_time = time.time()
            response = request.execute()
            end_time = time.time()
            logger.debug(f"API response time: {end_time - start_time:.2f} seconds")
            
            songs = []
            items_count = len(response.get("items", []))
            logger.debug(f"Received {items_count} songs")
            
            for item in response.get("items", []):
                snippet = item.get("snippet", {})
                video_id = snippet.get('resourceId', {}).get('videoId', '')
                
                # Get thumbnail - prioritize high quality
                thumbnails = snippet.get('thumbnails', {})
                thumbnail_url = ""
                
                # Check quality priority
                for quality in ['maxres', 'high', 'standard', 'medium', 'default']:
                    if quality in thumbnails:
                        thumbnail_url = thumbnails[quality].get('url', '')
                        break
                
                # Build song info
                song_info = {
                    "title": snippet.get("title", "Unknown Title"),
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "author": snippet.get("videoOwnerChannelTitle", "Unknown Author"),
                    "id": video_id,
                    "thumbnail": thumbnail_url,
                    "view_count": 0  # Default to 0, can be fetched later
                }
                songs.append(song_info)
                logger.info("[music] Songs available:")
                logger.info(f"{songs.index(song_info) + 1}. {song_info['title']} - by {song_info['author']}")
                
            # If view_count is needed, we can fetch it in batches (requires additional API calls)
            # Below is an example of fetching view_count
            if songs:
                self._fetch_video_statistics([song["id"] for song in songs], songs)
                
            return songs
            
        except socket.timeout as e:
            logger.error(f"Get songs request timeout: {str(e)}")
            return []
        except ConnectionError as e:
            logger.error(f"Get songs connection error: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error getting playlist songs: {str(e)}")
            return []

    def _fetch_video_statistics(self, video_ids, songs):
        """Fetch video view counts and other statistics"""
        try:
            # Use videos.list API to fetch video statistics
            # Note: YouTube API has quota limits, each request can handle up to 50 video IDs
            max_results_per_request = 50
            
            for i in range(0, len(video_ids), max_results_per_request):
                batch_ids = video_ids[i:i+max_results_per_request]
                
                logger.debug(f"Fetching statistics for {len(batch_ids)} videos")
                response = self.youtube.videos().list(
                    part="statistics",
                    id=",".join(batch_ids)
                ).execute()
                
                # Update view_count in the song list
                for item in response.get("items", []):
                    video_id = item["id"]
                    view_count = int(item.get("statistics", {}).get("viewCount", 0))
                    
                    # Find the corresponding song and update
                    for song in songs:
                        if song["id"] == video_id:
                            song["view_count"] = view_count
                            break
                
            logger.debug("Successfully fetched video statistics")
        except Exception as e:
            logger.error(f"Error fetching video statistics: {str(e)}")
            # If fetching statistics fails, retain the song list without accurate view_count

    def search_song(self, song_name, max_results=1):
        """Search for songs and return audio info"""
        logger.debug(f"Starting song search: {song_name}, max results: {max_results}")
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'extract_flat': True,
            'socket_timeout': 15,  # Increase timeout
            'retries': 5,          # Increase retry count
        }
        
        try:
            logger.debug("Initializing YoutubeDL")
            with YoutubeDL(ydl_opts) as ydl:
                logger.debug(f"Executing search query: ytsearch{max_results}:{song_name}")
                start_time = time.time()
                search_result = ydl.extract_info(f"ytsearch{max_results}:{song_name}", download=False)
                end_time = time.time()
                logger.debug(f"Search took: {end_time - start_time:.2f} seconds")
                
                songs_info = []
                if 'entries' in search_result and search_result['entries']:
                    entries_count = len(search_result['entries'])
                    logger.debug(f"Search returned {entries_count} results")
                    
                    for entry in search_result['entries']:
                        song_info = {
                            "title": entry['title'],
                            "url": entry['url'],
                            "author": entry.get('uploader', 'Unknown'),
                            "id": entry.get('id', ''),
                            "thumbnail": entry.get('thumbnails', [])[0].get('url', ''),
                            "view_count": entry.get('view_count', 0)
                        }
                        songs_info.append(song_info)
                        logger.debug(f"Found song: {song_info['title']} - by {song_info['author']}")
                    
                    logger.debug(f"Processing complete, returning {len(songs_info)} song info")
                    return songs_info
                else:
                    logger.warning(f"No matching songs found: {song_name}")
                    return []
                    
        except socket.timeout as e:
            logger.error(f"Search song request timeout: {str(e)}")
            return []
        except ConnectionError as e:
            logger.error(f"Search song connection error: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error searching song: {str(e)}")
            logger.exception("Detailed error information")  # This logs full exception stack
            return []

# Test functions
def test_network():
    """Test network connectivity"""
    try:
        logger.debug("Testing connection to Google servers")
        socket.create_connection(("www.googleapis.com", 443), timeout=5)
        logger.debug("Successfully connected to Google servers")
        
        logger.debug("Testing connection to YouTube servers")
        socket.create_connection(("www.youtube.com", 443), timeout=5)
        logger.debug("Successfully connected to YouTube servers")
        
        return True
    except Exception as e:
        logger.error(f"Network connection test failed: {str(e)}")
        return False

def test_yt_dlp(query="test music"):
    """Test yt-dlp functionality"""
    logger.debug(f"Testing yt-dlp search: {query}")
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'extract_flat': True,
        'socket_timeout': 15,
    }
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            logger.debug("Starting yt-dlp test search")
            start_time = time.time()
            result = ydl.extract_info(f"ytsearch1:{query}", download=False)
            end_time = time.time()
            
            logger.debug(f"Search took: {end_time - start_time:.2f} seconds")
            if 'entries' in result and result['entries']:
                logger.debug("yt-dlp search test successful")
                return True
            else:
                logger.warning("yt-dlp returned no search results")
                return False
    except Exception as e:
        logger.error(f"yt-dlp test failed: {str(e)}")
        return False

# Usage example
if __name__ == "__main__":
    logger.info("Starting YouTubeAPI tests")
    yt_api = YouTubeAPI()
    songs = yt_api.search_song("晚餐歌")
    print(songs)
    # Test network connection
    if not test_network():
        logger.error("Network connection test failed, cannot continue testing")
        sys.exit(1)
        
    # Test yt-dlp
    if not test_yt_dlp():
        logger.error("yt-dlp test failed, this may affect song search functionality")
    
    try:
        # Create API instance
        logger.debug("Creating YouTubeAPI instance")
        yt_api = YouTubeAPI()
        
        # Test song search
        logger.debug("Testing song search functionality")
        songs = yt_api.search_song("Jay Chou")
        if songs:
            logger.debug(f"Search test successful, found {len(songs)} songs")
        else:
            logger.warning("Search test found no songs")
        
        # Get own playlists
        logger.debug("Testing get playlists functionality")
        playlists = yt_api.get_self_playlists()
        
        # If playlists exist, get songs from first playlist
        if playlists:
            first_playlist_id = playlists[0]["id"]
            logger.debug(f"Testing get playlist songs functionality, playlist: {playlists[0]['title']}")
            songs = yt_api.get_playlist_songs(first_playlist_id)
            print(songs)
        
        logger.debug("YouTubeAPI tests completed")
        
    except Exception as e:
        logger.error(f"Error occurred during testing: {str(e)}")
        logger.exception("Detailed error information")