import { useState, useEffect, useMemo } from 'react';
import { 
  fetchSimulatorPresets, 
  generateSimulatedCase, 
  clearAllCases 
} from '../api/client';
import { Badge } from './Badge';
import { Spinner } from './Spinner';
import { 
  IconX, 
  IconSparkles, 
  IconBolt, 
  IconShieldCheck, 
  IconShieldAlert, 
  IconAlertTriangle, 
  IconCheckCircle, 
  IconClock, 
  IconRefreshCw, 
  IconActivity, 
  IconTruck, 
  IconPackage, 
  IconTrash, 
  IconSliders, 
  IconGitPullRequest 
} from './Icons';

export const DEFAULT_SIMULATION_PRESETS = [
  {
    id: 'physical_strong_delivery',
    name: 'Physical Goods: Strong Delivery Defense',
    category: 'Physical Goods',
    icon: 'truck',
    reason_code: 'product_not_received',
    reason_description: 'Customer claims package was never delivered.',
    default_product: 'Sony WH-1000XM5 Wireless Headphones',
    default_amount: 2499900,
    difficulty: 'Strong Defense',
    expected_recommendation: 'contest',
    expected_confidence: 'high',
    summary: 'Carrier tracking shows delivered with recipient signature and doorstep photo proof.',
  },
  {
    id: 'physical_weak_unsigned',
    name: 'Physical Goods: Left at Door (Unsigned)',
    category: 'Physical Goods',
    icon: 'package',
    reason_code: 'product_not_received',
    reason_description: 'Customer claims package stolen from porch or never received.',
    default_product: 'Ergonomic Standing Desk',
    default_amount: 1849900,
    difficulty: 'Weak Evidence',
    expected_recommendation: 'human_review',
    expected_confidence: 'medium',
    summary: 'Carrier marked delivered as "left at front door" without physical signature.',
  },
  {
    id: 'physical_in_transit_lost',
    name: 'Physical Goods: Package In-Transit / Lost',
    category: 'Physical Goods',
    icon: 'alert-triangle',
    reason_code: 'product_not_received',
    reason_description: 'Customer disputes order after tracking stalled in transit.',
    default_product: 'Mechanical Gaming Keyboard',
    default_amount: 899900,
    difficulty: 'Merchant Loss',
    expected_recommendation: 'accept_loss',
    expected_confidence: 'high',
    summary: 'Carrier tracking shows package stuck in transit. Non-delivery confirmed.',
  },
  {
    id: 'unauthorized_strong_3ds',
    name: 'Fraud: 3DS OTP Verified & Trusted Device',
    category: 'Fraud & Security',
    icon: 'shield-check',
    reason_code: 'unauthorized_transaction',
    reason_description: 'Cardholder claims transaction was fraudulent / stolen card.',
    default_product: 'Apple iPad Air M2 11-inch',
    default_amount: 5990000,
    difficulty: 'Strong Defense',
    expected_recommendation: 'contest',
    expected_confidence: 'high',
    summary: '3D Secure v2 OTP authenticated with matching repeat device fingerprint.',
  },
  {
    id: 'unauthorized_suspicious',
    name: 'Fraud: Foreign IP & Unverified Auth',
    category: 'Fraud & Security',
    icon: 'shield-alert',
    reason_code: 'unauthorized_transaction',
    reason_description: 'Cardholder claims unrecognized transaction on statement.',
    default_product: 'Luxury Designer Leather Bag',
    default_amount: 3499900,
    difficulty: 'High Risk Fraud',
    expected_recommendation: 'accept_loss',
    expected_confidence: 'high',
    summary: 'No 3DS verification, first-time untrusted device from unexpected foreign IP.',
  },
  {
    id: 'digital_service_active',
    name: 'Digital SaaS: Active Usage & API Activity',
    category: 'Digital Services',
    icon: 'activity',
    reason_code: 'service_not_rendered',
    reason_description: 'Customer claims enterprise subscription was never activated.',
    default_product: 'Developer Cloud API Enterprise Plan',
    default_amount: 4999900,
    difficulty: 'Strong Defense',
    expected_recommendation: 'contest',
    expected_confidence: 'high',
    summary: 'Active daily login session tokens, API request logs, and data exports.',
  },
  {
    id: 'quality_return_window_expired',
    name: 'Product Quality: Return Window Expired',
    category: 'Product Quality',
    icon: 'refresh-cw',
    reason_code: 'product_not_as_described',
    reason_description: 'Customer claims item was defective after 60 days of usage.',
    default_product: 'Kitchen Stand Mixer Pro 1200W',
    default_amount: 1249900,
    difficulty: 'Strong Defense',
    expected_recommendation: 'contest',
    expected_confidence: 'high',
    summary: 'Dispute filed 60+ days post delivery, exceeding the 7-day merchant return window.',
  },
  {
    id: 'duplicate_charge_refunded',
    name: 'Billing: Duplicate Charge Already Refunded',
    category: 'Billing & Payments',
    icon: 'refresh-cw',
    reason_code: 'duplicate_transaction',
    reason_description: 'Customer disputes duplicate billing on credit card statement.',
    default_product: 'Annual SaaS Pro Membership',
    default_amount: 1499900,
    difficulty: 'Strong Defense',
    expected_recommendation: 'contest',
    expected_confidence: 'high',
    summary: 'Second transaction was auto-refunded to customer card within 3 hours.',
  },
  {
    id: 'contradictory_carrier_rts',
    name: 'Contradiction: Carrier RTS vs Delivered',
    category: 'Contradictions',
    icon: 'git-pull-request',
    reason_code: 'product_not_received',
    reason_description: 'Customer claims order was never received.',
    default_product: 'Noise Isolating Earbuds',
    default_amount: 499900,
    difficulty: 'Contradiction Flagged',
    expected_recommendation: 'human_review',
    expected_confidence: 'low',
    summary: 'Carrier API status returns Returned to Sender (RTS) while merchant record shows Delivered.',
  },
  {
    id: 'edge_timezone_mismatch',
    name: 'Edge Case: Multi-Timezone Anomaly',
    category: 'Edge Cases',
    icon: 'clock',
    reason_code: 'product_not_received',
    reason_description: 'Disputed delivery timeline due to international timezone parsing discrepancies.',
    default_product: 'BenQ Designer Desk Lamp',
    default_amount: 699900,
    difficulty: 'Medium Strength',
    expected_recommendation: 'human_review',
    expected_confidence: 'medium',
    summary: 'Carrier timestamp logged in America/Los_Angeles (PST) while merchant order logged in Asia/Kolkata (IST).',
  },
];

