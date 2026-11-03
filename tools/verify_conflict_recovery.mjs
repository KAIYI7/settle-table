/**
 * Real automated browser end-to-end test using Chrome DevTools Protocol (CDP).
 * Spawns two isolated Headless Chrome browser instances (Organizer and Diner)
 * with separate user-data directories (isolated cookies, session, and DOM).
 * 
 * Works across Windows, Linux, and macOS without hardcoded paths.
 */
import { spawn, execSync } from 'node:child_process';
import fs, { existsSync } from 'node:fs';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path, { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:net';
import { randomBytes } from 'node:crypto';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function parseArgs() {
  const args = process.argv.slice(2);
  const options = {
    port: process.env.SETTLETABLE_PORT ? parseInt(process.env.SETTLETABLE_PORT, 10) : 8089,
    chrome: null,
    python: null,
    uiRegressionsOnly: args.includes('--ui-regressions-only'),
  };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--port' && args[i + 1]) {
      options.port = parseInt(args[++i], 10);
    } else if (args[i] === '--chrome' && args[i + 1]) {
      options.chrome = args[++i];
    } else if (args[i] === '--python' && args[i + 1]) {
      options.python = args[++i];
    }
  }
  return options;
}

function resolveChromePath(explicitPath) {
  if (explicitPath && existsSync(explicitPath)) return explicitPath;
  const envPath = process.env.CHROME_BIN || process.env.CHROME_PATH || process.env.PUPPETEER_EXECUTABLE_PATH;
  if (envPath && existsSync(envPath)) return envPath;

  const platform = process.platform;
  const candidates = [];

  if (platform === 'win32') {
    candidates.push(
      'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
      'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
      join(process.env.LOCALAPPDATA || '', 'Google', 'Chrome', 'Application', 'chrome.exe'),
      'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
      'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe'
    );
  } else if (platform === 'darwin') {
    candidates.push(
      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      '/Applications/Chromium.app/Contents/MacOS/Chromium',
      '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'
    );
  } else {
    // Linux and other Unix
    candidates.push(
      '/usr/bin/google-chrome-stable',
      '/usr/bin/google-chrome',
      '/usr/bin/chromium',
      '/usr/bin/chromium-browser',
      '/snap/bin/chromium'
    );
    // Also try `which` lookup
    for (const bin of ['google-chrome-stable', 'google-chrome', 'chromium', 'chromium-browser']) {
      try {
        const found = execSync(`which ${bin} 2>/dev/null`, { encoding: 'utf-8' }).trim();
        if (found && existsSync(found)) return found;
      } catch (e) {}
    }
  }

  for (const p of candidates) {
    if (p && existsSync(p)) return p;
  }

  throw new Error(
    'Could not find a Google Chrome / Chromium executable. ' +
    'Please set the CHROME_BIN environment variable or pass --chrome <path>.'
  );
}

function resolvePythonPath(explicitPath) {
  if (explicitPath) return explicitPath;
  const envPath = process.env.PYTHON_BIN || process.env.PYTHON_PATH;
  if (envPath && existsSync(envPath)) return envPath;

  if (process.platform === 'win32') {
    if (existsSync('C:\\Python314\\python.exe')) return 'C:\\Python314\\python.exe';
    if (existsSync('C:\\Python312\\python.exe')) return 'C:\\Python312\\python.exe';
    return 'python';
  }
  try {
    execSync('python --version', { stdio: 'ignore' });
    return 'python';
  } catch (e) {
    return 'python3';
  }
}

