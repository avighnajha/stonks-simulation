import unittest
from stonks_sim.runtime import Scheduler, stream, permitted_news
from stonks_sim.sdk import Scripted, Context

class RuntimeTests(unittest.TestCase):
    def test_stable_order_and_no_backwards_time(self):
        s=Scheduler();s.add(20,'b',{});s.add(10,'a',{});s.add(20,'c',{})
        self.assertEqual([s.pop()[1] for _ in range(3)],['a','b','c'])
        with self.assertRaises(ValueError):s.add(5,'late',{})
    def test_streams_are_independent(self):
        a=stream(42,'world');b=stream(42,'agent:a');x=a.random();b.random()
        self.assertEqual(x,stream(42,'world').random())
    def test_observation_does_not_expose_truth(self):
        event={'assetId':'a','headline':'news','signal':.3,'shock':.9,'secret':123}
        o=permitted_news(event,10,30,0,stream(1,'a'))
        self.assertNotIn('shock',o);self.assertNotIn('secret',o)
        self.assertEqual(o['observedAt'],30)
    def test_fixture_emits_only_scheduled_actions(self):
        bot=Scripted({'orders':[{'atMs':100,'asset':'a','side':'BUY','price':'10.00','quantity':'1.0000'}]})
        self.assertEqual(bot.on_wakeup(Context(0,{},stream(1,'a'))),[])
        self.assertEqual(len(bot.on_wakeup(Context(100,{},stream(1,'a')))),1)
        self.assertEqual(bot.on_wakeup(Context(100,{},stream(1,'a'))),[])

if __name__=='__main__':unittest.main()
