"""
Simplified HTTP server for emergency use
"""
import http.server
import socketserver
import json
import threading
import time
import datetime
import sys
import os

# Configuration
PORT = 10080
HOST = "0.0.0.0"  # Bind to all interfaces

# Print startup banner
print(f"\n\n=== EMERGENCY SERVER STARTING ON {HOST}:{PORT} ===\n\n")
print(f"Current working directory: {os.getcwd()}")
print(f"Python version: {sys.version}")

# Create a simple HTTP request handler
class SimpleHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/health' or self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            response = {
                "status": "ok",
                "message": "Emergency server is running!",
                "timestamp": datetime.datetime.now().isoformat()
            }
            
            self.wfile.write(json.dumps(response).encode('utf-8'))
        
        elif self.path == '/sse':
            self.send_response(200)
            self.send_header('Content-type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            # Send initial connection event
            initial_message = {
                "event_type": "connection_status",
                "status": "connected",
                "message": "Connected to emergency SSE stream"
            }
            
            self.wfile.write(f"data: {json.dumps(initial_message)}\n\n".encode('utf-8'))
            self.wfile.flush()
            
            # Keep connection open and send periodic updates
            count = 0
            try:
                while True:
                    count += 1
                    self.wfile.write(f": keepalive {datetime.datetime.now().isoformat()}\n\n".encode('utf-8'))
                    self.wfile.flush()
                    
                    # Every 5 seconds send a test event
                    if count % 5 == 0:
                        test_event = {
                            "event_type": "test_event",
                            "message": f"Test event {count}",
                            "timestamp": datetime.datetime.now().isoformat()
                        }
                        self.wfile.write(f"data: {json.dumps(test_event)}\n\n".encode('utf-8'))
                        self.wfile.flush()
                    
                    time.sleep(1)
            except BrokenPipeError:
                print("Client disconnected from SSE stream")
                return
        
        elif self.path == '/ws':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b"WebSocket not supported in emergency mode, please use SSE endpoint")
        
        else:
            self.send_response(404)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Not found")
    
    def log_message(self, format, *args):
        """Override to print to stdout directly"""
        print(f"{self.client_address[0]} - [{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {format % args}")

def start_server():
    """Start the HTTP server"""
    with socketserver.TCPServer((HOST, PORT), SimpleHandler) as httpd:
        print(f"Server started at http://{HOST}:{PORT}")
        print(f"Test with: http://localhost:{PORT}/health")
        print(f"SSE endpoint: http://localhost:{PORT}/sse")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("Shutting down server")
            httpd.server_close()

if __name__ == "__main__":
    try:
        start_server()
    except Exception as e:
        print(f"Server failed to start: {e}")
        sys.exit(1)