class CDPPage {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.id = 0;
    this.callbacks = new Map();
    this.ready = new Promise((resolve, reject) => {
      this.ws.onopen = resolve;
      this.ws.onerror = reject;
    });
    this.ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if(msg.method === 'Network.responseReceived' && msg.params.response.status === 409) console.log('OBSERVED HTTP 409', msg.params.response.url);
      if (msg.id && this.callbacks.has(msg.id)) {
        const { resolve, reject } = this.callbacks.get(msg.id);
        this.callbacks.delete(msg.id);
        if (msg.error) reject(new Error(msg.error.message));
        else resolve(msg.result);
      }
    };
  }

  async send(method, params = {}) {
    await this.ready;
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.callbacks.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async evaluate(expr) {
    const exprStr = typeof expr === 'function' ? `(${expr.toString()})()` : expr;
    const res = await this.send('Runtime.evaluate', {
      expression: exprStr,
      returnByValue: true,
      awaitPromise: true,
    });
    if (res.exceptionDetails) {
      throw new Error(`Evaluation failed in browser: ${JSON.stringify(res.exceptionDetails)}`);
    }
    return res.result?.value;
  }

  async navigate(url) {
    await this.send('Page.navigate', { url });
  }

  async reload() {
    await this.evaluate('window.__reloading_marker = true');
    await this.send('Page.reload');
    await this.waitFor('window.__reloading_marker === undefined');
  }

  async screenshot(filePath) {
    const res = await this.send('Page.captureScreenshot', { format: 'png' });
    const buffer = Buffer.from(res.data, 'base64');
    await fs.promises.writeFile(filePath, buffer);
  }

  async waitFor(expr, timeoutMs = 8000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      try {
        const val = await this.evaluate(expr);
        if (val) return val;
      } catch (e) {}
      await new Promise(r => setTimeout(r, 100));
    }
    throw new Error(`Timeout waiting for expression: ${expr}`);
  }

  close() {
    try {
      this.ws.close();
    } catch (e) {}
  }
}

async function startChrome(chromeBin, dataDir, ownedProcesses) {
  const proc = spawn(chromeBin, [
    '--headless=new',
    '--remote-debugging-port=0',
    '--remote-debugging-address=127.0.0.1',
    `--user-data-dir=${dataDir}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-background-networking',
    '--disable-default-apps',
    '--disable-gpu',
    '--no-sandbox',
    '--disable-dev-shm-usage',
    'about:blank',
  ]);

  let spawnError = null;
  proc.on('error', err => { spawnError = err; });
  const owned = {proc, page: null};
  ownedProcesses.push(owned);
  let stderr = '';
  proc.stderr?.on('data', d => { stderr += d.toString(); });

  // Wait for DevTools HTTP endpoint
  const activePortFile = join(dataDir, 'DevToolsActivePort');
  let target = null;
  for (let i = 0; i < 300; i++) {
    if (spawnError) throw spawnError;
    if (proc.exitCode !== null) {
      throw new Error(`Chrome exited prematurely with code ${proc.exitCode}: ${stderr}`);
    }
    try {
      const [port] = (await fs.promises.readFile(activePortFile, 'utf8')).trim().split('\n');
      const res = await fetch(`http://127.0.0.1:${Number(port)}/json/list`);
      const list = await res.json();
      target = list.find(t => t.type === 'page');
      if (target && target.webSocketDebuggerUrl) break;
    } catch (e) {}
    await new Promise(r => setTimeout(r, 100));
  }

  if (!target || !target.webSocketDebuggerUrl) {
    proc.kill();
    throw new Error(`Could not connect to Chrome after 30s. Stderr: ${stderr}`);
  }

  const page = new CDPPage(target.webSocketDebuggerUrl);
  owned.page = page;
  await page.send('Page.enable');
  await page.send('Runtime.enable');
  return { proc, page };
}

