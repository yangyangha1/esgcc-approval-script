"""Browser-free, read-only rule validation. No workflow token checks or save routes."""
import json,select,shutil,subprocess,time,urllib.parse,urllib.error,http.client
from client import Client,ROOT,BASE
ROUTES={'material':'/creEnquiryWorkflow/list/1','service':'/creEnquiryWorkflowNew/list/1','materialProcurement':'/workflowAuditing/list/1','serviceProcurement':'/workflowAuditing/purchaseProjectList/1'}

def command(c,url,html,name,info):
 p=subprocess.Popen([shutil.which('node') or 'node',str(ROOT/'validator.cjs')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
 try:
  p.stdin.write(json.dumps({'url':url,'html':html,'command':name,'input':info})+'\n');p.stdin.flush();deadline=time.monotonic()+70;calls=0
  while time.monotonic()<deadline:
   if not select.select([p.stdout],[],[],max(0,deadline-time.monotonic()))[0]:raise TimeoutError()
   line=p.stdout.readline()
   if not line:raise ValueError('validator stopped')
   message=json.loads(line)
   if 'result' in message:return message['result']
   if 'error' in message:raise ValueError('validator failed')
   calls+=1
   if calls>50 or message.get('fetch')!='/creEnquiryWorkflow/findGoodsList' or message.get('method')!='POST':raise ValueError('route denied')
   data=dict(urllib.parse.parse_qsl(message['body'],keep_blank_values=True))
   if set(data)!={'pageNo','enquiryId','enquirySource'}:raise ValueError('unexpected fields')
   final,body=c.request(message['fetch'],data)
   if urllib.parse.urlparse(final).path!=message['fetch']:raise ValueError('session changed')
   p.stdin.write(json.dumps({'data':json.loads(body)})+'\n');p.stdin.flush()
  raise TimeoutError()
 finally:
  p.terminate()
  try:p.wait(timeout=2)
  except subprocess.TimeoutExpired:p.kill();p.wait()
  p.stdin.close();p.stdout.close()

def run(settings):
 import execution,fcntl
 lock=open(ROOT/'private'/'runner.lock','a')
 try:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  return run_locked(settings,execution)
 finally:lock.close()

def run_locked(settings,execution):
 live=settings.get('validationOnly',True) is False
 c=Client()
 original_request=c.request
 def readonly_request(path,data=None,json_body=False):
  for attempt in range(3):
   try:return original_request(path,data,json_body)
   except (TimeoutError,ConnectionError,urllib.error.URLError,http.client.HTTPException) as exc:
    safe=(data is None and ('/list/' in path or '/forward/100' in path or '/purchaseProjectList/' in path)) or path=='/creEnquiryWorkflow/findGoodsList'
    if isinstance(exc,urllib.error.HTTPError) and exc.code not in (408,429,500,502,503,504):safe=False
    if not safe or attempt==2:raise
    time.sleep(2*(attempt+1))
 c.request=readonly_request
 if c.check()!='LOGIN_OK':raise ValueError('LOGIN_REQUIRED')
 result={'mode':'live' if live else 'validation_only','approved':0,'would_approve':0,'would_reject':0,'manual':0,'items':0,'categories':{},'unresolved':[],'reasons':{}}
 def reason(counts,text):
  counts['manual']+=1;result['reasons'][text]=result['reasons'].get(text,0)+1
 halted=False
 def collect(category,path):
  found={}
  for page in range(1,51):
   url,html=c.request(path+('' if page==1 else '?pageNo='+str(page)))
   listing=command(c,url,html,'list',{'category':category,'expectedPath':path})
   if listing.get('status')!='LOGIN_OK' or not listing.get('tableReady'):raise ValueError('list gate failed')
   if not listing['rows']:return list(found.values())
   fresh=0
   for row in listing['rows']:
    key=execution.identity(row['detail']) if row.get('detail') else row['key']
    if key not in found:row['stable_key']=key;found[key]=row;fresh+=1
   if not fresh:raise ValueError('pagination repeated')
  raise ValueError('pagination limit')
 for category,path in ROUTES.items():
  if halted:break
  enabled=settings.get(category+'Enabled',False) if category.endswith('Procurement') else any(settings.get(category+x+'Enabled',False) for x in ['Bid','Confirm'])
  if not enabled:continue
  if category.endswith('Procurement'):
   result['unresolved'].append(category+':请购付款与签章流程尚未迁移');continue
  counts={'items':0,'approved':0,'would_approve':0,'would_reject':0,'manual':0};seen=set();saved=set();complete=False
  try:
   for round_no in range(10 if live else 1):
    rows=collect(category,path)
    if live:
     present={r['stable_key'] for r in rows};removed=saved-present
     counts['approved']+=len(removed);execution.reconciled(removed);saved-=removed
    fresh=[r for r in rows if r['stable_key'] not in seen]
    if not fresh:complete=True;break
    for row in fresh:
     key=row['stable_key'];seen.add(key)
     if not settings.get(category+('Confirm' if row['kind']=='confirm' else 'Bid')+'Enabled',False):continue
     counts['items']+=1
     if not row.get('detail'):reason(counts,'详情入口未识别');continue
     parsed=urllib.parse.urlparse(row['detail']);expected=('/creEnquiryWorkflowNew' if category=='service' else '/creEnquiryWorkflow')+'/forward/100'
     if parsed.scheme or parsed.netloc or parsed.path!=expected:reason(counts,'详情地址不符合预期');continue
     detail_url,detail=c.request(row['detail'])
     if urllib.parse.urlparse(detail_url).path!=expected:raise ValueError('detail gate failed')
     decision=command(c,detail_url,detail,'detail',{'category':category,'kind':row['kind']})
     if decision.get('status')=='LOGIN_EXPIRED':raise ValueError('LOGIN_REQUIRED')
     if decision.get('wouldApprove'):
      if not live:counts['would_approve']+=1
      else:
       already_attempted=key in execution.load()
       ok,why=execution.submit(c,key,decision.get('execution',{}))
       if ok:saved.add(key)
       else:
        reason(counts,why)
        if not already_attempted:
         halted=True;result['unresolved'].append('提交链路未确认，已停止后续提交');break
       time.sleep(max(4,int(settings.get('processingIntervalSeconds',8))))
     elif decision.get('wouldReject'):
      if live:reason(counts,'多轮竞价无附件，驳回流程尚未验证，留人工')
      else:counts['would_reject']+=1
     else:reason(counts,decision.get('reason') or '必要字段或页面结构无法确认')
    if halted:complete=True;break
    if not live:complete=True;break
   if live and not complete:result['unresolved'].append(category+':达到复查轮次上限')
   if saved:
    for attempt in range(3):
     time.sleep(1);present={r['stable_key'] for r in collect(category,path)};removed=saved-present
     counts['approved']+=len(removed);execution.reconciled(removed);saved-=removed
     if not saved:break
    if saved:result['unresolved'].append(category+':保存成功但列表移除尚未确认');reason(counts,'网站显示审批成功，但单据仍在待审批列表，需人工确认')
  except Exception as e:
   result['unresolved'].append(category+':读取或核对异常 '+type(e).__name__)
   if saved:result['unresolved'].append(category+':存在保存成功但未完成列表核对的项目')
  result['categories'][category]=counts
  for key in counts:result[key]+=counts[key]
 result['status']='REVIEW_REQUIRED' if result['unresolved'] else 'COMPLETED' if live else 'VALIDATED'
 return result
if __name__=='__main__':
 # CLI is intentionally dry-run; real writes only through the scheduled service.
 try:
  cfg=json.loads((ROOT/'settings.json').read_text());cfg['validationOnly']=True
  print(json.dumps(run(cfg),ensure_ascii=False,indent=2))
 except Exception as e:print(json.dumps({'status':'FAILED','error_type':type(e).__name__}));raise SystemExit(1)
