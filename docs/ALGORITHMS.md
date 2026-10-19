# Algorithms: planner contract, station location, API

## Contract (apps/routing/planner/contract.py)
Route of D miles, stations at miles m_i with prices p_i, tank R = 500 mi (50 gal), 10 mpg, starts
with S0 miles of free fuel (default full). Buy any amount at stations while tank <= R. Minimise spend.
Empty tank on arrival is allowed. A plan is infeasible if the first station is beyond S0, any gap
exceeds R, or the last station is more than R from the end; the error names the mile.
Optimum = per-mile cheapest price within the previous R miles (lower bound and achievable).

## Algorithms compared (scripts/compare_planners.py, 3,000 random trips vs a grid-DP oracle)
Raw output of a full run, with timings for all four methods: `docs/benchmarks.txt`
(regenerate with `uv run python scripts/compare_planners.py --save`).

| method | optimal | notes |
|---|---|---|
| window DP (production) | 3000/3000 | O(n log n), 20k stations in 75-150 ms |
| greedy next-cheaper | 3000/3000 | correct, but O(n^2) worst case: 27 s on rising prices |
| state-graph Dijkstra | 3000/3000 | exact, needs integer miles, O(n*R): test oracle only |
| naive station graph | 645/3000 | wrong 79% of the time, avg 50% overpay |

## Locating stations (mile marker + offset)
Measured against stations placed at known route miles (0-3 mi off a 2,533 mi route):
| method | mean error | max error |
|---|---|---|
| planar lon/lat fraction x total length | 20 mi | 37 mi |
| planar lon/lat fraction, interpolated | 0.11 mi | 1.6 mi |
| nearest route vertex only | 0.09 mi | 1.5 mi |
| Mercator projection + KD-tree + segment projection (chosen) | 0.002 mi | ~0.02 mi at p99 |
PostGIS corridor queries on the full 14k-vertex geometry took 120 ms to 8 s depending on shape, so
selection and projection run in numpy over an in-memory snapshot (~8k stations, 12 ms per request).

## Assumptions
Starts with a full tank (not charged); stations within 3 mi (geocoded) / 5 mi (city centroid) of the
road are used; each stop off the road pays 2 x offset miles of extra fuel; capacity is reduced by that
reserve so a detour never strands the vehicle. Route distance is the sum of the geometry's segments.
