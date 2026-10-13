// @vitest-environment node
import { createServer as createHttpServer } from 'node:http';
import { createServer as createViteServer } from 'vite';
import type { AddressInfo } from 'node:net';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

it('forwards one protected write with its origin, cookies and CSRF while excluding lookalike routes',async({skip})=>{
  const fixtureRoot=await mkdtemp(join(tmpdir(),'auditor-proxy-test-'));
  const received:Array<{url:string|undefined;origin:string|undefined;cookie:string|undefined;csrf:string|string[]|undefined;body:string}>=[];
  const backend=createHttpServer(async(req,res)=>{
    let body='';for await(const chunk of req)body+=chunk;
    received.push({url:req.url,origin:req.headers.origin,cookie:req.headers.cookie,csrf:req.headers['x-csrf-token'],body});
    res.setHeader('Content-Type','application/json');res.end(JSON.stringify({saved:true}));
  });
  let frontend:Awaited<ReturnType<typeof createViteServer>>|undefined;
  try{
    await new Promise<void>((resolve,reject)=>{
      backend.once('error',reject);
      backend.listen(0,'127.0.0.1',()=>{backend.off('error',reject);resolve();});
    });
    vi.stubEnv('AUDITOR_PROXY_TARGET',`http://127.0.0.1:${(backend.address() as AddressInfo).port}`);
    const {default:configuration}=await import('../../vite.config');
    frontend=await createViteServer({configFile:false,root:fixtureRoot,cacheDir:join(fixtureRoot,'cache'),server:{host:'127.0.0.1',port:0,proxy:configuration.server?.proxy},logLevel:'silent'});
    await frontend.listen();
    const origin=`http://127.0.0.1:${(frontend.httpServer!.address() as AddressInfo).port}`;
    const response=await fetch(`${origin}/api/v1/proxy-verification`,{method:'POST',headers:{Origin:origin,Cookie:'synthetic-session=test-only','X-CSRF-Token':'synthetic-test-csrf','Content-Type':'application/json'},body:JSON.stringify({example:'synthetic'})});
    expect(await response.json()).toEqual({saved:true});
    expect(received).toEqual([{url:'/api/v1/proxy-verification',origin,cookie:'synthetic-session=test-only',csrf:'synthetic-test-csrf',body:'{"example":"synthetic"}'}]);
    await fetch(`${origin}/api/v10/proxy-verification`);
    expect(received).toHaveLength(1);
  }catch(error){
    const code=(error as NodeJS.ErrnoException).code;
    if(code==='EPERM'||code==='EACCES')skip();
    throw error;
  }finally{
    await frontend?.close();
    if(backend.listening)await new Promise<void>((resolve,reject)=>backend.close(error=>error?reject(error):resolve()));
    await rm(fixtureRoot,{recursive:true,force:true});
    vi.unstubAllEnvs();
  }
});
