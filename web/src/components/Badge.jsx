import { IconCheck, IconAlertTriangle, IconX, IconClock, IconInfo } from './Icons';

/**
 * Returns badge type string based on case status.
 */
export function getStatusBadgeType(status) {
  const map = {
    created: 'info',
    investigating: 'info',
    evidence_gathered: 'info',
    assessed: 'info',
    draft_ready: 'warning',
    under_review: 'warning',
    approved: 'success',
    submitted: 'success',
    rejected: 'danger',
    escalated: 'danger',
    won: 'success',
    lost: 'danger',
    closed: 'neutral',
  };
  return map[status] || 'info';
}

export function Badge({ type = 'neutral', children, icon = true }) {
  const renderIcon = () => {
    if (!icon) return null;
    if (type === 'success') return <IconCheck className="badge-icon" size={12} />;
    if (type === 'warning') return <IconAlertTriangle className="badge-icon" size={12} />;
    if (type === 'danger') return <IconX className="badge-icon" size={12} />;
    if (type === 'info') return <IconClock className="badge-icon" size={12} />;
    return <IconInfo className="badge-icon" size={12} />;
  };

  return (
    <span className={`badge badge-${type}`}>
      {renderIcon()}
      <span>{children}</span>
    </span>
  );
}
