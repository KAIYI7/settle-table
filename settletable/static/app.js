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
};

function formatSen(sen) {
  if (sen === null || sen === undefined) return 'RM 0.00';
  const val = Number(sen) / 100;
  return `RM ${val.toFixed(2)}`;
}

function parseSen(input) {
  if (typeof input !== 'string') {
    throw new Error('Price must be a string');
  }
  let s = input.trim();
  if (s.toUpperCase().startsWith('RM')) {
    s = s.slice(2).trim();
  }
  if (!s || !/^[0-9]+(?:\.[0-9]{1,2})?$/.test(s)) {
    throw new Error(`Invalid price '${input}'. Enter an amount like 12.50 or RM 12.50`);
  }
  const parts = s.split('.');
  const whole = parseInt(parts[0], 10);
  const fracStr = (parts[1] || '').padEnd(2, '0');
  const frac = parseInt(fracStr, 10);
  const totalSen = whole * 100 + frac;
  if (totalSen < 0 || totalSen > 1_000_000_000) {
    throw new Error('Price out of bounds: maximum RM 10,000,000.00');
  }
  return totalSen;
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
      state.snapshot = snap;
      state.currentUserId = snap.current_participant_id;
      state.isOrganizer = snap.is_organizer;
      updateMealUI();
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
function renderWelcome() {
  stopPolling();
  state.mealId = null;
  state.snapshot = null;
  document.getElementById('header-user-status').innerHTML = '';

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
  `;

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
        
        <div style="background: var(--bg-main); padding: 14px; border-radius: var(--radius-md); margin-bottom: 20px;">
          <div style="font-size: 0.85rem; color: var(--text-muted);">Joining as:</div>
          <div style="font-size: 1.25rem; font-weight: 700; color: #a7f3d0;">${escapeHtml(inspection.participant_name)}</div>
        </div>

        <button id="redeem-btn" class="btn btn-success btn-block" style="font-size: 1.05rem;">
          Accept & Join Meal
        </button>
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
        </div>
      `;
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
  const snap = state.snapshot;
  if (!snap) return;

  // Header Status
  const user = snap.participants?.find(p => p.id === state.currentUserId);
  const userName = user ? user.name : 'Unknown';
  const roleBadge = state.isOrganizer 
    ? '<span class="badge badge-organizer">👑 Organizer</span>' 
    : '<span class="badge badge-diner">🍽️ Diner</span>';
  
  document.getElementById('header-user-status').innerHTML = `
    ${roleBadge}
    <span style="font-weight: 600;">${escapeHtml(userName)}</span>
    <button id="manual-refresh-btn" class="btn btn-secondary btn-sm" title="Refresh Snapshot">⟳</button>
  `;
  document.getElementById('manual-refresh-btn')?.addEventListener('click', () => fetchSnapshot(true));

  const app = document.getElementById('app');
  let html = '';

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
          <span style="font-size: 0.75rem; color: #a7f3d0; font-weight: 600;">Self-Hosted / Local</span>
        </div>
        <p style="font-size: 0.8rem; color: var(--text-dim); margin-bottom: 10px;">
          Upload a receipt photo (JPEG/PNG/WebP) to automatically extract items, taxes, and service charges. Requires physical verification before sealing.
        </p>
        <input type="file" id="ocr-file-input" accept="image/jpeg,image/png,image/webp" style="display: none;">
        <button type="button" id="ocr-upload-btn" class="btn btn-secondary btn-sm btn-block">📷 Scan Receipt Image</button>
        <div id="ocr-spinner" style="display: none; text-align: center; margin-top: 8px; font-size: 0.85rem; color: var(--accent-indigo);">
          Analyzing receipt locally on device...
        </div>
      </div>

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
        <h3 class="card-title">Item Claims</h3>
        <p class="card-desc">No receipt items to claim. The organizer must add items first.</p>
      </div>
    `;
  }

  const itemsHtml = items.map(item => {
    const stateItem = snap.items?.find(i => i.item_id === item.id);
    const itemRevision = stateItem ? stateItem.item_revision : 0;
    const claims = snap.claims?.filter(c => c.item_id === item.id) || [];
    
    // User's own claim
    const ownClaim = claims.find(c => c.participant_id === state.currentUserId);
    const ownQty = ownClaim ? (Array.isArray(ownClaim.quantity) ? ownClaim.quantity[0]/ownClaim.quantity[1] : ownClaim.quantity) : 0;

    // Total claimed
    const totalClaimed = claims.reduce((acc, c) => acc + (Array.isArray(c.quantity) ? c.quantity[0]/c.quantity[1] : c.quantity), 0);
    const itemTotalQty = Array.isArray(item.quantity) ? item.quantity[0]/item.quantity[1] : item.quantity;
    const pct = Math.min(100, Math.round((totalClaimed / itemTotalQty) * 100));

    // Chips for other diners
    const chipsHtml = claims.map(c => {
      const p = snap.participants?.find(part => part.id === c.participant_id);
      const name = p ? p.name : c.participant_id;
      const isMe = c.participant_id === state.currentUserId;
      const qStr = Array.isArray(c.quantity) ? `${c.quantity[0]}/${c.quantity[1]}` : c.quantity;
      return `<span class="chip ${isMe ? 'own-chip' : ''}">${escapeHtml(name)}: ${qStr}</span>`;
    }).join('');

    return `
      <div class="item-card" id="item-card-${item.id}" data-item-id="${item.id}" data-revision="${itemRevision}">
        <div class="item-header">
          <div>
            <div class="item-label">${escapeHtml(item.label)}</div>
            <div class="item-meta">Total: ${itemTotalQty} &bull; Claimed: ${totalClaimed} / ${itemTotalQty}</div>
          </div>
          <div class="item-price">${formatSen(item.line_sen)}</div>
        </div>

        <div class="progress-bar-wrap">
          <div class="progress-bar-fill ${totalClaimed > itemTotalQty ? 'overclaimed' : ''}" style="width: ${pct}%"></div>
        </div>

        <div class="claim-actions">
          <div class="quantity-stepper">
            <button class="btn btn-secondary btn-sm claim-dec-btn" data-id="${item.id}" data-current="${ownQty}" data-rev="${itemRevision}">-</button>
            <span class="step-val">${ownQty}</span>
            <button class="btn btn-secondary btn-sm claim-inc-btn" data-id="${item.id}" data-current="${ownQty}" data-rev="${itemRevision}">+</button>
          </div>
          <div>
            <button class="btn btn-secondary btn-sm claim-all-btn" data-id="${item.id}" data-rev="${itemRevision}" data-total="${itemTotalQty}">Claim All</button>
          </div>
        </div>

        ${chipsHtml ? `<div class="chips-row">${chipsHtml}</div>` : ''}
      </div>
    `;
  }).join('');

  return `
    <div class="card">
      <h3 class="card-title">Claim Your Portions</h3>
      <p class="card-desc">Tap + or - to set your claimed portion for each item. Overlapping claims split the cost.</p>
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
    </div>
  `;
}

// --- Event Binding ---
function bindEvents(snap) {
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

      try {
        const res = await fetch(`/api/meals/${state.mealId}/ocr/extract`, {
          method: 'POST',
          headers: {
            'Content-Type': file.type || 'image/jpeg',
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

        // Apply extracted candidate items to draft receipt
        state.mutationActive = true;
        await apiCall(`/api/meals/${state.mealId}/apply`, 'POST', {
          kind: 'ReplaceReceipt',
          command_id: `ocr-rcpt-${Date.now()}`,
          expected_revision: snap.revision,
          expected_financial_revision: snap.financial_revision,
          receipt: {
            items: candidate.items,
            subtotal_sen: candidate.subtotal_sen,
            total_sen: candidate.total_sen,
            adjustments: candidate.adjustments || [],
            included_tax_sen: candidate.included_tax_sen || 0,
          }
        });
        state.mutationActive = false;
        await fetchSnapshot(true);

        if (candidate.route === 'manual_correction' || (candidate.issues && candidate.issues.length > 0)) {
          showAlert(`Extracted ${candidate.items.length} items (${formatSen(candidate.total_sen)}). Please verify items and adjustments.`, 'conflict');
        } else {
          showAlert(`Extracted ${candidate.items.length} items from receipt (${formatSen(candidate.total_sen)}) ✓`, 'success');
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

  // 5. Claim Adjustments (+ / - / Claim All)
  document.querySelectorAll('.claim-inc-btn, .claim-dec-btn, .claim-all-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const itemId = btn.getAttribute('data-id');
      const currentVal = parseFloat(btn.getAttribute('data-current') || '0');
      const rev = parseInt(btn.getAttribute('data-rev'), 10);
      let targetVal = currentVal;

      if (btn.classList.contains('claim-inc-btn')) {
        targetVal = currentVal + 1;
      } else if (btn.classList.contains('claim-dec-btn')) {
        targetVal = Math.max(0, currentVal - 1);
      } else if (btn.classList.contains('claim-all-btn')) {
        const total = parseFloat(btn.getAttribute('data-total') || '1');
        targetVal = (currentVal === total) ? 0 : total;
      }

      state.mutationActive = true;
      try {
        await apiCall(`/api/meals/${state.mealId}/apply`, 'POST', {
          kind: 'SetOwnQuantity',
          command_id: `claim-${Date.now()}-${itemId}`,
          item_id: itemId,
          quantity: targetVal === 0 ? null : targetVal,
          expected_item_revision: rev,
          expected_financial_revision: snap.financial_revision,
        });
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
