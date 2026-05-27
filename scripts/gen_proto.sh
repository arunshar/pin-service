#!/usr/bin/env bash
# Regenerate Python stubs from proto/pin_service.proto.
#
# Usage:   bash scripts/gen_proto.sh
# Output:  pin_service/pin_service_pb2.py
#          pin_service/pin_service_pb2_grpc.py
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python -m grpc_tools.protoc \
    -I proto \
    --python_out=pin_service \
    --grpc_python_out=pin_service \
    proto/pin_service.proto

# grpc_tools emits absolute import paths; rewrite to relative for our pkg.
sed -i 's/^import pin_service_pb2/from pin_service import pin_service_pb2/' \
    pin_service/pin_service_pb2_grpc.py

echo "generated:"
ls -la pin_service/pin_service_pb2*.py
