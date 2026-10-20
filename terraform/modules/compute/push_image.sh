#!/usr/bin/env bash
set -euo pipefail

aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$REGISTRY"

docker build --platform "$PLATFORM" --provenance=false -t "$IMAGE_URI" "$SOURCE_DIR"
docker push "$IMAGE_URI"
