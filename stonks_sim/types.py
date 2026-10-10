"""Public strategy contracts. TypedDicts preserve the existing JSON/dictionary API.

Decimal strings are exact exchange values, not floats. Asset labels identify run
instruments; UUIDs identify exchange records. Aliases document that distinction.
These annotations provide editor/static checks, not runtime validation.
"""
from typing import Any, Literal, Mapping, NotRequired, Sequence, TypeAlias, TypedDict

AssetLabel: TypeAlias = str
AssetId: TypeAlias = str
OrderId: TypeAlias = str
DecimalString: TypeAlias = str
Side: TypeAlias = Literal['BUY', 'SELL']
OrderType: TypeAlias = Literal['LIMIT', 'MARKET']
OrderStatus: TypeAlias = Literal['OPEN', 'PARTIALLY_FILLED', 'FILLED', 'CANCELLED']
StrategyParameters: TypeAlias = dict[str, Any]

class Asset(TypedDict):
    """Public static instrument metadata. initial_price is NOT a current valuation."""
    id: AssetLabel
    exchange_id: AssetId
    name: str
    sector: str
    subsector: str
    initial_price: DecimalString

class BookLevel(TypedDict):
    price: DecimalString
    quantity: DecimalString

class OrderBook(TypedDict):
    """Aggregated price levels, best first. Both lists may be empty."""
    buys: list[BookLevel]
    sells: list[BookLevel]

class Wallet(TypedDict):
    balance: DecimalString
    frozen_balance: DecimalString

class Position(TypedDict):
    assetId: AssetId
    name: str
    availableQuantity: DecimalString
    reservedQuantity: DecimalString
    quantity: DecimalString
    averageBuyPrice: DecimalString
    realizedPnl: DecimalString
    currentPrice: DecimalString
    currentValue: DecimalString
    profitLoss: DecimalString

class Account(TypedDict):
    wallet: Wallet
    positions: list[Position]

class Order(TypedDict):
    id: OrderId
    user_id: str
    asset_id: AssetId
    side: Side
    type: OrderType
    status: OrderStatus
    price: DecimalString
    initial_quantity: DecimalString
    remaining_quantity: DecimalString
    reserved_cash: DecimalString
    reserved_quantity: DecimalString
    sequence: str
    created_at: str
    updated_at: str

class MarketState(TypedDict):
    account: Account
    orders: list[Order]
    books: dict[AssetLabel, OrderBook]

class Fill(TypedDict):
    sequence: str
    id: str
    asset_id: AssetId
    price: DecimalString
    quantity: DecimalString
    timestamp: str
    side: Side
    order_id: OrderId

class NewsObservation(TypedDict):
    type: Literal['news']
    assetId: AssetLabel
    headline: str
    signal: float
    publishedAt: int
    observedAt: int

class ValuationObservation(TypedDict):
    type: Literal['valuation']
    assetId: AssetLabel
    estimate: float
    publishedAt: int
    observedAt: int

Observation: TypeAlias = NewsObservation | ValuationObservation

class PlaceAction(TypedDict):
    op: Literal['place']
    asset: AssetLabel
    side: Side
    type: OrderType
    price: DecimalString
    quantity: DecimalString

class CancelAction(TypedDict):
    op: Literal['cancel']
    orderId: OrderId

class ScheduleAction(TypedDict):
    op: Literal['schedule']
    atMs: int

Action: TypeAlias = PlaceAction | CancelAction | ScheduleAction

class OrderAccepted(TypedDict):
    """Successful place/cancel command. Cancel responses omit message/fill count."""
    orderId: OrderId
    status: OrderStatus
    remainingQuantity: DecimalString
    filledQuantity: NotRequired[DecimalString]
    message: NotRequired[str]

class OrderRejected(TypedDict):
    rejected: Literal[True]
    message: str

OrderUpdate: TypeAlias = OrderAccepted | OrderRejected


def public_assets(assets: Sequence[Mapping[str, Any]], identities: Mapping[str, str]) -> dict[AssetLabel, Asset]:
    """Project only public fields; never pass the full world manifest to a strategy."""
    return {a['id']: Asset(id=a['id'], exchange_id=identities[a['id']], name=a['name'],
                          sector=a['sector'], subsector=a['subsector'], initial_price=a['price'])
            for a in assets}
