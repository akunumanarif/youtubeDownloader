#!/bin/bash
# =============================================================================
# init-ssl.sh — First-time SSL certificate setup using Let's Encrypt
# Run ONCE on a fresh VPS before starting the main docker-compose stack.
# =============================================================================
set -e

DOMAIN="ytdownloader.numanarif.dev"
EMAIL="untukdummy687@gmail.com"

echo "==> [1/3] Stopping any running containers (freeing port 80)..."
docker compose down 2>/dev/null || true

echo "==> [2/3] Requesting Let's Encrypt certificate (standalone mode)..."
# Certbot standalone: creates its own temporary HTTP server on port 80.
# No nginx needed at this stage.
docker compose run --rm --no-deps \
  -p 80:80 \
  --entrypoint "certbot" \
  certbot certonly \
    --standalone \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    -d "$DOMAIN"

echo "==> [3/3] Creating required SSL support files..."
docker compose run --rm --no-deps \
  --entrypoint "sh" \
  certbot -c "
    set -e
    # Download Certbot's recommended nginx SSL options
    if [ ! -f /etc/letsencrypt/options-ssl-nginx.conf ]; then
      echo 'Downloading options-ssl-nginx.conf...'
      wget -q https://raw.githubusercontent.com/certbot/certbot/master/certbot-nginx/certbot_nginx/_internal/tls_configs/options-ssl-nginx.conf \
        -O /etc/letsencrypt/options-ssl-nginx.conf
    fi
    # Generate Diffie-Hellman params (takes ~1 min)
    if [ ! -f /etc/letsencrypt/ssl-dhparams.pem ]; then
      echo 'Generating DH params (this may take a minute)...'
      openssl dhparam -out /etc/letsencrypt/ssl-dhparams.pem 2048
    fi
    echo 'SSL support files ready.'
  "

echo ""
echo "=========================================="
echo " SSL certificate obtained successfully!"
echo " Now start the full stack with:"
echo "   docker compose up -d"
echo "=========================================="
