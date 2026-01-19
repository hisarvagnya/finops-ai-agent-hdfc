# --- Stage 1: Builder ---
FROM python:3.12.6-slim-bookworm AS builder

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# 1. Install build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 2. Upgrade pip and install dependencies
RUN python -m pip install --no-cache-dir --upgrade "pip>=25.3"
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/app/deps -r requirements.txt

# 3. Clean up the bundled pip wheels (CVE-2025-8869)
RUN rm -rf /usr/local/lib/python3.12/ensurepip/_bundled/pip*.whl \
    && rm -rf /usr/local/lib/python3.12/ensurepip/_bundled/setuptools*.whl

# 4. Identify and collect ALL system library dependencies (libz, libssl, etc.)
# This ensures we don't get "ImportError: libz.so.1"
RUN mkdir -p /app/lib && \
    cp /lib/x86_64-linux-gnu/libz.so.1 /app/lib/ && \
    cp /usr/lib/x86_64-linux-gnu/libexpat.so.1 /app/lib/ && \
    cp /usr/lib/x86_64-linux-gnu/libffi.so.8 /app/lib/ && \
    cp /lib/x86_64-linux-gnu/liblzma.so.5 /app/lib/ && \
    cp /lib/x86_64-linux-gnu/libbz2.so.1.0 /app/lib/ 

COPY . .

# --- Stage 2: Runner ---
FROM gcr.io/distroless/cc-debian12

WORKDIR /app

# Copy Python binaries
COPY --from=builder /usr/local/bin/python3 /usr/local/bin/python3
COPY --from=builder /usr/local/lib/ /usr/local/lib/

# Copy the collected system libraries into the runner's library path
COPY --from=builder /app/lib/ /lib/x86_64-linux-gnu/

# Copy app code and dependencies
COPY --from=builder /app /app

# Setup Environment
ENV PYTHONPATH=/app/deps
ENV PATH=/usr/local/bin:/app/deps/bin:$PATH
ENV PORT=443
EXPOSE 443

# Start Gunicorn
ENTRYPOINT ["/usr/local/bin/python3", "-m", "gunicorn", "--bind", "0.0.0.0:443", "--workers", "1", "--worker-class", "uvicorn.workers.UvicornWorker", "main:application"]