/**
 * Headless Chrome E2E verification of Notion Sharing and Post-Finalization Invitation UX.
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

function assert(condition, message) {
  if (!condition) {
    throw new Error(`Assertion failed: ${message}`);
  }
}

async function main() {
  const serverPort = 8092;
  await new Promise((resolve, reject) => {
    const probe = createServer();
    probe.once('error', reject);
    probe.listen(serverPort, '127.0.0.1', () => probe.close(resolve));
  });

  const dir = await mkdtemp(join(tmpdir(), 'settletable-notion-test-'));
  const capture = join(dir, 'mock-payload.json');
  const owner = randomBytes(32).toString('hex');
  const origin = `http://127.0.0.1:${serverPort}`;

  let server, chrome;

  try {
    server = spawn(resolvePythonPath(), [
      '-u', join(REPO_ROOT, 'tools', 'verify_financial_export_runner.py'),
      '--host', '127.0.0.1', '--port', String(serverPort), '--db', join(dir, 'test.sqlite'),
      '--mock-notion', '--mock-ocr',
    ], {
      cwd: REPO_ROOT,
      env: { ...process.env, SETTLETABLE_MOCK_CAPTURE: capture, SETTLETABLE_TEST_OWNER: owner }
    });

    let serverError;
    server.on('error', error => { serverError = error; });
    server.stderr.on('data', data => process.stderr.write(data));

    let ready = false;
    for (let i = 0; i < 100; i++) {
      if (serverError) throw serverError;
      if (server.exitCode !== null) throw Error('Loopback server exited');
      try {
        const response = await fetch(origin + '/__financial_test_owner__');
        if (response.ok && await response.text() === owner && server.exitCode === null) {
          ready = true;
          break;
        }
      } catch {}
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    assert(ready, 'Loopback server did not start');

    chrome = await startChrome(resolveChromePath(), 0, join(dir, 'profile'));
    const p = chrome.page;
    const ev = expression => p.evaluate(expression);
    const wait = expression => p.waitFor(expression, 15000);

    await p.send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false });
    await p.navigate(origin + '/');
    await wait("document.getElementById('create-meal-form')");

    // 1. Create meal room
    await ev(`
      document.getElementById('create-meal-id').value = 'notion-sharing-ux-test';
      document.getElementById('create-org-name').value = 'Alice';
      document.getElementById('create-diners').value = 'Bob, Charlie';
      document.getElementById('create-meal-form').requestSubmit();
    `);
    await wait("state.mealId === 'notion-sharing-ux-test' && state.snapshot");
    console.log('✓ Meal room created: notion-sharing-ux-test');

    // 2. Verify "Sharing & Access" section rendered pre-finalization
    await wait("document.getElementById('sharing-access-section')");
    const preSharingSection = await ev(`(() => {
      const sec = document.getElementById('sharing-access-section');
      return {
        visible: !!sec && !sec.hidden,
        hasDinerSubsection: !!document.getElementById('invitation-hub-card'),
        hasNotionSubsection: !!document.getElementById('sharing-notion-card'),
        hasRecoverySubsection: !!document.getElementById('sharing-recovery-card'),
        recoveryWarningPresent: sec ? (sec.innerText.includes('NEVER share with diners') || sec.innerText.includes('Keep this link private')) : false
      };
    })()`);
    assert(preSharingSection.visible, 'Sharing & Access section must be visible to organizer');
    assert(preSharingSection.hasDinerSubsection, 'Subsection 1 (Invite Diners) must exist');
    assert(preSharingSection.hasNotionSubsection, 'Subsection 2 (Share Notion Report) must exist');
    assert(preSharingSection.hasRecoverySubsection, 'Subsection 3 (Organizer Recovery) must exist');
    assert(preSharingSection.recoveryWarningPresent, 'Recovery link warning must be present');
    console.log('✓ Sharing & Access card verified pre-finalization with 3 distinct subsections');

    // 3. Issue personal diner invite for Bob (D1)
    await ev(`document.querySelector('.issue-invite-btn[data-id="D1"]').click()`);
    await wait("document.querySelector('.copy-invite-btn[data-part=\"D1\"]')");
    const bobInviteLink = await ev("state.issuedTokens['D1']");
    assert(bobInviteLink && bobInviteLink.includes('/#/invite/'), `Valid invite URL expected: ${bobInviteLink}`);
    console.log(`✓ Personal diner invitation issued for Bob: ${bobInviteLink}`);

    // 4. Add receipt items and finalize meal
    await ev(`
      document.getElementById('new-item-label').value = 'Steak';
      document.getElementById('new-item-qty').value = '1';
      document.getElementById('new-item-price').value = '25.00';
      document.getElementById('add-item-form').requestSubmit();
    `);
    await wait("state.snapshot.receipt.items.length === 1");

    await ev(`
      document.getElementById('new-item-label').value = 'Salad';
      document.getElementById('new-item-qty').value = '1';
      document.getElementById('new-item-price').value = '25.00';
      document.getElementById('add-item-form').requestSubmit();
    `);
    await wait("state.snapshot.receipt.items.length === 2");

    // Assign steak to Alice (O) and salad to Bob (D1)
    const firstItemId = await ev("state.snapshot.receipt.items[0].id");
    const secondItemId = await ev("state.snapshot.receipt.items[1].id");
    await ev(`document.querySelector('[data-action="hybrid-quick-assign"][data-item="${firstItemId}"][data-target="O"]').click()`);
    await wait(`state.snapshot.claims.some(c => c.participant_id === 'O' && c.item_id === '${firstItemId}')`);
    await ev(`document.querySelector('[data-action="hybrid-quick-assign"][data-item="${secondItemId}"][data-target="D1"]').click()`);
    await wait(`state.snapshot.claims.some(c => c.participant_id === 'D1' && c.item_id === '${secondItemId}')`);

    // Review & Finalize
    await ev("document.getElementById('review-confirm-check').click(); document.getElementById('review-submit-btn').click();");
    await wait("state.snapshot.review");
    await wait("!document.getElementById('finalize-btn').disabled");
    await ev("document.getElementById('finalize-btn').click()");
    await wait("state.snapshot.finalized");
    console.log('✓ Meal finalized successfully');

    // 5. Verify Post-Finalization Navigation & Persistent Sharing & Access
    await wait("document.getElementById('apportionment-section')");
    const quickNavBtn = await ev("!!document.getElementById('quick-nav-sharing-btn')");
    assert(quickNavBtn, 'Quick-navigation button [Sharing & Access ▾] must be rendered in finalized view');

    const postSharingSection = await ev(`(() => {
      const sec = document.getElementById('sharing-access-section');
      return {
        visible: !!sec && !sec.hidden,
        text: sec ? sec.innerText : ''
      };
    })()`);
    assert(postSharingSection.visible, 'Sharing & Access section must persist after finalization');
    console.log('✓ Persistent Sharing & Access section and quick-nav button verified in finalized view');

    // 6. Post-finalization Diner Invitation Lifecycle:
    // First, test Revoke on Bob's active cached invitation
    const revokeBtn = await ev("!!document.querySelector('.revoke-invite-btn[data-part=\"D1\"]')");
    assert(revokeBtn, 'Revoke button must be present for active invitation on finalized meal');
    await ev("document.querySelector('.revoke-invite-btn[data-part=\"D1\"]').click()");
    await wait("document.querySelector('.issue-invite-btn[data-id=\"D1\"]')");
    console.log('✓ Successfully revoked diner invitation on finalized meal');

    // Reissue invite for Bob on finalized meal
    await ev("document.querySelector('.issue-invite-btn[data-id=\"D1\"]').click()");
    await wait("document.querySelector('.copy-invite-btn[data-part=\"D1\"]')");
    const reissuedBobUrl = await ev("state.issuedTokens['D1']");
    assert(reissuedBobUrl && reissuedBobUrl.includes('/#/invite/'), 'Reissued invite must be valid');
    console.log(`✓ Successfully reissued diner invitation on finalized meal: ${reissuedBobUrl}`);

    // Simulate page reload or forgotten token for Bob: delete in-memory token and re-render
    await ev(`(() => {
      delete state.issuedTokens['D1'];
      renderInvitationList(state.snapshot);
      updateMealUI();
    })()`);
    await wait("document.querySelector('.reissue-invite-btn[data-part=\"D1\"]')");
    console.log('✓ Uncached active invitation displays [🔄 Revoke & Reissue] button');

    // Test 1-click Revoke & Reissue for uncached invitation
    await ev("document.querySelector('.reissue-invite-btn[data-part=\"D1\"]').click()");
    await wait("document.querySelector('.copy-invite-btn[data-part=\"D1\"]')");
    const freshBobUrl = await ev("state.issuedTokens['D1']");
    assert(freshBobUrl && freshBobUrl.includes('/#/invite/'), 'Revoke & Reissue must generate fresh invite URL');
    console.log(`✓ Successfully executed 1-click Revoke & Reissue: ${freshBobUrl}`);

    // Issue invite for Charlie (D2) on finalized meal
    const charlieInviteBtn = await ev("!!document.querySelector('.issue-invite-btn[data-id=\"D2\"]')");
    assert(charlieInviteBtn, 'Create Link button for uninvited diner Charlie must be present on finalized meal');
    await ev("document.querySelector('.issue-invite-btn[data-id=\"D2\"]').click()");
    await wait("document.querySelector('.copy-invite-btn[data-part=\"D2\"]')");
    console.log('✓ Successfully issued brand-new diner invitation on finalized meal');

    // 7. Notion Export & Sharing Workflow
    await ev(`(() => {
      document.getElementById('notion-parent-id').value = '3fb0ffe1-72a6-815e-b59d-ef81c6e8eb4d';
      document.getElementById('notion-export-btn').click();
    })()`);
    await wait("document.getElementById('notion-page-link')");
    console.log('✓ Notion export completed successfully');

    // Check Candidate Sharing Affordances
    const exportAffordances = await ev(`(() => {
      return {
        hasPrivateTestBtn: !!document.getElementById('test-notion-incognito-btn'),
        hasCandidateShareBtn: !!document.getElementById('share-candidate-notion-url-btn'),
        candidateConfirmHidden: document.getElementById('notion-candidate-share-confirm')?.style.display === 'none'
      };
    })()`);
    assert(exportAffordances.hasPrivateTestBtn, 'Private verification test button must be present');
    assert(exportAffordances.hasCandidateShareBtn, 'Share Exported Report with Diners button must be present');
    assert(exportAffordances.candidateConfirmHidden, 'Confirmation prompt must be initially hidden');
    console.log('✓ Candidate report sharing controls and private test action verified');

    // Click "Share Exported Report with Diners" to open confirmation dialog
    await ev("document.getElementById('share-candidate-notion-url-btn').click()");
    await wait("document.getElementById('notion-candidate-share-confirm')?.style.display === 'block'");
    const confirmPrompt = await ev(`(() => {
      const p = document.getElementById('notion-candidate-share-confirm');
      return {
        hasDisclaimer: p ? p.innerText.includes('inherited permissions') : false,
        hasWarning: p ? p.innerText.includes('Privacy Notice') : false,
        hasConfirmBtn: !!document.getElementById('confirm-share-candidate-btn'),
        hasCancelBtn: !!document.getElementById('cancel-share-candidate-btn')
      };
    })()`);
    assert(confirmPrompt.hasDisclaimer, 'Guest-access disclaimer must be displayed');
    assert(confirmPrompt.hasWarning, 'Privacy implication warning must be displayed');
    assert(confirmPrompt.hasConfirmBtn && confirmPrompt.hasCancelBtn, 'Confirm and Cancel buttons must be present');

    // Confirm sharing
    await ev("document.getElementById('confirm-share-candidate-btn').click()");
    await wait("state.snapshot.notion_public_url");
    const sharedUrl = await ev("state.snapshot.notion_public_url");
    assert(sharedUrl && (sharedUrl.includes('notion.site') || sharedUrl.includes('notion.so')), `Shared URL must match exported page URL: ${sharedUrl}`);
    console.log(`✓ Explicit confirmation accepted and shared URL activated: ${sharedUrl}`);

    // Verify Active Shared Status
    const sharedStatus = await ev(`(() => {
      return {
        hasStopSharingBtn: !!document.getElementById('clear-notion-public-url-btn'),
        hasSharedPrivateTestBtn: !!document.getElementById('test-shared-incognito-btn'),
        statusText: document.getElementById('notion-export-result')?.innerText
      };
    })()`);
    assert(sharedStatus.hasStopSharingBtn, 'Stop Sharing with Diners button must be present');
    assert(sharedStatus.hasSharedPrivateTestBtn, 'Test Shared Link in Private Window button must be present');
    console.log('✓ Active shared report card displayed with private test and unshare options');

    // 8. Security Boundary: Sensitive Link and Domain Validation
    await ev(`(() => {
      const d = document.getElementById('notion-custom-url-details');
      if (d) d.open = true;
    })()`);

    // Test rejection of Organizer Recovery URL
    const organizerRecoveryUrl = `${origin}/#/claim-organizer/5b6f3a74-test-organizer-secret-credential`;
    await ev(`
      document.getElementById('notion-public-url-input').value = '${organizerRecoveryUrl}';
      document.getElementById('save-notion-public-url-btn').click();
    `);
    await wait("document.getElementById('notion-url-validation-alert')?.innerText.includes('Organizer Recovery Link')");
    const recoveryErrorText = await ev("document.getElementById('notion-url-validation-alert').innerText");
    assert(recoveryErrorText.includes('Organizer Recovery Link'), 'Must reject organizer claim URL with clear alert');
    console.log('✓ Successfully blocked accidental organizer recovery link sharing');

    // Test rejection of Diner Invitation URL
    const dinerInviteUrl = `${origin}/#/invite/secret-invite-token-12345`;
    await ev(`
      document.getElementById('notion-public-url-input').value = '${dinerInviteUrl}';
      document.getElementById('save-notion-public-url-btn').click();
    `);
    await wait("document.getElementById('notion-url-validation-alert')?.innerText.includes('Diner Invitation Link')");
    console.log('✓ Successfully blocked accidental diner invitation link sharing');

    // Test rejection of External Non-Notion URL
    const externalUrl = 'https://malicious-or-unrelated-site.com/report';
    await ev(`
      document.getElementById('notion-public-url-input').value = '${externalUrl}';
      document.getElementById('save-notion-public-url-btn').click();
    `);
    await wait("document.getElementById('notion-url-validation-alert')?.innerText.includes('not a Notion domain')");
    console.log('✓ Successfully blocked non-Notion external URL sharing');

    // Test acceptance of official app.notion.com URL
    const appNotionUrl = 'https://app.notion.com/p/SettleTable-test-12345/197ad85';
    await ev(`
      document.getElementById('notion-public-url-input').value = '${appNotionUrl}';
      document.getElementById('save-notion-public-url-btn').click();
    `);
    await wait("state.snapshot.notion_public_url === '" + appNotionUrl + "'");
    console.log('✓ Successfully accepted and saved official app.notion.com report URL');

    // Test Stop Sharing with Diners
    await ev("document.getElementById('clear-notion-public-url-btn').click()");
    await wait("!state.snapshot.notion_public_url");
    console.log('✓ Successfully stopped sharing Notion report with diners');

    // 9. Financial and Calculation Invariance Verification
    const finalSnap = await ev("state.snapshot");
    assert(finalSnap.finalized, 'Meal must remain finalized');
    assert(finalSnap.receipt.total_sen === 5000, `Receipt total must remain 5000 sen (got ${finalSnap.receipt.total_sen})`);
    assert(finalSnap.calculation.consumption.reduce((s, c) => s + c.sen, 0) === 5000, 'Calculated shares must strictly conserve 5000 sen');
    console.log('✓ Bit-for-bit financial invariance preserved across all sharing operations');

    console.log('\n======================================================');
    console.log('🎉 ALL NOTION SHARING & POST-FINALIZATION E2E CHECKS PASSED!');
    console.log('======================================================');
  } finally {
    if (chrome) {
      chrome.page.close();
      chrome.proc.kill();
    }
    if (server) {
      server.kill();
    }
    await rm(dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }).catch(() => {});
  }
}

main().catch(err => {
  console.error('Test run failed:', err);
  process.exit(1);
});
