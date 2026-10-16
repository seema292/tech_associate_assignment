FROM python:3.12-slim

# xvfb gives the (non-headless) browser a virtual screen on a machine with no display.
RUN apt-get update \
    && apt-get install -y --no-install-recommends xvfb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    # download Chromium and the system libraries it needs
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY . .

# main.py notices there is no display and starts its own virtual screen (Xvfb).
CMD ["python", "main.py", "--config", "config.yaml"]
