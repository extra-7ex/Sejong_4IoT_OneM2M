"""Local-only MEC discovery -> test tinyIoT mock CIN. Not real Vision or Pi."""
import json, time, urllib.request, urllib.error, uuid
MEC='http://127.0.0.1:18080/safezone-a/mep-a/mec_service_mgmt/v1'
CSE='http://127.0.0.1:13000/TinyIoT'
APP='safezone-vision-test'
def request(url, method='GET', body=None, ty=None, onem2m=False):
    headers={'Accept':'application/json'}
    if onem2m: headers.update({'X-M2M-Origin':'CAdmin','X-M2M-RI':uuid.uuid4().hex,'X-M2M-RVI':'3'})
    if body is not None: headers['Content-Type']='application/json'+(f';ty={ty}' if ty else '')
    req=urllib.request.Request(url,method=method,headers=headers,data=None if body is None else json.dumps(body).encode())
    try:
        with urllib.request.urlopen(req,timeout=5) as res:
            raw=res.read(); return res.status, dict(res.headers), json.loads(raw) if raw else None
    except urllib.error.HTTPError as e: raise RuntimeError(f'{method} {url}: HTTP {e.code}: {e.read().decode()}') from e

def main():
    uid=uuid.uuid4().hex[:8]; ae='AE-VisionProbe-'+uid; path=f'{CSE}/{ae}/fusedTracks'; sid=None
    try:
        for label,url,body,ty in [('AE',CSE,{'m2m:ae':{'rn':ae,'api':'Nvisionprobe','rr':True,'srv':['3']}},2),('CNT',f'{CSE}/{ae}',{'m2m:cnt':{'rn':'fusedTracks','mni':10}},3),('CIN',path,{'m2m:cin':{'con':json.dumps({'ts':time.time(),'frame':1,'cam_ok':True,'tracks':[]})}},4)]:
            code,h,obj=request(url,'POST',body,ty,True); print(label,code,'rsc',h.get('X-M2M-RSC'))
        target=path+'/la'; name='safezone-fused-probe-'+uid
        body={'serName':name,'version':'1.0','state':'ACTIVE','serializer':'JSON','transportInfo':{'id':'cse-http','name':'http','type':'REST_HTTP','protocol':'HTTP','version':'1.1','endpoint':{'uris':[target]}}}
        code,h,obj=request(f'{MEC}/applications/{APP}/services','POST',body); sid=obj['serInstanceId']; print('MEC REGISTER',code)
        code,h,entries=request(f'{MEC}/services?ser_name={name}'); print('MEC DISCOVERY',code,'count',len(entries))
        assert len(entries)==1 and entries[0]['state']=='ACTIVE'
        endpoint=entries[0]['transportInfo']['endpoint']['uris'][0]; assert endpoint==target
        code,h,cin=request(endpoint,onem2m=True); print('CIN GET',code,'rsc',h.get('X-M2M-RSC'))
        value=cin['m2m:cin']['con']; parsed=json.loads(value) if isinstance(value,str) else value
        assert parsed['cam_ok'] is True and parsed['tracks']==[] and parsed['frame']==1
        print('CON PARSE PASS',json.dumps(parsed,ensure_ascii=False))
    finally:
        if sid:
            try: print('MEC CLEANUP',request(f'{MEC}/applications/{APP}/services/{sid}','DELETE')[0])
            except Exception as e: print('MEC CLEANUP FAILED',e)
        # Test CSE and its SQLite DB are isolated; retain AE/CIN as inspectable evidence.
if __name__=='__main__': main()
