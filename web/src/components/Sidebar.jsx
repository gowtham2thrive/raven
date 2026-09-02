import { NavLink } from 'react-router-dom';
import { 
  IconDisputes, 
  IconHistory, 
  IconSettings, 
  IconLayers, 
  IconActivity,
  IconX,
  IconChevronLeft,
  IconChevronRight 
} from './Icons';

export function Sidebar({ 
  pendingCount = 0, 
  isOpen = false, 
  onClose = () => {},
  isCollapsed = false,
  onToggleCollapse = () => {}
}) {


  return (
    <>
      {/* Mobile Backdrop Overlay */}
      {isOpen && (
        <div 
          className="sidebar-backdrop" 
          onClick={onClose} 
          aria-hidden="true" 
        />
      )}

      <aside 
        className={`sidebar ${isOpen ? 'open' : ''} ${isCollapsed ? 'collapsed' : ''}`} 
        aria-label="Main Navigation"
      >
        <div className="sidebar-brand">
          <img src="/raven.svg" alt="RAVEN" className="sidebar-brand-icon" />
          <span className="sidebar-brand-text">RAVEN</span>
          
          {/* Mobile Close Button */}
          <button 
            type="button" 
            className="sidebar-close-btn" 
            onClick={onClose} 
            aria-label="Close navigation menu"
          >
            <IconX size={18} />
          </button>
        </div>

        <div className="sidebar-subtitle">
          AI Chargeback Responder
        </div>

        <nav className="sidebar-nav">
          <div className="sidebar-section-label">Operations</div>
          
          <NavLink 
            to="/" 
            end 
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            onClick={onClose}
            title="Disputes"
          >
            <div className="nav-item-icon-wrap">
              <IconDisputes className="nav-item-icon" />
              {pendingCount > 0 && isCollapsed && (
                <span className="nav-dot-badge" />
              )}
            </div>
            <span className="nav-item-text">Disputes</span>
            {pendingCount > 0 && !isCollapsed && (
              <span className="nav-item-badge">{pendingCount}</span>
            )}
          </NavLink>

          <NavLink 
            to="/history" 
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            onClick={onClose}
            title="History"
          >
            <div className="nav-item-icon-wrap">
              <IconHistory className="nav-item-icon" />
            </div>
            <span className="nav-item-text">History</span>
          </NavLink>

          <NavLink 
            to="/analytics" 
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            onClick={onClose}
            title="Analytics"
          >
            <div className="nav-item-icon-wrap">
              <IconActivity className="nav-item-icon" />
            </div>
            <span className="nav-item-text">Analytics</span>
          </NavLink>

          <div className="sidebar-section-label">Platform</div>

          <NavLink 
            to="/integrations" 
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            onClick={onClose}
            title="Integrations"
          >
            <div className="nav-item-icon-wrap">
              <IconLayers className="nav-item-icon" />
            </div>
            <span className="nav-item-text">Integrations</span>
          </NavLink>


          <NavLink 
            to="/settings" 
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            onClick={onClose}
            title="Settings"
          >
            <div className="nav-item-icon-wrap">
              <IconSettings className="nav-item-icon" />
            </div>
            <span className="nav-item-text">Settings</span>
          </NavLink>
        </nav>

        {/* Desktop Collapse / Expand Toggle */}
        <div className="sidebar-footer">
          <div className="sidebar-version">Razorpay Buildathon v1.0</div>
          <button
            type="button"
            className="sidebar-collapse-btn"
            onClick={onToggleCollapse}
            title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar into slim strip'}
            aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {isCollapsed ? (
              <IconChevronRight size={16} />
            ) : (
              <>
                <IconChevronLeft size={16} />
                <span className="sidebar-collapse-text">Collapse</span>
              </>
            )}
          </button>
        </div>
      </aside>
    </>
  );
}
