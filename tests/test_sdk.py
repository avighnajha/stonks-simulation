import unittest
from random import Random
from typing import get_type_hints
from stonks_sim.sdk import Context, Strategy, Action, Observation, Fill, OrderUpdate
from stonks_sim.types import public_assets

class SdkTests(unittest.TestCase):
    def test_old_context_constructor_and_callbacks_stay_compatible(self):
        context = Context(0, {}, Random(42))
        self.assertEqual(context.asset_ids, {})
        self.assertEqual(context.assets, {})
        self.assertEqual(Strategy({}).on_wakeup(context), [])

    def test_asset_metadata_is_allowlisted_and_detached(self):
        original = {'id':'a','name':'Footballer','sector':'Sports','subsector':'Football',
                    'price':'100.00','marketWeight':0.2,'reference':123,'secret':'hidden'}
        assets = public_assets([original], {'a':'asset-uuid'})
        self.assertEqual(assets['a'], {'id':'a','exchange_id':'asset-uuid','name':'Footballer',
                         'sector':'Sports','subsector':'Football','initial_price':'100.00'})
        assets['a']['name'] = 'Changed locally'
        self.assertEqual(original['name'], 'Footballer')
        self.assertEqual(public_assets([original], {'a':'asset-uuid'})['a']['name'], 'Footballer')

    def test_callback_signatures_expose_types(self):
        self.assertEqual(get_type_hints(Strategy.on_wakeup)['context'], Context)
        self.assertEqual(get_type_hints(Strategy.on_wakeup)['return'], list[Action])
        self.assertEqual(get_type_hints(Strategy.on_observation)['observation'], Observation)
        self.assertEqual(get_type_hints(Strategy.on_fill)['fill'], Fill)
        self.assertEqual(get_type_hints(Strategy.on_order_update)['update'], OrderUpdate)
