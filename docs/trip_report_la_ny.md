# Trip comparison: Los Angeles, CA to New York, NY

Generated 2026-10-19. Route from `ors`: 2809.1 mi. Stations in the corridor: 334. Tank 490 mi (after the detour reserve), start fuel 490 mi (free), 10 mpg.

Costs are the planner's fuel cost for the stops chosen, before the detour fuel that the API adds. 'vs best' is the difference from the first row.

## Real route miles

| method                 | cost $ | vs best | ms  | stops | note                 |
|------------------------|--------|---------|-----|-------|----------------------|
| window DP (production) | 710.55 | +0.00   | 0.6 | 15    |                      |
| greedy next-cheaper    | 710.55 | +0.00   | 0.4 | 15    |                      |
| naive station graph    | 724.33 | +13.78  | 7.0 | -     | ignores fuel carried |

## Same trip on a 1-mile grid (what the oracle and the state graph need)

| method                 | cost $ | vs best | ms    | stops | note |
|------------------------|--------|---------|-------|-------|------|
| grid DP (oracle)       | 710.51 | +0.00   | 29.1  | -     |      |
| state graph (Dijkstra) | 710.51 | +0.00   | 426.2 | -     |      |
| window DP (production) | 710.51 | +0.00   | 0.6   | 15    |      |
| greedy next-cheaper    | 710.51 | +0.00   | 0.4   | 15    |      |

Largest gap between the exact methods: $0.000000. They agree.
