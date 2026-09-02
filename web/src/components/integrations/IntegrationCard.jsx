import { useState } from 'react';
import { 
  IconZap, 
  IconDatabase, 
  IconWebhook, 
  IconFileText, 
  IconRefreshCw, 
  IconTrash, 
  IconSliders
} from '../Icons';

const TYPE_ICONS = {
  rest_api: <IconZap size={18} />,
  database: <IconDatabase size={18} />,
  csv_file: <IconFileText size={18} />,
  excel_file: <IconFileText size={18} />,
  pdf_file: <IconFileText size={18} />,
  webhook: <IconWebhook size={18} />,
};

const TYPE_LABELS = {
  rest_api: 'REST API',
  database: 'SQL Database',
  csv_file: 'CSV Upload',
  excel_file: 'Excel Sheet',
  pdf_file: 'PDF Parser',
  webhook: 'Inbound Webhook',
};

function formatTimeAgo(isoStr) {
  if (!isoStr) return 'Never synced';
  const d = new Date(isoStr);
  const now = Date.now();
  const diffMs = now - d.getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function IntegrationCard({ 
  integration, 
  onDelete, 
  onTest, 
  onToggleStatus, 
  onOpenDrawer 
}) {
  const [testing, setTesting] = useState(false);
  const type = integration.integration_type;
  const icon = TYPE_ICONS[type] || <IconZap size={18} />;
  const typeLabel = TYPE_LABELS[type] || type;

  const handleTestClick = async (e) => {
    e.stopPropagation();
    setTesting(true);
    try {
      await onTest();
    } finally {
      setTesting(false);
    }
  };

  return (
    <div 
      className={`integration-card ${integration.status}`}
      onClick={onOpenDrawer}
      role="button"
      tabIndex={0}
    >
      {/* Header */}
      <div className="integration-card-header">
        <div className="integration-card-brand">
          <div className={`integration-card-avatar ${type}`}>
            {icon}
          </div>
          <div className="integration-card-title-group">
            <h3 className="integration-card-title">{integration.name}</h3>
            <span className="integration-card-type-tag">{typeLabel}</span>
          </div>
        </div>

        <div className="integration-card-status">
          <span className={`status-pill ${integration.status}`}>
            <span className="status-dot"></span>
            {integration.status}
          </span>
        </div>
      </div>

      {/* Description */}
      <p className="integration-card-desc">
        {integration.description || 'Configured evidence source connector.'}
      </p>

      {/* Badges / Categories */}
      <div className="integration-card-chips">
        <span className="category-chip">
          <span className="chip-label">Target:</span>
          <strong>{integration.evidence_category}</strong>
        </span>
        <span className="mappings-chip">
          {integration.field_mapping_count || 0} fields mapped
        </span>
      </div>

      {/* Sync stats */}
      <div className="integration-card-footer-stats">
        <div className="sync-meta-item">
          <span className="sync-label">Last Ingestion</span>
          <span className="sync-val">{formatTimeAgo(integration.last_sync_at)}</span>
        </div>
        <div className="sync-meta-item text-right">
          <span className="sync-label">Records Ingested</span>
          <span className="sync-val">{integration.sync_count || 0} syncs</span>
        </div>
      </div>

      {/* Action Toolbar */}
      <div className="integration-card-actions" onClick={(e) => e.stopPropagation()}>
        <button 
          className="btn-card-action primary-tint" 
          onClick={handleTestClick}
          disabled={testing}
          title="Test connection diagnostic"
        >
          {testing ? <IconRefreshCw className="spin" size={13} /> : <IconZap size={13} />}
          <span>{testing ? 'Testing...' : 'Test Connection'}</span>
        </button>

        <button 
          className="btn-card-action secondary-tint"
          onClick={onOpenDrawer}
          title="Configure field mappings and payload"
        >
          <IconSliders size={13} />
          <span>Mappings</span>
        </button>

        <button 
          className={`btn-card-action ${integration.status === 'active' ? 'toggle-active' : 'toggle-inactive'}`}
          onClick={onToggleStatus}
          title={integration.status === 'active' ? 'Deactivate ingestion' : 'Activate ingestion'}
        >
          {integration.status === 'active' ? 'Disable' : 'Enable'}
        </button>

        <button 
          className="btn-card-action danger-tint"
          onClick={onDelete}
          title="Delete integration"
        >
          <IconTrash size={13} />
        </button>
      </div>
    </div>
  );
}
