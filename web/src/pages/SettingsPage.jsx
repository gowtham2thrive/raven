import { useState, useEffect } from 'react';
import { useModel } from '../context/ModelContext';
import { ModelPicker } from '../components/ModelPicker';
import {
  sendTestWebhook,
  fetchCredentialStatus,
  validateCredentials,
  fetchGuardrails,
  updateGuardrails,
} from '../api/client';
import {
  IconKey,
  IconSliders,
  IconSend,
  IconLayers,
  IconShieldCheck,
  IconCheckCircle,
  IconXCircle,
  IconRefreshCw,
  IconLock,
  IconCpu,
  IconZap,
  IconCopy,
  IconCheck,
  IconUsers,
  IconAlertTriangle,
} from '../components/Icons';

export function SettingsPage() {
  const { selectedModel, setSelectedModel } = useModel();

  // ── Webhook State ──────────────────────────────────────────
  const [pingStatus, setPingStatus] = useState(null);
  const [isPinging, setIsPinging] = useState(false);
  const [copiedWebhook, setCopiedWebhook] = useState(false);
  const webhookUrl = 'http://127.0.0.1:8000/webhooks/razorpay';

  // ── Credential State ───────────────────────────────────────
  const [credentials, setCredentials] = useState(null);
  const [credentialResults, setCredentialResults] = useState(null);
  const [isValidating, setIsValidating] = useState(false);
  const [credentialError, setCredentialError] = useState(null);

  // ── Guardrails State ───────────────────────────────────────
  const [guardrails, setGuardrails] = useState(null);
  const [guardrailDraft, setGuardrailDraft] = useState(null);
  const [guardrailDefaults, setGuardrailDefaults] = useState(null);
  const [isSavingGuardrails, setIsSavingGuardrails] = useState(false);
  const [guardrailSaveStatus, setGuardrailSaveStatus] = useState(null);
  const [guardrailError, setGuardrailError] = useState(null);

  // ── Load credentials on mount ──────────────────────────────
  useEffect(() => {
    fetchCredentialStatus()
      .then(data => setCredentials(data?.credentials || null))
      .catch(err => setCredentialError(err.message));
  }, []);

  // ── Load guardrails on mount ───────────────────────────────
  useEffect(() => {
    fetchGuardrails()
      .then(data => {
        const g = data?.guardrails || null;
        setGuardrails(g);
        setGuardrailDraft(g ? { ...g } : null);
        if (data?.defaults) setGuardrailDefaults(data.defaults);
      })
      .catch(err => setGuardrailError(err.message));
  }, []);

  // ── Handlers ───────────────────────────────────────────────

  const handleCopyWebhook = async () => {
    try {
      await navigator.clipboard.writeText(webhookUrl);
      setCopiedWebhook(true);
      setTimeout(() => setCopiedWebhook(false), 2000);
    } catch {
      // Fallback
    }
  };

  const handleTestWebhook = async () => {
    setIsPinging(true);
    setPingStatus(null);
    try {
      const result = await sendTestWebhook();
      setPingStatus({ type: 'success', text: `Webhook responded: ${result.status} — Case ${result.case_id || 'created'}` });
    } catch (e) {
      setPingStatus({ type: 'error', text: `Webhook failed: ${e.message}` });
    } finally {
      setIsPinging(false);
    }
  };

  const handleValidateCredentials = async () => {
    setIsValidating(true);
    setCredentialResults(null);
    try {
      const data = await validateCredentials();
      setCredentialResults(data?.results || null);
    } catch (e) {
      setCredentialError(e.message);
    } finally {
      setIsValidating(false);
    }
  };

  const handleGuardrailChange = (field, value) => {
    setGuardrailDraft(prev => ({ ...prev, [field]: value }));
    setGuardrailSaveStatus(null);
  };

  const handleSaveGuardrails = async () => {
    if (!guardrailDraft) return;
    setIsSavingGuardrails(true);
    setGuardrailSaveStatus(null);
    try {
      const data = await updateGuardrails(guardrailDraft);
      setGuardrails(data?.guardrails || guardrailDraft);
      const warningCount = data?.warnings?.length || 0;
      const suffix = warningCount > 0 ? ` (${warningCount} warning${warningCount > 1 ? 's' : ''})` : '';
      setGuardrailSaveStatus({ type: 'success', text: `Guardrails saved successfully${suffix}` });
    } catch (e) {
      setGuardrailSaveStatus({ type: 'error', text: `Failed to save: ${e.message}` });
    } finally {
      setIsSavingGuardrails(false);
    }
  };

  const handleResetGuardrails = () => {
    if (guardrailDefaults) {
      setGuardrailDraft({ ...guardrailDefaults });
      setGuardrailSaveStatus(null);
    }
  };

  const hasGuardrailChanges = guardrails && guardrailDraft &&
    JSON.stringify(guardrails) !== JSON.stringify(guardrailDraft);

  // ── Amount formatting & parsing ────────────────────────────

  const AMOUNT_SLIDER_MAX = 50000000; // ₹5,00,000 in paise
  const AMOUNT_SLIDER_STEP = 50000;   // ₹500 in paise

  const formatAmount = (paise) => {
    if (paise === null || paise === undefined) return 'No limit';
    if (paise === 0) return '₹0';
    return `₹${(paise / 100).toLocaleString('en-IN')}`;
  };

  const formatAmountInput = (paise) => {
    if (paise === null || paise === undefined) return '';
    return (paise / 100).toLocaleString('en-IN');
  };

  const parseAmountInput = (rupeeStr) => {
    const cleaned = rupeeStr.replace(/[^0-9]/g, '');
    if (!cleaned) return 0;
    return parseInt(cleaned, 10) * 100;
  };

  // ── Cross-field validation warnings ────────────────────────

  const guardrailWarnings = [];
  if (guardrailDraft) {
    const maxAmt = guardrailDraft.max_dispute_amount;
    const reviewAbove = guardrailDraft.require_human_review_above;

    if (
      maxAmt !== null && maxAmt !== undefined &&
      reviewAbove !== null && reviewAbove !== undefined &&
      reviewAbove > maxAmt
    ) {
      guardrailWarnings.push(
        `Human review threshold (${formatAmount(reviewAbove)}) exceeds max dispute amount (${formatAmount(maxAmt)}) — human review will never trigger for auto-contested disputes.`
      );
    }
    if (guardrailDraft.min_confidence_threshold === 100) {
      guardrailWarnings.push(
        'Confidence threshold is 100% — no dispute will ever be auto-recommended for contest.'
      );
    }
    if (guardrailDraft.auto_contest_enabled && maxAmt === 0) {
      guardrailWarnings.push(
        'Auto-contest is enabled but max dispute amount is ₹0 — no disputes are eligible.'
      );
    }
  }

  const isMaxAmountNoLimit = guardrailDraft?.max_dispute_amount === null;
  const isReviewDisabled = guardrailDraft?.require_human_review_above === null;

  return (
    <div className="page">
      <header className="page-header">
        <div className="page-header-left">
          <h1>System Settings</h1>
          <p className="page-header-subtitle">
            Configure AI reasoning models, gateway webhooks, API credentials, and auto-pilot guardrails
          </p>
        </div>
      </header>

      <div className="settings-layout">
        {/* ─── AI Reasoning Engine ─────────────────────────── */}
        <section id="model" className="settings-card settings-card--model">
          <div className="settings-card-header">
            <div className="settings-card-icon settings-card-icon--blue">
              <IconCpu size={20} />
            </div>
            <div>
              <h2 className="settings-card-title">AI Reasoning Engine</h2>
              <p className="settings-card-desc">
                Choose your default Gemini reasoning model for dispute investigation and response synthesis.
              </p>
            </div>
          </div>
          <div className="settings-card-body">
            <ModelPicker selectedModel={selectedModel} onSelectModel={setSelectedModel} />
          </div>
        </section>

        {/* ─── Razorpay Webhook ─────────────────────────────── */}
        <section id="webhook" className="settings-card settings-card--webhook">
          <div className="settings-card-header">
            <div className="settings-card-icon settings-card-icon--purple">
              <IconLayers size={20} />
            </div>
            <div>
              <h2 className="settings-card-title">Razorpay Webhook Endpoint</h2>
              <p className="settings-card-desc">
                Incoming chargeback notifications are ingested here in real time.
              </p>
            </div>
          </div>
          <div className="settings-card-body">
            <div className="settings-input-row">
              <input
                type="text"
                readOnly
                value={webhookUrl}
                className="settings-input"
                id="webhook-url-input"
              />
              <div className="settings-input-buttons">
                <button
                  type="button"
                  className="btn btn-outline"
                  onClick={handleCopyWebhook}
                  title="Copy webhook URL to clipboard"
                  id="webhook-copy-btn"
                >
                  {copiedWebhook ? <IconCheck size={14} color="var(--color-success)" /> : <IconCopy size={14} />}
                  <span>{copiedWebhook ? 'Copied' : 'Copy'}</span>
                </button>
                <button
                  type="button"
                  className="btn btn-outline"
                  onClick={handleTestWebhook}
                  disabled={isPinging}
                  title="Test webhook endpoint handshake"
                  id="webhook-ping-btn"
                >
                  <IconSend size={14} />
                  <span>{isPinging ? 'Pinging...' : 'Ping'}</span>
                </button>
              </div>
            </div>
            {pingStatus && (
              <div className={`settings-status-msg settings-status-msg--${pingStatus.type}`}>
                {pingStatus.type === 'success' ? <IconCheckCircle size={14} /> : <IconXCircle size={14} />}
                <span>{pingStatus.text}</span>
              </div>
            )}
          </div>
        </section>
        {/* ─── API Credentials ──────────────────────────────── */}
        <section id="credentials" className="settings-card settings-card--credentials">
          <div className="settings-card-header">
            <div className="settings-card-icon settings-card-icon--amber">
              <IconKey size={20} />
            </div>
            <div>
              <h2 className="settings-card-title">API Credentials & Gateway Keys</h2>
              <p className="settings-card-desc">
                Server-side credential status. Keys are configured via environment variables (<code>.env</code>).
              </p>
            </div>
          </div>
          <div className="settings-card-body">
            {credentialError && (
              <div className="settings-status-msg settings-status-msg--error">
                <IconXCircle size={14} />
                <span>{credentialError}</span>
              </div>
            )}

            {credentials ? (
              <div className="credential-grid">
                {Object.entries(credentials).map(([key, cred]) => {
                  const validationResult = credentialResults?.[key];
                  return (
                    <div key={key} className="credential-row">
                      <div className="credential-info">
                        <div className="credential-label">
                          <IconLock size={12} />
                          <span>{cred.label}</span>
                        </div>
                        <div className="credential-value">
                          {cred.configured ? (
                            <code className="credential-masked">{cred.masked}</code>
                          ) : (
                            <span className="credential-missing">Not configured</span>
                          )}
                        </div>
                      </div>
                      <div className="credential-status">
                        {validationResult ? (
                          <span className={`credential-badge ${validationResult.valid ? 'credential-badge--valid' : 'credential-badge--invalid'}`}>
                            {validationResult.valid ? <IconCheckCircle size={12} /> : <IconXCircle size={12} />}
                            <span>{validationResult.valid ? 'Valid' : 'Failed'}</span>
                          </span>
                        ) : (
                          <span className={`credential-badge ${cred.configured ? 'credential-badge--configured' : 'credential-badge--missing'}`}>
                            {cred.configured ? 'Configured' : 'Missing'}
                          </span>
                        )}
                      </div>
                      {validationResult && (
                        <div className="credential-validation-msg">
                          {validationResult.message}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : !credentialError ? (
              <div className="settings-loading">Loading credentials...</div>
            ) : null}

            <div className="settings-card-actions">
              <button
                type="button"
                className="btn btn-outline"
                onClick={handleValidateCredentials}
                disabled={isValidating}
                id="validate-credentials-btn"
              >
                <IconRefreshCw size={14} className={isValidating ? 'spin' : ''} />
                <span>{isValidating ? 'Validating...' : 'Validate All Keys'}</span>
              </button>
            </div>
          </div>
        </section>

        {/* ─── Auto-Pilot Guardrails ────────────────────────── */}
        <section id="guardrails" className="settings-card settings-card--guardrails">
          <div className="settings-card-header">
            <div className="settings-card-icon settings-card-icon--green">
              <IconShieldCheck size={20} />
            </div>
            <div>
              <h2 className="settings-card-title">Auto-Pilot Policies & Guardrails</h2>
              <p className="settings-card-desc">
                Configure automated contest recommendation thresholds and amount gating policies.
              </p>
            </div>
          </div>
          <div className="settings-card-body">
            {guardrailError && (
              <div className="settings-status-msg settings-status-msg--error">
                <IconXCircle size={14} />
                <span>{guardrailError}</span>
              </div>
            )}

            {guardrailDraft ? (
              <div className="guardrail-controls">
                {/* Auto-Contest Toggle */}
                <div className="guardrail-field">
                  <div className="guardrail-field-header">
                    <div className="guardrail-field-label">
                      <IconZap size={14} />
                      <span>Auto-Contest Recommendations</span>
                    </div>
                    <button
                      type="button"
                      className={`toggle-switch ${guardrailDraft.auto_contest_enabled ? 'active' : ''}`}
                      onClick={() => handleGuardrailChange('auto_contest_enabled', !guardrailDraft.auto_contest_enabled)}
                      role="switch"
                      aria-checked={guardrailDraft.auto_contest_enabled}
                      id="auto-contest-toggle"
                    >
                      <span className="toggle-switch-knob" />
                    </button>
                  </div>
                  <p className="guardrail-field-desc">
                    When enabled, RAVEN will automatically recommend contesting disputes that meet all guardrail criteria. Human review is still required for final submission.
                  </p>
                </div>

                {/* ── Threshold Controls (disabled when auto-contest is OFF) ── */}
                <div className={`guardrail-threshold-controls${!guardrailDraft.auto_contest_enabled ? ' guardrail-threshold-controls--disabled' : ''}`}>

                  {!guardrailDraft.auto_contest_enabled && (
                    <div className="guardrail-disabled-notice">
                      <IconAlertTriangle size={16} />
                      <span>Enable auto-contest above to configure these thresholds.</span>
                    </div>
                  )}

                  {/* Confidence Threshold Slider */}
                  <div className="guardrail-field">
                    <div className="guardrail-field-header">
                      <div className="guardrail-field-label">
                        <IconSliders size={14} />
                        <span>Minimum Confidence Threshold</span>
                      </div>
                      <span className="guardrail-field-value">{guardrailDraft.min_confidence_threshold}%</span>
                    </div>
                    <input
                      type="range"
                      min="50"
                      max="100"
                      step="5"
                      value={guardrailDraft.min_confidence_threshold}
                      onChange={e => handleGuardrailChange('min_confidence_threshold', parseInt(e.target.value, 10))}
                      className="guardrail-slider"
                      id="confidence-threshold-slider"
                    />
                    <div className="guardrail-slider-labels">
                      <span>50%</span>
                      <span>75%</span>
                      <span>100%</span>
                    </div>
                    <p className="guardrail-field-desc">
                      Only disputes with investigation confidence at or above this level will be auto-recommended for contest.
                    </p>
                    {guardrailDraft.min_confidence_threshold === 100 && (
                      <div className="guardrail-warning">
                        <IconAlertTriangle size={14} />
                        <span>At 100%, no dispute will ever be auto-recommended.</span>
                      </div>
                    )}
                  </div>

                  {/* Max Dispute Amount */}
                  <div className="guardrail-field">
                    <div className="guardrail-field-header">
                      <div className="guardrail-field-label">
                        <IconShieldCheck size={14} />
                        <span>Maximum Dispute Amount</span>
                      </div>
                      <div className="guardrail-amount-row">
                        <span className="guardrail-currency-prefix">₹</span>
                        <input
                          type="text"
                          className={`guardrail-inline-input${isMaxAmountNoLimit ? ' guardrail-inline-input--no-limit' : ''}`}
                          value={isMaxAmountNoLimit ? '' : formatAmountInput(guardrailDraft.max_dispute_amount)}
                          onChange={e => handleGuardrailChange('max_dispute_amount', parseAmountInput(e.target.value))}
                          disabled={isMaxAmountNoLimit}
                          placeholder={isMaxAmountNoLimit ? 'No limit' : '0'}
                          id="max-amount-input"
                        />
                      </div>
                    </div>
                    {!isMaxAmountNoLimit && (
                      <>
                        <input
                          type="range"
                          min="0"
                          max={AMOUNT_SLIDER_MAX}
                          step={AMOUNT_SLIDER_STEP}
                          value={Math.min(guardrailDraft.max_dispute_amount ?? 0, AMOUNT_SLIDER_MAX)}
                          onChange={e => handleGuardrailChange('max_dispute_amount', parseInt(e.target.value, 10))}
                          className="guardrail-slider"
                          id="max-amount-slider"
                        />
                        <div className="guardrail-slider-labels">
                          <span>₹0</span>
                          <span>₹2,50,000</span>
                          <span>₹5,00,000</span>
                        </div>
                      </>
                    )}
                    <div className="guardrail-opt-toggle">
                      <input
                        type="checkbox"
                        className="guardrail-opt-checkbox"
                        checked={isMaxAmountNoLimit}
                        onChange={e => handleGuardrailChange(
                          'max_dispute_amount',
                          e.target.checked ? null : (guardrailDefaults?.max_dispute_amount ?? 5000000)
                        )}
                        id="max-amount-no-limit"
                      />
                      <label htmlFor="max-amount-no-limit" className="guardrail-opt-label">
                        No limit — any dispute amount is eligible for auto-contest
                      </label>
                    </div>
                    <p className="guardrail-field-desc">
                      Disputes above this amount will never be auto-recommended — they always require manual analyst review.
                    </p>
                    {guardrailDraft.auto_contest_enabled && guardrailDraft.max_dispute_amount === 0 && (
                      <div className="guardrail-warning">
                        <IconAlertTriangle size={14} />
                        <span>Max amount is ₹0 — no disputes are eligible for auto-contest.</span>
                      </div>
                    )}
                  </div>

                  {/* Human Review Threshold */}
                  <div className="guardrail-field">
                    <div className="guardrail-field-header">
                      <div className="guardrail-field-label">
                        <IconUsers size={14} />
                        <span>Mandatory Human Review Above</span>
                      </div>
                      <div className="guardrail-amount-row">
                        <span className="guardrail-currency-prefix">₹</span>
                        <input
                          type="text"
                          className={`guardrail-inline-input${isReviewDisabled ? ' guardrail-inline-input--no-limit' : ''}`}
                          value={isReviewDisabled ? '' : formatAmountInput(guardrailDraft.require_human_review_above)}
                          onChange={e => handleGuardrailChange('require_human_review_above', parseAmountInput(e.target.value))}
                          disabled={isReviewDisabled}
                          placeholder={isReviewDisabled ? 'Disabled' : '0'}
                          id="human-review-input"
                        />
                      </div>
                    </div>
                    {!isReviewDisabled && (
                      <>
                        <input
                          type="range"
                          min="0"
                          max={AMOUNT_SLIDER_MAX}
                          step={AMOUNT_SLIDER_STEP}
                          value={Math.min(guardrailDraft.require_human_review_above ?? 0, AMOUNT_SLIDER_MAX)}
                          onChange={e => handleGuardrailChange('require_human_review_above', parseInt(e.target.value, 10))}
                          className="guardrail-slider"
                          id="human-review-slider"
                        />
                        <div className="guardrail-slider-labels">
                          <span>₹0</span>
                          <span>₹2,50,000</span>
                          <span>₹5,00,000</span>
                        </div>
                      </>
                    )}
                    <div className="guardrail-opt-toggle">
                      <input
                        type="checkbox"
                        className="guardrail-opt-checkbox"
                        checked={isReviewDisabled}
                        onChange={e => handleGuardrailChange(
                          'require_human_review_above',
                          e.target.checked ? null : (guardrailDefaults?.require_human_review_above ?? 2500000)
                        )}
                        id="human-review-disabled"
                      />
                      <label htmlFor="human-review-disabled" className="guardrail-opt-label">
                        Disable — trust auto-contest logic without a mandatory review threshold
                      </label>
                    </div>
                    <p className="guardrail-field-desc">
                      Disputes above this value always require explicit human sign-off before any action, regardless of confidence score.
                    </p>
                  </div>
                </div>

                {/* Cross-field warnings */}
                {guardrailWarnings.filter(w =>
                  !w.includes('100%') && !w.includes('₹0')
                ).map((warning, i) => (
                  <div key={i} className="guardrail-warning">
                    <IconAlertTriangle size={14} />
                    <span>{warning}</span>
                  </div>
                ))}
              </div>
            ) : !guardrailError ? (
              <div className="settings-loading">Loading guardrails...</div>
            ) : null}

            {guardrailDraft && (
              <div className="settings-card-actions">
                <div className="guardrail-actions-row">
                  <button
                    type="button"
                    className={`btn ${hasGuardrailChanges ? 'btn-primary' : 'btn-outline'}`}
                    onClick={handleSaveGuardrails}
                    disabled={isSavingGuardrails || !hasGuardrailChanges}
                    id="save-guardrails-btn"
                  >
                    <IconShieldCheck size={14} />
                    <span>{isSavingGuardrails ? 'Saving...' : hasGuardrailChanges ? 'Save Changes' : 'No Changes'}</span>
                  </button>
                  {hasGuardrailChanges && guardrailDefaults && (
                    <button
                      type="button"
                      className="guardrail-reset-btn"
                      onClick={handleResetGuardrails}
                      id="reset-guardrails-btn"
                    >
                      Reset to defaults
                    </button>
                  )}
                </div>
              </div>
            )}

            {guardrailSaveStatus && (
              <div className={`settings-status-msg settings-status-msg--${guardrailSaveStatus.type}`}>
                {guardrailSaveStatus.type === 'success' ? <IconCheckCircle size={14} /> : <IconXCircle size={14} />}
                <span>{guardrailSaveStatus.text}</span>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
