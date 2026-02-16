import socket
import cv2
import numpy as np
import tkinter as tk
import time
import threading as Thread
from ultralytics import YOLO

DISCOVERY_PORT = 8499   # Must match Ground Control
TRACKPORT = 8501        # Must match Ground Control
VIDEO_PORT = None
GROUNDED_IP = None

MAX_UDP = 8000  # safe chunk size (<65507) # for windows
Target = None

# Load model once at start
print("Loading YOLO...")
model = YOLO('yolov8n-seg.pt')

# Discover ground station IP
def discover_Ground():
    global GROUNDED_IP, VIDEO_PORT
    print("Looking for Ground ...")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(5)

    try:
        sock.sendto(b"DISCOVER_STREAMING_SERVER", ("255.255.255.255", DISCOVERY_PORT))
        data, addr = sock.recvfrom(1024)
        reply = data.decode().split(":")
        GROUNDED_IP = reply[0]
        VIDEO_PORT = int(reply[1])
        print(f"[FOUND] server at {GROUNDED_IP}:{VIDEO_PORT}")
        return True
    except socket.timeout:
        print("[ERROR] No server found.")
        return False
    finally:
        sock.close()

def videoStreamer():
    global GROUNDED_IP, VIDEO_PORT, Target

    print(f"Streaming to Ground Station at {GROUNDED_IP}:{VIDEO_PORT}")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    cap = cv2.VideoCapture(0)  # Use the first camera device

    if not cap.isOpened():
        print("Error: Could not open video device.")
        return
    
    # Start the tracking listener
    Thread.Thread(target=trackObject, daemon=True).start()
    
    try:
        while True:
            ret, frame = cap.read()

            if not ret:
                print("Could not read frame.")
                break
            
            # 1. Resize FIRST for speed and consistency
            frame = cv2.resize(frame, (640, 480))

            # --- YOLO LOGIC START ---
            if Target is not None:
                # Run tracking
                results = model.track(frame, persist=True, verbose=False)
                
                # Check results
                for r in results:
                    if r.boxes:
                        for i, box in enumerate(r.boxes):
                            # Get class name (e.g., 'person', 'cup')
                            cls_name = model.names[int(box.cls[0])]
                            
                            # Only draw if it matches our Target
                            if cls_name == Target:
                                # Draw Bounding Box
                                x1, y1, x2, y2 = map(int, box.xyxy[0])
                                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                                cv2.putText(frame, cls_name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                                
                                # Draw Segmentation Mask
                                if r.masks is not None:
                                    # Handle mask coordinates
                                    mask_points = np.int32([r.masks.xy[i]])
                                    cv2.polylines(frame, mask_points, True, (0, 255, 0), 2)
            # --- YOLO LOGIC END ---

            # Encode and Send
            ok, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 40])
            data = buffer.tobytes()

            for i in range(0, len(data), MAX_UDP):
                sock.sendto(data[i:i + MAX_UDP], (GROUNDED_IP, VIDEO_PORT))

            sock.sendto(b'END', (GROUNDED_IP, VIDEO_PORT))
            
            # Small sleep to prevent network congestion
            # time.sleep(0.01) 

    finally:
        cap.release()
        sock.close()
        print("Video streaming ended.")

def trackObject():
    global TRACKPORT
    global Target

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)


    sock.bind(("0.0.0.0", TRACKPORT))
    print(f"Listening for Tracking commands on {TRACKPORT}")

    while True:
        try:
            data, _ = sock.recvfrom(1024)
            if not data:
                continue
            
            # Decode and strip whitespace/newlines
            Dtarget = data.decode().strip()
            
            if Dtarget == "STOP":
                Target = None
                print("Tracking Stopped")
            else:
                Target = Dtarget
                print(f"Tracking target: {Target}")
                
        except Exception as e:
            print(f"[ERROR] {e}")


connected = False
while not connected:
    connected = discover_Ground()
    if not connected:
        print("Retrying discovery...")

# Set up video stream from ground station
videoStreamer()
