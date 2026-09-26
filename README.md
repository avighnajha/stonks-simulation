# Stonks simulation

Python strategy SDK and controlled-run worker. Strategies are the owner's learning
work: `idle` and `scripted` are infrastructure test fixtures, not realistic populations.

Requires Python 3.11+, Node 22, a built Stonks checkout, and PostgreSQL 14+ on a
dedicated research server. The Python runtime has no third-party dependencies.

```sh
python -m unittest discover -s tests -v
export STONKS_EXCHANGE_DIR=/path/to/Stonks
export RESEARCH_DATABASE_ADMIN_URL=postgresql://provisioner:password@localhost:5432/postgres
export RESEARCH_API_URL=http://localhost:3004
export RESEARCH_WORKER_KEY=the-same-private-key-as-trading-service
python -m stonks_sim.worker
```

In PowerShell set variables with `$env:NAME='value'`. The provisioner requires
CREATEDB and CREATEROLE; do not point it at a production cluster. Each run gets a
fresh database and random restricted login. The database is dropped after export,
including on handled failure. A forcibly killed process can leave an orphan: use
the Stonks `provision.js drop stonks_run_<32 hex run ID>` operator command after
confirming that run is no longer active. Never enumerate and delete all databases.

Build the exchange bridge with `npm ci && npm run build` in
`Stonks/services/trading_service`. `NODE_BINARY` can override the Node executable.
For a standalone run use `--manifest examples/smoke.json --output result.json`.

## Your strategies

Subclass `stonks_sim.sdk.Strategy` in your own module. Implement callback methods
and return a list of place/cancel/schedule actions. Use `context.rng` and
`context.now_ms`; never wall time or unseeded randomness. Cash/quantity strings
preserve exchange precision. `context.state` contains your account/orders and
current public books. News/reference observations arrive separately after delay.
Fill notifications are delivered at scheduled agent wakeups, not instantaneously.

Operator registration: set `STONKS_STRATEGY_REGISTRY` to a JSON mapping such as
`{"my_maker":"strategies.my_maker:MyMaker"}` and add `my_maker` to the exchange's
comma-separated `RESEARCH_STRATEGIES`. User manifests cannot select arbitrary
module paths. Strategy code is trusted operator-installed Python: this is NOT an
untrusted-code security sandbox. In-process Python can access process resources.

Population parameters and strategy-specific JSON are snapshotted. IDs are stable
by group/index, so rename a group only when you intend different random streams.
World factor amplitudes are log-value volatility per square-root simulated hour.
`signalNoise` is log-value observation noise (valuation messages) and additive
signal noise (news). Zero noise is intentionally perfect information. No signal
is observed before its scheduled delivery. Latent value is not a redeemable payoff.

## Timing and measurements

Logical time is integer milliseconds from 2000-01-01 UTC. One priority queue orders
events by time then insertion sequence. Initial order: world tick, configured shock
events in manifest order, agent wakeups sorted by ID, sampling. Derived observations
and acknowledgements enter the same queue. This tie convention is part of protocol 1.
Zero-delay news is delivered after the already-enqueued events at that same time.
The matching/settlement implementation is the real exchange engine through a private
JSON-lines bridge. There is no Redis timing dependency and no duplicate matcher.

Sampling produces up to approximately 501 book/reference points. Spread and RMSE
are sample averages over two-sided books, with missing-book fraction reported
separately. They are not time-weighted liquidity estimates. P&L is marked using the
engine's last-trade/initial-price convention. Raw fills and action records support
further analysis. Fees are currently zero; no shorting, margin or derivatives.

Hard limits: 100 agents, 10 assets, validated scheduled-step budget, 5,000 commands,
100,000 processed events and 600 seconds of worker compute. This is a resource-light
reference implementation, not a throughput claim. At most one active run per worker.
Keep deployment concurrency bounded. Failed runs restart from a fresh manifest;
mid-run checkpoint recovery is not implemented.

Reproducibility is under pinned code/runtime/parameters. The economic hash excludes
physical logs and run UUIDs; compare hashes only with compatible versions. Strategy
code must obey the deterministic contract. Results do not establish real-market alpha.
