import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useParams, NavLink } from 'react-router-dom';
import { 
  fetchCase, 
  investigateCase, 
  reviewCase, 
  submitCase, 
  streamInvestigation 
} from '../api/client';
import { useModel } from '../context/ModelContext';
import { Badge, getStatusBadgeType } from '../components/Badge';
import { DeadlineBadge } from '../components/DeadlineBadge';
import { Spinner } from '../components/Spinner';
import { EvidenceItem } from '../components/EvidenceItem';
import { ContradictionAlert } from '../components/ContradictionAlert';
import { TimelineEvent } from '../components/TimelineEvent';
import { EmptyState } from '../components/EmptyState';
import { ResponsePackageCard } from '../components/ResponsePackageCard';
import { 
  IconArrowLeft, 
  IconBolt, 
  IconCheck, 
  IconX, 
  IconSend, 
  IconRefreshCw, 
  IconTarget, 
  IconLayers, 
  IconFileText, 
  IconShield,
  IconClock,
  IconAlertTriangle,
  IconCopy
} from '../components/Icons';

export function CaseDetailPage() {
  const { caseId } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [liveEvents, setLiveEvents] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamModel, setStreamModel] = useState('');
  const [activeTab, setActiveTab] = useState('overview');
  const [evidenceFilter, setEvidenceFilter] = useState('all');
  const [evidenceCategory, setEvidenceCategory] = useState('all');
  const [copiedField, setCopiedField] = useState(null);
  const eventSourceRef = useRef(null);
  const { selectedModel } = useModel();

  const handleCopyText = (text, fieldName) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    setCopiedField(fieldName);
    setTimeout(() => setCopiedField(null), 1800);
  };

  const evidenceCategories = useMemo(() => {
    const list = data?.evidence || [];
    if (list.length === 0) return [];
    return Array.from(new Set(list.map((e) => e.category).filter(Boolean)));
  }, [data?.evidence]);

  const filteredEvidence = useMemo(() => {
    const list = data?.evidence || [];
    return list.filter((e) => {
      if (evidenceFilter !== 'all' && e.status !== evidenceFilter) return false;
      if (evidenceCategory !== 'all' && e.category !== evidenceCategory) return false;
      return true;
    });
  }, [data?.evidence, evidenceFilter, evidenceCategory]);

  const load = useCallback(async (isInitial = false) => {
    if (isInitial) setLoading(true);
    try {
      const d = await fetchCase(caseId);
      setData(d);
    } catch (e) {
      console.error('Failed to fetch case detail:', e);
    }
    if (isInitial) setLoading(false);
  }, [caseId]);

  useEffect(() => {
    load(true);
  }, [load]);

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  const startLiveInvestigation = () => {
    setLiveEvents([]);
    setIsStreaming(true);
    setActiveTab('defense');
    setStreamModel(selectedModel);
    const es = streamInvestigation(
      caseId,
      (event) => {
        setLiveEvents((prev) => [...prev, event]);
        if (event.type === 'done' || event.type === 'error') {
          setIsStreaming(false);
          load(false);
        }
      },
      selectedModel
    );
    eventSourceRef.current = es;
  };

  const handleAction = async (action) => {
    setActionLoading(true);
    try {
      if (action === 'investigate') {
        await investigateCase(caseId, selectedModel);
      } else if (action === 'approve') {
        if (data?.case?.status !== 'approved') {
          await reviewCase(caseId, 'approve', 'Approved & Submitted to Razorpay');
        }
        await submitCase(caseId);
      } else if (action === 'reject') {
        await reviewCase(caseId, 'reject', 'Accepted dispute loss');
      } else if (action === 'submit') {
        await submitCase(caseId);
      }
      await load(false);
    } catch (e) {
      alert(`Action error: ${e.message}`);
    }
    setActionLoading(false);
  };

  if (loading && !data) {
    return (
      <div className="page-center">
        <Spinner />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="page-center">
        <EmptyState 
          title="Case Not Found"
          description={`Dispute with ID ${caseId} does not exist in the database.`}
        />
      </div>
    );
  }

  const { case: caseInfo, evidence, timeline, contradictions, assessment, response_draft: responseDraft, audit } = data;
  const amountFormatted = `₹${((caseInfo.amount || 0) / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;

  const availableEvidence = evidence?.filter((e) => e.status === 'available') || [];
  const coveragePct = evidence?.length 
    ? Math.round((availableEvidence.length / evidence.length) * 100) 
    : 0;

  return (
    <div className="page">
      {/* Top Header */}
      <header className="case-header">
        <div className="case-header-left">
          <NavLink to="/" className="back-link">
            <IconArrowLeft className="back-link-icon" />
            <span>Back to Disputes</span>
          </NavLink>
          <h1>{caseInfo.case_id}</h1>
          <Badge type={getStatusBadgeType(caseInfo.status)}>
            {caseInfo.status.toUpperCase()}
          </Badge>
          <DeadlineBadge respondBy={caseInfo.respond_by} />
        </div>

        <div className="case-header-right">
          <span className="case-amount">{amountFormatted}</span>
          <span className="case-reason">{caseInfo.reason_code || 'Product Not Received'}</span>
        </div>
      </header>

      {/* Action Toolbar — Streamlined & Minimal */}
      <div className="case-action-bar">
        <div className="case-action-bar-left">
          {caseInfo.status === 'created' && (
            <button 
              type="button" 
              className="btn btn-primary btn-sm" 
              onClick={startLiveInvestigation} 
              disabled={isStreaming}
            >
              <IconBolt size={14} />
              <span>{isStreaming ? 'Investigating...' : 'Start Investigation'}</span>
            </button>
          )}

          {(caseInfo.status === 'under_review' || caseInfo.status === 'draft_ready') && (
            <>
              <button 
                type="button" 
                className="btn btn-success btn-sm" 
                onClick={() => handleAction('approve')} 
                disabled={actionLoading}
              >
                <IconCheck size={14} />
                <span>Approve Contest</span>
              </button>
              <button 
                type="button" 
                className="btn btn-outline btn-sm" 
                onClick={() => handleAction('reject')} 
                disabled={actionLoading}
                style={{ color: 'var(--color-danger)', borderColor: 'var(--color-danger-border)' }}
              >
                <IconX size={14} />
                <span>Accept Loss</span>
              </button>
            </>
          )}

          {caseInfo.status === 'approved' && (
            <button 
              type="button" 
              className="btn btn-primary btn-sm" 
              onClick={() => handleAction('submit')} 
              disabled={actionLoading}
            >
              <IconSend size={14} />
              <span>Submit to Razorpay</span>
            </button>
          )}

          {caseInfo.status === 'submitted' && (
            <div className="assessment-submitted-badge" style={{ padding: '6px 12px', fontSize: '12px' }}>
              <IconCheck size={13} />
              <span>Contested at Gateway</span>
            </div>
          )}
        </div>

        <div className="case-action-bar-right">
          <button 
            type="button" 
            className="btn btn-outline btn-sm"
            onClick={startLiveInvestigation}
            disabled={isStreaming}
            title="Re-run evidence investigation"
          >
            <IconRefreshCw size={13} className={isStreaming ? 'spin' : ''} />
            <span>{isStreaming ? 'Streaming...' : 'Re-analyze'}</span>
          </button>

          <span className="active-model-tag" style={{ margin: 0, fontSize: '11px' }}>
            {selectedModel}
          </span>
        </div>
      </div>

      {/* Streamlined Minimal Workspace Navigation */}
      <nav className="case-tabs" aria-label="Investigation Workspaces">
        <button
          type="button"
          className={`case-tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          <IconTarget className="case-tab-icon" />
          <span>Overview</span>
        </button>

        <button
          type="button"
          className={`case-tab ${activeTab === 'evidence' ? 'active' : ''}`}
          onClick={() => setActiveTab('evidence')}
        >
          <IconLayers className="case-tab-icon" />
          <span>Evidence</span>
          <span className="case-tab-badge">{evidence?.length || 0}</span>
        </button>

        <button
          type="button"
          className={`case-tab ${activeTab === 'defense' ? 'active' : ''}`}
          onClick={() => setActiveTab('defense')}
        >
          <IconFileText className="case-tab-icon" />
          <span>Rebuttal & Trace</span>
          {isStreaming && <span className="live-pulse-dot" />}
        </button>
      </nav>

      {/* TAB 1: Overview & Bounded Decision */}
      {activeTab === 'overview' && (
        <div>
          {/* Contradiction Warning Banner if Cross-Source Conflicts Exist */}
          {contradictions?.length > 0 && (
            <div 
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                background: 'rgba(239, 68, 68, 0.12)',
                border: '1px solid var(--color-danger-border)',
                borderRadius: 'var(--radius-md)',
                padding: '14px 18px',
                marginBottom: 'var(--space-4)',
                cursor: 'pointer'
              }}
              onClick={() => setActiveTab('evidence')}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <IconAlertTriangle size={20} style={{ color: 'var(--color-danger)', flexShrink: 0 }} />
                <div>
                  <div style={{ color: 'var(--color-danger)', fontWeight: 700, fontSize: '14px' }}>
                    {contradictions.length} Cross-Source Contradiction{contradictions.length > 1 ? 's' : ''} Detected
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: 2 }}>
                    Conflicting claims identified across carrier and merchant records. Review required before contesting.
                  </div>
                </div>
              </div>
              <button type="button" className="btn btn-outline-danger btn-sm" style={{ flexShrink: 0 }}>
                View Conflicts &rarr;
              </button>
            </div>
          )}

          {/* Unified Dispute Dossier Card */}
          <div className="card dispute-dossier-card" style={{ marginBottom: 'var(--space-4)' }}>
            <div className="dossier-claim-row">
              <div className="dossier-claim-header">
                <span className="dossier-claim-title">Customer Dispute Claim</span>
                <span className="dossier-phase-pill">
                  Phase: <strong>{caseInfo.dispute_phase || 'chargeback'}</strong>
                </span>
              </div>
              <div className="dossier-claim-quote">
                "{caseInfo.reason_description || 'Product not received by customer. Delivery status disputed.'}"
              </div>
            </div>

            <div className="dossier-identifiers-grid">
              <div className="dossier-id-box">
                <span className="dossier-id-label">Gateway Dispute ID</span>
                <div className="dossier-id-val-row">
                  <code>{caseInfo.rzp_dispute_id || 'disp_unassigned'}</code>
                  <button
                    type="button"
                    className="history-copy-btn"
                    onClick={() => handleCopyText(caseInfo.rzp_dispute_id || '', 'dispute')}
                    title="Copy Dispute ID"
                  >
                    {copiedField === 'dispute' ? <IconCheck size={11} /> : <IconCopy size={11} />}
                  </button>
                </div>
              </div>

              <div className="dossier-id-box">
                <span className="dossier-id-label">Payment ID</span>
                <div className="dossier-id-val-row">
                  <code>{caseInfo.rzp_payment_id || 'pay_unassigned'}</code>
                  <button
                    type="button"
                    className="history-copy-btn"
                    onClick={() => handleCopyText(caseInfo.rzp_payment_id || '', 'payment')}
                    title="Copy Payment ID"
                  >
                    {copiedField === 'payment' ? <IconCheck size={11} /> : <IconCopy size={11} />}
                  </button>
                </div>
              </div>

              <div className="dossier-id-box">
                <span className="dossier-id-label">Order Reference</span>
                <div className="dossier-id-val-row">
                  <code>{caseInfo.rzp_order_id || 'order_unassigned'}</code>
                  <button
                    type="button"
                    className="history-copy-btn"
                    onClick={() => handleCopyText(caseInfo.rzp_order_id || '', 'order')}
                    title="Copy Order ID"
                  >
                    {copiedField === 'order' ? <IconCheck size={11} /> : <IconCopy size={11} />}
                  </button>
                </div>
              </div>

              <div className="dossier-id-box">
                <span className="dossier-id-label">Disputed Value</span>
                <div className="dossier-id-val-highlight">
                  {amountFormatted}
                </div>
              </div>

              {caseInfo.reviewed_by && (
                <div className="dossier-id-box">
                  <span className="dossier-id-label">Analyst Sign-off</span>
                  <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-heading)' }}>
                    {caseInfo.reviewed_by}
                    {caseInfo.reviewed_at && (
                      <span style={{ display: 'block', fontSize: '10px', color: 'var(--text-muted)', fontWeight: 400, marginTop: 1 }}>
                        {new Date(caseInfo.reviewed_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Enterprise Investigation Assessment & Forensic Matrix Card */}
          <div className="assessment-card">
            {/* Header: Recommendation & Confidence Metrics */}
            <div className="assessment-header">
              <div className="assessment-verdict-wrap">
                <Badge
                  type={
                    assessment?.recommendation === 'contest'
                      ? 'success'
                      : assessment?.recommendation === 'accept_loss'
                        ? 'danger'
                        : 'warning'
                  }
                  size="lg"
                >
                  {assessment?.recommendation === 'contest'
                    ? 'RECOMMENDED: CONTEST DISPUTE'
                    : assessment?.recommendation === 'accept_loss'
                      ? 'RECOMMENDED: CONCEDE LOSS'
                      : 'HUMAN REVIEW REQUIRED'}
                </Badge>
                <div>
                  <div className="assessment-verdict-title">
                    {assessment?.recommendation === 'accept_loss'
                      ? 'Concede chargeback to prevent non-refundable arbitration penalties'
                      : assessment?.recommendation === 'human_review'
                        ? 'Evidence conflicts or unverified delivery proofs require review'
                        : 'Sufficient verified proof to defend merchant claim'}
                  </div>
                  <div className="assessment-verdict-desc">
                    {assessment?.recommendation === 'accept_loss'
                      ? 'Key proof of delivery or authorization is missing. Defending risks a non-refundable ₹1,500 gateway fee.'
                      : assessment?.recommendation === 'human_review'
                        ? 'Cross-source records have missing signatures or unverified timestamps that warrant investigator authorization.'
                        : 'Customer claim is countered by verified fulfillment and authenticated checkout records.'}
                  </div>
                </div>
              </div>

              <div className="assessment-stats-grid">
                <div className="assessment-stat-item">
                  <div className="assessment-stat-label">Win Confidence</div>
                  <div className="assessment-stat-val" style={{ color: (assessment?.score ?? 0) >= 0.7 ? 'var(--color-success)' : 'var(--color-warning)' }}>
                    {assessment?.score != null ? `${(assessment.score * 100).toFixed(0)}%` : '—'}
                  </div>
                </div>
                <div className="assessment-stat-item">
                  <div className="assessment-stat-label">Win Strength</div>
                  <div className="assessment-stat-val" style={{ color: 'var(--brand-primary)' }}>
                    {assessment?.strength ? assessment.strength.toUpperCase() : 'MEDIUM'}
                  </div>
                </div>
                <div className="assessment-stat-item">
                  <div className="assessment-stat-label">Evidence Verified</div>
                  <div className="assessment-stat-val">
                    {availableEvidence.length} / {evidence?.length || 0} <span style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 500 }}>({coveragePct}%)</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Forensic Canonical Evidence Matrix */}
            <div className="assessment-matrix">
              <div className="assessment-section-title">Forensic Evidence Verification Matrix</div>
              {evidence && evidence.length > 0 ? (
                <div className="assessment-table-wrapper">
                  <table className="assessment-table">
                    <thead>
                      <tr>
                        <th style={{ width: '140px' }}>Category</th>
                        <th style={{ width: '200px' }}>Source Record</th>
                        <th style={{ width: '130px' }}>Verification</th>
                        <th>Evidentiary Finding</th>
                      </tr>
                    </thead>
                    <tbody>
                      {evidence.map((ev) => (
                        <tr key={ev.evidence_id}>
                          <td className="cell-category">{ev.category?.toUpperCase()}</td>
                          <td className="cell-source">
                            <code>{ev.source_system}</code>
                            {ev.source_record_id && (
                              <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginLeft: 6 }}>
                                ({ev.source_record_id})
                              </span>
                            )}
                          </td>
                          <td>
                            <Badge
                              type={
                                ev.status === 'available'
                                  ? 'success'
                                  : ev.status === 'unverified'
                                    ? 'warning'
                                    : ev.status === 'missing'
                                      ? 'danger'
                                      : 'neutral'
                              }
                            >
                              {ev.status === 'available'
                                ? 'Verified'
                                : ev.status === 'unverified'
                                  ? 'Attention'
                                  : ev.status === 'missing'
                                    ? 'Missing'
                                    : 'Not Applicable'}
                            </Badge>
                          </td>
                          <td className="cell-summary">{ev.summary}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <EmptyState
                  title="No Evidence Gathered"
                  description="Run an investigation to gather cross-source records from payments, carrier, and CRM."
                />
              )}
            </div>

            {/* Bounded Authority Action Bar */}
            <div className="assessment-footer">
              <div className="assessment-footer-text">
                <div className="assessment-footer-label">Bounded Authority Policy</div>
                <div className="assessment-footer-desc">
                  RAVEN recommends an action based on gathered records. Dispute submission to gateway is bounded to human authorization.
                </div>
              </div>

              <div className="assessment-footer-actions">
                {caseInfo.status === 'under_review' && (
                  <>
                    <button
                      type="button"
                      className="btn btn-outline"
                      onClick={() => handleAction('reject')}
                      disabled={actionLoading}
                      style={{ color: 'var(--color-danger)', borderColor: 'var(--color-danger-border)' }}
                    >
                      <IconX size={14} />
                      <span>Accept Dispute Loss</span>
                    </button>

                    <button
                      type="button"
                      className="btn btn-success"
                      onClick={() => handleAction('approve')}
                      disabled={actionLoading}
                    >
                      <IconCheck size={14} />
                      <span>Approve & Authorize Contest</span>
                    </button>
                  </>
                )}

                {caseInfo.status === 'approved' && (
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => handleAction('submit')}
                    disabled={actionLoading}
                  >
                    <IconSend size={14} />
                    <span>Submit Contest to Razorpay</span>
                  </button>
                )}

                {caseInfo.status === 'submitted' && (
                  <div className="assessment-submitted-badge">
                    <IconCheck size={14} />
                    <span>Contest Dispatched to Razorpay Gateway • Bank Review in Progress</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: Unified Evidence & Chronology */}
      {activeTab === 'evidence' && (
        <div>
          <ContradictionAlert contradictions={contradictions} />

          <div className="two-col-grid">
            {/* Left Column: Canonical Evidence Items */}
            <section className="card">
              <div className="table-toolbar">
                <h2 className="card-title" style={{ margin: 0, borderBottom: 'none' }}>
                  Canonical Evidence ({evidence?.length || 0})
                </h2>
              </div>

              {/* Canonical Evidence Filter Toolbar */}
              {evidence && evidence.length > 0 && (
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 'var(--space-3)', alignItems: 'center' }}>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginRight: 4 }}>Filter:</span>
                  {['all', 'available', 'missing', 'unverified'].map((st) => {
                    const count = st === 'all' ? evidence.length : evidence.filter((e) => e.status === st).length;
                    return (
                      <button
                        key={st}
                        type="button"
                        className={`btn btn-xs ${evidenceFilter === st ? 'btn-primary' : 'btn-outline'}`}
                        style={{ padding: '2px 8px', fontSize: '11px', textTransform: 'capitalize' }}
                        onClick={() => setEvidenceFilter(st)}
                      >
                        {st} ({count})
                      </button>
                    );
                  })}

                  {evidenceCategories.length > 1 && (
                    <>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginLeft: 8, marginRight: 4 }}>Category:</span>
                      <select
                        className="history-sort-select"
                        value={evidenceCategory}
                        onChange={(e) => setEvidenceCategory(e.target.value)}
                        style={{ fontSize: '11px', padding: '2px 8px', height: '24px' }}
                      >
                        <option value="all">All Categories ({evidence.length})</option>
                        {evidenceCategories.map((cat) => (
                          <option key={cat} value={cat}>{cat}</option>
                        ))}
                      </select>
                    </>
                  )}
                </div>
              )}

              {filteredEvidence && filteredEvidence.length > 0 ? (
                <div className="evidence-list">
                  {filteredEvidence.map((e) => (
                    <EvidenceItem key={e.evidence_id} evidence={e} />
                  ))}
                </div>
              ) : evidence && evidence.length > 0 ? (
                <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
                  No evidence items match the selected filter.
                  <div style={{ marginTop: '8px' }}>
                    <button type="button" className="btn btn-outline btn-xs" onClick={() => { setEvidenceFilter('all'); setEvidenceCategory('all'); }}>
                      Reset Filters
                    </button>
                  </div>
                </div>
              ) : (
                <EmptyState 
                  title="No Evidence Gathered"
                  description="Run an investigation to retrieve records from payments, carrier, and CRM."
                />
              )}
            </section>

            {/* Right Column: Timeline & System Audit */}
            <div>
              <section className="card" style={{ marginBottom: 'var(--space-4)' }}>
                <h2 className="card-title">
                  <IconClock className="card-title-icon" />
                  <span>Reconstructed Chronology</span>
                </h2>
                {timeline && timeline.length > 0 ? (
                  <div className="timeline">
                    {timeline.map((ev, i) => (
                      <TimelineEvent key={i} event={ev} />
                    ))}
                  </div>
                ) : (
                  <EmptyState 
                    title="No Chronological Events"
                    description="Timeline events will appear once investigation extracts timestamps."
                  />
                )}
              </section>

              <section className="card">
                <h2 className="card-title">
                  <IconShield className="card-title-icon" />
                  <span>Audit Trail</span>
                </h2>
                {audit && audit.length > 0 ? (
                  <div className="audit-list">
                    {audit.map((a, i) => (
                      <div key={i} className="audit-item">
                        <div className="audit-time">
                          {a.timestamp ? new Date(a.timestamp).toLocaleString() : ''}
                        </div>
                        <Badge type="info" icon={false}>{a.action}</Badge>
                        <div className="audit-actor">{a.actor}</div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyState 
                    title="No Audit Logs"
                    description="Actions taken on this dispute will be recorded here."
                  />
                )}
              </section>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: Defense Package & Live Agent Stream */}
      {activeTab === 'defense' && (
        <div className="two-col-grid">
          {/* Formal Legal Defense Package Card */}
          <ResponsePackageCard 
            caseData={data}
            responseDraft={responseDraft}
            onSubmitContest={() => handleAction('submit')}
            actionLoading={actionLoading}
          />

          {/* Live Agent Stream Trace */}
          <section className="card">
            <div className="table-toolbar">
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <h2 className="card-title" style={{ margin: 0, borderBottom: 'none' }}>
                  Live Agent Stream Trace
                </h2>
                {isStreaming && <Spinner size="sm" />}
              </div>
              <span className="active-model-tag">
                {streamModel || selectedModel}
              </span>
            </div>

            {liveEvents.length > 0 || isStreaming ? (
              <div className="live-panel">
                {liveEvents.map((ev, i) => (
                  <div key={i} className={`live-event live-event-${ev.type}`}>
                    <span className="live-event-icon">
                      {ev.type === 'step' ? '>' :
                       ev.type === 'evidence' ? (ev.data?.status === 'available' ? '✓' : '✕') :
                       ev.type === 'contradiction' ? '!' :
                       ev.type === 'thinking' ? '*' :
                       ev.type === 'result' ? '#' :
                       ev.type === 'done' ? '=' : '.'}
                    </span>
                    <span className="live-event-text">
                      {ev.type === 'step' && `Connecting to ${ev.data?.tool}... [${ev.data?.step}/${ev.data?.total}]`}
                      {ev.type === 'evidence' && `${ev.data?.category}: ${ev.data?.summary}`}
                      {ev.type === 'contradiction' && `CONFLICT: ${ev.data?.description}`}
                      {ev.type === 'thinking' && `THOUGHT: ${ev.data?.text || ev.data?.thought || ev.data?.message || (typeof ev.data === 'string' ? ev.data : JSON.stringify(ev.data))}`}
                      {ev.type === 'result' && `Confidence: ${ev.data?.score != null ? (ev.data.score * 100).toFixed(0) : 0}% | Recommendation: ${ev.data?.recommendation?.toUpperCase()}`}
                      {ev.type === 'done' && `Investigation completed successfully via ${ev.data?.model || selectedModel}.`}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState 
                title="No Active Stream"
                description="Start a live investigation to watch the autonomous evidence collection agent in real time."
                action={
                  <button type="button" className="btn btn-primary btn-sm" onClick={startLiveInvestigation}>
                    <IconBolt size={14} />
                    <span>Run Investigation</span>
                  </button>
                }
              />
            )}
          </section>
        </div>
      )}
    </div>
  );
}
