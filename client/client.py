"""Demo gRPC client for manual sanity checks.

Usage:
    python -m client.client
    python -m client.client --host localhost --port 50051 --n 10
"""

from __future__ import annotations

import argparse
import time

import grpc

from pin_service import pin_service_pb2, pin_service_pb2_grpc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=50051)
    parser.add_argument("--n", type=int, default=5, help="number of requests")
    args = parser.parse_args()

    channel = grpc.insecure_channel(f"{args.host}:{args.port}")
    stub = pin_service_pb2_grpc.PinServiceStub(channel)

    print("health:", stub.HealthCheck(pin_service_pb2.HealthCheckRequest()))

    rider = pin_service_pb2.LatLng(lat=37.7799, lon=-122.4080)
    drop = pin_service_pb2.LatLng(lat=37.7858, lon=-122.4080)

    for i in range(args.n):
        req = pin_service_pb2.SelectPinRequest(
            request_id=f"demo-{i}",
            rider_location=rider,
            dropoff_location=drop,
            rider_id="demo-rider",
            timestamp_ms=int(time.time() * 1000) + i,
        )
        resp = stub.SelectPin(req)
        status = pin_service_pb2.SelectPinResponse.Status.Name(resp.status)
        if resp.status == pin_service_pb2.SelectPinResponse.OK:
            print(
                f"[{i:02d}] {status} "
                f"lat={resp.pin.location.lat:.6f} lon={resp.pin.location.lon:.6f} "
                f"cell={resp.pin.h3_cell} score={resp.pin.score:.3f} "
                f"walk={resp.pin.estimated_walk_meters:.1f}m "
                f"latency={resp.server_latency_ms:.2f}ms "
                f"feasible={resp.candidates_feasible}/{resp.candidates_considered}"
            )
        else:
            print(f"[{i:02d}] {status}: {resp.reason}")


if __name__ == "__main__":
    main()
