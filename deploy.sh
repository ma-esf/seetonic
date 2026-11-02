#!/usr/bin/env bash
# Build the image from this folder in Cloud Build, deploy it to Cloud Run and print the service URL.
# Run setup.sh first. Safe to rerun: each run deploys a new revision of the same service.
# Passes every setting in app/config.py as an environment variable, with the same defaults; TYPESAFE_API_KEY comes
# from Secret Manager.
set -euo pipefail
cd "$(dirname "$0")"  # --source . must be this folder, wherever the script is run from

PROJECT="${GOOGLE_CLOUD_PROJECT:-seetonic-demo}"
REGION="${REGION:-europe-north1}"
LOCATION="${GOOGLE_CLOUD_LOCATION:-eu}"
EMBEDDING_MODEL="${EMBEDDING_MODEL:-gemini-embedding-2}"
FLASH_MODEL="${FLASH_MODEL:-gemini-3.8-flash}"
JEV_MODEL="${JEV_MODEL:-jev-1.13.0}"
DPI="${DPI:-144}"
TOP_K="${TOP_K:-3}"
EMBEDDING_SIZE="${EMBEDDING_SIZE:-768}"
DATA_LOCATION="${DATA_LOCATION:-europe-north1}"
BUCKET="${BUCKET:-$PROJECT-files}"
DATASET="${DATASET:-seetonic}"
QUESTIONS_TABLE="${QUESTIONS_TABLE:-questions}"
MAX_PAGES="${MAX_PAGES:-50}"

# Who may call the service is set in IAM, not here, so a redeploy keeps it open or closed. --concurrency 1 keeps
# PyMuPDF, which does not support threads, on one request per instance, and with --max-instances 2 it caps the
# service at two requests at once, which caps the rate of model calls. --min-instances 1 keeps one instance running,
# so the first request after a quiet spell skips the 7-8 s start.
gcloud run deploy seetonic --source . --quiet \
  --project "$PROJECT" --region "$REGION" \
  --service-account "seetonic-run@$PROJECT.iam.gserviceaccount.com" \
  --min-instances 1 --max-instances 2 --concurrency 1 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=$LOCATION,\
EMBEDDING_MODEL=$EMBEDDING_MODEL,FLASH_MODEL=$FLASH_MODEL,JEV_MODEL=$JEV_MODEL,DPI=$DPI,TOP_K=$TOP_K,\
EMBEDDING_SIZE=$EMBEDDING_SIZE,DATA_LOCATION=$DATA_LOCATION,BUCKET=$BUCKET,DATASET=$DATASET,\
QUESTIONS_TABLE=$QUESTIONS_TABLE,MAX_PAGES=$MAX_PAGES" \
  --set-secrets "TYPESAFE_API_KEY=typesafe-api-key:latest"

gcloud run services describe seetonic --project "$PROJECT" --region "$REGION" --format 'value(status.url)'
