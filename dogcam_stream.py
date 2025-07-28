import io
import os
import time
import threading
import atexit
import board
import adafruit_dht
from dotenv import load_dotenv
from flask import Flask, Response, render_template, request
from flask_httpauth import HTTPBasicAuth
from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput

load_dotenv()

app = Flask(__name__)
auth = HTTPBasicAuth()
camera = Picamera2()
viewer_semaphore = threading.Semaphore(int(os.getenv('MAX_VIEWERS', 3)))

dht_device = adafruit_dht.DHT22(board.D4)
dht_lock = threading.Lock()


class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = threading.Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


output = StreamingOutput()


camera.configure(camera.create_video_configuration(main={"size": (640, 480)}))
camera.start_recording(JpegEncoder(), FileOutput(output))


def cleanup():
    camera.stop_recording()


atexit.register(cleanup)


@auth.verify_password
def verify_password(username, password):
    return username == os.getenv('BASIC_AUTH_USERNAME') and password == os.getenv('BASIC_AUTH_PASSWORD')


def gen():
    while True:
        with output.condition:
            output.condition.wait()
            frame = output.frame
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


@app.route('/')
@auth.login_required
def index():
    dog_name = os.getenv('DOG_NAME', 'Dog')
    return render_template('index.html', dog_name=dog_name)


@app.route('/video_feed')
@auth.login_required
def video_feed():
    if not viewer_semaphore.acquire(blocking=False):
        return "Max viewers reached. Try again later.", 503
    try:
        return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')
    finally:
        viewer_semaphore.release()


@app.route('/temp')
@auth.login_required
def temp():
    max_retries = 5
    with dht_lock:
        for attempt in range(max_retries):
            try:
                temperature = dht_device.temperature
                humidity = dht_device.humidity
                if temperature is not None and humidity is not None:
                    return f"Room Temp: {temperature}°C ({temperature * 9/5 + 32}°F) | Humidity: {humidity}%"
            except RuntimeError:
                if attempt < max_retries - 1:
                    time.sleep(2)
                continue
            except Exception as error:
                return f"Error: {str(error)}"
    return "Data unavailable. Retrying soon..."
