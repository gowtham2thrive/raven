import { IconSearch } from './Icons';

export function EmptyState({ 
  icon, 
  title = 'No records found', 
  description = 'Try adjusting your search query or filters.',
  action = null 
}) {
  return (
    <div className="empty-state">
      {icon ? (
        <div className="empty-state-icon">{icon}</div>
      ) : (
        <IconSearch className="empty-state-icon" />
      )}
      <div className="empty-state-title">{title}</div>
      {description && <div className="empty-state-desc">{description}</div>}
      {action && <div className="empty-state-action">{action}</div>}
    </div>
  );
}
