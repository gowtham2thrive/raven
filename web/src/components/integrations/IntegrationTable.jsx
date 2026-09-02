import { useState } from 'react';
import { 
  IconZap, 
  IconDatabase, 
  IconWebhook, 
  IconFileText, 
  IconRefreshCw, 
  IconTrash,
  IconSliders,
  IconCheck,
  IconX
} from '../Icons';

const TYPE_ICONS = {
  rest_api: <IconZap size={14} />,
  database: <IconDatabase size={14} />,
  csv_file: <IconFileText size={14} />,
  excel_file: <IconFileText size={14} />,
  pdf_file: <IconFileText size={14} />,
  webhook: <IconWebhook size={14} />,
};

function formatTimeAgo(isoStr) {
  if (!isoStr) return 'Never';
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

export function IntegrationTable({ 
  integrations, 
  onSelectIntegration, 
  onDelete, 
  onTest, 
  onToggleStatus 
}) {
  const [testingId, setTestingId] = useState(null);

  const handleTestClick = async (e, id) => {
    e.stopPropagation();
    setTestingId(id);
    try {
      await onTest(id);
    } finally {
      setTestingId(null);
    }
  };

  return (
    <div className="integration-table-container">
      <table className="integration-table">
        <thead>
          <tr>
            <th>Integration Name & Source</th>
            <th>Type</th>
            <th>Evidence Category</th>
            <th>Status</th>
            <th>Field Mappings</th>
            <th>Total Ingested</th>
            <th>Last Synced</th>
            <th className="text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {integrations.map((item) => {
            const isTesting = testingId === item.id;
            return (
              <tr 
                key={item.id} 
                className="integration-table-row"
                onClick={() => onSelectIntegration(item.id)}
              >
                <td>
                  <div className="table-name-cell">
                    <div className={`table-type-icon ${item.integration_type}`}>
                      {TYPE_ICONS[item.integration_type] || <IconZap size={14} />}
                    </div>
                    <div>
                      <div className="table-row-title">{item.name}</div>
                      {item.description && (
                        <div className="table-row-desc">{item.description}</div>
                      )}
                    </div>
                  </div>
                </td>
                <td>
                  <span className="table-type-badge">
                    {item.integration_type.replace('_', ' ').toUpperCase()}
                  </span>
                </td>
                <td>
                  <span className="table-category-tag">
                    {item.evidence_category}
                  </span>
                </td>
                <td>
                  <span className={`status-pill ${item.status}`}>
                    <span className="status-dot"></span>
                    {item.status}
                  </span>
                </td>
                <td>
                  <span className="table-mappings-count">
                    {item.field_mapping_count || 0} fields
                  </span>
                </td>
                <td>
                  <span className="table-sync-count">
                    {item.sync_count || 0} runs
                  </span>
                </td>
                <td className="table-time-cell">
                  {formatTimeAgo(item.last_sync_at)}
                </td>
                <td>
                  <div className="table-actions-cell" onClick={(e) => e.stopPropagation()}>
                    <button 
                      className="btn-action-icon"
                      title="Test Connection"
                      onClick={(e) => handleTestClick(e, item.id)}
                      disabled={isTesting}
                    >
                      {isTesting ? <IconRefreshCw className="spin" size={13} /> : <IconZap size={13} />}
                    </button>
                    <button 
                      className="btn-action-icon"
                      title="Configure Mappings"
                      onClick={() => onSelectIntegration(item.id)}
                    >
                      <IconSliders size={13} />
                    </button>
                    <button 
                      className={`btn-action-icon ${item.status === 'active' ? 'active-toggle' : ''}`}
                      title={item.status === 'active' ? 'Deactivate' : 'Activate'}
                      onClick={() => onToggleStatus(item)}
                    >
                      {item.status === 'active' ? <IconCheck size={13} /> : <IconX size={13} />}
                    </button>
                    <button 
                      className="btn-action-icon danger"
                      title="Delete Integration"
                      onClick={() => onDelete(item.id)}
                    >
                      <IconTrash size={13} />
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
