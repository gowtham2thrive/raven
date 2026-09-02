import { useState, useMemo } from 'react';
import { Badge } from './Badge';
import { 
  IconSearch, 
  IconDownload, 
  IconEye, 
  IconSparkles,
  IconCopy,
  IconCheck,
  IconX,
  IconShield,
  IconTarget,
  IconActivity,
  IconClock
} from './Icons';
import { formatCurrency } from '../utils/format';

/**
 * Compute a human-readable relative time string from a date.
 * Returns strings like "3 days ago", "2 hours ago", "just now".
 */
function formatRelativeTime(dateStr) {
  if (!dateStr) return '';
  const now = new Date();
  const then = new Date(dateStr);
  const diffMs = now - then;
  if (diffMs < 0) return '';
  
  const diffMinutes = Math.floor(diffMs / 60000);
  if (diffMinutes < 1) return 'just now';
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 30) return `${diffDays}d ago`;
  
  const diffMonths = Math.floor(diffDays / 30);
  return `${diffMonths}mo ago`;
}

/**
 * DisputeHistoryTable — Settlement Ledger with summary metric cards,
 * improved outcome badges, and relative date hints.
 */
export function DisputeHistoryTable({
  cases = [],
  selectedCaseId = null,
  onSelectCase = null,
  onOpenSimulator = null,
  metrics = null,
}) {
  const [search, setSearch] = useState('');
  const [outcomeFilter, setOutcomeFilter] = useState('all');
  const [sortBy, setSortBy] = useState('newest');
  const [copiedId, setCopiedId] = useState(null);

  // Identify all historical cases
  const allHistoryCases = useMemo(() => {
    return cases.filter(c => {
      return (
        ['submitted', 'won', 'lost', 'closed', 'rejected'].includes(c.status) ||
        c.review_decision != null ||
        c.outcome != null
      );
    });
  }, [cases]);

  // Tab counts
  const tabCounts = useMemo(() => {
    return {
      all: allHistoryCases.length,
      submitted: allHistoryCases.filter(c => c.status === 'submitted' || c.status === 'approved').length,
      won: allHistoryCases.filter(c => c.outcome === 'won' || c.status === 'won').length,
      accepted: allHistoryCases.filter(c => 
        c.review_decision === 'reject' || 
        c.status === 'rejected' || 
        (c.recommendation === 'accept_loss' && c.status === 'approved')
      ).length,
      lost: allHistoryCases.filter(c => c.outcome === 'lost' || c.status === 'lost').length,
    };
  }, [allHistoryCases]);

  // Aggregate Ledger Metrics (prefer real backend metrics when available)
  const summaryMetrics = useMemo(() => {
    const wonTotal = metrics?.recovered_revenue ?? allHistoryCases
      .filter(c => c.outcome === 'won' || c.status === 'won')
      .reduce((acc, c) => acc + ((c.amount || 0) / 100), 0);

    const feesSavedTotal = metrics?.fees_saved ?? tabCounts.accepted * 1500;

    const totalResolved = (metrics?.won != null && metrics?.lost != null)
      ? (metrics.won + metrics.lost)
      : (tabCounts.won + tabCounts.lost);

    const winRate = totalResolved > 0
      ? `${((metrics?.win_rate != null ? metrics.win_rate : (tabCounts.won / totalResolved)) * 100).toFixed(0)}%`
      : '—';

    return {
      wonTotal,
      feesSavedTotal,
      winRate,
      inReview: tabCounts.submitted,
    };
  }, [allHistoryCases, tabCounts, metrics]);

  // Filter & Search
  const filteredCases = useMemo(() => {
    let result = allHistoryCases.filter(c => {
      // Search matching
      if (search.trim()) {
        const q = search.toLowerCase();
        const matchId = (c.case_id || '').toLowerCase().includes(q);
        const matchPayment = (c.rzp_payment_id || '').toLowerCase().includes(q);
        const matchOrder = (c.rzp_order_id || '').toLowerCase().includes(q);
        const matchDispute = (c.rzp_dispute_id || '').toLowerCase().includes(q);
        const matchReason = (c.reason_description || c.reason_code || '').toLowerCase().includes(q);
        const matchAmount = String(c.amount || '').includes(q);
        const matchOutcome = (c.outcome || c.status || '').toLowerCase().includes(q);
        if (!matchId && !matchPayment && !matchOrder && !matchDispute && !matchReason && !matchAmount && !matchOutcome) {
          return false;
        }
      }

      // Filter matching
      if (outcomeFilter === 'all') return true;
      if (outcomeFilter === 'won') return c.outcome === 'won' || c.status === 'won';
      if (outcomeFilter === 'lost') return c.outcome === 'lost' || c.status === 'lost';
      if (outcomeFilter === 'submitted') return c.status === 'submitted' || c.status === 'approved';
      if (outcomeFilter === 'accepted') {
        return c.review_decision === 'reject' || c.status === 'rejected' || (c.recommendation === 'accept_loss' && c.status === 'approved');
      }
      return true;
    });

    // Sorting
    result.sort((a, b) => {
      if (sortBy === 'newest') {
        const dateA = new Date(a.updated_at || a.created_at || 0).getTime();
        const dateB = new Date(b.updated_at || b.created_at || 0).getTime();
        return dateB - dateA;
      }
      if (sortBy === 'oldest') {
        const dateA = new Date(a.updated_at || a.created_at || 0).getTime();
        const dateB = new Date(b.updated_at || b.created_at || 0).getTime();
        return dateA - dateB;
      }
      if (sortBy === 'amount_desc') {
        return (b.amount || 0) - (a.amount || 0);
      }
      if (sortBy === 'amount_asc') {
        return (a.amount || 0) - (b.amount || 0);
      }
      return 0;
    });

    return result;
  }, [allHistoryCases, search, outcomeFilter, sortBy]);

  // Handle Copy to Clipboard
  const handleCopy = (e, text, id) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1800);
  };

  // Real CSV Export
  const handleExportCSV = () => {
    if (filteredCases.length === 0) {
      alert('No historical cases available to export.');
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
      'Outcome',
      'Review Decision',
      'Created At',
      'Updated At',
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
      c.outcome || '',
      c.review_decision || '',
      c.created_at || '',
      c.updated_at || '',
    ]);

    const csvContent = [
      headers.join(','),
      ...rows.map(r => r.map(field => `"${String(field).replace(/"/g, '""')}"`).join(',')),
    ].join('\r\n');

    const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `raven-settlement-ledger-${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  // Outcome badge renderer
  const renderOutcomeBadge = (c) => {
    if (c.status === 'won' || c.outcome === 'won') {
      const recoveredAmt = `+₹${((c.amount || 0) / 100).toLocaleString('en-IN')}`;
      return (
        <div className="history-outcome-wrap">
          <Badge type="success">WON</Badge>
          <span className="history-impact-tag won">{recoveredAmt} Recovered</span>
        </div>
      );
    }
    if (c.status === 'lost' || c.outcome === 'lost') {
      const lostAmt = `-₹${((c.amount || 0) / 100).toLocaleString('en-IN')}`;
      return (
        <div className="history-outcome-wrap">
          <Badge type="danger">LOST</Badge>
          <span className="history-impact-tag lost">{lostAmt} Written Off</span>
        </div>
      );
    }
    if (c.status === 'submitted' || c.status === 'approved') {
      return (
        <div className="history-outcome-wrap">
          <Badge type="info">GATEWAY REVIEW</Badge>
          <span className="history-impact-tag review">Verdict Pending</span>
        </div>
      );
    }
    if (c.review_decision === 'reject' || c.status === 'rejected' || (c.recommendation === 'accept_loss' && c.status === 'approved')) {
      return (
        <div className="history-outcome-wrap">
          <Badge type="warning">ACCEPTED LOSS</Badge>
          <span className="history-impact-tag saved">Saved ₹1,500 Fee</span>
        </div>
      );
    }
    return <Badge type="neutral">{c.status.toUpperCase()}</Badge>;
  };

  return (
    <div className="history-ledger-container">
      {/* Summary Metric Cards */}
      {allHistoryCases.length > 0 && (
        <div className="history-stats-strip">
          <div className="history-stat-card">
            <div className="history-stat-icon success">
              <IconShield size={16} />
            </div>
            <div>
              <div className="history-stat-value">+{formatCurrency(summaryMetrics.wonTotal)}</div>
              <div className="history-stat-label">Revenue Won</div>
            </div>
          </div>
          <div className="history-stat-card">
            <div className="history-stat-icon primary">
              <IconTarget size={16} />
            </div>
            <div>
              <div className="history-stat-value">{formatCurrency(summaryMetrics.feesSavedTotal)}</div>
              <div className="history-stat-label">Fees Saved</div>
            </div>
          </div>
          <div className="history-stat-card">
            <div className="history-stat-icon info">
              <IconActivity size={16} />
            </div>
            <div>
              <div className="history-stat-value">{summaryMetrics.winRate}</div>
              <div className="history-stat-label">Win Rate</div>
            </div>
          </div>
          <div className="history-stat-card">
            <div className="history-stat-icon warning">
              <IconClock size={16} />
            </div>
            <div>
              <div className="history-stat-value">{summaryMetrics.inReview}</div>
              <div className="history-stat-label">In Review</div>
            </div>
          </div>
        </div>
      )}

      <section className="history-card">
        {/* Header */}
        <div className="queue-header">
          <div className="queue-header-left">
            <h2 className="queue-title">
              Settlement Ledger
              <span className="queue-count-pill">{allHistoryCases.length}</span>
            </h2>
          </div>

          <div className="queue-header-actions">
            {onOpenSimulator && (
              <button
                type="button"
                className="btn btn-outline btn-sm"
                onClick={onOpenSimulator}
                title="Simulate dispute scenario"
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
              title="Export filtered records to CSV"
            >
              <IconDownload size={13} />
              <span>Export</span>
            </button>
          </div>
        </div>

        {/* Toolbar */}
        <div className="history-toolbar">
          <div className="history-search-wrap">
            <IconSearch className="history-search-icon" />
            <input
              type="text"
              className="history-search-input"
              placeholder="Search ID, payment, reason, amount..."
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
              { id: 'submitted', label: 'In Review', count: tabCounts.submitted },
              { id: 'won', label: 'Won', count: tabCounts.won },
              { id: 'accepted', label: 'Accepted Loss', count: tabCounts.accepted },
              { id: 'lost', label: 'Lost', count: tabCounts.lost },
            ].map(tab => (
              <button
                key={tab.id}
                type="button"
                className={`history-pill-btn ${outcomeFilter === tab.id ? 'active' : ''}`}
                onClick={() => setOutcomeFilter(tab.id)}
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
            <option value="newest">Newest First</option>
            <option value="oldest">Oldest First</option>
            <option value="amount_desc">Amount (High-Low)</option>
            <option value="amount_asc">Amount (Low-High)</option>
          </select>
        </div>

        {/* Table or Empty State */}
        {allHistoryCases.length === 0 ? (
          <div className="history-empty-card">
            <div className="history-empty-icon-ring">
              <IconSparkles size={22} />
            </div>
            <div className="history-empty-title">Settlement Ledger is Empty</div>
            <div className="history-empty-desc">
              Disputes transition here automatically once investigated and either submitted to Razorpay, won, or conceded to save arbitration fees.
            </div>
            {onOpenSimulator && (
              <button 
                type="button" 
                className="btn btn-primary btn-sm" 
                onClick={onOpenSimulator}
              >
                <IconSparkles size={13} />
                <span>Simulate a Resolved Dispute</span>
              </button>
            )}
          </div>
        ) : filteredCases.length === 0 ? (
          <div className="history-empty-card">
            <div className="history-empty-icon-ring" style={{ background: 'var(--color-neutral-bg)', color: 'var(--text-secondary)' }}>
              <IconSearch size={22} />
            </div>
            <div className="history-empty-title">No matching records found</div>
            <div className="history-empty-desc">
              No historical disputes match your active search &quot;{search}&quot; or outcome filter.
            </div>
            <button 
              type="button" 
              className="btn btn-outline btn-sm"
              onClick={() => { setSearch(''); setOutcomeFilter('all'); }}
            >
              <span>Reset Filters</span>
            </button>
          </div>
        ) : (
          <>
            {/* Desktop Table View */}
            <div className="history-table-wrap desktop-table-view">
              <table className="history-table">
                <thead>
                  <tr>
                    <th>Dispute & Reference</th>
                    <th>Customer Claim</th>
                    <th>Amount</th>
                    <th>AI vs Analyst</th>
                    <th>Final Outcome</th>
                    <th>Date Settled</th>
                    <th style={{ textAlign: 'right' }}>Forensic Audit</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredCases.map(c => {
                    const isSelected = selectedCaseId === c.case_id;
                    const rawDate = c.updated_at || c.created_at;
                    const dateStr = rawDate
                      ? new Date(rawDate).toLocaleDateString('en-IN', {
                          day: 'numeric',
                          month: 'short',
                          year: 'numeric',
                        })
                      : 'Recent';
                    const relativeStr = formatRelativeTime(rawDate);

                    const paymentRef = c.rzp_payment_id || `pay_${(c.case_id || '').replace('CASE-', '')}`;
                    const isCopied = copiedId === c.case_id;

                    return (
                      <tr 
                        key={c.case_id}
                        className={`history-row ${isSelected ? 'selected' : ''}`}
                        onClick={() => {
                          if (onSelectCase) onSelectCase(c.case_id);
                        }}
                      >
                        {/* Dispute ID & References */}
                        <td>
                          <div className="history-id-stack">
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

                        {/* AI vs Human Decision */}
                        <td>
                          <div className="ai-vs-human-stack">
                            <div className="ai-vs-human-row">
                              <span className="ai-vs-label">AI:</span>
                              <span className={`ai-vs-value ${
                                c.recommendation === 'contest' ? 'ai-contest' :
                                c.recommendation === 'accept_loss' ? 'ai-accept' :
                                c.recommendation === 'human_review' ? 'ai-review' : ''
                              }`}>
                                {c.recommendation ? c.recommendation.replace(/_/g, ' ') : '—'}
                              </span>
                            </div>
                            <div className="ai-vs-human-row">
                              <span className="ai-vs-label">Analyst:</span>
                              <span className={`ai-vs-value ${
                                c.review_decision === 'approve' ? 'ai-contest' :
                                c.review_decision === 'reject' ? 'ai-accept' : ''
                              }`}>
                                {c.review_decision ? c.review_decision : '—'}
                              </span>
                            </div>
                            {c.assessment_score != null && (
                              <div className="ai-vs-human-row">
                                <span className="ai-vs-label">Score:</span>
                                <span className="ai-vs-score">{(c.assessment_score * 100).toFixed(0)}%</span>
                              </div>
                            )}
                          </div>
                        </td>

                        {/* Final Outcome */}
                        <td>
                          {renderOutcomeBadge(c)}
                        </td>

                        {/* Date with relative time */}
                        <td className="history-date-cell">
                          <div>{dateStr}</div>
                          {relativeStr && <div className="history-date-relative">{relativeStr}</div>}
                        </td>

                        {/* Forensic Audit Action */}
                        <td style={{ textAlign: 'right' }}>
                          <button
                            type="button"
                            className="history-action-btn"
                            onClick={(e) => {
                              e.stopPropagation();
                              if (onSelectCase) onSelectCase(c.case_id);
                            }}
                            title="Inspect submitted evidence package, chronology, and audit trail"
                          >
                            <IconEye size={12} />
                            <span>Audit Package</span>
                          </button>
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
                const isCopied = copiedId === c.case_id;
                const rawDate = c.updated_at || c.created_at;
                const dateStr = rawDate
                  ? new Date(rawDate).toLocaleDateString('en-IN', {
                      day: 'numeric',
                      month: 'short',
                      year: 'numeric',
                    })
                  : 'Recent';
                const relativeStr = formatRelativeTime(rawDate);
                const paymentRef = c.rzp_payment_id || `pay_${(c.case_id || '').replace('CASE-', '')}`;
                const amountFormatted = `₹${((c.amount || 0) / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;

                return (
                  <div
                    key={c.case_id}
                    className={`mobile-dispute-card ${isSelected ? 'selected' : ''}`}
                    onClick={() => {
                      if (onSelectCase) onSelectCase(c.case_id);
                    }}
                  >
                    {/* Top Row: Case ID, Copy, Amount */}
                    <div className="mobile-card-top">
                      <div className="mobile-card-id-group" onClick={e => e.stopPropagation()}>
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

                    {/* Reference & Date Line */}
                    <div className="history-refs-sub" style={{ marginTop: '-4px', display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '4px' }}>
                      <span>{paymentRef} {c.rzp_order_id && `• ${c.rzp_order_id}`}</span>
                      <span style={{ color: 'var(--text-secondary)' }}>{dateStr}{relativeStr ? ` · ${relativeStr}` : ''}</span>
                    </div>

                    {/* Customer Claim */}
                    <div className="mobile-card-claim">
                      <div className="mobile-card-reason">
                        {c.reason_code ? c.reason_code.replace(/_/g, ' ') : 'Unknown'}
                      </div>
                      <div className="mobile-card-desc">
                        {c.reason_description || '—'}
                      </div>
                    </div>

                    {/* Outcome Badge & AI vs Human */}
                    <div className="mobile-card-tags">
                      {renderOutcomeBadge(c)}
                      {c.recommendation && (
                        <span className={`mobile-ai-verdict-chip ${
                          c.recommendation === 'contest' ? 'ai-contest' :
                          c.recommendation === 'accept_loss' ? 'ai-accept' : 'ai-review'
                        }`}>
                          AI: {c.recommendation.replace(/_/g, ' ')}
                        </span>
                      )}
                      {c.assessment_score != null && (
                        <span className="mobile-score-chip">
                          {(c.assessment_score * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>

                    {/* Touch Action Footer */}
                    <div className="mobile-card-actions" onClick={e => e.stopPropagation()}>
                      <button
                        type="button"
                        className="btn btn-sm btn-outline"
                        onClick={() => {
                          if (onSelectCase) onSelectCase(c.case_id);
                        }}
                      >
                        <IconEye size={13} />
                        <span>Audit Evidence Package</span>
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
