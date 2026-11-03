# Writing your first Python strategy

The SDK is `stonks_sim.sdk`. Write strategies in this repository; the runner owns
time, information delivery, accounts and exchange calls. You implement decisions.
This interface currently runs controlled experiments. A shared-market REST/WebSocket
adapter is future work.

## Interface

Create `strategies/__init__.py` and `strategies/my_strategy.py`:

```python
from stonks_sim.sdk import Strategy

class MyStrategy(Strategy):
    def __init__(self, parameters):
        super().__init__(parameters)
        self.estimates = {}

    def on_wakeup(self, context):
        # Read your account and the public books; return your trading decisions.
        return []

    def on_observation(self, observation, context):
        if observation['type'] == 'valuation':
            self.estimates[observation['assetId']] = observation['estimate']
        return []

    def on_fill(self, fill, context):
        return []

    def on_order_update(self, update, context):
        return []
```

This is an intentionally inactive skeleton. Each agent gets a separate instance
and private random stream. Store its beliefs and bookkeeping on `self`.

| Callback | When it runs |
| --- | --- |
| `on_wakeup(context)` | At time zero, every group `wakeMs`, and requested extra wakeups |
| `on_observation(observation, context)` | When a permitted news/valuation message reaches this agent |
| `on_fill(fill, context)` | At its next wakeup, for newly retrieved fills (up to 500 per wakeup) |
| `on_order_update(update, context)` | After its place/cancel action is processed |

All callbacks return a list, including `[]` when inactive. Keep callbacks finite
and fast. An acknowledgement callback that always emits another action can create
an endless same-time loop; react to meaningful state changes instead.

## Context and data

- `context.now_ms`: integer simulated milliseconds, not wall time.
- `context.rng`: seeded `random.Random` unique to the agent. Use this for randomness.
- `context.asset_ids`: mapping from manifest asset label to exchange UUID.
- `context.state['books']`: label -> `{'buys': [...], 'sells': [...]}`; levels contain
  price/quantity strings, ordered best first. Either side can be empty.
- `context.state['account']['wallet']`: available `balance` and `frozen_balance`.
- `context.state['account']['positions']`: positions with UUID `assetId`, quantities,
  reserved quantities, average cost and marked values.
- `context.state['orders']`: the latest 100 own orders, including terminal orders.
  Track IDs from acknowledgements if your strategy maintains a longer history.

Use `context.asset_ids['a']` to find the holding whose `assetId` matches asset `a`.
Actions and observation messages use manifest labels; fills and order records use
exchange UUIDs. The mapping contains public instrument identities, not private values.
Treat context as read-only. A context is a snapshot: actions can change the account
before a later callback, including between fill/wakeup callbacks at the same time.

Use `decimal.Decimal` for money/quantity calculations. Emit prices as strings with
two decimal places and quantities with four; no shorting or borrowing is supported.

## Types and editor autocomplete

Import contracts directly from `stonks_sim.sdk` (or `stonks_sim.types`).
The package includes a `py.typed` marker for editors and installed-package type checking.
See [the fully typed, inactive example](../examples/typed_strategy.py).

| Contract | What it describes |
| --- | --- |
| `Asset` | Public name, sector/subsector, manifest `id`, exchange UUID `exchange_id`, `initial_price` |
| `MarketState`, `Account`, `Wallet`, `Position` | Own available/reserved balances, holdings and marked P&L |
| `OrderBook`, `BookLevel` | Public aggregated bid/ask levels; either side may be empty |
| `Order`, `Fill` | Own exchange orders and executions, using exchange UUIDs |
| `Observation`, `NewsObservation`, `ValuationObservation` | Delayed information; narrow with `observation['type']` |
| `Action`, `PlaceAction`, `CancelAction`, `ScheduleAction` | Commands returned by callbacks |
| `OrderUpdate`, `OrderAccepted`, `OrderRejected` | Acknowledgements; failures have `rejected: True` and `message` |
| `Side`, `OrderType`, `OrderStatus` | Literal unions for valid enum values |
| `AssetLabel`, `AssetId`, `OrderId`, `DecimalString` | Documented string aliases, not runtime wrappers |
| `StrategyParameters` | Strategy-specific JSON configuration; validate your own parameters |

`context.assets['a']` now supplies typed public instrument metadata. Its `id` is
`'a'`; its `exchange_id` matches position/fill/order asset UUIDs. `initial_price`
is the listing/start price, **not** a live fundamental value. Factor weights,
shocks, future news and hidden values are excluded. Contexts receive detached metadata
dictionaries, so changes do not alter the manifest or other agents' metadata.
The existing `context.asset_ids` mapping remains available.

## Trading universe (SDK 0.2.0+)

Every agent has one cash balance shared across its tradable assets. Configure each
population group's Trading universe in the Research UI: all experiment assets or
an explicit selection. In manifests, `groups[].tradableAssets` is an optional
non-empty, unique list of run asset labels, for example `["a", "b"]`. Omission
means every experiment asset. This is a group setting, not strategy-specific JSON.

Every callback receives `context.tradable_assets: dict[AssetLabel, Asset]`:

```python
for label, asset in context.tradable_assets.items():
    book = context.state['books'][label]
    # Choose quotes using this asset's inventory and your shared cash budget.
```

