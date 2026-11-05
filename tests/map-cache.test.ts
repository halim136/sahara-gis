import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {MapDiskCache,tileSpec,TileError} from '../server/mapCache';
const image=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aR1kAAAAASUVORK5CYII=','base64');
const spec=tileSpec({source:'google_sat',z:'3',x:'4',y:'2'});
async function setup(fetcher:typeof fetch=async()=>{throw Error('Unexpected network');}){
  const base=path.resolve('build/cache-tests');await fs.mkdir(base,{recursive:true});
  const dir=await fs.mkdtemp(path.join(base,'case-'));
  const cache=new MapDiskCache(path.join(dir,'cache_gmt'),path.join(dir,'legacy'),fetcher);await cache.initialize();return cache;
}
test('initializes native source folders with distinct Google imagery and labels',async()=>{
  const cache=await setup();const dirs=await fs.readdir(cache.root);
  for(const name of ['sat','Both','Google.Hybrid','ArcGIS.Imagery','land'])assert.ok(dirs.includes(name));
});
test('imports GM1 files using XYZ z, Y directory and X filename',async()=>{
  const cache=await setup();const file=path.join(cache.root,'sat/z3/2/4.png');await fs.mkdir(path.dirname(file),{recursive:true});await fs.writeFile(file,image);
  const result=await cache.get(spec,true);assert.deepEqual(result.bytes,image);assert.equal(result.hit,true);
  await assert.rejects(cache.get(tileSpec({source:'google_sat',z:'3',x:'2',y:'4'}),true),error=>error instanceof TileError&&error.status===404);
});
test('offline miss does not make a network call',async()=>{
  let calls=0;const cache=await setup(async()=>{calls++;throw Error('network');});
  await assert.rejects(cache.get(spec,true),error=>error instanceof TileError&&error.status===404);assert.equal(calls,0);
});
test('online fetch persists exact bytes with actual image extension',async()=>{
  let calls=0;const cache=await setup(async(url)=>{calls++;assert.match(String(url),/x=4&y=2&z=3/);return new Response(new Uint8Array(image));});
  const result=await cache.get(spec);assert.equal(result.hit,false);assert.equal(result.mime,'image/png');
  assert.deepEqual(await fs.readFile(path.join(cache.root,'sat/z3/2/4.png')),image);
  assert.equal((await cache.get(spec,true)).hit,true);assert.equal(calls,1);
});
test('concurrent requests for one tile share a single download',async()=>{
  let calls=0;let resolve!:()=>void;const barrier=new Promise<void>(r=>resolve=r);
  const cache=await setup(async()=>{calls++;await barrier;return new Response(new Uint8Array(image));});
  const requests=[cache.get(spec),cache.get(spec),cache.get(spec)];
  setTimeout(resolve,30);await Promise.all(requests);assert.equal(calls,1);
});
test('migrates legacy web hierarchy while preserving original',async()=>{
  const cache=await setup();const old=path.join(cache.legacyRoot,'google_sat/z3/0/x4/0/y2.png');await fs.mkdir(path.dirname(old),{recursive:true});await fs.writeFile(old,image);
  assert.deepEqual((await cache.get(spec,true)).bytes,image);assert.deepEqual(await fs.readFile(old),image);
  assert.deepEqual(await fs.readFile(path.join(cache.root,'sat/z3/2/4.png')),image);
});
test('reads native SAS hierarchy with its zoom offset',async()=>{
  const cache=await setup();const file=path.join(cache.root,'sat/z4/0/x4/0/y2.png');await fs.mkdir(path.dirname(file),{recursive:true});await fs.writeFile(file,image);
  assert.deepEqual((await cache.get(spec,true)).bytes,image);
});
test('rejects traversal, unknown sources, noninteger and out-of-range coordinates',()=>{
  for(const query of [{source:'../sat',z:'3',x:'4',y:'2'},{source:'__proto__',z:'3',x:'4',y:'2'},
      {source:'google_sat',z:'3',x:'8',y:'2'},{source:'google_sat',z:'3.1',x:'4',y:'2'},
      {source:'google_sat',z:'3',x:'-1',y:'2'},{source:'google_sat',z:['3'],x:'4',y:'2'}])assert.throws(()=>tileSpec(query),TileError);
});
test('rejects upstream HTML and leaves no fake cached tile',async()=>{
  const cache=await setup(async()=>new Response('<html>error</html>'));await assert.rejects(cache.get(spec),TileError);
  assert.equal((await cache.stats()).total_tiles,0);
});
test('stats show source folder counts and image bytes',async()=>{
  const cache=await setup();await cache.save(spec,image);const stats=await cache.stats();
  assert.equal(stats.total_tiles,1);assert.equal(stats.total_size_bytes,image.length);assert.equal(stats.base_dir,cache.root);
  assert.equal(stats.layers.find(s=>s.folder==='sat')?.tiles,1);
});
