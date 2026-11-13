/**
 * Headless Chrome E2E verification of Cancel Join Request UX and Navigation Trapping Fix.
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

function resolveChromePath() {
  const envPath = process.env.CHROME_BIN || process.env.CHROME_PATH || process.env.PUPPETEER_EXECUTABLE_PATH;
  if (envPath && existsSync(envPath)) return envPath;

  const platform = process.platform;
  const candidates = [];
  if (platform === 'win32') {
    const programFiles = process.env.ProgramFiles || '';
    const programFilesX86 = process.env['ProgramFiles(x86)'] || '';
    const localAppData = process.env.LOCALAPPDATA || '';
    candidates.push(
      programFiles ? join(programFiles, 'Google', 'Chrome', 'Application', 'chrome.exe') : '',
      programFilesX86 ? join(programFilesX86, 'Google', 'Chrome', 'Application', 'chrome.exe') : '',
      localAppData ? join(localAppData, 'Google', 'Chrome', 'Application', 'chrome.exe') : '',
      programFilesX86 ? join(programFilesX86, 'Microsoft', 'Edge', 'Application', 'msedge.exe') : '',
      programFiles ? join(programFiles, 'Microsoft', 'Edge', 'Application', 'msedge.exe') : ''
    );
  } else {
    candidates.push('/usr/bin/google-chrome-stable', '/usr/bin/google-chrome', '/usr/bin/chromium');
  }

  for (const p of candidates) {
    if (p && existsSync(p)) return p;
  }
  throw new Error('Chrome executable not found.');
}

function resolvePythonPath() {
  const envPath = process.env.PYTHON_BIN || process.env.PYTHON_PATH;
  if (envPath && existsSync(envPath)) return envPath;
  if (process.platform === 'win32') {
    const sysDrive = process.env.SystemDrive || '';
    const py314 = sysDrive ? join(sysDrive, 'Python314', 'python.exe') : '';
    const py312 = sysDrive ? join(sysDrive, 'Python312', 'python.exe') : '';
    if (py314 && existsSync(py314)) return py314;
    if (py312 && existsSync(py312)) return py312;
    return 'python';
  }
  return 'python3';
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

  async waitFor(expr, timeoutMs = 15000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      try {
        const val = await this.evaluate(expr);
        if (val) return val;
      } catch (e) {}
      await new Promise((r) => setTimeout(r, 100));
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
  proc.on('error', (error) => {
    spawnError = error;
  });
  proc.stderr?.on('data', (d) => {
    stderr += d.toString();
  });

  try {
    let target = null;
    for (let i = 0; i < 300; i++) {
      if (spawnError) throw spawnError;
      if (proc.exitCode !== null) {
        throw new Error(`Chrome exited prematurely with code ${proc.exitCode} on port ${port}: ${stderr}`);
      }
      try {
        const selectedPort = Number((await fs.promises.readFile(join(dataDir, 'DevToolsActivePort'), 'utf8')).split('\n')[0]);
        if (!selectedPort) throw Error('Chrome has not published its port');
        const endpoint = `http://127.0.0.1:${selectedPort}/json/list`;
        const res = await fetch(endpoint);
        const list = await res.json();
        target = list.find((t) => t.type === 'page');
        if (target && target.webSocketDebuggerUrl) break;
      } catch (e) {}
      await new Promise((r) => setTimeout(r, 100));
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

function assert(condition, message) {
  if (!condition) {
    throw new Error(`Assertion failed: ${message}`);
  }
}

async function main() {
  console.log('--- Starting Cancel Join UX E2E Verification ---');
  const serverPort = 8097;
  await new Promise((resolve, reject) => {
    const probe = createServer();
    probe.once('error', reject);
    probe.listen(serverPort, '127.0.0.1', () => probe.close(resolve));
  });

  const dir = await mkdtemp(join(tmpdir(), 'settletable-cancel-ux-'));
  const capture = join(dir, 'mock-payload.json');
  fs.writeFileSync(capture, '{}');
  const owner = randomBytes(32).toString('hex');
  const origin = `http://127.0.0.1:${serverPort}`;

  let server, chrome;

  try {
    console.log(`[1] Launching test runner on ${origin}...`);
    server = spawn(
      resolvePythonPath(),
      [
        '-u',
        join(REPO_ROOT, 'tools', 'verify_financial_export_runner.py'),
        '--host',
        '127.0.0.1',
        '--port',
        String(serverPort),
        '--db',
        join(dir, 'test.sqlite'),
        '--mock-notion',
        '--mock-ocr',
      ],
      {
        cwd: REPO_ROOT,
        env: { ...process.env, SETTLETABLE_MOCK_CAPTURE: capture, SETTLETABLE_TEST_OWNER: owner },
      }
    );

    let serverError;
    server.on('error', (error) => {
      serverError = error;
    });
    server.stderr.on('data', (data) => process.stderr.write(data));

    let ready = false;
    for (let i = 0; i < 100; i++) {
      if (serverError) throw serverError;
      if (server.exitCode !== null) throw Error('Loopback server exited');
      try {
        const response = await fetch(origin + '/__financial_test_owner__');
        if (response.ok && (await response.text()) === owner && server.exitCode === null) {
          ready = true;
          break;
        }
      } catch {}
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    assert(ready, 'Loopback server did not start');
    console.log('    Server ready.');

    console.log('[2] Launching Headless Chrome...');
    chrome = await startChrome(resolveChromePath(), 0, join(dir, 'profile'));
    const p = chrome.page;
    const ev = (expression) => p.evaluate(expression);
    const wait = (expression) => p.waitFor(expression, 15000);

    await p.send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false });

    console.log('[3] Creating test meal table...');
    const mealId = 'm_' + randomBytes(4).toString('hex');
    const bootRes = await fetch(`${origin}/api/meals/${mealId}/bootstrap`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-SettleTable-Action': '1',
        Origin: origin,
      },
      body: JSON.stringify({
        participants: [
          { id: 'O', name: 'Alice (Organizer)', organizer: true },
          { id: 'D1', name: 'Bob', organizer: false },
          { id: 'D2', name: 'Charlie', organizer: false },
        ],
      }),
    });
    const bootData = await bootRes.json();
    assert(bootData.ok, 'Failed to bootstrap meal: ' + JSON.stringify(bootData));
    const orgCred = bootData.sessions[0].credential;

    // --- Scenario A: Cancel Request returns to join form with confirmation banner ---
    console.log('[4] Navigating to general join URL /join/' + mealId);
    await p.navigate(`${origin}/join/${mealId}`);
    await wait("document.getElementById('join-name-input')");

    console.log('    Entering name Charlie and submitting join request...');
    await ev(`
      document.getElementById('join-name-input').value = 'Charlie';
      document.getElementById('submit-join-req-btn').click();
    `);

    console.log('    Verifying waiting state UI...');
    await wait("document.getElementById('cancel-join-btn')");
    const descText = await ev("document.querySelector('.card-desc').textContent");
    assert(descText.includes('Charlie'), `Expected Charlie in waiting text, got: ${descText}`);

    const cancelBtnText = await ev("document.getElementById('cancel-join-btn').textContent.trim()");
    assert(cancelBtnText === 'Cancel Request', `Expected button 'Cancel Request', got: ${cancelBtnText}`);

    const cancelHomeBtnText = await ev("document.getElementById('cancel-join-home-btn').textContent.trim()");
    assert(cancelHomeBtnText === 'Cancel & Return to Home', `Expected button 'Cancel & Return to Home', got: ${cancelHomeBtnText}`);

    // Verify organizer sees 1 pending request
    const listRes1 = await fetch(`${origin}/api/meals/${mealId}/join-requests`, {
      headers: { Authorization: `Bearer ${orgCred}` },
    });
    const listData1 = await listRes1.json();
    assert(listData1.join_requests?.length === 1, `Expected 1 pending join request, got: ${listData1.join_requests?.length}`);

    console.log('    Clicking "Cancel Request"...');
    await ev("document.getElementById('cancel-join-btn').click();");

    console.log('    Verifying return to join form with info banner...');
    await wait("document.getElementById('join-name-input')");
    const bannerText = await ev("document.querySelector('.alert-info')?.textContent || ''");
    assert(bannerText.includes('Your join request was cancelled.'), `Expected cancel banner, got: ${bannerText}`);
    console.log('    ✓ Return to join landing with info banner verified.');

    // Verify organizer sees 0 pending requests
    const listRes2 = await fetch(`${origin}/api/meals/${mealId}/join-requests`, {
      headers: { Authorization: `Bearer ${orgCred}` },
    });
    const listData2 = await listRes2.json();
    assert(listData2.join_requests?.length === 0, `Expected 0 pending join requests, got: ${listData2.join_requests?.length}`);
    console.log('    ✓ Participant slot freed on server immediately.');

    // --- Scenario B: Immediate re-request succeeds without 409 conflict ---
    console.log('[5] Submitting join request again as Charlie immediately...');
    await ev(`
      document.getElementById('join-name-input').value = 'Charlie';
      document.getElementById('submit-join-req-btn').click();
    `);
    await wait("document.getElementById('cancel-join-btn')");
    console.log('    ✓ Immediate re-submission succeeded without 409 conflict.');

    // --- Scenario C: "Cancel & Return to Home" cleanly exits path trap to Home ---
    console.log('[6] Clicking "Cancel & Return to Home" from waiting screen...');
    await ev("document.getElementById('cancel-join-home-btn').click();");

    console.log('    Verifying Home screen rendered...');
    await wait("document.getElementById('create-meal-form')");
    const currentPath = await ev('window.location.pathname');
    assert(currentPath === '/' || currentPath === '', `Expected pathname to be '/', got: ${currentPath}`);
    console.log('    ✓ Returned to Home screen and cleared path trap.');

    // --- Scenario D: Navbar Home link from /join/{mealId} cleanly returns to Home ---
    console.log('[7] Testing navbar Home button from /join/{mealId}...');
    await p.navigate(`${origin}/join/${mealId}`);
    await wait("document.getElementById('join-name-input')");

    console.log('    Clicking navbar Home link...');
    await ev("document.getElementById('nav-home-btn').click();");
    await wait("document.getElementById('create-meal-form')");
    const navPath = await ev('window.location.pathname');
    assert(navPath === '/' || navPath === '', `Expected pathname to be '/', got: ${navPath}`);
    console.log('    ✓ Navbar Home button navigates to Home cleanly.');

    // --- Scenario E: Join form Cancel & Return to Home button cleanly returns to Home ---
    console.log('[8] Testing join form Cancel & Return to Home button...');
    await p.navigate(`${origin}/join/${mealId}`);
    await wait("document.getElementById('join-cancel-home-btn')");

    console.log('    Clicking join-cancel-home-btn...');
    await ev("document.getElementById('join-cancel-home-btn').click();");
    await wait("document.getElementById('create-meal-form')");
    const formNavPath = await ev('window.location.pathname');
    assert(formNavPath === '/' || formNavPath === '', `Expected pathname to be '/', got: ${formNavPath}`);
    console.log('    ✓ Join form Cancel & Return to Home button works cleanly.');

    // --- Scenario F: Organizer decline transitions waiting screen to declined state ---
    console.log('[9] Testing organizer decline reaction in requester view...');
    await p.navigate(`${origin}/join/${mealId}`);
    await wait("document.getElementById('join-name-input')");
    await ev(`
      document.getElementById('join-name-input').value = 'Bob';
      document.getElementById('submit-join-req-btn').click();
    `);
    await wait("document.getElementById('cancel-join-btn')");

    const listResBob = await fetch(`${origin}/api/meals/${mealId}/join-requests`, {
      headers: { Authorization: `Bearer ${orgCred}` },
    });
    const bobReqs = (await listResBob.json()).join_requests;
    const bobReq = bobReqs.find((r) => r.display_name === 'Bob');
    assert(bobReq, 'Could not find join request for Bob');

    console.log('    Organizer declining Bob...');
    const declineRes = await fetch(`${origin}/api/meals/${mealId}/join-requests/${bobReq.id}/review`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${orgCred}`,
        'Content-Type': 'application/json',
        'X-SettleTable-Action': '1',
        Origin: origin,
      },
      body: JSON.stringify({ action: 'reject' }),
    });
    assert(declineRes.ok, 'Failed to decline request');

    console.log('    Waiting for requester polling to detect declined status...');
    await wait("document.getElementById('join-status-alert')?.style.display !== 'none'");
    const alertText = await ev("document.getElementById('join-status-alert').textContent");
    assert(alertText.includes('The organizer declined your request'), `Expected decline message, got: ${alertText}`);

    const backBtnText = await ev("document.getElementById('cancel-join-btn').textContent.trim()");
    assert(backBtnText === 'Back to Table Join', `Expected button text 'Back to Table Join', got: ${backBtnText}`);
    console.log('    ✓ Polling detected decline and converted button to "Back to Table Join".');

    console.log('\n=== ALL CANCEL JOIN UX SCENARIOS PASSED (6/6) ===\n');
  } finally {
    if (chrome) {
      chrome.page.close();
      chrome.proc.kill();
    }
    if (server) {
      server.kill();
    }
    try {
      await rm(dir, { recursive: true, force: true });
    } catch {}
  }
}

main().catch((err) => {
  console.error('\n❌ Verification Failed:', err);
  process.exit(1);
});
