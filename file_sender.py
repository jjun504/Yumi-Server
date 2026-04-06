import os
import sys
import time
import socket
import requests
import logging
import argparse
import glob
from requests_toolbelt import MultipartEncoder
import socketio
from concurrent.futures import ThreadPoolExecutor

# Configuration
UDP_DISCOVERY_PORT = 50002
BUFFER_SIZE = 4096
DISCOVER_REQUEST = b"FILE_SERVER_REQUEST"
MAX_WORKERS = 10  # Maximum number of concurrent uploads
TIMEOUT = 10  # Request timeout in seconds

# Logging setup
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# SocketIO setup
sio = socketio.Client()

class FileSender:
    def __init__(self, server_address=None, port=5001):
        self.server_address = server_address
        self.server_port = port
        self.server_url = None
        self.connected = False
        self.batch_mode = False
        self.file_queue = []
        self.stats = {'total': 0, 'success': 0, 'failed': 0, 'bytes_sent': 0}
    
    def discover_server(self):
        """Discover file transfer server using UDP broadcast"""
        logger.info("Discovering file transfer server...")
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(3)  # Set timeout for discovery
        
        try:
            # Broadcast discovery request
            sock.sendto(DISCOVER_REQUEST, ('<broadcast>', UDP_DISCOVERY_PORT))
            
            # Wait for response
            while True:
                try:
                    data, server = sock.recvfrom(BUFFER_SIZE)
                    if data.startswith(b"FILE_SERVER_RESPONSE_"):
                        port = int(data.split(b"_")[-1])
                        logger.info(f"Discovered server at {server[0]}:{port}")
                        return server[0], port
                except socket.timeout:
                    break
        except Exception as e:
            logger.error(f"Discovery error: {e}")
        finally:
            sock.close()
        
        logger.warning("No server found via discovery")
        return None, None
    
    def connect(self):
        """Connect to the file transfer server"""
        if not self.server_address:
            discovered_addr, discovered_port = self.discover_server()
            if discovered_addr:
                self.server_address = discovered_addr
                self.server_port = discovered_port
            else:
                logger.error("No server address provided and discovery failed")
                return False
        
        self.server_url = f"http://{self.server_address}:{self.server_port}"
        
        # Connect to SocketIO server
        try:
            sio.connect(self.server_url, wait_timeout=5)
            self.connected = True
            logger.info(f"Connected to server at {self.server_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to server: {e}")
            self.connected = False
            return False
    
    def upload_file(self, file_path):
        """Upload a single file to the server"""
        if not self.connected and not self.connect():
            logger.error("Not connected to server")
            return False
        
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return False
        
        try:
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            
            start_time = time.time()
            
            # Create multipart form data
            with open(file_path, 'rb') as file:
                m = MultipartEncoder(
                    fields={'file': (file_name, file, 'application/octet-stream')}
                )
                headers = {'Content-Type': m.content_type}
                
                # Send POST request
                response = requests.post(
                    f"{self.server_url}/upload", 
                    data=m,
                    headers=headers,
                    timeout=TIMEOUT
                )
            
            elapsed = time.time() - start_time
            
            if response.status_code == 200 and response.json().get('status') == 'success':
                transfer_rate = file_size / (elapsed * 1024) if elapsed > 0 else 0
                logger.info(f"Uploaded {file_name} ({file_size/1024:.2f} KB) in {elapsed:.2f}s ({transfer_rate:.2f} KB/s)")
                
                # Update stats
                self.stats['success'] += 1
                self.stats['bytes_sent'] += file_size
                
                return True
            else:
                logger.error(f"Upload failed: {response.text}")
                self.stats['failed'] += 1
                return False
            
        except Exception as e:
            logger.error(f"Upload error for {file_path}: {e}")
            self.stats['failed'] += 1
            return False
    
    def start_batch_upload(self, file_paths):
        """Start a batch upload process"""
        if not self.connected and not self.connect():
            logger.error("Not connected to server")
            return False
        
        self.batch_mode = True
        self.file_queue = file_paths
        self.stats = {'total': len(file_paths), 'success': 0, 'failed': 0, 'bytes_sent': 0}
        
        logger.info(f"Starting batch upload of {len(file_paths)} files")
        
        # Signal the start of batch upload
        sio.emit('batch_upload_start', {'file_count': len(file_paths)})
        
        # Wait for the server to acknowledge
        time.sleep(0.5)
        
        # Start upload process with thread pool
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            results = list(executor.map(self.upload_file, file_paths))
        
        total_elapsed = time.time() - start_time
        success_count = sum(1 for r in results if r)
        fail_count = len(results) - success_count
        
        # Signal batch upload complete
        sio.emit('batch_upload_complete', {'file_count': success_count})
        
        logger.info(f"Batch upload completed in {total_elapsed:.2f}s")
        logger.info(f"Files: {success_count} succeeded, {fail_count} failed")
        logger.info(f"Total data sent: {self.stats['bytes_sent']/1024:.2f} KB")
        
        if self.stats['bytes_sent'] > 0 and total_elapsed > 0:
            avg_speed = self.stats['bytes_sent'] / (total_elapsed * 1024)
            logger.info(f"Average speed: {avg_speed:.2f} KB/s")
        
        self.batch_mode = False
        return success_count, fail_count
    
    def disconnect(self):
        """Disconnect from the server"""
        if self.connected:
            try:
                sio.disconnect()
                logger.info("Disconnected from server")
            except Exception as e:
                logger.error(f"Error during disconnect: {e}")
            
            self.connected = False


