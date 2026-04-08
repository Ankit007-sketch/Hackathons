import cv2
import numpy as np
import threading
import pyttsx3
from flask import Flask, Response, jsonify, send_from_directory
import time
import urllib.request
import serial

# Flask app setup
app = Flask(__name__, static_folder=".", static_url_path="")

# Globals
current_color = "none"
last_spoken = "none"
latest_frame = None
frame_lock = threading.Lock()

# Arduino connection
try:
    arduino = serial.Serial('COM5', 9600)
    time.sleep(3)
    print("[Arduino] Connected on COM5")
except Exception as e:
    arduino = None
    print(f"[Arduino] Not connected: {e}")

# IP Webcam URL
WEBCAM_BASE = "http://100.85.72.42:8080"
STREAM_URL = f"{WEBCAM_BASE}/video"
SHOT_URL = f"{WEBCAM_BASE}/shot.jpg"

# Audio
def speak(text):
    def _run():
        try:
            eng = pyttsx3.init()
            eng.setProperty('rate', 150)
            eng.say(text)
            eng.runAndWait()
            del eng
        except Exception as e:
            print(f"[Audio error] {e}")

    threading.Thread(target=_run, daemon=True).start()

# Color Detection
def detect_color(hsv):
    mask_r = cv2.bitwise_or(
        cv2.inRange(hsv, np.array([0, 120, 70]), np.array([10, 255, 255])),
        cv2.inRange(hsv, np.array([170, 120, 70]), np.array([180, 255, 255]))
    )

    mask_y = cv2.inRange(hsv, np.array([20, 100, 100]), np.array([35, 255, 255]))
    mask_g = cv2.inRange(hsv, np.array([40, 50, 50]), np.array([90, 255, 255]))

    scores = {
        "red": cv2.countNonZero(mask_r),
        "yellow": cv2.countNonZero(mask_y),
        "green": cv2.countNonZero(mask_g)
    }

    best, best_val = max(scores.items(), key=lambda x: x[1])

    if best_val > 1200:
        return best
    else:
        return "none"

# Frame Processing
def _process_frame(frame):
    global current_color, last_spoken, latest_frame

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    detected = detect_color(hsv)

    # Only act when color changes
    if detected != current_color:
        current_color = detected

        if detected == "red":
            print("STOP")
            if arduino:
                arduino.write(b'STOP\n')

        elif detected == "green":
            print("MOVE")
            if arduino:
                arduino.write(b'MOVE\n')

        elif detected == "yellow":
            print("WAIT")
            if arduino:
                arduino.write(b'STOP\n')

    # Voice Output
    if detected != "none" and detected != last_spoken:
        last_spoken = detected
        print(f"[Detection] {detected.upper()} color")
        speak(f"{detected} color")

    elif detected == "none":
        last_spoken = "none"

    # Save frame for website
    ret, buf = cv2.imencode('.jpg', frame)

    if ret:
        with frame_lock:
            latest_frame = buf.tobytes()

# Background Worker
def background_worker():
    global latest_frame

    print(f"[Worker] Trying mobile camera stream: {STREAM_URL}")

    while True:
        try:
            stream = urllib.request.urlopen(STREAM_URL, timeout=8)
            buf = b""

            print("[Worker] Mobile stream connected")

            while True:
                chunk = stream.read(4096)

                if not chunk:
                    break

                buf += chunk

                start = buf.find(b'\xff\xd8')
                end = buf.find(b'\xff\xd9')

                if start != -1 and end != -1 and end > start:
                    jpg = buf[start:end + 2]
                    buf = buf[end + 2:]

                    frame = cv2.imdecode(
                        np.frombuffer(jpg, dtype=np.uint8),
                        cv2.IMREAD_COLOR
                    )

                    if frame is not None:
                        _process_frame(frame)

        except Exception as e:
            print(f"[Stream error] {e}")
            print("[Worker] Retrying in 3 seconds...")
            time.sleep(3)

# Flask Routes
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/video_feed')
def video_feed():
    def gen():
        while True:
            with frame_lock:
                if latest_frame:
                    yield (
                        b'--frame\r\n'
                        b'Content-Type: image/jpeg\r\n\r\n' +
                        latest_frame +
                        b'\r\n'
                    )
            time.sleep(0.04)

    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/status')
def status():
    return jsonify({"color": current_color})

# Main
if __name__ == '__main__':
    t = threading.Thread(target=background_worker, daemon=True)
    t.start()

    print("Dashboard ready → http://localhost:5000")

    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)