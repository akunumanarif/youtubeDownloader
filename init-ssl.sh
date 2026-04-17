#!/bin/bash
# =============================================================================
# init-ssl.sh — First-time SSL certificate setup using Let's Encrypt
# Run ONCE on a fresh VPS before starting the main docker-compose stack.
# =============================================================================
set -e

DOMAIN="ytdownloader.numanarif.dev"
EMAIL="untukdummy687@gmail.com"   # <-- change this to your email

echo "==> [1/4] Starting nginx with HTTP-only config for ACME challenge..."
docker compose -f docker-compose.yml run --rm --no-deps \
  -v "$(pwd)/nginx/app-init.conf:/etc/nginx/conf.d/default.conf:ro" \
  -p 80:80 \
  nginx nginx -g "daemon off;" &

NGINX_PID=$!
sleep 3

echo "==> [2/4] Requesting Let's Encrypt certificate for $DOMAIN..."
docker compose run --rm certbot certbot certonly \
  --webroot \
  --webroot-path /var/www/certbot \
  --email "$EMAIL" \
  --agree-tos \
  --no-eff-email \
  -d "$DOMAIN"

echo "==> [3/4] Downloading recommended SSL parameters..."
docker compose run --rm certbot sh -c "
  if [ ! -f /etc/letsencrypt/options-ssl-nginx.conf ]; then
    wget -q https://raw.githubusercontent.com/certbot/certbot/master/certbot-nginx/certbot_nginx/_internal/tls_configs/options-ssl-nginx.conf \
      -O /etc/letsencrypt/options-ssl-nginx.conf
  fi
  if [ ! -f /etc/letsencrypt/ssl-dhparams.pem ]; then
    openssl dhparam -out /etc/letsencrypt/ssl-dhparams.pem 2048
  fi
"

echo "==> [4/4] Stopping temporary nginx..."
kill $NGINX_PID 2>/dev/null || true
wait $NGINX_PID 2>/dev/null || true

echo ""
echo "SSL certificate obtained successfully!"
echo "Now start the full stack with:"
echo "  docker compose up -d"
