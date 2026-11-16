#!/usr/bin/env bash
# Uso: ./deploy_oracle.sh <IP_PUBLICA_DE_LA_VM> [usuario]
# Sube ClipRadar a la VM de Oracle, instala Docker y lo deja corriendo en el puerto 8787.
set -euo pipefail
IP="${1:?Falta la IP publica}"; USER_="${2:-opc}"   # opc = Oracle Linux, ubuntu = Ubuntu
KEY="$(dirname "$0")/_oracle_ssh/clipradar_key"
SSH="ssh -i $KEY -o StrictHostKeyChecking=accept-new $USER_@$IP"
$SSH 'command -v docker >/dev/null || { (command -v dnf >/dev/null && sudo dnf install -y dnf-utils && sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo && sudo dnf install -y docker-ce docker-ce-cli containerd.io) || (curl -fsSL https://get.docker.com | sudo sh); sudo systemctl enable --now docker; }; sudo usermod -aG docker $USER'
# abre el puerto 8787 en el firewall del sistema operativo
$SSH 'sudo firewall-cmd --permanent --add-port=8787/tcp 2>/dev/null && sudo firewall-cmd --reload 2>/dev/null || sudo iptables -I INPUT -p tcp --dport 8787 -j ACCEPT'
tar --exclude=_oracle_ssh --exclude=.git --exclude=data --exclude=__pycache__ -czf - -C "$(dirname "$0")" . | $SSH 'mkdir -p ~/clipradar && tar xzf - -C ~/clipradar'
$SSH 'cd ~/clipradar && sudo docker build -t clipradar . && (sudo docker rm -f clipradar 2>/dev/null; sudo docker run -d --name clipradar --restart unless-stopped -p 8787:8787 -v clipradar_data:/app/data -e CLIPRADAR_ADMIN_EMAIL="${CLIPRADAR_ADMIN_EMAIL:-admin@clipradar.local}" clipradar)'
echo "Listo: http://$IP:8787  (recuerda abrir el puerto 8787 en la Security List de Oracle)"
