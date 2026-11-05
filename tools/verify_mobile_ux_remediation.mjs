import { spawn } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import fs, { existsSync } from 'node:fs';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path, { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:net';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const EVIDENCE_DIR = process.env.EVIDENCE_DIR || null;

async function maybeCaptureScreenshot(page, filename) {
  if (EVIDENCE_DIR) {
    if (!existsSync(EVIDENCE_DIR)) {
      fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
    }
    await page.captureScreenshot(join(EVIDENCE_DIR, filename));
  }
}

function resolveChromePath() {
  const env = process.env.CHROME || process.env.CHROME_BIN || process.env.GOOGLE_CHROME_BIN;
  if (env && existsSync(env)) return env;
  const candidates = [
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
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

function resolvePythonPath() {
  const env = process.env.PYTHON || process.env.PYTHON_BIN;
  if (env && existsSync(env)) return env;
  for (const c of ['C:\\Python314\\python.exe', 'C:\\Python312\\python.exe', 'python3', 'python']) {
    if (c && (existsSync(c) || !c.includes('\\'))) return c;
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

    this.ws.onmessage = (evt) => {
      const msg = JSON.parse(evt.data);
      if (msg.id && this.callbacks.has(msg.id)) {
        const cb = this.callbacks.get(msg.id);
        this.callbacks.delete(msg.id);
        if (msg.error) cb.reject(new Error(msg.error.message));
        else cb.resolve(msg.result);
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

  async navigate(url) {
    await this.send('Page.navigate', { url });
    await this.waitFor(() => document.readyState === 'complete');
  }

  async setViewport(width, height) {
    await this.send('Emulation.setDeviceMetricsOverride', {
      width,
      height,
      deviceScaleFactor: 2,
      mobile: width < 600,
    });
  }

  async waitFor(expr, timeoutMs = 10000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      try {
        const res = await this.evaluate(expr);
        if (res) return res;
      } catch (e) {}
      await new Promise(r => setTimeout(r, 50));
    }
    throw new Error(`Timeout waiting for expression: ${expr}`);
  }

  async captureScreenshot(filePath) {
    const res = await this.send('Page.captureScreenshot', { format: 'png' });
    await fs.promises.writeFile(filePath, Buffer.from(res.data, 'base64'));
  }

  async close() {
    try {
      this.ws.close();
    } catch (_) {}
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
    '--disable-extensions',
    '--disable-background-networking',
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

async function run() {
  console.log('=== Starting Focused Mobile UX Remediation Verification ===');
  const chromePath = resolveChromePath();
  const pythonPath = resolvePythonPath();

  const getFreePort = () => new Promise((res, rej) => {
    const s = createServer();
    s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); });
    s.on('error', rej);
  });
  const serverPort = await getFreePort();
  const chromePort = await getFreePort();
  const origin = `http://127.0.0.1:${serverPort}`;
  const mealId = `verify-${randomBytes(4).toString('hex')}`;

  const tempDir = await mkdtemp(join(tmpdir(), 'settletable-verify-'));
  const dbPath = join(tempDir, 'verify.sqlite');
  const capture = join(tempDir, 'mock-payload.json');
  const owner = randomBytes(32).toString('hex');

  const runnerScript = join(REPO_ROOT, 'tools', 'verify_financial_export_runner.py');
  const server = spawn(pythonPath, [
    '-u', runnerScript,
    '--host', '127.0.0.1',
    '--port', String(serverPort),
    '--db', dbPath,
    '--mock-notion',
    '--mock-ocr',
  ], {
    cwd: REPO_ROOT,
    env: {
      ...process.env,
      SETTLETABLE_MOCK_CAPTURE: capture,
      SETTLETABLE_TEST_OWNER: owner,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  server.stderr.on('data', d => process.stderr.write(d));

  let serverReady = false;
  for (let i = 0; i < 150; i++) {
    try {
      const res = await fetch(`${origin}/__financial_test_owner__`);
      if (res.status === 200 && (await res.text()).trim() === owner) {
        serverReady = true;
        break;
      }
    } catch (e) {}
    await new Promise(r => setTimeout(r, 100));
  }
  if (!serverReady) throw new Error('Server failed to start');

  const chromeDir = join(tempDir, 'chrome-profile');
  await fs.promises.mkdir(chromeDir, { recursive: true });
  const chrome = await startChrome(chromePath, chromePort, chromeDir);
  const page = chrome.page;

  try {
    // 1. Bootstrap meal with Alice and Bob
    console.log('\n[Stage 1] Bootstrapping room with Alice (Organizer) and Bob (Diner)...');
    await page.navigate(origin + '/');
    await page.waitFor(() => document.getElementById('create-meal-form') !== null);
    await page.evaluate((id) => {
      document.getElementById('create-meal-id').value = id;
      document.getElementById('create-org-name').value = 'Alice';
      document.getElementById('create-diners').value = 'Bob';
      document.getElementById('create-meal-form').requestSubmit();
    }, mealId);
    await page.waitFor(() => document.getElementById('manual-refresh-btn') !== null);
    console.log('   ✓ Room bootstrapped');

    // 2. Add normal paid item and complimentary item with long names
    console.log('[Stage 2] Adding paid item and complimentary items...');
    await page.evaluate(() => {
      document.getElementById('new-item-label').value = 'Australian Black Angus Prime Ribeye Steak';
      document.getElementById('new-item-qty').value = '2';
      document.getElementById('new-item-price').value = '120.00';
      document.getElementById('add-item-form').requestSubmit();
    });
    await page.waitFor('state.snapshot?.receipt?.items?.length === 1');

    await page.evaluate(() => {
      document.getElementById('new-item-label').value = 'Complimentary Green Tea & Pickles Refill Basket';
      document.getElementById('new-item-qty').value = '1';
      document.getElementById('new-item-price').value = '0.00';
      document.getElementById('add-item-form').requestSubmit();
    });
    await page.waitFor('state.snapshot?.receipt?.items?.length === 2');
    console.log('   ✓ Items added: long paid item and long complimentary item');

    // 3. Verify P3: Room Home Breadcrumb & Receipt Review Checkbox Touch Targets
    console.log('\n[Stage 3] Verifying P3 Touch Targets (Home link & Review Checkbox)...');
    await page.setViewport(375, 667);
    await new Promise(r => setTimeout(r, 200));

    const p3Metrics = await page.evaluate(() => {
      const homeLink = document.querySelector('.room-home-link');
      const homeRect = homeLink?.getBoundingClientRect();

      const reviewCheck = document.getElementById('review-confirm-check');
      const checkRect = reviewCheck?.getBoundingClientRect();
      const reviewLabel = reviewCheck?.closest('label');
      const labelRect = reviewLabel?.getBoundingClientRect();

      const reviewSection = document.getElementById('review-section');
      const reviewScrollMargin = reviewSection ? window.getComputedStyle(reviewSection).scrollMarginTop : null;

      return {
        homeLink: {
          width: homeRect?.width,
          height: homeRect?.height,
        },
        reviewCheckbox: {
          width: checkRect?.width,
          height: checkRect?.height,
        },
        reviewLabel: {
          width: labelRect?.width,
          height: labelRect?.height,
        },
        reviewScrollMargin,
      };
    });

    console.log(`   Room Home Link (Mobile 375px): ${p3Metrics.homeLink.width.toFixed(1)}x${p3Metrics.homeLink.height.toFixed(1)}px`);
    console.log(`   Review Checkbox: ${p3Metrics.reviewCheckbox.width.toFixed(1)}x${p3Metrics.reviewCheckbox.height.toFixed(1)}px`);
    console.log(`   Review Label: ${p3Metrics.reviewLabel.width.toFixed(1)}x${p3Metrics.reviewLabel.height.toFixed(1)}px`);
    console.log(`   Review Section scrollMarginTop: ${p3Metrics.reviewScrollMargin}`);

    if (p3Metrics.homeLink.height < 44) {
      throw new Error(`Room Home link height < 44px: ${p3Metrics.homeLink.height}px`);
    }
    if (p3Metrics.reviewLabel.height < 44) {
      throw new Error(`Review Label height < 44px: ${p3Metrics.reviewLabel.height}px`);
    }
    if (!p3Metrics.reviewScrollMargin || p3Metrics.reviewScrollMargin === '0px') {
      throw new Error(`Missing scroll-margin-top on review section: ${p3Metrics.reviewScrollMargin}`);
    }

    // Verify desktop viewport breadcrumb remains compact
    await page.setViewport(1024, 768);
    await new Promise(r => setTimeout(r, 150));
    const desktopHomeHeight = await page.evaluate(() => {
      const link = document.querySelector('.room-home-link');
      return link?.getBoundingClientRect()?.height || 0;
    });
    console.log(`   Room Home Link (Desktop 1024px): ${desktopHomeHeight.toFixed(1)}px (compact target <= 32px)`);
    if (desktopHomeHeight > 32) {
      throw new Error(`Desktop breadcrumb inflated unexpectedly: ${desktopHomeHeight}px`);
    }

    await page.setViewport(375, 667);
    console.log('   ✓ Room Home link (>= 44px on mobile, compact on desktop), Review Label (>= 44px), and sticky scroll margin verified');
    await maybeCaptureScreenshot(page, 'after_p3_breadcrumb_375.png');

    // 4. Verify P1 Overflow across all 6 required viewports
    console.log('\n[Stage 4] Verifying P1 (Complimentary Item Overflow) Across All 6 Viewports...');
    const viewports = [
      { name: '320x568 (Small Phone)', width: 320, height: 568 },
      { name: '375x667 (Standard Phone)', width: 375, height: 667 },
      { name: '390x844 (Modern Phone)', width: 390, height: 844 },
      { name: '430x932 (Large Phone)', width: 430, height: 932 },
      { name: '768x1024 (Tablet)', width: 768, height: 1024 },
      { name: '667x375 (Landscape)', width: 667, height: 375 },
    ];

    for (const vp of viewports) {
      await page.setViewport(vp.width, vp.height);
      await new Promise(r => setTimeout(r, 200));

      const metrics = await page.evaluate((targetWidth) => {
        const docScrollWidth = document.documentElement.scrollWidth;
        const bodyScrollWidth = document.body.scrollWidth;

        // Complimentary card
        const compCard = document.querySelector('.hybrid-item-card.is-complimentary') || document.querySelector('.item-card.is-complimentary');
        const compBadge = compCard?.querySelector('.complimentary-badge');
        const compPrice = compCard?.querySelector('.item-price');
        const compLabel = compCard?.querySelector('.item-label');
        const compCardRect = compCard?.getBoundingClientRect();
        const compBadgeRect = compBadge?.getBoundingClientRect();
        const compPriceRect = compPrice?.getBoundingClientRect();

        // Paid card
        const paidCard = document.querySelector('.hybrid-item-card:not(.is-complimentary)') || document.querySelector('.item-card:not(.is-complimentary)');
        const paidPrice = paidCard?.querySelector('.item-price');
        const paidPriceRect = paidPrice?.getBoundingClientRect();
        const paidCardRect = paidCard?.getBoundingClientRect();

        // Review section row
        const reviewRow = document.querySelector('.review-item-row.is-complimentary');
        const reviewRowRect = reviewRow?.getBoundingClientRect();
        const reviewBadge = reviewRow?.querySelector('.complimentary-badge');
        const reviewBadgeRect = reviewBadge?.getBoundingClientRect();

        return {
          targetWidth,
          docScrollWidth,
          bodyScrollWidth,
          compCardRight: compCardRect?.right,
          compBadgeRight: compBadgeRect?.right,
          compPriceRight: compPriceRect?.right,
          paidCardRight: paidCardRect?.right,
          paidPriceRight: paidPriceRect?.right,
          reviewRowRight: reviewRowRect?.right,
          reviewBadgeRight: reviewBadgeRect?.right,
          hasOverflow: docScrollWidth > targetWidth || bodyScrollWidth > targetWidth ||
                       (compBadgeRect?.right || 0) > targetWidth ||
                       (compCardRect?.right || 0) > targetWidth ||
                       (paidCardRect?.right || 0) > targetWidth ||
                       (reviewBadgeRect?.right || 0) > targetWidth,
        };
      }, vp.width);

      console.log(`   Viewport ${vp.name}: docScrollWidth=${metrics.docScrollWidth}px (target: ${vp.width}px), badgeRight=${metrics.compBadgeRight?.toFixed(1)}px, reviewBadgeRight=${metrics.reviewBadgeRight?.toFixed(1)}px, overflow: ${metrics.hasOverflow ? 'FAIL' : 'PASS'}`);

      if (metrics.hasOverflow) {
        throw new Error(`Horizontal overflow detected at ${vp.name}: ${JSON.stringify(metrics)}`);
      }

      if (vp.width === 320) {
        await maybeCaptureScreenshot(page, 'after_p1_complimentary_320.png');
      } else if (vp.width === 375 && vp.height === 667) {
        await maybeCaptureScreenshot(page, 'after_p1_complimentary_375.png');
        await maybeCaptureScreenshot(page, 'after_paid_item_layout_375.png');
      }
    }
    console.log('   ✓ All 6 viewports verified with ZERO horizontal overflow and complete badge containment');

    // 5. Verify Paid Item Visual Correctness at 375px
    console.log('\n[Stage 5] Verifying Paid Item Visual Placement...');
    await page.setViewport(375, 667);
    await new Promise(r => setTimeout(r, 200));

    const paidItemMetrics = await page.evaluate(() => {
      const paidCard = document.querySelector('.hybrid-item-card:not(.is-complimentary)');
      const header = paidCard?.querySelector('.item-header');
      const label = paidCard?.querySelector('.item-label');
      const price = paidCard?.querySelector('.item-price');

      const headerRect = header?.getBoundingClientRect();
      const labelRect = label?.getBoundingClientRect();
      const priceRect = price?.getBoundingClientRect();

      return {
        headerTop: headerRect?.top,
        priceTop: priceRect?.top,
        labelTop: labelRect?.top,
        priceRight: priceRect?.right,
        headerRight: headerRect?.right,
        isSameTopRow: Math.abs((priceRect?.top || 0) - (labelRect?.top || 0)) < 10,
        priceAlignsRight: Math.abs((priceRect?.right || 0) - (headerRect?.right || 0)) < 15,
      };
    });

    console.log('   Paid item header alignment:', paidItemMetrics);
    if (!paidItemMetrics.isSameTopRow) {
      throw new Error('Paid item price is not aligned on the same top row as item label');
    }
    if (!paidItemMetrics.priceAlignsRight) {
      throw new Error('Paid item price is not right-aligned within header');
    }
    console.log('   ✓ Paid item layout remains visually correct (price pinned top-right beside wrapping title)');

    // 6. Verify Diner View Layout Across All 6 Viewports
    console.log('\n[Stage 6] Verifying Diner View Layout Across All 6 Viewports...');
    await page.evaluate(() => {
      // Temporarily switch snapshot view to diner mode
      state.snapshot.is_organizer = false;
      state.isOrganizer = false;
      window.settletable.updateMealUI();
    });

    for (const vp of viewports) {
      await page.setViewport(vp.width, vp.height);
      await new Promise(r => setTimeout(r, 150));

      const dinerMetrics = await page.evaluate((targetWidth) => {
        const docScrollWidth = document.documentElement.scrollWidth;
        const compCard = document.querySelector('.item-card.is-complimentary');
        const compBadge = compCard?.querySelector('.complimentary-badge');
        const compBadgeRect = compBadge?.getBoundingClientRect();
        const compCardRect = compCard?.getBoundingClientRect();

        return {
          targetWidth,
          docScrollWidth,
          badgeRight: compBadgeRect?.right,
          cardRight: compCardRect?.right,
          hasOverflow: docScrollWidth > targetWidth || (compBadgeRect?.right || 0) > targetWidth,
        };
      }, vp.width);

      console.log(`   Diner View (${vp.name}): docScrollWidth=${dinerMetrics.docScrollWidth}px, badgeRight=${dinerMetrics.badgeRight?.toFixed(1)}px, overflow: ${dinerMetrics.hasOverflow ? 'FAIL' : 'PASS'}`);
      if (dinerMetrics.hasOverflow) {
        throw new Error(`Diner view overflowed at ${vp.name}: ${JSON.stringify(dinerMetrics)}`);
      }

      if (vp.width === 375 && vp.height === 667) {
        await maybeCaptureScreenshot(page, 'after_diner_view_complimentary_375.png');
      }
    }

    // Restore organizer view
    await page.evaluate(() => {
      state.snapshot.is_organizer = true;
      state.isOrganizer = true;
      window.settletable.updateMealUI();
    });
    console.log('   ✓ Diner view verified across all 6 viewports with zero horizontal overflow');

    // 7. Finalize Meal and Verify P2 Notion Token Input Styling & Focus
    console.log('\n[Stage 7] Finalizing Meal and Verifying P2 (Notion Token Input)...');
    await page.setViewport(375, 667);
    await new Promise(r => setTimeout(r, 200));

    // Verify and seal receipt
    await page.evaluate(() => {
      const check = document.getElementById('review-confirm-check');
      check.checked = true;
      check.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await page.waitFor(() => !document.getElementById('review-submit-btn').disabled);
    await page.evaluate(() => document.getElementById('review-submit-btn').click());
    await page.waitFor(() => document.getElementById('receipt-verified-status') !== null);

    // Claim paid item for Alice
    await page.evaluate(async (mid) => {
      const s = state.snapshot;
      const rev = s.financial_revision;
      const receiptItem = s.receipt.items.find(i => i.line_sen > 0);
      const steak = s.items.find(i => i.item_id === receiptItem.id);
      await apiCall(`/api/meals/${mid}/apply`, 'POST', {
        kind: 'SetOwnQuantity',
        command_id: `claim-alice-${Date.now()}`,
        item_id: steak.item_id,
        quantity: 2,
        expected_item_revision: steak.item_revision,
        expected_financial_revision: rev,
      });
      await fetchSnapshot(true);
    }, mealId);

    await page.waitFor(() => !document.getElementById('finalize-btn').disabled);
    await page.evaluate(() => {
      window.confirm = () => true;
      document.getElementById('finalize-btn').click();
    });
    await page.waitFor('document.getElementById("notion-export-card") !== null');

    const p2Metrics = await page.evaluate(() => {
      const parentInput = document.getElementById('notion-parent-id');
      const tokenInput = document.getElementById('notion-token');

      const parentStyle = window.getComputedStyle(parentInput);
      const tokenStyle = window.getComputedStyle(tokenInput);

      const parentRect = parentInput.getBoundingClientRect();
      const tokenRect = tokenInput.getBoundingClientRect();

      tokenInput.scrollIntoView({ block: 'center' });
      tokenInput.focus();
      tokenInput.click();
      // Verify CSS rule applies to input:focus and .form-input
      let focusRuleFound = false;
      for (const sheet of document.styleSheets) {
        try {
          for (const rule of sheet.cssRules) {
            if (rule.selectorText && (rule.selectorText.includes('input:focus') || rule.selectorText.includes('.form-input:focus'))) {
              if (rule.style.borderColor || rule.style.boxShadow) {
                focusRuleFound = true;
                break;
              }
            }
          }
        } catch {}
      }

      return {
        focusRuleFound,
        parentId: {
          height: parentRect.height,
          minHeight: parentStyle.minHeight,
          padding: parentStyle.padding,
          backgroundColor: parentStyle.backgroundColor,
          border: parentStyle.border,
          borderRadius: parentStyle.borderRadius,
        },
        token: {
          tagName: tokenInput.tagName,
          type: tokenInput.type,
          height: tokenRect.height,
          minHeight: tokenStyle.minHeight,
          padding: tokenStyle.padding,
          backgroundColor: tokenStyle.backgroundColor,
          border: tokenStyle.border,
          borderRadius: tokenStyle.borderRadius,
        },
      };
    });

    console.log('   Notion Focus Rule Found:', p2Metrics.focusRuleFound);
    console.log('   Notion Parent ID Input:', p2Metrics.parentId);
    console.log('   Notion Token Input:', p2Metrics.token);

    if (p2Metrics.token.height < 44) {
      throw new Error(`Notion token input height < 44px: ${p2Metrics.token.height}px`);
    }
    if (p2Metrics.token.backgroundColor !== p2Metrics.parentId.backgroundColor) {
      throw new Error(`Notion token background mismatch: got ${p2Metrics.token.backgroundColor}, expected ${p2Metrics.parentId.backgroundColor}`);
    }
    if (p2Metrics.token.padding !== p2Metrics.parentId.padding) {
      throw new Error(`Notion token padding mismatch: got ${p2Metrics.token.padding}, expected ${p2Metrics.parentId.padding}`);
    }
    if (p2Metrics.token.borderRadius !== p2Metrics.parentId.borderRadius) {
      throw new Error(`Notion token borderRadius mismatch: got ${p2Metrics.token.borderRadius}, expected ${p2Metrics.parentId.borderRadius}`);
    }
    if (!p2Metrics.focusRuleFound) {
      throw new Error('Missing input:focus / .form-input:focus rule with border-color or box-shadow');
    }
    console.log('   ✓ Notion token input matches shared input styling (>=44px, matching bg/padding/radius/focus rule)');
    await maybeCaptureScreenshot(page, 'after_p2_notion_token_375.png');

    await page.close();
    console.log('\n===========================================================');
    console.log(' ALL FOCUSED MOBILE UX REMEDIATION CHECKS PASSED 100%! ');
    console.log('===========================================================');
  } finally {
    server.kill();
    chrome.proc.kill();
    await rm(tempDir, { recursive: true, force: true }).catch(() => {});
  }
}

run().catch(err => {
  console.error('FAILED:', err);
  process.exit(1);
});
