// Disposable WASM CPU baseline. Precache assets once, then --offline proves no HTTP asset fetch.
const { createWorker } = require('tesseract.js');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const root = __dirname;
const cache = path.join(root, 'cache/tesseract');
fs.mkdirSync(cache, { recursive: true });
(async () => {
  const t = performance.now();
  const offline = process.argv.includes('--offline');
  const worker = await createWorker(['eng', 'msa'], 1, {
    cachePath: cache, cacheMethod: 'write',
    ...(offline ? { langPath: cache, gzip: false } : {}),
  });
  await worker.setParameters({ tessedit_pageseg_mode: '6' });
  const report = { engine: 'tesseract.js', version: require('tesseract.js/package.json').version,
    node: process.version, init_ms: performance.now()-t, languages: ['eng','msa'], psm: 6,
    offline_assets_only: offline, note: 'Node WASM worker, not a browser or phone measurement', runs: [] };
  const images = fs.readdirSync(path.join(root,'data/images')).filter(x => /\.(jpg|png)$/.test(x)).sort();
  for(let pass=0;pass<2;pass++) for(const name of images) {
    const start = performance.now();
    const { data } = await worker.recognize(path.join(root,'data/images',name), {}, { text:true, tsv:true });
    const elapsed_ms = performance.now()-start;
    const words = data.tsv.trim().split('\n').slice(1).map(x=>x.split('\t')).filter(x=>x[0]==='5' && x[11]?.trim());
    const lines = words.map(x => { const [left,top,width,height] = x.slice(6,10).map(Number); return {
      text:x.slice(11).join('\t'), score:Number(x[10])/100,
      box:[[left,top],[left+width,top],[left+width,top+height],[left,top+height]]};});
    report.runs.push({image:name,pass,elapsed_ms,sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(root,'data/images',name))).digest('hex'),lines});
    fs.mkdirSync(path.join(root,'results'),{recursive:true});
    fs.writeFileSync(path.join(root,'results/tesseract.json'), JSON.stringify(report,null,2));
    console.log('tesseract',pass,name,Math.round(elapsed_ms));
  }
  await worker.terminate();
})().catch(err=>{console.error(err.message);process.exitCode=1;});
