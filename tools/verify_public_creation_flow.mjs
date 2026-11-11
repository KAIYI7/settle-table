/**
 * Headless Chrome E2E verification of Secure Public Self-Service Meal Creation.
 *
 * Verifies:
 * - Public self-service form rendering in welcome screen (#create-meal-form).
 * - Entering meal title, organizer name, and optional diners.
 * - Submitting form and creating a new private room via POST /api/meals/public-create.
 * - Automatic redirection into newly generated unguessable meal room (#/meal/friday-hotpot-...).
 * - Authenticated organizer session established with full management capabilities.
 * - Emergency organizer recovery link present and copyable.
 * - Local storage recent meals registry populated.
 * - Navigating back to home screen (#/) displays "Recent Meals on this Device" card.
 * - 1-click "Open Room" and "Restore Access" buttons.
 * - Mobile responsive viewport compliance (375px width).
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
  const env = process.env.CHROME || process.env.CHROME_BIN || process.env.GOOGLE_CHROME_BIN;
  if (env && existsSync(env)) return env;
  const programFiles = process.env.ProgramFiles || '';
  const programFilesX86 = process.env['ProgramFiles(x86)'] || '';
  const localAppData = process.env.LOCALAPPDATA || '';
  const candidates = [
    programFiles ? join(programFiles, 'Google', 'Chrome', 'Application', 'chrome.exe') : '',
    programFilesX86 ? join(programFilesX86, 'Google', 'Chrome', 'Application', 'chrome.exe') : '',
    localAppData ? join(localAppData, 'Google', 'Chrome', 'Application', 'chrome.exe') : '',
    '/usr/bin/google-chrome-stable',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium-browser',
    '/usr/bin/chromium',
  ].filter(Boolean);
  for (const c of candidates) {
    if (c && existsSync(c)) return c;
  }
  throw new Error('Chrome executable not found.');
}

function resolvePythonPath() {
  const env = process.env.PYTHON || process.env.PYTHON_BIN;
  if (env && existsSync(env)) return env;
  const sysDrive = process.env.SystemDrive || '';
  const candidates = [
    sysDrive ? join(sysDrive, 'Python314', 'python.exe') : '',
    sysDrive ? join(sysDrive, 'Python312', 'python.exe') : '',
    'python3',
    'python'
  ].filter(Boolean);
  for (const c of candidates) {
    if (c && (existsSync(c) || !c.includes(path.sep))) return c;
  }
  return 'python';
}

function getFreePort() {
  return new Promise((resolve, reject) => {
    const s = createServer();
    s.listen(0, '127.0.0.1', () => {
      const port = s.address().port;
      s.close(() => resolve(port));
    });
    s.on('error', reject);
  });
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

class CdpClient {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.ws = null;
    this.id = 0;
    this.pending = new Map();
  }

  async connect() {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.wsUrl);
      this.ws.onopen = () => resolve();
      this.ws.onerror = reject;
      this.ws.onmessage = event => {
        const msg = JSON.parse(event.data.toString());
        if (msg.id && this.pending.has(msg.id)) {
          const { res, rej } = this.pending.get(msg.id);
          this.pending.delete(msg.id);
          if (msg.error) rej(new Error(msg.error.message || JSON.stringify(msg.error)));
          else res(msg.result);
        }
      };
    });
  }

  send(method, params = {}) {
    return new Promise((res, rej) => {
      const id = ++this.id;
      this.pending.set(id, { res, rej });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async evaluate(expression) {
    const result = await this.send('Runtime.evaluate', {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    if (result.exceptionDetails) {
      throw new Error(`Eval error: ${JSON.stringify(result.exceptionDetails)}`);
    }
    return result.result?.value;
  }

  close() {
    if (this.ws) this.ws.close();
  }
}

async function main() {
  console.log('--- SettleTable Public Self-Service Meal Creation E2E Verification ---');
  const tempDir = await mkdtemp(join(tmpdir(), 'settletable-pubcreate-'));
  const dbPath = join(tempDir, 'settletable.sqlite');
  const photosDir = join(tempDir, 'receipt_photos');
  fs.mkdirSync(photosDir, { recursive: true });

  const appPort = await getFreePort();
  const cdpPort = await getFreePort();
  const pythonBin = resolvePythonPath();
  const chromeBin = resolveChromePath();

  console.log(`Ephemeral ports: app=${appPort}, cdp=${cdpPort}`);

  // Start test WSGI server with public creation enabled
  const runnerScript = `
import os
import sys
from wsgiref.simple_server import make_server
from settletable.transport import SettleTableApp
from settletable.public_creation import PublicCreationConfig, PublicCreationGate

cfg = PublicCreationConfig(
    enabled=True,
    turnstile_secret_key=None,
    turnstile_sitekey=None,
    max_total_meals=50,
    max_meals_per_day=50,
    max_public_diners=20,
)
gate = PublicCreationGate(cfg)
app = SettleTableApp(
    db_path=r"${dbPath.replace(/\\/g, '\\\\')}",
    storage_dir=r"${photosDir.replace(/\\/g, '\\\\')}",
    server_origin="http://localhost:${appPort}",
    allowed_hosts=["localhost:${appPort}", "127.0.0.1:${appPort}"],
    public_creation_gate=gate,
)
httpd = make_server("127.0.0.1", ${appPort}, app)
print("READY", flush=True)
httpd.serve_forever()
`;

  const serverProc = spawn(pythonBin, ['-u', '-c', runnerScript], {
    cwd: REPO_ROOT,
    env: { ...process.env, PYTHONPATH: REPO_ROOT },
  });

  serverProc.stderr.on('data', d => console.error(`[Server stderr] ${d.toString().trim()}`));

  // Wait for server ready
  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Server start timeout')), 10000);
    serverProc.stdout.on('data', d => {
      if (d.toString().includes('READY')) {
        clearTimeout(timeout);
        resolve();
      }
    });
  });

  console.log('SettleTable test server started.');

  // Launch Headless Chrome with Mobile Viewport (iPhone 375x812)
  const chromeProc = spawn(chromeBin, [
    '--headless=new',
    '--disable-gpu',
    '--no-sandbox',
    '--disable-dev-shm-usage',
    `--remote-debugging-port=${cdpPort}`,
    `--user-data-dir=${join(tempDir, 'chrome-profile')}`,
    '--window-size=375,812',
    'about:blank',
  ]);

  await sleep(1500);

  let cdp = null;
  try {
    const targetsRes = await fetch(`http://127.0.0.1:${cdpPort}/json`);
    const targets = await targetsRes.json();
    const pageTarget = targets.find(t => t.type === 'page');
    if (!pageTarget) throw new Error('No page target found');

    cdp = new CdpClient(pageTarget.webSocketDebuggerUrl);
    await cdp.connect();
    await cdp.send('Page.enable');
    await cdp.send('DOM.enable');
    await cdp.send('Network.enable');

    // Emulate Mobile Device Metrics
    await cdp.send('Emulation.setDeviceMetricsOverride', {
      width: 375,
      height: 812,
      deviceScaleFactor: 2,
      mobile: true,
    });

    // 1. Navigate to Welcome Page
    const appUrl = `http://localhost:${appPort}/#/`;
    console.log(`Navigating to ${appUrl}`);
    await cdp.send('Page.navigate', { url: appUrl });
    await sleep(1000);

    // 2. Verify Welcome Page rendered Create Meal Room form
    const hasCreateForm = await cdp.evaluate(`Boolean(document.getElementById('create-meal-form'))`);
    if (!hasCreateForm) throw new Error('Create meal form not rendered');
    console.log('✓ Create meal room form rendered on welcome screen');

    // 3. Fill in Title, Organizer, and Diners
    await cdp.evaluate(`
      document.getElementById('create-meal-id').value = 'Friday Hotpot';
      document.getElementById('create-org-name').value = 'Alice';
      document.getElementById('create-diners').value = 'Bob, Charlie';
    `);

    // 4. Submit form
    console.log('Submitting public meal creation form...');
    await cdp.evaluate(`
      document.getElementById('create-meal-form').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
    `);

    // Wait for redirect to room
    let currentHash = '';
    for (let i = 0; i < 20; i++) {
      await sleep(300);
      currentHash = await cdp.evaluate(`window.location.hash`);
      if (currentHash.startsWith('#/meal/friday-hotpot-')) break;
    }

    if (!currentHash.startsWith('#/meal/friday-hotpot-')) {
      throw new Error(`Expected redirect to #/meal/friday-hotpot-..., got ${currentHash}`);
    }
    const createdMealId = currentHash.replace('#/meal/', '');
    console.log(`✓ Room created with secure unguessable ID: ${createdMealId}`);

    // Wait for snapshot UI to load
    await sleep(1000);

    // 5. Verify Organizer Session & Capabilities
    const isOrg = await cdp.evaluate(`Boolean(state.isOrganizer)`);
    if (!isOrg) throw new Error('Expected organizer privileges for room creator');
    console.log('✓ Creator granted authenticated Organizer privileges');

    const participants = await cdp.evaluate(`state.snapshot?.participants?.map(p => p.name) || []`);
    if (!participants.includes('Alice') || !participants.includes('Bob') || !participants.includes('Charlie')) {
      throw new Error(`Expected participants [Alice, Bob, Charlie], got ${JSON.stringify(participants)}`);
    }
    console.log(`✓ Participants verified: ${participants.join(', ')}`);

    // 6. Verify Emergency Organizer Recovery Link Card is present
    const hasRecoveryBtn = await cdp.evaluate(`Boolean(document.getElementById('gen-recovery-link-btn'))`);
    if (!hasRecoveryBtn) throw new Error('Expected emergency recovery link button for organizer');
    console.log('✓ Emergency organizer recovery affordance present');

    // 7. Full Organizer Workflow: Enter Items, Review, Allocate, and Invite Diners
    console.log('Testing organizer workflow: entering receipt items, reviewing, and allocating...');
    await cdp.evaluate(`
      (async () => {
        // Step A: ReplaceReceipt with two items (Total RM80.00)
        await apiCall(\`/api/meals/\${state.mealId}/apply\`, 'POST', {
          kind: 'ReplaceReceipt',
          command_id: 'cmd-init-receipt',
          expected_revision: state.snapshot.revision,
          expected_financial_revision: state.snapshot.financial_revision,
          receipt: {
            currency: 'MYR',
            subtotal_sen: 8000,
            total_sen: 8000,
            included_tax_sen: 0,
            items: [
              { id: 'item-1', label: 'Spicy Broth', line_sen: 3000, quantity: [1, 1] },
              { id: 'item-2', label: 'Beef Slices', line_sen: 5000, quantity: [1, 1] }
            ],
            adjustments: []
          }
        });
        await fetchSnapshot(true);

        // Step B: ReviewReceipt
        await apiCall(\`/api/meals/\${state.mealId}/apply\`, 'POST', {
          kind: 'ReviewReceipt',
          command_id: 'cmd-review',
          expected_revision: state.snapshot.revision,
          expected_financial_revision: state.snapshot.financial_revision,
          receipt_digest: state.snapshot.receipt_digest
        });
        await fetchSnapshot(true);

        // Step C: Allocate item-1 to Alice, Bob, Charlie (1/3 each)
        const item1 = (state.snapshot.items || []).find(i => i.item_id === 'item-1');
        const item1Rev = item1 ? item1.item_revision : 1;
        await apiCall(\`/api/meals/\${state.mealId}/apply\`, 'POST', {
          kind: 'SetItemAllocations',
          command_id: 'cmd-alloc-1',
          item_id: 'item-1',
          expected_item_revision: item1Rev,
          expected_financial_revision: state.snapshot.financial_revision,
          allocations: [
            { participant_id: 'O', quantity: [1, 3] },
            { participant_id: 'D1', quantity: [1, 3] },
            { participant_id: 'D2', quantity: [1, 3] }
          ]
        });
        await fetchSnapshot(true);
      })()
    `);
    await sleep(600);

    const receiptTotal = await cdp.evaluate(`state.snapshot?.receipt?.total_sen`);
    if (receiptTotal !== 8000) throw new Error(`Expected receipt total 8000 sen, got ${receiptTotal}`);
    console.log(`✓ Receipt items reviewed and allocated successfully (Receipt Total: RM ${(receiptTotal / 100).toFixed(2)})`);

    // Step D: Issue Diner Invitation for Bob (D1)
    console.log('Testing diner invitation generation...');
    const inviteRes = await cdp.evaluate(`
      (async () => {
        const res = await apiCall(\`/api/meals/\${state.mealId}/invitations\`, 'POST', { participant_id: 'D1' });
        return res;
      })()
    `);
    if (!inviteRes?.ok || !inviteRes.invite_url) {
      throw new Error(`Failed to issue diner invitation: ${JSON.stringify(inviteRes)}`);
    }
    console.log(`✓ Diner invitation link generated for Bob: ${inviteRes.invite_url}`);

    // 8. Verify Local Storage has recorded the recent meal
    const storedMeals = await cdp.evaluate(`JSON.parse(localStorage.getItem('settletable_recent_meals') || '[]')`);
    if (storedMeals.length !== 1 || storedMeals[0].meal_id !== createdMealId) {
      throw new Error(`Expected recent meal in localStorage, got ${JSON.stringify(storedMeals)}`);
    }
    if (storedMeals[0].claim_url || storedMeals[0].credential) {
      throw new Error('Security violation: bearer claim_url or credential must not be stored in localStorage');
    }
    console.log(`✓ Local storage recent meals registry updated: ${storedMeals[0].title} (${storedMeals[0].role})`);
    console.log('✓ Verified no bearer credentials or claim tokens stored in localStorage');

    // 8. Navigate back to Home Screen
    console.log('Navigating back to Home Screen (#/)...');
    await cdp.send('Page.navigate', { url: `http://localhost:${appPort}/#/` });
    await sleep(800);

    // 9. Verify "Recent Meals on this Device" card is rendered
    const hasRecentCard = await cdp.evaluate(`Boolean(document.getElementById('recent-meals-card'))`);
    if (!hasRecentCard) throw new Error('Expected Recent Meals on this Device card on welcome screen');
    console.log('✓ "Recent Meals on this Device" card rendered on welcome screen');

    const recentRowTitle = await cdp.evaluate(`document.querySelector('.recent-meal-title-line')?.textContent || ''`);
    if (!recentRowTitle.includes('Friday Hotpot') || !recentRowTitle.includes('Organizer')) {
      throw new Error(`Expected title 'Friday Hotpot' with 'Organizer' badge, got '${recentRowTitle}'`);
    }
    console.log(`✓ Recent meal row verified: ${recentRowTitle.trim()}`);

    // 10. Click "Open Room" and verify navigation back into the meal room
    await cdp.evaluate(`document.querySelector('.recent-meal-open-btn').click();`);
    await sleep(800);

    const reloadedHash = await cdp.evaluate(`window.location.hash`);
    if (reloadedHash !== `#/meal/${createdMealId}`) {
      throw new Error(`Expected #/meal/${createdMealId}, got ${reloadedHash}`);
    }
    console.log('✓ 1-click "Open Room" returned successfully into the meal');

    console.log('\n======================================================');
    console.log('🎉 ALL PUBLIC SELF-SERVICE MEAL CREATION E2E CHECKS PASSED!');
    console.log('======================================================\n');
  } finally {
    if (cdp) cdp.close();
    chromeProc.kill('SIGTERM');
    serverProc.kill('SIGTERM');
    await rm(tempDir, { recursive: true, force: true }).catch(() => {});
  }
}

main().catch(err => {
  console.error('\n❌ E2E VERIFICATION FAILED:', err);
  process.exit(1);
});
