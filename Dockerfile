# Dockerfile para ClipRadar en Producción
FROM python:3.12-slim

# Evitar prompts interactivos
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV CLIPRADAR_HOST=0.0.0.0
ENV CLIPRADAR_PORT=8787
ENV CLIPRADAR_DATA=/app/data

# Instalar dependencias del sistema: ffmpeg, nodejs (para yt-dlp), curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    git \
    ca-certificates \
    fonts-dejavu-core \
    fonts-noto-color-emoji \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar requirements e instalar
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código de la aplicación
COPY app/ ./app/
COPY web/ ./web/

# Crear volumen de datos persistente
RUN mkdir -p /app/data/jobs /app/data/models

EXPOSE 8787

# Ejecutar con uvicorn
CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8787", "--workers", "1"]
