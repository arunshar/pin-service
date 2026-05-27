"""OpenTelemetry tracing setup.

We export OTLP traces to a collector (default localhost:4317), which can
forward to Jaeger, Tempo, Honeycomb, or any OTLP-compatible backend.

Each `SelectPin` invocation creates a root span with child spans for
candidate generation, feasibility filtering, scoring, and congestion
re-ranking. The trace_id is surfaced back to the client in the response
so that ops can pivot from a client-side log line to the full server
trace in one click.
"""

from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


_SERVICE_NAME = os.environ.get("PIN_SERVICE_NAME", "pin-service")
_OTLP_ENDPOINT = os.environ.get(
    "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
)
_OTLP_INSECURE = (
    os.environ.get("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() == "true"
)


def setup_tracing() -> trace.Tracer:
    """Initialize the global tracer provider and return a tracer."""
    resource = Resource.create(
        {
            "service.name": _SERVICE_NAME,
            "service.version": os.environ.get("PIN_VERSION", "0.1.0"),
        }
    )
    provider = TracerProvider(resource=resource)

    # In CI / local dev we may not have a collector. Swallow connection
    # errors so the service stays up; traces are best-effort.
    try:
        exporter = OTLPSpanExporter(
            endpoint=_OTLP_ENDPOINT, insecure=_OTLP_INSECURE
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
    except Exception:  # pragma: no cover - dev convenience
        pass

    trace.set_tracer_provider(provider)
    return trace.get_tracer(_SERVICE_NAME)
