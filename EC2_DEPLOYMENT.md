# EC2 Docker Deployment

## 1. EC2 Security Group

Open inbound ports:

- `22` for SSH
- `3000` for the Next.js frontend
- `8000` for the FastAPI backend

## 2. Install Docker

On Ubuntu EC2:

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin git
sudo systemctl enable --now docker
sudo usermod -aG docker ubuntu
```

Log out and SSH back in after `usermod`.

## 3. Clone And Configure

```bash
git clone https://github.com/Amazon-Hackon-6-0/HackOn-6.0.git
cd HackOn-6.0
cp ec2.env.example .env
cp backend/.env.example backend/.env
```

Edit `.env` and replace `YOUR_EC2_PUBLIC_IP_OR_DOMAIN`.

Edit `backend/.env` with real secrets:

```env
GEMINI_API_KEY=...
DISCORD_BOT_TOKEN=...
DISCORD_GUILD_ID=...
DISCORD_TECH_SUPPORT_CHANNEL_ID=...
CAMPUSBUDDY_DISCORD_ENABLED=true
CAMPUS_RELAY_EMAIL_ENABLED=true
CAMPUS_RELAY_SMTP_HOST=smtp.gmail.com
CAMPUS_RELAY_SMTP_PORT=587
CAMPUS_RELAY_SMTP_USERNAME=...
CAMPUS_RELAY_SMTP_PASSWORD=...
CAMPUS_RELAY_FROM_EMAIL=...
```

## 4. Start Production Containers

```bash
docker compose --env-file .env -f docker-compose.ec2.yml up -d --build
```

Frontend:

```text
http://YOUR_EC2_PUBLIC_IP_OR_DOMAIN:3000
```

Backend health:

```text
http://YOUR_EC2_PUBLIC_IP_OR_DOMAIN:8000/health
```

## 5. Useful Commands

```bash
docker compose --env-file .env -f docker-compose.ec2.yml ps
docker compose --env-file .env -f docker-compose.ec2.yml logs -f backend
docker compose --env-file .env -f docker-compose.ec2.yml logs -f frontend
docker compose --env-file .env -f docker-compose.ec2.yml down
```

Backend runtime data is stored in the `backend_app_data` Docker volume so SQLite, uploaded policy data, and process relay state survive container rebuilds.
