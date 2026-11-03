"""Owner-written algorithms implement Strategy; these fixtures are not market models."""
from dataclasses import dataclass, field
from random import Random
from typing import cast
import importlib
import json
import os
from .types import (
    Action as Action, Asset as Asset, AssetId as AssetId, AssetLabel as AssetLabel,
    OrderId as OrderId, DecimalString as DecimalString, Side as Side,
    OrderType as OrderType, OrderStatus as OrderStatus,
    StrategyParameters as StrategyParameters, BookLevel as BookLevel,
    OrderBook as OrderBook, Wallet as Wallet, Position as Position,
    Account as Account, Order as Order, MarketState as MarketState, Fill as Fill,
    NewsObservation as NewsObservation, ValuationObservation as ValuationObservation,
    Observation as Observation, PlaceAction as PlaceAction, CancelAction as CancelAction,
    ScheduleAction as ScheduleAction, OrderAccepted as OrderAccepted,
    OrderRejected as OrderRejected, OrderUpdate as OrderUpdate,
)

@dataclass(frozen=True)
class Context:
    now_ms: int
    state: MarketState
    rng: Random
    asset_ids: dict[AssetLabel, AssetId] = field(default_factory=dict)
    assets: dict[AssetLabel, Asset] = field(default_factory=dict)
    tradable_assets: dict[AssetLabel, Asset] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Legacy manually constructed contexts default to their visible universe.
        if not self.tradable_assets:
            object.__setattr__(self, 'tradable_assets', {
                label: dict(asset) for label, asset in self.assets.items()
            })

class Strategy:
    def __init__(self, parameters: StrategyParameters) -> None:
        self.parameters = parameters
    def on_wakeup(self, context: Context) -> list[Action]: return []
    def on_observation(self, observation: Observation, context: Context) -> list[Action]: return []
    def on_fill(self, fill: Fill, context: Context) -> list[Action]: return []
    def on_order_update(self, update: OrderUpdate, context: Context) -> list[Action]: return []

class Idle(Strategy):
    """Infrastructure fixture: never places an order."""

class Scripted(Strategy):
    """Infrastructure fixture: emits explicit prescribed orders once, for tests."""
    def __init__(self, parameters: StrategyParameters) -> None:
        super().__init__(parameters)
        self.orders = list(enumerate(parameters.get('orders', [])))
        self.sent: set[int] = set()
    def on_wakeup(self, context: Context) -> list[Action]:
        actions: list[Action] = []
        for i, order in self.orders:
            if i not in self.sent and order['atMs'] <= context.now_ms:
                self.sent.add(i)
                actions.append(cast(PlaceAction, {'op': 'place', 'type': 'LIMIT', **{k:v for k,v in order.items() if k != 'atMs'}}))
        return actions

def registry() -> dict[str, type[Strategy]]:
    """Operator-installed only. Never load module names supplied in user manifests."""
    classes: dict[str, type[Strategy]] = {'idle': Idle, 'scripted': Scripted}
    for name, qualified in json.loads(os.environ.get('STONKS_STRATEGY_REGISTRY') or '{}').items():
        if name in classes: raise ValueError('Cannot replace infrastructure fixtures')
        module, cls = qualified.split(':', 1)
        implementation = getattr(importlib.import_module(module), cls)
        if not issubclass(implementation, Strategy): raise ValueError('Strategy must implement SDK')
        classes[name] = implementation
    return classes
