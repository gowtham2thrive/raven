export function Spinner({ size = 'md' }) {
  return (
    <div 
      className={`spinner ${size === 'sm' ? 'spinner-sm' : ''}`} 
      role="status" 
      aria-label="Loading..."
    />
  );
}