# SocketIO event handlers
@sio.event
def connect():
    logger.info("SocketIO connected")

@sio.event
def disconnect():
    logger.info("SocketIO disconnected")

@sio.event
def server_info(data):
    logger.info(f"Server info: {data}")


def main():
    parser = argparse.ArgumentParser(description="File Transfer Client")
    parser.add_argument('--server', '-s', help='Server address (IP or hostname)', default=None)
    parser.add_argument('--port', '-p', type=int, help='Server port', default=5001)
    parser.add_argument('--files', '-f', nargs='+', help='Files to upload (accepts glob patterns)')
    parser.add_argument('--discover', '-d', action='store_true', help='Discover server on local network')
    args = parser.parse_args()
    
    # Create sender client
    sender = FileSender(args.server, args.port)
    
    # Check connection method
    if args.discover or not args.server:
        discovered_addr, discovered_port = sender.discover_server()
        if discovered_addr:
            sender.server_address = discovered_addr
            sender.server_port = discovered_port
        else:
            logger.error("Server discovery failed")
            return 1
    
    # Connect to server
    if not sender.connect():
        logger.error("Failed to connect to server")
        return 1
    
    # Handle file upload
    try:
        if args.files:
            # Expand glob patterns
            file_paths = []
            for pattern in args.files:
                matched_files = glob.glob(pattern, recursive=True)
                if matched_files:
                    file_paths.extend(matched_files)
                else:
                    logger.warning(f"No files match pattern: {pattern}")
            
            if not file_paths:
                logger.error("No files to upload")
                return 1
            
            logger.info(f"Found {len(file_paths)} files to upload")
            
            if len(file_paths) == 1:
                # Single file upload
                if sender.upload_file(file_paths[0]):
                    logger.info("File uploaded successfully")
                    return 0
                else:
                    logger.error("File upload failed")
                    return 1
            else:
                # Batch upload
                success, failed = sender.start_batch_upload(file_paths)
                
                if failed == 0:
                    logger.info("All files uploaded successfully")
                    return 0
                else:
                    logger.warning(f"{failed} files failed to upload")
                    return 1
        else:
            logger.error("No files specified for upload")
            return 1
            
    finally:
        # Always disconnect in the end
        sender.disconnect()


if __name__ == '__main__':
    sys.exit(main())