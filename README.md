# Dog Cam Stream Project

This project sets up a Flask app on Raspberry Pi to stream video from a camera module, display environment temperature, and limit concurrent viewers. Uses UV for package management.

## Prerequisites
- Raspberry Pi with camera module enabled (via `raspi-config`).
- Python 3.12+.
- UV installed: `curl -LsSf https://astral.sh/uv/install.sh | sh`.

## Setup
1. Clone the repo:
   ```
   git clone https://github.com/yourusername/dog-stream.git
   cd dog-stream
   ```

2. Create and activate virtual environment with UV:
   ```
   uv venv
   source .venv/bin/activate
   ```

3. Install dependencies from `pyproject.toml`:
   ```
   uv sync
   ```

4. Create `.env` file in the project root:
   ```
   FLASK_SECRET_KEY=your_random_secret  # Generate with python -c 'import secrets; print(secrets.token_hex(16))'
   BASIC_AUTH_USERNAME=your_username
   BASIC_AUTH_PASSWORD=your_password
   MAX_VIEWERS=3
   PORT=5000
   ```

## Run Locally
1. Run the app:
   ```
   uv run dogcam_stream.py
   ```

2. Access in browser: `http://<raspberry-pi-local-ip>:<PORT>` (e.g., http://192.168.1.100:5000). Enter auth credentials.

## Optional: Deploy with Cloudflare Tunnel
1. Install cloudflared: Download ARM binary from https://github.com/cloudflare/cloudflared/releases and move to `/usr/local/bin/cloudflared`.

2. Authenticate: `cloudflared tunnel login`.

3. Create tunnel: `cloudflared tunnel create my-tunnel`.

4. Configure `~/.cloudflared/config.yml`:
   ```
   tunnel: my-tunnel
   credentials-file: /home/<user>/.cloudflared/<uuid>.json
   ingress:
     - hostname: your-subdomain.your-domain.com
       service: http://localhost:5000
     - service: http_status:404
   ```

5. Update your domain's DNS to point to the tunnel (e.g., CNAME to <uuid>.cfargotunnel.com with proxy enabled).

6. Run tunnel: `cloudflared tunnel run my-tunnel`.

7. For auto-start, create systemd service for the tunnel and Flask app.