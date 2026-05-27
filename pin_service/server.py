"""gRPC server for the Pin Infrastructure Service.

Wires together:
  - candidate generation (H3)
  - hard-constraint filtering (HD-map polygons)
  - ML scoring (sklearn GBR, loaded lazily)
  - congestion-aware re-ranking
  - load shedding
  - OpenTelemetry tracing
  - Prometheus metrics

Run with:
    python -m pin_service.server
"""

from __future__ import annotations

import logging
import os
import signal
import time
from concurrent import futures

import grpc
import numpy as np
from opentelemetry import trace

from pin_service import pin_service_pb2, pin_service_pb2_grpc
from pin_service.candidate_gen import generate_candidates
from pin_service.congestion import CongestionTracker
from pin_service.constraints import filter_feasible
from pin_service.metrics import (
    CANDIDATES_CONSIDERED,
    CANDIDATES_FEASIBLE,
    LATENCY,
    REQUESTS,
    start_metrics_server,
)
from pin_service.scorer import ScoringContext, score_candidates
from pin_service.telemetry import setup_tracing


logging.basicConfig(
    level=os.environ.get("PIN_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("pin_service.server")


_VERSION = os.environ.get("PIN_VERSION", "0.1.0")


class PinServiceServicer(pin_service_pb2_grpc.PinServiceServicer):
    """gRPC handler. Stateless except for the congestion tracker."""

    def __init__(self) -> None:
        self.congestion = CongestionTracker()
        self.tracer = setup_tracing()

    # --- internal helpers -------------------------------------------------

    @staticmethod
    def _haversine_m(lat1, lon1, lat2, lon2):
        """Great-circle distance in meters."""
        from math import radians, sin, cos, asin, sqrt

        r1, r2 = radians(lat1), radians(lat2)
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat / 2) ** 2 + cos(r1) * cos(r2) * sin(dlon / 2) ** 2
        return 2 * 6_371_000 * asin(sqrt(a))

    # --- RPC entry points -------------------------------------------------

    def SelectPin(self, request, context):
        t0 = time.perf_counter()
        with self.tracer.start_as_current_span("SelectPin") as span:
            span_ctx = span.get_span_context()
            trace_id_hex = format(span_ctx.trace_id, "032x")

            # Validate.
            if request.rider_location.lat == 0 and request.rider_location.lon == 0:
                return self._fail(
                    pin_service_pb2.SelectPinResponse.INVALID_REQUEST,
                    trace_id_hex,
                    "rider_location is unset",
                    t0,
                )

            # Backpressure: shed load before doing work.
            if self.congestion.should_load_shed():
                span.set_attribute("load_shed", True)
                return self._fail(
                    pin_service_pb2.SelectPinResponse.LOAD_SHED,
                    trace_id_hex,
                    "service overloaded; retry with backoff",
                    t0,
                )

            # 1. Candidate generation
            with self.tracer.start_as_current_span("candidate_gen"):
                candidates = generate_candidates(
                    request.rider_location.lat, request.rider_location.lon
                )
            CANDIDATES_CONSIDERED.observe(len(candidates))
            span.set_attribute("candidates_considered", len(candidates))

            # 2. Hard-constraint filter
            with self.tracer.start_as_current_span("feasibility_filter"):
                feasible = filter_feasible(candidates)
            CANDIDATES_FEASIBLE.observe(len(feasible))
            span.set_attribute("candidates_feasible", len(feasible))

            if not feasible:
                return self._fail(
                    pin_service_pb2.SelectPinResponse.NO_FEASIBLE_PIN,
                    trace_id_hex,
                    "no candidate satisfied hard constraints",
                    t0,
                    candidates_considered=len(candidates),
                    candidates_feasible=0,
                )

            # 3. ML scoring
            with self.tracer.start_as_current_span("ml_scoring"):
                ctx = ScoringContext(
                    rider_lat=request.rider_location.lat,
                    rider_lon=request.rider_location.lon,
                    timestamp_ms=request.timestamp_ms or int(time.time() * 1000),
                )
                scores = score_candidates(feasible, ctx)

            # 4. Congestion re-ranking
            with self.tracer.start_as_current_span("congestion_rerank"):
                cells = [c.h3_cell for c in feasible]
                penalties = self.congestion.penalties_for(cells)
                final_scores = scores - penalties
                best_idx = int(np.argmax(final_scores))
                best = feasible[best_idx]
                self.congestion.record_assignment(best.h3_cell)

            # 5. Build response
            walk_m = self._haversine_m(
                request.rider_location.lat,
                request.rider_location.lon,
                best.lat,
                best.lon,
            )
            latency_ms = (time.perf_counter() - t0) * 1000.0
            LATENCY.observe(latency_ms / 1000.0)
            REQUESTS.labels(status="OK").inc()

            return pin_service_pb2.SelectPinResponse(
                status=pin_service_pb2.SelectPinResponse.OK,
                pin=pin_service_pb2.SelectedPin(
                    location=pin_service_pb2.LatLng(lat=best.lat, lon=best.lon),
                    h3_cell=best.h3_cell,
                    score=float(final_scores[best_idx]),
                    estimated_walk_meters=walk_m,
                    # Rough ETA placeholder: 3 m/s walking + 30s vehicle overhead
                    estimated_eta_seconds=walk_m / 3.0 + 30.0,
                ),
                trace_id=trace_id_hex,
                candidates_considered=len(candidates),
                candidates_feasible=len(feasible),
                server_latency_ms=latency_ms,
            )

    def HealthCheck(self, request, context):
        return pin_service_pb2.HealthCheckResponse(
            status="SERVING", version=_VERSION
        )

    # --- error helpers ---------------------------------------------------

    def _fail(
        self,
        status,
        trace_id,
        reason,
        t0,
        candidates_considered: int = 0,
        candidates_feasible: int = 0,
    ):
        latency_ms = (time.perf_counter() - t0) * 1000.0
        LATENCY.observe(latency_ms / 1000.0)
        status_name = pin_service_pb2.SelectPinResponse.Status.Name(status)
        REQUESTS.labels(status=status_name).inc()
        return pin_service_pb2.SelectPinResponse(
            status=status,
            trace_id=trace_id,
            reason=reason,
            server_latency_ms=latency_ms,
            candidates_considered=candidates_considered,
            candidates_feasible=candidates_feasible,
        )


def serve(host: str = "[::]", port: int = 50051, workers: int = 8) -> None:
    """Start the gRPC server. Blocks until SIGTERM/SIGINT."""
    start_metrics_server()
    log.info("metrics endpoint listening on :%s", os.environ.get("PIN_METRICS_PORT", "9090"))

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=workers),
        options=[
            ("grpc.so_reuseport", 0),
            ("grpc.max_concurrent_streams", 100),
        ],
    )
    pin_service_pb2_grpc.add_PinServiceServicer_to_server(
        PinServiceServicer(), server
    )
    addr = f"{host}:{port}"
    server.add_insecure_port(addr)
    server.start()
    log.info("pin-service v%s listening on %s", _VERSION, addr)

    # Graceful shutdown on SIGTERM/SIGINT.
    def _shutdown(_signum, _frame):
        log.info("shutdown signal received; draining...")
        server.stop(grace=5).wait()
        log.info("server stopped")

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    server.wait_for_termination()


if __name__ == "__main__":
    serve(
        host=os.environ.get("PIN_HOST", "[::]"),
        port=int(os.environ.get("PIN_PORT", "50051")),
        workers=int(os.environ.get("PIN_WORKERS", "8")),
    )
