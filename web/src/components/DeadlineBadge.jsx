import { formatDeadline } from '../hooks/useDeadline';
import { IconClock, IconAlertTriangle } from './Icons';

export function DeadlineBadge({ respondBy }) {
  const deadline = formatDeadline(respondBy);
  const isUrgent = deadline.type === 'urgent';

  return (
    <span className={`deadline-badge deadline-${deadline.type}`}>
      {isUrgent ? (
        <IconAlertTriangle className="deadline-badge-icon" size={12} />
      ) : (
        <IconClock className="deadline-badge-icon" size={12} />
      )}
      <span>{deadline.text}</span>
    </span>
  );
}
