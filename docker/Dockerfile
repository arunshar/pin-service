# syntax=docker/dockerfile:1.6
# -----------------------------------------------------------------------------
# Pin Infrastructure Service — production-ish container.
#
# Multi-stage build:
#   1. builder  — installs all build-time deps and compiles protos
#   2. runtime  — slim image with only what the server needs
# -----------------------------------------------------------------------------

FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install --prefix=/install \
    grpcio grpcio-tools protobuf h3 shapely numpy scikit-learn joblib \
    prometheus-client \
    "opentelemetry-api>=1.20" "opentelemetry-sdk>=1.20" \
    "opentelemetry-exporter-otlp-proto-grpc>=1.20"

COPY proto/ ./proto/
COPY pin_service/ ./pin_service/
COPY scripts/ ./scripts/
COPY data/ ./data/

# Generate proto stubs and train the (toy) scoring model at build time so the
# runtime image has no codegen or training step on cold start.
RUN PYTHONPATH=. /install/bin/python -m grpc_tools.protoc \
        -I proto --python_out=pin_service --grpc_python_out=pin_service \
        proto/pin_service.proto \
    && sed -i 's/^import pin_service_pb2/from pin_service import pin_service_pb2/' \
        pin_service/pin_service_pb2_grpc.py \
    && PYTHONPATH=/install/lib/python3.11/site-packages:. python scripts/train_model.py

# -----------------------------------------------------------------------------
FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Non-root user for least-privilege runtime.
RUN useradd --create-home --uid 10001 pin
WORKDIR /app

COPY --from=builder /install /usr/local
COPY --from=builder /build/pin_service /app/pin_service
COPY --from=builder /build/data /app/data

USER pin
EXPOSE 50051 9090
ENTRYPOINT ["python", "-m", "pin_service.server"]
