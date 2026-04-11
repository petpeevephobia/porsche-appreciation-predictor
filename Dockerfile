FROM python:3.11-slim

# System deps: git for CLIP install, libgomp1 for torch/sklearn parallelism
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install CPU-only torch first (separate index URL), then the rest
COPY requirements.txt .
RUN pip install --no-cache-dir \
    torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY app.py config.py historical_matcher.py condition_analyzer.py ./
COPY templates/ templates/
COPY static/ static/

# Copy data files (models, vector DB, CSVs) — baked into image at build time
COPY project/data/ project/data/

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "--timeout", "120", "app:app"]
