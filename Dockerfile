# Use a clean stable Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies required by pdfplumber, PIL, and MuPDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    poppler-utils \
    python3-dev \
    gcc \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (better caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy entire project
COPY . .

# Expose FastAPI port
EXPOSE 8000

# Start FastAPI with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
