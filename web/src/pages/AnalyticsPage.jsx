import { useState, useEffect } from 'react';
import { fetchMetrics } from '../api/client';
import { Spinner } from '../components/Spinner';
import { Badge } from '../components/Badge';
import { formatCurrency } from '../utils/format';
import { 
  IconTarget,
  IconActivity,
  IconAlertTriangle,
  IconClock
} from '../components/Icons';

/**
 * AnalyticsPage — Live operational metrics and benchmark reference.
 *
 * Shows real data from the database for operational metrics.
 * Benchmark section is clearly labeled as static reference data.
 */
export function AnalyticsPage() {
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    fetchMetrics()
      .then(setMetrics)
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();

    window.addEventListener('raven:data-updated', load);
    window.addEventListener('focus', load);

    const interval = setInterval(load, 5000);

    return () => {
      window.removeEventListener('raven:data-updated', load);
      window.removeEventListener('focus', load);
      clearInterval(interval);
    };
  }, []);

  if (loading) {
    return (
      <div className="page-center">
        <Spinner />
      </div>
    );
  }

  // ── Live Operational Data (real from database) ──
  const totalCases = metrics?.total_cases || 0;
  const openCases = metrics?.open_cases || 0;
  const wonCount = metrics?.won || 0;
  const lostCount = metrics?.lost || 0;
  const submittedCount = metrics?.submitted || 0;
  const pendingReview = metrics?.pending_review || 0;
  const urgentCount = metrics?.urgent_count || 0;
  const amountAtRisk = metrics?.amount_at_risk || 0;
  const protectedValue = metrics?.protected_value || 0;
  const recoveredRevenue = metrics?.recovered_revenue || 0;
  const feesSaved = metrics?.fees_saved || 0;
  const winRate = metrics?.win_rate || 0;
  const avgScore = metrics?.avg_score || 0;

  const totalResolved = wonCount + lostCount;
  const winRatePct = totalResolved > 0 ? (winRate * 100).toFixed(0) : '—';

  // ── Live Recommendation Breakdown ──
  const liveRec = metrics?.recommendation_breakdown || {};
  const liveTotalRec = Object.values(liveRec).reduce((a, b) => a + b, 0) || 0;
  const liveContest = liveRec.contest || 0;
  const liveAccept = liveRec.accept_loss || 0;
  const liveReview = liveRec.human_review || 0;

  // ── Status Breakdown ──
  const statusBreakdown = metrics?.status_breakdown || {};

  // ── Static Benchmark Reference ──
  const evalData = metrics?.evaluation || {};
  const hasEvalData = evalData.cases_evaluated != null;

  return (
    <div className="page">
      {/* Live Operational Hero Banner */}
      <div className="eval-banner">
        <div className="eval-banner-top">
          <div className="eval-banner-title">Live Operational Dashboard</div>
          <Badge type={totalCases > 0 ? 'success' : 'info'}>{totalCases} Total Cases</Badge>
        </div>
        <div className="eval-banner-desc">
          Real-time dispute investigation metrics from the active database. All figures reflect actual case outcomes, not simulated benchmarks.
        </div>
      </div>

      {/* Live KPI Cards */}
      <div className="eval-grid">
        <div className="eval-card">
          <div className="eval-card-value">{totalCases}</div>
          <div className="eval-card-label">Total Cases</div>
          <div className="eval-card-sub">{openCases} active, {submittedCount} processed</div>
        </div>

        <div className="eval-card">
          <div className="eval-card-value" style={{ color: 'var(--color-success)' }}>
            {winRatePct}{winRatePct !== '—' ? '%' : ''}
          </div>
          <div className="eval-card-label">Win Rate</div>
          <div className="eval-card-sub">{wonCount}W / {lostCount}L ({totalResolved} resolved)</div>
        </div>

        <div className="eval-card">
          <div className="eval-card-value" style={{ color: 'var(--color-success)' }}>
            {formatCurrency(recoveredRevenue)}
          </div>
          <div className="eval-card-label">Revenue Recovered</div>
          <div className="eval-card-sub">From won dispute contests</div>
        </div>

        <div className="eval-card">
          <div className="eval-card-value" style={{ color: 'var(--brand-accent)' }}>
            {formatCurrency(feesSaved)}
          </div>
          <div className="eval-card-label">Arbitration Fees Saved</div>
          <div className="eval-card-sub">By accepting unwinnable disputes</div>
        </div>

        <div className="eval-card">
          <div className="eval-card-value" style={{ color: 'var(--brand-primary)' }}>
            {formatCurrency(protectedValue)}
          </div>
          <div className="eval-card-label">Protected Value</div>
          <div className="eval-card-sub">Submitted + approved + won</div>
        </div>

        <div className="eval-card">
          <div className="eval-card-value" style={{ color: 'var(--color-warning)' }}>
            {formatCurrency(amountAtRisk)}
          </div>
          <div className="eval-card-label">Amount at Risk</div>
          <div className="eval-card-sub">{urgentCount} urgent (expiring &lt;24h)</div>
        </div>
      </div>

      {/* Distribution and Insights Grid */}
      <div className="two-col-grid">
        {/* Live Recommendation Distribution */}
        <section className="card">
          <h2 className="card-title">
            <IconTarget className="card-title-icon" />
            <span>AI Recommendation Distribution</span>
          </h2>

          {liveTotalRec > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div>
                <div className="distribution-bar-label">
                  <span>Contest (Defend Merchant)</span>
                  <span style={{ color: 'var(--color-success)' }}>
                    {liveContest} cases ({((liveContest / liveTotalRec) * 100).toFixed(0)}%)
                  </span>
                </div>
                <div className="distribution-bar-track">
                  <div className="distribution-bar-fill" style={{ width: `${(liveContest / liveTotalRec) * 100}%`, background: 'var(--color-success)' }} />
                </div>
              </div>

              <div>
                <div className="distribution-bar-label">
                  <span>Accept Loss (Save Arbitration Fees)</span>
                  <span style={{ color: 'var(--color-danger)' }}>
                    {liveAccept} cases ({((liveAccept / liveTotalRec) * 100).toFixed(0)}%)
                  </span>
                </div>
                <div className="distribution-bar-track">
                  <div className="distribution-bar-fill" style={{ width: `${(liveAccept / liveTotalRec) * 100}%`, background: 'var(--color-danger)' }} />
                </div>
              </div>

              <div>
                <div className="distribution-bar-label">
                  <span>Human Review (Contradictions / Ambiguity)</span>
                  <span style={{ color: 'var(--color-warning)' }}>
                    {liveReview} cases ({((liveReview / liveTotalRec) * 100).toFixed(0)}%)
                  </span>
                </div>
                <div className="distribution-bar-track">
                  <div className="distribution-bar-fill" style={{ width: `${(liveReview / liveTotalRec) * 100}%`, background: 'var(--color-warning)' }} />
                </div>
              </div>
            </div>
          ) : (
            <div style={{ fontSize: '13px', color: 'var(--text-muted)', padding: '20px 0', textAlign: 'center' }}>
              No investigated cases yet. Generate and investigate disputes to see recommendation distribution.
            </div>
          )}

          {/* Average Confidence Score */}
          {avgScore > 0 && (
            <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--border-subtle)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Average Confidence Score</span>
                <span style={{ color: 'var(--color-success)', fontWeight: 700 }}>{(avgScore * 100).toFixed(0)}%</span>
              </div>
              <div className="distribution-bar-track" style={{ marginTop: 6 }}>
                <div className="distribution-bar-fill" style={{ width: `${avgScore * 100}%`, background: 'var(--color-success)' }} />
              </div>
            </div>
          )}
        </section>

        {/* Status Pipeline Breakdown */}
        <section className="card">
          <h2 className="card-title">
            <IconActivity className="card-title-icon" />
            <span>Case Pipeline Status</span>
          </h2>

          {Object.keys(statusBreakdown).length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {Object.entries(statusBreakdown)
                .sort((a, b) => b[1] - a[1])
                .map(([status, count]) => {
                  const statusColors = {
                    created: 'var(--text-secondary)',
                    investigating: 'var(--brand-primary)',
                    under_review: 'var(--color-warning)',
                    approved: 'var(--color-success)',
                    submitted: 'var(--color-success)',
                    rejected: 'var(--color-danger)',
                    won: '#34D399',
                    lost: 'var(--color-danger)',
                  };
                  const pct = totalCases > 0 ? (count / totalCases) * 100 : 0;
                  return (
                    <div key={status}>
                      <div className="distribution-bar-label">
                        <span>{status.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</span>
                        <span style={{ color: statusColors[status] || 'var(--text-secondary)' }}>
                          {count} ({pct.toFixed(0)}%)
                        </span>
                      </div>
                      <div className="distribution-bar-track">
                        <div className="distribution-bar-fill" style={{ width: `${pct}%`, background: statusColors[status] || 'var(--text-muted)' }} />
                      </div>
                    </div>
                  );
                })
              }
            </div>
          ) : (
            <div style={{ fontSize: '13px', color: 'var(--text-muted)', padding: '20px 0', textAlign: 'center' }}>
              No cases in the database yet. Create disputes to see pipeline distribution.
            </div>
          )}

          {/* Operational Highlights */}
          {(pendingReview > 0 || urgentCount > 0) && (
            <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--border-subtle)', display: 'flex', gap: 16, fontSize: '12px' }}>
              {pendingReview > 0 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--color-warning)' }}>
                  <IconAlertTriangle size={13} />
                  <span><strong>{pendingReview}</strong> awaiting review</span>
                </div>
              )}
              {urgentCount > 0 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--color-danger)' }}>
                  <IconClock size={13} />
                  <span><strong>{urgentCount}</strong> expiring &lt;24h</span>
                </div>
              )}
            </div>
          )}
        </section>
      </div>

      {/* Benchmark Reference Section (clearly labeled as static) */}
      {hasEvalData && (
        <>
          <div style={{ 
            margin: 'var(--space-5) 0 var(--space-3)', 
            padding: '12px 16px', 
            borderRadius: 8,
            background: 'rgba(139, 92, 246, 0.06)',
            border: '1px solid rgba(139, 92, 246, 0.15)',
            fontSize: '12px',
            color: 'var(--text-secondary)',
          }}>
            <strong style={{ color: 'var(--brand-accent)' }}>Reference Benchmark:</strong> The metrics below are from a standardized held-out test set of {evalData.cases_evaluated} cases, not from your live database. They represent the system's evaluated accuracy on known dispute patterns.
          </div>

          <div className="eval-grid">
            <div className="eval-card">
              <div className="eval-card-value">{evalData.cases_evaluated}</div>
              <div className="eval-card-label">Benchmark Cases</div>
              <div className="eval-card-sub">Held-out evaluation set</div>
            </div>

            <div className="eval-card">
              <div className="eval-card-value" style={{ color: 'var(--color-success)' }}>
                {evalData.precision}%
              </div>
              <div className="eval-card-label">Contest Precision</div>
              <div className="eval-card-sub">Accurate contest victories</div>
            </div>

            <div className="eval-card">
              <div className="eval-card-value" style={{ color: 'var(--brand-primary)' }}>
                {evalData.recall}%
              </div>
              <div className="eval-card-label">Dispute Recall</div>
              <div className="eval-card-sub">Defensible claims recovered</div>
            </div>

            <div className="eval-card">
              <div className="eval-card-value" style={{ color: 'var(--color-warning)' }}>
                {evalData.false_positive_rate}%
              </div>
              <div className="eval-card-label">False-Positive Rate</div>
              <div className="eval-card-sub">Minimal arbitration fee risk</div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
