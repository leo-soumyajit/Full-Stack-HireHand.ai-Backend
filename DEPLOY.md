# 🚀 HireHand AI Backend — EC2 Deployment (Amazon Linux 2023)

Deploy the FastAPI backend to EC2 behind Nginx + HTTPS, using the prebuilt Docker Hub image.

- **Backend domain:** `https://api.soumyajitbanerjee.in`
- **Frontend:** `https://www.soumyajitbanerjee.in` (already deployed)
- **EC2 Elastic IP:** `65.2.219.117` · **Region:** ap-south-1 · **OS:** Amazon Linux 2023 (`ec2-user`)
- **Image:** `soumyajit2005/hirehand-backend:latest` (public, built by GitHub Actions — amd64)
- **DB:** MongoDB Atlas · **Email:** Resend (domain verified) · **ChromaDB:** in-memory (no volume)
- **Flow:** Internet → Nginx (SSL) → `127.0.0.1:8000` (Docker container)

---

## ✅ Pre-flight (do in AWS Console / registrar, BEFORE SSL)

1. **DNS A record** at your registrar for `soumyajitbanerjee.in`:
   `api`  →  `65.2.219.117`   (Cloudflare: set grey cloud / DNS-only until SSL is issued)
   Verify: `dig +short api.soumyajitbanerjee.in`  → should print `65.2.219.117`
2. **EC2 Security Group** inbound: `22` (My IP), `80` (0.0.0.0/0), `443` (0.0.0.0/0).
   Do **not** open `8000` publicly.
3. **MongoDB Atlas → Network Access**: add `65.2.219.117` (or `0.0.0.0/0` for testing).

---

## STEP 1 — Install Docker, Nginx, Certbot (on EC2)

```bash
# System + Docker + git
sudo dnf update -y
sudo dnf install -y docker git nginx python3-pip cronie
sudo systemctl enable --now docker nginx crond
sudo usermod -aG docker ec2-user

# Docker Compose v2 plugin (not bundled on AL2023)
sudo mkdir -p /usr/libexec/docker/cli-plugins
sudo curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)" \
  -o /usr/libexec/docker/cli-plugins/docker-compose
sudo chmod +x /usr/libexec/docker/cli-plugins/docker-compose

# Certbot (via pip — not in AL2023 repos)
sudo python3 -m pip install certbot certbot-nginx
```

> **Log out and SSH back in** so the `docker` group applies (then `docker ps` works without sudo).

(Optional, small instances) add 2 GB swap:
```bash
sudo dnf install -y util-linux
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

---

## STEP 2 — Check CPU architecture

```bash
uname -m
```
- `x86_64` → continue below (pull the image).
- `aarch64` (Graviton) → the Docker Hub image is amd64-only; see **Appendix: arm64** at the bottom.

---

## STEP 3 — App folder + compose file

```bash
mkdir -p ~/hirehand/uploads && cd ~/hirehand
cat > docker-compose.prod.yml <<'EOF'
services:
  backend:
    image: soumyajit2005/hirehand-backend:latest
    container_name: hirehand_backend
    restart: unless-stopped
    ports:
      - "127.0.0.1:8000:8000"
    env_file:
      - .env
    volumes:
      - ./uploads:/app/uploads
EOF
```

---

## STEP 4 — Create `.env`

```bash
nano ~/hirehand/.env
```
Paste:
```
MONGO_URI=mongodb+srv://<user>:<pass>@cluster0.xxxx.mongodb.net/?appName=Cluster0
SECRET_KEY=<a-long-random-string>
FRONTEND_URL=https://www.soumyajitbanerjee.in
AI_API_URL=https://api.groq.com/openai/v1/chat/completions
AI_API_KEY=<your-groq-key>
AI_MODEL=openai/gpt-oss-120b
RESEND_API_KEY=<your-resend-key>
RESEND_FROM_EMAIL=HireHand AI <updates@soumyajitbanerjee.in>
RESEND_REPORTS_EMAIL=HireHand Reports <reports@soumyajitbanerjee.in>

# See .env.example for the full set (Groq interview/chatbot keys, Deepgram, Metered, embeddings).
```
Save: `Ctrl+O`, `Enter`, `Ctrl+X`.

---

## STEP 5 — Pull & run

```bash
cd ~/hirehand
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml logs --tail=40
curl http://127.0.0.1:8000/
```
Expected: `{"message":"HireHand AI API v3.1 ..."}` and logs show `✅ MongoDB indexes initialized`.

---

## STEP 6 — Nginx reverse proxy

```bash
# WebSocket upgrade map (http-level; conf.d is included in http{})
sudo tee /etc/nginx/conf.d/websocket-map.conf > /dev/null <<'EOF'
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}
EOF

# Site config
sudo tee /etc/nginx/conf.d/api.conf > /dev/null <<'EOF'
server {
    listen 80;
    server_name api.soumyajitbanerjee.in;
    client_max_body_size 25M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        proxy_connect_timeout 75s;
        proxy_buffering off;
    }
}
EOF

sudo nginx -t && sudo systemctl reload nginx
```
Now `http://api.soumyajitbanerjee.in` should hit the API.

---

## STEP 7 — HTTPS (Let's Encrypt)

```bash
sudo /usr/local/bin/certbot --nginx -d api.soumyajitbanerjee.in \
  --non-interactive --agree-tos -m banerjeesoumyajit2005@gmail.com --redirect

# Auto-renewal (pip certbot has no timer by default)
echo "0 3 * * * root /usr/local/bin/certbot renew --quiet --deploy-hook 'systemctl reload nginx'" \
  | sudo tee /etc/cron.d/certbot-renew

# Verify
curl https://api.soumyajitbanerjee.in/
sudo /usr/local/bin/certbot renew --dry-run
```

✅ Live at **https://api.soumyajitbanerjee.in**

---

## STEP 8 — Point the frontend at it

Set the frontend's API base URL to `https://api.soumyajitbanerjee.in` (its build env var,
e.g. `VITE_API_URL`) and redeploy. Backend CORS is already `*`, so no backend change needed.

---

## 🔄 Redeploy after new code (GitHub Actions rebuilds the image on push to main)

```bash
cd ~/hirehand
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

---

## 🛠️ Troubleshooting

| Problem | Fix |
|---|---|
| `curl 127.0.0.1:8000` fails | `docker compose -f docker-compose.prod.yml logs` — usually a bad `.env` value |
| Mongo timeout | add `65.2.219.117` to Atlas Network Access |
| 502 Bad Gateway | container down (`docker ps`), or SELinux blocking: `sudo setsebool -P httpd_can_network_connect 1` |
| Certbot fails | DNS not propagated, or port 80 blocked in Security Group |
| `exec format error` on run | image is amd64 but EC2 is arm64 → use Appendix below |
| Emails not sending | check `RESEND_API_KEY` in `.env`; Resend domain must be verified |

---

## Appendix: arm64 (Graviton) — build on server instead of pull

The Docker Hub image is amd64-only. On an aarch64 instance, build locally:
```bash
cd ~
git clone https://github.com/leo-soumyajit/Full-Stack-HireHand.ai-Backend.git
cd Full-Stack-HireHand.ai-Backend
cp ~/hirehand/.env .env          # reuse the .env you made
# edit docker-compose.prod.yml: replace the `image:` line with a build block:
#   build: { context: ., dockerfile: Dockerfile }
docker compose -f docker-compose.prod.yml up -d --build
```
Then continue from STEP 6.
