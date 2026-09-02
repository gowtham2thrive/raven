/**
 * Integration API Client — All fetch calls for the Integrations Hub.
 */

const API_BASE = `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/integrations`;

/**
 * List all integrations with optional filters.
 */
export async function fetchIntegrations({ status, evidenceCategory, integrationType } = {}) {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  if (evidenceCategory) params.set('evidence_category', evidenceCategory);
  if (integrationType) params.set('integration_type', integrationType);

  const url = params.toString() ? `${API_BASE}?${params}` : API_BASE;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch integrations: ${res.status}`);
  return res.json();
}

/**
 * Get full detail for a single integration.
 */
export async function fetchIntegration(id) {
  const res = await fetch(`${API_BASE}/${id}`);
  if (!res.ok) throw new Error(`Integration not found: ${res.status}`);
  return res.json();
}

/**
 * Create a new integration.
 */
export async function createIntegration(data) {
  const res = await fetch(API_BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Create failed: ${res.status}`);
  }
  return res.json();
}

/**
 * Update an integration.
 */
export async function updateIntegration(id, data) {
  const res = await fetch(`${API_BASE}/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Update failed: ${res.status}`);
  }
  return res.json();
}

/**
 * Delete an integration.
 */
export async function deleteIntegration(id) {
  const res = await fetch(`${API_BASE}/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Delete failed: ${res.status}`);
  return res.json();
}

/**
 * Test integration connectivity.
 */
export async function testIntegration(id) {
  const res = await fetch(`${API_BASE}/${id}/test`, { method: 'POST' });
  if (!res.ok) throw new Error(`Test failed: ${res.status}`);
  return res.json();
}

/**
 * Get sample data with field mappings applied.
 */
export async function fetchSampleData(id) {
  const res = await fetch(`${API_BASE}/${id}/sample`);
  if (!res.ok) throw new Error(`Sample fetch failed: ${res.status}`);
  return res.json();
}

/**
 * Save field mappings for an integration.
 */
export async function saveFieldMappings(id, mappings) {
  const res = await fetch(`${API_BASE}/${id}/mappings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(mappings),
  });
  if (!res.ok) throw new Error(`Save mappings failed: ${res.status}`);
  return res.json();
}

/**
 * Activate an integration.
 */
export async function activateIntegration(id) {
  const res = await fetch(`${API_BASE}/${id}/activate`, { method: 'POST' });
  if (!res.ok) throw new Error(`Activate failed: ${res.status}`);
  return res.json();
}

/**
 * Deactivate an integration.
 */
export async function deactivateIntegration(id) {
  const res = await fetch(`${API_BASE}/${id}/deactivate`, { method: 'POST' });
  if (!res.ok) throw new Error(`Deactivate failed: ${res.status}`);
  return res.json();
}

/**
 * Upload a file (CSV, Excel, PDF).
 */
export async function uploadFile(file, integrationType) {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${API_BASE}/upload?integration_type=${integrationType}`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Upload failed: ${res.status}`);
  }
  return res.json();
}

/**
 * Fetch available integration types.
 */
export async function fetchIntegrationTypes() {
  const res = await fetch(`${API_BASE}/types/available`);
  if (!res.ok) throw new Error(`Types fetch failed: ${res.status}`);
  return res.json();
}

/**
 * Fetch evidence categories.
 */
export async function fetchEvidenceCategories() {
  const res = await fetch(`${API_BASE}/categories/available`);
  if (!res.ok) throw new Error(`Categories fetch failed: ${res.status}`);
  return res.json();
}

/**
 * Sync / manually trigger data fetch.
 */
export async function syncIntegration(id) {
  const res = await fetch(`${API_BASE}/${id}/sync`, { method: 'POST' });
  if (!res.ok) throw new Error(`Sync failed: ${res.status}`);
  return res.json();
}
