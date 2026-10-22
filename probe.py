#!/usr/bin/env python3
"""Bounded browser-free diagnostic. No credentials, SMS, or approval writes."""
import argparse, base64, datetime, hashlib, http.cookiejar, json, re, secrets, subprocess, time, urllib.request
from pathlib import Path
BASE = 'https://j.esgcc.com.cn'
STATIC = 'https://static.esgcc.com.cn/static/jtqy/front/'

def aes_point(key, x=0):
    # Secret material is passed through stdin, never process arguments or files.
    js = "const c=require('node:crypto');let s='';process.stdin.on('data',d=>s+=d);process.stdin.on('end',()=>{const k=Buffer.from(JSON.parse(s).key);const e=c.createCipheriv('aes-'+k.length*8+'-ecb',k,null);process.stdout.write(Buffer.concat([e.update(JSON.stringify({x:JSON.parse(s).x,y:5})),e.final()]).toString('base64'));});"
    return subprocess.run(['node','-e',js],input=json.dumps({'key':key,'x':x}),text=True,capture_output=True,check=True).stdout

def run(check=False, no_move=False):
    started=time.monotonic()
    op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    sources=[]
    def get(path, data=None, headers=None):
        url=path if path.startswith('https://') else BASE+path
        req=urllib.request.Request(url,data=data,headers={'User-Agent':'Mozilla/5.0','Referer':BASE+'/login',**(headers or {})})
        with op.open(req,timeout=20) as r:
            raw=r.read(2_000_001)
            if len(raw)>2_000_000: raise ValueError('response too large')
            # No query strings, response bodies, cookies or challenge values persisted.
            sources.append({'source':url.split('?')[0],'status':r.status,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
            return raw.decode('utf-8')
    page=get('/login')
    def field(name):
        tag=re.search(r'<input\b[^>]*\bid=[\"\']'+re.escape(name)+r'[\"\'][^>]*>',page)
        val=re.search(r'\bvalue=[\"\']([^\"\']*)',tag[0]) if tag else None
        return val[1] if val else None
    login=get(STATIC+'res_v4.0/js/login/login20240808.js')
    verify=get(STATIC+'res/captcha/js/yjpl.umc.verify.js')
    result={'checked_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
            'browser_started':False,'sms_required_config':field('doubleConfig'),'verify_type':field('verifyType'),
            'password_pipeline_confirmed':all(x in login for x in ['hex_md5','SG_sm2Encrypt','/loginCheck']),
            'sms_endpoint_confirmed':'/forget/getMobileCodeByLogin' in login,
            'zero_distance_check':'not_requested','login_test':'not_performed','approval_writes':0}
    if check:
        if not all(x in verify for x in ['/getRandomValidateCodeBase64','/checkCaptchaCode','pointJson','randomCode']):
            raise ValueError('challenge protocol changed')
        randomcode=str(secrets.randbelow(900000)+100000)
        response=json.loads(get('/member/necp/mapp/umc/necp/login/getRandomValidateCodeBase64?p0='+randomcode+'&p1=4&p2=2',headers={'orgCode':'platform'}))
        d=response.get('data') or {}
        result['challenge_code']=str(response.get('code',''))
        if str(response.get('code')) not in ('0000','200','6100000') or not d.get('token'):
            result['zero_distance_check']='challenge_unavailable'
        else:
            payload={'captchaType':d.get('captchaType') or 'blockPuzzle','pointJson':aes_point(d['secretKey'], None if no_move else 0) if d.get('secretKey') else json.dumps({'x':None if no_move else 0,'y':5}), 'token':d['token'],'randomCode':randomcode}
            answer=json.loads(get('/member/necp/mapp/umc/necp/login/checkCaptchaCode',json.dumps(payload).encode(),{'Content-Type':'application/json'}))
            answer=answer.get('data') if isinstance(answer.get('data'),dict) and 'code' in answer['data'] else answer
            result['captcha_check_code']=str(answer.get('code',''))
            result['zero_distance_check']='accepted' if str(answer.get('code')) in ('0000','200','6100000') else 'rejected'
    result['gesture']='press_release_without_mousemove' if no_move else 'zero_distance'
    result['sources']=sources
    result['elapsed_seconds']=round(time.monotonic()-started,3)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check-zero-distance',action='store_true',help='one fresh challenge, one zero-distance server check; no retries')
    p.add_argument('--output',type=Path,default=Path(__file__).with_name('probe-result.json'))
    p.add_argument('--no-move',action='store_true',help='reproduce component unset movement value (JSON null)')
    args=p.parse_args()
    try:
        result=run(args.check_zero_distance, args.no_move)
    except Exception as e:
        result={'status':'probe_failed','error_type':type(e).__name__,'login_test':'not_performed','approval_writes':0}
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(1 if result.get('status')=='probe_failed' else 0)
