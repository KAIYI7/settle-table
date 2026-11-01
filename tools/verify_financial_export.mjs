/**
 * Financial correction and mock export regression using one isolated Chrome
 * profile, a disposable SQLite database, and a loopback-only demo server.
 */
import { spawn, execSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import fs, { existsSync } from 'node:fs';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path, { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:net';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function parseArgs() {
  const args = process.argv.slice(2);
  const options = {
    port: process.env.SETTLETABLE_PORT ? parseInt(process.env.SETTLETABLE_PORT, 10) : 8089,
    chrome: null,
    python: null,
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
      if(msg.method === 'Page.javascriptDialogOpening'){ console.log('DIALOG',msg.params.type,msg.params.message); this.send('Page.handleJavaScriptDialog',{accept:true}); }
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
    await this.send('Page.reload');
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

async function startChrome(chromeBin, port, dataDir) {
  const proc = spawn(chromeBin, [
    '--headless=new',
    `--remote-debugging-port=${port}`,
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

  let stderr = '';
  let spawnError;
  proc.on('error', error => { spawnError = error; });
  proc.stderr?.on('data', d => { stderr += d.toString(); });

  try {
  // Wait for DevTools HTTP endpoint
  let target = null;
  for (let i = 0; i < 300; i++) {
    if (spawnError) throw spawnError;
    if (proc.exitCode !== null) {
      throw new Error(`Chrome exited prematurely with code ${proc.exitCode} on port ${port}: ${stderr}`);
    }
    try {
      // Chrome writes its selected port only into this run's fresh profile.
      const selectedPort = Number((await fs.promises.readFile(join(dataDir, 'DevToolsActivePort'), 'utf8')).split('\n')[0]);
      if (!selectedPort) throw Error('Chrome has not published its port');
      const endpoint = `http://127.0.0.1:${selectedPort}/json/list`;
      const res = await fetch(endpoint);
      const list = await res.json();
      target = list.find(t => t.type === 'page');
      if (target && target.webSocketDebuggerUrl) break;
    } catch (e) {}
    await new Promise(r => setTimeout(r, 100));
  }

  if (!target || !target.webSocketDebuggerUrl) {
    proc.kill();
    throw new Error(`Could not connect to Chrome on port ${port} after 30s. Stderr: ${stderr}`);
  }

  const page = new CDPPage(target.webSocketDebuggerUrl);
  await page.send('Page.enable');
  await page.send('Runtime.enable');
  return { proc, page };
  } catch (error) {
    proc.kill();
    throw error;
  }
}

const options = parseArgs();
const serverPort = options.port;
for (const port of [serverPort]) {
  await new Promise((resolve, reject) => {
    const probe = createServer();
    probe.once('error', reject);
    probe.listen(port, '127.0.0.1', () => probe.close(resolve));
  });
}
const dir = await mkdtemp(join(tmpdir(), 'settletable-financial-'));
const capture = join(dir, 'mock-payload.json');
const owner = randomBytes(32).toString('hex');
const origin = `http://127.0.0.1:${serverPort}`;
let server, chrome;
const assert = (condition, message) => { if (!condition) throw Error(message); };
try {
  server = spawn(resolvePythonPath(options.python), [
    '-u', join(REPO_ROOT, 'tools', 'verify_financial_export_runner.py'),
    '--host', '127.0.0.1', '--port', String(serverPort), '--db', join(dir, 'financial.sqlite'),
    '--mock-notion', '--mock-ocr',
  ], { cwd: REPO_ROOT, env: { ...process.env, SETTLETABLE_MOCK_CAPTURE: capture, SETTLETABLE_TEST_OWNER: owner } });
  let serverError;
  server.on('error', error => { serverError = error; });
  server.stderr.on('data', data => process.stderr.write(data));
  let ready = false;
  for (let i = 0; i < 100; i++) {
    if (serverError) throw serverError;
    if (server.exitCode !== null) throw Error('Loopback server exited');
    try {
      const response = await fetch(origin + '/__financial_test_owner__');
      if (response.ok && await response.text() === owner && server.exitCode === null) { ready = true; break; }
    } catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  assert(ready, 'Loopback server did not start');
  chrome = await startChrome(resolveChromePath(options.chrome), 0, join(dir, 'profile'));
  const p = chrome.page;
  const ev = expression => p.evaluate(expression);
  const wait = expression => p.waitFor(expression, 15000);
  await p.send('Emulation.setDeviceMetricsOverride', {width:1280,height:900,deviceScaleFactor:1,mobile:false});
  await p.navigate(origin + '/');
  await wait("document.getElementById('create-meal-form')");
  // Match the UAT's historical item IDs so deterministic tie-breaking is
  // comparable despite production now generating fresh UUID-based IDs.
  await ev("{ let n=2; Object.defineProperty(crypto, 'randomUUID', {configurable:true, value:()=>String(++n)}); }");
  await ev(`document.getElementById('create-meal-id').value='financial-regression'; document.getElementById('create-org-name').value='Alice'; document.getElementById('create-diners').value='Bob, Chandra, Devi, Elaine, Farid'; document.getElementById('create-meal-form').requestSubmit()`);
  await wait("state.mealId==='financial-regression' && document.getElementById('ocr-file-input')");
  await ev(`(()=>{const b=new Uint8Array([137,80,78,71,13,10,26,10,0,0,0,13,73,72,68,82,0,0,0,100,0,0,0,100,8,2,0,0,0,144,145,104,60]);const d=new DataTransfer();d.items.add(new File([b],'synthetic.png',{type:'image/png'}));const x=document.getElementById('ocr-file-input');x.files=d.files;x.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  await wait("document.getElementById('ocr-candidate-card')");
  await ev("document.getElementById('ocr-add-item-btn').click()");
  await ev(`(()=>{const data=[['Nasi Lemak','1','12.01'],['Iced Tea','2','6.00'],['Satay Platter','1','26.00']];for(let i=0;i<data.length;i++){for(const [suffix,v] of [['label',data[i][0]],['qty',data[i][1]],['price',data[i][2]]]){const e=document.getElementById('ocr-item-'+suffix+'-'+i);e.value=v;e.dispatchEvent(new Event('input',{bubbles:true}));}}})()`);
  await ev("document.getElementById('ocr-add-adj-btn').click();document.getElementById('ocr-add-adj-btn').click()");
  await ev(`(()=>{const d=[['service','Service Charge','5.30'],['rounding','Rounding Adjustment','-0.01'],['tax','SST Tax','3.18'],['discount','Discount','1.00']];for(let i=0;i<d.length;i++){for(const [suffix,v] of [['kind',d[i][0]],['label',d[i][1]],['amount',d[i][2]]]){const e=document.getElementById('ocr-adj-'+suffix+'-'+i);e.value=v;e.dispatchEvent(new Event('change',{bubbles:true}));}}})()`);
  await ev("document.getElementById('ocr-accept-btn').click()");
  await wait("!document.getElementById('ocr-candidate-card') && state.snapshot.receipt.items.length===3");
  await ev("document.getElementById('review-confirm-check').click();document.getElementById('review-submit-btn').click()");
  await wait('state.snapshot.review');
  await ev("document.getElementById('new-item-label').value='Roti Canai';document.getElementById('new-item-qty').value='3';document.getElementById('new-item-price').value='9.00';document.getElementById('add-item-form').requestSubmit()");
  await wait('state.snapshot.receipt.items.length===4');
  const after = await ev('state.snapshot');
  assert(!after.review, 'Receipt correction must invalidate verification');
  const service = after.receipt.adjustments.find(a => a.kind === 'service');
  assert(service.amount_sen === 530, 'Printed service amount must remain 530 sen');
  assert(service.eligible_item_ids.length === 4 && service.eligible_item_ids.includes('item-4'), 'Service must include staged and post-accept missing items');
  assert(after.receipt.adjustments.filter(a => ['tax', 'discount'].includes(a.kind)).every(a => a.eligible_item_ids.join(',') === 'item-1,item-2,item-3'), 'Explicit tax and discount scopes must stay fixed');
  assert(after.receipt.adjustments.find(a => a.kind === 'rounding').eligible_item_ids.join(',') === 'item-1,item-2', 'Rounding scope must stay fixed');
  console.log('Corrected receipt:', JSON.stringify(after.receipt));
  const claim = async (item, target) => {
    await ev(`document.querySelector('[data-action="hybrid-quick-assign"][data-item="${item}"][data-target="${target}"]').click()`);
    await wait(`state.snapshot.claims.some(c=>c.item_id==='${item}' && c.participant_id==='${target}')`);
  };
  await claim('item-1','O'); await claim('item-2','D1'); await claim('item-2','D2');
  await ev(`document.querySelector('[data-action="hybrid-toggle-details"][data-item="item-3"]').click();document.querySelector('[data-action="split-clear-all"][data-item="item-3"]').click()`);
  for (const id of ['D1','D2','D3']) await ev(`document.querySelector('[data-action="toggle-split-diner"][data-item="item-3"][data-target="${id}"]').click()`);
  await ev(`document.querySelector('[data-action="apply-equal-split"][data-item="item-3"]').click()`);
  await wait("state.snapshot.claims.filter(c=>c.item_id==='item-3').length===3");
  await claim('item-4','D3'); await claim('item-4','D4'); await claim('item-4','D5');
  await ev("document.getElementById('review-confirm-check').click();document.getElementById('review-submit-btn').click()");
  await wait('state.snapshot.review');
  await wait("!document.getElementById('finalize-btn').disabled");
  await ev("document.getElementById('finalize-btn').click()");
  await wait('state.snapshot.finalized');
  const final = await ev('state.snapshot');
  assert(final.receipt.total_sen === 6048, 'Printed total changed');
  assert(final.calculation.consumption.reduce((sum, part) => sum + part.sen, 0) === 6048, 'Final shares must conserve 6048 sen');
  const serviceShares = final.calculation.adjustments.find(a => a.source_id === service.id).shares;
  const expectedService = {D1:117,D2:116,D3:117,D4:30,D5:30,O:120};
  const expectedTotals = {D1:1341,D2:1340,D3:1327,D4:330,D5:330,O:1380};
  assert(serviceShares.length === 6 && serviceShares.every(s => s.sen === expectedService[s.participant_id]), 'Service shares differ from expected 117/116/117/30/30/120 sen');
  const expectedAdjustments = {
    tax: {D1:84,D2:84,D3:63,D4:0,D5:0,O:87},
    discount: {D1:-27,D2:-26,D3:-20,D4:0,D5:0,O:-27},
    rounding: {D1:0,D2:0,D3:0,D4:0,D5:0,O:-1},
  };
  for (const [kind, expected] of Object.entries(expectedAdjustments)) {
    const id = final.receipt.adjustments.find(a => a.kind === kind).id;
    const shares = final.calculation.adjustments.find(a => a.source_id === id).shares;
    assert(shares.length === 6 && shares.every(s => s.sen === expected[s.participant_id]), `${kind} shares differ from expected`);
  }
  assert(final.calculation.consumption.length === 6 && final.calculation.consumption.every(s => s.sen === expectedTotals[s.participant_id]), 'Final balances differ from expected 1341/1340/1327/330/330/1380 sen');
  console.log('Final calculation:', JSON.stringify(final.calculation));
  await ev("document.getElementById('notion-parent-id').value='3fb0ffe1-72a6-815e-b59d-ef81c6e8eb4d';document.getElementById('notion-export-btn').click()");
  await wait("document.getElementById('notion-page-link')");
  const payload = JSON.parse(await fs.promises.readFile(capture, 'utf8'));
  const rows = Object.values(payload.blocks).flat().filter(b => b.type === 'table').flatMap(b => b.table.children || []).map(row => (row.table_row?.cells || []).map(cell => cell.map(t => t.text?.content || '').join('')));
  for (const part of final.calculation.consumption) {
    const name = final.participants.find(p => p.id === part.participant_id).name;
    const expected = `RM ${(part.sen / 100).toFixed(2)}`;
    assert(rows.some(row => row[0] === (part.participant_id === 'O' ? `${name} (Organizer)` : name) && row[4] === expected), `Mock Notion diner row missing ${name} ${expected}`);
  }
  for (const item of final.receipt.items) {
    assert(rows.some(row => row[0] === item.label && row[3] === `RM ${(item.line_sen / 100).toFixed(2)}`), `Mock Notion item row missing ${item.label}`);
  }
  const blocks = JSON.stringify(payload.blocks);
  assert(blocks.includes('Grand Total: RM 60.48') && blocks.includes('Service Charge: RM 5.30'), 'Mock Notion summary differs from receipt');
  console.log('PASS: browser receipt correction, re-verification, finalization and mock Notion balances');

  // Repeat the UAT amounts with all four items present before accepting the
  // candidate, so tax, discount and rounding can all explicitly cover them.
  await p.navigate(origin + '/');
  await wait("document.getElementById('create-meal-form')");
  await ev("{ let n=2; Object.defineProperty(crypto, 'randomUUID', {configurable:true, value:()=>String(++n)}); }");
  await ev(`document.getElementById('create-meal-id').value='financial-original';document.getElementById('create-org-name').value='Alice';document.getElementById('create-diners').value='Bob, Chandra, Devi, Elaine, Farid';document.getElementById('create-meal-form').requestSubmit()`);
  await wait("state.mealId==='financial-original' && document.getElementById('ocr-file-input')");
  await ev(`(()=>{const b=new Uint8Array([137,80,78,71,13,10,26,10,0,0,0,13,73,72,68,82,0,0,0,100,0,0,0,100,8,2,0,0,0,144,145,104,60]);const d=new DataTransfer();d.items.add(new File([b],'synthetic.png',{type:'image/png'}));const x=document.getElementById('ocr-file-input');x.files=d.files;x.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  await wait("document.getElementById('ocr-candidate-card')");
  await ev("document.getElementById('ocr-add-item-btn').click();document.getElementById('ocr-add-item-btn').click()");
  await ev(`(()=>{const data=[['Nasi Lemak','1','12.01'],['Iced Tea','2','6.00'],['Satay Platter','1','26.00'],['Roti Canai','3','9.00']];for(let i=0;i<data.length;i++){for(const [suffix,v] of [['label',data[i][0]],['qty',data[i][1]],['price',data[i][2]]]){const e=document.getElementById('ocr-item-'+suffix+'-'+i);e.value=v;e.dispatchEvent(new Event('input',{bubbles:true}));}}})()`);
  await ev("document.getElementById('ocr-add-adj-btn').click();document.getElementById('ocr-add-adj-btn').click()");
  await ev(`(()=>{const d=[['service','Service Charge','5.30'],['rounding','Rounding Adjustment','-0.01'],['tax','SST Tax','3.18'],['discount','Discount','1.00']];for(let i=0;i<d.length;i++){for(const [suffix,v] of [['kind',d[i][0]],['label',d[i][1]],['amount',d[i][2]]]){const e=document.getElementById('ocr-adj-'+suffix+'-'+i);e.value=v;e.dispatchEvent(new Event('change',{bubbles:true}));}}})()`);
  // Set fixed rounding scope to the complete receipt using the visible item selectors.
  for (const id of ['item-3','item-4']) {
    await ev(`(()=>{const x=document.querySelector('.ocr-scope-item[data-adj-idx="1"][value="${id}"]');if (!x.checked) x.click()})()`);
  }
  await ev("document.getElementById('ocr-accept-btn').click()");
  await wait("!document.getElementById('ocr-candidate-card') && state.snapshot.receipt.items.length===4");
  const originalReceipt = await ev('state.snapshot.receipt');
  assert(originalReceipt.adjustments.every(a => a.eligible_item_ids.length === 4), 'Every original-fixture adjustment must cover all four items');
  await claim('item-1','O'); await claim('item-2','D1'); await claim('item-2','D2');
  await ev(`document.querySelector('[data-action="hybrid-toggle-details"][data-item="item-3"]').click();document.querySelector('[data-action="split-clear-all"][data-item="item-3"]').click()`);
  for (const id of ['D1','D2','D3']) await ev(`document.querySelector('[data-action="toggle-split-diner"][data-item="item-3"][data-target="${id}"]').click()`);
  await ev(`document.querySelector('[data-action="apply-equal-split"][data-item="item-3"]').click()`);
  await wait("state.snapshot.claims.filter(c=>c.item_id==='item-3').length===3");
  await claim('item-4','D3'); await claim('item-4','D4'); await claim('item-4','D5');
  await ev("document.getElementById('review-confirm-check').click();document.getElementById('review-submit-btn').click()");
  await wait('state.snapshot.review');
  await wait("!document.getElementById('finalize-btn').disabled");
  await ev("document.getElementById('finalize-btn').click()");
  await wait('state.snapshot.finalized');
  const originalFinal = await ev('state.snapshot');
  const originalExpected = {D1:1332,D2:1330,D3:1332,D4:342,D5:342,O:1370};
  assert(originalFinal.calculation.consumption.length === 6 && originalFinal.calculation.consumption.every(s => s.sen === originalExpected[s.participant_id]), 'Original UAT fixture balances do not match expected corrected totals');
  assert(originalFinal.calculation.consumption.reduce((sum, s) => sum + s.sen, 0) === 6048, 'Original fixture did not conserve 6048 sen');
  console.log('Original UAT fixture corrected calculation:', JSON.stringify(originalFinal.calculation));
  await ev("document.getElementById('notion-parent-id').value='3fb0ffe1-72a6-815e-b59d-ef81c6e8eb4d';document.getElementById('notion-export-btn').click()");
  await wait("document.getElementById('notion-page-link')");
  const originalPayload = JSON.parse(await fs.promises.readFile(capture, 'utf8'));
  const originalPage = Object.values(originalPayload.pages).find(page => JSON.stringify(page.properties).includes('financial-original'));
  assert(originalPage, 'Original fixture mock page missing');
  const originalBlocks = originalPayload.blocks[originalPage.id];
  const originalRows = originalBlocks.filter(b => b.type === 'table').flatMap(b => b.table.children || []).map(row => (row.table_row?.cells || []).map(cell => cell.map(t => t.text?.content || '').join('')));
  for (const part of originalFinal.calculation.consumption) {
    const name = originalFinal.participants.find(p => p.id === part.participant_id).name;
    assert(originalRows.some(row => row[0] === (part.participant_id === 'O' ? `${name} (Organizer)` : name) && row[4] === `RM ${(part.sen / 100).toFixed(2)}`), `Original fixture mock row differs for ${name}`);
  }
  assert(JSON.stringify(originalBlocks).includes('Grand Total: RM 60.48'), 'Original fixture mock grand total differs');
  console.log('PASS: original UAT amounts with all-item adjustments and mock Notion balances');

  // A deliberate fixed service scope must survive staged edits and must never
  // expand silently when its last eligible item is removed.
  await p.navigate(origin + '/');
  await wait("document.getElementById('create-meal-form')");
  await ev(`document.getElementById('create-meal-id').value='financial-fixed';document.getElementById('create-org-name').value='Alice';document.getElementById('create-meal-form').requestSubmit()`);
  await wait("state.mealId==='financial-fixed' && document.getElementById('ocr-file-input')");
  await ev(`(()=>{const b=new Uint8Array([137,80,78,71,13,10,26,10,0,0,0,13,73,72,68,82,0,0,0,100,0,0,0,100,8,2,0,0,0,144,145,104,60]);const d=new DataTransfer();d.items.add(new File([b],'synthetic.png',{type:'image/png'}));const x=document.getElementById('ocr-file-input');x.files=d.files;x.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  await wait("document.getElementById('ocr-candidate-card')");
  await ev(`(()=>{const s=document.querySelector('.ocr-adj-scope[data-adj-idx="0"]');s.value='fixed';s.dispatchEvent(new Event('change',{bubbles:true}))})()`);
  await ev(`document.querySelector('.ocr-scope-item[data-adj-idx="0"][value="item-2"]').click()`);
  await ev("document.getElementById('ocr-add-item-btn').click()");
  const firstFreshId = await ev("state.ocrCandidate.items.at(-1).id");
  assert(firstFreshId !== 'item-1' && firstFreshId !== 'item-2', 'New staged ID must be fresh');
  assert(await ev(`JSON.stringify(state.ocrCandidate.adjustments[0].eligible_item_ids) === '["item-1"]'`), 'Fixed scope changed after staged addition');
  await ev("document.querySelector('.ocr-del-item-btn[data-idx=\"0\"]').click()");
  await ev("document.getElementById('ocr-add-item-btn').click()");
  const secondFreshId = await ev("state.ocrCandidate.items.at(-1).id");
  assert(secondFreshId !== firstFreshId && secondFreshId !== 'item-1' && secondFreshId !== 'item-2', 'Delete/add reused an item ID');
  await ev("document.getElementById('ocr-accept-btn').click()");
  assert(await ev("!!document.getElementById('ocr-candidate-card') && document.body.innerText.includes('no eligible items')"), 'Empty fixed scope must block receipt acceptance');
  await ev(`document.querySelector('.ocr-scope-item[data-adj-idx="0"][value="item-2"]').click()`);
  await ev("document.getElementById('ocr-accept-btn').click()");
  await wait("!document.getElementById('ocr-candidate-card') && state.snapshot.receipt.items.length===3");
  const fixed = await ev("state.snapshot.receipt.adjustments.find(a => a.kind==='service')");
  assert(fixed.scope_mode === 'fixed_items' && fixed.eligible_item_ids.join(',') === 'item-2', 'Explicit service scope was not preserved');
  console.log('PASS: selected service scope persists through staged edits and blocks empty scope');

  // Seed a historical draft through the normal transport with the old receipt
  // representation, then exercise the new controls entirely through the UI.
  await p.navigate(origin + '/');
  await wait("document.getElementById('create-meal-form')");
  await ev(`document.getElementById('create-meal-id').value='financial-legacy';document.getElementById('create-org-name').value='Alice';document.getElementById('create-meal-form').requestSubmit()`);
  await wait("state.mealId==='financial-legacy' && document.getElementById('add-item-form')");
  await ev(`(async()=>{const s=state.snapshot;await apiCall('/api/meals/financial-legacy/apply','POST',{kind:'ReplaceReceipt',command_id:'legacy-seed',expected_revision:s.revision,expected_financial_revision:s.financial_revision,receipt:{items:[{id:'a',label:'Rice',quantity:1,line_sen:1000},{id:'b',label:'Tea',quantity:1,line_sen:500}],subtotal_sen:1500,total_sen:1600,adjustments:[{id:'svc',label:'Service',kind:'service',amount_sen:100,eligible_item_ids:['a'],rationale:'Historical selected scope'}],included_tax_sen:0}});await fetchSnapshot(true)})()`);
  assert(await ev("state.snapshot.receipt.adjustments[0].scope_mode == null && state.snapshot.receipt.adjustments[0].eligible_item_ids.join(',')==='a'"), 'Legacy draft scope changed on load');
  await ev("document.getElementById('review-confirm-check').click();document.getElementById('review-submit-btn').click()");
  await wait('state.snapshot.review');
  await ev("document.querySelector('[data-action=\"service-all-items\"]').click()");
  await wait("state.snapshot.receipt.adjustments[0].scope_mode==='all_items'");
  assert(await ev("!state.snapshot.review && state.snapshot.receipt.adjustments[0].amount_sen===100 && state.snapshot.receipt.adjustments[0].eligible_item_ids.join(',')==='a,b'"), 'Bill-wide correction must invalidate review and preserve charge amount');
  await ev("document.getElementById('review-confirm-check').click();document.getElementById('review-submit-btn').click()");
  await wait('state.snapshot.review');
  await ev("document.querySelector('.service-scope-item[value=\"a\"]').click()");
  await ev("document.querySelector('[data-action=\"service-fixed-items\"]').click()");
  await wait("state.snapshot.receipt.adjustments[0].scope_mode==='fixed_items'");
  assert(await ev("!state.snapshot.review && state.snapshot.receipt.adjustments[0].amount_sen===100 && state.snapshot.receipt.adjustments[0].eligible_item_ids.join(',')==='b'"), 'Selected correction must invalidate review and preserve selected scope and amount');
  await ev("document.getElementById('review-confirm-check').click();document.getElementById('review-submit-btn').click()");
  await wait('state.snapshot.review');
  console.log('PASS: historical draft fixed to all to fixed scope with renewed verification');
} finally {
  chrome?.page.close();
  chrome?.proc.kill();
  server?.kill();
  await rm(dir, {recursive:true, force:true, maxRetries:5, retryDelay:200});
}


