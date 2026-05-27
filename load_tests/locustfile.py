"""Locust load-test for the gRPC pin-service.

Usage:
    # In one terminal:
    python -m pin_service.server

    # In another:
    locust -f load_tests/locustfile.py --headless \
           -u 200 -r 50 -t 1m --host=localhost:50051

Locust reports p50/p95/p99 latency. Pair with the Prometheus dashboard
on :9090 to verify server-side and client-side numbers match.
"""

from __future__ import annotations

import random
import time

import grpc
from locust import User, between, events, task

from pin_service import pin_service_pb2, pin_service_pb2_grpc


class PinUser(User):
    """A virtual user that hammers SelectPin with randomized riders."""

    wait_time = between(0.05, 0.2)

    def on_start(self) -> None:
        host, port = self.host.split(":")
        self.channel = grpc.insecure_channel(f"{host}:{port}")
        self.stub = pin_service_pb2_grpc.PinServiceStub(self.channel)

    def on_stop(self) -> None:
        self.channel.close()

    @task
    def select_pin(self) -> None:
        # Riders clustered around SF Union Square (matches the HD-map fixture).
        rider = pin_service_pb2.LatLng(
            lat=37.779 + random.uniform(-0.005, 0.005),
            lon=-122.408 + random.uniform(-0.005, 0.005),
        )
        drop = pin_service_pb2.LatLng(
            lat=37.785 + random.uniform(-0.005, 0.005),
            lon=-122.408 + random.uniform(-0.005, 0.005),
        )
        req = pin_service_pb2.SelectPinRequest(
            request_id=f"lt-{random.randint(0, 1_000_000_000)}",
            rider_location=rider,
            dropoff_location=drop,
            rider_id=f"rider-{random.randint(0, 10_000)}",
            timestamp_ms=int(time.time() * 1000),
        )
        t0 = time.perf_counter()
        try:
            resp = self.stub.SelectPin(req, timeout=2.0)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            status_name = pin_service_pb2.SelectPinResponse.Status.Name(
                resp.status
            )
            events.request.fire(
                request_type="grpc",
                name=f"SelectPin/{status_name}",
                response_time=elapsed_ms,
                response_length=resp.ByteSize(),
                exception=None,
            )
        except grpc.RpcError as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            events.request.fire(
                request_type="grpc",
                name="SelectPin/RPC_ERROR",
                response_time=elapsed_ms,
                response_length=0,
                exception=exc,
            )
