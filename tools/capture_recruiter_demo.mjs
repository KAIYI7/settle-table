import { spawn, execSync } from 'node:child_process';
import fs, { existsSync } from 'node:fs';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path, { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const OUTPUT_DIR = join(REPO_ROOT, 'docs', 'assets', 'demo');

function resolveChromePath() {
  const env = process.env.CHROME || process.env.CHROME_BIN || process.env.GOOGLE_CHROME_BIN;
  if (env && existsSync(env)) return env;
  const sysDrive = process.env.SystemDrive || ('C' + ':');
  const programFiles = process.env.ProgramFiles || path.join(sysDrive, 'Program Files');
  const programFilesX86 = process.env['ProgramFiles(x86)'] || path.join(sysDrive, 'Program Files (x86)');
  const localAppData = process.env.LOCALAPPDATA || '';

  const candidates = [
    join(programFiles, 'Google', 'Chrome', 'Application', 'chrome.exe'),
    join(programFilesX86, 'Google', 'Chrome', 'Application', 'chrome.exe'),
    join(localAppData, 'Google', 'Chrome', 'Application', 'chrome.exe'),
    '/usr/bin/google-chrome-stable',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium-browser',
    '/usr/bin/chromium',
  ];
  for (const c of candidates) {
    if (c && existsSync(c)) return c;
  }
  throw new Error('Chrome executable not found.');
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
      throw new Error(`Evaluation failed: ${JSON.stringify(res.exceptionDetails)}`);
    }
    return res.result?.value;
  }

  async navigate(url) {
    await this.send('Page.navigate', { url });
  }

  async screenshot(filePath, clip = null) {
    const params = { format: 'png' };
    if (clip) params.clip = clip;
    const res = await this.send('Page.captureScreenshot', params);
    const buffer = Buffer.from(res.data, 'base64');
    await fs.promises.writeFile(filePath, buffer);
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
  proc.stderr?.on('data', d => { stderr += d.toString(); });

  const endpoint = `http://127.0.0.1:${port}/json/list`;
  let target = null;
  for (let i = 0; i < 300; i++) {
    if (proc.exitCode !== null) {
      throw new Error(`Chrome exited prematurely with code ${proc.exitCode}: ${stderr}`);
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
    throw new Error(`Could not connect to Chrome on port ${port}: ${stderr}`);
  }

  const page = new CDPPage(target.webSocketDebuggerUrl);
  await page.send('Page.enable');
  await page.send('Runtime.enable');
  return { proc, page };
}

async function runDemoCapture() {
  console.log('===============================================================');
  console.log(' Starting SettleTable Recruiter Demonstration Capture Suite');
  console.log('===============================================================');

  const containerName = 'settletable-demo-capture';
  const port = 8095;
  const origin = `http://127.0.0.1:${port}`;
  const mealId = 'synthetic-lunch-demo';

  await fs.promises.mkdir(OUTPUT_DIR, { recursive: true });

  // 1. Clean any existing container
  try { execSync(`docker rm -f ${containerName}`, { stdio: 'ignore' }); } catch (e) {}

  // 2. Launch container
  console.log(`[1/8] Starting isolated Docker container on port ${port}...`);
  execSync(`docker run -d --name ${containerName} -p ${port}:8000 -e SETTLETABLE_SERVER_ORIGIN="${origin}" -e SETTLETABLE_ALLOWED_HOSTS="127.0.0.1:${port},localhost:${port},127.0.0.1,localhost" settletable:latest`);

  // Wait for /healthz
  let healthy = false;
  for (let i = 0; i < 60; i++) {
    try {
      const res = await fetch(`${origin}/healthz`);
      const body = await res.json();
      if (body.ok && body.status === 'healthy') {
        healthy = true;
        break;
      }
    } catch (e) {}
    await new Promise(r => setTimeout(r, 200));
  }
  if (!healthy) throw new Error('Container failed to become healthy');
  console.log('   ✓ Container is healthy');

  // 3. Bootstrap meal via CLI
  console.log(`[2/8] Provisioning meal "${mealId}" with Alex (Organizer), Sam, Taylor...`);
  const bootstrapOut = execSync(
    `docker exec ${containerName} python tools/bootstrap_meal.py bootstrap --meal-id "${mealId}" --organizer "Alex" --diners "Sam,Taylor"`,
    { encoding: 'utf-8' }
  );

  const orgLinkMatch = bootstrapOut.match(/http:\/\/127\.0\.0\.1:8095\/#\/claim-organizer\/([A-Za-z0-9_-]+)/);
  const samLinkMatch = bootstrapOut.match(/Sam\s+\(ID: D1\):\s+(http:\/\/127\.0\.0\.1:8095\/#\/invite\/[A-Za-z0-9_-]+)/);
  if (!orgLinkMatch) throw new Error(`Could not find organizer link in:\n${bootstrapOut}`);
  if (!samLinkMatch) throw new Error(`Could not find Sam invite link in:\n${bootstrapOut}`);

  const orgSetupUrl = `${origin}/#/claim-organizer/${orgLinkMatch[1]}`;
  const samInviteUrl = samLinkMatch[1];

  // Setup temp profiles
  const tempDir = await mkdtemp(join(tmpdir(), 'settletable-demo-chrome-'));
  const orgChromeDir = join(tempDir, 'org-profile');
  const dinerChromeDir = join(tempDir, 'diner-profile');
  await fs.promises.mkdir(orgChromeDir, { recursive: true });
  await fs.promises.mkdir(dinerChromeDir, { recursive: true });

  const chromeBin = resolveChromePath();
  const orgChrome = await startChrome(chromeBin, 9331, orgChromeDir);
  const dinerChrome = await startChrome(chromeBin, 9332, dinerChromeDir);

  const orgPage = orgChrome.page;
  const dinerPage = dinerChrome.page;

  try {
    await orgPage.send('Emulation.setDeviceMetricsOverride', {
      width: 1280,
      height: 820,
      deviceScaleFactor: 2,
      mobile: false,
    });

    // --- STEP 1: Room Setup ---
    console.log('[3/8] Capturing Step 1: Organizer Room Setup...');
    await orgPage.navigate(orgSetupUrl);
    await orgPage.waitFor(() => document.getElementById('claim-org-btn') !== null);
    await orgPage.evaluate(() => document.getElementById('claim-org-btn').click());
    await orgPage.waitFor(() => document.getElementById('manual-refresh-btn') !== null);
    await new Promise(r => setTimeout(r, 800));

    const step1Path = join(OUTPUT_DIR, '01-room-setup.png');
    await orgPage.screenshot(step1Path);
    console.log(`   ✓ Saved: ${step1Path}`);

    // --- STEP 2: Synthetic Receipt OCR Upload & Candidate Review ---
    console.log('[4/8] Performing OCR extraction on synthetic receipt fixture...');
    const receiptImagePath = join(REPO_ROOT, 'tests', 'fixtures', 'ocr', 'images', 'synthetic_clear.png');
    const imageBase64 = (await fs.promises.readFile(receiptImagePath)).toString('base64');

    await orgPage.evaluate(async (base64Str, mid) => {
      const bin = atob(base64Str);
      const arr = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);

      const res = await fetch(`/api/meals/${mid}/ocr/extract`, {
        method: 'POST',
        headers: {
          'Content-Type': 'image/png',
          'X-SettleTable-Action': '1',
        },
        body: arr,
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error);

      state.ocrCandidate = data.candidate;
      state.localPhotoUrl = `/api/meals/${mid}/receipt/photo`;
      updateMealUI();
    }, imageBase64, mealId);

    await orgPage.waitFor(() => document.getElementById('ocr-accept-btn') !== null);
    await new Promise(r => setTimeout(r, 800));

    const step2Path = join(OUTPUT_DIR, '02-candidate-review.png');
    await orgPage.screenshot(step2Path);
    console.log(`   ✓ Saved: ${step2Path}`);

    // --- STEP 3: Accept Candidates, Verify Receipt, and Allocate Portions ---
    console.log('[5/8] Applying scanned candidates, sealing receipt, and allocating items...');
    await orgPage.evaluate(() => {
      document.getElementById('ocr-accept-btn').click();
    });
    await orgPage.waitFor(() => document.getElementById('review-confirm-check') !== null);
    await new Promise(r => setTimeout(r, 400));

    // Confirm and seal receipt
    await orgPage.evaluate(() => {
      const chk = document.getElementById('review-confirm-check');
      chk.checked = true;
      chk.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await orgPage.waitFor(() => !document.getElementById('review-submit-btn').disabled);
    await orgPage.evaluate(() => document.getElementById('review-submit-btn').click());
    await orgPage.waitFor(() => document.getElementById('receipt-verified-status') !== null);
    await new Promise(r => setTimeout(r, 400));

    // Allocate portions:
    // Nasi Ikan (item-1, qty 2): 1 Alex, 1 Sam
    // Teh (item-2, qty 3): 1 Alex, 1 Sam, 1 Taylor
    await orgPage.evaluate(async (mid) => {
      const s = state.snapshot;
      const sam = s.participants.find(p => p.name === 'Sam').id;
      const taylor = s.participants.find(p => p.name === 'Taylor').id;
      let rev = s.financial_revision;
      const item1Rev = s.items.find(i => i.item_id === 'item-1').item_revision;
      const item2Rev = s.items.find(i => i.item_id === 'item-2').item_revision;

      // Alex claims 1 portion of item-1 (Nasi Ikan)
      await apiCall(`/api/meals/${mid}/apply`, 'POST', {
        kind: 'SetOwnQuantity',
        command_id: `claim-alex-1-${Date.now()}`,
        item_id: 'item-1',
        quantity: 1,
        expected_item_revision: item1Rev,
        expected_financial_revision: rev,
      });
      await fetchSnapshot(true);
      rev = state.snapshot.financial_revision;

      // Assign 1 portion of item-1 to Sam
      await apiCall(`/api/meals/${mid}/apply`, 'POST', {
        kind: 'AssignParticipantQuantity',
        command_id: `assign-sam-1-${Date.now()}`,
        participant_id: sam,
        item_id: 'item-1',
        quantity: 1,
        expected_item_revision: state.snapshot.items.find(i => i.item_id === 'item-1').item_revision,
        expected_financial_revision: rev,
      });
      await fetchSnapshot(true);
      rev = state.snapshot.financial_revision;

      // Alex claims 1 portion of item-2 (Teh)
      await apiCall(`/api/meals/${mid}/apply`, 'POST', {
        kind: 'SetOwnQuantity',
        command_id: `claim-alex-2-${Date.now()}`,
        item_id: 'item-2',
        quantity: 1,
        expected_item_revision: state.snapshot.items.find(i => i.item_id === 'item-2').item_revision,
        expected_financial_revision: rev,
      });
      await fetchSnapshot(true);
      rev = state.snapshot.financial_revision;

      // Assign 1 portion of item-2 to Sam
      await apiCall(`/api/meals/${mid}/apply`, 'POST', {
        kind: 'AssignParticipantQuantity',
        command_id: `assign-sam-2-${Date.now()}`,
        participant_id: sam,
        item_id: 'item-2',
        quantity: 1,
        expected_item_revision: state.snapshot.items.find(i => i.item_id === 'item-2').item_revision,
        expected_financial_revision: rev,
      });
      await fetchSnapshot(true);
      rev = state.snapshot.financial_revision;

      // Assign 1 portion of item-2 to Taylor
      await apiCall(`/api/meals/${mid}/apply`, 'POST', {
        kind: 'AssignParticipantQuantity',
        command_id: `assign-taylor-2-${Date.now()}`,
        participant_id: taylor,
        item_id: 'item-2',
        quantity: 1,
        expected_item_revision: state.snapshot.items.find(i => i.item_id === 'item-2').item_revision,
        expected_financial_revision: rev,
      });
      await fetchSnapshot(true);
    }, mealId);

    await new Promise(r => setTimeout(r, 600));

    const step3Path = join(OUTPUT_DIR, '03-portion-allocation.png');
    await orgPage.screenshot(step3Path);
    console.log(`   ✓ Saved: ${step3Path}`);

    // --- STEP 4: Diner Interaction on Mobile Viewport ---
    console.log('[6/8] Capturing Step 4: Diner Sam joining via mobile viewport...');
    await dinerPage.send('Emulation.setDeviceMetricsOverride', {
      width: 390,
      height: 844,
      deviceScaleFactor: 2,
      mobile: true,
    });

    await dinerPage.navigate(samInviteUrl);
    await dinerPage.waitFor(() => document.getElementById('redeem-btn') !== null);
    await dinerPage.evaluate(() => document.getElementById('redeem-btn').click());
    await dinerPage.waitFor(() => document.getElementById('manual-refresh-btn') !== null);
    await new Promise(r => setTimeout(r, 800));

    const step4Path = join(OUTPUT_DIR, '04-mobile-diner-view.png');
    await dinerPage.screenshot(step4Path);
    console.log(`   ✓ Saved: ${step4Path}`);

    // --- STEP 5: Finalize Meal & Multi-Payer Reconciliation ---
    console.log('[7/8] Finalizing meal and recording cashier contribution...');
    await orgPage.evaluate(async (mid) => {
      await fetchSnapshot(true);
      await apiCall(`/api/meals/${mid}/apply`, 'POST', {
        kind: 'Finalize',
        command_id: `fin-${Date.now()}`,
        expected_revision: state.snapshot.revision,
        expected_financial_revision: state.snapshot.financial_revision,
      });
      await fetchSnapshot(true);
    }, mealId);

    await orgPage.waitFor(() => document.getElementById('restaurant-funding-card') !== null);
    await new Promise(r => setTimeout(r, 400));

    // Alex pays full cashier bill: RM 31.65
    await orgPage.evaluate(() => {
      const select = document.getElementById('payer-participant-select');
      const alex = state.snapshot.participants.find(p => p.organizer);
      select.value = alex.id;
      document.getElementById('fill-remaining-btn').click();
      document.getElementById('payer-method-select').value = 'card';
      document.getElementById('record-contribution-btn').click();
    });
    await orgPage.waitFor(() => state.snapshot?.funding?.status === 'fully_funded');

    // Scroll to financial summary
    await orgPage.evaluate(() => {
      const summary = document.getElementById('restaurant-funding-card') || document.getElementById('finalized-summary-card');
      if (summary) summary.scrollIntoView({ behavior: 'instant', block: 'center' });
    });
    await new Promise(r => setTimeout(r, 800));

    const step5Path = join(OUTPUT_DIR, '05-payer-reconciliation.png');
    await orgPage.screenshot(step5Path);
    console.log(`   ✓ Saved: ${step5Path}`);

    // --- STEP 6: Peer Settlements & Suggested Reimbursements ---
    console.log('[8/8] Recording peer reimbursement and capturing settlement state...');
    await orgPage.evaluate(() => {
      const prefillBtn = document.querySelector('.prefill-transfer-btn');
      if (prefillBtn) prefillBtn.click();
      const noteInput = document.getElementById('transfer-note-input');
      if (noteInput) noteInput.value = 'DuitNow QR';
      document.getElementById('record-transfer-btn').click();
    });
    await orgPage.waitFor(() => state.snapshot?.settlement?.transfers?.length > 0);

    await orgPage.evaluate(() => {
      const settlement = document.getElementById('peer-settlement-card') || document.querySelector('.peer-settlement-card');
      if (settlement) settlement.scrollIntoView({ behavior: 'instant', block: 'center' });
    });
    await new Promise(r => setTimeout(r, 800));

    const step6Path = join(OUTPUT_DIR, '06-peer-settlement.png');
    await orgPage.screenshot(step6Path);
    console.log(`   ✓ Saved: ${step6Path}`);

    console.log('   ✓ All 6 authentic walkthrough screenshots successfully captured!');

    // --- STEP 7: Create Animated Walkthrough GIF using PIL inside container ---
    console.log('Creating animated walkthrough GIF with PIL inside container...');
    execSync(`docker run --rm -v "${REPO_ROOT}:/repo" -w /repo settletable:latest python -c "
from PIL import Image
from pathlib import Path

frames = [
    Path('docs/assets/demo/01-room-setup.png'),
    Path('docs/assets/demo/02-candidate-review.png'),
    Path('docs/assets/demo/03-portion-allocation.png'),
    Path('docs/assets/demo/05-payer-reconciliation.png'),
    Path('docs/assets/demo/06-peer-settlement.png'),
]

images = []
for f in frames:
    if f.exists():
        im = Image.open(f).convert('RGB')
        w, h = im.size
        new_w = 960
        new_h = int(h * (960 / w))
        im_resized = im.resize((new_w, new_h), Image.Resampling.LANCZOS)
        images.append(im_resized)

if images:
    out_gif = Path('docs/assets/demo/walkthrough.gif')
    images[0].save(
        out_gif,
        save_all=True,
        append_images=images[1:],
        duration=3500,
        loop=0,
        optimize=True
    )
    print(f'Saved {out_gif} ({out_gif.stat().st_size} bytes)')
"`);
    console.log('   ✓ Animated GIF created: docs/assets/demo/walkthrough.gif');

  } finally {
    try { orgPage.close(); } catch (e) {}
    try { dinerPage.close(); } catch (e) {}
    try { orgChrome.proc.kill(); } catch (e) {}
    try { dinerChrome.proc.kill(); } catch (e) {}
    try { execSync(`docker rm -f ${containerName}`, { stdio: 'ignore' }); } catch (e) {}
    await new Promise(r => setTimeout(r, 1000));
    try {
      await rm(tempDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 500 });
    } catch (e) {}
    console.log('   ✓ Cleaned up Docker demo container and Chrome temporary profiles.');
  }

  console.log('===============================================================');
  console.log(' Demonstration Assets Generation Completed Successfully!');
  console.log('===============================================================');
}

runDemoCapture().catch(err => {
  console.error('Fatal error during demo capture:', err);
  process.exit(1);
});
