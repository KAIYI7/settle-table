/**
 * Headless Chrome E2E verification of receipt photo preview, zoom modal,
 * organizer lifecycle controls, finalized view, and Notion export with photo option.
 */
import { spawn } from 'node:child_process';
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
    port: process.env.SETTLETABLE_PORT ? parseInt(process.env.SETTLETABLE_PORT, 10) : 8092,
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
    candidates.push('/usr/bin/google-chrome-stable', '/usr/bin/google-chrome', '/usr/bin/chromium-browser');
  }

  for (const candidate of candidates) {
    if (candidate && existsSync(candidate)) return candidate;
  }
  throw new Error('Chrome executable not found.');
}

function resolvePythonPath(explicitPath) {
  if (explicitPath && existsSync(explicitPath)) return explicitPath;
  for (const candidate of [process.env.PYTHON, 'C:\\Python314\\python.exe', 'python3', 'python']) {
    if (candidate && (existsSync(candidate) || !candidate.includes('\\'))) return candidate;
  }
  return 'python';
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
      if (msg.method === 'Page.javascriptDialogOpening') {
        this.send('Page.handleJavaScriptDialog', { accept: true });
      }
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
    '--disable-component-update',
    '--disable-sync',
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
    let target = null;
    for (let i = 0; i < 300; i++) {
      if (spawnError) throw spawnError;
      if (proc.exitCode !== null) {
        throw new Error(`Chrome exited prematurely with code ${proc.exitCode} on port ${port}: ${stderr}`);
      }
      try {
        let activePort = port;
        try {
          const devToolsFile = await fs.promises.readFile(join(dataDir, 'DevToolsActivePort'), 'utf8');
          const parsed = Number(devToolsFile.split('\n')[0]);
          if (parsed) activePort = parsed;
        } catch {}
        const endpoint = `http://127.0.0.1:${activePort}/json/list`;
        const res = await fetch(endpoint);
        const list = await res.json();
        target = list.find(t => t.type === 'page' && t.webSocketDebuggerUrl);
        if (!target) {
          const newRes = await fetch(`http://127.0.0.1:${activePort}/json/new`, { method: 'PUT' });
          const newPage = await newRes.json();
          if (newPage && newPage.webSocketDebuggerUrl) target = newPage;
        }
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
await new Promise((resolve, reject) => {
  const probe = createServer();
  probe.once('error', reject);
  probe.listen(serverPort, '127.0.0.1', () => probe.close(resolve));
});

const dir = await mkdtemp(join(tmpdir(), 'settletable-receipt-test-'));
const capture = join(dir, 'mock-payload.json');
const owner = randomBytes(32).toString('hex');
const origin = `http://127.0.0.1:${serverPort}`;
let server, chrome;
const assert = (condition, message) => { if (!condition) throw Error(message); };

try {
  server = spawn(resolvePythonPath(options.python), [
    '-u', join(REPO_ROOT, 'tools', 'verify_financial_export_runner.py'),
    '--host', '127.0.0.1', '--port', String(serverPort), '--db', join(dir, 'receipt_flow.sqlite'),
    '--mock-notion', '--mock-ocr',
  ], { cwd: REPO_ROOT, env: { ...process.env, SETTLETABLE_MOCK_CAPTURE: capture, SETTLETABLE_TEST_OWNER: owner } });

  let serverError;
  server.on('error', error => { serverError = error; });
  server.stderr.on('data', data => process.stderr.write(data));

  let ready = false;
  for (let i = 0; i < 150; i++) {
    if (serverError) throw serverError;
    try {
      const res = await fetch(`${origin}/__financial_test_owner__`);
      if (res.status === 200 && (await res.text()).trim() === owner) {
        ready = true;
        break;
      }
    } catch (e) {}
    await new Promise(r => setTimeout(r, 100));
  }
  assert(ready, 'Server failed to start');

  const chromeBin = resolveChromePath(options.chrome);
  const chromeDir = join(dir, 'chrome-profile');
  await fs.promises.mkdir(chromeDir, { recursive: true });
  chrome = await startChrome(chromeBin, serverPort + 10, chromeDir);
  const page = chrome.page;

  console.log('[1/7] Bootstrapping room via UI in browser...');
  const mealId = 'receipt-photo-e2e';
  await page.send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false });
  await page.navigate(origin + '/');
  await page.waitFor(() => document.getElementById('create-meal-form') !== null);
  await page.evaluate(`
    document.getElementById('create-meal-id').value = '${mealId}';
    document.getElementById('create-org-name').value = 'Alice';
    document.getElementById('create-diners').value = 'Bob';
    document.getElementById('create-meal-form').requestSubmit();
  `);
  await page.waitFor(() => document.getElementById('ocr-upload-btn') !== null);
  console.log('   ✓ Organizer view loaded');

  console.log('[2/7] Uploading receipt image to trigger OCR and candidate staging...');
  await page.evaluate(() => {
    const b = new Uint8Array([137,80,78,71,13,10,26,10,0,0,0,13,73,72,68,82,0,0,0,100,0,0,0,100,8,2,0,0,0,144,145,104,60]);
    const d = new DataTransfer();
    d.items.add(new File([b], 'synthetic.png', { type: 'image/png' }));
    const x = document.getElementById('ocr-file-input');
    x.files = d.files;
    x.dispatchEvent(new Event('change', { bubbles: true }));
  });

  await page.waitFor(() => document.getElementById('ocr-candidate-card') !== null);
  console.log('   ✓ OCR candidate card displayed');

  // Verify preview bar
  const hasPreviewBar = await page.evaluate(() => {
    const bar = document.querySelector('.ocr-source-preview-bar');
    const zoomBtn = document.getElementById('ocr-source-zoom-btn');
    const thumbBtn = document.getElementById('ocr-source-thumb-btn');
    return Boolean(bar && zoomBtn && thumbBtn);
  });
  assert(hasPreviewBar, 'OCR source preview bar missing');
  console.log('   ✓ Staged source preview bar and Zoom button present');

  console.log('[3/7] Testing Receipt Photo Fullscreen/Zoom Modal...');
  await page.evaluate(() => document.getElementById('ocr-source-zoom-btn').click());
  await page.waitFor(() => {
    const modal = document.getElementById('receipt-modal');
    return modal && modal.style.display === 'flex';
  });
  console.log('   ✓ Zoom modal opened (display: flex)');

  // Verify zoom controls
  const initialZoom = await page.evaluate(() => document.getElementById('receipt-zoom-level').textContent);
  assert(initialZoom === '100%', `Initial zoom level expected 100%, got ${initialZoom}`);

  await page.evaluate(() => document.getElementById('receipt-zoom-in').click());
  const zoomedIn = await page.evaluate(() => document.getElementById('receipt-zoom-level').textContent);
  assert(zoomedIn === '125%', `Zoomed in level expected 125%, got ${zoomedIn}`);

  await page.evaluate(() => document.getElementById('receipt-zoom-out').click());
  const zoomedOut = await page.evaluate(() => document.getElementById('receipt-zoom-level').textContent);
  assert(zoomedOut === '100%', `Zoomed out level expected 100%, got ${zoomedOut}`);

  await page.evaluate(() => document.getElementById('receipt-zoom-reset').click());
  const zoomReset = await page.evaluate(() => document.getElementById('receipt-zoom-level').textContent);
  assert(zoomReset === '100%', `Zoom reset expected 100%, got ${zoomReset}`);

  // Close modal via Escape key
  await page.evaluate(() => {
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
  });
  await page.waitFor(() => {
    const modal = document.getElementById('receipt-modal');
    return !modal || modal.style.display === 'none';
  });
  console.log('   ✓ Modal closed via Escape key');

  console.log('[4/7] Accepting candidate and verifying attached photo card...');
  await page.evaluate(() => document.getElementById('ocr-accept-btn').click());
  await page.waitFor(() => document.getElementById('receipt-photo-container') !== null);

  const cardControls = await page.evaluate(() => {
    const container = document.getElementById('receipt-photo-container');
    const viewBtn = document.getElementById('view-photo-modal-btn');
    const replaceBtn = document.getElementById('replace-photo-btn');
    const deleteBtn = document.getElementById('delete-photo-btn');
    const thumb = document.getElementById('receipt-card-thumb');
    return {
      hasContainer: Boolean(container),
      hasViewBtn: Boolean(viewBtn),
      hasReplaceBtn: Boolean(replaceBtn),
      hasDeleteBtn: Boolean(deleteBtn),
      thumbSrc: thumb ? thumb.getAttribute('src') : null,
    };
  });
  assert(cardControls.hasContainer, 'Attached receipt photo card missing');
  assert(cardControls.hasViewBtn, 'View & Zoom button missing');
  assert(cardControls.hasReplaceBtn, 'Replace Photo button missing');
  assert(cardControls.hasDeleteBtn, 'Remove Photo button missing');
  assert(cardControls.thumbSrc && (cardControls.thumbSrc.startsWith('blob:') || cardControls.thumbSrc.includes('/receipt/photo')), 'Thumbnail src invalid');
  console.log('   ✓ Attached receipt photo card rendered with complete lifecycle controls');

  // Open modal via View & Zoom button on the card, and close via Close button (✕)
  await page.evaluate(() => document.getElementById('view-photo-modal-btn').click());
  await page.waitFor(() => {
    const modal = document.getElementById('receipt-modal');
    return modal && modal.style.display === 'flex';
  });
  await page.evaluate(() => document.getElementById('receipt-modal-close').click());
  await page.waitFor(() => {
    const modal = document.getElementById('receipt-modal');
    return !modal || modal.style.display === 'none';
  });
  console.log('   ✓ Modal opened from card and closed via ✕ button');

  console.log('[5/7] Reviewing receipt, allocating items, and finalizing meal...');
  // Wait for snapshot to reflect applied receipt and UI to update
  await page.waitFor(() => !state.mutationActive && state.snapshot?.receipt?.items?.length > 0);
  // Check review confirmation checkbox and seal receipt
  await page.evaluate(() => {
    const check = document.getElementById('review-confirm-check');
    check.checked = true;
    check.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await page.waitFor(() => {
    const btn = document.getElementById('review-submit-btn');
    return btn && !btn.disabled;
  });
  await page.evaluate(() => document.getElementById('review-submit-btn').click());
  await page.waitFor(() => document.getElementById('receipt-verified-status') !== null);
  console.log('   ✓ Receipt confirmed and sealed');

  // Allocate all receipt items to Alice using hybrid quick assign
  await page.evaluate(() => {
    const snap = state.snapshot;
    for (const item of snap.receipt.items) {
      const btn = document.querySelector(`[data-action="hybrid-quick-assign"][data-item="${item.id}"][data-target="O"]`);
      if (btn) btn.click();
    }
  });
  await page.waitFor(() => {
    const btn = document.getElementById('finalize-btn');
    return btn && !btn.disabled;
  });

  // Finalize meal
  await page.evaluate(() => {
    window.confirm = () => true;
    document.getElementById('finalize-btn').click();
  });
  await page.waitFor(() => document.getElementById('finalized-receipt-photo-card') !== null);
  console.log('   ✓ Meal finalized and finalized view rendered');

  console.log('[6/7] Verifying finalized view receipt photo card and Notion photo option...');
  const finPhotoCard = await page.evaluate(() => {
    const card = document.getElementById('finalized-receipt-photo-card');
    const viewBtn = document.getElementById('view-finalized-photo-btn');
    const thumb = document.getElementById('finalized-receipt-thumb-btn');
    return Boolean(card && viewBtn && thumb);
  });
  assert(finPhotoCard, 'Finalized receipt photo card missing');

  // Open modal from finalized view
  await page.evaluate(() => document.getElementById('view-finalized-photo-btn').click());
  await page.waitFor(() => {
    const modal = document.getElementById('receipt-modal');
    return modal && modal.style.display === 'flex';
  });
  await page.evaluate(() => document.getElementById('receipt-modal-close').click());
  console.log('   ✓ Preserved receipt photo accessible after finalization');

  // Verify Notion export checkbox
  const photoCheckbox = await page.evaluate(() => {
    const box = document.getElementById('notion-include-photo');
    return {
      exists: Boolean(box),
      checked: box ? box.checked : null,
      disabled: box ? box.disabled : null,
    };
  });
  assert(photoCheckbox.exists, 'Notion include photo checkbox missing');
  assert(photoCheckbox.checked === false, 'Photo checkbox must be default OFF');
  assert(photoCheckbox.disabled === false, 'Photo checkbox should be enabled when meal has photo');
  console.log('   ✓ Notion photo option verified: Default OFF and enabled');

  console.log('[7/7] Testing Notion export with photo option and view-only sharing guidance...');
  // Check the photo option box
  await page.evaluate(() => {
    const box = document.getElementById('notion-include-photo');
    box.checked = true;
    const parentInput = document.getElementById('notion-parent-id');
    parentInput.value = '3fb0ffe1-72a6-815e-b59d-ef81c6e8eb4d';
  });

  await page.evaluate(() => document.getElementById('notion-export-btn').click());

  await page.waitFor(() => {
    const res = document.getElementById('notion-export-result');
    return res && res.textContent.includes('Export Successful');
  });

  const exportResult = await page.evaluate(() => {
    const res = document.getElementById('notion-export-result');
    const guidance = document.getElementById('notion-view-only-guidance');
    const link = document.getElementById('notion-page-link');
    return {
      hasGuidance: Boolean(guidance),
      guidanceText: guidance ? guidance.textContent : '',
      pageUrl: link ? link.getAttribute('href') : null,
    };
  });
  assert(exportResult.hasGuidance, 'View-only sharing guidance missing');
  assert(exportResult.guidanceText.includes('Publish to web'), 'Guidance missing Publish to web step');
  assert(exportResult.guidanceText.includes('Privacy Warning'), 'Guidance missing privacy warning');
  console.log('   ✓ 4-step view-only sharing guidance and privacy warning verified');

  // Verify captured mock Notion payload includes image block
  const capturedText = await fs.promises.readFile(capture, 'utf8');
  const capturedData = JSON.parse(capturedText);
  const pageList = Object.values(capturedData.pages || {});
  assert(pageList.length > 0, 'No Notion page captured');
  const allBlocks = Object.values(capturedData.blocks || {}).flat();
  const imageBlock = allBlocks.find(b => b.type === 'image');
  assert(imageBlock !== undefined, 'Image block missing from Notion blocks');
  assert(imageBlock.image?.type === 'file_upload', 'Image block must use file_upload');
  assert(imageBlock.image?.file_upload?.id, 'Image block missing file_upload id');
  assert(allBlocks.length <= 40, `Notion page blocks (${allBlocks.length}) exceed compact limit (40)`);
  console.log(`   ✓ Notion page verified: compact count ${allBlocks.length} <= 40, image block attached: file_upload id=${imageBlock.image.file_upload.id}`);

  console.log('\n===========================================================');
  console.log(' ALL RECEIPT PHOTO E2E TESTS PASSED WITH 100% SUCCESS! ');
  console.log('===========================================================');
} finally {
  if (chrome) {
    chrome.page.close();
    chrome.proc.kill();
  }
  if (server) server.kill();
  try {
    await rm(dir, { recursive: true, force: true });
  } catch (e) {}
}
