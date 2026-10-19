# Trip comparison: New York, NY to Chicago, IL

Generated 2026-10-19. Route from `ors`: 802.8 mi. Stations in the corridor: 153. Tank 490 mi (after the detour reserve), start fuel 490 mi (free), 10 mpg.

Costs are the planner's fuel cost for the stops chosen, before the detour fuel that the API adds. 'vs best' is the difference from the first row.

## Real route miles

| method                 | cost $ | vs best | ms  | stops | note                 |
|------------------------|--------|---------|-----|-------|----------------------|
| window DP (production) | 95.67  | +0.00   | 0.2 | 1     |                      |
| greedy next-cheaper    | 95.67  | -0.00   | 0.1 | 1     |                      |
| naive station graph    | 106.04 | +10.37  | 2.8 | -     | ignores fuel carried |

## Same trip on a 1-mile grid (what the oracle and the state graph need)

| method                 | cost $ | vs best | ms    | stops | note |
|------------------------|--------|---------|-------|-------|------|
| grid DP (oracle)       | 95.75  | +0.00   | 10.8  | -     |      |
| state graph (Dijkstra) | 95.75  | +0.00   | 124.7 | -     |      |
| window DP (production) | 95.75  | +0.00   | 0.2   | 1     |      |
| greedy next-cheaper    | 95.75  | +0.00   | 0.1   | 1     |      |

Largest gap between the exact methods: $0.000000. They agree.