export function CaseSimulatorModal({
  isOpen,
  onClose,
  onCaseCreated,
  onCasesCleared,
}) {
  const [activeTab, setActiveTab] = useState('presets'); // presets | custom
  const [categoryFilter, setCategoryFilter] = useState('All');
  const [presets, setPresets] = useState(DEFAULT_SIMULATION_PRESETS);
  const [loadingPresets, setLoadingPresets] = useState(false);
  const [submittingPresetId, setSubmittingPresetId] = useState(null);
  const [isSubmittingCustom, setIsSubmittingCustom] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const [autoInvestigate, setAutoInvestigate] = useState(true);
  const [statusMessage, setStatusMessage] = useState(null);
  const [confirmClearOpen, setConfirmClearOpen] = useState(false);

  // Custom scenario state
  const [customForm, setCustomForm] = useState({
    customer_name: 'Aditya Verma',
    customer_email: 'aditya.verma@example.com',
    customer_phone: '+919876543210',
    product_name: 'Wireless Noise Cancelling Headphones',
    amount_inr: 14999,
    reason_code: 'product_not_received',
    reason_description: 'Customer claims the package was not delivered.',
    evidence_profile: 'strong',
    carrier: 'BlueDart',
    delivery_status: 'delivered',
    proof_type: 'signature',
    auth_verified: true,
    device_known: true,
    has_refund: false,
    has_support_chat: false,
  });

  useEffect(() => {
    if (!isOpen) return;
    async function loadPresets() {
      setLoadingPresets(true);
      try {
        const res = await fetchSimulatorPresets();
        if (res && res.presets && res.presets.length > 0) {
          setPresets(res.presets);
        }
      } catch (e) {
        console.warn('Using default simulator presets:', e.message);
      } finally {
        setLoadingPresets(false);
      }
    }
    loadPresets();
  }, [isOpen]);

  // Categories for filter
  const categories = useMemo(() => {
    const set = new Set(presets.map(p => p.category));
    return ['All', ...Array.from(set)];
  }, [presets]);

  const filteredPresets = useMemo(() => {
    if (categoryFilter === 'All') return presets;
    return presets.filter(p => p.category === categoryFilter);
  }, [presets, categoryFilter]);

  if (!isOpen) return null;

  const handleSimulatePreset = async (preset) => {
    setSubmittingPresetId(preset.id);
    setStatusMessage({ type: 'info', text: `Generating ${preset.name}...` });
    try {
      const res = await generateSimulatedCase({
        preset_id: preset.id,
        auto_investigate: autoInvestigate,
      });
      setStatusMessage({ 
        type: 'success', 
        text: `Simulated case ${res.case_id} generated successfully! ${autoInvestigate ? 'AI Investigation complete.' : 'Added to pending queue.'}` 
      });
      if (onCaseCreated) {
        onCaseCreated(res.case_id, res);
      }
      setTimeout(() => {
        onClose();
      }, 700);
    } catch (e) {
      setStatusMessage({ type: 'error', text: `Simulation failed: ${e.message}` });
    } finally {
      setSubmittingPresetId(null);
    }
  };

  const handleSimulateCustom = async (e) => {
    e.preventDefault();
    setIsSubmittingCustom(true);
    setStatusMessage({ type: 'info', text: 'Generating custom scenario...' });
    try {
      const res = await generateSimulatedCase({
        custom_config: customForm,
        auto_investigate: autoInvestigate,
      });
      setStatusMessage({ 
        type: 'success', 
        text: `Custom case ${res.case_id} created successfully! ${autoInvestigate ? 'AI Investigation complete.' : 'Added to pending queue.'}` 
      });
      if (onCaseCreated) {
        onCaseCreated(res.case_id, res);
      }
      setTimeout(() => {
        onClose();
      }, 700);
    } catch (e) {
      setStatusMessage({ type: 'error', text: `Custom simulation failed: ${e.message}` });
    } finally {
      setIsSubmittingCustom(false);
    }
  };

  const handleClearAll = async () => {
    setIsClearing(true);
    setStatusMessage({ type: 'info', text: 'Purging test environment cases...' });
    try {
      const res = await clearAllCases();
      setStatusMessage({ type: 'success', text: `Test environment reset: ${res.deleted_count || 0} cases cleared.` });
      setConfirmClearOpen(false);
      if (onCasesCleared) {
        onCasesCleared();
      }
    } catch (e) {
      setStatusMessage({ type: 'error', text: `Failed to clear cases: ${e.message}` });
    } finally {
      setIsClearing(false);
    }
  };

  const getPresetIcon = (iconName) => {
    switch (iconName) {
      case 'truck': return <IconTruck size={18} />;
      case 'package': return <IconPackage size={18} />;
      case 'shield-check': return <IconShieldCheck size={18} />;
      case 'shield-alert': return <IconShieldAlert size={18} />;
      case 'activity': return <IconActivity size={18} />;
      case 'refresh-cw': return <IconRefreshCw size={18} />;
      case 'git-pull-request': return <IconGitPullRequest size={18} />;
      case 'clock': return <IconClock size={18} />;
      case 'alert-triangle': return <IconAlertTriangle size={18} />;
      default: return <IconSparkles size={18} />;
    }
  };

  const getExpectedBadge = (recommendation, difficulty) => {
    if (recommendation === 'contest') {
      return <Badge type="success">Expected: CONTEST</Badge>;
    }
    if (recommendation === 'accept_loss') {
      return <Badge type="danger">Expected: ACCEPT LOSS</Badge>;
    }
    if (difficulty === 'Contradiction Flagged') {
      return <Badge type="warning">CONTRADICTION DETECTED</Badge>;
    }
    return <Badge type="warning">Expected: HUMAN REVIEW</Badge>;
  };

  return (
    <div className="simulator-modal-overlay" onClick={onClose}>
      <div className="simulator-modal" onClick={e => e.stopPropagation()}>
        {/* Modal Header */}
        <div className="simulator-header">
          <div className="simulator-header-left">
            <div className="simulator-header-icon">
              <IconSparkles size={20} />
            </div>
            <div>
              <h2 className="simulator-title">Dispute Case Simulator</h2>
              <p className="simulator-subtitle">
                Generate realistic chargeback dispute cases across physical goods, fraud, digital services, and contradictions to test AI investigation.
              </p>
            </div>
          </div>
          <button type="button" className="simulator-close-btn" onClick={onClose} aria-label="Close modal">
            <IconX size={16} />
          </button>
        </div>

        {/* Global Controls & Mode Switcher */}
        <div className="simulator-nav-bar">
          <div className="simulator-tabs">
            <button
              type="button"
              className={`simulator-tab ${activeTab === 'presets' ? 'active' : ''}`}
              onClick={() => setActiveTab('presets')}
            >
              <IconSparkles size={14} />
              <span>Preset Archetypes ({presets.length})</span>
            </button>
            <button
              type="button"
              className={`simulator-tab ${activeTab === 'custom' ? 'active' : ''}`}
              onClick={() => setActiveTab('custom')}
            >
              <IconSliders size={14} />
              <span>Custom Scenario Builder</span>
            </button>
          </div>

          <div className="simulator-auto-toggle">
            <label className="simulator-checkbox-label">
              <input
                type="checkbox"
                checked={autoInvestigate}
                onChange={e => setAutoInvestigate(e.target.checked)}
              />
              <span>Auto-investigate with AI immediately</span>
            </label>
          </div>
        </div>

        {/* Status Toast Notification */}
        {statusMessage && (
          <div className={`simulator-status-banner status-${statusMessage.type}`}>
            {statusMessage.type === 'info' && <Spinner size="small" />}
            {statusMessage.type === 'success' && <IconCheckCircle size={16} />}
            {statusMessage.type === 'error' && <IconAlertTriangle size={16} />}
            <span>{statusMessage.text}</span>
          </div>
        )}

        {/* TAB 1: PRESET ARCHETYPES */}
        {activeTab === 'presets' && (
          <div className="simulator-body">
            {/* Category Filter Chips */}
            <div className="simulator-filter-chips">
              {categories.map(cat => (
                <button
                  key={cat}
                  type="button"
                  className={`filter-chip ${categoryFilter === cat ? 'active' : ''}`}
                  onClick={() => setCategoryFilter(cat)}
                >
                  {cat}
                </button>
              ))}
            </div>

            {loadingPresets ? (
              <div className="simulator-loading">
                <Spinner />
                <p>Loading dispute simulation catalog...</p>
              </div>
            ) : (
              <div className="simulator-preset-grid">
                {filteredPresets.map(preset => (
                  <div key={preset.id} className="simulator-card">
                    <div className="simulator-card-top">
                      <div className="simulator-card-icon">
                        {getPresetIcon(preset.icon)}
                      </div>
                      <div className="simulator-card-badges">
                        <span className="simulator-category-tag">{preset.category}</span>
                        {getExpectedBadge(preset.expected_recommendation, preset.difficulty)}
                      </div>
                    </div>

                    <h3 className="simulator-card-title">{preset.name}</h3>
                    <div className="simulator-card-amount">
                      ₹{((preset.default_amount || 0) / 100).toLocaleString('en-IN')} • <code>{preset.reason_code}</code>
                    </div>

                    <p className="simulator-card-narrative">{preset.reason_description}</p>
                    <p className="simulator-card-summary">{preset.summary}</p>

                    <div className="simulator-card-footer">
                      <button
                        type="button"
                        className="btn btn-primary simulator-simulate-btn"
                        disabled={submittingPresetId != null}
                        onClick={() => handleSimulatePreset(preset)}
                      >
                        {submittingPresetId === preset.id ? (
                          <>
                            <Spinner size="small" />
                            <span>Generating...</span>
                          </>
                        ) : (
                          <>
                            <IconBolt size={14} />
                            <span>Simulate Case</span>
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* TAB 2: CUSTOM SCENARIO BUILDER */}
        {activeTab === 'custom' && (
          <form className="simulator-body simulator-custom-form" onSubmit={handleSimulateCustom}>
            <div className="custom-form-grid">
              {/* Row 1: Reason & Amount */}
              <div className="form-group">
                <label className="form-label">Dispute Reason Code</label>
                <select
                  className="form-select"
                  value={customForm.reason_code}
                  onChange={e => {
                    const code = e.target.value;
                    let desc = 'Customer disputes transaction.';
                    let profile = 'strong';
                    if (code === 'product_not_received') desc = 'Customer claims order was never delivered.';
                    if (code === 'unauthorized_transaction') {
                      desc = 'Customer claims card charged without authorization.';
                      profile = 'strong';
                    }
                    if (code === 'service_not_rendered') desc = 'Customer claims digital subscription not delivered.';
                    if (code === 'product_not_as_described') desc = 'Product materially different from advertisement.';
                    if (code === 'duplicate_transaction') desc = 'Customer disputes double billing.';
                    setCustomForm(prev => ({
                      ...prev,
                      reason_code: code,
                      reason_description: desc,
                      evidence_profile: profile,
                    }));
                  }}
                >
                  <option value="product_not_received">product_not_received (Goods Non-Delivery)</option>
                  <option value="unauthorized_transaction">unauthorized_transaction (Fraud / Stolen Card)</option>
                  <option value="service_not_rendered">service_not_rendered (SaaS / Digital Service)</option>
                  <option value="product_not_as_described">product_not_as_described (Quality / Defect)</option>
                  <option value="duplicate_transaction">duplicate_transaction (Double Charge)</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Disputed Amount (₹ INR)</label>
                <input
                  type="number"
                  className="form-input"
                  min="1"
                  step="any"
                  placeholder="e.g. 14999"
                  value={customForm.amount_inr}
                  onChange={e => setCustomForm(prev => ({ ...prev, amount_inr: parseFloat(e.target.value) || 0 }))}
                  required
                />
              </div>

              {/* Row 2: Customer & Product */}
              <div className="form-group">
                <label className="form-label">Customer Name</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. Aditya Verma"
                  value={customForm.customer_name}
                  onChange={e => setCustomForm(prev => ({ ...prev, customer_name: e.target.value }))}
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">Customer Email</label>
                <input
                  type="email"
                  className="form-input"
                  placeholder="e.g. aditya.verma@example.com"
                  value={customForm.customer_email}
                  onChange={e => setCustomForm(prev => ({ ...prev, customer_email: e.target.value }))}
                  required
                />
              </div>

              <div className="form-group full-width">
                <label className="form-label">Product / Service Item Description</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. Wireless Noise Cancelling Headphones"
                  value={customForm.product_name}
                  onChange={e => setCustomForm(prev => ({ ...prev, product_name: e.target.value }))}
                  required
                />
              </div>

              <div className="form-group full-width">
                <label className="form-label">Dispute Narrative / Customer Claim Summary</label>
                <textarea
                  className="form-textarea"
                  rows={2}
                  placeholder="Describe the claim made by customer..."
                  value={customForm.reason_description}
                  onChange={e => setCustomForm(prev => ({ ...prev, reason_description: e.target.value }))}
                  required
                />
              </div>

              {/* Row 3: Shipping & Delivery Proof */}
              <div className="form-group">
                <label className="form-label">Delivery & Carrier Status</label>
                <select
                  className="form-select"
                  value={customForm.delivery_status}
                  onChange={e => setCustomForm(prev => ({ ...prev, delivery_status: e.target.value }))}
                >
                  <option value="delivered">Delivered (Physical Confirmation)</option>
                  <option value="in_transit">In Transit (Never Marked Delivered)</option>
                  <option value="returned_to_sender">Returned to Sender (Carrier RTS Conflict)</option>
                  <option value="none">None / Digital Fulfillment</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Proof of Delivery Type</label>
                <select
                  className="form-select"
                  value={customForm.proof_type}
                  onChange={e => setCustomForm(prev => ({ ...prev, proof_type: e.target.value }))}
                >
                  <option value="signature">Signed by Recipient + Photo Proof</option>
                  <option value="left_at_door">Left at Door (Unsigned)</option>
                  <option value="none">No Proof / Inconclusive</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Carrier Provider</label>
                <select
                  className="form-select"
                  value={customForm.carrier}
                  onChange={e => setCustomForm(prev => ({ ...prev, carrier: e.target.value }))}
                >
                  <option value="BlueDart">BlueDart Express</option>
                  <option value="Delhivery">Delhivery</option>
                  <option value="FedEx India">FedEx India</option>
                  <option value="DTDC">DTDC</option>
                  <option value="Ecom Express">Ecom Express</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Evidence Quality Profile</label>
                <select
                  className="form-select"
                  value={customForm.evidence_profile}
                  onChange={e => setCustomForm(prev => ({ ...prev, evidence_profile: e.target.value }))}
                >
                  <option value="strong">Strong (High Defense / Contest)</option>
                  <option value="weak">Weak (Ambiguous / Human Review)</option>
                  <option value="missing">Missing Evidence (Accept Loss)</option>
                  <option value="contradictory">Contradictory Evidence (Flag Conflict)</option>
                </select>
              </div>

              {/* Row 4: Checkbox Options */}
              <div className="form-group full-width custom-checkbox-row">
                <label className="simulator-checkbox-label">
                  <input
                    type="checkbox"
                    checked={customForm.auth_verified}
                    onChange={e => setCustomForm(prev => ({ ...prev, auth_verified: e.target.checked }))}
                  />
                  <span>3D Secure / OTP Verified at checkout</span>
                </label>

                <label className="simulator-checkbox-label">
                  <input
                    type="checkbox"
                    checked={customForm.device_known}
                    onChange={e => setCustomForm(prev => ({ ...prev, device_known: e.target.checked }))}
                  />
                  <span>Known Trusted Device Fingerprint</span>
                </label>

                <label className="simulator-checkbox-label">
                  <input
                    type="checkbox"
                    checked={customForm.has_refund}
                    onChange={e => setCustomForm(prev => ({ ...prev, has_refund: e.target.checked }))}
                  />
                  <span>Attach Prior Refund Record</span>
                </label>

                <label className="simulator-checkbox-label">
                  <input
                    type="checkbox"
                    checked={customForm.has_support_chat}
                    onChange={e => setCustomForm(prev => ({ ...prev, has_support_chat: e.target.checked }))}
                  />
                  <span>Include Customer Support Chat Logs</span>
                </label>
              </div>
            </div>

            <div className="simulator-custom-actions">
              <button
                type="submit"
                className="btn btn-primary"
                disabled={isSubmittingCustom}
              >
                {isSubmittingCustom ? (
                  <>
                    <Spinner size="small" />
                    <span>Simulating Custom Case...</span>
                  </>
                ) : (
                  <>
                    <IconBolt size={14} />
                    <span>Generate & Simulate Custom Case</span>
                  </>
                )}
              </button>
            </div>
          </form>
        )}

        {/* Modal Footer / Reset Environment */}
        <div className="simulator-footer">
          <div className="simulator-footer-left">
            {!confirmClearOpen ? (
              <button
                type="button"
                className="btn btn-outline-danger btn-sm"
                onClick={() => setConfirmClearOpen(true)}
              >
                <IconTrash size={14} />
                <span>Clear All Cases (Clean Slate)</span>
              </button>
            ) : (
              <div className="simulator-confirm-clear">
                <span className="confirm-clear-text">Purge all active & historical cases?</span>
                <button
                  type="button"
                  className="btn btn-danger btn-sm"
                  disabled={isClearing}
                  onClick={handleClearAll}
                >
                  {isClearing ? <Spinner size="small" /> : 'Yes, Delete All'}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => setConfirmClearOpen(false)}
                >
                  Cancel
                </button>
              </div>
            )}
          </div>

          <div className="simulator-footer-right">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
