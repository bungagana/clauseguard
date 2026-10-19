# Chat turn latency

Measured in process through the FastAPI sandbox on one developer machine. `live` includes key rotation when a quota ran out.

| mode | turns | median | p90 | max |
|---|---|---|---|---|
| offline | 20 | 0.18 s | 0.30 s | 0.81 s |
| live | 5 | 8.59 s | 12.74 s | 40.51 s |
