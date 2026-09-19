#!/usr/bin/env node
// Node.js alternative: built-in modules only. Local machine only.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';

const root=fs.realpathSync(path.join(path.dirname(fileURLToPath(import.meta.url)),'public'));
const health={app:'python360-local',version:'1.0.0'};
const args=process.argv.slice(2);
let port=4173,open=true;
for(let i=0;i<args.length;i++){
 if(args[i]==='--no-browser')open=false;
 else if(args[i]==='--port')port=Number(args[++i]);
 else {console.error('Usage: node server.mjs [--port 4173] [--no-browser]');process.exit(1);}
}
if(!Number.isInteger(port)||port<1||port>65535){console.error('Port must be between 1 and 65535.');process.exit(1);}
const url=`http://localhost:${port}`;
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8','.svg':'image/svg+xml','.woff2':'font/woff2'};
const openBrowser=()=>{if(!open)return;const cmd=process.platform==='win32'?'rundll32':process.platform==='darwin'?'open':'xdg-open';const a=process.platform==='win32'?['url.dll,FileProtocolHandler',url]:[url];const child=spawn(cmd,a,{detached:true,stdio:'ignore'});child.on('error',()=>console.log('Open this URL in a browser: '+url));child.unref();};
const server=http.createServer((req,res)=>{
 function reply(status,body,type='text/plain; charset=utf-8'){
  const buffer=Buffer.isBuffer(body)?body:Buffer.from(body);
  const headers={'Content-Type':type,'Content-Length':buffer.length,'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','Content-Security-Policy':"frame-ancestors 'none'; object-src 'none'; base-uri 'none'"};
  if(status===405)headers.Allow='GET, HEAD';
  res.writeHead(status,headers);res.end(req.method==='HEAD'?undefined:buffer);
 }
 if(!['GET','HEAD'].includes(req.method))return reply(405,'Only GET and HEAD are supported.');
 if(![`localhost:${port}`,`127.0.0.1:${port}`].includes((req.headers.host||'').toLowerCase()))return reply(403,'Localhost access only.');
 let pathname;try{pathname=decodeURIComponent(req.url.split('?')[0]);}catch{return reply(400,'Invalid path.');}
 if(pathname==='/__python360_health')return reply(200,JSON.stringify(health),'application/json');
 if(!pathname.startsWith('/')||pathname.includes('\\')||pathname.includes('\0')||pathname.split('/').filter(Boolean).some(x=>x.startsWith('.')))return reply(404,'Not found.');
 try{
  const file=fs.realpathSync(path.join(root,pathname==='/'?'index.html':pathname.slice(1)));
  const relative=path.relative(root,file);
  if(relative.startsWith('..')||path.isAbsolute(relative)||!fs.statSync(file).isFile())return reply(404,'Not found.');
  reply(200,fs.readFileSync(file),mime[path.extname(file)]||'application/octet-stream');
 }catch{return reply(404,'Not found.');}
});
server.on('error',err=>{
 if(err.code!=='EADDRINUSE'){console.error('Cannot start the local server: '+err.message);process.exitCode=1;return;}
 const request=http.get({hostname:'127.0.0.1',port,path:'/__python360_health',headers:{Host:`localhost:${port}`},timeout:2000},response=>{
  let data='';response.on('data',chunk=>{data+=chunk;if(data.length>1024)request.destroy();});
  response.on('end',()=>{let same=false;try{const v=JSON.parse(data);same=v.app===health.app&&v.version===health.version;}catch{}
   if(same){console.log('Python 360 is already running at '+url);openBrowser();}else fail();
  });
 });
 function fail(){console.error(`Port ${port} is used by another app. Close it or run: node server.mjs --port 4174`);process.exitCode=1;}
 request.on('timeout',()=>request.destroy());request.on('error',fail);
});
server.listen(port,'127.0.0.1',()=>{console.log('Python 360 is ready: '+url);console.log('Keep this window open. Press Ctrl+C to stop.');openBrowser();});
process.on('SIGINT',()=>{console.log('\nPython 360 stopped.');server.close(()=>process.exit(0));});
