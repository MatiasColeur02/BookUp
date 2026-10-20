#!/usr/bin/env bash
# Alta y baja de un bucket con la CLI (ver el comentario de terraform_data.bucket).
set -euo pipefail

case "$1" in
  create)
    # Idempotente: si ya es nuestro, no hace nada.
    if aws s3api head-bucket --bucket "$BUCKET" --region "$REGION" 2>/dev/null; then
      echo "Bucket $BUCKET already exists"
      exit 0
    fi
    if [ "$REGION" = "us-east-1" ]; then
      aws s3api create-bucket --bucket "$BUCKET" --region "$REGION"
    else
      aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
        --create-bucket-configuration "LocationConstraint=$REGION"
    fi
    aws s3api wait bucket-exists --bucket "$BUCKET" --region "$REGION"
    ;;
  delete)
    if ! aws s3api head-bucket --bucket "$BUCKET" --region "$REGION" 2>/dev/null; then
      exit 0
    fi
    if [ "$FORCE_DESTROY" = "true" ]; then
      aws s3 rb "s3://$BUCKET" --region "$REGION" --force
    else
      aws s3 rb "s3://$BUCKET" --region "$REGION"
    fi
    ;;
  *)
    echo "usage: bucket.sh create|delete" >&2
    exit 2
    ;;
esac
