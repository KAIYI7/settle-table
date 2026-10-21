/**
 * SettleTable Mobile-Friendly Single-Page Application
 * Zero external dependencies, pure vanilla ES2022.
 */

// --- Global Utilities & State ---
const state = {
  mealId: null,
  snapshot: null,
  currentUserId: null,
  isOrganizer: false,
  loading: false,
  pollTimer: null,
  pollSeq: 0,
  mutationActive: false,
  issuedTokens: {},
  ocrCandidate: null,
  notionParentId: '',
  notionToken: '',
  notionExport: null,
  allocationTargetId: null,
};

function formatSen(sen) {
  if (sen === null || sen === undefined) return 'RM 0.00';
  const val = Number(sen) / 100;
  return `RM ${val.toFixed(2)}`;
}

function parseSen(input, allowNegative = false) {
  if (typeof input !== 'string') {
    throw new Error('Price must be a string');
  }
  let s = input.trim();
  let isNegative = false;
  if (s.startsWith('-')) {
    isNegative = true;
    s = s.slice(1).trim();
  }
  if (s.toUpperCase().startsWith('RM')) {
    s = s.slice(2).trim();
  }
  if (s.startsWith('-')) {
    isNegative = true;
    s = s.slice(1).trim();
  }
  if (!s || !/^[0-9]+(?:\.[0-9]{1,2})?$/.test(s)) {
    throw new Error(`Invalid price '${input}'. Enter an amount like 12.50 or RM 12.50`);
  }
  if (isNegative && !allowNegative) {
    throw new Error(`Negative amount not allowed for '${input}'`);
  }
  const parts = s.split('.');
  const whole = parseInt(parts[0], 10);
  const fracStr = (parts[1] || '').padEnd(2, '0');
  const frac = parseInt(fracStr, 10);
  const totalSen = whole * 100 + frac;
  if (totalSen < 0 || totalSen > 1_000_000_000) {
    throw new Error('Price out of bounds: maximum RM 10,000,000.00');
  }
  return isNegative ? -totalSen : totalSen;
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function extractNotionUuid(val) {
  if (!val || typeof val !== 'string') return null;
  const trimmed = val.trim();
  const hyphenMatch = trimmed.match(/\b([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b/);
  if (hyphenMatch) return hyphenMatch[1].toLowerCase();

  const hexMatch = trimmed.match(/([0-9a-fA-F]{32})/);
  if (hexMatch) {
    const h = hexMatch[1].toLowerCase();
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20, 32)}`;
  }
  return null;
}

function showAlert(message, type = 'error') {
  const container = document.getElementById('alert-container');
  if (!container) return;
  container.innerHTML = '';
  const div = document.createElement('div');
  div.className = `alert-banner alert-${type}`;
  div.textContent = message;
  container.appendChild(div);
  if (type !== 'conflict') {
    setTimeout(() => {
      if (div.parentNode) div.parentNode.removeChild(div);
    }, 5000);
  }
}

function clearAlerts() {
  const container = document.getElementById('alert-container');
  if (container) container.innerHTML = '';
}

// --- API Layer ---
async function apiCall(endpoint, method = 'GET', body = null) {
  const headers = {};
  if (method === 'POST') {
    headers['X-SettleTable-Action'] = '1';
    headers['Content-Type'] = 'application/json';
  }

  const opts = {
    method,
    headers,
    credentials: 'same-origin',
  };
  if (body !== null) {
    opts.body = JSON.stringify(body);
  }

  try {
    const res = await fetch(endpoint, opts);
    const data = await res.json().catch(() => null);

    if (!res.ok) {
      const err = new Error(data?.error || `HTTP ${res.status}`);
      err.status = res.status;
      err.code = data?.error || 'unknown_error';
      throw err;
    }
    return data;
  } catch (err) {
    throw err;
  }
}

// --- Router ---
function route() {
  clearAlerts();
  const path = window.location.pathname;
  const hash = window.location.hash;

  // 1. Check path for invitation landing /invite/{token}
  const inviteMatch = path.match(/^\/invite\/([A-Za-z0-9_-]{43})$/);
  if (inviteMatch) {
    renderInviteLanding(inviteMatch[1]);
    return;
  }

  // 2. Hash routing
  if (hash.startsWith('#/meal/')) {
    const mealId = hash.replace('#/meal/', '').trim();
    if (mealId) {
      loadMeal(mealId);
      return;
    }
  }

  renderWelcome();
}

window.addEventListener('hashchange', route);
window.addEventListener('DOMContentLoaded', route);

// Document visibility to pause polling
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') {
    stopPolling();
  } else if (state.mealId && !state.pollTimer) {
    startPolling();
  }
});

function startPolling() {
  stopPolling();
  state.pollTimer = setInterval(pollSnapshot, 3000);
}

function stopPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

async function fetchSnapshot(force = false) {
  if (!state.mealId) return;
  if (!force && state.mutationActive) return;
  const seq = ++state.pollSeq;
  try {
    const snap = await apiCall(`/api/meals/${state.mealId}/snapshot`);
    if (seq >= state.pollSeq && snap?.ok) {
      const prevSnap = state.snapshot;
      const prevRev = prevSnap ? prevSnap.revision : -1;
      const prevFinRev = prevSnap ? prevSnap.financial_revision : -1;
      const prevFinalized = prevSnap ? prevSnap.finalized : null;
      const prevUser = state.currentUserId;
      const prevIsOrg = state.isOrganizer;

      state.snapshot = snap;
      state.currentUserId = snap.current_participant_id;
      state.isOrganizer = snap.is_organizer;

      const hasChanged = !prevSnap 
        || snap.revision !== prevRev 
        || snap.financial_revision !== prevFinRev
        || snap.finalized !== prevFinalized
        || snap.current_participant_id !== prevUser
        || snap.is_organizer !== prevIsOrg;

      if (force || hasChanged) {
        updateMealUI();
      }
    }
  } catch (err) {
    if (err.status === 401) {
      stopPolling();
      showAlert('Session expired. Please rejoin or request a new invite.', 'error');
    }
  }
}

function pollSnapshot() {
  return fetchSnapshot(false);
}

// --- View 1: Welcome Screen ---
async function handleLeaveRoom() {
  const mealId = state.mealId || 'the room';
  try {
    await apiCall('/api/session/clear', 'POST', {});
  } catch (err) {
    console.warn('Session clear error:', err);
  }
  stopPolling();
  state.mealId = null;
  state.snapshot = null;
  state.currentUserId = null;
  state.isOrganizer = false;
  state.ocrCandidate = null;
  state.notionParentId = '';
  state.notionToken = '';
  state.notionExport = null;
  state.allocationTargetId = null;
  const headerStatus = document.getElementById('header-user-status');
  if (headerStatus) headerStatus.innerHTML = '';
  if (window.location.hash === '#/') {
    renderWelcome();
  } else {
    window.location.hash = '#/';
  }
  setTimeout(() => {
    showAlert(`You have left ${mealId} and exited your session. Session cookie cleared.`, 'info');
  }, 50);
}

function renderWelcome() {
  stopPolling();
  state.mealId = null;
  state.snapshot = null;
  state.currentUserId = null;
  state.isOrganizer = false;
  const headerStatus = document.getElementById('header-user-status');
  if (headerStatus) headerStatus.innerHTML = '';

  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="card">
      <h2 class="card-title">Create a Meal Room</h2>
      <p class="card-desc">Set up a new meal, enter receipt items, and invite diners to claim portions.</p>
      
      <form id="create-meal-form">
        <div class="form-group">
          <label for="create-meal-id">Meal ID / Name</label>
          <input type="text" id="create-meal-id" placeholder="e.g. dinner-friday" required pattern="[A-Za-z0-9_-]+" title="Letters, numbers, dashes and underscores only">
        </div>
        
        <div class="form-group">
          <label for="create-org-name">Your Name (Organizer)</label>
          <input type="text" id="create-org-name" placeholder="e.g. Alice" required>
        </div>

        <div class="form-group">
          <label for="create-diners">Diners (Comma-separated names)</label>
          <input type="text" id="create-diners" placeholder="e.g. Bob, Charlie, Dave">
        </div>

        <button type="submit" class="btn btn-primary btn-block">Create & Provision Meal</button>
      </form>
    </div>

    <div class="card">
      <h2 class="card-title">Open Existing Meal</h2>
      <form id="open-meal-form">
        <div class="form-group">
          <label for="open-meal-id">Meal ID</label>
          <input type="text" id="open-meal-id" placeholder="e.g. dinner-friday" required>
        </div>
        <button type="submit" class="btn btn-secondary btn-block">Enter Meal Room</button>
      </form>
    </div>

    <div style="text-align: center; margin-top: 16px;">
      <button id="welcome-clear-session-btn" class="btn btn-secondary btn-sm" style="font-size: 0.85rem; color: var(--text-muted);" title="Clear current session cookie">
        Exit / Clear Active Session Cookie
      </button>
    </div>
  `;

  document.getElementById('welcome-clear-session-btn')?.addEventListener('click', handleLeaveRoom);

  document.getElementById('create-meal-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const mealId = document.getElementById('create-meal-id').value.trim();
    const orgName = document.getElementById('create-org-name').value.trim();
    const dinersRaw = document.getElementById('create-diners').value.trim();

    const participants = [
      { id: 'O', name: orgName, organizer: true }
    ];

    if (dinersRaw) {
      dinersRaw.split(',').forEach((name, idx) => {
        const clean = name.trim();
        if (clean) {
          participants.push({ id: `D${idx + 1}`, name: clean, organizer: false });
        }
      });
    }

    try {
      showAlert('Creating meal...', 'success');
      const res = await apiCall(`/api/meals/${mealId}/bootstrap`, 'POST', { participants });
      if (res?.ok) {
        window.location.hash = `#/meal/${mealId}`;
      }
    } catch (err) {
      showAlert(`Failed to create meal: ${err.message}`, 'error');
    }
  });

  document.getElementById('open-meal-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const mealId = document.getElementById('open-meal-id').value.trim();
    if (mealId) {
      window.location.hash = `#/meal/${mealId}`;
    }
  });
}

