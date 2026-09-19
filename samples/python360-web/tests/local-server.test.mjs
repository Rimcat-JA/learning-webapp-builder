import assert from 'node:assert/strict';
import http from 'node:http';
import net from 'node:net';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const results=[];
const record=s=>{results.push(s);console.log('PASS',s);};
fs.mkdirSync(path.join(root,'tests/results'),{recursive:true});
function launch(command,args,options={}){
 const child=spawn(command,args,{cwd:os.tmpdir(),env:process.env,...options});let text='';
 child.stdout.on('data',chunk=>{text+=chunk;});child.stderr.on('data',chunk=>{text+=chunk;});
 return {child,text:()=>text};
}
function done(child,timeout=20000){return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{child.kill();reject(Error('Child timed out'));},timeout);child.once('error',e=>{clearTimeout(timer);reject(e);});child.once('exit',code=>{clearTimeout(timer);resolve(code);});});}
const freePort=()=>new Promise(resolve=>{const s=net.createServer();s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>resolve(p));});});
function request(port,route='/',method='GET',host=`localhost:${port}`){return new Promise((resolve,reject)=>{const req=http.request({hostname:'127.0.0.1',port,path:route,method,headers:{Host:host}},res=>{const parts=[];res.on('data',c=>parts.push(c));res.on('end',()=>resolve({status:res.statusCode,headers:res.headers,body:Buffer.concat(parts)}));});req.on('error',reject);req.end();});}
async function ready(port){for(let i=0;i<80;i++){try{const r=await request(port,'/__python360_health');if(r.status===200)return;}catch{}await new Promise(r=>setTimeout(r,50));}throw Error('Server did not start');}
for(const backend of ['python','node']){
 const port=await freePort();const command=backend==='python'?(process.env.PYTHON_COMMAND||(process.platform==='win32'?'python':'python3')):process.execPath;
 const args=[path.join(root,backend==='python'?'server.py':'server.mjs'),'--no-browser','--port',String(port)];
 const running=launch(command,args);
 try{
  await ready(port);
  const home=await request(port);assert.equal(home.status,200);assert.match(home.headers['content-type'],/text\/html/);assert.match(home.body.toString(),/Python 360/);
  const data=JSON.parse((await request(port,'/data.json')).body.toString());assert.equal(data.questions.length,360);
  assert.equal(data.questions.filter(q=>q.type==='number').length,251);assert.equal(data.questions.filter(q=>q.type==='choice').length,109);
  const js=await request(port,'/app.js');assert.match(js.headers['content-type'],/(text|application)\/javascript/);
  const font=await request(port,'/fonts/noto-sans-jp-latin-wght-normal.woff2');assert.equal(font.status,200);assert.equal(font.headers['content-type'],'font/woff2');
  const head=await request(port,'/data.json','HEAD');assert.equal(head.status,200);assert.equal(head.body.length,0);
  assert.equal((await request(port,'/','POST')).status,405);
  assert.equal((await request(port,'/','GET','untrusted.example')).status,403);
  for(const route of ['/server.py','/fonts/','/%2e%2e/server.py','/../README.md','/.openai/hosting.json','/unknown'])assert.equal((await request(port,route)).status,404,route);
  record(backend+': real server, correct asset types, all 360 questions, HEAD, no directory listing, path/host restrictions');
  const duplicate=launch(command,args);assert.equal(await done(duplicate.child),0,duplicate.text());assert.match(duplicate.text(),/already running/);record(backend+': repeated start reuses same origin and existing server');
  if(backend==='python'){
   const browserTest=launch(process.execPath,[path.join(root,'tests/browser.test.mjs')],{cwd:root,env:{...process.env,TEST_URL:`http://localhost:${port}`}});
   browserTest.child.stdout.on('data',chunk=>process.stdout.write(chunk));
   const exit=await done(browserTest.child,120000);assert.equal(exit,0,browserTest.text());record('Python localhost: full 16-scenario browser suite against the actual packaged server');
  }else{
   const {createRequire}=await import('node:module');const require=createRequire(import.meta.url);const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
   const browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});
   try{
    const page=await browser.newPage();await page.goto(`http://localhost:${port}/#q/G001`);await page.locator('#answer').fill('２');await page.getByRole('button',{name:'回答を確定する'}).click();await page.waitForSelector('.feedback.success');
    await page.goto(`http://localhost:${port}/#q/G005`);await page.locator('.choice').filter({has:page.locator('input[value="エ"]')}).click();await page.getByRole('button',{name:'回答を確定する'}).click();await page.waitForSelector('.feedback.success');
    await page.goto(`http://localhost:${port}/#progress`);assert.equal(await page.locator('.heat-cell.correct').count(),2);await page.reload();await page.waitForSelector('.heatmap');assert.equal(await page.locator('.heat-cell.correct').count(),2);
   }finally{await browser.close();}
   record('Node localhost: numeric/choice grading and persistence through page reload');
  }
 }finally{const finished=done(running.child);running.child.kill();await finished;}
 const blocker=http.createServer((req,res)=>res.end('other app'));
 await new Promise(resolve=>blocker.listen(port,'127.0.0.1',resolve));
 try{const conflict=launch(command,args);assert.equal(await done(conflict.child),1,conflict.text());assert.match(conflict.text(),/used by another app/);record(backend+': occupied port reports a clear error without changing ports');}finally{await new Promise(resolve=>blocker.close(resolve));}
}
fs.writeFileSync(path.join(root,'tests/results/local-server-report.json'),JSON.stringify({at:new Date().toISOString(),passed:results},null,2));
console.log('LOCAL SERVER: all checks passed.');
