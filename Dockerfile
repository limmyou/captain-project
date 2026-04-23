FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    proj-data \
    proj-bin \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN echo "===== requirements.txt =====" && cat requirements.txt

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY . .

ENV PYTHONPATH=/app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]