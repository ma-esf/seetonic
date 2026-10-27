#!/usr/bin/env bash
# Create the bucket, the BigQuery dataset and the pages table. Safe to rerun: each step leaves an existing one as it is.
# Reads the same environment variables as app/config.py, with the same defaults.
set -euo pipefail

PROJECT="${GOOGLE_CLOUD_PROJECT:-seetonic-demo}"
DATA_LOCATION="${DATA_LOCATION:-europe-north1}"
BUCKET="${BUCKET:-$PROJECT-files}"
DATASET="${DATASET:-seetonic}"

if ! gcloud storage buckets describe "gs://$BUCKET" --project "$PROJECT" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://$BUCKET" --project "$PROJECT" --location "$DATA_LOCATION"
fi

bq --project_id "$PROJECT" --location "$DATA_LOCATION" query --nouse_legacy_sql "
CREATE SCHEMA IF NOT EXISTS \`$PROJECT.$DATASET\` OPTIONS (location = '$DATA_LOCATION');
CREATE TABLE IF NOT EXISTS \`$PROJECT.$DATASET.pages\` (
  doc_id STRING, page INT64, width INT64, height INT64, has_text BOOL, embedding ARRAY<FLOAT64>
);"
