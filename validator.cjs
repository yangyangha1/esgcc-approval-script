const readline=require('node:readline'),fs=require('node:fs'),vm=require('node:vm');
const {parseHTML}=require('linkedom'),acorn=require('acorn');
const rl=readline.createInterface({input:process.stdin});let started=false,pending;
function parseLiteralArgs(s){const ast=acorn.parseExpressionAt('['+s+']',0,{ecmaVersion:2020});if(ast.end!==s.length+2||ast.type!=='ArrayExpression'||ast.elements.some(x=>!x||x.type!=='Literal'||x.regex))throw Error('nonliteral');return ast.elements.map(x=>x.value);}
function send(x){process.stdout.write(JSON.stringify(x)+'\n')}
async function run(a){
 const {document,HTMLElement}=parseHTML(a.html);
 // Match browser text semantics for non-rendered scripts and explicit hidden nodes.
 function visibleText(node){
  if(node.nodeType===3)return node.textContent;
  if(node.nodeType!==1)return '';
  if(['SCRIPT','STYLE','TEMPLATE','NOSCRIPT'].includes(node.tagName)||node.hasAttribute('hidden')||/display\s*:\s*none|visibility\s*:\s*hidden/i.test(node.getAttribute('style')||''))return '';
  return [...node.childNodes].map(visibleText).join(' ');
 }
 Object.defineProperty(HTMLElement.prototype,'innerText',{configurable:true,get(){return visibleText(this)}});

 Object.defineProperty(document,'scripts',{value:[...document.querySelectorAll('script')]});
 HTMLElement.prototype.getClientRects=()=>[{}];
 const remoteFetch=(url,options={})=>new Promise((resolve,reject)=>{pending={resolve,reject};send({fetch:String(url),method:options.method||'GET',body:options.body||''});});
 const scope={document,location:new URL(a.url),URL,URLSearchParams,setTimeout,clearTimeout,parseLiteralArgs,fetch:remoteFetch};
 const context=vm.createContext(scope,{codeGeneration:{strings:false,wasm:false}});
 vm.runInContext(fs.readFileSync(__dirname+'/vendor/page-command.js','utf8'),context,{timeout:2000});
 if(!['list','detail'].includes(a.command))throw Error('command denied');
 scope.command=a.command;scope.input={...a.input,dryRun:true};
 const result=await vm.runInContext('pageCommand(command,input)',context,{timeout:3000});
 if(a.command==='detail'&&result.wouldApprove){
  const agree=[...document.querySelectorAll('a,button,input')].find(n=>(n.innerText||n.value||'').trim()==='同意');
  const m=(agree?.getAttribute('onclick')||'').match(/agreeOrDisAgree\((.*)\)/s);
  const args=parseLiteralArgs(m[1]);const applyType=new URL(a.url).searchParams.get('applyType');
  const scripts=[...document.scripts].map(n=>n.text||'').join('\n');
  const names=[...new Set(scripts.match(/creEnquiryApprovalAutting\d+/g)||[])];
  const tokenName=names.find(n=>n.endsWith(applyType))||(names.length===1?names[0]:'');
  result.execution={isAgress:String(args[0]),enquiryId:String(args[1]),[tokenName]:String(args[2]),opinion:'',applyType,gidTypeCount:String(args[4]||''),workflowStep:String(args[5]||''),winBiddingWorkflowStep:String(args[6]||'')};
  if(a.input.category==='service')result.execution.inviteList='[]';
 }
 if(a.command==='list'&&result.tableReady){
  const table=[...document.querySelectorAll('table')].find(t=>[...t.querySelectorAll('thead th')].some(th=>th.innerText.trim()==='操作'));
  result.rows=result.rows.map(r=>{
   const tr=table.querySelectorAll('tbody tr')[r.index];
   const action=[...tr.querySelectorAll('a,button,input')].find(n=>/shenpi\s*\(/.test(n.getAttribute('onclick')||''));
   const call=action?.getAttribute('onclick')?.match(/^\s*shenpi\((.*)\)\s*;?\s*$/s);
   if(call){try{const args=parseLiteralArgs(call[1]);if(args.length===4&&[...document.scripts].some(n=>(n.textContent||'').includes('/forward/100?enquiryId='))){const p=a.input.category==='service'?'/creEnquiryWorkflowNew':'/creEnquiryWorkflow';r.detail=p+'/forward/100?'+new URLSearchParams({enquiryId:args[0],applyType:args[2],gidTypeCount:args[3]});}}catch{}}
   return r;
  });
 }
 send({result});rl.close();
}
rl.on('line',line=>{try{const data=JSON.parse(line);if(!started){started=true;run(data).catch(()=>{send({error:'VALIDATION_FAILED'});rl.close();});}else if(pending){const p=pending;pending=null;if(data.error)p.reject(Error(data.error));else p.resolve({ok:true,json:async()=>data.data});}}catch{send({error:'INVALID_PROTOCOL'});rl.close();}});
