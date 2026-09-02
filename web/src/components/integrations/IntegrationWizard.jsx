import { useState } from 'react';
import { 
  createIntegration, 
  updateIntegration, 
  testIntegration, 
  uploadFile, 
  activateIntegration, 
  saveFieldMappings 
} from '../../api/integrations';
import { FieldMappingEditor } from './FieldMappingEditor';
import { FileUploader } from './FileUploader';
import { 
  IconZap, 
  IconDatabase, 
  IconFileText, 
  IconTable, 
  IconWebhook 
} from '../Icons';

const STEPS = [
  { id: 'type', label: 'Source Type' },
  { id: 'config', label: 'Configure' },
  { id: 'test', label: 'Test' },
  { id: 'mapping', label: 'Map Fields' },
  { id: 'activate', label: 'Activate' },
];

const INTEGRATION_TYPES = [
  {
    id: 'rest_api', 
    name: 'REST API', 
    icon: <IconZap size={22} />,
    iconClass: 'rest_api',
    desc: 'Connect to any REST API endpoint',
  },
  {
    id: 'database', 
    name: 'Database', 
    icon: <IconDatabase size={22} />,
    iconClass: 'database',
    desc: 'Query PostgreSQL, MySQL, or SQLite',
  },
  {
    id: 'csv_file', 
    name: 'CSV File', 
    icon: <IconFileText size={22} />,
    iconClass: 'csv_file',
    desc: 'Upload CSV or TSV data files',
  },
  {
    id: 'excel_file', 
    name: 'Excel', 
    icon: <IconTable size={22} />,
    iconClass: 'excel_file',
    desc: 'Upload .xlsx spreadsheets',
  },
  {
    id: 'pdf_file', 
    name: 'PDF', 
    icon: <IconFileText size={22} />,
    iconClass: 'pdf_file',
    desc: 'Extract text & tables from PDFs',
  },
  {
    id: 'webhook', 
    name: 'Webhook', 
    icon: <IconWebhook size={22} />,
    iconClass: 'webhook',
    desc: 'Receive data via inbound webhooks',
  },
];


const EVIDENCE_CATEGORIES = [
  { id: 'payment', name: 'Payment' },
  { id: 'order', name: 'Order' },
  { id: 'shipping', name: 'Shipping' },
  { id: 'delivery', name: 'Delivery' },
  { id: 'authentication', name: 'Authentication' },
  { id: 'communication', name: 'Communication' },
  { id: 'refund', name: 'Refund' },
  { id: 'service', name: 'Service' },
  { id: 'policy', name: 'Policy' },
  { id: 'device', name: 'Device' },
  { id: 'other', name: 'Other' },
];

const FILE_TYPES = new Set(['csv_file', 'excel_file', 'pdf_file']);

