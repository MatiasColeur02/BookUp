#!/usr/bin/env bash
# Arma el directorio del paquete de Lambda: dependencias para el runtime de Lambda
# (manylinux x86_64) + el paquete app/ de la API.
set -euo pipefail

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

python3 -m pip install \
  --quiet \
  --disable-pip-version-check \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version "$PYTHON_VERSION" \
  --only-binary=:all: \
  --target "$BUILD_DIR" \
  -r "$SOURCE_DIR/requirements.txt"

# boto3 ya viene en el runtime de Lambda: sacarlo achica el zip a la mitad.
rm -rf "$BUILD_DIR"/boto3* "$BUILD_DIR"/botocore* "$BUILD_DIR"/s3transfer*

cp -R "$SOURCE_DIR/app" "$BUILD_DIR/app"
find "$BUILD_DIR" -type d -name "__pycache__" -prune -exec rm -rf {} +
