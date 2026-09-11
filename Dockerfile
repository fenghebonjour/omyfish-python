FROM python:3.11-slim

WORKDIR /app

# Install system deps needed by OpenCV headless and albumentations
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libsm6 libxrender1 libxext6 libgl1 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install CPU-only torch first: the default PyPI wheels bundle the full CUDA
# stack (~6 GB of nvidia-* wheels), which exceeds the Space build timeout on
# CPU hardware. Pre-satisfying torch/torchvision keeps the requirements step
# from pulling the CUDA variants.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
    "torch>=2.1.0" "torchvision>=0.16.0"

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Patch Streamlit's index.html to permanently reserve the scrollbar gutter.
# Streamlit's own CSS has no overflow rule on any layout container, so the
# page scrollbar lives on <html> (browser default). st.markdown CSS is
# managed by React and briefly absent during reconciliation, causing the
# 10px width jump on every rerun. Patching index.html puts the fix before
# React loads — it can never be removed.
RUN python -c "\
import streamlit, pathlib; \
idx = pathlib.Path(streamlit.__file__).parent / 'static' / 'index.html'; \
css = '<style>html{overflow-y:scroll!important}*,*::before,*::after{scrollbar-gutter:stable}</style>'; \
content = idx.read_text(); \
idx.write_text(content.replace('</head>', css + '</head>', 1))"

# ── Bundled bite-score service ────────────────────────────────────────────────
# HF requires PRO for new Docker Spaces, so the shared omyfish-ai service
# (single source of the bite-score domain) is bundled into this Space's image
# instead of getting its own Space. A rebuild refreshes it from GitHub main
# (pulls in omyfish-ai@0a555ef — switches the bite-score weather provider
# from Open-Meteo to OpenWeatherMap; needs OPENWEATHERMAP_API_KEY as a
# Space secret, and caps the forecast horizon at 48h).
ADD https://github.com/fenghebonjour/omyfish-ai/archive/refs/heads/main.tar.gz /tmp/omyfish-ai.tar.gz
RUN mkdir /ai && tar -xzf /tmp/omyfish-ai.tar.gz -C /ai --strip-components=1 \
    && rm /tmp/omyfish-ai.tar.gz \
    && pip install --no-cache-dir "httpx>=0.27.0" "ephem>=4.1.0" "beautifulsoup4>=4.12.0" "groq>=0.11.0"

# Timing tab talks to the bundled service; fish-ID stays in-process via
# Streamlit's own predictors, so the bundled copy skips its model loading.
# NOTE: this pip install list must track omyfish-ai's module-level imports
# (bs4/groq/httpx/ephem etc.) — a missing one crashes the bundled uvicorn
# process silently at import time, and only Streamlit comes up on 7860.
ENV BITE_SERVICE_URL=http://127.0.0.1:8000 \
    DISABLE_FISH_ID=1

# Runs as root by default otherwise — a container breakout or dependency RCE would have full
# root inside the container for no benefit (BACKLOG.md item B, WEAKNESS_AUDIT.md §1.4).
# `chown -R app:app /app` (chowning the whole copied source+dependency tree) was tried first
# and measured at 12+ minutes on this image alone — a real risk of blowing the HF Space build
# timeout on top of the already-documented torch-wheel-size concern above, for no benefit
# (COPY leaves regular files world-readable by default, so a non-owner user can already read
# everything under /app it needs to). Scoped instead to a dedicated home directory the new
# user actually owns, plus the one app-specific write path: data/observations.db (SQLite,
# apps/omyfish_api/db/engine.py). Streamlit's own one-time ~/.streamlit/credentials.toml
# write (even in --headless mode) and the CLIP fish-gate's model cache
# (services/fish_ai/predictors/clip.py, transformers.from_pretrained) both resolve under
# $HOME, which HF_HOME/HOME below point at this same small directory rather than /app.
RUN groupadd -r app && useradd -r -g app -m -d /home/app -s /sbin/nologin app \
    && mkdir -p /app/data \
    && chown -R app:app /app/data /home/app
USER app
ENV HOME=/home/app \
    HF_HOME=/home/app/.cache/huggingface

# HuggingFace Spaces requires apps to listen on port 7860
EXPOSE 7860

CMD ["/bin/sh", "-c", "\
     uvicorn main:app --app-dir /ai --host 127.0.0.1 --port 8000 & \
     exec streamlit run apps/omyfish_web/main.py \
       --server.port=7860 \
       --server.address=0.0.0.0 \
       --server.headless=true \
       --server.enableCORS=false \
       --server.enableXsrfProtection=false"]
