import sys
import os
import socket
import PyQt6
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QLineEdit
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QImage, QPixmap

# --- CONFIGURATION ---
DISCOVERY_PORT = 8499   # Changed from 6499
VIDEO_PORT = 8500       # Changed from 6500 (was blocked)
TRACKPORT = 8501
MAX_UDP_BUFFER = 65536 
drone_ip = None

# --- MAC OS FIX ---
try:
    dirname = os.path.dirname(PyQt6.__file__)
    plugin_path = os.path.join(dirname, 'Qt6', 'plugins')
    os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = plugin_path
except:
    pass

# --- VIDEO RECEIVER THREAD ---
class VideoThread(QThread):
    change_pixmap_signal = pyqtSignal(QImage)

    def run(self):
        print(f"[VIDEO THREAD] Listening on port {VIDEO_PORT}...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            sock.bind(("0.0.0.0", VIDEO_PORT))
        except OSError:
            print(f"[ERROR] Port {VIDEO_PORT} is busy. Close other apps.")
            return

        datagram_buffer = b""

        while True:
            try:
                # 1. Receive Packet
                packet, _ = sock.recvfrom(MAX_UDP_BUFFER)

                # 2. Check for End of Frame
                if packet == b"END":
                    if len(datagram_buffer) > 0:
                        qt_img = QImage.fromData(datagram_buffer)
                        if not qt_img.isNull():
                            self.change_pixmap_signal.emit(qt_img)
                    
                    # Clear buffer for next frame
                    datagram_buffer = b""
                else:
                    # 3. Append Chunk
                    datagram_buffer += packet

            except Exception as e:
                # Reset buffer on error
                datagram_buffer = b""

# --- MAIN GUI CLASS ---
class GroundStation(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Drone Tracker") 
        self.resize(1000, 800)

        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)
        
        # This loop blocks the window from opening until the Drone is found.
        self.connected = False
        print("[STARTUP] Looking for Drone...")
        
        while not self.connected:
            self.connected = self.connect()
            if not self.connected:
                # Process GUI events to prevent "Not Responding"
                QApplication.processEvents() 
        
        # --- UI SETUP ---
        self.video_label = QLabel("Video Feed Here")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: black; color: white; font-size: 20px;")
        self.video_label.setMinimumSize(640, 480)
        self.main_layout.addWidget(self.video_label)

        self.textBox = QLineEdit()
        self.textBox.setPlaceholderText("Enter Target Description")
        self.textBox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.textBox.setStyleSheet("background-color: grey; color: white; font-size: 18px; border-radius: 10px;")
        self.textBox.setFixedHeight(60)
        self.main_layout.addWidget(self.textBox)

        self.track_button = QPushButton("START TRACKING")
        self.track_button.setMinimumHeight(50) 
        self.track_button.setStyleSheet("font-size: 18px;")
        self.track_button.clicked.connect(self.start_tracking)
        self.main_layout.addWidget(self.track_button)

        # --- START VIDEO THREAD ---
        if self.connected:
            self.thread = VideoThread()
            self.thread.change_pixmap_signal.connect(self.update_image)
            self.thread.start()

    def connect(self):
        global drone_ip, VIDEO_PORT
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            # Bind to discovery port
            sock.bind(("0.0.0.0", DISCOVERY_PORT))
            sock.settimeout(1.0) # Check every 1 second

            # Wait for "DISCOVER" message
            msg, addr = sock.recvfrom(1024)
            
            if msg.strip() == b"DISCOVER_STREAMING_SERVER":
                drone_ip = addr[0]
                print(f"[DISCOVERY] Found Drone at {drone_ip}")
                
                # Send our IP:PORT back to the drone
                my_ip = socket.gethostbyname(socket.gethostname())
                reply = f"{my_ip}:{VIDEO_PORT}".encode()
                sock.sendto(reply, addr)
                
                sock.close()
                return True
                
        except socket.timeout:
            print("Searching for drone...")
        except Exception as e:
            print(f"[ERROR] {e}")

        sock.close()
        return False

    @pyqtSlot(QImage)
    def update_image(self, qt_img):
        # Scale image to fit label
        scaled_pixmap = QPixmap.fromImage(qt_img).scaled(
            self.video_label.width(), 
            self.video_label.height(), 
            Qt.AspectRatioMode.KeepAspectRatio
        )
        self.video_label.setPixmap(scaled_pixmap)

    def start_tracking(self): 
        global drone_ip
        user_input = self.textBox.text()
        if not user_input:
            print("Please enter a target description.")
            return
        print(f"SAVED TARGET: {user_input}")

        self.track_button.setText("Currently Tracking")
        self.track_button.setStyleSheet("font-size: 18px ; background-color: Red; color: White;")
        self.track_button.font().setBold(True)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        message = user_input.encode()
        sock.sendto(message, (drone_ip, TRACKPORT))
        sock.close()

        

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = GroundStation()
    window.show()
    sys.exit(app.exec())
