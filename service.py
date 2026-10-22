#!/usr/bin/env python3
"""Loopback settings UI, persistent session checks and scheduled dry-run validation."""
import datetime,hashlib,json,os,re,secrets,subprocess,threading,time,urllib.error,http.client
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from zoneinfo import ZoneInfo
from client import Client,ROOT,PRIVATE
import runner
SETTINGS=ROOT/'settings.json';STATE=ROOT/'state.json';TZ=ZoneInfo('Asia/Shanghai');TOKEN=secrets.token_urlsafe(32)
JOB=threading.Lock();STATE_LOCK=threading.RLock()
state={'session':'UNKNOWN','running':False,'scheduled_done':[],'last_result':None,'last_bark':None,'pending_notice':None}
if STATE.exists():
 try:state.update(json.loads(STATE.read_text()));state['running']=False
 except Exception:pass

def now():return datetime.datetime.now(TZ).isoformat()
def atomic(path,value,mode=0o600):
 temp=path.with_name(path.name+'.tmp');fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,mode)
 with os.fdopen(fd,'w') as f:json.dump(value,f,ensure_ascii=False,indent=2)
 os.chmod(temp,mode);os.replace(temp,path)
def update(**fields):
 with STATE_LOCK:state.update(fields);atomic(STATE,state)
def settings():
 d=json.loads(SETTINGS.read_text());validate(d);return d