The values have the same typed public metadata as `context.assets`. Use this
mapping as the order-placement universe. `context.assets`, `context.asset_ids`,
books and permitted observations still include all experiment assets, so a bot
can use another market as information without trading it. Full account positions
remain visible. The runner and Node adapter independently reject placement outside
the configured scope, even if strategy code changes its local context dictionary.
These checks are not an operating-system sandbox for untrusted Python.

Starting inventory is allocated per agent per tradable asset; cohort initial
wealth uses that same set. An old manifest without `tradableAssets` behaves as
before. Existing manually constructed `Context` objects default their tradable
metadata to a detached copy of `assets`. New runtime contexts always carry the
configured subset. Fill and wakeup callbacks in one wake cycle can share a
snapshot; treat all context data as read-only.

See `examples/scoped.json` for a two-asset experiment with a specialist buyer.


These are `TypedDict` contracts: access remains `position['quantity']`, not
`position.quantity`. They add autocomplete/static checking without changing the
JSON wire format or converting monetary values to floats. Runtime validation is
still performed by the runner/exchange. Treat callback data as read-only.

Prices, cash and quantities use decimal strings; `DecimalString` does not validate
precision. Observation estimates/signals are floating-point model outputs.
A successful cancellation omits `filledQuantity` and `message`; a rejected command
has no `orderId`. Check for the relevant key before accessing it.

To check your SDK and the example (Python 3.11+):

```sh
python -m pip install -e ".[dev]"
python -m mypy
python -m mypy --strict strategies/my_strategy.py
```

## Actions

```python
# Resting limit order, or an immediate match if it crosses the opposite book:
{'op': 'place', 'asset': 'a', 'side': 'BUY', 'type': 'LIMIT',
 'price': '99.50', 'quantity': '1.0000'}

# Protected market order: BUY price is a maximum; SELL price is a minimum.
# Unfilled quantity is cancelled immediately.
{'op': 'place', 'asset': 'a', 'side': 'BUY', 'type': 'MARKET',
 'price': '101.00', 'quantity': '1.0000'}

{'op': 'cancel', 'orderId': '<your exchange order UUID>'}
{'op': 'schedule', 'atMs': context.now_ms + 500}
```

Return at most 20 actions per callback. Extra wakeups must be strictly in the future
and do not replace the regular cadence. There is a 5,000-command budget per run.
Invalid exchange orders produce `{'rejected': True, 'message': '...'}` acknowledgements;
malformed runner actions fail the run. Inspect `examples/smoke.json` and exported
`decisions` for actual successful exchange response shapes.

## Information access

Configure each group's `information` as `public` (default, news only), `valuation`,
`both`, or `none`. `delayMs` delays observations; `signalNoise` controls their noise.
Every group can see current public books when a callback runs. These controls do
not simulate network latency on orders or stale book feeds.

News contains `type`, label `assetId`, `headline`, `signal`, `publishedAt`, `observedAt`.
Valuation messages replace headline/signal with `estimate`. Hidden shock size and
true reference values are absent from callback data. Reference curves in exported
results are for researcher analysis after the experiment.

## Register and use it

From this checkout, the operator sets:

```sh
export STONKS_STRATEGY_REGISTRY='{"my_strategy":"strategies.my_strategy:MyStrategy"}'
export RESEARCH_STRATEGIES=my_strategy
```

The exchange trading service also needs `RESEARCH_STRATEGIES=my_strategy`. Both
settings are supplied by the Stonks Docker overlay from its root `.env`. Rebuild
the worker after changing Python source and recreate the trading service when
changing its allowlist. The name then appears in Research's strategy selector.
Modules must be importable from the checkout; the initial runtime runs from there.
Only trusted operator-installed code is supported; this is not a Python sandbox.

Select your strategy for a group, set count/cash/inventory/wakeup/information,
and put your strategy-specific settings in the group's parameters JSON. Inventory
is allocated per tradable asset per agent, so changing scope changes initial wealth.
Start with one asset and a small population. Idle counterparties do not trade;
use the scripted fixture initially to supply known orders while checking behaviour.

## Development sequence

1. Unit-test decision rules using `Context` with a small fabricated state and seeded
   `Random`; verify empty books, exhausted cash/inventory, rejections and cancellations.
2. Test against a deterministic scripted counterparty using a standalone manifest:
   `python -m stonks_sim.worker --manifest your-run.json --output result.json`.
3. Run the integration suite with a disposable research PostgreSQL URL and built
   exchange checkout: `python -m unittest discover -s tests -v`. Tests explicitly
   skip database cases when those settings are absent.
4. Repeat a manifest/seed and compare `economicHash`, then inspect fills and decisions.
5. Add noise/liquidity traders, then value/informed traders, and vary one parameter
   across several seeds. Check spread, empty-book fraction and volume before P&L.

A suggested first substantive strategy is a simple inventory-aware market maker:
learn quote placement, cancellation and inventory control before optimizing profit.
The financial rules and implementations are intentionally left for you.

Reproducibility requires fixed code/runtime/parameters and no external I/O, wall-time
decisions or unseeded randomness. Cross-version hashes are not promised. Current
P&L uses last-trade/initial-price marks; fees are zero. Test performance across
held-out scenarios before treating a simulated result as evidence of an advantage.
