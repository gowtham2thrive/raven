import { useState, useMemo, useEffect } from 'react';
import { Badge, getStatusBadgeType } from './Badge';
import { DeadlineBadge } from './DeadlineBadge';
import { formatDeadline } from '../hooks/useDeadline';
import { 
  IconSearch, 
  IconDownload, 
  IconEye, 
  IconAlertTriangle, 
  IconCheck, 
  IconSend, 
  IconX,
  IconSparkles,
  IconCopy,
  IconCheckCircle,
  IconRefreshCw,
  IconClock,
  IconShield,
  IconTarget
} from './Icons';
import { formatCurrency } from '../utils/format';

/**
 * DisputeTable — Redesigned Dispute Queue with compact rows, 
 * accurate filter counts, confidence scores, and sandbox controls.
 */
export function DisputeTable({
  cases = [],
  selectedCaseId = null,
  onSelectCase = null,
  onQuickAction = null,
  onInvestigateCase = null,
  onBatchInvestigate = null,
  onBatchSubmit = null,
  onOpenSimulator = null,
  sandboxControls = null,
}) {
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState('urgent_first');
  const [selectedIds, setSelectedIds] = useState([]);
  const [copiedId, setCopiedId] = useState(null);
  const [isBatchInvestigating, setIsBatchInvestigating] = useState(false);
  const [isBatchSubmitting, setIsBatchSubmitting] = useState(false);
  const [investigatingCaseId, setInvestigatingCaseId] = useState(null);

  // Clear selection on Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && selectedIds.length > 0) {
        setSelectedIds([]);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedIds.length]);

  // Aggregate selected amount
  const selectedAmount = useMemo(() => {
    return cases
      .filter(c => selectedIds.includes(c.case_id))
      .reduce((sum, c) => sum + ((c.amount || 0) / 100), 0);
  }, [cases, selectedIds]);

  // Dynamic Tab Counts — aligned with visual verdict display
  const tabCounts = useMemo(() => {
    return {
      all: cases.length,
      needs_review: cases.filter(c => c.status === 'under_review').length,
      auto_contest: cases.filter(c => 
        c.status === 'under_review' && c.recommendation === 'contest'
      ).length,
      unprocessed: cases.filter(c => c.status === 'created').length,
      urgent: cases.filter(c => formatDeadline(c.respond_by).type === 'urgent').length,
    };
  }, [cases]);

  // Summary Metrics for stat cards
  const queueMetrics = useMemo(() => {
    const totalAtRisk = cases
      .filter(c => c.status !== 'submitted')
      .reduce((sum, c) => sum + ((c.amount || 0) / 100), 0);

    return {
      needsReview: tabCounts.needs_review,
      urgent: tabCounts.urgent,
      unprocessed: tabCounts.unprocessed,
      autoContest: tabCounts.auto_contest,
      atRisk: totalAtRisk,
    };
  }, [cases, tabCounts]);

  // Filter and Search
  const filteredCases = useMemo(() => {
    let result = cases.filter(c => {
      // Search matching
      if (search.trim()) {
        const q = search.toLowerCase();
        const matchId = (c.case_id || '').toLowerCase().includes(q);
        const matchPayment = (c.rzp_payment_id || '').toLowerCase().includes(q);
        const matchOrder = (c.rzp_order_id || '').toLowerCase().includes(q);
        const matchDispute = (c.rzp_dispute_id || '').toLowerCase().includes(q);
        const matchReason = (c.reason_description || c.reason_code || '').toLowerCase().includes(q);
        const matchAmount = String(c.amount || '').includes(q);
        const matchStatus = (c.status || '').toLowerCase().includes(q);
        if (!matchId && !matchPayment && !matchOrder && !matchDispute && !matchReason && !matchAmount && !matchStatus) {
          return false;
        }
      }

      // Filter matching — aligned with tabCounts logic
      if (filter === 'all') return true;
      if (filter === 'needs_review') return c.status === 'under_review';
      if (filter === 'auto_contest') return c.status === 'under_review' && c.recommendation === 'contest';
      if (filter === 'unprocessed') return c.status === 'created';
      if (filter === 'urgent') return formatDeadline(c.respond_by).type === 'urgent';
      return true;
    });

    // Sorting
    result.sort((a, b) => {
      if (sortBy === 'urgent_first') {
        const deadlineA = new Date(a.respond_by || 0).getTime();
        const deadlineB = new Date(b.respond_by || 0).getTime();
        return deadlineA - deadlineB;
      }
      if (sortBy === 'amount_desc') {
        return (b.amount || 0) - (a.amount || 0);
      }
      if (sortBy === 'amount_asc') {
        return (a.amount || 0) - (b.amount || 0);
      }
      if (sortBy === 'score_desc') {
        return (b.assessment_score || 0) - (a.assessment_score || 0);
      }
      if (sortBy === 'newest') {
        const dateA = new Date(a.created_at || 0).getTime();
        const dateB = new Date(b.created_at || 0).getTime();
        return dateB - dateA;
      }
      return 0;
    });

    return result;
  }, [cases, search, filter, sortBy]);

  // Copy to clipboard
  const handleCopy = (e, text, id) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1800);
  };

  // Toggle selection
  const toggleSelectRow = (e, caseId) => {
    e.stopPropagation();
    setSelectedIds(prev => 
      prev.includes(caseId) ? prev.filter(id => id !== caseId) : [...prev, caseId]
    );
  };

  const toggleSelectAll = () => {
    if (selectedIds.length === filteredCases.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(filteredCases.map(c => c.case_id));
    }
  };

  // 1-Click Single Investigation
  const handleRunInvestigation = async (e, caseId) => {
    e.stopPropagation();
    if (onInvestigateCase) {
      setInvestigatingCaseId(caseId);
      try {
        await onInvestigateCase(caseId);
      } finally {
        setInvestigatingCaseId(null);
      }
    }
  };

  // 1-Click Batch Investigation
  const handleTriggerBatchInvestigate = async () => {
    if (!onBatchInvestigate) return;
    setIsBatchInvestigating(true);
    try {
      await onBatchInvestigate();
    } finally {
      setIsBatchInvestigating(false);
    }
  };

  // 1-Click Batch Submit
  const handleTriggerBatchSubmit = async () => {
    if (!onBatchSubmit) return;
    setIsBatchSubmitting(true);
    try {
      await onBatchSubmit();
    } finally {
      setIsBatchSubmitting(false);
    }
  };

  // Bulk Actions on Selected
  const handleBulkInvestigate = async () => {
    if (!onInvestigateCase) return;
    setIsBatchInvestigating(true);
    try {
      for (const id of selectedIds) {
        await onInvestigateCase(id);
      }
      setSelectedIds([]);
    } finally {
      setIsBatchInvestigating(false);
    }
  };

  const handleBulkApprove = async () => {
    if (!onQuickAction) return;
    for (const id of selectedIds) {
      await onQuickAction(id, 'approve');
    }
    setSelectedIds([]);
  };

  const handleBulkReject = async () => {
    if (!onQuickAction) return;
    for (const id of selectedIds) {
      await onQuickAction(id, 'reject');
    }
    setSelectedIds([]);
  };

  // Real CSV Export
  const handleExportCSV = () => {
    if (filteredCases.length === 0) {
      alert('No disputes matching active filters to export.');
      return;
    }

    const headers = [
      'Case ID',
      'Dispute ID',
      'Payment ID',
      'Order ID',
      'Amount (INR)',
      'Reason Code',
      'Reason Description',
      'Status',
      'Recommendation',
      'Confidence Score',
      'Respond By',
      'Created At',
    ];

    const rows = filteredCases.map(c => [
      c.case_id || '',
      c.rzp_dispute_id || '',
      c.rzp_payment_id || '',
      c.rzp_order_id || '',
      ((c.amount || 0) / 100).toFixed(2),
      c.reason_code || '',
      (c.reason_description || '').replace(/"/g, '""'),
      c.status || '',
      c.recommendation || '',
      c.assessment_score != null ? `${(c.assessment_score * 100).toFixed(0)}%` : '',
      c.respond_by || '',
      c.created_at || '',
    ]);

    const csvContent = [
      headers.join(','),
      ...rows.map(r => r.map(field => `"${String(field).replace(/"/g, '""')}"`).join(',')),
    ].join('\r\n');

    const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `raven-active-disputes-${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  // Render AI Verdict & Score Pill — now includes confidence %
  const renderAIVerdict = (c) => {
    if (c.status === 'created') {
      return (
        <button
          type="button"
          className="queue-score-pill uninvestigated"
          onClick={(e) => handleRunInvestigation(e, c.case_id)}
          disabled={investigatingCaseId === c.case_id || isBatchInvestigating}
          title="Click to run instant AI investigation on this case"
          style={{ cursor: 'pointer', border: '1px dashed var(--brand-primary)' }}
        >
          {investigatingCaseId === c.case_id ? (
            <>
              <IconRefreshCw size={11} className="spinner-rotate" />
              <span>Analyzing...</span>
            </>
          ) : (
            <>
              <IconSparkles size={11} style={{ color: 'var(--brand-primary)' }} />
              <span style={{ color: 'var(--brand-primary)', fontWeight: 600 }}>Run AI Investigation</span>
            </>
          )}
        </button>
      );
    }

    const scoreLabel = c.assessment_score != null 
      ? `${(c.assessment_score * 100).toFixed(0)}%` 
      : null;

    if (c.recommendation === 'contest') {
      return (
        <div className="queue-score-pill contest" title="Strong merchant defense verified">
          <IconCheckCircle size={12} />
          <span>CONTEST{scoreLabel ? ` · ${scoreLabel}` : ''}</span>
        </div>
      );
    }

    if (c.recommendation === 'human_review' || c.status === 'under_review') {
      return (
        <div className="queue-score-pill review" title="Ambiguity or contradiction requires human decision">
          <IconAlertTriangle size={12} />
          <span>REVIEW{scoreLabel ? ` · ${scoreLabel}` : ''}</span>
        </div>
      );
    }

    if (c.recommendation === 'accept_loss') {
      return (
        <div className="queue-score-pill accept" title="Evidence weak: Accept to save arbitration fees">
          <IconX size={12} />
          <span>ACCEPT LOSS{scoreLabel ? ` · ${scoreLabel}` : ''}</span>
        </div>
      );
    }

    return (
      <Badge type={getStatusBadgeType(c.status)}>
        {c.status.replace('_', ' ')}
      </Badge>
    );
  };

  return (
    <div className="history-ledger-container">
      {/* Page-Level Summary Stats */}
      {cases.length > 0 && (
        <div className="queue-stats-strip">
          <div className="queue-stat-card">
            <div className="queue-stat-icon danger">
              <IconShield size={16} />
            </div>
            <div>
              <div className="queue-stat-value">{formatCurrency(queueMetrics.atRisk)}</div>
              <div className="queue-stat-label">Total At Risk</div>
            </div>
          </div>
          <div className="queue-stat-card">
            <div className="queue-stat-icon warning">
              <IconAlertTriangle size={16} />
            </div>
            <div>
              <div className="queue-stat-value">{queueMetrics.needsReview}</div>
              <div className="queue-stat-label">Needs Review</div>
            </div>
          </div>
          <div className="queue-stat-card">
            <div className="queue-stat-icon success">
              <IconCheckCircle size={16} />
            </div>
            <div>
              <div className="queue-stat-value">{queueMetrics.autoContest}</div>
              <div className="queue-stat-label">Contest Ready</div>
            </div>
          </div>
          <div className="queue-stat-card">
            <div className="queue-stat-icon info">
              <IconClock size={16} />
            </div>
            <div>
              <div className="queue-stat-value">{queueMetrics.urgent}</div>
              <div className="queue-stat-label">Urgent Deadline</div>
            </div>
          </div>
        </div>
      )}

      <section className="queue-card">
        {/* Header */}
        <div className="queue-header">
          <div className="queue-header-left">
            <h2 className="queue-title">
              Dispute Queue
              <span className="queue-count-pill">{cases.length}</span>
            </h2>
          </div>

          {/* Header Actions — includes sandbox controls */}
          <div className="queue-header-actions">
            {tabCounts.unprocessed > 0 && onBatchInvestigate && (
              <button
                type="button"
                className="btn-automation-primary"
                onClick={handleTriggerBatchInvestigate}
                disabled={isBatchInvestigating}
                title="Run automated 7-source evidence gathering on all new disputes"
              >
                {isBatchInvestigating ? <IconRefreshCw size={12} className="spinner-rotate" /> : <IconSparkles size={12} />}
                <span>Auto-Investigate ({tabCounts.unprocessed})</span>
              </button>
            )}

            {tabCounts.auto_contest > 0 && onBatchSubmit && (
              <button
                type="button"
                className="btn-automation-success"
                onClick={handleTriggerBatchSubmit}
                disabled={isBatchSubmitting}
                title="Submit strong verified defenses to Razorpay"
              >
                {isBatchSubmitting ? <IconRefreshCw size={12} className="spinner-rotate" /> : <IconSend size={12} />}
                <span>Submit Contests ({tabCounts.auto_contest})</span>
              </button>
            )}

            {onOpenSimulator && (
              <button
                type="button"
                className="btn btn-outline btn-sm"
                onClick={onOpenSimulator}
                title="Simulate case scenario"
              >
                <IconSparkles size={12} />
                <span>Simulate</span>
              </button>
            )}

            <button
              type="button"
              className="btn btn-outline btn-sm"
              onClick={handleExportCSV}
              disabled={filteredCases.length === 0}
              title="Export active dispute records to CSV"
            >
              <IconDownload size={13} />
              <span>Export</span>
            </button>

            {sandboxControls}
          </div>
        </div>

        {/* Multi-Select Floating Glass Bulk Action Dock */}
        {selectedIds.length > 0 && (
          <div className="queue-bulk-floating-dock" role="toolbar" aria-label="Bulk actions for selected disputes">
            <div className="queue-bulk-info">
              <span className="queue-bulk-badge">{selectedIds.length}</span>
              <span className="queue-bulk-count-text">
                {selectedIds.length === 1 ? '1 dispute selected' : `${selectedIds.length} disputes selected`}
              </span>
              {selectedAmount > 0 && (
                <span className="queue-bulk-amount-tag">
                  · <span className="queue-bulk-amount-val">{formatCurrency(selectedAmount)}</span> at risk
                </span>
              )}
            </div>

            <div className="queue-bulk-divider" />

            <div className="queue-bulk-actions">
              {onInvestigateCase && (
                <button
                  type="button"
                  className="queue-bulk-btn queue-bulk-btn-investigate"
                  onClick={handleBulkInvestigate}
                  disabled={isBatchInvestigating}
                  title="Run 7-source evidence investigation on selected disputes"
                >
                  {isBatchInvestigating ? (
                    <IconRefreshCw size={12} className="spinner-rotate" />
                  ) : (
                    <IconSparkles size={12} />
                  )}
                  <span>Investigate {selectedIds.length > 1 ? `(${selectedIds.length})` : ''}</span>
                </button>
              )}

              {onQuickAction && (
                <>
                  <button
                    type="button"
                    className="queue-bulk-btn queue-bulk-btn-approve"
                    onClick={handleBulkApprove}
                    title="Approve and submit verified evidence to Razorpay"
                  >
                    <IconCheck size={12} />
                    <span>Approve Contest</span>
                  </button>

                  <button
                    type="button"
                    className="queue-bulk-btn queue-bulk-btn-reject"
                    onClick={handleBulkReject}
                    title="Concede selected disputes and avoid arbitration fees"
                  >
                    <IconX size={12} />
                    <span>Accept Loss</span>
                  </button>
                </>
              )}

              <button
                type="button"
                className="queue-bulk-btn queue-bulk-btn-clear"
                onClick={() => setSelectedIds([])}
                title="Deselect all (Esc)"
              >
                <span>Clear</span>
              </button>
            </div>
          </div>
        )}

        {/* Toolbar: Search, Filters, Sort */}
        <div className="history-toolbar">
          <div className="history-search-wrap">
            <IconSearch className="history-search-icon" />
            <input
              type="text"
              className="history-search-input"
              placeholder="Search ID, customer, payment, reason..."
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            {search && (
              <button 
                type="button" 
                className="history-search-clear" 
                onClick={() => setSearch('')}
                title="Clear search"
              >
                <IconX size={12} />
              </button>
            )}
          </div>

          <div className="history-filter-pills">
            {[
              { id: 'all', label: 'All', count: tabCounts.all },
              { id: 'needs_review', label: 'Needs Review', count: tabCounts.needs_review },
              { id: 'auto_contest', label: 'Contest Ready', count: tabCounts.auto_contest },
              { id: 'unprocessed', label: 'Unprocessed', count: tabCounts.unprocessed },
              { id: 'urgent', label: 'Urgent', count: tabCounts.urgent },
            ].map(tab => (
              <button
                key={tab.id}
                type="button"
                className={`history-pill-btn ${filter === tab.id ? 'active' : ''}`}
                onClick={() => setFilter(tab.id)}
              >
                <span>{tab.label}</span>
                <span className="history-pill-count">{tab.count}</span>
              </button>
            ))}
          </div>

          <select 
            className="history-sort-select"
            value={sortBy}
            onChange={e => setSortBy(e.target.value)}
            title="Sort dispute records"
          >
            <option value="urgent_first">Urgent First</option>
            <option value="score_desc">Win Prob (High-Low)</option>
            <option value="amount_desc">Amount (High-Low)</option>
            <option value="amount_asc">Amount (Low-High)</option>
            <option value="newest">Newest</option>
          </select>
        </div>

        {/* Table or Empty State */}
        {cases.length === 0 ? (
          <div className="history-empty-card">
            <div className="history-empty-icon-ring">
              <IconSparkles size={22} />
            </div>
            <div className="history-empty-title">Dispute Queue is Clean</div>
            <div className="history-empty-desc">
              No chargebacks are currently pending. Simulate dispute scenarios to test the 7-source evidence correlation engine.
            </div>
            {onOpenSimulator && (
              <button 
                type="button" 
                className="btn btn-primary btn-sm" 
                onClick={onOpenSimulator}
              >
                <IconSparkles size={13} />
                <span>Simulate a Dispute Scenario</span>
              </button>
            )}
          </div>
        ) : filteredCases.length === 0 ? (
          <div className="history-empty-card">
            <div className="history-empty-icon-ring" style={{ background: 'var(--color-neutral-bg)', color: 'var(--text-secondary)' }}>
              <IconSearch size={22} />
            </div>
            <div className="history-empty-title">No matching disputes found</div>
            <div className="history-empty-desc">
              No disputes match your active search &quot;{search}&quot; or filter criteria.
            </div>
            <button 
              type="button" 
              className="btn btn-outline btn-sm"
              onClick={() => { setSearch(''); setFilter('all'); }}
            >
              <span>Reset Filters</span>
            </button>
          </div>
        ) : (
          <>
            {/* Desktop Table View (Visible on > 768px) */}
            <div className="history-table-wrap desktop-table-view">
              <table className="history-table">
                <thead>
                  <tr>
                    <th className="queue-checkbox-cell">
                      <input
                        type="checkbox"
                        className="queue-checkbox"
                        checked={selectedIds.length === filteredCases.length && filteredCases.length > 0}
                        onChange={toggleSelectAll}
                        title="Select all"
                      />
                    </th>
                    <th>Dispute & Ref</th>
                    <th>Customer Claim</th>
                    <th>Amount</th>
                    <th>AI Verdict & Confidence</th>
                    <th>Flags</th>
                    <th>Deadline</th>
                    <th style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredCases.map(c => {
                    const isSelected = selectedCaseId === c.case_id;
                    const isChecked = selectedIds.includes(c.case_id);
                    const isReviewNeeded = c.status === 'under_review';
                    const isUrgent = formatDeadline(c.respond_by).type === 'urgent';
                    const isCopied = copiedId === c.case_id;
                    const paymentRef = c.rzp_payment_id || `pay_${(c.case_id || '').replace('CASE-', '')}`;

                    return (
                      <tr 
                        key={c.case_id}
                        className={`history-row ${isSelected ? 'selected' : ''}`}
                        onClick={() => {
                          if (onSelectCase) onSelectCase(c.case_id);
                        }}
                      >
                        {/* Checkbox */}
                        <td className="queue-checkbox-cell" onClick={(e) => toggleSelectRow(e, c.case_id)}>
                          <input
                            type="checkbox"
                            className="queue-checkbox"
                            checked={isChecked}
                            onChange={(e) => toggleSelectRow(e, c.case_id)}
                          />
                        </td>

                        {/* Dispute ID & References */}
                        <td>
                          <div className="history-id-stack">
                            {(isReviewNeeded || isUrgent) && (
                              <span 
                                className="priority-pulse-indicator" 
                                title={isUrgent ? "Expiring soon" : "Needs review"} 
                              />
                            )}
                            <span className="history-case-id">{c.case_id}</span>
                            <button
                              type="button"
                              className={`history-copy-btn ${isCopied ? 'copied' : ''}`}
                              onClick={(e) => handleCopy(e, c.case_id, c.case_id)}
                              title={isCopied ? 'Copied!' : 'Copy Case ID'}
                            >
                              {isCopied ? <IconCheck size={11} /> : <IconCopy size={11} />}
                            </button>
                          </div>
                          <div className="history-refs-sub">
                            <span>{paymentRef}</span>
                            {c.rzp_order_id && <span> • {c.rzp_order_id}</span>}
                          </div>
                        </td>

                        {/* Customer Claim — reason code tag + real description */}
                        <td>
                          <div className="history-claim-title">
                            {c.reason_code ? (
                              <span className="reason-code-tag">
                                {c.reason_code.replace(/_/g, ' ')}
                              </span>
                            ) : (
                              <span className="reason-code-tag">Unknown</span>
                            )}
                          </div>
                          <div className="history-claim-desc" title={c.reason_description}>
                            {c.reason_description || '—'}
                          </div>
                        </td>

                        {/* Dispute Amount */}
                        <td className="history-amount-cell">
                          ₹{((c.amount || 0) / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </td>

                        {/* AI Verdict & Confidence Score */}
                        <td>
                          {renderAIVerdict(c)}
                        </td>

                        {/* Contradiction Flags */}
                        <td>
                          {(c.contradiction_count > 0) ? (
                            <span
                              className="contradiction-flag-badge"
                              title={`${c.contradiction_count} evidence conflict${c.contradiction_count > 1 ? 's' : ''} detected`}
                            >
                              <IconAlertTriangle size={11} />
                              <span>{c.contradiction_count} Conflict{c.contradiction_count > 1 ? 's' : ''}</span>
                            </span>
                          ) : c.status !== 'created' ? (
                            <span className="no-conflicts-badge" title="No evidence conflicts detected">
                              <IconCheckCircle size={11} />
                              <span>Clean</span>
                            </span>
                          ) : null}
                        </td>

                        {/* Deadline */}
                        <td>
                          <DeadlineBadge respondBy={c.respond_by} />
                        </td>

                        {/* Action Buttons */}
                        <td style={{ textAlign: 'right' }}>
                          <div style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
                            {/* Case in created state -> Run AI */}
                            {c.status === 'created' && onInvestigateCase && (
                              <button
                                type="button"
                                className="btn-row btn-row-investigate"
                                onClick={(e) => handleRunInvestigation(e, c.case_id)}
                                disabled={investigatingCaseId === c.case_id}
                                title="Run AI Evidence Investigation"
                              >
                                <IconSparkles size={11} />
                                <span>{investigatingCaseId === c.case_id ? 'Analyzing...' : 'Investigate'}</span>
                              </button>
                            )}

                            {/* Case in assessed, under_review, or draft_ready -> Approve / Loss */}
                            {(c.status === 'assessed' || c.status === 'under_review' || c.status === 'draft_ready') && onQuickAction && (
                              <>
                                <button
                                  type="button"
                                  className="btn-row btn-row-approve"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    onQuickAction(c.case_id, 'approve');
                                  }}
                                  title="Approve & Submit Defense"
                                >
                                  <IconCheck size={11} />
                                  <span>Approve</span>
                                </button>

                                <button
                                  type="button"
                                  className="btn-row btn-row-reject"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    onQuickAction(c.case_id, 'reject');
                                  }}
                                  title="Accept Dispute Loss (Save Arbitration Fees)"
                                >
                                  <IconX size={11} />
                                  <span>Loss</span>
                                </button>
                              </>
                            )}

                            {/* Case already approved -> Submit only (cannot reject after approval) */}
                            {c.status === 'approved' && onQuickAction && (
                              <button
                                type="button"
                                className="btn-row btn-row-approve"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onQuickAction(c.case_id, 'approve');
                                }}
                                title="Submit Contest to Razorpay"
                              >
                                <IconSend size={11} />
                                <span>Submit</span>
                              </button>
                            )}

                            {/* Inspect Drawer Button */}
                            <button
                              type="button"
                              className="history-action-btn"
                              onClick={(e) => {
                                e.stopPropagation();
                                if (onSelectCase) onSelectCase(c.case_id);
                              }}
                              title="Inspect evidence, chronology, and AI rebuttal package"
                            >
                              <IconEye size={12} />
                              <span>Inspect</span>
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Mobile Touch-Friendly Card View (Visible on <= 768px) */}
            <div className="mobile-cards-view">
              {filteredCases.map(c => {
                const isSelected = selectedCaseId === c.case_id;
                const isChecked = selectedIds.includes(c.case_id);
                const isReviewNeeded = c.status === 'under_review';
                const isUrgent = formatDeadline(c.respond_by).type === 'urgent';
                const isCopied = copiedId === c.case_id;
                const paymentRef = c.rzp_payment_id || `pay_${(c.case_id || '').replace('CASE-', '')}`;
                const amountFormatted = `₹${((c.amount || 0) / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;

                return (
                  <div
                    key={c.case_id}
                    className={`mobile-dispute-card ${isSelected ? 'selected' : ''} ${isUrgent ? 'urgent' : isReviewNeeded ? 'priority' : ''}`}
                    onClick={() => {
                      if (onSelectCase) onSelectCase(c.case_id);
                    }}
                  >
                    {/* Top Row: Checkbox, Case ID, Copy, Amount */}
                    <div className="mobile-card-top">
                      <div className="mobile-card-id-group" onClick={e => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          className="queue-checkbox"
                          checked={isChecked}
                          onChange={(e) => toggleSelectRow(e, c.case_id)}
                          aria-label={`Select ${c.case_id}`}
                        />
                        <span className="mobile-card-id">{c.case_id}</span>
                        <button
                          type="button"
                          className={`history-copy-btn ${isCopied ? 'copied' : ''}`}
                          onClick={(e) => handleCopy(e, c.case_id, c.case_id)}
                          title="Copy Case ID"
                        >
                          {isCopied ? <IconCheck size={12} /> : <IconCopy size={12} />}
                        </button>
                      </div>

                      <span className="mobile-card-amount">{amountFormatted}</span>
                    </div>

                    {/* Reference line */}
                    <div className="history-refs-sub" style={{ marginTop: '-4px' }}>
                      <span>{paymentRef}</span>
                      {c.rzp_order_id && <span> • {c.rzp_order_id}</span>}
                    </div>

                    {/* Customer Claim & Reason */}
                    <div className="mobile-card-claim">
                      <div className="mobile-card-reason">
                        {c.reason_code ? c.reason_code.replace(/_/g, ' ') : 'Unknown'}
                      </div>
                      <div className="mobile-card-desc">
                        {c.reason_description || '—'}
                      </div>
                    </div>

                    {/* AI Verdict, Flags & Deadline Badges */}
                    <div className="mobile-card-tags">
                      {renderAIVerdict(c)}
                      {(c.contradiction_count > 0) && (
                        <span
                          className="contradiction-flag-badge"
                          title={`${c.contradiction_count} evidence conflict${c.contradiction_count > 1 ? 's' : ''} detected`}
                        >
                          <IconAlertTriangle size={11} />
                          <span>{c.contradiction_count}</span>
                        </span>
                      )}
                      <DeadlineBadge respondBy={c.respond_by} />
                    </div>

                    {/* Touch Action Buttons */}
                    <div className="mobile-card-actions" onClick={e => e.stopPropagation()}>
                      {c.status === 'created' && onInvestigateCase && (
                        <button
                          type="button"
                          className="btn btn-sm btn-primary"
                          onClick={(e) => handleRunInvestigation(e, c.case_id)}
                          disabled={investigatingCaseId === c.case_id}
                        >
                          <IconSparkles size={13} />
                          <span>{investigatingCaseId === c.case_id ? 'Analyzing...' : 'Investigate'}</span>
                        </button>
                      )}

                      {(c.status === 'assessed' || c.status === 'under_review' || c.status === 'draft_ready') && onQuickAction && (
                        <>
                          <button
                            type="button"
                            className="btn btn-sm btn-success"
                            onClick={() => onQuickAction(c.case_id, 'approve')}
                          >
                            <IconCheck size={13} />
                            <span>Approve</span>
                          </button>

                          <button
                            type="button"
                            className="btn btn-sm btn-outline-danger"
                            onClick={() => onQuickAction(c.case_id, 'reject')}
                          >
                            <IconX size={13} />
                            <span>Loss</span>
                          </button>
                        </>
                      )}

                      {/* Approved -> Submit only */}
                      {c.status === 'approved' && onQuickAction && (
                        <button
                          type="button"
                          className="btn btn-sm btn-success"
                          onClick={() => onQuickAction(c.case_id, 'approve')}
                        >
                          <IconSend size={13} />
                          <span>Submit</span>
                        </button>
                      )}

                      <button
                        type="button"
                        className="btn btn-sm btn-outline"
                        onClick={() => {
                          if (onSelectCase) onSelectCase(c.case_id);
                        }}
                      >
                        <IconEye size={13} />
                        <span>Inspect</span>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
