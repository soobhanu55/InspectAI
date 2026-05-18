FROM python:3.11-slim

WORKDIR /code

# Install system deps
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .

# Install PyTorch CPU-only (saves ~1.5GB vs CUDA version)
RUN pip install --no-cache-dir \
    torch==2.5.1+cpu torchvision==0.20.1+cpu \
    --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir -r requirements.txt

# Pre-download models at build time (not at runtime)
RUN python -c "from sentence_transformers import SentenceTransformer; from sentence_transformers import CrossEncoder; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2'); CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2'); print('Models cached')"
RUN python -c "from ultralytics import YOLO; YOLO('yolov8n.pt'); print('YOLO cached')"

COPY backend/ .

# HuggingFace Spaces requires port 7860
EXPOSE 7860

# Pre-download NLTK data
RUN python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab'); nltk.download('stopwords')"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
