/**
 * Experimental checkout demo, observed-evidence mode, browser regression using Chrome DevTools
 * Protocol (CDP). Runs SettleTable with SETTLETABLE_CHECKOUT_DEMO_OBSERVED_EVIDENCE=true against an
 * in-process stub bridge that follows the KP-SETTLETABLE-TNG-02 v1.3 observed wire contract
 * (pinned 1 sen, single use, evidenceMode key). No real bridge, phone or wallet is involved.
 * Helpers mirror verify_checkout_demo.mjs.
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


// --- Experimental checkout demo (observed notification) browser regression ---
// Observed card copy, word-for-word mapping, payer-identity line, no NEW or RETRY after the
// first PUT, latched refusals and mode mismatch, and financial invariance.
const assert = (cond, message) => { if (!cond) throw new Error(message); };
const dir = await mkdtemp(join(tmpdir(), 'settletable-checkout-observed-'));
const procs = [];
let server, a;
const ev = (p, s) => p.evaluate(s);
const wait = (p, s, ms = 15000) => p.waitFor(s, ms);
const OBS = {
  waiting: "Waiting for the organizer's own wallet notification. Nothing is recorded in SettleTable. Transfer at most once; if already sent, do not send again.",
  detected: 'Notification observed — unverified. The organizer checks their own wallet history in the bridge.',
  confirmed: 'Notification observed, unverified, manually confirmed by the organizer — SettleTable balance unchanged',
  review: 'Needs organizer review — not confirmed. Do not transfer again.',
  ended: 'Ended without confirmation. If money was sent, check your wallet history; do not transfer again.',
  refused: 'Not created — do not transfer',
  mismatch: 'Bridge mode does not match this SettleTable configuration — do not transfer',
  payer: "Test transfer between the organizer's own wallets; the named diner did not pay.",
};
const BANNED = [/paid/i, /settled/i, /payment verified/i, /payment confirmed/i, /confirm payment/i, /payment detected/i,
  /kaipay/i, /\bTNG\b/, /synthetic/i, /nonpayable/i];
const statusText = "document.getElementById('checkout-demo-status')?.textContent.trim()";
const statusIs = text => `${statusText} === ${JSON.stringify(text)}`;
const requestButtons = "document.querySelectorAll('[data-checkout-demo-action=\"request\"]').length";
const financial = "fetchSnapshot(true).then(()=>JSON.stringify({s:state.snapshot.settlement,f:state.snapshot.funding,t:state.snapshot.transfers,c:state.snapshot.contributions,p:state.snapshot.pending_transfers}))";
try {
  const port = await freePort();
  const origin = `http://127.0.0.1:${port}`;
  const nonce = randomBytes(32).toString('hex');
  server = spawn(resolvePythonPath(), [join(REPO_ROOT, 'tools/verify_checkout_demo_observed_runner.py'), '--port', String(port),
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
  const checkCopy = async (page, label) => {
    const text = await ev(page, "document.getElementById('checkout-demo-card').innerText");
    for (const banned of BANNED) assert(!banned.test(text), `Observed card copy (${label}) matches ${banned}: ${text}`);
    assert(text.includes(OBS.payer), `Observed card (${label}) lacks the payer-identity line: ${text}`);
    assert(text.includes('Experimental checkout demo (observed notification)'), `Observed title missing (${label})`);
  };

  // A fresh browser profile per meal: an organizer and the test counterparty share one RM0.02
  // item, and the organizer paid it, so the only suggestion is a one-sen transfer to the organizer.
  const openOneSenMeal = async mealId => {
    const page = (await startChrome(resolveChromePath(), join(dir, mealId), procs)).page;
    await page.send('Emulation.setDeviceMetricsOverride', { width: 375, height: 740, deviceScaleFactor: 1, mobile: true });
    await page.navigate(origin + '/');
    await wait(page, "document.getElementById('create-meal-form')");
    await ev(page, `document.getElementById('create-meal-id').value=${JSON.stringify(mealId)};document.getElementById('create-org-name').value='Organizer';document.getElementById('create-diners').value=${JSON.stringify("Owner's other wallet (test)")};document.getElementById('create-meal-form').requestSubmit()`);
    await wait(page, `state.mealId===${JSON.stringify(mealId)} && document.getElementById('add-item-form')`);
    await ev(page, `(async()=>{
      const mid=${JSON.stringify(mealId)}; const apply=body=>apiCall('/api/meals/'+mid+'/apply','POST',body);
      let s=state.snapshot;
      await apply({kind:'ReplaceReceipt',command_id:'rcpt',expected_revision:s.revision,expected_financial_revision:s.financial_revision,
        receipt:{items:[{id:'item-s',label:'Shared test item',quantity:[1,1],line_sen:2}],adjustments:[],subtotal_sen:2,total_sen:2,included_tax_sen:0}});
      await fetchSnapshot(true);
      const ids=state.snapshot.participants; const org=ids.find(p=>p.organizer).id; const diner=ids.find(p=>!p.organizer).id;
      for (const who of [org, diner]) {
        s=state.snapshot;
        await apply({kind:'AssignParticipantQuantity',command_id:'assign-'+who,participant_id:who,item_id:'item-s',quantity:[1,2],
          expected_item_revision:s.items.find(i=>i.item_id==='item-s').item_revision,expected_financial_revision:s.financial_revision});
        await fetchSnapshot(true);
      }
      s=state.snapshot; await apply({kind:'ReviewReceipt',command_id:'review',expected_revision:s.revision,expected_financial_revision:s.financial_revision,receipt_digest:s.receipt_digest});
      await fetchSnapshot(true);
      s=state.snapshot; await apply({kind:'Finalize',command_id:'final',expected_revision:s.revision,expected_financial_revision:s.financial_revision});
      await fetchSnapshot(true);
      window.demoIds={org,diner};
    })()`);
    // The card shows observed copy from the snapshot flag, before and after its first read.
    await wait(page, "document.getElementById('checkout-demo-card')?.dataset.checkoutDemoMode==='observed'");
    await wait(page, 'state.checkoutDemo && !state.checkoutDemoBusy && state.checkoutDemo.observed===true');
    await ev(page, `(async()=>{
      const s=state.snapshot;
      await apiCall('/api/meals/${mealId}/apply','POST',{kind:'RecordContribution',command_id:'pay',expected_revision:s.revision,participant_id:window.demoIds.org,amount_sen:2,payment_method:'card'});
      await fetchSnapshot(true);
    })()`);
    await wait(page, `${requestButtons}===1`);
    const suggestion = await ev(page, 'JSON.stringify(state.snapshot.settlement.suggested_transfers.map(t=>[t.sender_id===window.demoIds.diner,t.receiver_id===window.demoIds.org,t.amount_sen]))');
    assert(suggestion === '[[true,true,1]]', `Expected one one-sen suggestion to the organizer, got ${suggestion}`);
    const label = await ev(page, "document.querySelector('[data-checkout-demo-action=\"request\"]').textContent.trim()");
    assert(label === 'Request observed-notification checkout', `Request label wrong: ${label}`);
    await checkCopy(page, `${mealId} initial`);
    return page;
  };

  console.log('[1/5] One-sen meal shows the observed card before any request...');
  a = await openOneSenMeal('observed-meal');
  assert((await bridgeCalls()).length === 0, 'Loading the card before any intent must not call the bridge');
  const buttonBox = await ev(a, "(()=>{const r=document.querySelector('[data-checkout-demo-action=\"request\"]').getBoundingClientRect();return {w:r.width,h:r.height}})()");
  assert(buttonBox.h >= 44 && buttonBox.w >= 44, `Request button below 44px touch target: ${JSON.stringify(buttonBox)}`);
  assert(await ev(a, 'document.documentElement.scrollWidth <= window.innerWidth'), 'Observed card causes horizontal scroll');
  const financialBefore = await ev(a, financial);
  console.log('   ✓ Observed title, payer-identity line and one RM0.01 suggestion; no bridge call');

  console.log('[2/5] Request, observed notification and manual confirmation (word-for-word copy)...');
  await ev(a, "document.querySelector('[data-checkout-demo-action=\"request\"]').click()");
  await wait(a, statusIs(OBS.waiting));
  let calls = await bridgeCalls();
  assert(calls.length === 1 && calls[0][0] === 'PUT', `Expected exactly one PUT, got ${JSON.stringify(calls)}`);
  assert(await ev(a, `${requestButtons}===0`), 'No request may be offered while the checkout is open');
  await checkCopy(a, 'waiting');
  await control('notification');
  await wait(a, statusIs(OBS.detected), 8000);
  await checkCopy(a, 'detected');
  await control('confirm');
  await wait(a, statusIs(OBS.confirmed), 12000);
  await checkCopy(a, 'confirmed');
  await wait(a, 'state.checkoutDemoTimers.length===0', 3000);
  assert(await ev(a, `${requestButtons}===0 && state.checkoutDemo.eligible.length===0`), 'NEW must never be offered after the first PUT');
  assert(await ev(a, financial) === financialBefore, 'Settlement, funding or transfers changed');
  console.log('   ✓ Waiting → observed → manually confirmed; balance unchanged; no further request offered');

  console.log('[3/5] A second meal meets the spent store and latches "do not transfer"...');
  const b = await openOneSenMeal('spent-meal');
  const spentBefore = await ev(b, financial);
  await ev(b, "document.querySelector('[data-checkout-demo-action=\"request\"]').click()");
  await wait(b, statusIs(OBS.refused));
  assert(await ev(b, "state.checkoutDemo.intent.notCreatedReason==='OBSERVED_CHECKOUT_SPENT' && state.checkoutDemo.intent.latched"), 'Spent refusal not latched');
  assert(await ev(b, `${requestButtons}===0`), 'Neither NEW nor RETRY may follow an OBSERVED_* refusal');
  await checkCopy(b, 'refused');
  calls = await bridgeCalls();
  await ev(b, "document.getElementById('checkout-demo-refresh-btn').click()");
  await wait(b, `!state.checkoutDemoBusy && ${statusIs(OBS.refused)}`);
  assert((await bridgeCalls()).length === calls.length, 'A latched refusal must send no further bridge request');
  assert(await ev(b, financial) === spentBefore, 'A refusal changed financial state');
  console.log('   ✓ Not created — do not transfer; latched with no further bridge I/O');

  console.log('[4/5] A synthetic-mode bridge answer latches the mode mismatch...');
  const c = await openOneSenMeal('mismatch-meal');
  await control('synthetic-mode');
  await ev(c, "document.querySelector('[data-checkout-demo-action=\"request\"]').click()");
  await wait(c, statusIs(OBS.mismatch));
  assert(await ev(c, "state.checkoutDemo.intent.latched && state.checkoutDemo.intent.checkoutId===null"), 'Mismatch must latch without binding');
  assert(await ev(c, `${requestButtons}===0`), 'Nothing may be offered after a mode mismatch');
  await checkCopy(c, 'mismatch');
  calls = await bridgeCalls();
  await ev(c, "document.getElementById('checkout-demo-refresh-btn').click()");
  await wait(c, `!state.checkoutDemoBusy && ${statusIs(OBS.mismatch)}`);
  assert((await bridgeCalls()).length === calls.length, 'A latched mismatch must send no further bridge request');
  console.log('   ✓ Bridge mode does not match — do not transfer; latched');

  console.log('[5/5] Remaining observed states render the design copy and the RETRY rule...');
  await ev(c, 'clearCheckoutDemoTimers()');
  const base = await ev(c, 'JSON.stringify(state.checkoutDemo.intent)');
  const render = async (patch, eligible = [], lastCheck = null) => ev(c, `(()=>{
    state.checkoutDemo={...state.checkoutDemo, intent:{...${base}, ...${JSON.stringify(patch)}}, eligible:${JSON.stringify(eligible)}, lastCheck:${JSON.stringify(lastCheck)}};
    updateMealUI(); return ${statusText};
  })()`);
  const cases = [
    [{state: 'NEEDS_REVIEW', latched: false, terminal: false, notCreatedReason: null}, OBS.review],
    [{state: 'EXPIRED', latched: false, terminal: true, notCreatedReason: null}, OBS.ended],
    [{state: 'CONFLICT', latched: true, terminal: true, notCreatedReason: 'OBSERVED_AMOUNT_MISMATCH'}, OBS.refused],
    [{state: 'CONFLICT', latched: true, terminal: true, notCreatedReason: null}, 'Demo checkout conflict — automatic actions stopped. Do not transfer.'],
    [{state: 'UNEXPECTED_STATUS', latched: true, terminal: false, notCreatedReason: null}, 'Unexpected demo checkout status — automatic actions stopped. Do not transfer.'],
    [{state: 'REQUEST_UNKNOWN', latched: false, terminal: false, notCreatedReason: null}, 'Request outcome unknown — do not transfer. Refresh status before anything else.'],
    [{state: 'UNAVAILABLE', lastKnownState: 'AWAITING_EVIDENCE', latched: false, terminal: false, notCreatedReason: null, referenceLost: false},
      'Demo checkout status unavailable — refresh to check again. Do not send money while it is unavailable.'],
    [{state: 'NOT_CREATED', latched: false, terminal: true, notCreatedReason: 'SAME_AMOUNT_HELD', checkoutId: null}, 'Demo checkout was not created — do not transfer.'],
  ];
  for (const [patch, text] of cases) {
    const shown = await render(patch);
    assert(shown === text, `State ${JSON.stringify(patch)} shows "${shown}", expected "${text}"`);
    await checkCopy(c, patch.state);
  }
  await render({state: 'UNAVAILABLE', lastKnownState: 'AWAITING_EVIDENCE', latched: false, terminal: false, notCreatedReason: null, referenceLost: false});
  const unavailableNote = await ev(c, "document.getElementById('checkout-demo-card').innerText");
  assert(unavailableNote.includes('Last known: ' + OBS.waiting), 'Last-known note must use the observed copy');
  const ids = await ev(c, 'window.demoIds');
  const retry = await render({state: 'NOT_CREATED', latched: false, terminal: true, notCreatedReason: 'REFERENCE_NOT_FOUND', checkoutId: null},
    [{senderId: ids.diner, receiverId: ids.org, amountSen: 1, action: 'RETRY'}]);
  assert(retry === 'Demo checkout was not created — do not transfer. You may request the same checkout again.', `RETRY state copy wrong: ${retry}`);
  const retryLabel = await ev(c, "document.querySelector('[data-checkout-demo-action=\"request\"]').textContent.trim()");
  assert(retryLabel === 'Request the same checkout again', `RETRY label wrong: ${retryLabel}`);
  await checkCopy(c, 'retry');
  console.log('   ✓ Review, ended, refusals, conflict, unknown, unavailable, held and RETRY copy');
  console.log('CHECKOUT DEMO OBSERVED BROWSER REGRESSION OK');
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