BOOLS=['validationOnly','approvalEnabled','keepaliveEnabled','barkEnabled','materialBidEnabled','materialConfirmEnabled','serviceBidEnabled','serviceConfirmEnabled','materialProcurementEnabled','serviceProcurementEnabled','notifyApproved','notifyManual','notifyLoginExpired','notifyError','notifyZero']
def validate(d):
 if any(type(d.get(k))!=bool for k in BOOLS):raise ValueError('开关必须为布尔值')
 if type(d.get('processingIntervalSeconds',8))!=int or not 4<=d.get('processingIntervalSeconds',8)<=60:raise ValueError('单据间隔须为 4–60 秒')
 if type(d.get('keepaliveMinutes'))!=int or not 1<=d['keepaliveMinutes']<=60:raise ValueError('保活间隔须为 1–60 分钟')
 if not isinstance(d.get('approvalTimes'),list) or not 1<=len(d['approvalTimes'])<=24 or any(not isinstance(x,str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',x) for x in d['approvalTimes']):raise ValueError('执行时间须为 HH:MM')
 if not isinstance(d.get('approvalWeekdays'),list) or any(type(x)!=int or not 0<=x<=6 for x in d['approvalWeekdays']):raise ValueError('星期须在 0–6 之间')
 if type(d.get('validationOnly'))!=bool:raise ValueError('执行模式无效')
 if d.get('bindHost')!='127.0.0.1' or d.get('bindPort')!=18766:raise ValueError('只允许本机 18766 端口')
 if d.get('barkUrl')!='https://api.day.app/push':raise ValueError('Bark 地址不受支持')

def bark(title,body):
 cfg=settings()
 if not cfg['barkEnabled']:return {'accepted':False,'disabled':True,'at':now()}
 key=json.loads((PRIVATE/'notification.json').read_text()).get('barkKey','')
 if not key:return {'accepted':False,'error':'MISSING_KEY','at':now()}
 payload=json.dumps({'device_key':key,'title':title,'body':body,'group':'电商审批脚本'},ensure_ascii=False).encode()
 try:
  p=subprocess.run(['/usr/bin/curl','--noproxy','*','--silent','--show-error','--max-time','15','--header','Content-Type: application/json; charset=utf-8','--data-binary','@-','https://api.day.app/push'],input=payload,capture_output=True,timeout=20)
  accepted=p.returncode==0 and json.loads(p.stdout).get('code')==200
  return {'accepted':accepted,'at':now(),'error':None if accepted else 'BARK_REJECTED'}
 except Exception:return {'accepted':False,'at':now(),'error':'BARK_TRANSPORT'}
def notify(title,body):
 result=bark(title,body);update(last_bark=result,pending_notice=None if result.get('accepted') or result.get('disabled') else {'title':title,'body':body});return result

def error_info(exc):
 info={'type':type(exc).__name__}
 if isinstance(exc,urllib.error.HTTPError):info['http_status']=exc.code
 elif isinstance(exc,urllib.error.URLError):info['reason_type']=type(exc.reason).__name__
 if isinstance(getattr(exc,'errno',None),int):info['errno']=exc.errno
 return info

def session_probe():
 attempts=[]
 for index in range(3):
  try:
   status=Client().check()
   attempts.append({'at':now(),'status':status})
   return status,attempts
  except Exception as exc:
   attempts.append({'at':now(),'status':'ERROR','error':error_info(exc)})
   retryable=isinstance(exc,(urllib.error.URLError,TimeoutError,ConnectionError,http.client.HTTPException))
   if isinstance(exc,urllib.error.HTTPError):retryable=exc.code in (408,429,500,502,503,504)
   if not retryable or index==2:return 'ERROR',attempts
   time.sleep(2*(index+1))
 return 'ERROR',attempts

def keepalive():
 if not JOB.acquire(False):return
 try:
  previous=state.get('session');status,attempts=session_probe()
  fields={'session':status,'last_keepalive':now(),'keepalive_attempts':attempts}
  if len(attempts)>1 or status!='LOGIN_OK' or previous!='LOGIN_OK':
   event={'at':now(),'previous':previous,'status':status,'attempts':attempts}
   fields['keepalive_history']=(state.get('keepalive_history',[])+[event])[-50:]
  update(**fields)
  try:
   cfg=settings()
   if status=='ERROR' and previous!='ERROR' and cfg['notifyError']:
    notify('电商脚本：保活检查失败',f"本轮 {len(attempts)} 次检查未成功，原因类型：{attempts[-1]['error']['type']}。尚不能判定登录失效；后续周期将重查。")
   elif status=='LOGIN_REQUIRED' and status!=previous and cfg['notifyLoginExpired']:
    notify('电商脚本：登录已失效','网站明确返回登录页，请重新登录；脚本不会自动发送短信。')
   elif status=='UNKNOWN' and status!=previous and cfg['notifyError']:
    notify('电商脚本：页面无法确认','页面结构不符合预期，验证已暂停；尚不能判定登录失效。')
   elif status=='LOGIN_OK' and previous not in ('LOGIN_OK','UNKNOWN'):
    notify('电商脚本：会话恢复','固定审批列表已确认登录有效，恢复按设置执行验证。')
  except Exception as exc:
   update(notification_error=error_info(exc))
 finally:JOB.release()

def validate_run(trigger):
 if not JOB.acquire(False):return False
 try:
  update(running=True,last_trigger=trigger)
  cfg=settings()
  if trigger not in ('schedule','manual_live'):cfg['validationOnly']=True
  result=runner.run(cfg);result['at']=now();result['trigger']=trigger;update(last_result=result,session='LOGIN_OK')
  cfg=settings();should=(result['items']>0 and (cfg['notifyApproved'] or cfg['notifyManual'])) or (result['unresolved'] and cfg['notifyError']) or cfg['notifyZero']
  if should:
   live=result['mode']=='live'
   title='电商脚本：审批结果' if live else '电商脚本：任务验证结果'
   body=(f"已审批 {result['approved']} 项，未审批 {result['manual']} 项。" if live else f"验证 {result['items']} 项；可审批 {result['would_approve']} 项，需人工 {result['manual']} 项。实际审批 0 项。")
   reasons=list(result.get('reasons',{}).items())
   if reasons:body+='\n原因：'+'；'.join(f"{count} 张：{why}" for why,count in reasons[:4])+('；其余见设置页' if len(reasons)>4 else '')
   if result['unresolved']:body+='\n存在流程或结果核对异常，详见设置页。'
   notify(title,body)
  return True
 except Exception as e:
  update(last_result={'status':'FAILED','error_type':type(e).__name__,'at':now(),'trigger':trigger,'submission_status':'check_execution_journal'})
  if settings()['notifyError']:notify('电商脚本：运行异常','本次运行中断，请检查记录；如有提交，须核对结果，禁止直接重试。')
  return False
 finally:update(running=False);JOB.release()

def loop():
 next_check=0
 while True:
  try:
   cfg=settings()
   if time.monotonic()>=next_check:
    if state.get('pending_notice'):
     n=state['pending_notice'];notify(n['title'],n['body'])
    if cfg['keepaliveEnabled']:keepalive()
    next_check=time.monotonic()+cfg['keepaliveMinutes']*60
   current=datetime.datetime.now(TZ);day=(current.weekday()+1)%7
   if cfg['approvalEnabled'] and day in cfg['approvalWeekdays']:
    for t in cfg['approvalTimes']:
     stamp=current.date().isoformat()+' '+t;h,m=map(int,t.split(':'));planned=current.replace(hour=h,minute=m,second=0,microsecond=0)
     if 0<=(current-planned).total_seconds()<120 and stamp not in state.get('scheduled_done',[]):
      update(scheduled_done=(state.get('scheduled_done',[])+[stamp])[-50:]);validate_run('schedule')
  except Exception as e:update(service_error=type(e).__name__)
  time.sleep(10)

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def send(self,data,code=200,kind='application/json; charset=utf-8'):
  raw=data.encode() if isinstance(data,str) else json.dumps(data,ensure_ascii=False).encode();self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; frame-ancestors 'none'");self.end_headers();self.wfile.write(raw)
 def allowed(self):return self.headers.get('Host') in ('127.0.0.1:18766','localhost:18766')
 def do_GET(self):
  if not self.allowed():return self.send({'error':'host'},403)
  if self.path=='/':return self.send((ROOT/'settings.html').read_text().replace('__TOKEN__',TOKEN),kind='text/html; charset=utf-8')
  if self.path=='/api/settings':
   cfg=settings();cfg['barkKeyConfigured']=bool(json.loads((PRIVATE/'notification.json').read_text()).get('barkKey'));return self.send(cfg)
  if self.path=='/api/status':
   with STATE_LOCK:return self.send(dict(state))
  self.send({'error':'not found'},404)
 def do_POST(self):
  if not self.allowed() or self.headers.get('X-Local-Token')!=TOKEN or self.headers.get('Origin','http://127.0.0.1:18766') not in ('http://127.0.0.1:18766','http://localhost:18766'):return self.send({'error':'access denied'},403)
  try:
   n=int(self.headers.get('Content-Length','0'))
   if not 0<=n<=16384:raise ValueError('request too large')
   data=json.loads(self.rfile.read(n) or b'{}')
   if self.path=='/api/settings':
    cfg=settings();allowed=set(BOOLS+['approvalTimes','approvalWeekdays','keepaliveMinutes','processingIntervalSeconds']);cfg.update({k:v for k,v in data.items() if k in allowed});validate(cfg)
    if data.get('barkKey'):
     secret=json.loads((PRIVATE/'notification.json').read_text());secret['barkKey']=str(data['barkKey']).strip();atomic(PRIVATE/'notification.json',secret)
    atomic(SETTINGS,cfg);return self.send({'saved':True})
   if self.path=='/api/run':
    if state.get('running'):return self.send({'error':'已有验证运行'},409)
    threading.Thread(target=validate_run,args=('manual_live' if data.get('execute') is True else 'manual',),daemon=True).start();return self.send({'started':True})
   if self.path=='/api/bark-test':return self.send(notify('电商脚本：Bark 测试','这是本机设置页面发送的测试通知。当前为验证模式，不提交真实审批。'))
   self.send({'error':'not found'},404)
  except Exception:self.send({'error':'设置或请求无效'},400)
if __name__=='__main__':
 settings();threading.Thread(target=loop,daemon=True).start();ThreadingHTTPServer(('127.0.0.1',18766),Handler).serve_forever()
