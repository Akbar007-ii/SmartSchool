#!/usr/bin/env bash
# Smart School API'ни таза Ubuntu серверге (AWS EC2) орнотот же жаңыртат.
#
#   curl -fsSL https://raw.githubusercontent.com/Akbar007-ii/SmartSchool/master/deploy/setup_server.sh | bash
#
# Кайра иштетсе болот: ар бир жолу кодду жаңыртып, контейнерлерди кайра курат.
# .env бир гана жолу (биринчи орнотууда) кокустук сырлар менен түзүлөт.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Akbar007-ii/SmartSchool.git}"
BRANCH="${BRANCH:-master}"
APP_DIR="${APP_DIR:-$HOME/SmartSchool}"

log() { printf '\n==> %s\n' "$*"; }

# 1. Swap — 1–2 GB RAM'дуу серверде Docker build жана PostgreSQL үчүн запас
if ! sudo swapon --show | grep -q '/swapfile'; then
    log "2 GB swap түзүлүүдө"
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile >/dev/null
    sudo swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

# 2. Docker
if ! command -v docker >/dev/null 2>&1; then
    log "Docker орнотулууда"
    curl -fsSL https://get.docker.com | sudo sh
fi
sudo usermod -aG docker "$USER" || true
DOCKER="sudo docker"

# 3. Код
if [ -d "$APP_DIR/.git" ]; then
    log "Код жаңыртылууда ($BRANCH)"
    git -C "$APP_DIR" fetch --quiet origin "$BRANCH"
    git -C "$APP_DIR" checkout --quiet "$BRANCH"
    git -C "$APP_DIR" reset --quiet --hard "origin/$BRANCH"
else
    log "Код жүктөлүүдө ($BRANCH)"
    git clone --quiet --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

# 4. .env — биринчи жолу гана, кокустук сырлар менен
if [ ! -f .env ]; then
    log ".env түзүлүүдө"
    cp .env.example .env
    secret_key="$(openssl rand -hex 48)"
    db_password="$(openssl rand -hex 24)"
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${secret_key}|" .env
    sed -i "s|^DB_PASSWORD=.*|DB_PASSWORD=${db_password}|" .env
    chmod 600 .env
fi

# 5. Иштетүү
log "Контейнерлер курулуп, иштетилүүдө (биринчи жолу 3–5 мүнөт)"
$DOCKER compose up -d --build

API_PORT="$(grep -E '^API_PORT=' .env | cut -d= -f2)"
API_PORT="${API_PORT:-80}"

log "API даяр болгуча күтүлүүдө"
for _ in $(seq 1 60); do
    if curl -fsS "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
        ready=1
        break
    fi
    sleep 3
done

if [ "${ready:-0}" != 1 ]; then
    echo "КАТА: API 3 мүнөттө көтөрүлгөн жок. Логдор:" >&2
    $DOCKER compose logs --tail 80 api >&2
    exit 1
fi

# 6. Демо-маалымат (мурда түзүлгөн болсо, эч нерсе өзгөрбөйт)
log "Демо-маалымат"
$DOCKER compose exec -T api python seed_demo.py || true

PUBLIC_IP="$(curl -fsS https://checkip.amazonaws.com 2>/dev/null || echo '<СЕРВЕРДИН-IP>')"
PORT_SUFFIX=""
[ "$API_PORT" != "80" ] && PORT_SUFFIX=":${API_PORT}"

log "Даяр!"
echo "API:     http://${PUBLIC_IP}${PORT_SUFFIX}"
echo "Swagger: http://${PUBLIC_IP}${PORT_SUFFIX}/docs"
