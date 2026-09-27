"""Single logical clock. No wall sleeps, network observations or shared-market state."""
import hashlib
import json
import math
import time
from decimal import Decimal
from .runtime import Scheduler,stream,permitted_news
from .sdk import Context,registry
from . import __version__

class Cancelled(Exception): pass

def run(manifest, bridge, progress=lambda _:None, cancelled=lambda:False):
    m=manifest;seed=m['seed'];end=m['durationMs'];scheduler=Scheduler();agents={};classes=registry()
    identities=bridge.request('init',0,manifest=m)
    assets={a['id']:a for a in m['assets']};values={a['id']:math.log(float(a['price'])) for a in m['assets']}
    rngs={};samples=[];decisions=[];count=0;commands=0;started=time.monotonic()
    def rng(key):
        if key not in rngs:rngs[key]=stream(seed,key)
        return rngs[key]
    for g in m['groups']:
        if g['strategy'] not in classes:raise ValueError('Strategy not installed: '+g['strategy'])
        for i in range(g['count']):
            label=f"{g['id']}:{i}";agents[label]={'bot':classes[g['strategy']](g['parameters']),'group':g,'rng':stream(seed,'agent:'+label),'fills':'0'}
    # Initial insertion order is part of protocol v1. Later ties use insertion sequence.
    scheduler.add(0,'world',{})
    for i,e in enumerate(m['events']):scheduler.add(e['atMs'],'shock',{'event':e,'index':i})
    for label in sorted(agents):scheduler.add(0,'wake',{'agent':label})
    sample_step=max(m['stepMs'],math.ceil(end/500))
    scheduler.add(0,'sample',{})
    def context(label,tick):return Context(tick,bridge.request('state',tick,agent=label),agents[label]['rng'])
    def actions(label,tick,items):
        nonlocal commands
        if not isinstance(items,list) or len(items)>20:raise ValueError('Strategy must return at most 20 actions per callback')
        for item in items:
            if not isinstance(item,dict):raise ValueError('Invalid strategy action')
            action=dict(item);op=action.pop('op',None)
            if op=='schedule':
                at=action.get('atMs')
                if not isinstance(at,int) or at<=tick:raise ValueError('Wakeup must be in the future')
                if at<=end:scheduler.add(at,'wake_once',{'agent':label})
                continue
            if op not in ('place','cancel'):raise ValueError('Unknown action')
            allowed={'asset','side','type','price','quantity'} if op=='place' else {'orderId'}
            if set(action)-allowed:raise ValueError('Invalid action fields')
            commands+=1
            if commands>5000:raise ValueError('5,000-command run budget exceeded')
            key=f'cmd:{commands}'
            try:result=bridge.request(op,tick,agent=label,key=key,**action)
            except ValueError as error:result={'rejected':True,'message':str(error)}
            decisions.append({'tick':tick,'agent':label,'action':{'op':op,**action},'result':result})
            scheduler.add(tick,'ack',{'agent':label,'result':result})
    while scheduler:
        tick,kind,p=scheduler.pop()
        if tick>end:break
        count+=1
        if count>100000 or time.monotonic()-started>600:raise ValueError('Run compute budget exceeded')
        if cancelled():raise Cancelled('Cancelled by owner')
        if kind=='world':
            dt=m['stepMs']/3600000 # factor amplitudes per square-root simulated hour
            common=rng('world:market').gauss(0,1)
            # Draw each shared factor once, independent of how many assets use it.
            sectors={s:rng('sector-factor:'+s).gauss(0,1) for s in sorted({a['sector'] for a in assets.values()})}
            subs={s:rng('subsector-factor:'+s).gauss(0,1) for s in sorted({a['sector']+'/'+a['subsector'] for a in assets.values()})}
            for a in assets.values():
                if tick:values[a['id']]+=math.sqrt(dt)*(a['marketWeight']*common+a['sectorWeight']*sectors[a['sector']]+a['subsectorWeight']*subs[a['sector']+'/'+a['subsector']]+a['idiosyncraticWeight']*rng('asset:'+a['id']).gauss(0,1))
                if not math.isfinite(values[a['id']]) or not -10<values[a['id']]<25:raise ValueError('Reference value outside model range')
                for label,agent in agents.items():
                    if agent['group'].get('information','public') not in ('valuation','both'):continue
                    at=tick+agent['group']['delayMs']
                    if at<=end:
                        observed=math.exp(values[a['id']]+rng('valuation:'+label+':'+a['id']).gauss(0,agent['group']['signalNoise']))
                        scheduler.add(at,'observation',{'agent':label,'observation':{'type':'valuation','assetId':a['id'],'publishedAt':tick,'observedAt':at,'estimate':observed}})
            if tick+m['stepMs']<=end:scheduler.add(tick+m['stepMs'],'world',{})
        elif kind=='shock':
            e=p['event'];values[e['assetId']]+=math.log1p(e['shock']);scheduler.add(tick+e['releaseDelayMs'],'release',p)
        elif kind=='release':
            e=p['event'];bridge.request('news',tick,asset=e['assetId'],headline=e['headline'],signal=e['signal'],key='news:'+str(p['index']))
            for label,a in agents.items():
                if a['group'].get('information','public') not in ('public','both'):continue
                at=tick+a['group']['delayMs']
                if at<=end:scheduler.add(at,'observation',{'agent':label,'observation':permitted_news(e,tick,at,a['group']['signalNoise'],rng('news:'+label))})
        elif kind in ('wake','wake_once'):
            label=p['agent'];a=agents[label];ctx=context(label,tick)
            # Only explicit observation messages contain news; state has own account and books.
            fills=bridge.request('fills',tick,agent=label,after=a['fills'])
            for fill in fills:
                a['fills']=fill['sequence'];actions(label,tick,a['bot'].on_fill(fill,ctx))
            actions(label,tick,a['bot'].on_wakeup(ctx))
            if kind=='wake' and tick+a['group']['wakeMs']<=end:scheduler.add(tick+a['group']['wakeMs'],'wake',p)
        elif kind=='observation':
            label=p['agent'];actions(label,tick,agents[label]['bot'].on_observation(p['observation'],context(label,tick)))
        elif kind=='ack':
            label=p['agent'];actions(label,tick,agents[label]['bot'].on_order_update(p['result'],context(label,tick)))
        elif kind=='sample':
            # Sampling happens after the earlier events at this timestamp; this convention is pinned.
            state=bridge.request('state',tick,agent=next(iter(agents)));rows={}
            for label,b in state['books'].items():
                bid=float(b['buys'][0]['price']) if b['buys'] else None;ask=float(b['sells'][0]['price']) if b['sells'] else None
                rows[label]={'bid':bid,'ask':ask,'mid':(bid+ask)/2 if bid is not None and ask is not None else None,'spread':ask-bid if bid is not None and ask is not None else None,'reference':math.exp(values[label]),'bidDepth':sum(float(x['quantity']) for x in b['buys']),'askDepth':sum(float(x['quantity']) for x in b['sells'])}
            samples.append({'tick':tick,'assets':rows})
            if tick+sample_step<=end:scheduler.add(tick+sample_step,'sample',{})
        if count%20==0:progress({'tick':tick,'durationMs':end,'processedEvents':count,'commands':commands,'latest':samples[-1] if samples else None})
    report=bridge.request('report',end)
    expected_cash=sum(Decimal(g['cash'])*g['count'] for g in m['groups'])
    if Decimal(report['cash'])!=expected_cash or any(Decimal(s['expected'])!=Decimal(s['actual']) for s in report['supplies']):raise RuntimeError('Conservation invariant failed')
    metrics={}
    for label in assets:
        observations=[s['assets'][label] for s in samples];quoted=[o for o in observations if o['mid'] is not None]
        metrics[label]={'meanSpread':sum(o['spread'] for o in quoted)/len(quoted) if quoted else None,'emptyBookFraction':1-len(quoted)/len(observations) if observations else None,'referenceRmse':math.sqrt(sum((o['mid']-o['reference'])**2 for o in quoted)/len(quoted)) if quoted else None}
    cohort={}
    for g in m['groups']:
        initial=float(g['cash'])+sum(float(g['inventory'])*float(a['price']) for a in m['assets']);wealth=[]
        for i in range(g['count']):
            a=report['accounts'][f"{g['id']}:{i}"];wealth.append(float(a['wallet']['balance'])+float(a['wallet']['frozen_balance'])+sum(float(p['currentValue']) for p in a['positions']))
        cohort[g['id']]={'initialWealth':initial*g['count'],'finalWealth':sum(wealth),'pnl':sum(wealth)-initial*g['count']}
    result={'protocol':1,'runnerVersion':__version__,'manifest':m,'identities':identities,'metrics':metrics,'cohorts':cohort,'samples':samples,'decisions':decisions,'report':report,'processedEvents':count}
    result['economicHash']=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return result
