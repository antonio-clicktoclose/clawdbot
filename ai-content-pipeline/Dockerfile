FROM python:3.12-slim

# ffmpeg is required for video editing pipeline steps
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

# Create output directories
RUN mkdir -p outputs/videos outputs/audio outputs/final outputs/logs \
            soul_id/photos soul_id/voice_samples

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "120", "dashboard:app"]
