"""Opt-in real PostgreSQL + Node bridge integration; creates and drops own databases."""
import copy,json,os,unittest,uuid
from pathlib import Path
from stonks_sim.worker import execute
from stonks_sim.bridge import Bridge,provision
from stonks_sim.sdk import Strategy
from unittest.mock import patch

@unittest.skipUnless(os.environ.get('RESEARCH_DATABASE_ADMIN_URL') and os.environ.get('STONKS_EXCHANGE_DIR'),'Isolated research PostgreSQL and built exchange required')
class ExchangeTests(unittest.TestCase):
    def test_runner_enforces_information_scope_and_delivery_time(self):
        seen=[]
        class Spy(Strategy):
            def on_observation(self, observation, context):
                seen.append((observation,context.now_ms));return []
        m=json.loads((Path(__file__).parent.parent/'examples'/'smoke.json').read_text())
        m['groups']=[{**m['groups'][0],'id':'observer','strategy':'idle','information':'none','delayMs':300}]
        with patch('stonks_sim.simulation.registry',return_value={'idle':Spy}):
            execute(m,str(uuid.uuid4()));self.assertEqual(seen,[])
            m['groups'][0]['information']='public';execute(m,str(uuid.uuid4()))
        self.assertEqual(len(seen),1)
        observation,tick=seen[0]
        self.assertEqual(tick,1000) # shock 500 + release 200 + delivery 300
        self.assertNotIn('shock',observation)
        self.assertEqual(observation['observedAt'],tick)

    def test_repeatable_real_settlement_and_observations(self):
        m=json.loads((Path(__file__).parent.parent/'examples'/'smoke.json').read_text())
        first=execute(m,str(uuid.uuid4()));second=execute(m,str(uuid.uuid4()))
        self.assertEqual(first['economicHash'],second['economicHash'])
        self.assertEqual(len(first['report']['trades']),1)
        self.assertEqual(first['report']['trades'][0]['price'],'99.00')
        self.assertEqual(first['report']['cash'],'2000.000000')
        self.assertTrue(first['report']['trades'][0]['timestamp'].startswith('2000-01-01T00:00:01'))
        changed=copy.deepcopy(m);changed['seed']=43
        third=execute(changed,str(uuid.uuid4()))
        self.assertNotEqual(first['samples'],third['samples'])
    def test_simultaneous_databases_cannot_share_books(self):
        names=['stonks_run_'+uuid.uuid4().hex for _ in range(2)];bridges=[];created=[]
        try:
            for name in names:
                url=provision('create',name)['url'];created.append(name);bridges.append(Bridge(url))
            m=json.loads((Path(__file__).parent.parent/'examples'/'smoke.json').read_text())
            for b in bridges:b.request('init',0,manifest=m)
            bridges[0].request('place',0,agent='seller:0',asset='a',side='SELL',type='LIMIT',price='99.00',quantity='1.0000',key='ask')
            empty=bridges[1].request('state',0,agent='buyer:0')
            self.assertEqual(empty['books']['a']['sells'],[])
        finally:
            for b in bridges:b.close()
            for name in created:provision('drop',name)
