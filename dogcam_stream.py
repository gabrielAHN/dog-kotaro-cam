import io
import time
from threading import Condition, Thread, Lock, Semaphore
from flask import Flask, Response, render_template_string, request
import board
from picamera2 import Picamera2
from picamera2.encoders import MJPEGEncoder
from picamera2.outputs import FileOutput
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from dotenv import load_dotenv
import os
import signal  # For socket.send fix
import multiprocessing as mp

# Ignore SIGPIPE to prevent socket.send exceptions on client disconnects
signal.signal(signal.SIGPIPE, signal.SIG_IGN)

try:
    import adafruit_dht
except ImportError:
    adafruit_dht = None

load_dotenv()

app = Flask(__name__)

USERNAME = os.getenv('USERNAME')
PASSWORD = os.getenv('PASSWORD')

PAGE = """\
<html>
<head>
<title>Dog Cam with Temperature</title>
</head>
<body>
<center><h1>Live Stream of Your Dog</h1></center>
<center><img src="stream.mjpg" width="640" height="480"></center>
</body>
</html>
"""

class StreamingOutput(FileOutput):
    def __init__(self):
        self.frame = None
        self.buffer = io.BytesIO()
        self.condition = Condition()

    def outputframe(self, frame, keyframe=True, timestamp=None, packet=None, audio=None):
        self.buffer.write(frame)
        if keyframe:
            self.buffer.seek(0)
            with self.condition:
                self.frame = self.buffer.getvalue()
                self.condition.notify_all()
            self.buffer.seek(0)
            self.buffer.truncate()

# Shared queue for latest frames (maxsize=1 to always have the most recent)
frame_queue = mp.Queue(maxsize=1)

# Globals for capture process (not shared)
picam2 = None
dht_device = None
output = None
init_lock = Lock()  # Not needed across processes, but kept for consistency

def initialize_camera_and_sensor():
    global picam2, dht_device, output
    with init_lock:
        if picam2 is None:
            for attempt in range(5):  # Retry camera init
                try:
                    picam2 = Picamera2()
                    picam2.configure(picam2.create_video_configuration(main={"size": (640, 480)}))
                    output = StreamingOutput()
                    picam2.start_recording(MJPEGEncoder(), output)
                    print("Camera initialized successfully.")
                    break
                except Exception as e:
                    time.sleep(1)
            else:
                print("Failed to initialize camera after retries.")

        if adafruit_dht and dht_device is None:
            for attempt in range(5):  # Retry DHT init silently
                try:
                    dht_device = adafruit_dht.DHT22(board.D4, use_pulseio=False)  # Fix for "unable to set line 4 to input"
                    print("DHT sensor initialized successfully.")
                    break
                except Exception:
                    time.sleep(1)
            else:
                print("Failed to initialize DHT after retries. Check wiring (pull-up resistor on GPIO4).")

def update_temperature():
    font = ImageFont.load_default()
    while True:
        initialize_camera_and_sensor()
        if dht_device and picam2:
            temperature_c = None
            for attempt in range(3):
                try:
                    temperature_c = dht_device.temperature
                    break
                except RuntimeError:
                    time.sleep(2)  # Silent retry
            if temperature_c is not None:
                overlay = Image.new("RGBA", (640, 60), (0, 0, 0, 128))
                draw = ImageDraw.Draw(overlay)
                draw.text((10, 10), f"Temperature: {temperature_c:.1f} C", font=font, fill=(255, 255, 255, 255))
                overlay_array = np.array(overlay)
                picam2.set_overlay(overlay_array)
            else:
                picam2.set_overlay(None)
        elif picam2:
            picam2.set_overlay(None)
        time.sleep(5)

def camera_capture_process():
    initialize_camera_and_sensor()  # Init in this process
    # Start temperature thread in this process
    temp_thread = Thread(target=update_temperature)
    temp_thread.daemon = True
    temp_thread.start()
    while True:
        with output.condition:
            output.condition.wait()
            frame = output.frame
        try:
            frame_queue.put_nowait(frame)  # Put latest frame, overwrite if full
        except mp.queues.Full:
            pass  # Discard if not consumed

# Create the process (start in hook)
capture_proc = mp.Process(target=camera_capture_process, daemon=False)

# Semaphore to limit concurrent stream viewers (max 5)
stream_semaphore = Semaphore(5)

def check_auth():
    auth = request.authorization
    if not auth or auth.username != USERNAME or auth.password != PASSWORD:
        return Response('Could not verify access.\nLogin required', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})
    return None

@app.before_request
def require_basic_auth():
    response = check_auth()
    if response:
        return response

@app.route('/')
def index():
    return render_template_string(PAGE)

@app.route('/stream.mjpg')
def stream():
    if not stream_semaphore.acquire(blocking=False):
        return Response("Max viewers reached (5). Try again later.", status=503)

    def generate():
        try:
            # Brief wait for initial frame if queue empty
            if frame_queue.empty():
                time.sleep(1)
            while True:
                try:
                    frame = frame_queue.get(timeout=5)  # Timeout to avoid permanent block
                    yield (b'--FRAME\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                except mp.queues.Empty:
                    # Yield placeholder on timeout (minimal empty JPEG)
                    yield (b'--FRAME\r\nContent-Type: image/jpeg\r\n\r\n' + b'\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00\x48\x00\x48\x00\x00\xFF\xD9' + b'\r\n')
        finally:
            stream_semaphore.release()

    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=FRAME')