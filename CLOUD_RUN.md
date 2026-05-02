# Cloud Run Deployment

This deploys the app as one Cloud Run service:

- FastAPI serves `/api/*`
- FastAPI also serves the static frontend from `/`
- Nginx, Certbot, and `init-ssl.sh` are not needed for the default Cloud Run URL

## Deploy

Set these values first:

```bash
PROJECT_ID="arif-project-473214"
REGION="asia-southeast2"
SERVICE="yt-downloader"
```

Build and deploy:

```bash
gcloud config set project "$PROJECT_ID"

gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 1 \
  --cpu 1 \
  --memory 1Gi \
  --timeout 3600 \
  --set-env-vars DOWNLOADS_DIR=/app/downloads,FRONTEND_DIR=/app/frontend
```

## Notes

- Keep `min-instances` at `0` so the service can scale to zero when idle.
- `max-instances 1` helps prevent accidental parallel usage from increasing cost.
- The local filesystem is temporary. This app only keeps files long enough for the user to download them, so that is acceptable.
- The default Cloud Run URL already includes HTTPS.
