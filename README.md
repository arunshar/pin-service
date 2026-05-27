# Pin Infrastructure Service

A reference implementation of a **pickup / drop-off (PUDO) pin selection service** for an autonomous-vehicle ride-hail fleet. This repo demonstrates the canonical serving path used by teams like Waymo's Pin Infrastructure group: candidate generation → hard-constraint filtering → ML scoring → congestion-aware re-ranking → load shedding, fronted by a gRPC API with end-to-end observability.

> **Why this exists.** Production AV ride-hail systems can't just pick "the lat/lon nearest the rider." The chosen pin has to be on a drivable lane, legal to stop at, walkable from the rider's actual position, and globally coordinated so that a hundred riders converging on a stadium exit don't all get assigned the same curb. This repo is a minimal but realistic implementation of that problem.

---

## Architecture

```
              ┌────────────────────────────────────────────────────────────┐
  rider  ──►  │  gRPC SelectPin                                            │
              │   1. candidate generation (H3 grid)                        │
              │   2. hard-constraint filter (HD map polygons)              │
              │   3. ML scoring (gradient-boosted regressor)               │
              │   4. congestion-aware re-rank (sliding-window penalty)     │
              │   5. load shedding (global backpressure)                   │
              │                                                            │
              │   metrics → Prometheus :9090                               │
              │   traces  → OTLP → OpenTelemetry Collector → Jaeger        │
              └────────────────────────────────────────────────────────────┘
```

### Design invariants

- **ML never overrides hard constraints.** A high model score cannot legalize an illegal stop. Constraints are evaluated before scoring; scoring only ranks the feasible set.
- **Latency budget: p99 < 200 ms.** Every stage emits its own span and bucket.
- **Stateless except for congestion.** The only mutable state is the sliding-window congestion tracker. Everything else is pure functions of the request + model + HD map.
- **Reproducibility under load.** Candidate generation is deterministic for a given (rider, params) tuple, so load tests are repeatable.

---

## Quick start (local Python)

```bash
# 1. Create venv + install
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Generate proto stubs and train the toy model
bash scripts/gen_proto.sh
python scripts/train_model.py

# 3. Run tests
pytest

# 4. Start the server (terminal A)
python -m pin_service.server

# 5. Hit it (terminal B)
python -m client.client --n 10

# 6. Scrape metrics
curl localhost:9090/metrics | grep pin_
```

## Full stack with observability

```bash
docker compose -f docker/docker-compose.yml up --build
```

Then open:

- **Jaeger UI** — http://localhost:16686 (browse traces by `service.name=pin-service`)
- **Prometheus** — http://localhost:9091
- **Grafana** — http://localhost:3000 (admin/admin)

## Load testing

```bash
locust -f load_tests/locustfile.py --headless \
       -u 200 -r 50 -t 1m --host=localhost:50051
```

Watch the Prometheus `pin_latency_seconds` histogram and the `pin_requests_total{status}` counter. As you push more users you should see the congestion penalty kick in (visible in Jaeger trace timing on the `congestion_rerank` span) and eventually `LOAD_SHED` responses appear.

---

## Repository layout

| Path | Purpose |
|------|---------|
| `proto/pin_service.proto` | gRPC service contract |
| `pin_service/server.py` | Server entry point; wires the pipeline |
| `pin_service/candidate_gen.py` | H3-based candidate generation |
| `pin_service/constraints.py` | HD-map polygon hard-constraint filter |
| `pin_service/scorer.py` | ML scoring (sklearn GBR) |
| `pin_service/congestion.py` | Sliding-window congestion + load shedding |
| `pin_service/metrics.py` | Prometheus counters & histograms |
| `pin_service/telemetry.py` | OpenTelemetry tracing setup |
| `scripts/train_model.py` | Train and persist the scoring model |
| `scripts/gen_proto.sh` | Regenerate Python stubs from `.proto` |
| `tests/` | Unit tests for each module |
| `load_tests/locustfile.py` | gRPC load-test harness |
| `docker/` | Dockerfile + full observability compose |

---

## Production extensions (a real Pin Infrastructure team's roadmap)

This scaffold is a clean foundation; in a production system you would extend it with:

1. **C++ serving path.** Port the hot path (steps 1-4) to a C++ gRPC server, with the trained sklearn model exported to ONNX and served by ONNX Runtime or NVIDIA Triton. The Python service stays as the reference implementation and the integration-test oracle.
2. **Real HD-map backend.** Replace the Shapely-polygon stub with a service backed by Lanelet2 or an internal HD map. Add lane-level reachability, curb-side validation, and dynamic geofences.
3. **Feature store.** Replace the in-line feature stubs with calls to Feast / Tecton / an internal store, with sub-10ms p99 reads.
4. **Sharded congestion state.** The single-mutex tracker doesn't scale past one process. Use a sharded LRU keyed by H3 cell with consistent hashing, or move to Redis with Lua scripts for the increment-and-evict step.
5. **Shadow-mode model deployment.** Run new scoring models in shadow on a fraction of traffic, compare to production, and gate roll-out on offline-online metric parity.
6. **Closed-loop training data.** Pipe completed-trip telemetry (rider rating, actual stop precision, manual pin edits) into the training set automatically.
7. **Differential privacy on rider features.** Aggregate rider behavior features with DP noise before they enter the feature store.

---

## License

Apache 2.0
