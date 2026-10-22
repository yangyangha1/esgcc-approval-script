"""Durable, single-attempt approval transaction. No automatic retry after reservation."""
import hashlib,json,os,time,urllib.parse,urllib.error,socket
from pathlib import Path
from client import PRIVATE
JOURNAL=PRIVATE/'execution-journal.json'
def identity(detail):
 q=urllib.parse.parse_qs(urllib.parse.urlparse(detail).query)
 return hashlib.sha256(json.dumps([q.get('enquiryId'),q.get('applyType')],sort_keys=True).encode()).hexdigest()
def load():return json.loads(JOURNAL.read_text()) if JOURNAL.exists() else {}
def store(data):
 temp=JOURNAL.with_suffix('.tmp');fd=os.open(temp,os.O_CREAT|os.O_WRONLY|os.O_TRUNC,0o600)
 with os.fdopen(fd,'w') as f:json.dump(data,f);f.flush();os.fsync(f.fileno())
 os.replace(temp,JOURNAL)

def submit(c,key,payload):
 data=load()
 if key in data:
  previous=data[key]
  if previous.get('error_type')=='TimeoutError':return False,'上次处理超时，结果待确认，本次未再提交'
  return False,'上次处理结果待确认，本次未再提交'
 token_names=[k for k in payload if k.startswith('creEnquiryApprovalAutting')]
 if len(token_names)!=1 or payload.get('isAgress')!='0' or not payload.get('enquiryId'):return False,'保存参数不完整'
 token=token_names[0]
 if not token.endswith(payload.get('applyType','')):return False,'审批令牌类型不匹配'
 data[key]={'state':'reserved','at':time.time(),'category':'service' if payload['applyType'] in ('4','11') else 'material'};store(data)
 def get_json(path,body=None):
  for attempt in range(3):
   try:
    url,text=c.request(path,body);break
   except urllib.error.URLError as exc:
    # Only errors proving connection was never established; not read timeouts/resets.
    safe=isinstance(exc.reason,(socket.gaierror,ConnectionRefusedError))
    if not safe or attempt==2:raise
    data[key]['connect_retries']=data[key].get('connect_retries',0)+1;store(data)
    time.sleep(3*(attempt+1))
  if urllib.parse.urlparse(url).path!=urllib.parse.urlparse(path).path:raise ValueError('redirect')
  return json.loads(text)
 try:
  time.sleep(2)
  check=get_json('/creEnquiryWorkflow/beanValidatorForToken?'+urllib.parse.urlencode({token:payload[token],'applyType':payload['applyType']}))
  if str(check.get('resultCode',''))!='00':
   data[key]['state']='token_unconfirmed';store(data);return False,'令牌校验未确认通过，需人工核对'
  time.sleep(2.5)
  valid=get_json('/creEnquiryWorkflow/validateEnquiryWorkflow?'+urllib.parse.urlencode({'enquiryId':payload['enquiryId'],'applyType':payload['applyType']}))
  if valid is not True:
   data[key]['state']='workflow_blocked';store(data);return False,'单据已取消、已处理或流程状态不明确'
  time.sleep(2)
  data[key]['state']='save_started';store(data)
  answer=get_json('/creEnquiryWorkflow/save',payload)
  if str(answer.get('resultCode'))=='00' and '审批通过' in str(answer.get('resultMessage','')):
   data[key]['state']='save_confirmed';store(data);return True,''
  data[key]['state']='save_unclear';store(data);return False,'网站未返回明确审批结果，需人工确认'
 except Exception as e:
  data[key].update(previous_stage=data[key]['state'],state='uncertain',error_type=type(e).__name__);store(data)
  return False,'处理请求异常，结果待确认，已停止继续提交'

def reconciled(keys):
 data=load()
 for key in keys:
  if key in data:data[key]['state']='reconciled'
 store(data)
