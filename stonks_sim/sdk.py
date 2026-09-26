"""Owner-written algorithms implement Strategy; these fixtures are not market models."""
from dataclasses import dataclass
from random import Random
from typing import Any
import importlib
import json
import os

@dataclass(frozen=True)
class Context:
    now_ms: int
    state: dict[str, Any]
    rng: Random

class Strategy:
    def __init__(self, parameters):
        self.parameters = parameters
    def on_wakeup(self, context): return []
    def on_observation(self, observation, context): return []
    def on_fill(self, fill, context): return []
    def on_order_update(self, update, context): return []

class Idle(Strategy):
    """Infrastructure fixture: never places an order."""

class Scripted(Strategy):
    """Infrastructure fixture: emits explicit prescribed orders once, for tests."""
    def __init__(self, parameters):
        super().__init__(parameters)
        self.orders = list(enumerate(parameters.get('orders', [])))
        self.sent = set()
    def on_wakeup(self, context):
        actions = []
        for i, order in self.orders:
            if i not in self.sent and order['atMs'] <= context.now_ms:
                self.sent.add(i)
                actions.append({'op': 'place', 'type': 'LIMIT', **{k:v for k,v in order.items() if k != 'atMs'}})
        return actions

def registry():
    """Operator-installed only. Never load module names supplied in user manifests."""
    classes = {'idle': Idle, 'scripted': Scripted}
    for name, qualified in json.loads(os.environ.get('STONKS_STRATEGY_REGISTRY', '{}')).items():
        if name in classes: raise ValueError('Cannot replace infrastructure fixtures')
        module, cls = qualified.split(':', 1)
        implementation = getattr(importlib.import_module(module), cls)
        if not issubclass(implementation, Strategy): raise ValueError('Strategy must implement SDK')
        classes[name] = implementation
    return classes
