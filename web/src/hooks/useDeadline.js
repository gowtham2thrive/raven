/**
 * Calculate and format human-readable deadline information with urgency level.
 *
 * @param {string|number|Date|null} respondBy - ISO string or timestamp
 * @returns {{ text: string, type: 'urgent'|'warning'|'normal', diffHours: number }}
 */
export function formatDeadline(respondBy) {
  if (!respondBy) return { text: '2 days left', type: 'normal', diffHours: 48 };
  
  const target = typeof respondBy === 'number' && respondBy < 1e11 
    ? respondBy * 1000 
    : new Date(respondBy).getTime();
  const now = Date.now();
  const diffHours = (target - now) / (1000 * 60 * 60);

  if (diffHours <= 0) return { text: 'Expired', type: 'urgent', diffHours };
  if (diffHours < 6) {
    const hours = Math.floor(diffHours);
    const mins = Math.floor((diffHours - hours) * 60);
    return { text: `${hours}h ${mins}m left`, type: 'urgent', diffHours };
  }
  if (diffHours < 24) {
    return { text: `${Math.round(diffHours)}h left`, type: 'warning', diffHours };
  }
  const days = Math.round(diffHours / 24);
  return { text: `${days} day${days > 1 ? 's' : ''} left`, type: 'normal', diffHours };
}
