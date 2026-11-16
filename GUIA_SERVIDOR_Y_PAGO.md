# 🚀 Guía de Despliegue en Servidor y Sistema de Pantallas — ClipRadar

Esta guía contiene todo lo necesario para poner tu aplicación **ClipRadar** en un servidor en la nube y empezar a venderla.

---

## 📺 1. Configuración de Pantallas Simultáneas

El sistema ya está programado y activo en el código:

| Tipo de Cuenta | Pantallas Simultáneas | Clips y Cuota | Precio |
| :--- | :---: | :--- | :--- |
| **👑 Administrador Maestro (Tú)** | **6 Pantallas** | Ilimitado de por vida (VIP) | **\$0 (Sin cobro)** |
| **⭐ Cuentas de Pago (Pro Mensual)** | **4 Pantallas** | Clips ilimitados, 1080p, sin marca | **RD\$ 990 / mes** (\$17 USD) |
| **⭐ Cuentas de Pago (VIP Vitalicio)** | **4 Pantallas** | Clips ilimitados de por vida | **RD\$ 2,490 único** (\$39 USD) |
| **🎁 Prueba Gratuita (Free Trial)** | **1 Pantalla** | 3 clips completos | **Gratis** |

* **¿Cómo funciona el límite de pantallas?**
  * Si un cliente de pago intenta abrir una 5ª pantalla, el sistema desconecta automáticamente la sesión más antigua (estilo Netflix/Spotify), permitiéndole trabajar cómodamente en sus 4 dispositivos sin bloqueos molestos.
  * Si intenta procesar más de 4 videos al mismo tiempo en el servidor, el sistema le muestra: *"Límite de 4 pantallas simultáneas alcanzado. Tienes 4 clips procesándose al mismo tiempo."*
  * En tu cuenta de Administrador tienes **hasta 6 pantallas/procesos simultáneos**.

---

## ☁️ 2. ¿Qué servidor contratar cuando vayas a pagar?

Para que ClipRadar procese videos en la nube rápido y fluido con **Whisper + YAMNet + FFmpeg**, te recomiendo cualquiera de estas dos opciones económicas y potentes:

### Opción A (La más recomendada y económica): Hetzner Cloud
* **Proveedor:** [hetzner.com/cloud](https://www.hetzner.com/cloud)
* **Plan recomendado:** **CPX31** (4 vCPU AMD EPYC, 8 GB RAM, 160 GB NVMe SSD).
* **Costo mensual:** **~€13.50 / mes (aprox. \$14 USD / RD\$ 850 al mes)**.
* **Ubicación:** Falkenstein (Alemania) o Ashburn (USA).

### Opción B: DigitalOcean
* **Proveedor:** [digitalocean.com](https://www.digitalocean.com)
* **Plan recomendado:** Basic Droplet (4 vCPU, 8 GB RAM, 160 GB SSD).
* **Costo mensual:** **~\$48 USD / mes**.

---

## 🛠️ 3. Pasos para ponerlo a funcionar en tu Servidor (En 5 minutos)

Una vez que compres tu servidor (con sistema operativo **Ubuntu 22.04 o 24.04 LTS**):

### Paso 1: Conectarte a tu servidor
Desde tu computadora abres la terminal (PowerShell o CMD) y te conectas con el comando que te dé el proveedor:
```bash
ssh root@IP_DE_TU_SERVIDOR
```

### Paso 2: Subir tu carpeta `clipradar`
Puedes subirla usando **FileZilla** (por protocolo SFTP con la IP y contraseña de tu servidor) o usando `git clone`.

### Paso 3: Ejecutar el instalador automático
Dentro de la carpeta `clipradar` en tu servidor ejecutas:
```bash
chmod +x deploy.sh
./deploy.sh
```
El script instalará Docker, configurará las fuentes, preparará FFmpeg y levantará la aplicación automáticamente.

¡Y listo! Abres en tu navegador:
`http://IP_DE_TU_SERVIDOR:8787`

---

## 🔒 4. Ponerle tu propio Dominio con Candado SSL (HTTPS) Gratis

Si compras un dominio (por ejemplo en Namecheap o Porkbun por \$8/año):
1. Apuntas el dominio (`A Record`) a la IP de tu servidor.
2. Instalas **Caddy** en tu servidor con dos comandos:
   ```bash
   sudo apt install -y caddy
   ```
3. Editas `/etc/caddy/Caddyfile` y pones:
   ```caddy
   tudominio.com {
       reverse_proxy localhost:8787
   }
   ```
4. Reinicias Caddy (`sudo systemctl restart caddy`) y Caddy le pondrá el certificado SSL (candado verde) gratis y automático.

---

## 🛡️ 5. Anti-bloqueo de YouTube en Servidores Cloud

Los servidores en la nube a veces son detectados por YouTube si descargan decenas de videos seguidos. Para que nunca falle:
1. En tu navegador de PC instala la extensión *"Get cookies.txt LOCALLY"*.
2. Entras a YouTube con cualquier cuenta y descargas el archivo `cookies.txt`.
3. Copias ese archivo dentro de la carpeta `data/cookies.txt` de tu servidor.
4. `ClipRadar` lo detectará automáticamente y descargará los videos con identidad legítima sin que YouTube jamás te bloquee.

---

## 💰 6. Cómo cobrar a tus clientes en República Dominicana

1. Tu cliente ve los precios en la web o te contacta por WhatsApp:
   * **Pro Mensual:** RD\$ 990 / mes
   * **VIP Vitalicio:** RD\$ 2,490
2. Te transfieren a tu cuenta (Banco Popular, Banreservas o BHD).
3. Entras a tu ClipRadar con tu cuenta de Administrador y pulsas **`🔑 Generar Claves`**.
4. Seleccionas el plan y pulsas **"Generar Nueva Clave"**.
5. Te saldrá una clave como: `CLIP-PRO-98BC-21A4`.
6. Se la mandas por WhatsApp a tu cliente.
7. El cliente la pega en la web en *"Activar Licencia"* y en **1 segundo** su cuenta se desbloquea con sus **4 pantallas simultáneas**.