export function IntegrationWizard({ onClose, onComplete }) {
  const [step, setStep] = useState(0);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    integration_type: '',
    evidence_category: 'shipping',
    // REST API
    url: '',
    method: 'GET',
    auth_method: 'none',
    auth_header: 'X-Api-Key',
    auth_value: '',
    response_path: '$',
    timeout_seconds: 30,
    // Database
    dialect: 'postgresql',
    host: 'localhost',
    port: '',
    database: '',
    db_username: '',
    db_password: '',
    query: '',
    // File
    file: null,
    fileMetadata: null,
    delimiter: ',',
    encoding: 'utf-8',
    has_header: true,
    sheet_name: '',
    // Webhook
    webhook_secret: '',
    signature_header: 'X-Webhook-Signature',
  });
  const [testResult, setTestResult] = useState(null);
  const [testLoading, setTestLoading] = useState(false);
  const [fieldMappings, setFieldMappings] = useState([]);
  const [discoveredFields, setDiscoveredFields] = useState([]);
  const [createdId, setCreatedId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const currentStep = STEPS[step];
  const isFileType = FILE_TYPES.has(formData.integration_type);

  const updateField = (key, value) => {
    setFormData(prev => ({ ...prev, [key]: value }));
  };

  // ── Step Navigation ────────────────────────────────────────

  const canProceed = () => {
    switch (currentStep.id) {
      case 'type':
        return !!formData.integration_type;
      case 'config':
        if (!formData.name.trim()) return false;
        if (formData.integration_type === 'rest_api' && !formData.url.trim()) return false;
        if (formData.integration_type === 'database' && !formData.query.trim()) return false;
        if (isFileType && !formData.fileMetadata) return false;
        return true;
      case 'test':
        return testResult?.success;
      case 'mapping':
        return true; // Mappings are optional
      case 'activate':
        return true;
      default:
        return false;
    }
  };

  const handleNext = async () => {
    if (step === 1) {
      // After config, create the integration
      try {
        await handleCreate();
      } catch {
        // Error already set in handleCreate — don't advance
        return;
      }
    }
    if (step < STEPS.length - 1) {
      setStep(step + 1);
    }
  };

  const handleBack = () => {
    if (step > 0) {
      setStep(step - 1);
      setError(null);
    }
  };

  // ── Create or Update Integration ───────────────────────────

  const handleCreate = async () => {
    setSaving(true);
    setError(null);
    try {
      const body = buildCreatePayload();
      if (createdId) {
        await updateIntegration(createdId, body);
      } else {
        const result = await createIntegration(body);
        setCreatedId(result.id);
      }
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setSaving(false);
    }
  };

  const buildCreatePayload = () => {
    const payload = {
      name: formData.name.trim(),
      description: formData.description.trim(),
      integration_type: formData.integration_type,
      evidence_category: formData.evidence_category,
    };

    switch (formData.integration_type) {
      case 'rest_api':
        payload.rest_api = {
          url: formData.url.trim(),
          method: formData.method,
          auth_method: formData.auth_method,
          auth_config: buildAuthConfig(),
          response_path: formData.response_path || '$',
          timeout_seconds: parseInt(formData.timeout_seconds) || 30,
        };
        break;

      case 'database':
        payload.database = {
          dialect: formData.dialect,
          host: formData.host,
          port: formData.port ? parseInt(formData.port) : null,
          database: formData.database,
          username: formData.db_username,
          password: formData.db_password,
          query: formData.query,
        };
        break;

      case 'csv_file':
      case 'excel_file':
      case 'pdf_file':
        if (formData.fileMetadata) {
          payload.file_upload = {
            filename: formData.fileMetadata.filename,
            stored_path: formData.fileMetadata.stored_path,
            file_size_bytes: formData.fileMetadata.file_size_bytes,
            delimiter: formData.delimiter,
            encoding: formData.encoding,
            has_header: formData.has_header,
            sheet_name: formData.sheet_name || null,
          };
        }
        break;

      case 'webhook':
        payload.webhook = {
          secret: formData.webhook_secret,
          signature_header: formData.signature_header,
        };
        break;
    }

    return payload;
  };

  const buildAuthConfig = () => {
    switch (formData.auth_method) {
      case 'api_key':
        return { header: formData.auth_header, value: formData.auth_value };
      case 'bearer_token':
        return { token: formData.auth_value };
      case 'basic_auth':
        return { username: formData.auth_header, password: formData.auth_value };
      default:
        return {};
    }
  };

  // ── Test ───────────────────────────────────────────────────

  const handleTest = async () => {
    if (!createdId) return;
    setTestLoading(true);
    setTestResult(null);
    try {
      const result = await testIntegration(createdId);
      setTestResult(result);
      if (result.discovered_fields) {
        setDiscoveredFields(result.discovered_fields);
      }
    } catch (err) {
      setTestResult({ success: false, message: err.message, errors: [err.message] });
    } finally {
      setTestLoading(false);
    }
  };

  // ── File Upload ────────────────────────────────────────────

  const handleFileSelect = async (file) => {
    updateField('file', file);
    try {
      const metadata = await uploadFile(file, formData.integration_type);
      updateField('fileMetadata', metadata);
    } catch (err) {
      setError(`Upload failed: ${err.message}`);
    }
  };

  // ── Activate / Complete ────────────────────────────────────

  const handleActivate = async () => {
    if (!createdId) return;
    setSaving(true);
    try {
      if (fieldMappings.length > 0) {
        await saveFieldMappings(createdId, fieldMappings);
      }
      await activateIntegration(createdId);
      onComplete();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleSkipActivation = async () => {
    if (createdId && fieldMappings.length > 0) {
      try {
        await saveFieldMappings(createdId, fieldMappings);
      } catch (err) {
        console.error('Failed to save mappings on skip:', err);
      }
    }
    onComplete();
  };

  // ── Render Steps ───────────────────────────────────────────

  return (
    <div className="wizard-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="wizard-modal">
        {/* Header */}
        <div className="wizard-header">
          <h2>
            {step === 0 ? 'Add Integration' : formData.name || 'New Integration'}
          </h2>
          <button className="wizard-close" onClick={onClose}>✕</button>
        </div>

        {/* Steps Indicator */}
        <div className="wizard-steps">
          {STEPS.map((s, i) => (
            <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
              <div
                className={`wizard-step-dot ${i === step ? 'active' : ''} ${i < step ? 'completed' : ''}`}
              />
              {i === step && (
                <span className="wizard-step-label active">{s.label}</span>
              )}
            </div>
          ))}
        </div>

        {/* Body */}
        <div className="wizard-body">
          {error && (
            <div className="test-result error" style={{ marginBottom: '1rem' }}>
              <div className="test-result-header">
                <span className="test-result-icon">⚠️</span>
                <span className="test-result-message">{error}</span>
              </div>
            </div>
          )}

          {currentStep.id === 'type' && (
            <StepTypeSelection formData={formData} updateField={updateField} />
          )}
          {currentStep.id === 'config' && (
            <StepConfiguration formData={formData} updateField={updateField} onFileSelect={handleFileSelect} />
          )}
          {currentStep.id === 'test' && (
            <StepTest
              testResult={testResult}
              testLoading={testLoading}
              onTest={handleTest}
            />
          )}
          {currentStep.id === 'mapping' && (
            <StepFieldMapping
              discoveredFields={discoveredFields}
              mappings={fieldMappings}
              onMappingsChange={setFieldMappings}
              evidenceCategory={formData.evidence_category}
            />
          )}
          {currentStep.id === 'activate' && (
            <StepActivate formData={formData} mappingCount={fieldMappings.length} />
          )}
        </div>

        {/* Footer */}
        <div className="wizard-footer">
          <button
            className="btn-wizard"
            onClick={step === 0 ? onClose : handleBack}
          >
            {step === 0 ? 'Cancel' : '← Back'}
          </button>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {currentStep.id === 'activate' && (
              <button className="btn-wizard" onClick={handleSkipActivation}>
                Save as Inactive
              </button>
            )}
            <button
              className="btn-wizard primary"
              disabled={!canProceed() || saving}
              onClick={currentStep.id === 'activate' ? handleActivate : handleNext}
            >
              {saving ? 'Saving...' : currentStep.id === 'activate' ? 'Activate Integration' : 'Continue →'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════
//  Step Sub-Components
// ═══════════════════════════════════════════════════════════════

function StepTypeSelection({ formData, updateField }) {
  return (
    <>
      <h3 className="wizard-section-title">Choose Data Source Type</h3>
      <p className="wizard-section-desc">
        What kind of external system will provide evidence data?
      </p>
      <div className="type-selection-grid">
        {INTEGRATION_TYPES.map(t => (
          <div
            key={t.id}
            className={`type-card ${formData.integration_type === t.id ? 'selected' : ''}`}
            onClick={() => updateField('integration_type', t.id)}
          >
            <div className={`type-card-icon-box ${t.iconClass}`}>
              {t.icon}
            </div>
            <div className="type-card-name">{t.name}</div>
            <div className="type-card-desc">{t.desc}</div>
          </div>
        ))}
      </div>
    </>
  );
}



function StepConfiguration({ formData, updateField, onFileSelect }) {
  const isFile = FILE_TYPES.has(formData.integration_type);

  return (
    <>
      <h3 className="wizard-section-title">Configure Connection</h3>

      {/* Common Fields */}
      <div className="wizard-form-row">
        <div className="wizard-form-group">
          <label>Integration Name *</label>
          <input
            type="text"
            placeholder="e.g., Shopify Orders API"
            value={formData.name}
            onChange={e => updateField('name', e.target.value)}
          />
        </div>
        <div className="wizard-form-group">
          <label>Evidence Category</label>
          <select
            value={formData.evidence_category}
            onChange={e => updateField('evidence_category', e.target.value)}
          >
            {EVIDENCE_CATEGORIES.map(c => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="wizard-form-group">
        <label>Description</label>
        <input
          type="text"
          placeholder="Brief description of this data source"
          value={formData.description}
          onChange={e => updateField('description', e.target.value)}
        />
      </div>

      {/* Type-specific fields */}
      {formData.integration_type === 'rest_api' && (
        <RestApiFields formData={formData} updateField={updateField} />
      )}
      {formData.integration_type === 'database' && (
        <DatabaseFields formData={formData} updateField={updateField} />
      )}
      {isFile && (
        <FileFields formData={formData} updateField={updateField} onFileSelect={onFileSelect} />
      )}
      {formData.integration_type === 'webhook' && (
        <WebhookFields formData={formData} updateField={updateField} />
      )}
    </>
  );
}


function RestApiFields({ formData, updateField }) {
  return (
    <>
      <div className="wizard-form-group">
        <label>API URL *</label>
        <input
          type="url"
          placeholder="https://api.example.com/v1/orders"
          value={formData.url}
          onChange={e => updateField('url', e.target.value)}
        />
      </div>
      <div className="wizard-form-row">
        <div className="wizard-form-group">
          <label>HTTP Method</label>
          <select value={formData.method} onChange={e => updateField('method', e.target.value)}>
            <option value="GET">GET</option>
            <option value="POST">POST</option>
          </select>
        </div>
        <div className="wizard-form-group">
          <label>Response Path (JSONPath)</label>
          <input
            type="text"
            placeholder="$.data.orders[*]"
            value={formData.response_path}
            onChange={e => updateField('response_path', e.target.value)}
          />
          <span className="wizard-form-hint">Path to extract records from the JSON response</span>
        </div>
      </div>
      <div className="wizard-form-row">
        <div className="wizard-form-group">
          <label>Authentication</label>
          <select value={formData.auth_method} onChange={e => updateField('auth_method', e.target.value)}>
            <option value="none">None</option>
            <option value="api_key">API Key</option>
            <option value="bearer_token">Bearer Token</option>
            <option value="basic_auth">Basic Auth</option>
          </select>
        </div>
        {formData.auth_method !== 'none' && (
          <div className="wizard-form-group">
            <label>
              {formData.auth_method === 'api_key' ? 'API Key' :
               formData.auth_method === 'bearer_token' ? 'Token' : 'Password'}
            </label>
            <input
              type="password"
              placeholder="Enter credential"
              value={formData.auth_value}
              onChange={e => updateField('auth_value', e.target.value)}
            />
          </div>
        )}
      </div>
    </>
  );
}


function DatabaseFields({ formData, updateField }) {
  return (
    <>
      <div className="wizard-form-row">
        <div className="wizard-form-group">
          <label>Database Type</label>
          <select value={formData.dialect} onChange={e => updateField('dialect', e.target.value)}>
            <option value="postgresql">PostgreSQL</option>
            <option value="mysql">MySQL</option>
            <option value="sqlite">SQLite</option>
          </select>
        </div>
        <div className="wizard-form-group">
          <label>Host</label>
          <input
            type="text"
            placeholder="localhost"
            value={formData.host}
            onChange={e => updateField('host', e.target.value)}
          />
        </div>
      </div>
      <div className="wizard-form-row">
        <div className="wizard-form-group">
          <label>Database Name</label>
          <input
            type="text"
            placeholder="merchant_db"
            value={formData.database}
            onChange={e => updateField('database', e.target.value)}
          />
        </div>
        <div className="wizard-form-group">
          <label>Port</label>
          <input
            type="text"
            placeholder="5432"
            value={formData.port}
            onChange={e => updateField('port', e.target.value)}
          />
        </div>
      </div>
      <div className="wizard-form-row">
        <div className="wizard-form-group">
          <label>Username</label>
          <input
            type="text"
            value={formData.db_username}
            onChange={e => updateField('db_username', e.target.value)}
          />
        </div>
        <div className="wizard-form-group">
          <label>Password</label>
          <input
            type="password"
            value={formData.db_password}
            onChange={e => updateField('db_password', e.target.value)}
          />
        </div>
      </div>
      <div className="wizard-form-group">
        <label>SQL Query *</label>
        <textarea
          placeholder="SELECT * FROM orders WHERE order_id = :order_id"
          value={formData.query}
          onChange={e => updateField('query', e.target.value)}
        />
        <span className="wizard-form-hint">Read-only queries only. Use :param for parameters.</span>
      </div>
    </>
  );
}


function FileFields({ formData, updateField, onFileSelect }) {
  const acceptMap = {
    csv_file: '.csv, .tsv, .txt',
    excel_file: '.xlsx, .xls',
    pdf_file: '.pdf',
  };

  return (
    <>
      <FileUploader
        accept={acceptMap[formData.integration_type] || '*'}
        onFileSelect={onFileSelect}
        selectedFile={formData.file}
        fileMetadata={formData.fileMetadata}
        onClear={() => {
          updateField('file', null);
          updateField('fileMetadata', null);
        }}
      />


      {formData.integration_type === 'csv_file' && (
        <div className="wizard-form-row" style={{ marginTop: '1rem' }}>
          <div className="wizard-form-group">
            <label>Delimiter</label>
            <select value={formData.delimiter} onChange={e => updateField('delimiter', e.target.value)}>
              <option value=",">Comma (,)</option>
              <option value=";">Semicolon (;)</option>
              <option value={'\t'}>Tab</option>
              <option value="|">Pipe (|)</option>
            </select>
          </div>
          <div className="wizard-form-group">
            <label>Encoding</label>
            <select value={formData.encoding} onChange={e => updateField('encoding', e.target.value)}>
              <option value="utf-8">UTF-8</option>
              <option value="latin-1">Latin-1</option>
              <option value="ascii">ASCII</option>
            </select>
          </div>
        </div>
      )}

      {formData.integration_type === 'excel_file' && (
        <div className="wizard-form-group" style={{ marginTop: '1rem' }}>
          <label>Sheet Name (optional)</label>
          <input
            type="text"
            placeholder="Leave blank for first sheet"
            value={formData.sheet_name}
            onChange={e => updateField('sheet_name', e.target.value)}
          />
        </div>
      )}
    </>
  );
}


function WebhookFields({ formData, updateField }) {
  return (
    <>
      <div className="wizard-form-group">
        <label>Webhook Secret (optional)</label>
        <input
          type="text"
          placeholder="HMAC secret for signature verification"
          value={formData.webhook_secret}
          onChange={e => updateField('webhook_secret', e.target.value)}
        />
        <span className="wizard-form-hint">Leave blank to skip signature verification</span>
      </div>
      <div className="wizard-form-group">
        <label>Signature Header</label>
        <input
          type="text"
          value={formData.signature_header}
          onChange={e => updateField('signature_header', e.target.value)}
        />
      </div>
    </>
  );
}


function StepTest({ testResult, testLoading, onTest }) {
  return (
    <>
      <h3 className="wizard-section-title">Test Connection</h3>
      <p className="wizard-section-desc">
        Verify the data source is reachable and preview sample records.
      </p>

      <button
        className="btn-add-integration"
        onClick={onTest}
        disabled={testLoading}
        style={{ marginBottom: '1rem' }}
      >
        {testLoading ? '⟳ Testing...' : '⚡ Run Test'}
      </button>

      {testResult && (
        <div className={`test-result ${testResult.success ? 'success' : 'error'}`}>
          <div className="test-result-header">
            <span className="test-result-icon">
              {testResult.success ? '✅' : '❌'}
            </span>
            <span className="test-result-message">{testResult.message}</span>
          </div>
          {testResult.latency_ms > 0 && (
            <div className="test-result-details">
              Latency: {testResult.latency_ms.toFixed(0)}ms
              {testResult.record_count > 0 && ` · ${testResult.record_count} records`}
              {testResult.discovered_fields?.length > 0 && ` · ${testResult.discovered_fields.length} fields`}
            </div>
          )}
          {testResult.sample_data?.length > 0 && (
            <div className="test-result-sample">
              {JSON.stringify(testResult.sample_data[0], null, 2)}
            </div>
          )}
          {testResult.errors?.length > 0 && (
            <div className="test-result-details" style={{ color: '#f87171' }}>
              {testResult.errors.join('; ')}
            </div>
          )}
        </div>
      )}
    </>
  );
}


function StepFieldMapping({ discoveredFields, mappings, onMappingsChange, evidenceCategory }) {
  return (
    <>
      <h3 className="wizard-section-title">Map Fields</h3>
      <p className="wizard-section-desc">
        Map source fields to RAVEN's canonical evidence model. This tells RAVEN
        which field in your data corresponds to which evidence property.
      </p>

      <FieldMappingEditor
        sourceFields={discoveredFields}
        mappings={mappings}
        onChange={onMappingsChange}
        evidenceCategory={evidenceCategory}
      />
    </>
  );
}


function StepActivate({ formData, mappingCount }) {
  const typeLabel = INTEGRATION_TYPES.find(t => t.id === formData.integration_type)?.name || formData.integration_type;

  return (
    <>
      <h3 className="wizard-section-title">Review & Activate</h3>
      <p className="wizard-section-desc">
        Your integration is configured and tested. Activating it will make it
        feed evidence into all future investigations.
      </p>

      <div style={{
        background: 'rgba(255,255,255,0.03)',
        border: '1px solid var(--border-subtle, #27272a)',
        borderRadius: '10px',
        padding: '1.25rem',
      }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.85rem', fontSize: '0.82rem' }}>
          <div>
            <div style={{ color: 'var(--text-tertiary, #52525b)', fontSize: '0.7rem', marginBottom: '0.2rem' }}>Name</div>
            <div style={{ color: 'var(--text-primary, #e4e4e7)', fontWeight: 500 }}>{formData.name}</div>
          </div>
          <div>
            <div style={{ color: 'var(--text-tertiary, #52525b)', fontSize: '0.7rem', marginBottom: '0.2rem' }}>Type</div>
            <div style={{ color: 'var(--text-primary, #e4e4e7)', fontWeight: 500 }}>{typeLabel}</div>
          </div>
          <div>
            <div style={{ color: 'var(--text-tertiary, #52525b)', fontSize: '0.7rem', marginBottom: '0.2rem' }}>Evidence Category</div>
            <div style={{ color: 'var(--text-primary, #e4e4e7)', fontWeight: 500 }}>
              {formData.evidence_category.replace('_', ' ')}
            </div>
          </div>
          <div>
            <div style={{ color: 'var(--text-tertiary, #52525b)', fontSize: '0.7rem', marginBottom: '0.2rem' }}>Field Mappings</div>
            <div style={{ color: 'var(--text-primary, #e4e4e7)', fontWeight: 500 }}>
              {mappingCount > 0 ? `${mappingCount} configured` : 'None (raw data)'}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
