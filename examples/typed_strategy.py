"""Typed, inactive starting point. The financial decision rules are yours to write."""
from decimal import Decimal
from stonks_sim.sdk import (
    Action, Context, Fill, Observation, OrderUpdate, PlaceAction,
    Strategy, StrategyParameters,
)

class MyStrategy(Strategy):
    def __init__(self, parameters: StrategyParameters) -> None:
        super().__init__(parameters)
        self.estimates: dict[str, float] = {}
        self.available_cash = Decimal('0')
        self.last_fill: Fill | None = None
        self.last_update: OrderUpdate | None = None

    def on_wakeup(self, context: Context) -> list[Action]:
        self.available_cash = Decimal(context.state['account']['wallet']['balance'])
        for label, asset in context.tradable_assets.items():
            book = context.state['books'][label]
            position = next((p for p in context.state['account']['positions']
                             if p['assetId'] == asset['exchange_id']), None)
            # Empty books and missing positions are normal. Choose your own rules.
            if not book['buys'] or not book['sells'] or position is None:
                continue
        return []

    def on_observation(self, observation: Observation, context: Context) -> list[Action]:
        if observation['type'] == 'valuation':
            self.estimates[observation['assetId']] = observation['estimate']
        return []

    def on_fill(self, fill: Fill, context: Context) -> list[Action]:
        self.last_fill = fill
        return []

    def on_order_update(self, update: OrderUpdate, context: Context) -> list[Action]:
        self.last_update = update
        return []


def example_order(label: str) -> PlaceAction:
    """Illustrates the action shape; MyStrategy never submits this order."""
    return {'op':'place', 'asset':label, 'side':'BUY', 'type':'LIMIT',
            'price':'99.50', 'quantity':'1.0000'}
