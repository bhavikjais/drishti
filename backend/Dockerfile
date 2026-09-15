# Drishti backend - FastAPI + torch/opencv/ultralytics CV pipelines.
# Built from the repo root (see render.yaml: dockerContext: .) so it can
# COPY the backend/, models/, and requirements.txt that live at top level.
FROM python:3.11-slim

# tesseract-ocr: system binary backend/modules/anpr/ocr.py's pytesseract
# fallback shells out to. libgl1/libglib2.0-0: opencv-python's runtime
# native deps (headless base image lacks these).
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# requirements.txt pins fast-plate-ocr/open-image-models bare (no [onnx]
# extra) so a plain -r install doesn't drag in opencv-python-headless and
# shadow the pinned opencv-python above - reinstall just those 4 with the
# [onnx] extra and --no-deps, per the comment in requirements.txt.
RUN grep -vE '^(fast-plate-ocr|open-image-models|onnxruntime|rich)==' requirements.txt > requirements.core.txt \
    && pip install --no-cache-dir -r requirements.core.txt \
    && pip install --no-cache-dir --no-deps "fast-plate-ocr[onnx]==1.1.0" "open-image-models[onnx]==0.6.0" "onnxruntime==1.29.0" "rich==15.0.0"

COPY backend/ backend/
COPY models/ models/

# Runtime data dirs (uploads/outputs/jobs/etc.) - created by backend/config.py
# on import, but ensuring they exist here keeps the image self-contained.
RUN mkdir -p jobs outputs uploads references zones evidence

ENV DRISHTI_DEVICE=cpu
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
