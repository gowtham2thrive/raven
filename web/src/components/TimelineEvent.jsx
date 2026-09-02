import { IconAlertTriangle, IconClock } from './Icons';

export function TimelineEvent({ event }) {
  const {
    timestamp_utc,
    timezone_confident,
    label,
    description,
    source_system,
    category,
  } = event;

  const formattedTime = timestamp_utc 
    ? new Date(timestamp_utc).toUTCString() 
    : 'Time unknown';

  return (
    <div className="timeline-event">
      <div className="timeline-dot" />
      <div className="timeline-time">
        <IconClock size={11} />
        <span>{formattedTime}</span>
        {!timezone_confident && (
          <span className="tz-flag" title="Timezone ambiguous — verified UTC">
            <IconAlertTriangle size={11} /> tz
          </span>
        )}
      </div>
      <div className="timeline-label">{label}</div>
      <div className="timeline-source">
        {description} • <em>{source_system} ({category})</em>
      </div>
    </div>
  );
}
