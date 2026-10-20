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
      # `s3 rb --force` borra solo las versiones actuales: en un bucket versionado quedan
      # las anteriores y los delete markers, y el bucket no se puede borrar. Se vacía todo
      # por tandas (delete-objects acepta hasta 1000 claves; Versions + DeleteMarkers de una
      # página de 500 entran siempre).
      while :; do
        BATCH=$(aws s3api list-object-versions --bucket "$BUCKET" --region "$REGION" \
          --max-items 500 --output json \
          --query '{Objects: [Versions, DeleteMarkers][][].{Key: Key, VersionId: VersionId}, Quiet: `true`}')
        if [ "$(echo "$BATCH" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["Objects"]))')" = "0" ]; then
          break
        fi
        aws s3api delete-objects --bucket "$BUCKET" --region "$REGION" --delete "$BATCH" >/dev/null
      done
    fi
    aws s3api delete-bucket --bucket "$BUCKET" --region "$REGION"
    ;;
  *)
    echo "usage: bucket.sh create|delete" >&2
    exit 2
    ;;
esac
