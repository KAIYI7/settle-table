/**
 * Experimental checkout demo, multi-diner observed mode, browser regression using Chrome DevTools
 * Protocol (CDP). Runs SettleTable with SETTLETABLE_CHECKOUT_DEMO_OBSERVED_EVIDENCE=true and
 * SETTLETABLE_CHECKOUT_DEMO_OBSERVED_MULTI=true against an in-process stub bridge that follows the
 * multi-checkout observed wire contract (three single-use checkouts, any amount, distinct held
 * amounts, evidenceMode key). No real bridge, phone or wallet is involved.
 * Helpers mirror verify_checkout_demo_observed.mjs.
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


// --- Experimental checkout demo (multi-diner observed notifications) browser regression ---
// One card per diner, distinct offset amounts with the share, offset and exact amount shown,
// the owner's notice and read-out hint word for word, one bridge GET per open checkout, plain
// refusal states, mobile layout and financial invariance.
const assert = (cond, message) => { if (!cond) throw new Error(message); };
const dir = await mkdtemp(join(tmpdir(), 'settletable-checkout-multi-'));
const procs = [];
let server, a;
const ev = (p, s) => p.evaluate(s);
const wait = (p, s, ms = 15000) => p.waitFor(s, ms);
const NOTICE = "The organizer's phone reads its own TNG payment notifications to update this status. TNG shows the organizer your name and amount. From the notification, SettleTable and the bridge keep only the amount, the time and technical IDs, never your name. The organizer checks TNG before marking you paid.";
const AMOUNT_LINE = 'A notification shows an amount and time only; it does not show that this diner paid.';
const hint = rm => `My phone reads my TNG payment alerts to update the bill. It keeps the amount and time, not your name. I still check TNG myself before marking you paid. Please pay exactly ${rm}.`;
const MULTI = {
  waiting: 'Waiting — no TNG payment notification has been matched to this checkout. Nothing is recorded in SettleTable.',
  detected: 'Notification observed — unverified. The organizer checks TNG before confirming in the bridge.',
  confirmed: 'Manually confirmed by the organizer — notification unverified',
  ambiguous: 'Ambiguous — not confirmed; notification unverified. The organizer checks TNG history; any reimbursement is recorded manually in SettleTable.',
  spent: 'Not created — the bridge has no observed checkouts left. No checkout exists for this diner.',
  noFree: 'No distinct amount within 9 sen of this share is free right now. It is offered again when a held amount frees up.',
  none: 'No checkout requested yet',
};
// Outside the owner's exact notice and hint, no copy may claim payment, settlement or verification.
const BANNED = [/paid/i, /settled/i, /payment verified/i, /payment confirmed/i, /confirm payment/i, /payment detected/i,
  /kaipay/i, /synthetic/i, /nonpayable/i, /own wallets/i];
const DINERS = ['Diner B', 'Diner C', 'Diner D', 'Diner E'];
const SHARES = {'Diner B': 863, 'Diner C': 863, 'Diner D': 500, 'Diner E': 700};
const card = name => `[...document.querySelectorAll('.checkout-demo-diner-card')].find(c => c.querySelector('.card-title').textContent.startsWith(${JSON.stringify(name)}))`;
const cardStatus = name => `${card(name)}?.querySelector('.checkout-demo-status')?.textContent.trim()`;
const cardIs = (name, text) => `${cardStatus(name)} === ${JSON.stringify(text)}`;
const cardButton = name => `${card(name)}?.querySelector('[data-checkout-demo-action="request"]')`;
const financial = "fetchSnapshot(true).then(()=>JSON.stringify({s:state.snapshot.settlement,f:state.snapshot.funding,t:state.snapshot.transfers,c:state.snapshot.contributions,p:state.snapshot.pending_transfers}))";
try {
  const port = await freePort();
  const origin = `http://127.0.0.1:${port}`;
  const nonce = randomBytes(32).toString('hex');
  server = spawn(resolvePythonPath(), [join(REPO_ROOT, 'tools/verify_checkout_demo_observed_multi_runner.py'), '--port', String(port),
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
  assert(stubPort !== 28082, 'The stub must never use the reserved bridge port');
  const control = async (action, body = null, method = 'POST') => {
    const response = await fetch(`http://127.0.0.1:${stubPort}/__control/${nonce}/${action}`,
      { method, ...(body ? { body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } } : {}) });
    assert(response.ok, `Stub control ${action} failed: ${response.status}`);
    return response.json();
  };
  const bridgeCalls = async () => (await control('state', null, 'GET')).calls;
  const puts = async () => (await control('state', null, 'GET')).checkouts.map(c => c.amountMinor);
  const checkCopy = async (page, label) => {
    let text = await ev(page, "[...document.querySelectorAll('.checkout-demo-card')].map(c => c.innerText).join('\\n')");
    for (const exact of [NOTICE, AMOUNT_LINE]) text = text.split(exact).join('');
    text = text.replace(/My phone reads my TNG payment alerts[^”]*/g, '');
    for (const banned of BANNED) assert(!banned.test(text), `Multi card copy (${label}) matches ${banned}: ${text}`);
  };
  const reference = name => ev(a, `state.checkoutDemo.intents.find(i => i.senderId === state.snapshot.participants.find(p => p.name === ${JSON.stringify(name)}).id).reference`);

  console.log('[1/6] Four diners, two with the same share: one card each, no plain duplicate share...');
  a = (await startChrome(resolveChromePath(), join(dir, 'profile'), procs)).page;
  await a.send('Emulation.setDeviceMetricsOverride', { width: 375, height: 740, deviceScaleFactor: 1, mobile: true });
  await a.navigate(origin + '/');
  await wait(a, "document.getElementById('create-meal-form')");
  await ev(a, `document.getElementById('create-meal-id').value='multi-meal';document.getElementById('create-org-name').value='Organizer';document.getElementById('create-diners').value=${JSON.stringify(DINERS.join(', '))};document.getElementById('create-meal-form').requestSubmit()`);
  await wait(a, "state.mealId==='multi-meal' && document.getElementById('add-item-form')");
  await ev(a, `(async()=>{
    const apply=body=>apiCall('/api/meals/multi-meal/apply','POST',body);
    const shares=${JSON.stringify(SHARES)};
    const people=state.snapshot.participants; const org=people.find(p=>p.organizer).id;
    const items=[{id:'item-org',label:'Organizer dish',quantity:[1,1],line_sen:1000}].concat(people.filter(p=>!p.organizer)
      .map(p=>({id:'item-'+p.id,label:'Dish',quantity:[1,1],line_sen:shares[p.name]})));
    const total=items.reduce((n,i)=>n+i.line_sen,0);
    let s=state.snapshot;
    await apply({kind:'ReplaceReceipt',command_id:'rcpt',expected_revision:s.revision,expected_financial_revision:s.financial_revision,
      receipt:{items,adjustments:[],subtotal_sen:total,total_sen:total,included_tax_sen:0}});
    await fetchSnapshot(true);
    for (const p of people) {
      const item=p.organizer?'item-org':'item-'+p.id;
      s=state.snapshot;
      await apply({kind:'AssignParticipantQuantity',command_id:'assign-'+p.id,participant_id:p.id,item_id:item,quantity:[1,1],
        expected_item_revision:s.items.find(i=>i.item_id===item).item_revision,expected_financial_revision:s.financial_revision});
      await fetchSnapshot(true);
    }
    s=state.snapshot; await apply({kind:'ReviewReceipt',command_id:'review',expected_revision:s.revision,expected_financial_revision:s.financial_revision,receipt_digest:s.receipt_digest});
    await fetchSnapshot(true);
    s=state.snapshot; await apply({kind:'Finalize',command_id:'final',expected_revision:s.revision,expected_financial_revision:s.financial_revision});
    await fetchSnapshot(true);
    s=state.snapshot; await apply({kind:'RecordContribution',command_id:'pay',expected_revision:s.revision,participant_id:org,amount_sen:total,payment_method:'card'});
    await fetchSnapshot(true);
  })()`);
  await wait(a, "document.getElementById('checkout-demo-card')?.dataset.checkoutDemoMode==='multi'");
  await wait(a, "state.checkoutDemo?.multi===true && !state.checkoutDemoBusy && document.querySelectorAll('.checkout-demo-diner-card').length===4");
  assert((await bridgeCalls()).length === 0, 'Loading the cards before any intent must not call the bridge');
  const amountsOf = name => ev(a, `${card(name)}.querySelector('[data-checkout-demo-amounts]').textContent.trim()`);
  for (const [name, text] of [['Diner B', 'Share RM 8.63 − 1 sen offset = pay exactly RM 8.62'],
    ['Diner C', 'Share RM 8.63 − 1 sen offset = pay exactly RM 8.62'], ['Diner D', 'Share RM 5.00 − 0 sen offset = pay exactly RM 5.00'],
    ['Diner E', 'Share RM 7.00 − 0 sen offset = pay exactly RM 7.00']]) {
    assert(await amountsOf(name) === text, `${name} amounts: ${await amountsOf(name)}`);
    assert(await ev(a, cardIs(name, MULTI.none)), `${name} status: ${await ev(a, cardStatus(name))}`);
    assert(await ev(a, `${card(name)}.querySelector('[data-checkout-demo-multi-notice]').textContent === ${JSON.stringify(NOTICE)}`), `${name} notice text`);
    assert(await ev(a, `${card(name)}.querySelector('[data-checkout-demo-amount-line]').textContent === ${JSON.stringify(AMOUNT_LINE)}`), `${name} amount line`);
    assert(await ev(a, `!${card(name)}.querySelector('[data-checkout-demo-hint]')`), `${name}: no read-out hint before a checkout exists`);
  }
  const box = await ev(a, `(()=>{const r=${cardButton('Diner B')}.getBoundingClientRect();return {w:r.width,h:r.height}})()`);
  assert(box.h >= 44 && box.w >= 44, `Request button below 44px touch target: ${JSON.stringify(box)}`);
  assert(await ev(a, 'document.documentElement.scrollWidth <= window.innerWidth'), 'Multi cards cause horizontal scroll at 375 px');
  await checkCopy(a, 'initial');
  const financialBefore = await ev(a, financial);
  console.log('   ✓ Four diner cards; B and C offered RM 8.62, D and E their plain shares; notice text exact; no bridge call');

  console.log('[2/6] Requests freeze distinct amounts; the read-out hint names the exact amount...');
  await ev(a, `${cardButton('Diner B')}.click()`);
  await wait(a, cardIs('Diner B', MULTI.waiting));
  const hintB = await ev(a, `${card('Diner B')}.querySelector('[data-checkout-demo-hint]').textContent.trim()`);
  assert(hintB === `Read out: “${hint('RM 8.62')}”`, `B hint: ${hintB}`);
  // C was offered 862 too; after B's checkout exists the card shows C's new amount before any request.
  await wait(a, `${card('Diner C')}.querySelector('[data-checkout-demo-amounts]').textContent.includes('pay exactly RM 8.61')`);
  await ev(a, `${cardButton('Diner C')}.click()`);
  await wait(a, `!state.checkoutDemoBusy && ${cardIs('Diner C', MULTI.waiting)}`);
  await ev(a, `${cardButton('Diner D')}.click()`);
  await wait(a, `!state.checkoutDemoBusy && ${cardIs('Diner D', MULTI.waiting)}`);
  assert(JSON.stringify(await puts()) === '[862,861,500]', `Bridge amounts: ${await puts()}`);
  const putBodies = (await bridgeCalls()).filter(([m]) => m === 'PUT').length;
  assert(putBodies === 3, `Expected three PUTs, got ${putBodies}`);
  await checkCopy(a, 'requested');
  if (process.env.CHECKOUT_DEMO_SCREENSHOT_DIR) {  // Optional local visual check; not used in CI.
    await ev(a, `${card('Diner B')}.scrollIntoView()`);
    await a.screenshot(join(process.env.CHECKOUT_DEMO_SCREENSHOT_DIR, 'multi-diner-card.png'));
  }
  console.log('   ✓ PUTs of RM 8.62, RM 8.61 and RM 5.00; hint "Please pay exactly RM 8.62"');

  console.log('[3/6] The bridge has no checkout left for a fourth diner: a plain, latched state...');
  await ev(a, `${cardButton('Diner E')}.click()`);
  await wait(a, `!state.checkoutDemoBusy && ${cardIs('Diner E', MULTI.spent)}`);
  assert(await ev(a, `!${cardButton('Diner E')}`), 'No further request for a diner after OBSERVED_CHECKOUT_SPENT');
  assert(JSON.stringify(await puts()) === '[862,861,500]', 'A spent store creates nothing');
  console.log('   ✓ Not created — the bridge has no observed checkouts left');

  console.log('[4/6] Notifications, ambiguity and confirmation; one GET per open checkout...');
  await ev(a, 'clearCheckoutDemoTimers()');
  await control('notification', { reference: await reference('Diner C') });
  await control('notification', { reference: await reference('Diner D') });
  await control('ambiguous', { reference: await reference('Diner D') });
  await control('confirm', { reference: await reference('Diner B') });
  const before = (await bridgeCalls()).length;
  await ev(a, "document.getElementById('checkout-demo-refresh-btn').click()");
  await wait(a, `!state.checkoutDemoBusy && ${cardIs('Diner B', MULTI.confirmed)}`);
  const refreshCalls = (await bridgeCalls()).slice(before);
  assert(refreshCalls.length === 3 && refreshCalls.every(([m]) => m === 'GET'), `Refresh sent ${JSON.stringify(refreshCalls)}`);
  assert(await ev(a, cardIs('Diner C', MULTI.detected)), `C: ${await ev(a, cardStatus('Diner C'))}`);
  assert(await ev(a, cardIs('Diner D', MULTI.ambiguous)), `D: ${await ev(a, cardStatus('Diner D'))}`);
  for (const name of ['Diner B', 'Diner C', 'Diner D']) {
    assert(await ev(a, `!${card(name)}.querySelector('[data-checkout-demo-hint]')`), `${name}: the hint is only shown while waiting`);
  }
  // Finished and latched checkouts are not read again; only C and D are open.
  const before2 = (await bridgeCalls()).length;
  await ev(a, "document.getElementById('checkout-demo-refresh-btn').click()");
  await wait(a, '!state.checkoutDemoBusy');
  await wait(a, `state.checkoutDemo.intents.length===4`);
  const second = (await bridgeCalls()).slice(before2);
  assert(second.length === 2, `Second refresh sent ${second.length} requests`);
  assert(await ev(a, financial) === financialBefore, 'Settlement, funding or transfers changed');
  await checkCopy(a, 'states');
  console.log('   ✓ Confirmed (unverified), observed, ambiguous; balances unchanged; terminal checkouts not re-read');

  console.log('[5/6] The no-free-amount state and the remaining plain states render...');
  const base = await ev(a, 'JSON.stringify(state.checkoutDemo)');
  const render = (patch) => ev(a, `(()=>{ state.checkoutDemo={...${base}, ...${JSON.stringify(patch)}}; updateMealUI(); return true; })()`);
  const eId = await ev(a, "state.snapshot.participants.find(p => p.name === 'Diner E').id");
  const intentsWithoutE = await ev(a, `JSON.stringify(state.checkoutDemo.intents.filter(i => i.senderId !== ${JSON.stringify(eId)}))`);
  await render({intents: JSON.parse(intentsWithoutE), eligible: [], noFreeAmount: [{senderId: eId, receiverId: 'x', amountSen: 700}]});
  assert(await ev(a, cardIs('Diner E', MULTI.noFree)), `No-fit state: ${await ev(a, cardStatus('Diner E'))}`);
  assert(await ev(a, `!${cardButton('Diner E')}`), 'No request offered without a free amount');
  await checkCopy(a, 'no-fit');
  console.log('   ✓ No distinct amount within 9 sen is free right now');

  console.log('[6/6] Hidden page clears every checkout-demo timer...');
  await ev(a, "Object.defineProperty(document,'visibilityState',{configurable:true,get:()=> 'hidden'}); document.dispatchEvent(new Event('visibilitychange'))");
  assert(await ev(a, 'state.checkoutDemoTimers.length===0 && state.checkoutDemoTailTimer===null'), 'Hidden page must clear the schedule');
  console.log('   ✓ Hidden pause');
  console.log('CHECKOUT DEMO OBSERVED MULTI BROWSER REGRESSION OK');
} catch (e) {
  console.error('FAIL', e);
  try { console.log('PAGE', await ev(a, "[...document.querySelectorAll('.checkout-demo-card')].map(c=>c.innerText).join('\\n---\\n') || document.body.innerText")); } catch (_) {}
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
