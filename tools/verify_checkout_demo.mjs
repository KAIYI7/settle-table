/**
 * Experimental checkout demo (synthetic) browser regression using Chrome DevTools Protocol (CDP).
 * Runs SettleTable with the feature enabled against an in-process stub bridge that follows
 * the KP-SETTLETABLE-TNG-01 v2.1 wire contract. Helpers mirror verify_conflict_recovery.mjs.
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

// --- Experimental checkout demo (synthetic) browser regression ---
// Control, polling schedule, display mapping, stale and no-repeat rules, and
// financial invariance, against the in-process stub bridge.
const assert = (cond, message) => { if (!cond) throw new Error(message); };
const dir = await mkdtemp(join(tmpdir(), 'settletable-checkout-demo-'));
const procs = [];
let server, a, b;
const ev = (p, s) => p.evaluate(s);
const wait = (p, s, ms = 15000) => p.waitFor(s, ms);
try {
  const port = await freePort();
  const origin = `http://127.0.0.1:${port}`;
  const nonce = randomBytes(32).toString('hex');
  server = spawn(resolvePythonPath(), [join(REPO_ROOT, 'tools/verify_checkout_demo_runner.py'), '--port', String(port),
    '--db', join(dir, 'test.sqlite'), '--mock-notion', '--mock-ocr'],
    { cwd: REPO_ROOT, env: { ...process.env, SETTLETABLE_TEST_NONCE: nonce } });
  let serverError = null;
  server.on('error', err => { serverError = err; });
  server.stdout?.resume(); server.stderr?.resume();
  let stubPort = null;
  for (let i = 0; i < 150 && !stubPort; i++) {
    if (serverError) throw serverError;
    if (server.exitCode !== null) throw Error('Owned test server exited before readiness');
    try {
      const response = await fetch(`${origin}/__checkout_demo_ready/${nonce}`);
      const text = response.ok ? await response.text() : '';
      if (text.startsWith('owned-test-server:')) stubPort = Number(text.split(':')[1]);
    } catch {}
    if (!stubPort) await new Promise(r => setTimeout(r, 100));
  }
  assert(stubPort, 'Owned test server failed readiness handshake');
  const control = async (action, method = 'POST') => {
    const response = await fetch(`http://127.0.0.1:${stubPort}/__control/${nonce}/${action}`, { method });
    assert(response.ok, `Stub control ${action} failed: ${response.status}`);
    return response.json();
  };
  const bridgeCalls = async () => (await control('state', 'GET')).calls;

  a = (await startChrome(resolveChromePath(), join(dir, 'organizer'), procs)).page;
  // Record every request path and keep the snapshot poll under observation.
  await a.send('Network.enable');
  const demoRequests = [];
  const originalHandler = a.ws.onmessage;
  a.ws.onmessage = event => {
    const msg = JSON.parse(event.data);
    if (msg.method === 'Network.requestWillBeSent' && msg.params.request.url.includes('/checkout-demo')) {
      demoRequests.push({ method: msg.params.request.method, at: Date.now() });
    }
    originalHandler(event);
  };
  await a.send('Emulation.setDeviceMetricsOverride', { width: 375, height: 740, deviceScaleFactor: 1, mobile: true });

  console.log('[1/7] Creating, finalizing and funding a synthetic meal...');
  await a.navigate(origin + '/');
  await wait(a, "document.getElementById('create-meal-form')");
  await ev(a, `document.getElementById('create-meal-id').value='demo-meal';document.getElementById('create-org-name').value='Organizer';document.getElementById('create-diners').value='Demo Diner, Other Diner';document.getElementById('create-meal-form').requestSubmit()`);
  await wait(a, "state.mealId==='demo-meal' && document.getElementById('add-item-form')");
  await ev(a, `(async()=>{
    const mid='demo-meal'; const apply=body=>apiCall('/api/meals/'+mid+'/apply','POST',body);
    let s=state.snapshot;
    await apply({kind:'ReplaceReceipt',command_id:'rcpt',expected_revision:s.revision,expected_financial_revision:s.financial_revision,
      receipt:{items:[{id:'item-a',label:'Organizer dish',quantity:[1,1],line_sen:1000},{id:'item-b',label:'Diner dish',quantity:[1,1],line_sen:863},
      {id:'item-c',label:'Other dish',quantity:[1,1],line_sen:500}],adjustments:[],subtotal_sen:2363,total_sen:2363,included_tax_sen:0}});
    await fetchSnapshot(true);
    const ids=state.snapshot.participants; const org=ids.find(p=>p.organizer).id;
    const diner=ids.find(p=>p.name==='Demo Diner').id; const other=ids.find(p=>p.name==='Other Diner').id;
    for (const [item, who] of [['item-a',org],['item-b',diner],['item-c',other]]) {
      s=state.snapshot;
      await apply({kind:'AssignParticipantQuantity',command_id:'assign-'+item,participant_id:who,item_id:item,quantity:1,
        expected_item_revision:s.items.find(i=>i.item_id===item).item_revision,expected_financial_revision:s.financial_revision});
      await fetchSnapshot(true);
    }
    s=state.snapshot; await apply({kind:'ReviewReceipt',command_id:'review',expected_revision:s.revision,expected_financial_revision:s.financial_revision,receipt_digest:s.receipt_digest});
    await fetchSnapshot(true);
    s=state.snapshot; await apply({kind:'Finalize',command_id:'final',expected_revision:s.revision,expected_financial_revision:s.financial_revision});
    await fetchSnapshot(true);
    window.demoIds={org,diner,other};
  })()`);
  // Pin the order that hosted CI hit: the read started by the Finalize transition
  // completes before any contribution exists, so it lists no eligible suggestion.
  await wait(a, "state.checkoutDemo && !state.checkoutDemoBusy && state.checkoutDemo.eligible.length===0");
  await ev(a, `(async()=>{
    const s=state.snapshot;
    await apiCall('/api/meals/demo-meal/apply','POST',{kind:'RecordContribution',command_id:'pay',expected_revision:s.revision,participant_id:window.demoIds.org,amount_sen:2363,payment_method:'card'});
    await fetchSnapshot(true);
  })()`);
  // The contribution changes the suggestions, so the card must re-read on its own.
  await wait(a, "document.getElementById('checkout-demo-card') && document.querySelectorAll('[data-checkout-demo-action=\"request\"]').length===2");
  const ids = await ev(a, 'window.demoIds');
  const cardText = await ev(a, "document.getElementById('checkout-demo-card').innerText");
  assert(cardText.includes('Experimental checkout demo (synthetic)'), 'Card title missing');
  const checkCopy = async label => {
    const text = await ev(a, "document.getElementById('checkout-demo-card').innerText");
    for (const banned of ['TNG', 'KaiPay', 'paid', 'settled', 'Settled']) {
      assert(!text.includes(banned), `Card copy (${label}) must not say "${banned}": ${text}`);
    }
  };
  await checkCopy('initial');
  assert((await bridgeCalls()).length === 0, 'Loading the card before any intent must not call the bridge');
  const financialBefore = await ev(a, "JSON.stringify({s:state.snapshot.settlement,f:state.snapshot.funding,t:state.snapshot.transfers,c:state.snapshot.contributions,p:state.snapshot.pending_transfers})");
  const buttonBox = await ev(a, "(()=>{const r=document.querySelector('[data-checkout-demo-action=\"request\"]').getBoundingClientRect();return {w:r.width,h:r.height}})()");
  assert(buttonBox.h >= 44 && buttonBox.w >= 44, `Request button below 44px touch target: ${JSON.stringify(buttonBox)}`);
  assert(await ev(a, 'document.documentElement.scrollWidth <= window.innerWidth'), 'Checkout demo card causes horizontal scroll');
  console.log('   ✓ Organizer sees two eligible suggestions, honest copy, no bridge call yet');

  console.log('[2/7] Diner never sees the control...');
  const invite = await ev(a, `(async()=>{const r=await apiCall('/api/meals/demo-meal/invitations','POST',{participant_id:'${ids.diner}',invite_ttl:86400}); return r.invite_url || (location.origin+'/#/invite/'+r.token);})()`);
  {
    b = (await startChrome(resolveChromePath(), join(dir, 'diner'), procs)).page;
    await b.navigate(invite);
    await wait(b, "document.getElementById('redeem-btn')");
    await ev(b, "document.getElementById('redeem-btn').click()");
    await wait(b, "state.currentUserId && document.getElementById('peer-settlement-card')");
    assert(!(await ev(b, "Boolean(document.getElementById('checkout-demo-card'))")), 'Diner must not see the demo control');
    assert(await ev(b, 'state.snapshot.checkout_demo_enabled === false'), 'Diner snapshot flag must be false');
    const dinerStatus = await ev(b, "fetch('/api/meals/demo-meal/checkout-demo').then(r=>r.status)");
    assert(dinerStatus === 403, `Diner status read must be forbidden, got ${dinerStatus}`);
    console.log('   ✓ Diner has no control and is refused by the status endpoint');
  }

  console.log('[3/7] Requesting the demo checkout and following the I06 polling schedule...');
  demoRequests.length = 0;
  const clickedAt = Date.now();
  await ev(a, `document.querySelector('[data-checkout-demo-action="request"][data-sender-id="${ids.diner}"]').click()`);
  await wait(a, "document.getElementById('checkout-demo-status')?.textContent.includes('Awaiting synthetic evidence')");
  let calls = await bridgeCalls();
  assert(calls.length === 1 && calls[0][0] === 'PUT', `Expected exactly one PUT, got ${JSON.stringify(calls)}`);
  assert(await ev(a, "document.querySelectorAll('[data-checkout-demo-action=\"request\"]').length===0"), 'No new request while one is open');
  await wait(a, `state.checkoutDemoTimers.length===7`, 3000);
  await control('candidate');
  await wait(a, "document.getElementById('checkout-demo-status')?.textContent.includes('Synthetic evidence detected')", 6000);
  const firstPoll = demoRequests.find(r => r.method === 'GET');
  assert(firstPoll && firstPoll.at - clickedAt >= 1500, 'First poll must follow the 2 s step, not the 3 s snapshot loop');
  await control('confirm');
  await wait(a, "document.getElementById('checkout-demo-status')?.textContent.includes('Organizer marked the synthetic demo checkout confirmed')", 8000);
  const confirmedText = await ev(a, "document.getElementById('checkout-demo-status').textContent");
  assert(confirmedText.includes('no money moved; balance unchanged'), `Confirmed copy wrong: ${confirmedText}`);
  await checkCopy('confirmed');
  await wait(a, 'state.checkoutDemoTimers.length===0', 3000);
  const getsAtConfirm = demoRequests.filter(r => r.method === 'GET').length;
  await new Promise(r => setTimeout(r, 7000));  // Snapshot poll keeps running; demo polling has stopped.
  assert(demoRequests.filter(r => r.method === 'GET').length === getsAtConfirm, 'Polling continued after a terminal state');
  console.log('   ✓ One PUT, schedule-driven GETs, polling stopped at the terminal state');

  console.log('[4/7] Financial state is unchanged and the debt is not repeatable...');
  const financialAfter = await ev(a, "fetchSnapshot(true).then(()=>JSON.stringify({s:state.snapshot.settlement,f:state.snapshot.funding,t:state.snapshot.transfers,c:state.snapshot.contributions,p:state.snapshot.pending_transfers}))");
  assert(financialAfter === financialBefore, 'Settlement, funding or transfers changed');
  assert(await ev(a, `![...document.querySelectorAll('[data-checkout-demo-action="request"]')].some(b=>b.dataset.senderId==='${ids.diner}')`),
    'Confirmed suggestion must not be requestable again');
  assert(await ev(a, `[...document.querySelectorAll('[data-checkout-demo-action="request"]')].some(b=>b.dataset.senderId==='${ids.other}')`),
    'Other suggestion should be requestable');
  const repeat = await ev(a, `fetch('/api/meals/demo-meal/checkout-demo',{method:'POST',headers:{'Content-Type':'application/json','X-SettleTable-Action':'1'},body:JSON.stringify({sender_id:'${ids.diner}',amount_sen:863})}).then(async r=>[r.status,(await r.json()).error])`);
  assert(repeat[0] === 409 && repeat[1] === 'checkout_demo_already_confirmed', `Repeat after confirm not refused: ${repeat}`);
  console.log('   ✓ Settlement bytes unchanged; repeat refused');

  console.log('[5/7] Stale suggestion is shown and refused...');
  await ev(a, `document.querySelector('[data-checkout-demo-action="request"][data-sender-id="${ids.other}"]').click()`);
  await wait(a, "document.getElementById('checkout-demo-status')?.textContent.includes('Awaiting synthetic evidence') && state.checkoutDemo.intent.attempt===2");
  // A status read is answered before the transfer but delivered after it. Scheduled reads are
  // cleared so only the deferred re-read can reveal the stale state.
  // Clearing the timers and checking for idle in one evaluation means no scheduled read can start after it.
  await wait(a, '(()=>{ clearCheckoutDemoTimers(); return !state.checkoutDemoBusy; })()');
  const seqBeforeHeld = await ev(a, 'state.checkoutDemoSeq');
  await ev(a, `(()=>{
    let release; const held = new Promise(r => { release = r; });
    window.__demoHold = { held, release };
    const original = window.fetch;
    window.fetch = async (url, opts = {}) => {
      const response = await original(url, opts);
      if (window.__demoHold && String(url).includes('/checkout-demo') && (opts.method || 'GET') === 'GET') await window.__demoHold.held;
      return response;
    };
    window.__restoreFetch = () => { window.fetch = original; };
    void requestCheckoutDemo(null, false);
  })()`);
  assert(await ev(a, `state.checkoutDemoBusy && state.checkoutDemoSeq===${seqBeforeHeld}+1`), 'The held status read did not start');
  await ev(a, `(async()=>{const s=state.snapshot; await apiCall('/api/meals/demo-meal/apply','POST',{kind:'RecordTransfer',command_id:'partial',expected_revision:s.revision,sender_id:'${ids.other}',receiver_id:'${ids.org}',amount_sen:100}); await fetchSnapshot(true);})()`);
  assert(await ev(a, 'state.checkoutDemoBusy && Boolean(state.checkoutDemoRereadPending)'), 'A suggestion change during a read must queue a re-read');
  await ev(a, 'window.__demoHold.release(); window.__demoHold = null; window.__restoreFetch()');
  await wait(a, "document.getElementById('checkout-demo-stale')", 5000);
  await checkCopy('stale');
  const putsBefore = (await bridgeCalls()).filter(c => c[0] === 'PUT').length;
  const stale = await ev(a, `fetch('/api/meals/demo-meal/checkout-demo',{method:'POST',headers:{'Content-Type':'application/json','X-SettleTable-Action':'1'},body:JSON.stringify({sender_id:'${ids.other}',amount_sen:500})}).then(async r=>[r.status,(await r.json()).error])`);
  assert(stale[0] === 409 && stale[1] === 'checkout_demo_stale', `Stale request not refused: ${stale}`);
  assert((await bridgeCalls()).filter(c => c[0] === 'PUT').length === putsBefore, 'A PUT was sent for a stale suggestion');
  console.log('   ✓ Stale badge shown and no PUT sent');

  console.log('[6/7] Expiry offers a new attempt for the current suggestion...');
  await control('expire');
  await ev(a, "document.getElementById('checkout-demo-refresh-btn').click()");
  await wait(a, "document.getElementById('checkout-demo-status')?.textContent.includes('Expired — you may request again')");
  await wait(a, `[...document.querySelectorAll('[data-checkout-demo-action="request"]')].some(b=>b.dataset.senderId==='${ids.other}' && b.dataset.amountSen==='400')`);
  await checkCopy('expired');
  console.log('   ✓ Expired state offers the recomputed RM4.00 suggestion');

  console.log('[7/7] Hidden page pauses demo polling...');
  await ev(a, `document.querySelector('[data-checkout-demo-action="request"][data-sender-id="${ids.other}"]').click()`);
  await wait(a, "state.checkoutDemo?.intent?.attempt===3 && state.checkoutDemoTimers.length===7");
  await a.send('Emulation.setFocusEmulationEnabled', { enabled: false }).catch(() => {});
  await ev(a, "Object.defineProperty(document,'visibilityState',{configurable:true,get:()=> 'hidden'}); document.dispatchEvent(new Event('visibilitychange'))");
  assert(await ev(a, 'state.checkoutDemoTimers.length===0'), 'Hidden page kept demo timers');
  // A suggestion change seen while hidden is kept, not dropped, and read once when visible.
  await wait(a, '!state.checkoutDemoBusy');
  const seqHidden = await ev(a, 'loadCheckoutDemo(state.snapshot, false); state.checkoutDemoSeq');
  assert(await ev(a, `Boolean(state.checkoutDemoRereadPending) && state.checkoutDemoSeq===${seqHidden}`), 'Hidden page must queue, not send, a re-read');
  await ev(a, "Object.defineProperty(document,'visibilityState',{configurable:true,get:()=> 'visible'}); document.dispatchEvent(new Event('visibilitychange'))");
  assert(await ev(a, 'state.checkoutDemoTimers.length===7'), 'Visible page did not resume demo polling');
  assert(await ev(a, `state.checkoutDemoRereadPending===null && state.checkoutDemoSeq===${seqHidden}+1`), 'Visible page did not send the queued re-read');
  console.log('   ✓ Polling pauses while hidden and resumes when visible');
  console.log('CHECKOUT DEMO BROWSER REGRESSION OK');
} catch (e) {
  console.error('FAIL', e);
  try { console.log('PAGE', await ev(a, "document.getElementById('checkout-demo-card')?.innerText || document.body.innerText")); } catch (_) {}
  process.exitCode = 1;
} finally {
  const children = [...procs.map(x => x.proc), ...(server ? [server] : [])];
  for (const x of procs) x.page?.close();
  await Promise.all(children.map(child => new Promise(resolve => {
    if (child.exitCode !== null || child.signalCode !== null || !child.pid) return resolve();
    child.once('exit', resolve);
    child.kill();
    setTimeout(resolve, 3000).unref();
  })));
  await rm(dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }).catch(() => {});
}