// --- View 2: Invitation Landing Screen ---
async function renderInviteLanding(token) {
  stopPolling();
  document.getElementById('header-user-status').innerHTML = '';
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="loading-state">
      <div class="spinner"></div>
      <p>Verifying invitation token...</p>
    </div>
  `;

  try {
    const inspection = await apiCall(`/api/invitations/${token}`);
    if (!inspection?.ok || !inspection.valid) {
      const reasonMap = {
        expired: 'This invitation has expired.',
        consumed: 'This invitation was already used.',
        revoked: 'This invitation was revoked by the organizer.',
        not_found: 'Invitation not found. Please check your link.',
        invalid_token: 'Invalid invitation link format.',
      };
      app.innerHTML = `
        <div class="card">
          <h2 class="card-title" style="color: var(--accent-rose)">Invitation Invalid</h2>
          <p class="card-desc">${reasonMap[inspection?.reason] || 'This link cannot be redeemed.'}</p>
          <a href="#/" class="btn btn-secondary btn-block">Go to Home</a>
        </div>
      `;
      return;
    }

    // Valid invitation card
    app.innerHTML = `
      <div class="card">
        <h2 class="card-title">You're Invited to Dine!</h2>
        <p class="card-desc">Join meal <strong>${escapeHtml(inspection.meal_id)}</strong> to view the bill and claim your portion.</p>
        
        <div style="background: var(--bg-main); padding: 14px; border-radius: var(--radius-md); margin-bottom: 16px;">
          <div style="font-size: 0.85rem; color: var(--text-muted);">Joining as:</div>
          <div style="font-size: 1.25rem; font-weight: 700; color: #a7f3d0;">${escapeHtml(inspection.participant_name)}</div>
        </div>

        <div class="alert alert-conflict" style="margin-bottom: 20px; font-size: 0.85rem; line-height: 1.45;">
          <div>
            <strong>⚠️ Same-Browser Profile Notice:</strong><br>
            Accepting this invitation will assign this browser window to <strong>${escapeHtml(inspection.participant_name)} (Diner)</strong>.
            If you are the Organizer testing this meal in the same browser, this will <strong>replace your Organizer session</strong>.
            <div style="margin-top: 6px; color: #fef08a;">
              💡 <em>To test diner claiming while keeping your Organizer view open, copy this link and open it in a <strong>Private / Incognito window</strong> or a separate browser profile.</em>
            </div>
          </div>
        </div>

        <button id="redeem-btn" class="btn btn-success btn-block" style="font-size: 1.05rem; margin-bottom: 10px;">
          Accept & Join Meal
        </button>

        <a href="#/" class="btn btn-secondary btn-block">Cancel & Return to Home</a>
      </div>
    `;

    document.getElementById('redeem-btn').addEventListener('click', async () => {
      try {
        const btn = document.getElementById('redeem-btn');
        btn.disabled = true;
        btn.textContent = 'Joining...';
        
        const redeemRes = await apiCall(`/api/meals/${inspection.meal_id}/invitations/${token}/redeem`, 'POST', {});
        if (redeemRes?.ok) {
          // Sanitize URL immediately so refreshing doesn't re-trigger consumed token
          window.history.replaceState(null, '', `/#/meal/${inspection.meal_id}`);
          loadMeal(inspection.meal_id);
        }
      } catch (err) {
        showAlert(`Failed to join: ${err.message}`, 'error');
        document.getElementById('redeem-btn').disabled = false;
        document.getElementById('redeem-btn').textContent = 'Accept & Join Meal';
      }
    });

  } catch (err) {
    app.innerHTML = `
      <div class="card">
        <h2 class="card-title" style="color: var(--accent-rose)">Network Error</h2>
        <p class="card-desc">Could not connect to SettleTable server. ${escapeHtml(err.message)}</p>
        <a href="#/" class="btn btn-secondary btn-block">Go to Home</a>
      </div>
    `;
  }
}

