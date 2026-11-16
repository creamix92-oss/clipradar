#!/usr/bin/env bash
# Se ejecuta DENTRO de la VM de Oracle (Oracle Linux 9). Lo lanza desplegar_oracle.bat
set -e
# 1) Swap de 4 GB (la VM gratis tiene 1 GB de RAM)
if ! swapon --show | grep -q .; then
  sudo fallocate -l 4G /swapfile 2>/dev/null || sudo dd if=/dev/zero of=/swapfile bs=1M count=4096
  sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi
# 2) Docker
if ! command -v docker >/dev/null; then
  sudo dnf install -y dnf-utils
  sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
  sudo dnf install -y docker-ce docker-ce-cli containerd.io
fi
sudo systemctl enable --now docker
# 3) Firewall del sistema: puerto 8787
sudo firewall-cmd --permanent --add-port=8787/tcp >/dev/null 2>&1 && sudo firewall-cmd --reload >/dev/null 2>&1 || true
# 4) Codigo
rm -rf ~/clipradar && mkdir -p ~/clipradar && tar xzf ~/clipradar.tgz -C ~/clipradar
cd ~/clipradar
# 5) Build + run
sudo docker build -t clipradar .
sudo docker rm -f clipradar >/dev/null 2>&1 || true
sudo docker run -d --name clipradar --restart unless-stopped -p 8787:8787 -v clipradar_data:/app/data clipradar
sleep 20
echo "=== RESPUESTA LOCAL ==="; curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8787/ || true
echo "=== LOGS ==="; sudo docker logs --tail 15 clipradar 2>&1
echo "=== CLAVE ADMIN ==="; sudo docker exec clipradar sh -c 'cat /app/data/ADMIN_PASSWORD.txt 2>/dev/null || echo "(usa CLIPRADAR_ADMIN_PASS o revisa logs)"'
