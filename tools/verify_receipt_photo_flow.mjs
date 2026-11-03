/**
 * Headless Chrome E2E verification of receipt photo preview, zoom modal,
 * organizer lifecycle controls, finalized view, and Notion export with photo option.
 *
 * Verifies:
 * - CSP compliance: blob: and server-served receipt images load cleanly without violations.
 * - Create Meal ID pattern regex compliance and validation in modern Chromium.
 * - Actual image decoding: complete === true, naturalWidth > 0, naturalHeight > 0.
 * - Preview stages: staged OCR thumbnail (blob:), zoom modal (blob:), attached card,
 *   refreshed page (server-served), and finalized receipt viewer.
 */
import { spawn } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import fs, { existsSync } from 'node:fs';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path, { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:net';
import zlib from 'node:zlib';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function makeMinimalPngBuffer(width = 100, height = 100) {
  const sig = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  function makeChunk(type, data) {
    const len = Buffer.alloc(4);
    len.writeUInt32BE(data.length, 0);
    const typeBuf = Buffer.from(type, 'ascii');
    const toCrc = Buffer.concat([typeBuf, data]);
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(zlib.crc32(toCrc), 0);
    return Buffer.concat([len, toCrc, crc]);
  }
  const ihdrData = Buffer.alloc(13);
  ihdrData.writeUInt32BE(width, 0);
  ihdrData.writeUInt32BE(height, 4);
  ihdrData[8] = 8;
  ihdrData[9] = 2;
  ihdrData[10] = 0;
  ihdrData[11] = 0;
  ihdrData[12] = 0;
  const ihdr = makeChunk('IHDR', ihdrData);

  const scanlines = Buffer.alloc(height * (1 + width * 3));
  for (let y = 0; y < height; y++) {
    const rowOffset = y * (1 + width * 3);
    scanlines[rowOffset] = 0;
    for (let x = 0; x < width; x++) {
      scanlines[rowOffset + 1 + x * 3] = 0xff; // R
      scanlines[rowOffset + 1 + x * 3 + 1] = 0x00; // G
      scanlines[rowOffset + 1 + x * 3 + 2] = 0x00; // B
    }
  }
  const idat = makeChunk('IDAT', zlib.deflateSync(scanlines));
  const iend = makeChunk('IEND', Buffer.alloc(0));
  return Buffer.concat([sig, ihdr, idat, iend]);
}

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
      'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
      'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
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
    this.consoleErrors = [];
    this.ready = new Promise((resolve, reject) => {
      this.ws.onopen = resolve;
      this.ws.onerror = reject;
    });
    this.ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.method === 'Page.javascriptDialogOpening') {
        this.send('Page.handleJavaScriptDialog', { accept: true });
      }
      if (msg.method === 'Runtime.consoleAPICalled') {
        const type = msg.params.type;
        const text = (msg.params.args || []).map(a => a.value || a.description || '').join(' ');
        if (type === 'error' || text.includes('Content Security Policy') || text.includes('not a valid regular expression')) {
          this.consoleErrors.push(text);
        }
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

  async evaluate(expr, ...args) {
    const exprStr = typeof expr === 'function'
      ? `(${expr.toString()})(${args.map(a => JSON.stringify(a)).join(',')})`
      : expr;
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

  async attachPageDiagnostics() {
    await this.evaluate(() => {
      window.__cspViolations = [];
      window.__imageErrors = [];
      window.addEventListener('securitypolicyviolation', (e) => {
        window.__cspViolations.push({
          blockedURI: e.blockedURI,
          violatedDirective: e.violatedDirective,
          originalPolicy: e.originalPolicy,
        });
      });
      window.addEventListener('error', (e) => {
        if (e.target && e.target.tagName === 'IMG') {
          window.__imageErrors.push({
            src: e.target.src,
            id: e.target.id,
            className: e.target.className,
          });
        }
      }, true);
    });
  }

  async navigate(url) {
    await this.send('Page.navigate', { url });
    await this.waitFor(() => document.readyState === 'complete');
    await this.attachPageDiagnostics();
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

async function assertImageLoaded(page, selector, description) {
  const selJson = JSON.stringify(selector);
  await page.waitFor(`(() => {
    const img = document.querySelector(${selJson});
    return Boolean(img && img.complete);
  })()`);

  const imgState = await page.evaluate(`(() => {
    const img = document.querySelector(${selJson});
    if (!img) return null;
    return {
      complete: img.complete,
      naturalWidth: img.naturalWidth,
      naturalHeight: img.naturalHeight,
      src: img.src,
      currentSrc: img.currentSrc,
    };
  })()`);

  if (!imgState) throw new Error(`${description}: Image element '${selector}' not found`);
  if (!imgState.complete) throw new Error(`${description}: Image complete is false`);
  if (imgState.naturalWidth <= 0 || imgState.naturalHeight <= 0) {
    throw new Error(`${description}: Image failed to decode: naturalWidth=${imgState.naturalWidth}, naturalHeight=${imgState.naturalHeight}, src=${imgState.src}`);
  }

  const errors = await page.evaluate(() => ({
    csp: window.__cspViolations || [],
    imgErrors: window.__imageErrors || [],
  }));
  if (errors.csp.length > 0) {
    throw new Error(`${description}: CSP violation detected: ${JSON.stringify(errors.csp)}`);
  }
  if (errors.imgErrors.length > 0) {
    throw new Error(`${description}: Image loading error detected: ${JSON.stringify(errors.imgErrors)}`);
  }
  return imgState;
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

  console.log('[1/8] Verifying Create Meal ID pattern regex compliance and validation...');
  await page.send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false });
  await page.navigate(origin + '/');
  await page.waitFor(() => document.getElementById('create-meal-form') !== null);

  // Check HTML pattern attribute value and browser regular expression compilation
  const patternValidation = await page.evaluate(() => {
    const input = document.getElementById('create-meal-id');
    const pat = input.getAttribute('pattern');
    
    // Test valid inputs
    const validSamples = ['dinner-friday', 'lunch_room-1', 'meal-2026', 'ABC_123-x'];
    const validResults = validSamples.map(val => {
      input.value = val;
      return input.checkValidity();
    });

    // Test invalid inputs
    const invalidSamples = ['dinner@friday', 'dinner friday', 'lunch!', 'room#1', 'meal/1'];
    const invalidResults = invalidSamples.map(val => {
      input.value = val;
      return input.checkValidity();
    });

    return {
      patternAttribute: pat,
      validResults,
      invalidResults,
    };
  });

  assert(patternValidation.patternAttribute === '[A-Za-z0-9_\\-]+', `Expected pattern '[A-Za-z0-9_\\-]', got '${patternValidation.patternAttribute}'`);
  assert(patternValidation.validResults.every(r => r === true), 'Valid hyphenated/underscored meal IDs must pass validity');
  assert(patternValidation.invalidResults.every(r => r === false), 'Invalid characters (@, space, !, #, /) must fail validity');

  // Verify no regex compilation errors were raised in browser console
  const regexConsoleErrors = page.consoleErrors.filter(e => e.includes('not a valid regular expression'));
  assert(regexConsoleErrors.length === 0, `Pattern regex compilation error in console: ${regexConsoleErrors.join('; ')}`);
  console.log('   ✓ Create Meal ID pattern regex verified ([A-Za-z0-9_\\-]+): valid hyphenated/underscore accepted, invalid rejected, 0 console regex errors');

  console.log('[2/8] Bootstrapping room with hyphenated Meal ID via UI in browser...');
  const mealId = 'receipt-photo-e2e';
  await page.evaluate(`
    document.getElementById('create-meal-id').value = '${mealId}';
    document.getElementById('create-org-name').value = 'Alice';
    document.getElementById('create-diners').value = 'Bob';
    document.getElementById('create-meal-form').requestSubmit();
  `);
  await page.waitFor(() => document.getElementById('ocr-upload-btn') !== null);
  console.log('   ✓ Organizer view loaded');

  console.log('[3/8] Uploading genuine decodable PNG to trigger OCR and candidate staging...');
  const pngBuffer = makeMinimalPngBuffer(100, 100);
  const pngBytes = Array.from(pngBuffer);

  await page.evaluate((bytes) => {
    const b = new Uint8Array(bytes);
    const d = new DataTransfer();
    d.items.add(new File([b], 'synthetic.png', { type: 'image/png' }));
    const x = document.getElementById('ocr-file-input');
    x.files = d.files;
    x.dispatchEvent(new Event('change', { bubbles: true }));
  }, pngBytes);

  await page.waitFor(() => document.getElementById('ocr-candidate-card') !== null);
  console.log('   ✓ OCR candidate card displayed');

  // Verify staged OCR thumbnail preview (temporary blob: URL)
  const stagedThumb = await assertImageLoaded(page, '.ocr-source-preview-bar img', 'Staged OCR thumbnail (blob:)');
  assert(stagedThumb.src.startsWith('blob:'), `Staged OCR thumbnail expected blob: URL, got ${stagedThumb.src}`);
  assert(stagedThumb.naturalWidth === 100 && stagedThumb.naturalHeight === 100, 'Staged OCR thumbnail image decoded to 100x100');
  console.log('   ✓ Staged OCR source preview decoded cleanly via blob: URL without CSP errors (natural 100x100)');

  console.log('[4/8] Testing Receipt Photo Fullscreen/Zoom Modal with staged blob: preview...');
  await page.evaluate(() => document.getElementById('ocr-source-zoom-btn').click());
  await page.waitFor(() => {
    const modal = document.getElementById('receipt-modal');
    return modal && modal.style.display === 'flex';
  });

  const stagedModalImg = await assertImageLoaded(page, '#receipt-modal-img', 'Zoom modal with staged blob');
  assert(stagedModalImg.src.startsWith('blob:'), `Modal expected blob: URL, got ${stagedModalImg.src}`);
  assert(stagedModalImg.naturalWidth === 100 && stagedModalImg.naturalHeight === 100, 'Modal image decoded to 100x100');
  console.log('   ✓ Zoom modal opened (display: flex) and rendered blob: image cleanly');

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

  console.log('[5/8] Accepting candidate and verifying attached photo card and modal...');
  await page.evaluate(() => document.getElementById('ocr-accept-btn').click());
  await page.waitFor(() => document.getElementById('receipt-photo-container') !== null);

  const cardThumb = await assertImageLoaded(page, '#receipt-card-thumb', 'Attached receipt photo card');
  assert(cardThumb.naturalWidth === 100 && cardThumb.naturalHeight === 100, 'Attached card image decoded to 100x100');
  console.log('   ✓ Attached receipt photo card rendered and decoded image cleanly');

  // Open modal via View & Zoom button on the card, and close via Close button (✕)
  await page.evaluate(() => document.getElementById('view-photo-modal-btn').click());
  await page.waitFor(() => {
    const modal = document.getElementById('receipt-modal');
    return modal && modal.style.display === 'flex';
  });
  const cardModalImg = await assertImageLoaded(page, '#receipt-modal-img', 'Zoom modal from attached card');
  assert(cardModalImg.naturalWidth === 100 && cardModalImg.naturalHeight === 100, 'Modal image decoded to 100x100');

  await page.evaluate(() => document.getElementById('receipt-modal-close').click());
  await page.waitFor(() => {
    const modal = document.getElementById('receipt-modal');
    return !modal || modal.style.display === 'none';
  });
  console.log('   ✓ Modal opened from card and closed via ✕ button');

  console.log('[6/8] Verifying refreshed page loads authenticated server-served photo without blob/CSP errors...');
  // Reload page to test server-served endpoint (/api/meals/{mealId}/receipt/photo)
  await page.navigate(origin + '/');
  await page.waitFor(() => document.getElementById('open-meal-form') !== null);
  await page.evaluate((id) => {
    document.getElementById('open-meal-id').value = id;
    document.getElementById('open-meal-form').requestSubmit();
  }, mealId);
  await page.waitFor(() => document.getElementById('receipt-photo-container') !== null);

  const refreshedThumb = await assertImageLoaded(page, '#receipt-card-thumb', 'Refreshed attached photo card (server-served)');
  assert(refreshedThumb.src.includes(`/api/meals/${mealId}/receipt/photo`), `Refreshed page must use server-served photo endpoint, got: ${refreshedThumb.src}`);
  assert(refreshedThumb.naturalWidth === 100 && refreshedThumb.naturalHeight === 100, 'Server-served photo decoded to 100x100');

  // Open modal on refreshed page
  await page.evaluate(() => document.getElementById('view-photo-modal-btn').click());
  await page.waitFor(() => {
    const modal = document.getElementById('receipt-modal');
    return modal && modal.style.display === 'flex';
  });
  const refreshedModalImg = await assertImageLoaded(page, '#receipt-modal-img', 'Refreshed zoom modal (server-served)');
  assert(refreshedModalImg.src.includes(`/api/meals/${mealId}/receipt/photo`), `Refreshed modal must use server endpoint, got: ${refreshedModalImg.src}`);
  await page.evaluate(() => document.getElementById('receipt-modal-close').click());
  console.log('   ✓ Authenticated server-served receipt photo rendered and zoomed cleanly on refreshed page');

  console.log('[7/8] Reviewing receipt, allocating items, and finalizing meal...');
  await page.waitFor(() => !state.mutationActive && state.snapshot?.receipt?.items?.length > 0);
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

  // Verify finalized photo preview and zoom
  const finalizedThumb = await assertImageLoaded(page, '#finalized-receipt-thumb-btn img', 'Finalized receipt thumbnail');
  assert(finalizedThumb.src.includes(`/api/meals/${mealId}/receipt/photo`), `Finalized thumb must use server endpoint, got: ${finalizedThumb.src}`);
  assert(finalizedThumb.naturalWidth === 100 && finalizedThumb.naturalHeight === 100, 'Finalized thumbnail decoded to 100x100');

  await page.evaluate(() => document.getElementById('view-finalized-photo-btn').click());
  await page.waitFor(() => {
    const modal = document.getElementById('receipt-modal');
    return modal && modal.style.display === 'flex';
  });
  const finalizedModalImg = await assertImageLoaded(page, '#receipt-modal-img', 'Finalized zoom modal');
  assert(finalizedModalImg.naturalWidth === 100 && finalizedModalImg.naturalHeight === 100, 'Finalized modal image decoded to 100x100');
  await page.evaluate(() => document.getElementById('receipt-modal-close').click());
  console.log('   ✓ Finalized receipt photo accessible and zoomed cleanly');

  console.log('[8/8] Testing Notion export with photo option and view-only sharing guidance...');
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

  // Confirm zero CSP violations and zero image errors occurred during the entire test
  const finalViolations = await page.evaluate(() => window.__cspViolations || []);
  assert(finalViolations.length === 0, `CSP violations occurred during test: ${JSON.stringify(finalViolations)}`);
  const finalConsoleErrors = page.consoleErrors;
  assert(finalConsoleErrors.length === 0, `Browser console errors detected: ${finalConsoleErrors.join(' | ')}`);

  console.log('\n===========================================================');
  console.log(' ALL RECEIPT PHOTO & PATTERN TESTS PASSED WITH 100% SUCCESS!');
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
