import hashlib
import heapq
import random

class Scheduler:
    def __init__(self): self.events=[]; self.sequence=0; self.now=0
    def add(self, at, kind, payload):
        if not isinstance(at,int) or at < self.now: raise ValueError('Backwards or fractional event time')
        self.sequence+=1;heapq.heappush(self.events,(at,self.sequence,kind,payload))
    def pop(self):
        at,_,kind,payload=heapq.heappop(self.events);self.now=at;return at,kind,payload
    def __bool__(self): return bool(self.events)

def stream(seed, identity):
    return random.Random(int.from_bytes(hashlib.sha256(f'{seed}:{identity}'.encode()).digest(),'big'))

def permitted_news(event, published, observed, noise, rng):
    return {'type':'news','assetId':event['assetId'],'headline':event['headline'],
            'publishedAt':published,'observedAt':observed,
            'signal':max(-1,min(1,event['signal']+rng.gauss(0,noise)))}
