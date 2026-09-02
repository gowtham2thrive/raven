import { IconMenu } from './Icons';

export function MobileNavbar({ onToggleSidebar, pendingCount = 0 }) {
  return (
    <header className="mobile-navbar" aria-label="Mobile Navigation Bar">
      <button 
        type="button" 
        className="mobile-menu-btn" 
        onClick={onToggleSidebar}
        aria-label="Open navigation menu"
      >
        <IconMenu size={22} />
      </button>

      <div className="mobile-brand">
        <img src="/raven.svg" alt="RAVEN" className="mobile-brand-icon" />
        <span className="mobile-brand-text">RAVEN</span>
      </div>

      <div className="mobile-navbar-right">
        {pendingCount > 0 && (
          <span className="mobile-pending-badge" title={`${pendingCount} pending review`}>
            {pendingCount}
          </span>
        )}
      </div>
    </header>
  );
}
