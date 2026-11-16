#!/bin/bash
# Script de Despliegue Automático para Servidor Cloud (Ubuntu / Debian)
# ClipRadar — Servidor de Producción

set -e

echo "=========================================================="
echo "📡 Iniciando despliegue de ClipRadar en Servidor Cloud..."
echo "=========================================================="

# 1. Actualizar el sistema
sudo apt-get update && sudo apt-get upgrade -y

# 2. Instalar Docker si no existe
if ! command -v docker &> /dev/null; then
    echo "🐳 Instalando Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
else
    echo "✔ Docker ya está instalado."
fi

# 3. Instalar Docker Compose si no existe
if ! command -v docker-compose &> /dev/null; then
    echo "📦 Instalando Docker Compose..."
    sudo apt-get install -y docker-compose-plugin docker-compose
fi

# 4. Crear carpeta de datos si no existe
mkdir -p data/jobs data/models

# 5. Construir y levantar el contenedor
echo "🚀 Levantando contenedor de ClipRadar..."
docker-compose down || true
docker-compose up --build -d

echo "=========================================================="
echo "🎉 ¡ClipRadar está corriendo exitosamente en el servidor!"
echo "Accede en tu navegador a: http://TU_IP_DEL_SERVIDOR:8787"
echo "=========================================================="
