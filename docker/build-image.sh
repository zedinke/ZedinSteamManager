#!/bin/bash
# ZedinArkManager - ARK Server Docker Image Build Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="zedinarkmanager/ark-server"
IMAGE_TAG="${1:-latest}"

echo "Building ZedinArkManager ARK Server Docker image..."
echo "Image: ${IMAGE_NAME}:${IMAGE_TAG}"

cd "$SCRIPT_DIR"

docker build -f Dockerfile.zedin-ark-server -t "${IMAGE_NAME}:${IMAGE_TAG}" .

echo ""
echo "✅ Docker image built successfully!"
echo "Image: ${IMAGE_NAME}:${IMAGE_TAG}"
echo ""
echo "To push to registry (optional):"
echo "  docker push ${IMAGE_NAME}:${IMAGE_TAG}"

