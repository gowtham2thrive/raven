/**
 * RAVEN API Client.
 *
 * Fetch wrapper for backend API calls.
 * Base URL configurable via environment.
 */

const API_BASE = 'http://localhost:8000';

export function notifyDataChanged() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('raven:data-updated'));
  }
}

async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const config = {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  };

  const response = await fetch(url, config);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `API error: ${response.status}`);
  }

  const data = await response.json();

  // Broadcast change event for any mutation so the entire app updates dynamically
  if (options.method && options.method !== 'GET') {
    notifyDataChanged();
  }

  return data;
}

// ── Cases ──────────────────────────────────────────────────

export function fetchCases(params = {}) {
  const query = new URLSearchParams(params).toString();
  return request(`/cases/${query ? `?${query}` : ''}`);
}

export function fetchCase(caseId) {
  return request(`/cases/${caseId}`);
}

export function investigateCase(caseId, model = null) {
  const query = model ? `?model=${encodeURIComponent(model)}` : '';
  return request(`/cases/${caseId}/investigate${query}`, { method: 'POST' });
}

export function batchInvestigateCases() {
  return request('/cases/batch-investigate', { method: 'POST' });
}

export function batchSubmitCases() {
  return request('/cases/batch-submit', { method: 'POST' });
}

export function fetchEvidence(caseId) {
  return request(`/cases/${caseId}/evidence`);
}

export function fetchTimeline(caseId) {
  return request(`/cases/${caseId}/timeline`);
}

export function fetchAssessment(caseId) {
  return request(`/cases/${caseId}/assessment`);
}

export function fetchResponse(caseId) {
  return request(`/cases/${caseId}/response`);
}

export function fetchAudit(caseId) {
  return request(`/cases/${caseId}/audit`);
}

// ── Models & Pricing Catalog ───────────────────────────────

export function fetchModels() {
  return request('/models');
}

// ── Review ─────────────────────────────────────────────────

export function reviewCase(caseId, decision, notes = '', reviewedBy = 'analyst@raven.dev') {
  return request(`/cases/${caseId}/review`, {
    method: 'POST',
    body: JSON.stringify({ decision, notes, reviewed_by: reviewedBy }),
  });
}

export function submitCase(caseId) {
  return request(`/cases/${caseId}/submit`, {
    method: 'POST',
    body: JSON.stringify({ confirmed: true }),
  });
}

// ── Metrics ────────────────────────────────────────────────

export function fetchMetrics() {
  return request('/metrics/summary');
}

// ── Simulator ──────────────────────────────────────────────

export function fetchSimulatorPresets() {
  return request('/simulator/presets');
}

export function generateSimulatedCase(params = {}) {
  return request('/simulator/generate', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export function clearAllCases() {
  return request('/cases', {
    method: 'DELETE',
  });
}

// ── Webhooks (for testing) ─────────────────────────────────

export function sendTestWebhook(disputeId = 'disp_test001', amount = 849900) {
  return request('/webhooks/razorpay', {
    method: 'POST',
    body: JSON.stringify({
      event: 'payment.dispute.created',
      payload: {
        dispute: {
          entity: {
            id: disputeId,
            payment_id: `pay_${disputeId.replace('disp_', '')}`,
            amount,
            currency: 'INR',
            reason_code: 'chargeback',
            reason_description: 'Product not received',
            phase: 'chargeback',
            status: 'open',
            respond_by_date: Math.floor(Date.now() / 1000) + 86400 * 7,
            created_at: Math.floor(Date.now() / 1000),
          },
        },
      },
    }),
  });
}

// ── Live Investigation Stream ─────────────────────────────

/**
 * Connect to SSE endpoint for live investigation streaming.
 *
 * @param {string} caseId - Case to investigate
 * @param {function} onEvent - Callback receiving { type, data } events
 * @param {string} [model] - Optional model identifier
 * @returns {EventSource} - The EventSource (call .close() to stop)
 */
export function streamInvestigation(caseId, onEvent, model = null) {
  const query = model ? `?model=${encodeURIComponent(model)}` : '';
  const url = `${API_BASE}/cases/${caseId}/investigate/stream${query}`;
  const eventSource = new EventSource(url);

  const eventTypes = ['step', 'evidence', 'thinking', 'contradiction', 'result', 'error', 'done'];

  eventTypes.forEach(type => {
    eventSource.addEventListener(type, (e) => {
      try {
        const data = JSON.parse(e.data);
        onEvent({ type, data });
      } catch {
        onEvent({ type, data: { message: e.data } });
      }

      if (type === 'done') {
        notifyDataChanged();
        eventSource.close();
      }
    });
  });

  eventSource.onerror = () => {
    onEvent({ type: 'error', data: { message: 'Connection lost' } });
    eventSource.close();
  };

  return eventSource;
}

// ── Settings ───────────────────────────────────────────────

export function fetchCredentialStatus() {
  return request('/settings/credentials/status');
}

export function validateCredentials() {
  return request('/settings/credentials/validate', { method: 'POST' });
}

export function fetchGuardrails() {
  return request('/settings/guardrails');
}

export function updateGuardrails(guardrails) {
  return request('/settings/guardrails', {
    method: 'PUT',
    body: JSON.stringify(guardrails),
  });
}
