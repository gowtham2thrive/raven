import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchCase, reviewCase, submitCase } from '../api/client';
import { Badge, getStatusBadgeType } from './Badge';
import { DeadlineBadge } from './DeadlineBadge';
import { Spinner } from './Spinner';
import { TimelineEvent } from './TimelineEvent';
import { 
  IconX, 
  IconCheck, 
  IconExternalLink, 
  IconShieldCheck, 
  IconCheckCircle,
  IconCopy,
  IconFileText
} from './Icons';

export function DisputeDrawer({ caseId, onClose, onCaseUpdated }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [drawerTab, setDrawerTab] = useState('overview'); // 'overview' | 'rebuttal' | 'timeline'
  const navigate = useNavigate();

  useEffect(() => {
    if (!caseId) return;
    setLoading(true);
    fetchCase(caseId)
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [caseId]);

  if (!caseId) return null;

  const handleAction = async (action) => {
    setActionLoading(true);
    try {
      if (action === 'approve') {
        if (data?.case?.status !== 'approved') {
          await reviewCase(caseId, 'approve', 'Approved & Submitted via Quick Drawer');
        }
        await submitCase(caseId);
      } else if (action === 'reject') {
        await reviewCase(caseId, 'reject', 'Accepted loss via Quick Drawer');
      } else if (action === 'submit') {
        await submitCase(caseId);
      }
      const updated = await fetchCase(caseId);
      setData(updated);
      if (onCaseUpdated) onCaseUpdated();
    } catch (e) {
      alert(`Action failed: ${e.message}`);
    }
    setActionLoading(false);
  };

  const caseInfo = data?.case;
  const assessment = data?.assessment;
  const evidence = data?.evidence || [];
  const availableEvidence = evidence.filter(e => e.status === 'available');
  const missingEvidence = evidence.filter(e => e.status === 'missing');
  const conflictingEvidence = evidence.filter(e => e.status === 'conflicting');
  const coveragePct = evidence.length ? Math.round((availableEvidence.length / evidence.length) * 100) : 0;
  const reasonsList = assessment?.data?.reasons || [];
  const amountFormatted = caseInfo ? `₹${((caseInfo.amount || 0) / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : '—';

  return (
    <>
      {/* Backdrop blur overlay */}
      <div className="drawer-backdrop" onClick={onClose} aria-hidden="true" />

      {/* Slide-Over Drawer Container */}
      <aside className="dispute-drawer" aria-label="Dispute Quick Inspector">
        {/* Drawer Header */}
        <div className="drawer-header">
          <div className="drawer-header-left">
            <span className="drawer-case-id">{caseId}</span>
            {caseInfo && (
              <Badge type={getStatusBadgeType(caseInfo.status)}>
                {caseInfo.status.toUpperCase()}
              </Badge>
            )}
          </div>

          <button 
            type="button" 
            className="drawer-close-btn" 
            onClick={onClose}
            aria-label="Close Inspector"
          >
            <IconX size={18} />
          </button>
        </div>

        {loading ? (
          <div className="page-center" style={{ minHeight: 300 }}>
            <Spinner />
          </div>
        ) : !data ? (
          <div className="drawer-body">
            <p style={{ color: 'var(--text-muted)' }}>Could not load dispute details.</p>
          </div>
        ) : (
          <div className="drawer-body">
            {/* Amount & Deadline Bar */}
            <div className="drawer-amount-row">
              <div>
                <div className="drawer-amount-label">Disputed Amount</div>
                <div className="drawer-amount-value">{amountFormatted}</div>
              </div>
              <div className="drawer-verdict-right">
                <div className="drawer-amount-label">Response Deadline</div>
                <DeadlineBadge respondBy={caseInfo.respond_by} />
              </div>
            </div>

            {/* Segmented Tabs */}
            <nav className="drawer-tabs" aria-label="Inspection Tabs">
              <button
                type="button"
                className={`drawer-tab ${drawerTab === 'overview' ? 'active' : ''}`}
                onClick={() => setDrawerTab('overview')}
              >
                <span>Overview</span>
              </button>
              <button
                type="button"
                className={`drawer-tab ${drawerTab === 'rebuttal' ? 'active' : ''}`}
                onClick={() => setDrawerTab('rebuttal')}
              >
                <span>Rebuttal</span>
                {data?.response_draft && <span className="drawer-tab-dot" />}
              </button>
              <button
                type="button"
                className={`drawer-tab ${drawerTab === 'timeline' ? 'active' : ''}`}
                onClick={() => setDrawerTab('timeline')}
              >
                <span>Chronology</span>
                {data?.timeline?.length > 0 && <span className="drawer-tab-count">{data.timeline.length}</span>}
              </button>
            </nav>

            {/* TAB 1: OVERVIEW — structured into 3 distinct cards */}
            {drawerTab === 'overview' && (
              <>
                {/* Section 1: Customer Claim */}
                <div className="drawer-claim-box">
                  <div className="drawer-section-title">Customer Claim</div>
                  <div className="drawer-claim-quote">
                    "{caseInfo.reason_description || '—'}"
                  </div>
                  <div className="drawer-claim-meta">
                    Reason Code: <strong>{caseInfo.reason_code || '—'}</strong>
                  </div>
                </div>

                {/* Section 2: AI Verdict */}
                <div className="drawer-verdict-card">
                  <div className="drawer-verdict-row">
                    <div>
                      <div className="drawer-verdict-label">AI Investigation Verdict</div>
                      <div className="drawer-verdict-badge-wrap">
                        <span
                          className={`hero-rec-badge ${
                            assessment?.recommendation === 'accept_loss'
                              ? 'hero-rec-accept'
                              : assessment?.recommendation === 'human_review'
                                ? 'hero-rec-review'
                                : 'hero-rec-contest'
                          }`}
                          style={{ fontSize: '14px', padding: '3px 10px' }}
                        >
                          {assessment?.recommendation ? assessment.recommendation.toUpperCase() : 'PENDING'}
                        </span>
                      </div>
                    </div>

                    <div className="drawer-verdict-right">
                      <div className="drawer-verdict-label">Win Confidence</div>
                      <div className="drawer-score-val">
                        {assessment?.score != null ? `${(assessment.score * 100).toFixed(0)}%` : '—'}
                      </div>
                    </div>
                  </div>

                  {/* Key Defense Proofs */}
                  {reasonsList.length > 0 && (
                    <div className="drawer-reasons-list">
                      <div className="drawer-section-title" style={{ color: '#94A3B8' }}>Verified Defense Proofs</div>
                      {reasonsList.slice(0, 3).map((r, i) => (
                        <div key={i} className="drawer-reason-item">
                          <IconCheckCircle className="drawer-reason-icon" size={14} />
                          <span>{r}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Section 3: Evidence Coverage */}
                <div className="drawer-section-card">
                  <div className="drawer-section-title">Evidence Coverage</div>
                  <div className="drawer-coverage-row">
                    <span>Sources Verified</span>
                    <span className="drawer-coverage-value">
                      {coveragePct}% ({availableEvidence.length}/{evidence.length} records)
                    </span>
                  </div>
                  <div className="coverage-bar-track">
                    <div className="coverage-bar-fill" style={{ width: `${coveragePct}%` }} />
                  </div>
                  {evidence.length > 0 && (
                    <div className="drawer-evidence-breakdown">
                      <span className="drawer-evidence-stat">
                        <span className="drawer-evidence-dot available" />
                        {availableEvidence.length} available
                      </span>
                      {missingEvidence.length > 0 && (
                        <span className="drawer-evidence-stat">
                          <span className="drawer-evidence-dot missing" />
                          {missingEvidence.length} missing
                        </span>
                      )}
                      {conflictingEvidence.length > 0 && (
                        <span className="drawer-evidence-stat">
                          <span className="drawer-evidence-dot conflicting" />
                          {conflictingEvidence.length} conflicting
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </>
            )}

            {/* TAB 2: REBUTTAL */}
            {drawerTab === 'rebuttal' && (
              <div className="drawer-response-box">
                <div className="drawer-response-header">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <IconFileText size={15} color="var(--brand-primary)" />
                    <span className="drawer-section-title" style={{ margin: 0, fontSize: '12px' }}>
                      Compiled Defense Rebuttal
                    </span>
                  </div>
                  {data?.response_draft && (
                    <button
                      type="button"
                      className="btn btn-outline btn-xs"
                      onClick={() => {
                        navigator.clipboard.writeText(data.response_draft);
                        setCopied(true);
                        setTimeout(() => setCopied(false), 2000);
                      }}
                      title="Copy full rebuttal text"
                    >
                      {copied ? <IconCheck size={12} /> : <IconCopy size={12} />}
                      <span>{copied ? 'Copied' : 'Copy Rebuttal'}</span>
                    </button>
                  )}
                </div>
                {data?.response_draft ? (
                  <div className="drawer-response-content">
                    {data.response_draft.split('\n\n').map((para, idx) => (
                      <p key={idx}>{para}</p>
                    ))}
                  </div>
                ) : (
                  <div className="drawer-empty-state">
                    No rebuttal draft compiled yet. Run an investigation to generate a defense rebuttal.
                  </div>
                )}
              </div>
            )}

            {/* TAB 3: CHRONOLOGY */}
            {drawerTab === 'timeline' && (
              <div className="drawer-timeline-scroll">
                {data?.timeline && data.timeline.length > 0 ? (
                  data.timeline.map((ev, i) => (
                    <TimelineEvent key={i} event={ev} />
                  ))
                ) : (
                  <div className="drawer-empty-state">
                    No chronology events extracted yet. Run an investigation to build timeline.
                  </div>
                )}
              </div>
            )}

            {/* Quick 1-Click Action Buttons */}
            <div className="drawer-actions-card">
              {['under_review', 'assessed', 'draft_ready'].includes(caseInfo.status) && (
                <div className="drawer-action-buttons-grid">
                  <button
                    type="button"
                    className="btn btn-success"
                    onClick={() => handleAction('approve')}
                    disabled={actionLoading}
                    style={{ flex: 1 }}
                  >
                    <IconCheck size={14} />
                    <span>Approve & Submit</span>
                  </button>

                  <button
                    type="button"
                    className="btn btn-outline"
                    onClick={() => handleAction('reject')}
                    disabled={actionLoading}
                    style={{ color: 'var(--color-danger)', borderColor: 'var(--color-danger-border)' }}
                  >
                    <IconX size={14} />
                    <span>Accept Loss</span>
                  </button>
                </div>
              )}

              {caseInfo.status === 'approved' && (
                <div className="drawer-action-buttons-grid">
                  <button
                    type="button"
                    className="btn btn-success"
                    onClick={() => handleAction('submit')}
                    disabled={actionLoading}
                    style={{ flex: 1 }}
                  >
                    <IconShieldCheck size={14} />
                    <span>Submit to Gateway</span>
                  </button>
                </div>
              )}

              {caseInfo.status === 'submitted' && (
                <div className="drawer-submitted-notice">
                  <IconShieldCheck size={16} color="#34D399" />
                  <span>Submitted to Razorpay Gateway (Under Review)</span>
                </div>
              )}

              {caseInfo.status === 'rejected' && (
                <div className="drawer-submitted-notice" style={{ borderColor: 'rgba(245, 158, 11, 0.2)', background: 'rgba(245, 158, 11, 0.06)' }}>
                  <IconX size={16} color="var(--color-warning)" />
                  <span>Loss Accepted — Arbitration Fee Saved</span>
                </div>
              )}

              {(caseInfo.status === 'won' || caseInfo.outcome === 'won') && (
                <div className="drawer-submitted-notice" style={{ borderColor: 'rgba(52, 211, 153, 0.3)', background: 'rgba(52, 211, 153, 0.08)' }}>
                  <IconShieldCheck size={16} color="#34D399" />
                  <span>Dispute Won — Revenue Recovered</span>
                </div>
              )}

              {(caseInfo.status === 'lost' || caseInfo.outcome === 'lost') && (
                <div className="drawer-submitted-notice" style={{ borderColor: 'rgba(239, 68, 68, 0.2)', background: 'rgba(239, 68, 68, 0.06)' }}>
                  <IconX size={16} color="var(--color-danger)" />
                  <span>Dispute Lost</span>
                </div>
              )}
            </div>

            {/* Link to Full Investigation Workspace */}
            <button
              type="button"
              className="drawer-full-workspace-btn"
              onClick={() => navigate(`/cases/${caseId}`)}
            >
              <span>Open Full Investigation Workspace</span>
              <IconExternalLink size={14} />
            </button>
          </div>
        )}
      </aside>
    </>
  );
}
