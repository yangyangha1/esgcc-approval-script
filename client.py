#!/usr/bin/env python3
"""Browser-free login and read-only keepalive prototype. No approval submission."""
import argparse, datetime, getpass, hashlib, http.cookiejar, json, os, re, secrets, stat, subprocess, time, urllib.parse, urllib.request
from pathlib import Path
from probe import aes_point, BASE, STATIC
ROOT=Path(__file__).resolve().parent
PRIVATE=ROOT/'private'
CANONICAL='/creEnquiryWorkflow/list/1'
class SameSiteRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        u=urllib.parse.urlparse(newurl)
        if u.scheme!='https' or u.hostname!='j.esgcc.com.cn':
            raise ValueError('unexpected redirect')
        return super().redirect_request(req,fp,code,msg,headers,newurl)
class NoWorkflowRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise urllib.error.HTTPError(req.full_url,code,'workflow redirect refused',headers,fp)
class Client:
    def __init__(self):
        PRIVATE.mkdir(mode=0o700,exist_ok=True);os.chmod(PRIVATE,0o700)
        self.jar=http.cookiejar.LWPCookieJar(str(PRIVATE/'session.cookies'))
        if Path(self.jar.filename).exists():
            if stat.S_IMODE(os.stat(self.jar.filename).st_mode)!=0o600: raise ValueError('unsafe session permissions')
            self.jar.load(ignore_discard=True)
        self.op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar),SameSiteRedirect())
    def request(self,path,data=None,json_body=False):
        if not path.startswith('/') or path.startswith('//'): raise ValueError('invalid route')
        headers={'User-Agent':'Mozilla/5.0','Referer':BASE+'/login'}
        if path.startswith(('/creEnquiryWorkflow/beanValidatorForToken','/creEnquiryWorkflow/validateEnquiryWorkflow','/creEnquiryWorkflow/save','/creEnquiryWorkflow/findGoodsList')):
            headers['X-Requested-With']='XMLHttpRequest'
        if data is not None:
            headers['Content-Type']='application/json' if json_body else 'application/x-www-form-urlencoded; charset=UTF-8'
            data=(json.dumps(data) if json_body else urllib.parse.urlencode(data)).encode()
        if 'getRandomValidateCodeBase64' in path: headers['orgCode']='platform'
        op=self.op
        if path.startswith(('/creEnquiryWorkflow/beanValidatorForToken','/creEnquiryWorkflow/validateEnquiryWorkflow','/creEnquiryWorkflow/save')):
            op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar),NoWorkflowRedirect())
        with op.open(urllib.request.Request(BASE+path,data=data,headers=headers),timeout=20) as r:
            text=r.read(3_000_001).decode('utf-8')
            if len(text)>3_000_000: raise ValueError('oversized response')
            return r.geturl(),text
    def save(self):
        # Operational credential store, not an analysis cache.
        os.umask(0o077)
        self.jar.save(ignore_discard=True);os.chmod(self.jar.filename,0o600)
    def check(self):
        url,text=self.request(CANONICAL)
        if '/login' in urllib.parse.urlparse(url).path or re.search(r'<input[^>]+type=[\"\']password',text,re.I): return 'LOGIN_REQUIRED'
        if 'disable-devtool' in url: return 'UNKNOWN'
        # Require actual approval list structure and logged-in navigation.
        if '竞价单审批' in text and ('退出' in text or 'indexView' in text) and ('<table' in text or 'listTable' in text):
            self.save(); return 'LOGIN_OK'
        return 'UNKNOWN'
    def challenge(self):
        randomcode=str(secrets.randbelow(900000)+100000)
        _,raw=self.request('/member/necp/mapp/umc/necp/login/getRandomValidateCodeBase64?p0='+randomcode+'&p1=4&p2=2')
        answer=json.loads(raw);d=answer.get('data') or {}
        if answer.get('code')!='0000' or not d.get('token'): raise ValueError('challenge unavailable')
        payload={'captchaType':d.get('captchaType') or 'blockPuzzle','pointJson':aes_point(d['secretKey'],None) if d.get('secretKey') else '{"x":null,"y":5}', 'token':d['token'],'randomCode':randomcode}
        _,raw=self.request('/member/necp/mapp/umc/necp/login/checkCaptchaCode',payload,True)
        reply=json.loads(raw);reply=reply.get('data') if isinstance(reply.get('data'),dict) and 'code' in reply['data'] else reply
        if str(reply.get('code')) not in ('0000','200','6100000'): raise ValueError('challenge rejected')
        return d['token']
    def login(self):
        state = self.check()
        if state == 'LOGIN_OK':
            print('Existing session valid; SMS skipped.',flush=True)
            return True
        if state != 'LOGIN_REQUIRED':
            raise ValueError('ambiguous session; do not send SMS')
        path=PRIVATE/'credentials.json'
        if stat.S_IMODE(path.stat().st_mode)!=0o600: raise ValueError('unsafe credential permissions')
        account=json.loads(path.read_text())
        self.request('/login')
        with urllib.request.urlopen(STATIC+'res_v4.0/js/login/login20240808.js',timeout=20) as r: js=r.read().decode()
        key=re.search(r'var flag\s*=\s*"([0-9a-fA-F]+)"',js)
        if not key: raise ValueError('public key unavailable')
        password=subprocess.run(['node',str(ROOT/'crypto.cjs')],input=json.dumps({'password':account['password'],'publicKey':key[1]}),capture_output=True,text=True,check=True).stdout
        payload={'username':account['username'],'privateCode':password}
        _,raw=self.request('/forget/getMobileCodeByLogin',{**payload,'dingxiangCaptcha':''})
        response=json.loads(raw)
        if str(response.get('code'))!='1':
            message=str(response.get('resultMessage') or response.get('message') or '')
            message=message.replace(account['username'],'[account]')
            message=re.sub(r'[0-9]{5,}', '[redacted]', message)
            print(json.dumps({'sms_send':'failed','code':str(response.get('code','')),'fields':list(response),'reason':message},ensure_ascii=False),flush=True);return False
        print('SMS_SENT: enter the new code at the hidden prompt; never logged.',flush=True)
        otp=getpass.getpass('SMS code: ')
        token=self.challenge()
        _,raw=self.request('/loginCheck',{**payload,'captcha':token,'constID':'','smsCaptcha':otp})
        otp='';response=json.loads(raw)
        if response.get('success') is not True:
            print(json.dumps({'login':'failed','code':str(response.get('code',''))}),flush=True);return False
        status = self.check()
        print('Login response accepted; canonical check: '+status,flush=True)
        return status == 'LOGIN_OK'

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['login','check','keepalive']);p.add_argument('--interval',type=int,default=300);p.add_argument('--rounds',type=int,default=1);a=p.parse_args()
    if a.interval<60 or a.rounds<1: p.error('interval >=60, rounds >=1 required')
    c=Client()
    if a.action=='login':return 0 if c.login() else 1
    for i in range(a.rounds if a.action=='keepalive' else 1):
        status=c.check();print(json.dumps({'time':datetime.datetime.now().astimezone().isoformat(),'status':status}),flush=True)
        if status!='LOGIN_OK':return 1
        if i+1<a.rounds and a.action=='keepalive':time.sleep(a.interval)
    return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as e:
        print(json.dumps({'status':'STOPPED','error_type':type(e).__name__}),flush=True)
        raise SystemExit(1)
