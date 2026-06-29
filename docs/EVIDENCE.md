# pin-service — reproduced evidence

These are **reproduced** results: the serving path runs, the unit suite passes, and a real
Locust load test was executed against the live gRPC server on 2026-06-29. The ML scorer is a
gradient-boosted regressor trained on a **synthetic** satisfaction label and the map / supply
signals are **fixtures**, so the model and data stay illustrative; the **serving and
backpressure behavior below is real and measured**.

## Unit suite (per-stage)
```
20 passed
```
Candidate generation, hard-constraint filtering, ML scoring, congestion-aware re-ranking, and
load shedding each have unit coverage. Run with `PYTHONPATH=.:pin_service pytest -q`.

## Reproduced load test (Locust against the live gRPC server)
Run: `python -m pin_service.server` then
`locust -f load_tests/locustfile.py --headless -u 200 -r 50 -t 60s --host=localhost:50051`
(200 virtual users, 60 s, riders clustered on a single SF Union Square cell, localhost).

**Served curb-selection latency (status OK):**

| metric | value |
|---|---|
| p50 | 1 ms |
| p95 | 2 ms |
| p99 | 6 ms |
| mean | 4.4 ms |
| served requests | 150 |

**Backpressure fail-safe (the demand-control finding):** under a single-hotspot flood the
congestion tracker's load-shed engaged and shed **88,995 of 89,146 requests (~99.8%)** with a
fast reject at **~0.26 ms median**, holding served tail latency in the single-digit-ms range.
Offered rate **~1,495 req/s**; **0 server-side errors** (1 client-side RPC timeout / 89,146).

This reproduces the intended behavior: the congestion fail-safe (default `threshold=3`
assignments/cell/window, `load_shed_ratio=50`) caps admitted assignments at roughly 150 per 60 s
window and sheds the rest fast, so a curb hotspot cannot drive the served path into a latency
doom loop. The default congestion config is demo-scale; the docstring notes a sharded lock-free
LRU for production traffic.

## Honest scope
- **Reproduced (real, measured):** the gRPC serving path, the per-stage unit suite, the Locust
  load test, served p50/p95/p99, and the load-shed backpressure behavior above.
- **Illustrative (not a benchmark):** the GBDT scorer is trained on a synthetic satisfaction
  label; the HD-map and supply signals are fixtures. No external leaderboard is claimed.
