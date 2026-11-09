FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies required for dlib and face_recognition
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libopenblas-dev \
    liblapack-dev \
    libx11-dev \
    libgtk-3-dev \
    redis-server \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
# Prevent dlib compilation from exhausting RAM by limiting CMake to 1 core
ENV CMAKE_BUILD_PARALLEL_LEVEL=1
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose FastAPI port
EXPOSE 7860

# Give permissions to the Hugging Face user (1000)
RUN chown -R 1000:1000 /app
USER 1000

RUN chmod +x start.sh

CMD ["./start.sh"]
