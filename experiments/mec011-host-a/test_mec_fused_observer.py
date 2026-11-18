"""Experiment: MEC-discovered test CSE endpoint feeds existing observation poller.
Requires an external engine copy containing engine.fused_tracks. No risk decisions.
"""
import json, time, uuid
from engine.fused_tracks import FusedPoller
from test_cse_discovery import APP, CSE, MEC, request
from fused_freshness import assess
from vision4iot.fusion import CamPerson, fuse, message

def main():
    uid=uuid.uuid4().hex[:8]; ae='AE-VisionObserve-'+uid; path=f'{CSE}/{ae}/fusedTracks'; sid=None
    def post(frame):
        now=time.time()
        tracks=fuse([], [CamPerson(3, .2, 2., 'crouching', .9)])
        msg=message(now, frame, True, tracks, radar_ok=False, now=now)
        return request(path,'POST',{'m2m:cin':{'con':json.dumps(msg)}},4,True)
    try:
        request(CSE,'POST',{'m2m:ae':{'rn':ae,'api':'Nvisionobserve','rr':True,'srv':['3']}},2,True,origin='Cobserve'+uid)
        request(f'{CSE}/{ae}','POST',{'m2m:cnt':{'rn':'fusedTracks','mni':10}},3,True)
        post(1)
        target=path+'/la'; name='safezone-vision-observe-'+uid
        body={'serName':name,'version':'1.0','state':'ACTIVE','serializer':'JSON','transportInfo':{'id':'test-http','name':'http','type':'REST_HTTP','protocol':'HTTP','version':'1.1','endpoint':{'uris':[target]}}}
        code,_,created=request(f'{MEC}/applications/{APP}/services','POST',body); sid=created['serInstanceId']
        code,_,entries=request(f'{MEC}/services?ser_name={name}'); assert code==200 and len(entries)==1 and entries[0]['state']=='ACTIVE'
        endpoint=entries[0]['transportInfo']['endpoint']['uris'][0]
        # Never forward credentials to an untrusted/discovered address in this test.
        assert endpoint==target
        class Client:
            def get_latest_fused_cin(self):
                code,_,cin=request(endpoint,onem2m=True); assert code==200
                assert assess(cin,time.time())=='OK'
                payload=json.loads(cin['m2m:cin']['con'])
                assert payload['tracks'][0]['state']=='camera_only'
                assert payload['tracks'][0]['advice']=='raise'
                print('VISION PAYLOAD camera_only / raise; synthetic inputs')
                return cin
        poller=FusedPoller(Client())
        first=poller.poll_once(); print('FIRST',first); assert first=='WAITING_FOR_NEW_CIN'
        post(2)
        second=poller.poll_once(); print('NEXT',second); assert second=='FRESH'
        print('PASS: MEC discovery -> tinyIoT -> synthetic Vision functions -> observation-only FusedPoller')
    finally:
        if sid: print('MEC CLEANUP',request(f'{MEC}/applications/{APP}/services/{sid}','DELETE')[0])

if __name__=='__main__': main()
