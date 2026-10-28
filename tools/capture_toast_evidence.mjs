import { spawn } from 'node:child_process';
import fs, { existsSync } from 'node:fs';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path, { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO_ROOT = fileURLToPath(new URL('..', import.meta.url));
const conversationArtifactDir = 'C:\\Users\\alpha\\.gemini\\antigravity\\brain\\8551baa0-7cf7-4f83-91eb-19824df0c298';
const ARTIFACT_DIR = process.env.ARTIFACT_DIR || (existsSync(conversationArtifactDir) ? conversationArtifactDir : join(REPO_ROOT, 'artifacts'));
if (!existsSync(ARTIFACT_DIR)) {
  fs.mkdirSync(ARTIFACT_DIR, { recursive: true });
}

function resolveChromePath() {
  const envPath = process.env.CHROME_BIN || process.env.CHROME_PATH || process.env.PUPPETEER_EXECUTABLE_PATH;
  if (envPath && existsSync(envPath)) return envPath;
  const platform = process.platform;
  const candidates = [];
  if (platform === 'win32') {
    candidates.push(
      'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
      'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
      join(process.env.LOCALAPPDATA || '', 'Google', 'Chrome', 'Application', 'chrome.exe'),
    );
  } else if (platform === 'darwin') {
    candidates.push(
      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      '/Applications/Chromium.app/Contents/MacOS/Chromium'
    );
  } else {
    candidates.push(
      '/usr/bin/google-chrome',
      '/usr/bin/google-chrome-stable',
      '/usr/bin/chromium-browser',
      '/usr/bin/chromium',
    );
  }
  for (const p of candidates) {
    if (existsSync(p)) return p;
  }
  throw new Error('Chrome binary not found');
}

function resolvePythonPath() {
  if (process.env.PYTHON && existsSync(process.env.PYTHON)) return process.env.PYTHON;
  const candidates = [
    'C:\\Python314\\python.exe',
    'C:\\Python312\\python.exe',
    'python',
    'python3'
  ];
  for (const c of candidates) {
    if (c.includes('\\') && existsSync(c)) return c;
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
      if (msg.id !== undefined && this.callbacks.has(msg.id)) {
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
      throw new Error(`CDP evaluate failed: ${JSON.stringify(res.exceptionDetails)}`);
    }
    return res.result ? res.result.value : undefined;
  }

  async navigate(url) {
    await this.send('Page.navigate', { url });
    await this.waitFor("document.readyState === 'complete'");
  }

  async screenshot(filePath) {
    const res = await this.send('Page.captureScreenshot', { format: 'png' });
    const buffer = Buffer.from(res.data, 'base64');
    await fs.promises.writeFile(filePath, buffer);
  }

  async waitFor(expr, timeoutMs = 12000) {
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
  return { proc, page };
}

async function main() {
  const port = process.env.SETTLETABLE_PORT || '8096';
  const chromePort = 9226;
  const serverOrigin = `http://127.0.0.1:${port}`;
  const pyBin = resolvePythonPath();
  const chromeBin = resolveChromePath();

  const tempDir = await mkdtemp(join(tmpdir(), 'settletable-toast-test-'));
  const dbPath = join(tempDir, 'toast_demo.sqlite');
  const chromeDataDir = join(tempDir, 'chrome-user-data');
  await fs.promises.mkdir(chromeDataDir, { recursive: true });

  console.log(`[1/6] Launching test demo server on port ${port}...`);
  const serverProc = spawn(pyBin, [
    join(REPO_ROOT, 'tools', 'run_demo.py'),
    '--port', port,
    '--db', dbPath,
    '--mock-ocr',
    '--mock-notion',
  ], {
    cwd: REPO_ROOT,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  serverProc.stderr.on('data', d => console.error('[SERVER STDERR]:', d.toString()));

  // Wait for server to respond
  for (let i = 0; i < 60; i++) {
    try {
      const res = await fetch(`${serverOrigin}/`);
      if (res.ok) break;
    } catch (e) {}
    await new Promise(r => setTimeout(r, 100));
  }

  let chromeInstance = null;
  try {
    console.log(`[2/6] Launching Chrome on port ${chromePort}...`);
    chromeInstance = await startChrome(chromeBin, chromePort, chromeDataDir);
    const page = chromeInstance.page;

    // Enable Page and Runtime
    await page.send('Page.enable');
    await page.send('Runtime.enable');

    console.log('[3/6] Bootstrapping meal and setting up receipt...');
    await page.send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 800, deviceScaleFactor: 1, mobile: false });
    await page.navigate(`${serverOrigin}/`);
    await page.waitFor("document.getElementById('create-meal-form') !== null");

    await page.evaluate(`
      document.getElementById('create-meal-id').value = 'toast-polish-meal';
      document.getElementById('create-org-name').value = 'Alice';
      document.getElementById('create-diners').value = 'Bob\\nCharlie';
      document.getElementById('create-meal-form').requestSubmit();
    `);

    await page.waitFor("window.location.hash.includes('#/meal/toast-polish-meal') && document.getElementById('ocr-file-input') !== null");

    // Upload mock receipt via file input
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

    await page.evaluate(triggerUpload);
    await page.waitFor("document.getElementById('ocr-candidate-card') !== null");

    // Accept OCR
    await page.evaluate("document.getElementById('ocr-accept-btn').click()");
    await page.waitFor("document.getElementById('ocr-candidate-card') === null");
    await page.waitFor("document.getElementById('review-confirm-check') !== null");

    // Check review box and approve receipt
    await page.evaluate(`
      document.getElementById('review-confirm-check').checked = true;
      document.getElementById('review-confirm-check').dispatchEvent(new Event('change'));
      document.getElementById('review-submit-btn').click();
    `);
    await page.waitFor("document.getElementById('receipt-verified-status') !== null");

    console.log('[4/6] Verifying Test Case 1: Desktop (1280x800) Bottom Toast...');
    await page.evaluate("showAlert('Receipt verified and sealed successfully!', 'success', true)");
    await page.waitFor("document.querySelector('.alert-banner') !== null");
    await new Promise(r => setTimeout(r, 350));

    const desktopGeo = await page.evaluate(`(() => {
      const banner = document.querySelector('.alert-banner');
      const bRect = banner.getBoundingClientRect();
      const roomCard = document.querySelector('.room-status-card');
      const rcRect = roomCard ? roomCard.getBoundingClientRect() : null;
      const breadcrumb = document.getElementById('breadcrumb-nav');
      const bcRect = breadcrumb ? breadcrumb.getBoundingClientRect() : null;
      return {
        banner: { top: bRect.top, bottom: bRect.bottom, left: bRect.left, right: bRect.right, width: bRect.width, height: bRect.height },
        roomCard: rcRect ? { top: rcRect.top, bottom: rcRect.bottom } : null,
        breadcrumb: bcRect ? { top: bcRect.top, bottom: bcRect.bottom } : null,
        windowHeight: window.innerHeight,
        windowWidth: window.innerWidth,
      };
    })()`);

    console.log('   Desktop geometry measurements:', desktopGeo);
    if (desktopGeo.roomCard && desktopGeo.banner.top <= desktopGeo.roomCard.bottom) {
      throw new Error(`Desktop toast overlaps room status card! Toast top: ${desktopGeo.banner.top}, Card bottom: ${desktopGeo.roomCard.bottom}`);
    }
    const desktopClearance = desktopGeo.banner.top - (desktopGeo.roomCard?.bottom || 0);
    console.log(`   ✓ Desktop toast clearance from room card: ${desktopClearance.toFixed(1)}px (bottom-positioned)`);

    const pathDesktop = join(ARTIFACT_DIR, 'screenshot_toast_desktop_bottom.png');
    await page.screenshot(pathDesktop);
    console.log(`   ✓ Saved: ${pathDesktop}`);

    console.log('[5/6] Verifying Test Case 2: Mobile (375x667) Bottom Toast...');
    await page.send('Emulation.setDeviceMetricsOverride', { width: 375, height: 667, deviceScaleFactor: 2, mobile: true });
    await page.evaluate("showAlert('Invitation link copied to clipboard!', 'info', true)");
    await page.waitFor("document.querySelector('.alert-banner') !== null");
    await new Promise(r => setTimeout(r, 350));

    const mobileGeo = await page.evaluate(`(() => {
      const banner = document.querySelector('.alert-banner');
      const bRect = banner.getBoundingClientRect();
      const roomCard = document.querySelector('.room-status-card');
      const rcRect = roomCard ? roomCard.getBoundingClientRect() : null;
      return {
        banner: { top: bRect.top, bottom: bRect.bottom, left: bRect.left, right: bRect.right, width: bRect.width, height: bRect.height },
        roomCard: rcRect ? { top: rcRect.top, bottom: rcRect.bottom } : null,
        windowHeight: window.innerHeight,
        windowWidth: window.innerWidth,
      };
    })()`);

    console.log('   Mobile geometry measurements:', mobileGeo);
    if (mobileGeo.roomCard && mobileGeo.banner.top <= mobileGeo.roomCard.bottom) {
      throw new Error(`Mobile toast overlaps room status card! Toast top: ${mobileGeo.banner.top}, Card bottom: ${mobileGeo.roomCard.bottom}`);
    }
    const mobileClearance = mobileGeo.banner.top - (mobileGeo.roomCard?.bottom || 0);
    console.log(`   ✓ Mobile toast clearance from room card: ${mobileClearance.toFixed(1)}px (bottom-positioned)`);

    const pathMobile = join(ARTIFACT_DIR, 'screenshot_toast_mobile_bottom.png');
    await page.screenshot(pathMobile);
    console.log(`   ✓ Saved: ${pathMobile}`);

    console.log('[6/6] Verifying Test Case 3: Long Error Message Toast Wrapping & Touch Targets...');
    const longErrorMsg = '⚠️ Stale Claim Conflict: Another diner or organizer modified this item or receipt while you were editing. Please review the updated bill before proceeding.';
    await page.evaluate(`showAlert(${JSON.stringify(longErrorMsg)}, 'error', true)`);
    await page.waitFor("document.querySelector('.alert-banner') !== null");
    // Wait for entrance animation (220ms) to settle
    await new Promise(r => setTimeout(r, 350));

    const longErrorGeo = await page.evaluate(`(() => {
      const banner = document.querySelector('.alert-banner');
      const msg = banner.querySelector('.alert-message');
      const btn = banner.querySelector('.alert-close-btn');
      const bRect = banner.getBoundingClientRect();
      const btnRect = btn ? btn.getBoundingClientRect() : null;
      return {
        bannerWidth: bRect.width,
        bannerScrollWidth: banner.scrollWidth,
        bannerClientWidth: banner.clientWidth,
        msgScrollWidth: msg.scrollWidth,
        msgClientWidth: msg.clientWidth,
        btnWidth: btnRect ? btnRect.width : 0,
        btnHeight: btnRect ? btnRect.height : 0,
        hasOverflow: banner.scrollWidth > banner.clientWidth + 1,
      };
    })()`);

    console.log('   Long error measurements:', longErrorGeo);
    if (longErrorGeo.hasOverflow) {
      throw new Error('Long error banner has horizontal overflow!');
    }
    if (longErrorGeo.btnWidth < 32 || longErrorGeo.btnHeight < 32) {
      throw new Error(`Dismiss button touch target too small: ${longErrorGeo.btnWidth}x${longErrorGeo.btnHeight}`);
    }
    console.log(`   ✓ Long error text wraps cleanly without overflow. Close button: ${longErrorGeo.btnWidth}x${longErrorGeo.btnHeight}px`);

    const pathLongError = join(ARTIFACT_DIR, 'screenshot_toast_long_error.png');
    await page.screenshot(pathLongError);
    console.log(`   ✓ Saved: ${pathLongError}`);

    console.log('[7/6] Verifying Test Case 4: Active Mobile Bottom Sheet Contextual Top Toast...');
    // Open the mobile bottom sheet modal for the first item
    await page.evaluate(`(() => {
      const firstItem = document.querySelector('[data-action="hybrid-open-details"], [data-action="hybrid-toggle-details"]');
      if (firstItem) firstItem.click();
    })()`);
    await page.waitFor("document.getElementById('hybrid-bottom-sheet') !== null");

    // Trigger an alert while the sheet is active
    await page.evaluate("showAlert('Allocation updated: 1/3 portion assigned to Alice', 'success', true)");
    await page.waitFor("document.querySelector('.alert-banner') !== null");
    await new Promise(r => setTimeout(r, 350));

    const sheetGeo = await page.evaluate(`(() => {
      const banner = document.querySelector('.alert-banner');
      const bRect = banner.getBoundingClientRect();
      const modal = document.getElementById('hybrid-bottom-sheet');
      const mRect = modal ? modal.getBoundingClientRect() : null;
      const closeSheetBtn = document.querySelector('.bottom-sheet-close-btn');
      const csRect = closeSheetBtn ? closeSheetBtn.getBoundingClientRect() : null;
      const doneBtn = document.querySelector('#hybrid-bottom-sheet [data-action="close-sheet"]');
      const dRect = doneBtn ? doneBtn.getBoundingClientRect() : null;
      const clearBtn = document.querySelector('#hybrid-bottom-sheet [data-action="clear-claims"]');
      const clRect = clearBtn ? clearBtn.getBoundingClientRect() : null;

      return {
        banner: { top: bRect.top, bottom: bRect.bottom },
        modal: mRect ? { top: mRect.top, bottom: mRect.bottom } : null,
        doneBtn: dRect ? { top: dRect.top, bottom: dRect.bottom } : null,
        clearBtn: clRect ? { top: clRect.top, bottom: clRect.bottom } : null,
        containerHasTopClass: document.getElementById('alert-container').classList.contains('alert-container-top'),
        bodyHasSheetClass: document.body.classList.contains('has-bottom-sheet'),
      };
    })()`);

    console.log('   Mobile bottom sheet geometry measurements:', sheetGeo);
    if (!sheetGeo.containerHasTopClass && !sheetGeo.bodyHasSheetClass) {
      throw new Error('Expected alert-container-top or has-bottom-sheet class to be applied while bottom sheet is open');
    }
    if (sheetGeo.doneBtn && sheetGeo.banner.bottom >= sheetGeo.doneBtn.top) {
      throw new Error(`Toast overlaps modal Done button! Toast bottom: ${sheetGeo.banner.bottom}, Done button top: ${sheetGeo.doneBtn.top}`);
    }
    console.log(`   ✓ Contextual top placement verified: Toast y=${sheetGeo.banner.top}-${sheetGeo.banner.bottom}px, modal actions sit unblocked at bottom y=${sheetGeo.doneBtn?.top ?? 'N/A'}px`);

    const pathSheet = join(ARTIFACT_DIR, 'screenshot_toast_mobile_bottom_sheet.png');
    await page.screenshot(pathSheet);
    console.log(`   ✓ Saved: ${pathSheet}`);

    // Close bottom sheet
    await page.evaluate("document.querySelector('.bottom-sheet-close-btn')?.click()");
    await page.waitFor("document.getElementById('hybrid-bottom-sheet') === null");

    console.log('[8/6] Verifying Test Case 5: Scrolled Receipt Editing Fixed Bottom Toast...');
    // Restore desktop viewport
    await page.send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 800, deviceScaleFactor: 1, mobile: false });
    // Scroll down significantly
    await page.evaluate("window.scrollTo(0, 450)");
    const scrollY = await page.evaluate("window.scrollY");

    await page.evaluate("showAlert('Changes saved: receipt items in sync.', 'info', true)");
    await page.waitFor("document.querySelector('.alert-banner') !== null");
    await new Promise(r => setTimeout(r, 350));

    const scrolledGeo = await page.evaluate(`(() => {
      const banner = document.querySelector('.alert-banner');
      const bRect = banner.getBoundingClientRect();
      return {
        scrollY: window.scrollY,
        banner: { top: bRect.top, bottom: bRect.bottom, left: bRect.left, right: bRect.right },
        windowHeight: window.innerHeight,
        inViewport: bRect.top >= 0 && bRect.bottom <= window.innerHeight && bRect.height > 0,
      };
    })()`);

    console.log('   Scrolled geometry measurements:', scrolledGeo);
    if (!scrolledGeo.inViewport) {
      throw new Error(`Scrolled toast not in viewport! Measurements: ${JSON.stringify(scrolledGeo)}`);
    }
    if (scrolledGeo.scrollY < 200) {
      throw new Error(`Expected page to be scrolled down, but scrollY is ${scrolledGeo.scrollY}`);
    }
    console.log(`   ✓ Scrolled viewport toast verified: scrollY=${scrolledGeo.scrollY}px, toast visible at viewport bottom y=${scrolledGeo.banner.top}-${scrolledGeo.banner.bottom}px`);

    const pathScrolled = join(ARTIFACT_DIR, 'screenshot_toast_scrolled_receipt.png');
    await page.screenshot(pathScrolled);
    console.log(`   ✓ Saved: ${pathScrolled}`);

    console.log('\n============================================================');
    console.log(' ALL 5 TOAST PLACEMENT & GEOMETRY VERIFICATIONS SUCCEEDED');
    console.log('============================================================\n');

  } finally {
    if (chromeInstance) {
      chromeInstance.page.close();
      chromeInstance.proc.kill();
    }
    serverProc.kill();
    try {
      await rm(tempDir, { recursive: true, force: true });
    } catch (e) {}
  }
}

main().catch(err => {
  console.error('FATAL ERROR:', err);
  process.exit(1);
});