async function freePort() {
  const server = createServer();
  await new Promise((resolve, reject) => server.once('error', reject).listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return port;
}
const dir = await mkdtemp(join(tmpdir(), 'settletable-conflict-'));
const procs = [];
let server, a, b, c;
const ev=(p,s)=>p.evaluate(s); const wait=(p,s)=>p.waitFor(s,15000);
try {
 const port = await freePort();
 const origin = `http://127.0.0.1:${port}`;
 const nonce = randomBytes(32).toString('hex');
 server = spawn(resolvePythonPath(), [join(REPO_ROOT, 'tools/verify_conflict_recovery_runner.py'), '--port', String(port), '--db', join(dir, 'test.sqlite'), '--mock-notion', '--mock-ocr'], { cwd: REPO_ROOT, env: {...process.env, SETTLETABLE_TEST_NONCE: nonce} });
 let serverError = null; server.on('error', err => { serverError = err; });
 server.stdout?.resume(); server.stderr?.resume();
 const launch = async label => {
   const browser = await startChrome(resolveChromePath(), join(dir, label), procs);
   return browser.page;
 };
 let ready = false;
 for (let i = 0; i < 100; i++) {
   if (serverError) throw serverError;
   if (server.exitCode !== null) throw Error('Owned test server exited before readiness');
   try {
     const response = await fetch(`${origin}/__conflict_test_ready/${nonce}`);
     if (response.ok && await response.text() === 'owned-test-server') { ready = true; break; }
   } catch {}
   await new Promise(r => setTimeout(r, 100));
 }
 if (!ready) throw Error('Owned test server failed readiness handshake');
 a = await launch('organizer'); b = await launch('bob'); c = await launch('charlie');
 let mutations = 0; await a.send('Emulation.setDeviceMetricsOverride', {width: 375, height: 667, deviceScaleFactor: 1, mobile: true}); await a.send('Network.enable'); const originalHandler = a.ws.onmessage; a.ws.onmessage = event => { const msg = JSON.parse(event.data); if (msg.method === 'Network.requestWillBeSent' && msg.params.request.method === 'POST' && msg.params.request.url.endsWith('/apply')) mutations++; originalHandler(event); }; await a.navigate(origin+'/'); await wait(a,"document.getElementById('create-meal-form')");
 await ev(a,`document.getElementById('create-meal-id').value='recovery-test';document.getElementById('create-org-name').value='Organizer';document.getElementById('create-diners').value='Bob, Charlie';document.getElementById('create-meal-form').requestSubmit()`);
 await wait(a,"state.mealId==='recovery-test' && document.getElementById('add-item-form')");
 await ev(a,`document.getElementById('new-item-label').value='Shared Noodles';document.getElementById('new-item-qty').value='3';document.getElementById('new-item-price').value='30.00';document.getElementById('add-item-form').requestSubmit()`); await wait(a,"state.snapshot.receipt.items.length===1");
 await ev(a, `(async()=>{const snap=state.snapshot; const receipt={...snap.receipt,total_sen:3100,adjustments:[{id:'fee',label:'Service',kind:'service',amount_sen:100,eligible_item_ids:['item-1'],scope_mode:'all_items',rationale:'Printed service'}]}; await apiCall("/api/meals/"+snap.meal_id+"/apply",'POST',{kind:'ReplaceReceipt',command_id:'seed-fee',expected_revision:snap.revision,expected_financial_revision:snap.financial_revision,receipt}); await fetchSnapshot(true);})()`);
 await ev(a,`document.querySelector('.issue-invite-btn[data-id="D1"]').click()`);await wait(a,"state.issuedTokens.D1");let invite=await ev(a,'state.issuedTokens.D1');
 await b.navigate(invite);await wait(b,"document.getElementById('redeem-btn')");await ev(b,"document.getElementById('redeem-btn').click()");await wait(b,"state.currentUserId==='D1' && document.querySelector('.claim-inc-btn')");console.log('PERSONAL REDEEM OK');
 await c.navigate(origin+'/join/recovery-test');await wait(c,"document.getElementById('join-name-input')");await ev(c,`document.getElementById('join-name-input').value='Charlie';document.getElementById('submit-join-req-btn').click()`);await wait(c,"document.body.innerText.includes('Join Request Submitted')");await wait(a,"document.querySelector('.approve-join-req-btn')");await ev(a,"document.querySelector('.approve-join-req-btn').click()");await wait(c,"state.currentUserId==='D2' && document.querySelector('.claim-inc-btn')");console.log('GENERAL APPROVAL OK');
 // Force the same timestamp in two isolated identities and capture the actual
 // accepted self-claim command IDs. These actions are sequential only so each
 // uses the current item revision; the clock deliberately remains identical.
 for (const page of [b, c]) await ev(page, `window.savedNow=Date.now; Date.now=()=>1700000000000; window.savedClaimFetch=window.fetch; window.fetch=(...args)=>{if(args[1]?.method==='POST' && args[0].endsWith('/apply')) {const payload=JSON.parse(args[1].body); if(payload.kind==='SetOwnQuantity') window.claimCommandId=payload.command_id;} return window.savedClaimFetch(...args);}`);
 await ev(b,`document.querySelector('.claim-inc-btn[data-id="item-1"]').click()`);await wait(b,"state.snapshot.claims.some(c=>c.participant_id==='D1')");
 await ev(a,'fetchSnapshot(true)');await wait(a,"state.snapshot.claims.some(c=>c.participant_id==='D1')"); console.log('ORG BEFORE',JSON.stringify(await ev(a,'state.snapshot.claims')));
 await ev(c,'fetchSnapshot(true)'); await wait(c,"state.snapshot.claims.some(c=>c.participant_id==='D1')"); await a.send('Network.setBlockedURLs',{urls:[origin+'/api/meals/recovery-test/snapshot*']});
 await ev(c,`document.querySelector('.claim-inc-btn[data-id="item-1"]').click()`);await wait(c,"state.snapshot.claims.some(c=>c.participant_id==='D2')");
 const bobCommand = await ev(b, 'window.claimCommandId'); const charlieCommand = await ev(c, 'window.claimCommandId');
 if (!bobCommand || !charlieCommand || bobCommand === charlieCommand || bobCommand.length > 64 || charlieCommand.length > 64) throw Error('Same-time diner command IDs were missing, duplicate or too long');
 if (!(await ev(c, "state.snapshot.claims.some(c=>c.participant_id==='D1') && state.snapshot.claims.some(c=>c.participant_id==='D2')"))) throw Error('Both same-time diner claims did not persist');
 for (const page of [b, c]) await ev(page, 'Date.now=window.savedNow; window.fetch=window.savedClaimFetch');
 console.log('SAME-TIMESTAMP DISTINCT DINER COMMANDS OK');
 console.log('STALE ORG',JSON.stringify(await ev(a,'state.snapshot.claims')));console.log('DINER NEW',JSON.stringify(await ev(c,'state.snapshot.claims')));
 await ev(a, `document.querySelector('details[data-service-scope]').open=true; document.querySelector('.service-scope-item').checked=false`); await ev(a,`document.querySelector('[data-action="hybrid-toggle-details"][data-item="item-1"]').click()`); await wait(a, `document.getElementById('hybrid-bottom-sheet')`); await ev(a, `document.querySelector('[data-action="toggle-split-diner"][data-target="D1"]').click()`); await ev(a,`document.getElementById('new-item-label').value='Unsaved draft'; document.querySelector('[data-action="hybrid-step"][data-item="item-1"][data-target="O"][data-step="1"]').click()`); await wait(a,"document.querySelector('.alert-message')?.textContent.includes('Refresh failed')"); if (mutations !== 3) throw Error(`Expected one stale allocation POST after receipt setup, got ${mutations}`); await ev(a, `document.querySelector('[data-action="hybrid-step"][data-target="O"][data-step="1"]').click()`); if (mutations !== 3) throw Error('Stale allocation sent while refresh pending'); if (!(await ev(a, `document.querySelector('.alert-message').textContent.includes('Refresh failed')`))) throw Error('Blocked refresh incorrectly reported as successful'); console.log('BLOCKED REFRESH STATUS OK');
 if (!(await ev(a, `document.querySelector('.alert-message').textContent.includes('close Details / Split')`))) throw Error('Missing modal retry instructions'); await ev(a, `document.querySelector('.bottom-sheet-close-btn').click()`); await a.send('Network.setBlockedURLs',{urls:[]}); await ev(a,"document.getElementById('manual-refresh-btn').click()");await wait(a,"state.snapshot.claims.some(c=>c.participant_id==='D2') && document.querySelector('.alert-message')?.textContent.includes('Latest state reloaded')"); if (await ev(a, `document.getElementById('new-item-label').value`) !== 'Unsaved draft') throw Error('Draft lost during refresh'); if (await ev(a, `state.selectedSplitDiners.get('item-1').has('D1')`)) throw Error('Split selection lost'); if (!(await ev(a, `document.querySelector('details[data-service-scope]').open && !document.querySelector('.service-scope-item').checked`))) throw Error('Unsaved service scope selection lost'); await ev(a, 'updateMealUI()'); if (await ev(a, `document.getElementById('new-item-label').value`) !== 'Unsaved draft') throw Error('Draft lost on subsequent redraw'); if (mutations !== 3) throw Error('Refresh issued another mutation'); console.log('REFRESHED',JSON.stringify(await ev(a,'state.snapshot.claims')));
 // A separate real conflict with the network available must confirm automatic refresh.
 await ev(a,'stopPolling()'); await ev(b,'fetchSnapshot(true)'); await ev(b,`document.querySelector('.claim-dec-btn[data-id="item-1"]').click()`); await wait(b,"!state.snapshot.claims.some(c=>c.participant_id==='D1')");
 await ev(a, `window.baseRaceFetch=window.fetch; window.raceCount=0; window.fetch=async (...args)=>{if(args[0].includes('/snapshot')){const n=++window.raceCount; await new Promise(resolve=>window['releaseRace'+n]=resolve); if(n===1) throw Error('blocked stale refresh');} return window.baseRaceFetch(...args)}; document.querySelector('[data-action="hybrid-quick-assign"][data-item="item-1"][data-target="O"]').click()`);
 await wait(a, `window.releaseRace1`); await ev(a, `void fetchSnapshot(true)`); await wait(a, `window.releaseRace2`); await ev(a, `window.releaseRace1()`);
 await ev(a, `new Promise(resolve=>setTimeout(resolve,100))`);
 if (await ev(a, `document.querySelector('.alert-message').textContent.includes('Refresh failed')`)) throw Error('Superseded failed request claimed latest refresh failed');
 await ev(a, `window.releaseRace2()`); await wait(a,"document.querySelector('.alert-message')?.textContent.includes('Latest state reloaded') && !state.snapshot.claims.some(c=>c.participant_id==='D1')"); await ev(a, `window.fetch=window.baseRaceFetch`); if (mutations !== 4) throw Error('Automatic recovery issued another mutation'); if (await ev(a, `document.getElementById('new-item-label').value`) !== 'Unsaved draft') throw Error('Draft lost during automatic recovery');
 await ev(a,`document.querySelector('[data-action="hybrid-quick-assign"][data-item="item-1"][data-target="O"]').click()`); await wait(a,"state.snapshot.claims.length===2");console.log('RECOVERED',JSON.stringify(await ev(a,'state.snapshot.claims')));
 await a.reload(); await wait(a, "Boolean(typeof state !== 'undefined' && state?.snapshot?.claims?.length === 2 && document.getElementById('add-item-form'))"); console.log('RELOAD',JSON.stringify(await ev(a,'state.snapshot.claims')));
 // Preserve a draft entered before opening the sheet, and handle a form redraw
 // while an accepted Add Item response is delayed.
 await ev(a, `document.getElementById('new-item-label').value='Delayed item'; document.getElementById('new-item-price').value='2.00'; document.querySelector('[data-action="hybrid-toggle-details"][data-item="item-1"]').click()`);
 if (await ev(a, `document.getElementById('new-item-label').value`) !== 'Delayed item') throw Error('Opening sheet lost draft');
 await ev(a, `document.querySelector('.bottom-sheet-close-btn').click()`);
 await ev(a, `window.originalTestFetch=window.fetch; window.fetch=async (...args)=>{ const response=await window.originalTestFetch(...args); if(args[1]?.method==='POST' && args[0].endsWith('/apply')) await new Promise(resolve=>window.releaseTestResponse=resolve); return response; }; document.getElementById('add-item-form').requestSubmit()`);
 await wait(a, `window.releaseTestResponse`);
 await ev(a, `document.querySelector('[data-action="hybrid-toggle-details"][data-item="item-1"]').click(); window.releaseTestResponse();`);
 await wait(a, `state.snapshot.receipt.items.length===2`);
 if (await ev(a, `document.getElementById('new-item-label').value`) !== '') throw Error('Submitted draft remained after response and redraw');
 await ev(a, `document.querySelector('.bottom-sheet-close-btn').click(); window.releaseTestResponse=null; document.getElementById('new-item-label').value='Another item'; document.getElementById('new-item-price').value='3.00'; document.getElementById('add-item-form').requestSubmit()`);
 await wait(a, `window.releaseTestResponse`);
 await ev(a, `document.querySelector('[data-action="hybrid-toggle-details"][data-item="item-1"]').click(); document.getElementById('new-item-label').value='Next unsaved item'; window.releaseTestResponse();`);
 await wait(a, `state.snapshot.receipt.items.length===3`);
 if (await ev(a, `document.getElementById('new-item-label').value`) !== 'Next unsaved item') throw Error('New edits were cleared after delayed response'); await ev(a, 'window.fetch=window.originalTestFetch');
 await ev(a, `document.querySelector('.bottom-sheet-close-btn').click(); const details=document.querySelector('details[data-service-scope]'); details.open=true; for(const input of details.querySelectorAll('.service-scope-item')) input.checked=input.defaultChecked;`);
 await ev(a, `(async()=>{const snap=state.snapshot; const adjustments=snap.receipt.adjustments.map(a=>a.id==='fee'?{...a,scope_mode:'fixed_items',eligible_item_ids:['item-1']}:a); await apiCall('/api/meals/'+snap.meal_id+'/apply','POST',{kind:'ReplaceReceipt',command_id:'scope-external-test',expected_revision:snap.revision,expected_financial_revision:snap.financial_revision,receipt:{...snap.receipt,adjustments}}); await fetchSnapshot(true);})()`);
 if (!(await ev(a, `document.querySelector('details[data-service-scope]').open && ![...document.querySelectorAll('.service-scope-item')].find(el=>el.value===state.snapshot.receipt.items.find(i=>i.label==='Delayed item').id).checked`))) throw Error('Pristine scope editor hid authoritative change');
 console.log('PRISTINE SCOPE REFRESH OK');
 await ev(a, `document.querySelector('.service-scope-item[value="item-1"]').checked=false`);
 await ev(a, `(async()=>{const snap=state.snapshot; const adjustments=snap.receipt.adjustments.map(a=>a.id==='fee'?{...a,scope_mode:'all_items',eligible_item_ids:snap.receipt.items.map(i=>i.id)}:a); await apiCall('/api/meals/'+snap.meal_id+'/apply','POST',{kind:'ReplaceReceipt',command_id:'scope-external-2',expected_revision:snap.revision,expected_financial_revision:snap.financial_revision,receipt:{...snap.receipt,adjustments}}); await fetchSnapshot(true);})()`);
 if (!(await ev(a, `!document.querySelector('.service-scope-item[value="item-1"]').checked && document.querySelector('.scope-draft-warning')`))) throw Error('Dirty scope draft was not retained and warned');
 await ev(a, 'updateMealUI()');
 if (!(await ev(a, `document.querySelector('.scope-draft-warning')`))) throw Error('Scope warning disappeared while draft remained');
 console.log('DIRTY SCOPE WARNING OK');

 console.log('DELAYED ADD ITEM AND NEW EDITS OK');

} catch(e){console.error('FAIL',e);try{console.log('PAGE',await ev(a,'document.body.innerText'));}catch(_){} process.exitCode=1;} finally {
  const children = [...procs.map(x => x.proc), ...(server ? [server] : [])];
  for (const x of procs) x.page?.close();
  await Promise.all(children.map(child => new Promise(resolve => {
    if (child.exitCode !== null || child.signalCode !== null || !child.pid) return resolve();
    child.once('exit', resolve);
    child.kill();
    setTimeout(resolve, 3000).unref();
  })));
  await rm(dir, {recursive:true, force:true, maxRetries:5, retryDelay:200}).catch(() => {});
}
