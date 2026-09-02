import { useState, useEffect } from 'react';
import { 
  IconX, 
  IconZap, 
  IconRefreshCw, 
  IconCheckCircle, 
  IconAlertTriangle,
  IconCopy,
  IconDatabase,
  IconWebhook,
  IconFileText,
  IconLayers
} from '../Icons';
import { testIntegration, fetchIntegration } from '../../api/integrations';

const TYPE_ICONS = {
  rest_api: <IconZap size={16} />,
  database: <IconDatabase size={16} />,
  csv_file: <IconFileText size={16} />,
  excel_file: <IconFileText size={16} />,
  pdf_file: <IconFileText size={16} />,
  webhook: <IconWebhook size={16} />,
};

export function IntegrationDrawer({ integrationId, onClose, onRefreshList }) {
  const [integration, setIntegration] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview'); // overview | mappings | test
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!integrationId) return;
    setLoading(true);
    fetchIntegration(integrationId)
      .then(setIntegration)
      .catch((err) => console.error('Failed to fetch integration detail:', err))
      .finally(() => setLoading(false));
  }, [integrationId]);

  if (!integrationId) return null;

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await testIntegration(integrationId);
      setTestResult(result);
      if (onRefreshList) onRefreshList();
    } catch (err) {
      setTestResult({ success: false, error: err.message });
    } finally {
      setTesting(false);
    }
  };

  const handleCopy = (text) => {
    navigator.clipboard.writeText(typeof text === 'object' ? JSON.stringify(text, null, 2) : text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const config = integration?.config || {};
  const mappings = integration?.field_mappings || [];

  return (
    <div className="integration-drawer-overlay" onClick={onClose}>
      <div className="integration-drawer" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="integration-drawer-header">
          <div className="integration-drawer-header-info">
            <div className="integration-drawer-icon">
              {TYPE_ICONS[integration?.integration_type] || <IconLayers size={18} />}
            </div>
            <div>
              <h2>{integration?.name || 'Integration Details'}</h2>
              <div className="integration-drawer-subtitle">
                <span>{integration?.integration_type?.toUpperCase()}</span>
                <span>•</span>
                <span>Category: {integration?.evidence_category}</span>
              </div>
            </div>
          </div>
          <button className="drawer-close-btn" onClick={onClose} aria-label="Close">
            <IconX size={18} />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="integration-drawer-tabs">
          <button 
            className={`drawer-tab ${activeTab === 'overview' ? 'active' : ''}`}
            onClick={() => setActiveTab('overview')}
          >
            Overview & Config
          </button>
          <button 
            className={`drawer-tab ${activeTab === 'mappings' ? 'active' : ''}`}
            onClick={() => setActiveTab('mappings')}
          >
            Field Mappings ({mappings.length})
          </button>
          <button 
            className={`drawer-tab ${activeTab === 'test' ? 'active' : ''}`}
            onClick={() => setActiveTab('test')}
          >
            Live Test & Diagnostic
          </button>
        </div>

        {/* Body */}
        <div className="integration-drawer-body">
          {loading ? (
            <div className="drawer-loading">
              <IconRefreshCw className="spin" size={24} />
              <p>Loading integration specifications...</p>
            </div>
          ) : (
            <>
              {activeTab === 'overview' && (
                <div className="drawer-section">
                  <div className="drawer-card">
                    <h3>Source Information</h3>
                    <p className="drawer-desc">{integration?.description || 'No description provided.'}</p>
                    
                    <div className="drawer-kv-grid">
                      <div className="drawer-kv">
                        <span className="kv-label">Status</span>
                        <span className={`status-badge-inline ${integration?.status}`}>
                          ● {integration?.status?.toUpperCase()}
                        </span>
                      </div>
                      <div className="drawer-kv">
                        <span className="kv-label">Target Evidence</span>
                        <span className="kv-val category-tag">{integration?.evidence_category}</span>
                      </div>
                      <div className="drawer-kv">
                        <span className="kv-label">Total Syncs</span>
                        <span className="kv-val">{integration?.sync_count || 0} runs</span>
                      </div>
                      <div className="drawer-kv">
                        <span className="kv-label">Created At</span>
                        <span className="kv-val">{new Date(integration?.created_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                  </div>

                  <div className="drawer-card">
                    <div className="card-header-flex">
                      <h3>Connection Configuration</h3>
                      <button className="btn-copy-code" onClick={() => handleCopy(config)}>
                        <IconCopy size={13} />
                        <span>{copied ? 'Copied!' : 'Copy Config'}</span>
                      </button>
                    </div>

                    <div className="config-code-preview">
                      <pre>{JSON.stringify(config, null, 2)}</pre>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'mappings' && (
                <div className="drawer-section">
                  <div className="drawer-card">
                    <h3>Canonical Evidence Field Mappings</h3>
                    <p className="drawer-desc">
                      Normalizes external payloads into RAVEN's dispute investigation schema.
                    </p>

                    {mappings.length === 0 ? (
                      <div className="drawer-empty-state">
                        <p>No specific field mappings defined. Raw payload passes through canonical extractor.</p>
                      </div>
                    ) : (
                      <table className="drawer-mappings-table">
                        <thead>
                          <tr>
                            <th>Source Field (External)</th>
                            <th></th>
                            <th>Canonical Target (RAVEN)</th>
                            <th>Transform</th>
                          </tr>
                        </thead>
                        <tbody>
                          {mappings.map((m, idx) => (
                            <tr key={idx}>
                              <td><code>{m.source_field}</code></td>
                              <td className="mapping-arrow">→</td>
                              <td><span className="target-field-tag">{m.target_field}</span></td>
                              <td><span className="transform-tag">{m.transform || 'pass-through'}</span></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                </div>
              )}

              {activeTab === 'test' && (
                <div className="drawer-section">
                  <div className="drawer-card">
                    <div className="card-header-flex">
                      <div>
                        <h3>Live Connection Diagnostic</h3>
                        <p className="drawer-desc">Executes sample ping to verify authentication, latency, and schema matching.</p>
                      </div>
                      <button 
                        className="btn-primary-sm" 
                        onClick={handleTest} 
                        disabled={testing}
                      >
                        {testing ? <IconRefreshCw className="spin" size={14} /> : <IconZap size={14} />}
                        <span>{testing ? 'Testing...' : 'Run Test Now'}</span>
                      </button>
                    </div>

                    {testResult && (
                      <div className={`test-output-banner ${testResult.success ? 'success' : 'error'}`}>
                        <div className="test-output-header">
                          {testResult.success ? (
                            <>
                              <IconCheckCircle size={18} className="icon-success" />
                              <span className="test-title">Connection Successful</span>
                            </>
                          ) : (
                            <>
                              <IconAlertTriangle size={18} className="icon-error" />
                              <span className="test-title">Diagnostic Failed</span>
                            </>
                          )}
                          <span className="test-latency">
                            {testResult.latency_ms ? `${testResult.latency_ms}ms` : ''}
                          </span>
                        </div>

                        {(testResult.error || testResult.message) && !testResult.success && (
                          <div className="test-error-msg">{testResult.error || testResult.message}</div>
                        )}

                        {testResult.sample_data && (
                          <div className="test-sample-box">
                            <div className="sample-label">Sample Extracted Payload:</div>
                            <pre>{JSON.stringify(testResult.sample_data, null, 2)}</pre>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="integration-drawer-footer">
          <button className="btn-secondary" onClick={onClose}>Close</button>
          <button className="btn-primary" onClick={handleTest} disabled={testing}>
            <IconZap size={14} />
            <span>Test Connection</span>
          </button>
        </div>
      </div>
    </div>
  );
}