// --- View 3: Meal Room ---
async function loadMeal(mealId) {
  state.mealId = mealId;
  state.notionParentId = '';
  state.notionToken = '';
  state.notionExport = null;
  state.allocationTargetId = null;
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="loading-state">
      <div class="spinner"></div>
      <p>Loading meal details...</p>
    </div>
  `;

  try {
    const snap = await apiCall(`/api/meals/${mealId}/snapshot`);
    if (snap?.ok) {
      state.snapshot = snap;
      state.currentUserId = snap.current_participant_id;
      state.isOrganizer = snap.is_organizer;

      // If finalized and organizer, check if this revision was already exported to Notion
      if (snap.finalized && snap.is_organizer) {
        try {
          const expRes = await apiCall(`/api/meals/${mealId}/export/notion`);
          if (expRes?.ok && expRes.export && (expRes.export.status === 'completed' || expRes.export.status === 'already_exported' || expRes.export.status === 'failed')) {
            state.notionExport = expRes.export;
          }
        } catch {
          // Non-critical, ignore
        }
      }

      updateMealUI();
      startPolling();
    }
  } catch (err) {
    if (err.status === 401) {
      app.innerHTML = `
        <div class="card">
          <h2 class="card-title" style="color: var(--accent-rose)">Session Required</h2>
          <p class="card-desc">You are not authenticated for meal <strong>${escapeHtml(mealId)}</strong>.</p>
          <p class="card-desc">If you are a diner, open the invitation link sent by the organizer.</p>
          <a href="#/" class="btn btn-secondary btn-block">Back to Home</a>
          <button id="clear-invalid-session-btn" class="btn btn-secondary btn-block" style="margin-top: 10px;">Clear Active Session Cookie</button>
        </div>
      `;
      document.getElementById('clear-invalid-session-btn')?.addEventListener('click', handleLeaveRoom);
    } else {
      app.innerHTML = `
        <div class="card">
          <h2 class="card-title">Error Loading Meal</h2>
          <p class="card-desc">${escapeHtml(err.message)}</p>
          <a href="#/" class="btn btn-secondary btn-block">Back to Home</a>
        </div>
      `;
    }
  }
}

function updateMealUI() {
  window.settletable = { state, updateMealUI };
  const snap = state.snapshot;
  if (!snap) return;

  // Preserve any in-progress input values and active focus across re-renders
  const activeElem = document.activeElement;
  const activeId = activeElem?.id;
  const selectionStart = activeElem?.selectionStart;
  const selectionEnd = activeElem?.selectionEnd;

  const currentParentId = document.getElementById('notion-parent-id')?.value;
  if (currentParentId !== undefined && currentParentId !== '') {
    state.notionParentId = currentParentId;
  }
  const currentToken = document.getElementById('notion-token')?.value;
  if (currentToken !== undefined && currentToken !== '') {
    state.notionToken = currentToken;
  }

  const restoreFocus = () => {
    if (activeId) {
      const el = document.getElementById(activeId);
      if (el) {
        el.focus();
        if (typeof selectionStart === 'number' && typeof selectionEnd === 'number') {
          try {
            el.setSelectionRange(selectionStart, selectionEnd);
          } catch {}
        }
      }
    }
  };

  // Header Status
  const user = snap.participants?.find(p => p.id === state.currentUserId);
  const userName = user ? user.name : 'Unknown';
  const roleBadge = state.isOrganizer 
    ? '<span class="badge badge-organizer">👑 Organizer</span>' 
    : '<span class="badge badge-diner">🍽️ Diner</span>';
  
  document.getElementById('header-user-status').innerHTML = `
    <div class="header-participant-info">
      ${roleBadge}
      <span class="header-username" title="Participant: ${escapeHtml(userName)}">${escapeHtml(userName)}</span>
    </div>
    <button id="manual-refresh-btn" class="btn btn-secondary btn-sm" title="Refresh Snapshot">⟳</button>
    <button id="header-leave-btn" class="btn btn-secondary btn-sm btn-leave" title="Exit room and clear session cookie">Leave Room</button>
  `;
  document.getElementById('manual-refresh-btn')?.addEventListener('click', () => fetchSnapshot(true));
  document.getElementById('header-leave-btn')?.addEventListener('click', handleLeaveRoom);

  const app = document.getElementById('app');
  let html = '';

  // Room Navigation Bar
  html += `
    <div class="room-nav-bar" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; font-size: 0.85rem;">
      <div style="display: flex; align-items: center; gap: 8px;">
        <a href="#/" class="btn btn-secondary btn-sm" style="min-height: 36px; padding: 4px 10px; font-size: 0.85rem;" title="Return to Home screen">← Home</a>
        <span style="color: var(--text-dim);">Room:</span>
        <strong style="color: var(--text-main); font-size: 0.95rem;">${escapeHtml(snap.meal_id)}</strong>
      </div>
      <button id="room-leave-btn" class="btn btn-secondary btn-sm btn-leave" style="min-height: 36px; padding: 4px 10px; font-size: 0.85rem;" title="Exit room and clear session cookie">
        Leave Room
      </button>
    </div>
  `;

  // 1. Status Bar Card
  const finalized = snap.finalized;
  const reviewConfirmed = Boolean(snap.review);
  const issues = snap.issues || [];

  let statusBadge = '<span class="badge badge-pending">Drafting</span>';
  if (finalized) {
    statusBadge = '<span class="badge badge-verified">Finalized ✓</span>';
  } else if (reviewConfirmed) {
    statusBadge = '<span class="badge badge-verified">Review Verified ✓</span>';
  }

  html += `
    <div class="card" style="margin-bottom: 16px;">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
          <span style="font-size: 0.8rem; color: var(--text-dim); text-transform: uppercase;">Room</span>
          <h2 style="font-size: 1.2rem; font-weight: 700;">${escapeHtml(snap.meal_id)}</h2>
        </div>
        <div style="text-align: right;">
          ${statusBadge}
          <div style="font-size: 0.75rem; color: var(--text-dim); margin-top: 2px;">Revision ${snap.revision}</div>
        </div>
      </div>
    </div>
  `;

  // 2. Finalized View: Apportionment Breakdown
  if (finalized && snap.calculation) {
    html += renderFinalizedCalculation(snap);
    app.innerHTML = html;
    bindEvents(snap);
    restoreFocus();
    return;
  }

  // 3. Organizer Section: Receipt Entry & Review
  if (state.isOrganizer) {
    html += renderOrganizerSection(snap);
  }

  // 4. Claims Section (Both Organizer & Diners)
  html += renderClaimsSection(snap);

  // 5. Organizer Finalize Action
  if (state.isOrganizer && !finalized) {
    const issues = snap.issues || [];
    const hasItems = Boolean(snap.receipt?.items?.length > 0);
    const hasClaimIssues = issues.includes('incomplete_quantity') || issues.includes('pending_claim');
    const canFinalize = hasItems && reviewConfirmed && issues.length === 0;

    let warningHtml = '';
    if (!reviewConfirmed) {
      warningHtml += '<div style="color: var(--accent-amber); font-size: 0.85rem; margin-bottom: 8px;">⚠️ Receipt must be verified before finalization.</div>';
    }
    if (!hasItems) {
      warningHtml += '<div style="color: var(--accent-amber); font-size: 0.85rem; margin-bottom: 8px;">⚠️ Add receipt items before finalization.</div>';
    } else if (hasClaimIssues) {
      warningHtml += '<div style="color: var(--accent-amber); font-size: 0.85rem; margin-bottom: 8px;">⚠️ All items must be fully claimed before finalization.</div>';
    } else if (issues.length > 0) {
      warningHtml += `<div style="color: var(--accent-amber); font-size: 0.85rem; margin-bottom: 8px;">⚠️ Issues detected: ${escapeHtml(issues.join(', '))}</div>`;
    }

    html += `
      <div class="card" style="border-color: ${canFinalize ? 'var(--accent-emerald)' : 'var(--border-subtle)'};">
        <h3 class="card-title">Seal & Finalize Meal</h3>
        <p class="card-desc">Once all items are claimed and verified, finalize to lock claims and compute individual shares.</p>
        
        ${warningHtml}

        <button id="finalize-btn" class="btn btn-success btn-block" ${!canFinalize ? 'disabled' : ''}>
          Finalize & Calculate Bill
        </button>
      </div>
    `;
  }

  app.innerHTML = html;
  bindEvents(snap);
  restoreFocus();
}

// --- Sub-renderers ---
function renderOrganizerSection(snap) {
  const receipt = snap.receipt;
  const items = receipt?.items || [];
  const reviewConfirmed = Boolean(snap.review);
  
  let itemsRowsHtml = items.map((it, idx) => `
    <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--border-subtle);">
      <div>
        <strong>${escapeHtml(it.label)}</strong>
        <span style="color: var(--text-dim); font-size: 0.85rem;">(x${it.quantity})</span>
      </div>
      <div style="font-weight: 600;">${formatSen(it.line_sen)}</div>
    </div>
  `).join('');

  let totalsHtml = '';
  if (items.length > 0 && receipt?.subtotal_sen !== null && receipt?.subtotal_sen !== undefined) {
    let adjRows = (receipt?.adjustments || []).map(a => `
      <div style="display: flex; justify-content: space-between; font-size: 0.85rem; color: var(--text-muted); margin-bottom: 2px;">
        <span>${escapeHtml(a.label || a.kind)}</span>
        <span>${formatSen(a.amount_sen)}</span>
      </div>
    `).join('');

    totalsHtml = `
      <div style="border-top: 1px solid var(--border-subtle); padding-top: 10px; margin-top: 10px;">
        <div style="display: flex; justify-content: space-between; font-size: 0.9rem; color: var(--text-muted); margin-bottom: 4px;">
          <span>Items Subtotal</span>
          <span>${formatSen(receipt.subtotal_sen)}</span>
        </div>
        ${adjRows}
        <div style="display: flex; justify-content: space-between; font-weight: 700; font-size: 1.05rem; margin-top: 4px;">
          <span>Receipt Total</span>
          <span style="color: #a7f3d0;">${formatSen(receipt.total_sen)}</span>
        </div>
      </div>
    `;
  }

  return `
    <div class="card">
      <div class="card-title">
        <span>Receipt & Charges</span>
        ${reviewConfirmed ? '<span class="badge badge-verified">Review Verified ✓</span>' : '<span class="badge badge-pending">Needs Review</span>'}
      </div>

      <div style="margin-bottom: 16px;">
        ${itemsRowsHtml || '<p style="color: var(--text-muted); font-size: 0.9rem;">No items added yet.</p>'}
        ${totalsHtml}
      </div>

      <!-- Local OCR Receipt Scanner -->
      <div style="background: var(--bg-main); padding: 14px; border-radius: var(--radius-md); margin-bottom: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
          <span style="font-weight: 600; font-size: 0.85rem; color: var(--text-muted);">LOCAL RECEIPT OCR SCANNER</span>
          <span style="font-size: 0.75rem; color: #a7f3d0; font-weight: 600;">Server-Side Local Inference</span>
        </div>
        <p style="font-size: 0.8rem; color: var(--text-dim); margin-bottom: 10px;">
          Upload a receipt photo (JPEG/PNG/WebP) to automatically extract items, taxes, and service charges via local server-side inference (RapidOCR ONNX). Requires physical verification before sealing.
        </p>
        <input type="file" id="ocr-file-input" accept="image/jpeg,image/png,image/webp" style="display: none;">
        <button type="button" id="ocr-upload-btn" class="btn btn-secondary btn-sm btn-block">📷 Scan Receipt Image</button>
        <div id="ocr-spinner" style="display: none; text-align: center; margin-top: 8px; font-size: 0.85rem; color: var(--accent-indigo);">
          Analyzing receipt via local server-side inference (RapidOCR ONNX)...
        </div>
      </div>

      ${state.ocrCandidate ? `
        <!-- Staged OCR Candidate Card with Polished Responsive Editor -->
        <div id="ocr-candidate-card" class="ocr-candidate-card">
          <div class="ocr-candidate-header">
            <span class="ocr-candidate-title">📋 SCANNED CANDIDATE (STAGED)</span>
            ${state.ocrCandidate.route === 'manual_correction'
              ? '<span class="badge" style="background: #fef3c7; color: #92400e; border: 1px solid #fcd34d;">⚠️ Needs Correction</span>'
              : '<span class="badge" style="background: #d1fae5; color: #065f46; border: 1px solid #a7f3d0;">✓ Ready for Review</span>'}
          </div>
          <p style="font-size: 0.85rem; color: var(--text-dim); margin-bottom: 12px; line-height: 1.4;">
            Staged in browser memory outside SQLite. Edit any misread items, quantities, line totals, taxes, discounts, or BNM cash rounding below before applying to authoritative receipt.
          </p>
          ${state.ocrCandidate.issues && state.ocrCandidate.issues.length > 0 ? `
            <div style="background: #fffbeb; border: 1px solid #fcd34d; border-radius: var(--radius-sm); padding: 8px 12px; margin-bottom: 12px; font-size: 0.82rem; color: #92400e;">
              <strong>Verification Note:</strong> ${escapeHtml(state.ocrCandidate.issues.join('; '))}
            </div>
          ` : ''}
          <div class="ocr-meta-bar">
            <span>Merchant: <strong>${escapeHtml(state.ocrCandidate.merchant || 'Unknown')}</strong></span>
            <span>Confidence: <strong>${((state.ocrCandidate.mean_confidence || 0) * 100).toFixed(1)}%</strong></span>
          </div>

          <!-- Section: Scanned Items -->
          <div class="ocr-section-title">
            <span>Receipt Items</span>
            <span class="ocr-section-hint">Amounts represent Line Totals (Qty &times; Unit Price)</span>
          </div>

          <!-- Candidate Items Table (Responsive Desktop Table + Mobile Stacked Cards) -->
          <div class="ocr-table-container">
            <table class="ocr-items-table">
              <thead>
                <tr>
                  <th>Item Name</th>
                  <th class="col-qty">Qty</th>
                  <th class="col-amount">Line Total (RM)</th>
                  <th class="col-unit">Unit Price (est.)</th>
                  <th class="col-action"></th>
                </tr>
              </thead>
              <tbody id="ocr-cand-items-body">
                ${state.ocrCandidate.items.map((it, idx) => {
                  const qtyVal = Array.isArray(it.quantity) ? it.quantity[0] : (it.quantity || 1);
                  const lineSen = it.line_sen || 0;
                  const unitSen = qtyVal > 0 ? Math.round(lineSen / qtyVal) : lineSen;
                  return `
                  <tr class="ocr-cand-item-row" data-idx="${idx}">
                    <td class="cell-label">
                      <div class="ocr-mobile-only ocr-field-label">Item Name</div>
                      <input type="text" id="ocr-item-label-${idx}" class="ocr-edit-item-label form-input" data-idx="${idx}" value="${escapeHtml(it.label)}" placeholder="Item name" />
                    </td>

                    <td class="cell-qty">
                      <div class="ocr-mobile-only ocr-field-label">Qty</div>
                      <input type="number" id="ocr-item-qty-${idx}" class="ocr-edit-item-qty form-input" data-idx="${idx}" min="1" step="1" value="${qtyVal}" />
                    </td>

                    <td class="cell-amount">
                      <div class="ocr-mobile-only ocr-field-label">Line Total (RM)</div>
                      <input type="text" id="ocr-item-price-${idx}" class="ocr-edit-item-price form-input" data-idx="${idx}" value="${(lineSen / 100).toFixed(2)}" placeholder="0.00" />
                      <div class="ocr-mobile-only ocr-cand-item-unit-mobile ocr-cand-item-unit" data-idx="${idx}">@ RM ${(unitSen / 100).toFixed(2)} ea</div>
                    </td>

                    <td class="cell-unit ocr-desktop-only">
                      <span class="ocr-cand-item-unit" data-idx="${idx}">@ RM ${(unitSen / 100).toFixed(2)}</span>
                    </td>

                    <td class="cell-action">
                      <button type="button" class="ocr-del-btn ocr-del-item-btn" data-idx="${idx}" title="Remove item" aria-label="Remove item">✕</button>
                    </td>
                  </tr>
                `;}).join('')}
              </tbody>
            </table>
            <div class="ocr-table-footer">
              <button type="button" id="ocr-add-item-btn" class="btn btn-secondary btn-sm">+ Add Missing Item</button>
              <span style="font-size: 0.8rem; color: var(--text-dim);">${state.ocrCandidate.items.length} item(s)</span>
            </div>
          </div>

          <!-- Section: Adjustments, Taxes & BNM Rounding -->
          <div style="background: var(--bg-main); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle); margin-bottom: 14px;">
            <div class="ocr-section-title">
              <span>Adjustments, Taxes & Discounts</span>
              <span class="ocr-section-hint">Signed minor units (e.g. -0.02 BNM rounding)</span>
            </div>
            <div id="ocr-cand-adjustments-list">
              ${(state.ocrCandidate.adjustments || []).map((adj, idx) => `
                <div class="ocr-cand-adj-row" data-adj-idx="${idx}">
                  <input type="text" id="ocr-adj-label-${idx}" class="ocr-edit-adj-label form-input" data-adj-idx="${idx}" value="${escapeHtml(adj.label || '')}" placeholder="Label (e.g. Service Charge)" style="flex: 2; min-height: 44px;" />
                  <div class="ocr-adj-controls-mobile">
                    <select id="ocr-adj-kind-${idx}" class="ocr-edit-adj-kind form-input" data-adj-idx="${idx}" style="min-height: 44px;">
                      <option value="service" ${adj.kind === 'service' ? 'selected' : ''}>Service Charge</option>
                      <option value="tax" ${adj.kind === 'tax' ? 'selected' : ''}>SST / Tax</option>
                      <option value="discount" ${adj.kind === 'discount' ? 'selected' : ''}>Discount</option>
                      <option value="rounding" ${adj.kind === 'rounding' ? 'selected' : ''}>BNM Rounding</option>
                    </select>
                    <input type="text" id="ocr-adj-amount-${idx}" class="ocr-edit-adj-amount form-input" data-adj-idx="${idx}" value="${adj.kind === 'discount' ? (Math.abs(adj.amount_sen || 0) / 100).toFixed(2) : ((adj.amount_sen || 0) / 100).toFixed(2)}" placeholder="0.00" style="width: 100px; text-align: right; font-family: monospace; min-height: 44px;" />
                    <button type="button" class="ocr-del-btn ocr-del-adj-btn" data-adj-idx="${idx}" title="Remove charge" aria-label="Remove adjustment">✕</button>
                  </div>
                </div>
              `).join('')}
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 10px;">
              <button type="button" id="ocr-add-adj-btn" class="btn btn-secondary btn-sm" style="min-height: 44px;">+ Add Fee / Tax / Rounding</button>
            </div>

            <!-- Tax-inclusive Included SST -->
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 12px; padding-top: 10px; border-top: 1px dashed var(--border-subtle); font-size: 0.85rem; color: var(--text-dim); flex-wrap: wrap; gap: 6px;">
              <span>Included SST (tax-inclusive, informational):</span>
              <div style="display: flex; align-items: center; gap: 6px;">
                <span>RM</span>
                <input type="text" id="ocr-edit-included-tax" class="form-input" value="${((state.ocrCandidate.included_tax_sen || 0) / 100).toFixed(2)}" style="width: 80px; text-align: right; min-height: 44px; font-family: monospace;" />
              </div>
            </div>

            <!-- Dynamic Recalculated Totals Display -->
            <div style="border-top: 1px solid var(--border-subtle); margin-top: 12px; padding-top: 10px;">
              <div style="display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 0.9rem;">
                <span style="color: var(--text-muted);">Candidate Subtotal (sum of line totals):</span>
                <span id="ocr-cand-subtotal-val" style="font-weight: 600; font-family: monospace;">${formatSen(state.ocrCandidate.subtotal_sen)}</span>
              </div>
              <div style="display: flex; justify-content: space-between; font-weight: 700; font-size: 1.05rem;">
                <span>Candidate Final Total:</span>
                <span id="ocr-cand-total-val" style="color: #a5b4fc; font-family: monospace;">${formatSen(state.ocrCandidate.total_sen)}</span>
              </div>
            </div>
          </div>

          ${snap.receipt && snap.receipt.items && snap.receipt.items.length > 0 ? `
            <div style="background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: var(--radius-sm); padding: 8px 12px; margin-bottom: 12px; font-size: 0.8rem; color: #fde68a;">
              ⚠️ Applying candidate will replace the ${snap.receipt.items.length} existing items on the draft receipt.
            </div>
          ` : ''}
          <div style="display: flex; gap: 10px; flex-wrap: wrap;">
            <button type="button" id="ocr-accept-btn" class="btn btn-primary" style="flex: 2; min-height: 48px; font-size: 1rem;">Accept & Apply to Receipt</button>
            <button type="button" id="ocr-discard-btn" class="btn btn-secondary" style="flex: 1; min-height: 48px; font-size: 1rem;">Discard</button>
          </div>
        </div>
      ` : ''}

      <!-- Add Item Form -->
      <form id="add-item-form" style="background: var(--bg-main); padding: 14px; border-radius: var(--radius-md); margin-bottom: 16px;">
        <div style="font-weight: 600; font-size: 0.85rem; margin-bottom: 8px; color: var(--text-muted);">ADD RECEIPT ITEM</div>
        <div style="display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 8px; margin-bottom: 10px;">
          <input type="text" id="new-item-label" placeholder="Item name" required>
          <input type="number" id="new-item-qty" value="1" min="1" step="1" required>
          <input type="text" id="new-item-price" placeholder="RM 0.00" required>
        </div>
        <button type="submit" class="btn btn-secondary btn-sm btn-block">+ Add Item</button>
      </form>

      <!-- Review & Verification Card -->
      <div style="background: var(--bg-main); padding: 14px; border-radius: var(--radius-md);">
        <div style="font-weight: 600; font-size: 0.85rem; margin-bottom: 8px; color: var(--text-muted);">HUMAN RECEIPT REVIEW</div>
        <p style="font-size: 0.85rem; color: var(--text-dim); margin-bottom: 10px;">
          Examine the items above against the merchant receipt. Confirm the digest before finalization.
        </p>
        <label style="display: flex; align-items: center; gap: 8px; text-transform: none; color: var(--text-main); font-size: 0.9rem; cursor: pointer;">
          <input type="checkbox" id="review-confirm-check" ${reviewConfirmed ? 'checked disabled' : ''}>
          I confirm totals match the physical bill.
        </label>
        ${!reviewConfirmed ? `
          <button id="review-submit-btn" class="btn btn-primary btn-sm btn-block" style="margin-top: 10px;" disabled>
            Approve & Seal Receipt
          </button>
        ` : ''}
      </div>
    </div>

    <!-- Invitation Hub -->
    <div class="card">
      <div class="card-title">Diner Invitations</div>
      <p class="card-desc">Send single-use invite links to your dining companions so they can claim portions.</p>
      <div id="invitation-list">
        ${renderInvitationList(snap)}
      </div>
    </div>
  `;
}

function renderInvitationList(snap) {
  const diners = snap.participants?.filter(p => !p.organizer) || [];
  if (diners.length === 0) {
    return '<p style="color: var(--text-dim); font-size: 0.85rem;">No other diners declared in this meal room.</p>';
  }

  return diners.map(d => {
    const inv = snap.invitations?.find(i => i.participant_id === d.id && !i.revoked);
    let actionHtml = '';

    if (!inv) {
      actionHtml = `<button class="btn btn-secondary btn-sm issue-invite-btn" data-id="${d.id}">Create Link</button>`;
    } else if (inv.consumed) {
      actionHtml = '<span class="badge badge-verified">Joined ✓</span>';
    } else {
      const hasToken = Boolean(state.issuedTokens[d.id]);
      actionHtml = `
        <button class="btn ${hasToken ? 'btn-primary' : 'btn-secondary'} btn-sm copy-invite-btn" data-part="${d.id}" title="${hasToken ? 'Copy Invite Link' : 'Invite Active'}">
          ${hasToken ? '📋 Copy Link' : '📋 Active Link'}
        </button>
      `;
    }

    return `
      <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--border-subtle);">
        <span style="font-weight: 600;">${escapeHtml(d.name)}</span>
        <div>${actionHtml}</div>
      </div>
    `;
  }).join('');
}

function renderClaimsSection(snap) {
  const receipt = snap.receipt;
  const items = receipt?.items || [];
  if (items.length === 0) {
    return `
      <div class="card">
        <h3 class="card-title">${snap.is_organizer ? 'Item Allocation' : 'Item Claims'}</h3>
        <p class="card-desc">No receipt items to claim. The organizer must add items first.</p>
      </div>
    `;
  }

  // Active participants list
  const activeParts = snap.participants?.filter(p => !snap.inactive_participant_ids?.includes(p.id)) || [];
  const validTarget = activeParts.some(p => p.id === state.allocationTargetId);
  if (!validTarget && activeParts.length > 0) {
    state.allocationTargetId = state.currentUserId || activeParts[0].id;
  }
  const currentTarget = activeParts.find(p => p.id === state.allocationTargetId) || activeParts[0];

  let selectorBarHtml = '';
  if (snap.is_organizer && activeParts.length > 0) {
    selectorBarHtml = `
      <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 12px 14px; margin-bottom: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
          <div>
            <div style="font-weight: 700; font-size: 0.9rem; color: #a5b4fc;">ALLOCATION TARGET SELECTOR</div>
            <div style="font-size: 0.8rem; color: var(--text-dim);">Select who you are allocating items for. (Diners do not need to log in for organizer-managed meals).</div>
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <label for="allocation-target-select" style="font-size: 0.82rem; font-weight: 600; color: var(--text-muted); margin: 0; white-space: nowrap;">Allocating for:</label>
            <select id="allocation-target-select" class="form-input" style="min-height: 40px; padding: 6px 12px; font-weight: 600; min-width: 170px;">
              ${activeParts.map(p => `
                <option value="${p.id}" ${p.id === currentTarget?.id ? 'selected' : ''}>
                  ${p.organizer ? '👑' : '🍽️'} ${escapeHtml(p.name)}${p.id === state.currentUserId ? ' (You)' : ''}
                </option>
              `).join('')}
            </select>
          </div>
        </div>
      </div>
    `;
  }

  const itemsHtml = items.map(item => {
    const stateItem = snap.items?.find(i => i.item_id === item.id);
    const itemRevision = stateItem ? stateItem.item_revision : 0;
    const claims = snap.claims?.filter(c => c.item_id === item.id) || [];
    
    // Target participant's claim (for organizer, currentTarget; for diner, currentUserId)
    const activeUserId = snap.is_organizer ? (currentTarget?.id || state.currentUserId) : state.currentUserId;
    const targetClaim = claims.find(c => c.participant_id === activeUserId);
    const targetQty = targetClaim ? (Array.isArray(targetClaim.quantity) ? targetClaim.quantity[0]/targetClaim.quantity[1] : targetClaim.quantity) : 0;

    // Total claimed & capacity
    const totalClaimed = claims.reduce((acc, c) => acc + (Array.isArray(c.quantity) ? c.quantity[0]/c.quantity[1] : c.quantity), 0);
    const itemTotalQty = Array.isArray(item.quantity) ? item.quantity[0]/item.quantity[1] : item.quantity;
    const pct = Math.min(100, Math.round((totalClaimed / itemTotalQty) * 100));
    const unassigned = Math.max(0, itemTotalQty - totalClaimed);

    // Status badge
    let statusBadge = '';
    if (totalClaimed === itemTotalQty) {
      statusBadge = '<span class="badge badge-verified">✓ Fully Allocated</span>';
    } else if (totalClaimed < itemTotalQty) {
      statusBadge = `<span class="badge badge-pending">⚠️ ${unassigned} unassigned</span>`;
    } else {
      statusBadge = '<span class="badge" style="background: rgba(244,63,94,0.2); color: #fecdd3; border: 1px solid var(--accent-rose);">⚠️ Over-allocated</span>';
    }

    // Chips for diners with audit distinction
    const chipsHtml = claims.map(c => {
      const p = snap.participants?.find(part => part.id === c.participant_id);
      const name = p ? p.name : c.participant_id;
      const isSelected = c.participant_id === activeUserId;
      const qStr = Array.isArray(c.quantity) ? `${c.quantity[0]}/${c.quantity[1]}` : c.quantity;
      let badgeLabel = '';
      if (c.assigned_by && c.assigned_by !== c.participant_id) {
        badgeLabel = ' <span style="font-size: 0.68rem; color: #a5b4fc;">(Organizer Assigned)</span>';
      } else if (!p?.organizer) {
        badgeLabel = ' <span style="font-size: 0.68rem; color: #6ee7b7;">(Diner Claim)</span>';
      }
      return `<span class="chip ${isSelected ? 'own-chip' : ''}">${escapeHtml(name)}: ${qStr}${badgeLabel}</span>`;
    }).join('');

    const actionLabel = snap.is_organizer
      ? `Portion for ${escapeHtml(currentTarget?.name || 'Selected')}:`
      : 'Your Portion:';

    return `
      <div class="item-card" id="item-card-${item.id}" data-item-id="${item.id}" data-revision="${itemRevision}">
        <div class="item-header">
          <div>
            <div class="item-label">${escapeHtml(item.label)}</div>
            <div class="item-meta">Total: ${itemTotalQty} &bull; Allocated: ${totalClaimed} / ${itemTotalQty} &bull; ${statusBadge}</div>
          </div>
          <div class="item-price">${formatSen(item.line_sen)}</div>
        </div>

        <div class="progress-bar-wrap">
          <div class="progress-bar-fill ${totalClaimed > itemTotalQty ? 'overclaimed' : ''}" style="width: ${pct}%"></div>
        </div>

        <div class="claim-actions">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="font-size: 0.85rem; font-weight: 600; color: var(--text-muted);">${actionLabel}</span>
            <div class="quantity-stepper">
              <button class="btn btn-secondary btn-sm claim-dec-btn" data-id="${item.id}" data-current="${targetQty}" data-target="${activeUserId}" data-rev="${itemRevision}">-</button>
              <span class="step-val">${targetQty}</span>
              <button class="btn btn-secondary btn-sm claim-inc-btn" data-id="${item.id}" data-current="${targetQty}" data-target="${activeUserId}" data-rev="${itemRevision}">+</button>
            </div>
          </div>
          <div>
            <button class="btn btn-secondary btn-sm claim-all-btn" data-id="${item.id}" data-target="${activeUserId}" data-rev="${itemRevision}" data-total="${itemTotalQty}" data-unassigned="${unassigned}">
              ${snap.is_organizer ? 'Assign All' : 'Claim All'}
            </button>
          </div>
        </div>

        ${chipsHtml ? `<div class="chips-row">${chipsHtml}</div>` : ''}
      </div>
    `;
  }).join('');

  return `
    <div class="card">
      <h3 class="card-title">${snap.is_organizer ? 'Item Allocation (Organizer & Collaborative)' : 'Claim Your Portions'}</h3>
      <p class="card-desc">
        ${snap.is_organizer 
          ? 'Assign portions for any diner below. Collaborative diners can also claim their own portions.'
          : 'Tap + or - to set your claimed portion for each item. Overlapping claims split the cost.'}
      </p>
      ${selectorBarHtml}
      ${itemsHtml}
    </div>
  `;
}

function renderFinalizedCalculation(snap) {
  const calc = snap.calculation;
  if (!calc || !Array.isArray(calc.consumption)) {
    return `
      <div class="card">
        <div class="card-title" style="color: var(--accent-rose);">Calculation Data Missing</div>
        <p class="card-desc">Finalized calculation records could not be loaded.</p>
      </div>
    `;
  }

  const consumptionMap = new Map();
  for (const entry of calc.consumption) {
    if (entry && entry.participant_id !== undefined && entry.sen !== undefined) {
      consumptionMap.set(entry.participant_id, entry.sen);
    }
  }

  let grandTotalSen = snap.receipt?.total_sen;
  if (grandTotalSen === null || grandTotalSen === undefined) {
    grandTotalSen = calc.consumption.reduce((sum, c) => sum + (c.sen ?? 0), 0);
  }

  const dinersRows = snap.participants?.map(p => {
    if (!consumptionMap.has(p.id)) {
      return `
        <tr>
          <td><strong>${escapeHtml(p.name)}</strong> ${p.organizer ? '(Organizer)' : ''}</td>
          <td class="amount" style="color: var(--accent-rose);">Amount Missing</td>
        </tr>
      `;
    }
    const totalSen = consumptionMap.get(p.id);
    return `
      <tr>
        <td><strong>${escapeHtml(p.name)}</strong> ${p.organizer ? '(Organizer)' : ''}</td>
        <td class="amount" style="color: #6ee7b7; font-weight: 700;">${formatSen(totalSen)}</td>
      </tr>
    `;
  }).join('');

  const parentVal = state.notionParentId || '';
  const tokenVal = state.notionToken || '';

  let exportResultHtml = '';
  if (state.notionExport && (state.notionExport.status === 'completed' || state.notionExport.status === 'already_exported')) {
    exportResultHtml = `
      <div id="notion-export-result" style="display: block; margin-top: 0.75rem; padding: 0.75rem; border-radius: 6px; background-color: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); color: #6ee7b7;">
        <strong>✓ Export Successful!</strong><br/>
        Page ID: <code style="font-size: 0.8rem;">${escapeHtml(state.notionExport.page_id || '')}</code><br/>
        <a href="${escapeHtml(state.notionExport.page_url || '#')}" target="_blank" rel="noopener noreferrer" style="color: #6ee7b7; font-weight: bold; text-decoration: underline; display: inline-block; margin-top: 0.5rem;" id="notion-page-link">
          Open Report in Notion ↗
        </a>
      </div>
    `;
  } else if (state.notionExport && state.notionExport.status === 'failed') {
    exportResultHtml = `
      <div id="notion-export-result" style="display: block; margin-top: 0.75rem; padding: 0.75rem; border-radius: 6px; background-color: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); color: var(--accent-rose);">
        Export failed: ${escapeHtml(state.notionExport.export_digest || 'notion_error')}
      </div>
    `;
  } else {
    exportResultHtml = `<div id="notion-export-result" style="display: none; margin-top: 0.75rem; padding: 0.75rem; border-radius: 6px;"></div>`;
  }

  return `
    <div class="card">
      <div class="card-title" style="color: var(--accent-emerald);">Final Apportionment Summary</div>
      <p class="card-desc">Every cent accounted for. Apportionment rounded deterministically with cent conservation.</p>

      <table class="breakdown-table">
        <thead>
          <tr>
            <th>Participant</th>
            <th style="text-align: right;">Total Share</th>
          </tr>
        </thead>
        <tbody>
          ${dinersRows}
          <tr class="breakdown-total-row">
            <td>Grand Total</td>
            <td class="amount">${formatSen(grandTotalSen)}</td>
          </tr>
        </tbody>
      </table>

      ${snap.is_organizer ? `
        <div class="card" id="notion-export-card" style="margin-top: 1.5rem; border-color: rgba(99, 102, 241, 0.4); background: rgba(99, 102, 241, 0.05);">
          <div class="card-title" style="color: #818cf8;">📤 Notion Archive & Reporting</div>
          <p class="card-desc">Export an immutable, structured summary to your Notion workspace in Compact Mode (&le; 40 blocks).</p>

          <div id="notion-export-controls">
            <div style="display: flex; flex-direction: column; gap: 0.35rem; margin-bottom: 0.75rem;">
              <label style="font-size: 0.8rem; color: var(--text-muted);">Notion Parent Page URL or UUID:</label>
              <input type="text" id="notion-parent-id" value="${escapeHtml(parentVal)}" placeholder="Paste Notion page URL or UUID (e.g. 3fb0ffe1-72a6-815e-b59d-ef81c6e8eb4d)" class="form-input" style="font-family: monospace; font-size: 0.85rem;" />
            </div>
            <div style="display: flex; flex-direction: column; gap: 0.35rem; margin-bottom: 0.75rem;">
              <label style="font-size: 0.8rem; color: var(--text-muted);">Integration Token (optional if set on server):</label>
              <input type="password" id="notion-token" value="${escapeHtml(tokenVal)}" placeholder="secret_..." class="form-input" style="font-family: monospace; font-size: 0.85rem;" />
            </div>
            <button id="notion-export-btn" class="btn btn-primary" style="width: 100%;">
              Export Finalized Report to Notion
            </button>
          </div>

          <div id="notion-export-spinner" style="display: none; text-align: center; padding: 1rem; color: var(--text-muted);">
            ⏳ Creating structured Notion page...
          </div>

          ${exportResultHtml}
        </div>
      ` : ''}
    </div>
  `;
}

// --- Event Binding ---
function bindEvents(snap) {
  // Navigation: Leave Room button
  const roomLeaveBtn = document.getElementById('room-leave-btn');
  if (roomLeaveBtn) {
    roomLeaveBtn.addEventListener('click', handleLeaveRoom);
  }

  // 1. Add Item Form
  const addItemForm = document.getElementById('add-item-form');
  if (addItemForm) {
    addItemForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const label = document.getElementById('new-item-label').value.trim();
      const qty = parseInt(document.getElementById('new-item-qty').value, 10);
      if (!label) {
        showAlert('Item name is required', 'error');
        return;
      }
      if (!qty || qty < 1) {
        showAlert('Quantity must be at least 1', 'error');
        return;
      }

      let priceSen;
      try {
        priceSen = parseSen(document.getElementById('new-item-price').value);
        if (priceSen <= 0) {
          showAlert('Price must be greater than RM 0.00', 'error');
          return;
        }
      } catch (err) {
        showAlert(err.message, 'error');
        return;
      }

      const currentItems = snap.receipt?.items ? [...snap.receipt.items] : [];
      const newItemId = `item-${currentItems.length + 1}`;
      currentItems.push({
        id: newItemId,
        label,
        quantity: qty,
        line_sen: priceSen,
      });

      const subtotalSen = currentItems.reduce((acc, it) => acc + (it.line_sen || 0), 0);
      const adjTotal = (snap.receipt?.adjustments || []).reduce((acc, a) => acc + (a.amount_sen || 0), 0);
      const totalSen = subtotalSen + adjTotal;

      state.mutationActive = true;
      try {
        await apiCall(`/api/meals/${state.mealId}/apply`, 'POST', {
          kind: 'ReplaceReceipt',
          command_id: `rcpt-${Date.now()}`,
          expected_revision: snap.revision,
          expected_financial_revision: snap.financial_revision,
          receipt: {
            items: currentItems,
            subtotal_sen: subtotalSen,
            total_sen: totalSen,
            adjustments: snap.receipt?.adjustments || [],
            included_tax_sen: snap.receipt?.included_tax_sen || 0,
          }
        });
        state.mutationActive = false;
        await fetchSnapshot(true);
        showAlert(`Added "${label}" (${formatSen(priceSen)}) ✓`, 'success');
      } catch (err) {
        state.mutationActive = false;
        handleApiError(err);
      } finally {
        state.mutationActive = false;
      }
    });
  }

  // 1b. OCR Receipt Scanner Upload
  const ocrBtn = document.getElementById('ocr-upload-btn');
  const ocrInput = document.getElementById('ocr-file-input');
  const ocrSpinner = document.getElementById('ocr-spinner');
  if (ocrBtn && ocrInput) {
    ocrBtn.addEventListener('click', () => ocrInput.click());
    ocrInput.addEventListener('change', async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;

      if (ocrSpinner) ocrSpinner.style.display = 'block';
      ocrBtn.disabled = true;

      let mimeType = file.type;
      if (!mimeType) {
        const lowerName = (file.name || '').toLowerCase();
        if (lowerName.endsWith('.png')) mimeType = 'image/png';
        else if (lowerName.endsWith('.webp')) mimeType = 'image/webp';
        else mimeType = 'image/jpeg';
      }

      try {
        const res = await fetch(`/api/meals/${state.mealId}/ocr/extract`, {
          method: 'POST',
          headers: {
            'Content-Type': mimeType,
            'X-SettleTable-Action': '1',
          },
          body: file,
        });
        const data = await res.json();
        if (!res.ok || !data.ok) {
          throw { status: res.status, code: data.error, message: data.error };
        }

        const candidate = data.candidate;
        if (!candidate.items || candidate.items.length === 0) {
          showAlert('No receipt items recognized from photo. Please enter items manually.', 'error');
          return;
        }

        // Stage candidate outside authoritative SQLite state until explicit organizer acceptance
        state.ocrCandidate = candidate;
        updateMealUI();

        if (candidate.route === 'manual_correction' || (candidate.issues && candidate.issues.length > 0)) {
          showAlert(`Extracted ${candidate.items.length} candidate items (${formatSen(candidate.total_sen)}). Please inspect and verify before accepting.`, 'conflict');
        } else {
          showAlert(`Extracted ${candidate.items.length} candidate items (${formatSen(candidate.total_sen)}). Please inspect and accept below.`, 'success');
        }
      } catch (err) {
        state.mutationActive = false;
        if (err.status === 503 || err.code === 'ocr_unavailable') {
          showAlert('Local OCR engine unavailable. Please enter items manually.', 'error');
        } else if (err.status === 413 || err.code === 'payload_too_large') {
          showAlert('Receipt image exceeds 5MB limit. Please upload a smaller photo.', 'error');
        } else {
          handleApiError(err);
        }
      } finally {
        if (ocrSpinner) ocrSpinner.style.display = 'none';
        ocrBtn.disabled = false;
        ocrInput.value = '';
      }
    });
  }

  // 1c. Staged OCR Candidate Edit & Verification Actions
  const syncCandidateInputs = () => {
    if (!state.ocrCandidate) return;
    const cand = state.ocrCandidate;

    // Read items from candidate table
    const itemRows = document.querySelectorAll('.ocr-cand-item-row');
    const items = [];
    itemRows.forEach((row, i) => {
      const labelInput = row.querySelector('.ocr-edit-item-label');
      const qtyInput = row.querySelector('.ocr-edit-item-qty');
      const priceInput = row.querySelector('.ocr-edit-item-price');
      const label = labelInput ? (labelInput.value.trim() || `Item ${i + 1}`) : `Item ${i + 1}`;
      const qty = qtyInput ? Math.max(1, parseInt(qtyInput.value, 10) || 1) : 1;
      let lineSen = 0;
      if (priceInput) {
        try {
          lineSen = parseSen(priceInput.value);
        } catch {
          lineSen = 0;
        }
      }
      const existingId = (cand.items && cand.items[i]) ? cand.items[i].id : `item-${i + 1}`;
      items.push({ id: existingId, label, quantity: qty, line_sen: lineSen });

      // Update unit price estimate displays live
      const unitSen = qty > 0 ? Math.round(lineSen / qty) : lineSen;
      row.querySelectorAll('.ocr-cand-item-unit').forEach(unitEl => {
        const isMobile = unitEl.classList.contains('ocr-cand-item-unit-mobile');
        unitEl.textContent = `@ RM ${(unitSen / 100).toFixed(2)}${isMobile ? ' ea' : ''}`;
      });
    });

    // Read adjustments from candidate list
    const adjRows = document.querySelectorAll('.ocr-cand-adj-row');
    const adjustments = [];
    adjRows.forEach((row, j) => {
      const labelInput = row.querySelector('.ocr-edit-adj-label');
      const kindSelect = row.querySelector('.ocr-edit-adj-kind');
      const amountInput = row.querySelector('.ocr-edit-adj-amount');
      const label = labelInput ? (labelInput.value.trim() || 'Adjustment') : 'Adjustment';
      const kind = kindSelect ? kindSelect.value : 'service';
      let rawSen = 0;
      if (amountInput) {
        try {
          rawSen = parseSen(amountInput.value, true);
        } catch {
          rawSen = 0;
        }
      }
      let amountSen = rawSen;
      if (kind === 'discount') {
        amountSen = -Math.abs(rawSen);
      } else if (kind === 'service' || kind === 'tax') {
        amountSen = Math.abs(rawSen);
      } else if (kind === 'rounding') {
        if (amountInput && amountInput.value.trim().startsWith('-')) {
          amountSen = -Math.abs(rawSen);
        } else {
          amountSen = Math.abs(rawSen);
        }
      }
      const existingId = (cand.adjustments && cand.adjustments[j]) ? cand.adjustments[j].id : `adj-${j + 1}`;
      const existingRationale = (cand.adjustments && cand.adjustments[j] && cand.adjustments[j].rationale)
        ? cand.adjustments[j].rationale
        : `${label} adjustment`;
      const eligible = (cand.adjustments && cand.adjustments[j] && cand.adjustments[j].eligible_item_ids)
        ? cand.adjustments[j].eligible_item_ids
        : items.map(it => it.id);
      adjustments.push({
        id: existingId,
        label,
        kind,
        amount_sen: amountSen,
        eligible_item_ids: eligible,
        rationale: existingRationale,
      });
    });

    // Read included tax
    const incTaxInput = document.getElementById('ocr-edit-included-tax');
    let incTaxSen = 0;
    if (incTaxInput) {
      try {
        incTaxSen = parseSen(incTaxInput.value);
      } catch {
        incTaxSen = 0;
      }
    }

    const subtotalSen = items.reduce((acc, it) => acc + (it.line_sen || 0), 0);
    const adjTotalSen = adjustments.reduce((acc, a) => acc + (a.amount_sen || 0), 0);
    const totalSen = subtotalSen + adjTotalSen;

    cand.items = items;
    cand.adjustments = adjustments;
    cand.included_tax_sen = incTaxSen;
    cand.subtotal_sen = subtotalSen;
    cand.total_sen = totalSen;

    const subtotalValEl = document.getElementById('ocr-cand-subtotal-val');
    const totalValEl = document.getElementById('ocr-cand-total-val');
    if (subtotalValEl) subtotalValEl.textContent = formatSen(subtotalSen);
    if (totalValEl) totalValEl.textContent = formatSen(totalSen);
  };

  if (state.ocrCandidate) {
    document.querySelectorAll('.ocr-edit-item-label, .ocr-edit-item-qty, .ocr-edit-item-price, .ocr-edit-adj-label, .ocr-edit-adj-kind, .ocr-edit-adj-amount, #ocr-edit-included-tax').forEach(el => {
      el.addEventListener('input', syncCandidateInputs);
      el.addEventListener('change', syncCandidateInputs);
    });

    document.getElementById('ocr-add-item-btn')?.addEventListener('click', () => {
      syncCandidateInputs();
      const items = state.ocrCandidate.items || [];
      items.push({
        id: `item-${items.length + 1}`,
        label: `Item ${items.length + 1}`,
        quantity: 1,
        line_sen: 1000,
      });
      state.ocrCandidate.items = items;
      state.ocrCandidate.subtotal_sen = items.reduce((s, i) => s + (i.line_sen || 0), 0);
      state.ocrCandidate.total_sen = state.ocrCandidate.subtotal_sen + (state.ocrCandidate.adjustments || []).reduce((s, a) => s + (a.amount_sen || 0), 0);
      updateMealUI();
    });

    document.querySelectorAll('.ocr-del-item-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        syncCandidateInputs();
        const idx = parseInt(btn.getAttribute('data-idx'), 10);
        if (state.ocrCandidate.items && state.ocrCandidate.items.length > 1) {
          state.ocrCandidate.items.splice(idx, 1);
          state.ocrCandidate.subtotal_sen = state.ocrCandidate.items.reduce((s, i) => s + (i.line_sen || 0), 0);
          state.ocrCandidate.total_sen = state.ocrCandidate.subtotal_sen + (state.ocrCandidate.adjustments || []).reduce((s, a) => s + (a.amount_sen || 0), 0);
          updateMealUI();
        } else {
          showAlert('Candidate must have at least one receipt item.', 'conflict');
        }
      });
    });

    document.getElementById('ocr-add-adj-btn')?.addEventListener('click', () => {
      syncCandidateInputs();
      const adjs = state.ocrCandidate.adjustments || [];
      const allItemIds = (state.ocrCandidate.items || []).map(it => it.id);
      adjs.push({
        id: `adj-${adjs.length + 1}`,
        label: 'Service Charge',
        kind: 'service',
        amount_sen: 100,
        eligible_item_ids: allItemIds,
      });
      state.ocrCandidate.adjustments = adjs;
      state.ocrCandidate.total_sen = (state.ocrCandidate.subtotal_sen || 0) + adjs.reduce((s, a) => s + (a.amount_sen || 0), 0);
      updateMealUI();
    });

    document.querySelectorAll('.ocr-del-adj-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        syncCandidateInputs();
        const idx = parseInt(btn.getAttribute('data-adj-idx'), 10);
        if (state.ocrCandidate.adjustments) {
          state.ocrCandidate.adjustments.splice(idx, 1);
          state.ocrCandidate.total_sen = (state.ocrCandidate.subtotal_sen || 0) + state.ocrCandidate.adjustments.reduce((s, a) => s + (a.amount_sen || 0), 0);
          updateMealUI();
        }
      });
    });
  }

  const ocrAcceptBtn = document.getElementById('ocr-accept-btn');
  const ocrDiscardBtn = document.getElementById('ocr-discard-btn');
  if (ocrAcceptBtn && state.ocrCandidate) {
    ocrAcceptBtn.addEventListener('click', async () => {
      syncCandidateInputs();
      const candidate = state.ocrCandidate;
      if (!candidate) return;

      if (!candidate.items || candidate.items.length === 0) {
        showAlert('Candidate must have at least one receipt item.', 'error');
        return;
      }

      for (const it of candidate.items) {
        if (!it.label || it.line_sen <= 0) {
          showAlert(`Item "${it.label || 'Unnamed'}" must have a valid name and price greater than RM 0.00`, 'error');
          return;
        }
      }

      const allItemIds = candidate.items.map(i => i.id);
      const itemIdSet = new Set(allItemIds);
      const cleanAdjustments = (candidate.adjustments || []).map((adj, idx) => {
        const filteredEligible = (adj.eligible_item_ids || []).filter(id => itemIdSet.has(id));
        const finalEligible = filteredEligible.length > 0 ? filteredEligible : allItemIds;
        const fallbackRationale = `${adj.label || adj.kind || 'Receipt'} adjustment`;
        return {
          id: adj.id || `adj-${idx + 1}`,
          label: adj.label || adj.kind || 'Adjustment',
          kind: adj.kind || 'rounding',
          amount_sen: adj.amount_sen,
          eligible_item_ids: finalEligible,
          rationale: (adj.rationale && adj.rationale.trim()) ? adj.rationale.trim() : fallbackRationale,
        };
      });

      ocrAcceptBtn.disabled = true;
      state.mutationActive = true;
      try {
        await apiCall(`/api/meals/${state.mealId}/apply`, 'POST', {
          kind: 'ReplaceReceipt',
          command_id: `ocr-rcpt-${Date.now()}`,
          expected_revision: snap.revision,
          expected_financial_revision: snap.financial_revision,
          receipt: {
            items: candidate.items,
            subtotal_sen: candidate.subtotal_sen,
            total_sen: candidate.total_sen,
            adjustments: cleanAdjustments,
            included_tax_sen: candidate.included_tax_sen || 0,
          }
        });
        state.ocrCandidate = null;
        state.mutationActive = false;
        await fetchSnapshot(true);
        showAlert('Scanned receipt accepted and applied to draft. Mandatory human receipt review is still required before finalization.', 'success');
      } catch (err) {
        state.mutationActive = false;
        ocrAcceptBtn.disabled = false;
        handleApiError(err);
      }
    });
  }
  if (ocrDiscardBtn) {
    ocrDiscardBtn.addEventListener('click', () => {
      state.ocrCandidate = null;
      updateMealUI();
      showAlert('Scanned receipt candidate discarded. Existing receipt unchanged.', 'info');
    });
  }

  // 2. Review Confirmation Checkbox & Button
  const reviewCheck = document.getElementById('review-confirm-check');
  const reviewBtn = document.getElementById('review-submit-btn');
  if (reviewCheck && reviewBtn) {
    reviewCheck.addEventListener('change', () => {
      reviewBtn.disabled = !reviewCheck.checked;
    });

    reviewBtn.addEventListener('click', async () => {
      state.mutationActive = true;
      try {
        await apiCall(`/api/meals/${state.mealId}/apply`, 'POST', {
          kind: 'ReviewReceipt',
          command_id: `rev-${Date.now()}`,
          expected_revision: snap.revision,
          expected_financial_revision: snap.financial_revision,
          receipt_digest: snap.receipt_digest,
        });
        state.mutationActive = false;
        await fetchSnapshot(true);
        showAlert('Receipt verified and sealed ✓', 'success');
      } catch (err) {
        state.mutationActive = false;
        handleApiError(err);
      } finally {
        state.mutationActive = false;
      }
    });
  }

  // 3. Issue Invite Buttons
  document.querySelectorAll('.issue-invite-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const partId = btn.getAttribute('data-id');
      try {
        btn.disabled = true;
        btn.textContent = 'Creating...';
        const invRes = await apiCall(`/api/meals/${state.mealId}/invitations`, 'POST', {
          participant_id: partId,
          invite_ttl: 86400,
        });
        if (invRes?.token) {
          const inviteUrl = `${window.location.origin}/invite/${invRes.token}`;
          state.issuedTokens[partId] = inviteUrl;
          navigator.clipboard.writeText(inviteUrl).catch(() => {});
          showAlert(`Invite link created & copied for ${partId}!`, 'success');
          await fetchSnapshot(true);
        }
      } catch (err) {
        handleApiError(err);
      }
    });
  });

  // 4. Copy Active Invite Link
  document.querySelectorAll('.copy-invite-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const partId = btn.getAttribute('data-part');
      const cachedUrl = state.issuedTokens[partId];
      if (cachedUrl) {
        navigator.clipboard.writeText(cachedUrl).then(() => {
          showAlert(`Invite link copied to clipboard for ${partId}!`, 'success');
        }).catch(() => {
          showAlert(`Link: ${cachedUrl}`, 'info');
        });
      } else {
        showAlert(`Invite is already active for ${partId}. Raw tokens are not stored across page reloads. If the link was lost, revoke it and create a new one.`, 'info');
      }
    });
  });

  // 4b. Allocation Target Selector (Organizer)
  const targetSelect = document.getElementById('allocation-target-select');
  if (targetSelect) {
    targetSelect.addEventListener('change', (e) => {
      state.allocationTargetId = e.target.value;
      updateMealUI();
    });
  }

  // 5. Claim / Allocation Adjustments (+ / - / Claim All / Assign All)
  document.querySelectorAll('.claim-inc-btn, .claim-dec-btn, .claim-all-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const itemId = btn.getAttribute('data-id');
      const currentVal = parseFloat(btn.getAttribute('data-current') || '0');
      const targetUserId = btn.getAttribute('data-target') || state.currentUserId;
      const rev = parseInt(btn.getAttribute('data-rev'), 10);
      let targetVal = currentVal;

      if (btn.classList.contains('claim-inc-btn')) {
        targetVal = currentVal + 1;
      } else if (btn.classList.contains('claim-dec-btn')) {
        targetVal = Math.max(0, currentVal - 1);
      } else if (btn.classList.contains('claim-all-btn')) {
        const total = parseFloat(btn.getAttribute('data-total') || '1');
        const unassigned = parseFloat(btn.getAttribute('data-unassigned') || '0');
        if (currentVal === total) {
          targetVal = 0;
        } else if (unassigned > 0) {
          targetVal = currentVal + unassigned;
        } else {
          targetVal = total;
        }
      }

      state.mutationActive = true;
      try {
        const commandKind = snap.is_organizer ? 'AssignParticipantQuantity' : 'SetOwnQuantity';
        const payload = {
          kind: commandKind,
          command_id: `${commandKind.toLowerCase()}-${Date.now()}-${itemId}`,
          item_id: itemId,
          quantity: targetVal === 0 ? null : targetVal,
          expected_item_revision: rev,
          expected_financial_revision: snap.financial_revision,
        };
        if (snap.is_organizer) {
          payload.participant_id = targetUserId;
        }

        await apiCall(`/api/meals/${state.mealId}/apply`, 'POST', payload);
        state.mutationActive = false;
        await fetchSnapshot(true);
      } catch (err) {
        state.mutationActive = false;
        handleApiError(err, itemId);
      } finally {
        state.mutationActive = false;
      }
    });
  });

  // 6. Finalize Meal
  const finalizeBtn = document.getElementById('finalize-btn');
  if (finalizeBtn) {
    finalizeBtn.addEventListener('click', async () => {
      if (!confirm('Are you sure you want to finalize the meal? Claims will be locked.')) return;
      state.mutationActive = true;
      try {
        await apiCall(`/api/meals/${state.mealId}/apply`, 'POST', {
          kind: 'Finalize',
          command_id: `fin-${Date.now()}`,
          expected_revision: snap.revision,
          expected_financial_revision: snap.financial_revision,
        });
        state.mutationActive = false;
        await fetchSnapshot(true);
        showAlert('Meal finalized successfully!', 'success');
      } catch (err) {
        state.mutationActive = false;
        handleApiError(err);
      } finally {
        state.mutationActive = false;
      }
    });
  }

  // 7. Notion Export
  const parentInputElem = document.getElementById('notion-parent-id');
  if (parentInputElem) {
    parentInputElem.addEventListener('input', () => {
      const parsed = extractNotionUuid(parentInputElem.value);
      if (parsed && (parentInputElem.value.includes('http') || parentInputElem.value.length === 32)) {
        parentInputElem.value = parsed;
      }
      state.notionParentId = parentInputElem.value;
    });
  }

  const tokenInputElem = document.getElementById('notion-token');
  if (tokenInputElem) {
    tokenInputElem.addEventListener('input', () => {
      state.notionToken = tokenInputElem.value;
    });
  }

  const notionBtn = document.getElementById('notion-export-btn');
  if (notionBtn) {
    notionBtn.addEventListener('click', async () => {
      const parentInput = document.getElementById('notion-parent-id');
      const tokenInput = document.getElementById('notion-token');
      const spinner = document.getElementById('notion-export-spinner');
      const resultDiv = document.getElementById('notion-export-result');

      const rawParent = (parentInput?.value || '').trim();
      const parentId = extractNotionUuid(rawParent);
      const token = (tokenInput?.value || '').trim();

      if (!parentId) {
        showAlert('Please enter a valid Notion Parent Page UUID or paste your Notion page URL.', 'error');
        return;
      }
      if (parentInput) parentInput.value = parentId;

      notionBtn.disabled = true;
      if (spinner) spinner.style.display = 'block';
      if (resultDiv) resultDiv.style.display = 'none';

      try {
        const payload = {
          parent_id: parentId,
          parent_type: 'page_id',
          mode: 'compact',
        };
        if (token) payload.token = token;

        const res = await fetch(`/api/meals/${state.mealId}/export/notion`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-SettleTable-Action': '1',
          },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok || !data.ok) {
          throw { status: res.status, code: data.error, message: data.error };
        }

        const exp = data.export || {};
        if (exp.status === 'in_progress') {
          if (resultDiv) {
            resultDiv.style.display = 'block';
            resultDiv.style.backgroundColor = 'rgba(99, 102, 241, 0.1)';
            resultDiv.style.border = '1px solid rgba(99, 102, 241, 0.3)';
            resultDiv.style.color = 'var(--accent-indigo)';
            resultDiv.innerHTML = '<strong>⏳ Archiving to Notion...</strong><br/><span style="font-size:0.8rem;">Export running asynchronously in background. Live dining updates continue uninterrupted.</span>';
          }
          let pollAttempts = 0;
          const pollInterval = setInterval(async () => {
            pollAttempts++;
            try {
              const pollRes = await fetch(`/api/meals/${state.mealId}/export/notion`);
              const pollData = await pollRes.json();
              if (pollData.ok && pollData.export && (pollData.export.status === 'completed' || pollData.export.status === 'already_exported')) {
                clearInterval(pollInterval);
                const pollExp = pollData.export;
                state.notionExport = pollExp;
                if (resultDiv) {
                  resultDiv.style.display = 'block';
                  resultDiv.style.backgroundColor = 'rgba(16, 185, 129, 0.1)';
                  resultDiv.style.border = '1px solid rgba(16, 185, 129, 0.3)';
                  resultDiv.style.color = '#6ee7b7';
                  resultDiv.innerHTML = `
                    <strong>✓ Export Successful!</strong><br/>
                    Page ID: <code style="font-size: 0.8rem;">${escapeHtml(pollExp.page_id || '')}</code><br/>
                    <a href="${escapeHtml(pollExp.page_url || '#')}" target="_blank" rel="noopener noreferrer" style="color: #6ee7b7; font-weight: bold; text-decoration: underline; display: inline-block; margin-top: 0.5rem;" id="notion-page-link">
                      Open Report in Notion ↗
                    </a>
                  `;
                }
                showAlert('Report exported to Notion successfully!', 'success');
                notionBtn.disabled = false;
                if (spinner) spinner.style.display = 'none';
              } else if (pollData.ok && pollData.export && pollData.export.status === 'failed') {
                clearInterval(pollInterval);
                state.notionExport = pollData.export;
                notionBtn.disabled = false;
                if (spinner) spinner.style.display = 'none';
                const errDetail = pollData.export.export_digest || 'notion_error';
                if (resultDiv) {
                  resultDiv.style.display = 'block';
                  resultDiv.style.backgroundColor = 'rgba(239, 68, 68, 0.1)';
                  resultDiv.style.border = '1px solid rgba(239, 68, 68, 0.3)';
                  resultDiv.style.color = 'var(--accent-rose)';
                  resultDiv.textContent = `Export failed: ${errDetail}`;
                }
                showAlert(`Notion export failed: ${errDetail}`, 'error');
              } else if (pollAttempts >= 30) {
                clearInterval(pollInterval);
                notionBtn.disabled = false;
                if (spinner) spinner.style.display = 'none';
                showAlert('Notion export is taking longer than expected. Please check back later.', 'conflict');
              }
            } catch (pollErr) {
              clearInterval(pollInterval);
              notionBtn.disabled = false;
              if (spinner) spinner.style.display = 'none';
              showAlert('Failed to poll Notion export status.', 'error');
            }
          }, 1000);
          return;
        }

        if (resultDiv) {
          resultDiv.style.display = 'block';
          resultDiv.style.backgroundColor = 'rgba(16, 185, 129, 0.1)';
          resultDiv.style.border = '1px solid rgba(16, 185, 129, 0.3)';
          resultDiv.style.color = '#6ee7b7';
          resultDiv.innerHTML = `
            <strong>✓ Export Successful!</strong><br/>
            Page ID: <code style="font-size: 0.8rem;">${escapeHtml(exp.page_id || '')}</code><br/>
            <a href="${escapeHtml(exp.page_url || '#')}" target="_blank" rel="noopener noreferrer" style="color: #6ee7b7; font-weight: bold; text-decoration: underline; display: inline-block; margin-top: 0.5rem;" id="notion-page-link">
              Open Report in Notion ↗
            </a>
          `;
        }
        showAlert('Report exported to Notion successfully!', 'success');
      } catch (err) {
        if (resultDiv) {
          resultDiv.style.display = 'block';
          resultDiv.style.backgroundColor = 'rgba(239, 68, 68, 0.1)';
          resultDiv.style.border = '1px solid rgba(239, 68, 68, 0.3)';
          resultDiv.style.color = 'var(--accent-rose)';
          resultDiv.textContent = `Export failed: ${err.code || err.message || 'unknown error'}`;
        }
        showAlert(`Notion export rejected: ${err.code || err.message}`, 'error');
      } finally {
        notionBtn.disabled = false;
        if (spinner) spinner.style.display = 'none';
      }
    });
  }
}

// --- Error & Conflict Handling ---
function handleApiError(err, itemId = null) {
  state.mutationActive = false;
  if (err.status === 409 || err.code === 'item_revision_conflict' || err.code === 'financial_revision_conflict' || err.code === 'revision_conflict') {
    showAlert('⚠️ Stale Claim Conflict: Another diner updated quantities. Refreshing latest data...', 'conflict');
    if (itemId) {
      const card = document.getElementById(`item-card-${itemId}`);
      if (card) card.classList.add('contested');
    }
    fetchSnapshot(true);
  } else if (err.status === 401) {
    showAlert('Session expired or unauthorized. Please re-open from invitation.', 'error');
  } else {
    showAlert(`Action rejected: ${err.code || err.message}`, 'error');
  }
}
