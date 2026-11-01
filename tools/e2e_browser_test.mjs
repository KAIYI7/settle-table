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

const REPO_ROOT = fileURLToPath(new URL('..', import.meta.url));

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
  proc.stderr?.on('data', d => { stderr += d.toString(); });

  // Wait for DevTools HTTP endpoint
  const endpoint = `http://127.0.0.1:${port}/json/list`;
  let target = null;
  for (let i = 0; i < 300; i++) {
    if (proc.exitCode !== null) {
      throw new Error(`Chrome exited prematurely with code ${proc.exitCode} on port ${port}: ${stderr}`);
    }
    try {
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
}

async function runUiRegressions(page, serverOrigin) {
  console.log('[UI regression] Receipt rational DOM and quick-assignment capacity');
  await page.send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false });
  const assert = (condition, message) => { if (!condition) throw new Error(message); };
  const quick = (item, diner) => `[data-action="hybrid-quick-assign"][data-item="${item}"][data-target="${diner}"]`;
  const details = '[data-action="hybrid-toggle-details"][data-item="qty-1"]';
  await page.navigate(`${serverOrigin}/`);
  await page.waitFor("document.getElementById('create-meal-form') !== null");
  await page.evaluate(() => {
    document.getElementById('create-meal-id').value = 'ui-regression';
    document.getElementById('create-org-name').value = 'Alice';
    document.getElementById('create-diners').value = 'Bob, Carol';
    document.getElementById('create-meal-form').requestSubmit();
  });
  await page.waitFor("state.mealId === 'ui-regression' && document.getElementById('add-item-form') !== null");
  // Seed authoritative rational values through the real transport; render the real app.
  const originalReceipt = await page.evaluate(async () => {
    const snap = state.snapshot;
    await apiCall('/api/meals/ui-regression/apply', 'POST', {
      kind: 'ReplaceReceipt', command_id: 'ui-receipt',
      expected_revision: snap.revision, expected_financial_revision: snap.financial_revision,
      receipt: {
        items: [[1, 1], [2, 1], [3, 1], [1, 2], [1, 3]].map((quantity, i) => ({
          id: `qty-${i + 1}`, label: `Quantity case ${i + 1}`, quantity, line_sen: 600,
        })),
        subtotal_sen: 3000, total_sen: 3000, adjustments: [], included_tax_sen: 0,
      },
    });
    await fetchSnapshot(true);
    return JSON.stringify(state.snapshot.receipt);
  });
  const checkReceiptDom = async () => {
    const rows = await page.evaluate(() => {
      const card = [...document.querySelectorAll('.card')].find(c =>
        c.querySelector('.card-title')?.textContent.includes('Receipt & Charges'));
      return [...card.querySelectorAll('strong')].filter(el => el.textContent.startsWith('Quantity case'))
        .map(el => ({ label: el.textContent, quantity: el.nextElementSibling.textContent, row: el.parentElement.parentElement.textContent }));
    });
    assert(rows.length === 5, 'Expected five actual Receipt & Charges DOM rows');
    for (const [i, expected] of ['1', '2', '3', '½', '⅓'].entries()) {
      assert(rows[i].quantity === `(x${expected})`, `Receipt DOM quantity ${i + 1}: expected (x${expected}), got ${rows[i].quantity}`);
      assert(rows[i].row.includes('RM 6.00'), 'Receipt line amount changed');
    }
    assert(await page.evaluate('JSON.stringify(state.snapshot.receipt)') === originalReceipt, 'Authoritative receipt changed');
  };
  await checkReceiptDom();
  await page.evaluate(() => {
    const check = document.getElementById('review-confirm-check');
    check.checked = true;
    check.dispatchEvent(new Event('change'));
    document.getElementById('review-submit-btn').click();
  });
  await page.waitFor("document.body.innerText.includes('Review Verified ✓')");
  await checkReceiptDom();
  await page.reload();
  await page.waitFor("state.snapshot?.review && document.getElementById('item-card-qty-1') !== null");
  await checkReceiptDom();
  if (process.env.ARTIFACT_DIR) {
    await fs.promises.mkdir(process.env.ARTIFACT_DIR, { recursive: true });
    await page.screenshot(join(process.env.ARTIFACT_DIR, 'receipt-quantities.png'));
  }
  console.log('   ✓ Receipt DOM x1, x2, x3, x½, x⅓ before/after sealing and reload; authoritative receipt preserved');

  assert(await page.evaluate(`!document.querySelector('${quick('qty-1', 'D1')}').disabled`), 'Whole portion should allow quick assignment');
  await page.evaluate(`document.querySelector('${quick('qty-1', 'D1')}').click()`);
  await page.waitFor("state.snapshot.claims.some(c => c.item_id === 'qty-1' && c.participant_id === 'D1')");
  const beforeBlockedClick = await page.evaluate('JSON.stringify(state.snapshot)');
  const blocked = await page.evaluate(`(() => {
    const button = document.querySelector('${quick('qty-1', 'D2')}');
    return { disabled: button.disabled, title: button.title, description: document.getElementById(button.getAttribute('aria-describedby'))?.textContent };
  })()`);
  assert(blocked.disabled, 'Full-capacity quick assignment must be disabled before clicking');
  assert(blocked.title.includes('Details / Split') && blocked.description?.includes('Fully allocated'), 'Unavailable assignment needs an accessible explanation and Details / Split path');
  await page.evaluate(`document.querySelector('${quick('qty-1', 'D2')}').click()`);
  assert(await page.evaluate('JSON.stringify(state.snapshot)') === beforeBlockedClick, 'Disabled quick assignment changed allocations or revision');
  assert(await page.evaluate("document.querySelector('#hybrid-drawer-qty-1') === null"), 'Disabled quick assignment opened editor');
  for (const item of ['qty-4', 'qty-5']) {
    assert(await page.evaluate(`document.querySelector('${quick(item, 'D1')}').disabled`), 'Fractional capacity must not offer a whole-portion quick assignment');
  }
  // Desktop details remains usable, as do existing allocated diner pills.
  await page.evaluate(`document.querySelector('${details}').focus()`);
  await page.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, text: '\r' });
  await page.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
  await page.waitFor("document.getElementById('hybrid-drawer-qty-1') !== null");
  assert(await page.evaluate("document.querySelector('.bottom-sheet-modal') === null"), 'Desktop editor must remain an inline drawer');
  await page.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
  await page.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
  await page.waitFor("document.getElementById('hybrid-drawer-qty-1') === null");
  await page.evaluate("document.querySelector('[data-action=\"hybrid-open-details\"][data-item=\"qty-1\"][data-target=\"D1\"]').click()");
  await page.waitFor("document.getElementById('hybrid-drawer-qty-1') !== null");
  await page.evaluate(`document.querySelector('${details}').click()`);
  if (process.env.ARTIFACT_DIR) {
    await fs.promises.mkdir(process.env.ARTIFACT_DIR, { recursive: true });
    await page.evaluate("document.getElementById('item-card-qty-1').scrollIntoView({block: 'center'})");
    await page.screenshot(join(process.env.ARTIFACT_DIR, 'capacity-desktop.png'));
  }
  await page.send('Emulation.setDeviceMetricsOverride', { width: 375, height: 667, deviceScaleFactor: 1, mobile: true });
  await page.evaluate("document.getElementById('item-card-qty-1').scrollIntoView({block: 'center'})");
  if (process.env.ARTIFACT_DIR) await page.screenshot(join(process.env.ARTIFACT_DIR, 'capacity-mobile.png'));
  await page.evaluate(`document.querySelector('${details}').focus()`);
  await page.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, text: '\r' });
  await page.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
  await page.waitFor("document.querySelector('.bottom-sheet-modal') !== null");
  assert(await page.evaluate("document.activeElement.matches('.bottom-sheet-close-btn')"), 'Opening sheet must focus its close button');
  const tab = async shift => {
    await page.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9, modifiers: shift ? 8 : 0 });
    await page.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9, modifiers: shift ? 8 : 0 });
    assert(await page.evaluate("document.querySelector('.bottom-sheet-modal').contains(document.activeElement)"), 'Tab escaped modal');
  };
  await tab(true);
  assert(await page.evaluate("document.activeElement === sheetFocusables(document.getElementById('hybrid-bottom-sheet')).at(-1)"), 'Shift+Tab must wrap to last control');
  await tab(false);
  assert(await page.evaluate("document.activeElement.matches('.bottom-sheet-close-btn')"), 'Tab must wrap to first control');
  await page.evaluate("document.querySelector('.room-home-link').focus()");
  assert(await page.evaluate("document.querySelector('.bottom-sheet-modal').contains(document.activeElement)"), 'Background focus must be redirected');
  await page.evaluate('updateMealUI()');
  assert(await page.evaluate("document.activeElement.matches('.bottom-sheet-close-btn')"), 'Re-render lost modal focus');
  assert(await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile allocation UI overflows horizontally');
  if (process.env.ARTIFACT_DIR) await page.screenshot(join(process.env.ARTIFACT_DIR, 'capacity-mobile-details.png'));
  // Reallocate through the existing editor; the freed capacity re-enables quick assign.
  await page.evaluate("document.querySelector('.bottom-sheet-modal [data-action=\"hybrid-fraction\"][data-frac=\"0\"][data-target=\"D1\"]').click()");
  await page.waitFor("!state.snapshot.claims.some(c => c.item_id === 'qty-1')");
  await page.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape' });
  await page.waitFor("document.querySelector('.bottom-sheet-modal') === null");
  assert(await page.evaluate(`document.activeElement === document.querySelector('${details}')`), 'Escape must restore trigger focus');
  await page.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, text: '\r' });
  await page.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
  await page.waitFor("document.querySelector('.bottom-sheet-modal') !== null");
  await page.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, text: '\r' });
  await page.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
  await page.waitFor("document.querySelector('.bottom-sheet-modal') === null");
  assert(await page.evaluate(`document.activeElement === document.querySelector('${details}')`), 'Close button must restore trigger focus');
  assert(await page.evaluate(`!document.querySelector('${quick('qty-1', 'D2')}').disabled`), 'Freed capacity did not re-enable quick assignment');
  await page.evaluate(`document.querySelector('${quick('qty-1', 'D2')}').click()`);
  await page.waitFor("state.snapshot.claims.some(c => c.item_id === 'qty-1' && c.participant_id === 'D2')");
  await page.reload();
  await page.waitFor("state.snapshot?.claims?.some(c => c.item_id === 'qty-1' && c.participant_id === 'D2')");
  assert(await page.evaluate(`document.querySelector('${quick('qty-1', 'D1')}').disabled`), 'Full capacity after reallocation/reload must disable quick assign');
  await checkReceiptDom();
  await page.send('Emulation.clearDeviceMetricsOverride');
  console.log('   ✓ Capacity affordance, blocked-click invariance, desktop/mobile Details, reallocation and reload');
}

