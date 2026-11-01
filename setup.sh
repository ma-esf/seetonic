#!/usr/bin/env bash
# Enable the deploy APIs, create the Cloud Run service account and grant it its roles and access to the
# typesafe-api-key secret, and create the bucket, the BigQuery dataset and its two tables. Create that secret by hand
# first.
# Safe to rerun: each step leaves an existing one as it is.
# Reads the same environment variables as app/config.py, with the same defaults.
set -euo pipefail

PROJECT="${GOOGLE_CLOUD_PROJECT:-seetonic-demo}"
DATA_LOCATION="${DATA_LOCATION:-europe-north1}"
BUCKET="${BUCKET:-$PROJECT-files}"
DATASET="${DATASET:-seetonic}"
QUESTIONS_TABLE="${QUESTIONS_TABLE:-questions}"
SERVICE_ACCOUNT="seetonic-run@$PROJECT.iam.gserviceaccount.com"

# Run one command that grants the service account a role. IAM can take a minute to see a new account, so retry.
grant() {
  for attempt in 1 2 3 4 5; do
    "$@" && return
    sleep 10
  done
  "$@"
}

# Without these, gcloud run deploy stops to ask whether to enable them, and creating the service account fails.
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com iam.googleapis.com \
  secretmanager.googleapis.com --project "$PROJECT"

if ! gcloud iam service-accounts describe "$SERVICE_ACCOUNT" --project "$PROJECT" >/dev/null 2>&1; then
  gcloud iam service-accounts create seetonic-run --project "$PROJECT" --display-name "Seetonic on Cloud Run"
fi
# Adding a binding that already exists changes nothing. --condition None stops a prompt when the policy has conditions.
# --format none drops the whole policy that each call prints.
for role in roles/aiplatform.user roles/bigquery.jobUser; do
  grant gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$SERVICE_ACCOUNT" --role "$role" \
    --condition None --format none
done
# Created by hand, not here, so the key never lands in a file.
grant gcloud secrets add-iam-policy-binding typesafe-api-key --project "$PROJECT" \
  --member "serviceAccount:$SERVICE_ACCOUNT" --role roles/secretmanager.secretAccessor --format none

if ! gcloud storage buckets describe "gs://$BUCKET" --project "$PROJECT" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://$BUCKET" --project "$PROJECT" --location "$DATA_LOCATION"
fi
grant gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member "serviceAccount:$SERVICE_ACCOUNT" \
  --role roles/storage.objectAdmin --format none

bq --project_id "$PROJECT" --location "$DATA_LOCATION" query --nouse_legacy_sql "
CREATE SCHEMA IF NOT EXISTS \`$PROJECT.$DATASET\` OPTIONS (location = '$DATA_LOCATION');
CREATE TABLE IF NOT EXISTS \`$PROJECT.$DATASET.pages\` (
  doc_id STRING, page INT64, embedding ARRAY<FLOAT64>
);
CREATE TABLE IF NOT EXISTS \`$PROJECT.$DATASET.$QUESTIONS_TABLE\` (
  ts TIMESTAMP, doc_id STRING, question STRING, pages ARRAY<STRUCT<page INT64, score FLOAT64>>,
  statuses ARRAY<STRING>, latency_ms INT64, embed_model STRING, answer_model STRING, route STRING,
  jev_route STRING, jev_confidence FLOAT64
);
-- CREATE TABLE IF NOT EXISTS leaves a table made before a column without it.
ALTER TABLE \`$PROJECT.$DATASET.$QUESTIONS_TABLE\` ADD COLUMN IF NOT EXISTS route STRING,
  ADD COLUMN IF NOT EXISTS jev_route STRING, ADD COLUMN IF NOT EXISTS jev_confidence FLOAT64;"
grant bq --project_id "$PROJECT" --location "$DATA_LOCATION" query --nouse_legacy_sql \
  "GRANT \`roles/bigquery.dataEditor\` ON SCHEMA \`$PROJECT.$DATASET\` TO 'serviceAccount:$SERVICE_ACCOUNT'"
