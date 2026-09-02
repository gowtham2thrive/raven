import { useState } from 'react';
import { Badge } from './Badge';
import { IconCheck, IconX, IconAlertTriangle, IconHelpCircle, IconChevronDown, IconClock } from './Icons';

/**
 * Expandable evidence record card.
 *
 * Shows category, status, summary, source metadata at a glance.
 * Click to expand and reveal raw content JSON, event timestamp, and timezone flag.
 */
export function EvidenceItem({ evidence }) {
  const [expanded, setExpanded] = useState(false);

  const {
    category,
    status,
    summary,
    source_system,
    source_record_id,
    relevance,
    reliability,
    content,
    event_time_utc,
    timezone_confident,
  } = evidence;

  const renderStatusIcon = () => {
    if (status === 'available') return <IconCheck size={14} />;
    if (status === 'missing') return <IconX size={14} />;
    if (status === 'unverified') return <IconAlertTriangle size={14} />;
    return <IconHelpCircle size={14} />;
  };

  const getStatusBadgeType = () => {
    if (status === 'available') return 'success';
    if (status === 'missing') return 'danger';
    if (status === 'unverified') return 'warning';
    return 'neutral';
  };

  const formattedTime = event_time_utc
    ? new Date(event_time_utc).toUTCString()
    : null;

  return (
    <div
      className={`evidence-item evidence-${status} ${expanded ? 'evidence-expanded' : ''}`}
      onClick={() => setExpanded((prev) => !prev)}
      style={{ cursor: 'pointer' }}
    >
      <div className="evidence-status-icon">
        {renderStatusIcon()}
      </div>
      <div className="evidence-info">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
          <span className="evidence-category">{category}</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Badge type={getStatusBadgeType()}>
              {status}
            </Badge>
            <IconChevronDown
              size={12}
              style={{
                transition: 'transform 0.2s',
                transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
                opacity: 0.5,
              }}
            />
          </div>
        </div>
        <div className="evidence-summary">{summary}</div>
        <div className="evidence-meta">
          <span>Source: <strong>{source_system}</strong></span>
          {source_record_id && <span>Record ID: <code>{source_record_id}</code></span>}
          {relevance && <span>Relevance: <strong>{relevance}</strong></span>}
          {reliability != null && <span>Reliability: <strong>{(reliability * 100).toFixed(0)}%</strong></span>}
        </div>

        {/* Expanded Detail View */}
        {expanded && (
          <div className="evidence-expanded-content" onClick={(e) => e.stopPropagation()}>
            {/* Timestamp row */}
            {formattedTime && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '11px', color: 'var(--text-secondary)', marginBottom: 8 }}>
                <IconClock size={11} />
                <span>{formattedTime}</span>
                {timezone_confident === false && (
                  <span style={{ color: 'var(--color-warning)', fontWeight: 600 }}>
                    <IconAlertTriangle size={10} /> Timezone unverified
                  </span>
                )}
                {timezone_confident === true && (
                  <span style={{ color: 'var(--color-success)' }}>
                    <IconCheck size={10} /> Timezone verified
                  </span>
                )}
              </div>
            )}

            {/* Raw Content */}
            {content && (
              <div style={{
                marginTop: 4,
                padding: '10px 12px',
                borderRadius: 6,
                background: 'rgba(0, 0, 0, 0.25)',
                border: '1px solid var(--border-subtle)',
                fontSize: '11px',
                fontFamily: 'monospace',
                lineHeight: 1.6,
                color: 'var(--text-secondary)',
                maxHeight: 220,
                overflowY: 'auto',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}>
                {typeof content === 'object' ? JSON.stringify(content, null, 2) : String(content)}
              </div>
            )}

            {!content && (
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontStyle: 'italic', marginTop: 4 }}>
                No raw content data available for this evidence record.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