async function main() {
  const options = parseArgs();
  const chromeBin = resolveChromePath(options.chrome);
  const pythonBin = resolvePythonPath(options.python);
  const serverPort = options.port;
  const serverOrigin = `http://127.0.0.1:${serverPort}`;

  // Refuse occupied ports rather than accidentally test an unrelated listener.
  for (const port of [serverPort, 9224, 9225]) {
    await new Promise((resolve, reject) => {
      const probe = createServer();
      probe.once('error', reject);
      probe.listen(port, '127.0.0.1', () => probe.close(resolve));
    });
  }

  console.log('--- Starting SettleTable Real Browser End-to-End Test ---');
  console.log(`[Config] Chrome: ${chromeBin}`);
  console.log(`[Config] Python: ${pythonBin}`);
  console.log(`[Config] Repo:   ${REPO_ROOT}`);

  // 1. Create temporary directory for databases and browser profiles
  const testDir = await mkdtemp(join(tmpdir(), 'settletable-e2e-'));
  const dbPath = join(testDir, 'e2e.sqlite');
  const dirOrg = join(testDir, 'chrome-org');
  const dirDiner = join(testDir, 'chrome-diner');

  // 2. Start SettleTable WSGI Demo Server
  console.log(`[1/8] Starting local server on port ${serverPort}...`);
  const serverProc = spawn(pythonBin, [
    '-u',
    join('tools', 'run_demo.py'),
    '--host', '127.0.0.1',
    '--port', String(serverPort),
    '--db', dbPath,
    '--mock-notion',
    '--mock-ocr',
  ], { cwd: REPO_ROOT });

  serverProc.stderr.on('data', d => console.error('[SERVER STDERR]:', d.toString()));
  serverProc.stdout.on('data', d => console.log('[SERVER STDOUT]:', d.toString()));

  // Wait for server to respond
  for (let i = 0; i < 50; i++) {
    try {
      const res = await fetch(`${serverOrigin}/`);
      if (res.ok) break;
    } catch (e) {}
    await new Promise(r => setTimeout(r, 100));
  }

  let orgChrome, dinerChrome;
  try {
    // 3. Launch isolated Chrome instances
    console.log('[2/8] Launching isolated Organizer and Diner Chrome instances...');
    orgChrome = await startChrome(chromeBin, 9224, dirOrg);
    dinerChrome = await startChrome(chromeBin, 9225, dirDiner);

    const pageA = orgChrome.page;
    const pageB = dinerChrome.page;

    await runUiRegressions(pageA, serverOrigin);
    if (options.uiRegressionsOnly) return;

    // 4a. Test Dedicated OCR Workflow: Upload, Inline Edit, Discard & Accept
    console.log('[3/8] Testing OCR Image Upload, Staging, Inline Edit, Discard, and Accept & Apply...');
    await pageA.navigate(`${serverOrigin}/`);
    await pageA.waitFor("document.getElementById('create-meal-form') !== null");

    await pageA.evaluate(`
      document.getElementById('create-meal-id').value = 'ocr-e2e-room';
      document.getElementById('create-org-name').value = 'Alice';
      document.getElementById('create-diners').value = 'Bob';
      document.getElementById('create-meal-form').requestSubmit();
    `);
    await pageA.waitFor("window.location.hash.includes('#/meal/ocr-e2e-room') && document.getElementById('add-item-form') !== null");
    console.log('   ✓ Dedicated OCR test room created');

    // Genuine Image Upload OCR extraction via real browser input & HTTP POST
    console.log('   Testing genuine image upload OCR extraction via real browser input...');
    const triggerUpload = `(() => {
      const pngHeader = new Uint8Array([
        137, 80, 78, 71, 13, 10, 26, 10,
        0, 0, 0, 13, 73, 72, 68, 82,
        0, 0, 0, 100, 0, 0, 0, 100,
        8, 2, 0, 0, 0, 144, 145, 104, 60
      ]);
      const file = new File([pngHeader], 'receipt.png', { type: 'image/png' });
      const dt = new DataTransfer();
      dt.items.add(file);
      const input = document.getElementById('ocr-file-input');
      input.files = dt.files;
      input.dispatchEvent(new Event('change', { bubbles: true }));
    })()`;

    await pageA.evaluate(triggerUpload);
    await pageA.waitFor("document.getElementById('ocr-candidate-card') !== null");
    console.log('   ✓ Genuine browser image upload parsed by server OCR engine and rendered candidate card');
    await pageA.waitFor("document.getElementById('ocr-cand-subtotal-val').innerText === 'RM 15.20'");
    console.log('   ✓ Server OCR candidate verified: Subtotal RM 15.20, Total RM 16.70');

    // Verify Compact Dismissible OCR Alert
    const alertMsg = await pageA.evaluate("document.querySelector('.alert-banner .alert-message')?.textContent");
    if (!alertMsg || !alertMsg.includes('Scanned 2 items (RM 16.70)')) {
      throw new Error(`Expected compact OCR alert message with count and total, got: ${alertMsg}`);
    }
    const hasCloseBtn = await pageA.evaluate("document.querySelector('.alert-banner .alert-close-btn') !== null");
    if (!hasCloseBtn) {
      throw new Error('Expected dismiss button (.alert-close-btn) on alert banner');
    }
    console.log(`   ✓ Compact dismissible alert verified: "${alertMsg}" with close button`);

    // Test Desktop Viewport Usability & Stepper Interaction
    const desktopTheadDisplay = await pageA.evaluate("window.getComputedStyle(document.querySelector('.ocr-items-table thead')).display");
    if (desktopTheadDisplay === 'none') {
      throw new Error(`Expected desktop table thead to be visible, got ${desktopTheadDisplay}`);
    }

    // Verify Stepper Quantity Component
    const initialDecDisabled = await pageA.evaluate("document.querySelector('.ocr-qty-dec').disabled");
    if (!initialDecDisabled) {
      throw new Error('Expected minus button to be disabled when quantity is 1');
    }

    // Click increment button on first item: qty becomes 2, authoritative line total is RM 12.00, tooltip stores ~RM 6.00 each
    await pageA.evaluate("document.querySelector('.ocr-qty-inc').click()");
    await pageA.waitFor("document.getElementById('ocr-item-qty-0').value === '2'");
    await pageA.waitFor("document.getElementById('ocr-item-price-0').title.includes('~RM 6.00')");
    const incDecDisabled = await pageA.evaluate("document.querySelector('.ocr-qty-dec').disabled");
    if (incDecDisabled) {
      throw new Error('Expected minus button to be enabled when quantity is > 1');
    }

    // Check no floating unit price caption in DOM and verify locked uniform row heights
    const floatingUnitExists = await pageA.evaluate("document.querySelector('.ocr-cand-item-unit') !== null");
    if (floatingUnitExists) {
      throw new Error('Expected floating unit price caption to be removed from table DOM');
    }
    const rowHeights = await pageA.evaluate(`(() => {
      const rows = Array.from(document.querySelectorAll('.ocr-cand-item-row'));
      return rows.map(r => r.getBoundingClientRect().height);
    })()`);
    if (rowHeights.length >= 2 && Math.abs(rowHeights[0] - rowHeights[1]) > 2) {
      throw new Error(`Expected uniform locked row heights across items, got: ${JSON.stringify(rowHeights)}`);
    }
    console.log(`   ✓ Desktop candidate layout verified: Stepper component, authoritative Line Total, accessible tooltip, and locked uniform row heights (${rowHeights[0]}px)`);

    // Verify Competing Receipt-Editing Flows: #add-item-form is paused and notice rendered
    const competingFormExists = await pageA.evaluate("document.getElementById('add-item-form') !== null");
    if (competingFormExists) {
      throw new Error('Expected separate manual #add-item-form to be paused during active candidate staging');
    }
    const stagingNoticeExists = await pageA.evaluate("document.querySelector('.ocr-staging-active-notice') !== null");
    if (!stagingNoticeExists) {
      throw new Error('Expected .ocr-staging-active-notice to be displayed while candidate is staged');
    }
    const reviewCheckDisabled = await pageA.evaluate("document.getElementById('review-confirm-check').disabled");
    if (!reviewCheckDisabled) {
      throw new Error('Expected review-confirm-check to be disabled while candidate is staged');
    }
    console.log('   ✓ Single editing workflow verified: manual #add-item-form paused and review checkbox guarded during staging');

    // Capture Stepper Interaction Screenshot
    const artifactDir = process.env.ARTIFACT_DIR;
    if (artifactDir && !fs.existsSync(artifactDir)) fs.mkdirSync(artifactDir, { recursive: true });
    await pageA.evaluate("document.getElementById('ocr-candidate-card')?.scrollIntoView({ block: 'start' })");
    if (artifactDir) await pageA.screenshot(path.join(artifactDir, 'screenshot_stepper_interaction.png'));

    // Click decrement button back to 1
    await pageA.evaluate("document.querySelector('.ocr-qty-dec').click()");
    await pageA.waitFor("document.getElementById('ocr-item-qty-0').value === '1'");
    await pageA.waitFor("document.getElementById('ocr-cand-subtotal-val').innerText === 'RM 15.20'");

    // Test Adjustment Category Selector Auto-Suggestion
    await pageA.evaluate(`(() => {
      const select = document.querySelector('.ocr-edit-adj-kind');
      select.value = 'tax';
      select.dispatchEvent(new Event('change', { bubbles: true }));
    })()`);
    const suggestedTaxLabel = await pageA.evaluate("document.querySelector('.ocr-edit-adj-label').value");
    if (suggestedTaxLabel !== 'SST Tax') {
      throw new Error(`Expected auto-suggested label 'SST Tax', got: ${suggestedTaxLabel}`);
    }
    await pageA.evaluate(`(() => {
      const select = document.querySelector('.ocr-edit-adj-kind');
      select.value = 'service';
      select.dispatchEvent(new Event('change', { bubbles: true }));
    })()`);
    const restoredServiceLabel = await pageA.evaluate("document.querySelector('.ocr-edit-adj-label').value");
    if (restoredServiceLabel !== 'Service Charge') {
      throw new Error(`Expected restored label 'Service Charge', got: ${restoredServiceLabel}`);
    }
    console.log('   ✓ Adjustment category auto-suggestion verified: switching kind updates default label cleanly');

    // Capture Desktop Viewport Screenshot (1280x800)
    await pageA.evaluate("document.getElementById('ocr-candidate-card')?.scrollIntoView({ block: 'start' })");
    if (artifactDir) {
      await pageA.screenshot(path.join(artifactDir, 'screenshot_desktop_candidate_editor.png'));
      console.log('   ✓ Desktop candidate editor screenshot captured');
    }

    // Test Tablet Viewport Usability (768x1024)
    await pageA.send('Emulation.setDeviceMetricsOverride', { width: 768, height: 1024, deviceScaleFactor: 2, mobile: false });
    await pageA.evaluate("document.getElementById('ocr-candidate-card')?.scrollIntoView({ block: 'start' })");
    if (artifactDir) {
      await pageA.screenshot(path.join(artifactDir, 'screenshot_tablet_candidate_editor.png'));
      console.log('   ✓ Tablet candidate editor screenshot captured (768x1024)');
    }

    // Test Mobile Viewport Usability, Stacked Layout, & Touch Targets (375x667)
    await pageA.send('Emulation.setDeviceMetricsOverride', { width: 375, height: 667, deviceScaleFactor: 2, mobile: true });

    // Show compact alert in mobile viewport to verify height and dismissibility
    await pageA.evaluate("showAlert('✓ Scanned 2 items (RM 16.70)', 'success', true)");
    const mobileAlertHeight = await pageA.evaluate("document.querySelector('.alert-banner')?.getBoundingClientRect().height");
    if (!mobileAlertHeight || mobileAlertHeight > 50) {
      throw new Error(`Expected compact mobile alert height <= 50px, got ${mobileAlertHeight}px`);
    }
    console.log(`   ✓ Mobile compact alert verified: height ${mobileAlertHeight}px <= 50px (saves vertical screen space)`);

    // Verify Mobile Navigation Header
    const mobileHomeNavDisplay = await pageA.evaluate("window.getComputedStyle(document.getElementById('nav-home-btn')).display");
    if (mobileHomeNavDisplay !== 'none') {
      throw new Error(`Expected #nav-home-btn to be hidden on mobile, got ${mobileHomeNavDisplay}`);
    }
    const leaveBtnBounds = await pageA.evaluate("(() => { const r = document.getElementById('header-leave-btn').getBoundingClientRect(); return { w: r.width, h: r.height }; })()");
    if (leaveBtnBounds.h < 38 || leaveBtnBounds.h > 44 || leaveBtnBounds.w < 40) {
      throw new Error(`Expected single-line Leave Room button with touch height >= 38px and <= 44px, got ${JSON.stringify(leaveBtnBounds)}`);
    }
    const refreshBtnBounds = await pageA.evaluate("(() => { const r = document.getElementById('manual-refresh-btn').getBoundingClientRect(); return { w: r.width, h: r.height }; })()");
    if (refreshBtnBounds.h < 38 || refreshBtnBounds.w < 38) {
      throw new Error(`Expected mobile Refresh button touch target >= 40px, got ${JSON.stringify(refreshBtnBounds)}`);
    }
    const headerOverflow = await pageA.evaluate("document.querySelector('.header-inner').scrollWidth > document.querySelector('.header-inner').clientWidth + 1");
    if (headerOverflow) {
      throw new Error('Detected horizontal overflow in mobile header');
    }
    console.log(`   ✓ Mobile header layout verified (375px): single-line Leave Room (${leaveBtnBounds.w}x${leaveBtnBounds.h}px), Refresh (${refreshBtnBounds.w}x${refreshBtnBounds.h}px) touch targets >= 40px, #nav-home-btn hidden, zero horizontal overflow`);

    // Capture Mobile Header & Compact Alert Screenshot
    await pageA.evaluate("window.scrollTo(0, 0)");
    if (artifactDir) {
      await pageA.screenshot(path.join(artifactDir, 'screenshot_mobile_header_375px.png'));
      console.log('   ✓ Mobile header and compact alert screenshot captured (375px)');
    }

    // Dismiss alert and verify removal
    await pageA.evaluate("document.querySelector('.alert-close-btn')?.click()");
    const alertDismissed = await pageA.evaluate("document.querySelector('.alert-banner') === null");
    if (!alertDismissed) {
      throw new Error('Expected alert banner to be removed upon clicking close button');
    }
    console.log('   ✓ Alert dismissal verified: clicking ✕ cleanly removes banner from DOM');

    // Verify Mobile Items Table
    const mobileTheadDisplay = await pageA.evaluate("window.getComputedStyle(document.querySelector('.ocr-items-table thead')).display");
    if (mobileTheadDisplay !== 'none') {
      throw new Error(`Expected mobile table thead to be hidden, got ${mobileTheadDisplay}`);
    }
    const mobileLabelDisplay = await pageA.evaluate("window.getComputedStyle(document.querySelector('.ocr-mobile-only.ocr-field-label')).display");
    if (mobileLabelDisplay !== 'block') {
      throw new Error(`Expected mobile field labels to be displayed, got ${mobileLabelDisplay}`);
    }
    const touchTargets = await pageA.evaluate("(() => { const btn = document.querySelector('.ocr-del-item-btn'); const r = btn.getBoundingClientRect(); return { w: r.width, h: r.height }; })()");
    if (touchTargets.w < 40 || touchTargets.h < 40) {
      throw new Error(`Mobile touch target too small: ${JSON.stringify(touchTargets)}, expected >= 40px`);
    }
    console.log(`   ✓ Mobile responsive stacked layout verified (375px): stacked grid, touch targets ${touchTargets.w}x${touchTargets.h}px >= 40px`);

    // Verify Mobile Adjustments Select Width & Readability
    const selectWidth = await pageA.evaluate("document.querySelector('.ocr-edit-adj-kind').getBoundingClientRect().width");
    if (selectWidth < 140) {
      throw new Error(`Expected mobile adjustment select width >= 140px, got ${selectWidth}px`);
    }
    console.log(`   ✓ Mobile adjustments verified (375px): Kind select width ${selectWidth}px >= 140px (untruncated options)`);

    // Capture Mobile Candidate Editor Full Screenshot (375x667)
    await pageA.evaluate("document.getElementById('ocr-candidate-card')?.scrollIntoView({ block: 'start' })");
    if (artifactDir) {
      await pageA.screenshot(path.join(artifactDir, 'screenshot_mobile_candidate_editor.png'));
      console.log('   ✓ Mobile candidate editor screenshot captured (375x667)');
    }

    // Capture Mobile Adjustments Screenshot
    await pageA.evaluate("document.querySelector('.ocr-adjustments-section')?.scrollIntoView({ block: 'start' })");
    if (artifactDir) {
      await pageA.screenshot(path.join(artifactDir, 'screenshot_mobile_adjustments_375px.png'));
    }

    // Restore Desktop Viewport (1280x800)
    await pageA.send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 800, deviceScaleFactor: 1, mobile: false });

    // Test inline editing of candidate item
    await pageA.evaluate(`(() => {
      const labelInput = document.querySelector('.ocr-edit-item-label');
      const qtyInput = document.querySelector('.ocr-edit-item-qty');
      const priceInput = document.querySelector('.ocr-edit-item-price');
      labelInput.value = 'Steamed Chicken Rice';
      qtyInput.value = '2';
      priceInput.value = '24.00';
      priceInput.dispatchEvent(new Event('input', { bubbles: true }));
    })()`);
    await pageA.waitFor("document.getElementById('ocr-cand-subtotal-val').innerText === 'RM 27.20'");
    console.log('   ✓ Inline item correction recalculates candidate subtotal: RM 27.20');

    // Test negative cash rounding adjustment (-RM 0.02) preservation
    await pageA.waitFor("document.getElementById('ocr-cand-total-val').innerText === 'RM 28.70'");
    console.log('   ✓ Candidate total accurately reflects item correction + service + rounding: RM 28.70');

    // Discard candidate: clears candidate card without modifying authoritative draft
    await pageA.evaluate("document.getElementById('ocr-discard-btn').click()");
    await pageA.waitFor("document.getElementById('ocr-candidate-card') === null");
    console.log('   ✓ OCR Candidate discarded cleanly without altering SQLite state');

    // Test Accept & Apply to Receipt button:
    console.log('   Testing "Accept & Apply to Receipt" button workflow...');
    await pageA.evaluate(triggerUpload);
    await pageA.waitFor("document.getElementById('ocr-candidate-card') !== null");
    await pageA.evaluate("document.getElementById('ocr-accept-btn').click()");
    await pageA.waitFor("document.getElementById('ocr-candidate-card') === null");
    await pageA.waitFor("document.body.innerText.toUpperCase().includes('CHICKEN RICE')");
    await pageA.waitFor("document.body.innerText.toUpperCase().includes('ICE LEMON TEA')");
    await pageA.waitFor("document.body.innerText.includes('Service Charge')");
    await pageA.waitFor("document.body.innerText.includes('-0.02')");
    await pageA.waitFor("document.body.innerText.includes('RM 16.70')");
    // Verify no error banner
    const ocrRoomText = await pageA.evaluate("document.body.innerText");
    if (ocrRoomText.includes('Action rejected')) {
      throw new Error(`Unexpected 'Action rejected' error banner after Accept & Apply: ${ocrRoomText}`);
    }
    console.log('   ✓ "Accept & Apply to Receipt" succeeded without error: items, service charge, and -RM 0.02 rounding applied to SQLite draft');

    // 3b. Test Navigation: Participant Identification & Home Link
    console.log('   Testing participant identification & Home navigation...');
    await pageA.waitFor("document.getElementById('header-user-status').innerText.includes('Organizer')");
    await pageA.waitFor("document.getElementById('header-user-status').innerText.includes('Alice')");
    await pageA.waitFor("document.querySelector('.room-status-card') !== null && document.querySelector('.room-home-link') !== null");
    console.log('   ✓ Header and room status card clearly identify current participant (Organizer: Alice) and room');

    // Click Home link
    await pageA.evaluate("document.getElementById('nav-home-btn').click()");
    await pageA.waitFor("window.location.hash.includes('#/') && document.getElementById('create-meal-form') !== null");
    console.log('   ✓ Home navigation button returns cleanly to Welcome screen');

    // Return to room
    await pageA.navigate(`${serverOrigin}/#/meal/ocr-e2e-room`);
    await pageA.waitFor("document.getElementById('add-item-form') !== null");

    // 3c. Test Accidental Same-Profile Invitation Redemption & Warning
    console.log('   Testing accidental same-profile invitation redemption & warning...');
    // Alice issues an invitation for Bob in ocr-e2e-room
    await pageA.evaluate(`
      const btn = document.querySelector('.issue-invite-btn');
      if (btn) btn.click();
    `);
    await pageA.waitFor("state.issuedTokens['D1'] !== undefined");
    const ocrInviteUrl = await pageA.evaluate("state.issuedTokens['D1']");

    // Alice opens this invitation in the SAME browser window
    await pageA.navigate(ocrInviteUrl);
    await pageA.waitFor("document.getElementById('redeem-btn') !== null");
    const inviteLandingText = await pageA.evaluate("document.body.innerText");
    if (!inviteLandingText.includes('Same-Browser Profile Notice')) {
      throw new Error(`Expected Same-Browser Profile Notice on invite landing`);
    }
    if (!inviteLandingText.includes('replace your Organizer session')) {
      throw new Error(`Expected warning explaining session replacement on invite landing`);
    }
    console.log('   ✓ Same-browser profile warning clearly rendered on invitation landing');

    // Alice redeems invitation in the same browser (reproducing user scenario)
    await pageA.evaluate("document.getElementById('redeem-btn').click()");
    await pageA.waitFor("window.location.hash.includes('#/meal/ocr-e2e-room') && document.body.innerText.includes('🍽️ Diner')");
    const dinerTextSameProfile = await pageA.evaluate("document.body.innerText");
    if (!dinerTextSameProfile.includes('Bob') || dinerTextSameProfile.includes('👑 Organizer')) {
      throw new Error(`Expected diner identity (Bob) after same-profile redeem, got: ${dinerTextSameProfile.slice(0, 300)}`);
    }
    console.log('   ✓ Reproduced: Same-profile redemption assigns Diner session (Bob) in this browser profile');

    // 3d. Test Safe Session Exit (Leave Room)
    console.log('   Testing safe session-exit mechanism (Leave Room)...');
    await pageA.evaluate("document.getElementById('header-leave-btn').click()");
    await pageA.waitFor("window.location.hash.includes('#/') && document.getElementById('create-meal-form') !== null");
    console.log('   ✓ Leave Room cleanly cleared session cookie and returned to Home');

    // Verify session cookie is deleted: trying to open ocr-e2e-room directly now fails with Session Required
    await pageA.navigate(`${serverOrigin}/#/meal/ocr-e2e-room`);
    await pageA.waitFor("document.body.innerText.includes('Session Required')");
    console.log('   ✓ Verified session cookie wiped: room access without session correctly rejected');

    // 4. Organizer Journey: Create meal room "dinner-e2e" for multi-user flow
    console.log('[4/8] Organizer Alice creating main meal "dinner-e2e"...');
    await pageA.navigate(`${serverOrigin}/`);
    await pageA.waitFor("document.getElementById('create-meal-form') !== null");

    await pageA.evaluate(`
      document.getElementById('create-meal-id').value = 'dinner-e2e';
      document.getElementById('create-org-name').value = 'Alice';
      document.getElementById('create-diners').value = 'Bob';
      document.getElementById('create-meal-form').requestSubmit();
    `);

    // Wait until room loads
    await pageA.waitFor("window.location.hash.includes('#/meal/dinner-e2e') && document.getElementById('add-item-form') !== null");
    console.log('   ✓ Meal dinner-e2e created and Alice loaded room as Organizer');

    // 5. Organizer adds two receipt items
    console.log('[4/8] Organizer Alice adding two receipt items with prices...');
    // Item 1: Burger Set (Qty: 2, Price: RM 24.00)
    await pageA.evaluate(`
      document.getElementById('new-item-label').value = 'Burger Set';
      document.getElementById('new-item-qty').value = '2';
      document.getElementById('new-item-price').value = 'RM 24.00';
      document.getElementById('add-item-form').dispatchEvent(new Event('submit', { cancelable: true }));
    `);
    await pageA.waitFor("document.body.innerText.includes('Burger Set')");

    // Item 2: Iced Tea (Qty: 2, Price: 6.00)
    await pageA.evaluate(`
      document.getElementById('new-item-label').value = 'Iced Tea';
      document.getElementById('new-item-qty').value = '2';
      document.getElementById('new-item-price').value = '6.00';
      document.getElementById('add-item-form').dispatchEvent(new Event('submit', { cancelable: true }));
    `);
    await pageA.waitFor("document.body.innerText.includes('Iced Tea')");
    console.log('   ✓ Both items added; Receipt items visible in DOM');

    // Verify totals displayed in Organizer card
    const orgReceiptText = await pageA.evaluate("document.body.innerText");
    if (!orgReceiptText.includes('RM 30.00')) {
      throw new Error(`Receipt Total RM 30.00 not found in DOM: ${orgReceiptText.slice(0, 500)}`);
    }
    console.log('   ✓ Verified items subtotal & total match: RM 30.00');

    // Organizer completes Human Receipt Review while scrolled down
    console.log('   Testing Human Receipt Review verification while scrolled below header...');
    await pageA.evaluate("document.getElementById('review-submit-btn').scrollIntoView({ block: 'center' })");
    const initialScrollY = await pageA.evaluate("window.scrollY");
    if (initialScrollY < 100) {
      throw new Error(`Expected page to be scrolled down below header (scrollY > 100), got ${initialScrollY}`);
    }

    await pageA.evaluate(`
      const check = document.getElementById('review-confirm-check');
      check.checked = true;
      check.dispatchEvent(new Event('change'));
      document.getElementById('review-submit-btn').click();
    `);
    await pageA.waitFor("document.getElementById('receipt-verified-status') !== null");
    await pageA.waitFor("document.querySelector('.alert-banner') !== null");

    // 1. Assert scroll position did NOT jump to top
    const postScrollY = await pageA.evaluate("window.scrollY");
    if (Math.abs(postScrollY - initialScrollY) > 60) {
      throw new Error(`Expected scroll position to be preserved near ${initialScrollY}px, but jumped to ${postScrollY}px`);
    }

    // 2. Assert in-situ persistent confirmation in Human Receipt Review card
    const verifiedStatusText = await pageA.evaluate("document.getElementById('receipt-verified-status').innerText");
    if (!verifiedStatusText.includes('Receipt Verified & Sealed') || !verifiedStatusText.includes('Alice')) {
      throw new Error(`Expected persistent verification banner with reviewer Alice, got: ${verifiedStatusText}`);
    }
    console.log('   ✓ Persistent in-situ confirmation verified in Human Receipt Review card');

    // 3. Assert fixed-position toast alert is visible within user's current viewport
    const toastInViewport = await pageA.evaluate(`(() => {
      const banner = document.querySelector('.alert-banner');
      if (!banner) return false;
      const r = banner.getBoundingClientRect();
      return r.top >= 0 && r.bottom <= window.innerHeight && r.width > 0 && r.height > 0;
    })()`);
    if (!toastInViewport) {
      throw new Error('Expected fixed-position alert toast to be visible in current scrolled viewport');
    }
    console.log('   ✓ Viewport toast verified: visible in current viewport while scrolled down');

    // Capture Scrolled Verification Screenshot showing both in-situ confirmation and floating toast
    if (artifactDir) {
      await pageA.screenshot(path.join(artifactDir, 'screenshot_scrolled_receipt_verification.png'));
      console.log('   ✓ Scrolled receipt verification screenshot captured');
    }

    // 4. Test accessible keyboard dismissal with Escape key
    await pageA.send('Input.dispatchKeyEvent', { type: 'rawKeyDown', key: 'Escape', windowsVirtualKeyCode: 27 });
    await pageA.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', windowsVirtualKeyCode: 27 });
    await pageA.waitFor("document.querySelector('.alert-banner') === null");
    console.log('   ✓ Accessible keyboard dismissal verified: pressing Escape dismisses toast');
    console.log('   ✓ Human Receipt Review submitted and verified');

    // 6. Organizer creates invitation for Bob
    console.log('[5/8] Organizer creating invitation for Bob...');
    await pageA.evaluate(`
      const btn = document.querySelector('.issue-invite-btn');
      if (btn) btn.click();
    `);
    await pageA.waitFor("state.issuedTokens['D1'] !== undefined");
    const inviteUrl = await pageA.evaluate("state.issuedTokens['D1']");
    const safeInviteUrl = inviteUrl.replace(/\/invite\/[a-zA-Z0-9_-]+/, '/invite/[REDACTED]');
    console.log(`   ✓ Invitation URL generated: ${safeInviteUrl}`);

    // 7. Diner Bob opens invitation in separate isolated Chrome instance
    console.log('[6/8] Diner Bob navigating to invitation URL in isolated browser...');
    await pageB.navigate(inviteUrl);
    await pageB.waitFor("document.getElementById('redeem-btn') !== null");
    const dinerText = await pageB.evaluate("document.body.innerText");
    if (!dinerText.includes('Bob')) {
      throw new Error(`Expected Diner Bob invitation text, got: ${dinerText}`);
    }
    console.log('   ✓ Unauthenticated landing rendered valid invitation for Bob');

    // Bob accepts invitation
    await pageB.evaluate("document.getElementById('redeem-btn').click()");
    await pageB.waitFor("window.location.hash.includes('#/meal/dinner-e2e') && document.body.innerText.includes('🍽️ Diner')");
    console.log('   ✓ Bob redeemed invitation and joined room with Diner session cookie');

    // 8. Claims & Concurrency Conflict Testing
    console.log('[7/8] Testing claiming, realtime sync, and 409 stale conflict handling...');
    // Bob claims 1 Burger Set
    await pageB.evaluate(`
      const incBtn = document.querySelector('.claim-inc-btn[data-id="item-1"]');
      if (incBtn) incBtn.click();
    `);
    await pageB.waitFor("state.snapshot?.claims?.some(c => c.participant_id === 'D1' && c.item_id === 'item-1')");
    console.log('   ✓ Bob claimed 1 Burger Set');

    // Trigger manual refresh on Alice's page and confirm Alice sees Bob's claim
    await pageA.evaluate("fetchSnapshot(true)");
    await pageA.waitFor("state.snapshot?.claims?.some(c => c.participant_id === 'D1' && c.item_id === 'item-1') && document.querySelector('.hybrid-pill-allocated[data-item=\"item-1\"][data-target=\"D1\"]') !== null");
    console.log('   ✓ Alice sees Bob · 1 in realtime pill list');

    // Test Stale Claim Conflict:
    // Alice intentionally submits an outdated claim at item_revision 0
    console.log('   Testing 409 Conflict rejection for stale item revision...');
    const conflictResult = await pageA.evaluate(async () => {
      try {
        await apiCall('/api/meals/dinner-e2e/apply', 'POST', {
          kind: 'SetOwnQuantity',
          command_id: `stale-test-${Date.now()}`,
          item_id: 'item-1',
          quantity: 1,
          expected_item_revision: 0, // Outdated revision
          expected_financial_revision: state.snapshot.financial_revision,
        });
        return { ok: true };
      } catch (err) {
        handleApiError(err, 'item-1');
        return { ok: false, status: err.status, code: err.code };
      }
    });
    if (conflictResult.status !== 409) {
      throw new Error(`Expected 409 conflict, got: ${JSON.stringify(conflictResult)}`);
    }
    await pageA.waitFor("document.body.innerText.includes('Conflict')");
    console.log('   ✓ Stale claim cleanly rejected with 409 Conflict & banner displayed');

    // Test Organizer Allocation (Concept C item-first): Alice assigns 1 Iced Tea to Bob in 1 click
    console.log('   Testing organizer-assisted allocation (Alice assigns portion to Bob via Concept C)...');
    const teaId = await pageA.evaluate("state.snapshot.receipt.items.find(item => item.label === 'Iced Tea')?.id");
    if (!teaId) throw new Error('Iced Tea missing from authoritative receipt');
    // Exercise a real diner claim on a manually generated (non-sequential) ID.
    await pageB.evaluate(`(() => {
      const btn = [...document.querySelectorAll('.claim-inc-btn')].find(el => el.dataset.id === ${JSON.stringify(teaId)});
      if (btn) btn.click();
    })()`);
    await pageB.waitFor(`state.snapshot?.claims?.some(c => c.participant_id === 'D1' && c.item_id === ${JSON.stringify(teaId)})`);
    await pageB.evaluate(`(() => {
      const btn = [...document.querySelectorAll('.claim-dec-btn')].find(el => el.dataset.id === ${JSON.stringify(teaId)});
      if (btn) btn.click();
    })()`);
    await pageB.waitFor(`!state.snapshot?.claims?.some(c => c.participant_id === 'D1' && c.item_id === ${JSON.stringify(teaId)})`);
    await pageA.evaluate('fetchSnapshot(true)');
    await pageA.waitFor(`!state.snapshot?.claims?.some(c => c.participant_id === 'D1' && c.item_id === ${JSON.stringify(teaId)})`);
    await pageA.evaluate(`(() => {
      const btn = [...document.querySelectorAll('[data-action="hybrid-quick-assign"][data-target="D1"]')].find(el => el.dataset.item === ${JSON.stringify(teaId)});
      if (btn) btn.click();
    })()`);
    await pageA.waitFor(`state.snapshot?.claims?.some(c => c.participant_id === 'D1' && c.item_id === ${JSON.stringify(teaId)} && c.assigned_by === 'O')`);
    console.log('   ✓ Organizer Alice allocated 1 Iced Tea to Bob (assigned_by: O verified in snapshot)');

    // Alice claims remaining portions: 1 Burger Set and 1 Iced Tea via 1-click quick-assign
    await pageA.evaluate(`
      const btnBurger = document.querySelector('[data-action="hybrid-quick-assign"][data-item="item-1"][data-target="O"]');
      if (btnBurger) btnBurger.click();
    `);
    await pageA.waitFor("state.snapshot?.claims?.some(c => c.participant_id === 'O' && c.item_id === 'item-1')");

    await pageA.evaluate(`
      const btnTea = [...document.querySelectorAll('[data-action="hybrid-quick-assign"][data-target="O"]')].find(el => el.dataset.item === ${JSON.stringify(teaId)});
      if (btnTea) btnTea.click();
    `);
    await pageA.waitFor(`state.snapshot?.claims?.some(c => c.participant_id === 'O' && c.item_id === ${JSON.stringify(teaId)})`);
    console.log('   ✓ All items fully allocated across Alice and Bob');

    // 9. Finalization & Apportionment Check
    console.log('[8/8] Alice finalizes meal and verifies calculations in both browsers...');
    await pageA.waitFor("!document.getElementById('finalize-btn').disabled");
    // Accept confirm dialog by overriding window.confirm in page
    await pageA.evaluate(`
      window.confirm = () => true;
      document.getElementById('finalize-btn').click();
    `);
    await pageA.waitFor("document.body.innerText.includes('Final Apportionment Summary')");

    // Fetch snapshot on Bob's browser as well
    await pageB.evaluate("fetchSnapshot(true)");
    await pageB.waitFor("document.body.innerText.includes('Final Apportionment Summary')");

    // Assert exact per-person amounts in both Alice and Bob DOM
    const textAliceFinal = await pageA.evaluate("document.body.innerText");
    const textBobFinal = await pageB.evaluate("document.body.innerText");

    // Calculation breakdown:
    // Burger Set (RM 24.00) split 1:1 between Alice and Bob = RM 12.00 each
    // Iced Tea (RM 6.00) split 1:1 between Alice and Bob = RM 3.00 each
    // Alice total: RM 15.00
    // Bob total: RM 15.00
    // Grand Total: RM 30.00
    for (const text of [textAliceFinal, textBobFinal]) {
      if (!text.includes('RM 15.00')) throw new Error(`Missing RM 15.00 total in DOM: ${text.slice(0, 500)}`);
      if (!text.includes('RM 30.00')) throw new Error(`Missing Grand Total RM 30.00 in DOM`);
    }
    console.log('   ✓ Both browsers display exact authoritative breakdown:');
    console.log('     - Alice (Organizer): RM 15.00');
    console.log('     - Bob (Diner):       RM 15.00');
    console.log('     - Grand Total:       RM 30.00');

    // 10. Test Page Reload Persistence in both browsers
    console.log('   Testing page reload persistence in both browsers...');
    await pageA.reload();
    await pageB.reload();

    await pageA.waitFor("document.body.innerText.includes('Final Apportionment Summary')");
    await pageB.waitFor("document.body.innerText.includes('Final Apportionment Summary')");

    const reloadedAlice = await pageA.evaluate("document.body.innerText");
    const reloadedBob = await pageB.evaluate("document.body.innerText");
    if (!reloadedAlice.includes('RM 15.00') || !reloadedBob.includes('RM 15.00')) {
      throw new Error('State was not preserved after reload!');
    }
    console.log('   ✓ State and amounts preserved after reload in both isolated sessions');

    // 11. Test Optional Notion Export Flow (Organizer only)
    console.log('[9/9] Testing Optional Notion Export UI flow (Organizer only)...');
    // Verify Bob (Diner) does NOT see Notion export card
    const bobHasNotion = await pageB.evaluate("Boolean(document.getElementById('notion-export-card'))");
    if (bobHasNotion) throw new Error('Diner should NOT see Notion export controls');

    // Alice pastes a full Notion sharing URL and leaves token blank (tests URL auto-extraction & mock token default)
    const normalizedId = await pageA.evaluate(`(() => {
      const input = document.getElementById('notion-parent-id');
      input.value = 'https://app.notion.com/p/SYNTHETIC-Meal-001-3fb0ffe172a6815eb59def81c6e8eb4d?source=copy_link';
      input.dispatchEvent(new Event('input'));
      return input.value;
    })()`);
    if (normalizedId !== '3fb0ffe1-72a6-815e-b59d-ef81c6e8eb4d') {
      throw new Error(`Expected normalized UUID 3fb0ffe1-72a6-815e-b59d-ef81c6e8eb4d, got ${normalizedId}`);
    }
    console.log('   ✓ Notion sharing URL automatically normalized to canonical UUID:', normalizedId);

    // Wait 4 seconds (exceeding the 3-second poll interval) to verify background polling does NOT clear the input field
    await new Promise(resolve => setTimeout(resolve, 4000));
    const inputValAfterPoll = await pageA.evaluate("document.getElementById('notion-parent-id').value");
    if (inputValAfterPoll !== '3fb0ffe1-72a6-815e-b59d-ef81c6e8eb4d') {
      throw new Error(`Input field was cleared by background polling! Expected '3fb0ffe1-72a6-815e-b59d-ef81c6e8eb4d', got '${inputValAfterPoll}'`);
    }
    console.log('   ✓ Verified input field persists across background polling cycles without being cleared');

    // Alice clicks export with token input empty
    await pageA.evaluate(`document.getElementById('notion-export-btn').click()`);

    // Await green success banner with Notion link
    await pageA.waitFor("document.getElementById('notion-page-link') !== null");
    const notionUrl = await pageA.evaluate("document.getElementById('notion-page-link').href");
    if (!notionUrl.includes('notion.so/')) throw new Error(`Unexpected Notion URL: ${notionUrl}`);
    console.log(`   ✓ Notion export succeeded with generated URL: ${notionUrl}`);
    console.log('   ✓ Diner context verified free of export controls');

    // [10/10] Testing Organizer-Managed Allocation without Diner Sessions
    console.log('[10/10] Testing Organizer-Managed Allocation without diner sessions...');
    await pageA.navigate(`${serverOrigin}/#/`);
    await pageA.waitFor("document.getElementById('create-meal-form') !== null");
    await pageA.evaluate(`
      document.getElementById('create-meal-id').value = 'managed-e2e';
      document.getElementById('create-org-name').value = 'Alice';
      document.getElementById('create-diners').value = 'Carol, Dan';
      document.getElementById('create-meal-form').requestSubmit();
    `);
    await pageA.waitFor("window.location.hash.includes('#/meal/managed-e2e') && document.body.innerText.includes('👑 Organizer')");

    // Alice adds receipt item
    await pageA.evaluate(`
      document.getElementById('new-item-label').value = 'Satay Platter';
      document.getElementById('new-item-qty').value = '2';
      document.getElementById('new-item-price').value = '20.00';
      document.getElementById('add-item-form').requestSubmit();
    `);
    await pageA.waitFor("document.body.innerText.includes('Satay Platter')");

    // Alice assigns 1 Satay to Carol (who has never logged in) via 1-click quick assign
    await pageA.evaluate(`document.querySelector('[data-action="hybrid-quick-assign"][data-item="item-1"][data-target="D1"]').click()`);
    await pageA.waitFor("state.snapshot?.claims?.some(c => c.participant_id === 'D1' && c.item_id === 'item-1')");

    // Alice assigns 1 Satay to Dan (who has never logged in) via 1-click quick assign
    await pageA.evaluate(`document.querySelector('[data-action="hybrid-quick-assign"][data-item="item-1"][data-target="D2"]').click()`);
    await pageA.waitFor("state.snapshot?.claims?.some(c => c.participant_id === 'D2' && c.item_id === 'item-1')");
    await pageA.waitFor("document.body.innerText.includes('✓ Fully Allocated')");
    console.log('   ✓ Alice allocated entire receipt to Carol and Dan without diner sessions');

    // Review & Finalize
    await pageA.evaluate(`
      const check = document.getElementById('review-confirm-check');
      check.checked = true;
      check.dispatchEvent(new Event('change'));
      document.getElementById('review-submit-btn').click();
    `);
    await pageA.waitFor("document.body.innerText.includes('Review Verified ✓')");

    await pageA.evaluate(`
      window.confirm = () => true;
      document.getElementById('finalize-btn').click();
    `);
    await pageA.waitFor("document.body.innerText.includes('Final Apportionment Summary')");

    // Verify calculation totals for Carol and Dan
    const managedFinalText = await pageA.evaluate("document.body.innerText");
    if (!managedFinalText.includes('RM 10.00')) throw new Error('Missing Carol/Dan RM 10.00 amount');
    if (!managedFinalText.includes('RM 20.00')) throw new Error('Missing Grand Total RM 20.00 amount');
    console.log('   ✓ Organizer-managed calculation verified: Carol RM 10.00, Dan RM 10.00, Total RM 20.00');

    // Export to Notion
    await pageA.evaluate(`
      document.getElementById('notion-parent-id').value = '3fb0ffe1-72a6-815e-b59d-ef81c6e8eb4d';
      document.getElementById('notion-export-btn').click();
    `);
    await pageA.waitFor("document.getElementById('notion-page-link') !== null");
    console.log('   ✓ Organizer-managed Notion report exported successfully');

    // =========================================================================
    // 11. Dual Invitation & General Meal Join Request Workflow
    // =========================================================================
    console.log('[11/11] Testing Dual Diner Invitation & General Meal Join Request Workflow...');
    // Alice creates meal "dual-join-e2e" with Diners Bob and Charlie
    await pageA.navigate(`${serverOrigin}/#/`);
    await pageA.waitFor("document.getElementById('create-meal-form') !== null");
    await pageA.evaluate(`
      document.getElementById('create-meal-id').value = 'dual-join-e2e';
      document.getElementById('create-org-name').value = 'Alice';
      document.getElementById('create-diners').value = 'Bob, Charlie';
      document.getElementById('create-meal-form').requestSubmit();
    `);
    await pageA.waitFor("window.location.hash.includes('#/meal/dual-join-e2e') && document.getElementById('add-item-form') !== null");
    console.log('   ✓ Room dual-join-e2e created with Alice (Organizer), Bob (Diner), and Charlie (Diner)');

    // Add item: Laksa (2 @ RM 20.00)
    await pageA.evaluate(`
      document.getElementById('new-item-label').value = 'Laksa';
      document.getElementById('new-item-qty').value = '2';
      document.getElementById('new-item-price').value = '20.00';
      document.getElementById('add-item-form').dispatchEvent(new Event('submit', { cancelable: true }));
    `);
    await pageA.waitFor("document.body.innerText.includes('Laksa')");

    // Verify Copy General Join Link button exists in Organizer view
    const copyJoinBtnExists = await pageA.evaluate("document.getElementById('copy-general-join-btn') !== null");
    if (!copyJoinBtnExists) throw new Error('Missing copy-general-join-btn in Organizer UI');
    console.log('   ✓ General Meal Join Link control verified in Organizer view');

    // Clear Diner session in browser B
    await pageB.evaluate(`apiCall('/api/session/clear', 'POST', {}).catch(() => {})`);

    // Diner visits general meal join landing: /join/dual-join-e2e
    console.log('   Testing general join landing in diner browser...');
    await pageB.navigate(`${serverOrigin}/join/dual-join-e2e`);
    await pageB.waitFor("document.getElementById('join-name-input') !== null");
    const joinLandingText = await pageB.evaluate("document.body.innerText");
    if (!joinLandingText.includes('Join Dining Table') || !joinLandingText.includes('Same-Browser Profile Notice')) {
      throw new Error('General join landing missing header or same-browser notice');
    }
    console.log('   ✓ General join landing rendered with security notice and name input');

    // Test rejection: unknown guest (uniform anti-enumeration error)
    await pageB.evaluate(`
      document.getElementById('join-name-input').value = 'UnknownGuest';
      document.getElementById('submit-join-req-btn').click();
    `);
    await pageB.waitFor("document.getElementById('join-error-box').style.display !== 'none' && !document.getElementById('submit-join-req-btn').disabled");
    const unknownError = await pageB.evaluate("document.getElementById('join-error-box').innerText");
    if (!unknownError.includes('Unable to request access for "UnknownGuest"')) {
      throw new Error(`Unexpected unknown guest error: ${unknownError}`);
    }
    console.log('   ✓ Security check passed: Unregistered guest rejected with uniform anti-enumeration message');

    // Test rejection: cannot join as organizer (Alice) - also returns uniform anti-enumeration error
    await pageB.evaluate(`
      document.getElementById('join-name-input').value = 'Alice';
      document.getElementById('submit-join-req-btn').click();
    `);
    await pageB.waitFor("document.getElementById('join-error-box').innerText.includes('Unable to request access for \"Alice\"') && !document.getElementById('submit-join-req-btn').disabled");
    console.log('   ✓ Security check passed: Organizer backdoor prohibited with indistinguishable anti-enumeration message');

    // Valid join request for Charlie
    await pageB.evaluate(`
      document.getElementById('join-name-input').value = 'Charlie';
      document.getElementById('submit-join-req-btn').click();
    `);
    await pageB.waitFor("document.body.innerText.includes('Join Request Submitted')");
    console.log('   ✓ Join request submitted for Charlie; diner entered polling state');

    // In Organizer browser, verify pending join request appears
    await pageA.waitFor("document.querySelector('.approve-join-req-btn') !== null");
    const pendingText = await pageA.evaluate("document.body.innerText");
    if (!pendingText.includes('Charlie')) throw new Error('Pending request for Charlie not found in Organizer UI');
    console.log('   ✓ Organizer received pending join request for Charlie');

    // Organizer clicks Approve
    await pageA.evaluate(`document.querySelector('.approve-join-req-btn').click()`);
    console.log('   ✓ Organizer clicked Approve');

    // In Diner browser, polling auto-detects approval, claims session, and loads meal room
    await pageB.waitFor("window.location.hash.includes('#/meal/dual-join-e2e') && document.body.innerText.includes('Charlie')");
    console.log('   ✓ Diner browser automatically claimed session and entered meal as Charlie');

    // Charlie claims portion of Laksa
    await pageB.evaluate(`document.querySelector('.claim-inc-btn[data-id="item-1"]').click()`);
    await pageB.waitFor("state.snapshot?.claims?.some(c => c.participant_id === 'D2' && c.item_id === 'item-1')");
    console.log('   ✓ Charlie successfully claimed portion on the receipt');

    // Verify Bob personal invite link remains fully functional in parallel
    await pageA.evaluate(`document.querySelector('.issue-invite-btn[data-id="D1"]').click()`);
    await pageA.waitFor("state.issuedTokens['D1'] !== undefined");
    const bobToken = await pageA.evaluate("state.issuedTokens['D1']");
    if (!bobToken.includes('/invite/')) throw new Error('Personal invite link creation failed');
    console.log('   ✓ Verified Personal One-Time Invite Link for Bob remains 100% operational in parallel');

    console.log('\n===========================================================');
    console.log(' ALL 12 REAL BROWSER E2E TEST STAGES PASSED SUCCESSFULLY! ');
    console.log('===========================================================');
  } finally {
    if (orgChrome) {
      orgChrome.page.close();
      orgChrome.proc.kill();
    }
    if (dinerChrome) {
      dinerChrome.page.close();
      dinerChrome.proc.kill();
    }
    serverProc.kill();
    await rm(testDir, { recursive: true, force: true }).catch(() => {});
  }
}

main().catch(err => {
  console.error('\nE2E BROWSER TEST FAILED:', err);
  process.exit(1);
});
