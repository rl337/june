"""
Locust load test for Gateway WebSocket connections.

Tests:
- WebSocket connection establishment
- Real-time message sending and receiving
- Concurrent WebSocket connections
- Message throughput
"""
import asyncio
import json
import random
import time
import websocket
from locust import User, task, between, events
import logging
import threading

logger = logging.getLogger(__name__)

SAMPLE_MESSAGES = [
    {"type": "text", "text": "Hello, how are you?"},
    {"type": "text", "text": "What is the weather like today?"},
    {"type": "text", "text": "Tell me a short story."},
    {"type": "text", "text": "Explain quantum computing."},
    {"type": "text", "text": "What are the benefits of exercise?"},
]


class WebSocketClient:
    """WebSocket client for load testing."""
    
    def __init__(self, host, user_id, token):
        self.host = host.replace("http://", "ws://").replace("https://", "wss://")
        self.user_id = user_id
        self.token = token
        self.ws = None
        self.connected = False
        self.messages_received = 0
        self.errors = 0
    
    def connect(self):
        """Establish WebSocket connection."""
        try:
            url = f"{self.host}/ws/{self.user_id}"
            headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
            
            self.ws = websocket.WebSocketApp(
                url,
                header=headers,
                on_open=self.on_open,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close
            )
            
            # Run in a separate thread
            self.ws_thread = threading.Thread(target=self.ws.run_forever)
            self.ws_thread.daemon = True
            self.ws_thread.start()
            
            # Wait for connection (with timeout)
            timeout = 5
            start_time = time.time()
            while not self.connected and (time.time() - start_time) < timeout:
                time.sleep(0.1)
            
            return self.connected
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            self.errors += 1
            return False
    
    def on_open(self, ws):
        """Called when WebSocket connection is opened."""
        self.connected = True
        logger.debug(f"WebSocket connected for user {self.user_id}")
    
    def on_message(self, ws, message):
        """Called when a message is received."""
        try:
            data = json.loads(message)
            self.messages_received += 1
            logger.debug(f"Received message: {data}")
        except Exception as e:
            logger.error(f"Error parsing message: {e}")
            self.errors += 1
    
    def on_error(self, ws, error):
        """Called when an error occurs."""
        logger.error(f"WebSocket error: {error}")
        self.errors += 1
    
    def on_close(self, ws, close_status_code, close_msg):
        """Called when WebSocket connection is closed."""
        self.connected = False
        logger.debug(f"WebSocket closed for user {self.user_id}")
    
    def send_message(self, message):
        """Send a message through WebSocket."""
        if not self.connected or not self.ws:
            return False
        
        try:
            message_str = json.dumps(message)
            self.ws.send(message_str)
            return True
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            self.errors += 1
            return False
    
    def close(self):
        """Close WebSocket connection."""
        if self.ws:
            self.ws.close()
        if self.ws_thread:
            self.ws_thread.join(timeout=2)


class GatewayWebSocketUser(User):
    """Load test user for Gateway WebSocket connections."""
    
    wait_time = between(2, 5)  # Wait 2-5 seconds between operations
    
    def on_start(self):
        """Setup user session."""
        self.user_id = f"ws_user_{random.randint(1000, 9999)}"
        
        # Get auth token first (using HTTP client)
        import requests
        try:
            host = self.environment.host or "http://localhost:8000"
            response = requests.post(
                f"{host}/auth/token",
                params={"user_id": self.user_id},
                timeout=5
            )
            if response.status_code == 200:
                self.token = response.json().get("access_token")
            else:
                self.token = None
                logger.warning(f"Failed to get auth token for {self.user_id}")
        except Exception as e:
            logger.error(f"Error getting auth token: {e}")
            self.token = None
        
        # Connect WebSocket
        host = self.environment.host or "http://localhost:8000"
        self.ws_client = WebSocketClient(host, self.user_id, self.token)
        if not self.ws_client.connect():
            logger.error(f"Failed to connect WebSocket for {self.user_id}")
            # Still continue - some tests might work without connection
    
    def on_stop(self):
        """Cleanup user session."""
        if hasattr(self, 'ws_client'):
            self.ws_client.close()
    
    @task(10)
    def send_text_message(self):
        """Send a text message through WebSocket."""
        if not self.ws_client or not self.ws_client.connected:
            return
        
        message = random.choice(SAMPLE_MESSAGES)
        start_time = time.time()
        
        success = self.ws_client.send_message(message)
        
        response_time = (time.time() - start_time) * 1000  # Convert to ms
        
        # Report to Locust
        if success:
            events.request_success.fire(
                request_type="WebSocket",
                name="/ws/send",
                response_time=response_time,
                response_length=0
            )
        else:
            events.request_failure.fire(
                request_type="WebSocket",
                name="/ws/send",
                response_time=response_time,
                response_length=0,
                exception=Exception("Failed to send message")
            )
    
    @task(5)
    def check_connection(self):
        """Check if WebSocket connection is still alive."""
        if not self.ws_client:
            return
        
        start_time = time.time()
        is_connected = self.ws_client.connected
        response_time = (time.time() - start_time) * 1000
        
        if is_connected:
            events.request_success.fire(
                request_type="WebSocket",
                name="/ws/check",
                response_time=response_time,
                response_length=0
            )
        else:
            events.request_failure.fire(
                request_type="WebSocket",
                name="/ws/check",
                response_time=response_time,
                response_length=0,
                exception=Exception("WebSocket not connected")
            )
