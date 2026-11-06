#!/usr/bin/env bash
# Build the image from this folder in Cloud Build, deploy it to Cloud Run and print the service URL.
# Run setup.sh first. Safe to rerun: each run deploys a new revision of the same service.
# Passes every setting app/config.py reads from the environment, with the same defaults; TYPESAFE_API_KEY comes
# from Secret Manager.
set -euo pipefail
cd "$(dirname "$0")"  # --source . must be this folder, wherever the script is run from

PROJECT="${GOOGLE_CLOUD_PROJECT:-seetonic-demo}"
REGION="${REGION:-europe-north1}"
LOCATION="${GOOGLE_CLOUD_LOCATION:-eu}"
FLASH_MODEL="${FLASH_MODEL:-gemini-3.8-flash}"
JEV_MODEL="${JEV_MODEL:-jev-1.13.0}"
DPI="${DPI:-144}"
TOP_K="${TOP_K:-3}"
DATA_LOCATION="${DATA_LOCATION:-europe-north1}"
BUCKET="${BUCKET:-$PROJECT-files}"
DATASET="${DATASET:-seetonic}"
QUESTIONS_TABLE="${QUESTIONS_TABLE:-questions}"
MAX_PAGES="${MAX_PAGES:-50}"

# IAM controls access; redeploying does not change whether the service is public.
# --concurrency 1 avoids concurrent PyMuPDF requests within an instance.
# --max-instances 2 normally limits each revision to two concurrent requests, not a model-call rate or spending cap.
# Cloud Run can temporarily exceed the instance limit.
# --min-instances 1 keeps an instance warm to reduce cold-start latency, not eliminate cold starts.
gcloud run deploy seetonic --source . --quiet \
  --project "$PROJECT" --region "$REGION" \
  --service-account "seetonic-run@$PROJECT.iam.gserviceaccount.com" \
  --min-instances 1 --max-instances 2 --concurrency 1 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=$LOCATION,\
FLASH_MODEL=$FLASH_MODEL,JEV_MODEL=$JEV_MODEL,DPI=$DPI,TOP_K=$TOP_K,\
DATA_LOCATION=$DATA_LOCATION,BUCKET=$BUCKET,DATASET=$DATASET,\
QUESTIONS_TABLE=$QUESTIONS_TABLE,MAX_PAGES=$MAX_PAGES" \
  --set-secrets "TYPESAFE_API_KEY=typesafe-api-key:latest"

gcloud run services describe seetonic --project "$PROJECT" --region "$REGION" --format 'value(status.url)'
