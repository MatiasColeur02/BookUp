#!/usr/bin/env bash
set -euo pipefail

aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$REGISTRY"

# Los tags son inmutables: si este hash ya está en el repo no hay nada que subir.
REPO="${IMAGE_URI#*/}"
if aws ecr describe-images --region "$REGION" --repository-name "${REPO%%:*}" \
  --image-ids imageTag="${IMAGE_URI##*:}" >/dev/null 2>&1; then
  echo "La imagen $IMAGE_URI ya existe, no se vuelve a subir."
  exit 0
fi

docker build --platform "$PLATFORM" --provenance=false -t "$IMAGE_URI" "$SOURCE_DIR"
docker push "$IMAGE_URI"
