import os
import threading
import time
from flask import Flask, Response, render_template_string, request
from flask_httpauth import HTTPBasicAuth
from picamera2 import Picamera2
from dotenv import load_dotenv
import io
import glob

load_dotenv()

app = Flask(__name__)
auth = HTTPBasicAuth()
semaphore = threading.Semaphore(int(os.getenv('MAX_VIEWERS', 3)))

# Basic auth verification
users = {
    os.getenv('BASIC_AUTH_USERNAME'): os.getenv('BASIC_AUTH_PASSWORD')
}

@auth.verify_password
def verify_password(username, password):
    if username in users and users[username] == password:
        return username

# Read temperature from DS18B20
def read_temp():
    base_dir = '/sys/bus/w1/devices/'
    device_folder = glob.glob(base_dir + '28*')[0]
    device_file = device_folder + '/w1_slave'
    with open(device_file, 'r') as f:
        lines = f.readlines()
    equals_pos = lines[1].find('t=')
    if equals_pos != -1:
        temp_string = lines[1][equals_pos+2:]
        temp_c = float(temp_string) / 1000.0
        temp_f = temp_c * 9.0 / 5.0 + 32.0
        return temp_c, temp_f
    return None, None

# Camera setup
picam2 = Picamera2()
picam2.configure(picam2.create_video_configuration(main={"size": tuple(map(int, os.getenv('CAMERA_RESOLUTION', '640x480').split('x')))}))
picam2.start()

def gen():
    stream = io.BytesIO()
    while True:
        picam2.capture_file(stream, format='jpeg')
        stream.seek(0)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + stream.read() + b'\r\n')
        stream.seek(0)
        stream.truncate()
        time.sleep(0.1)  # Frame rate control

@app.route('/')
@auth.login_required
def index():
    temp_c, temp_f = read_temp()
    temp_display = f"Temperature: {temp_c:.2f}°C / {temp_f:.2f}°F" if temp_c else "Sensor error"
    return render_template_string('''
    <html>
        <body>
            <h1>Dog Stream</h1>
            <p>{{ temp }}</p>
            <img src="/video_feed" width="640" height="480">
        </body>
    </html>
    ''', temp=temp_display)

@app.route('/video_feed')
@auth.login_required
def video_feed():
    if not semaphore.acquire(blocking=False):
        return "Max viewers reached. Try again later.", 503
    try:
        return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')
    finally:
        semaphore.release()  # Release on disconnect

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)  # Threaded for concurrency on Pi