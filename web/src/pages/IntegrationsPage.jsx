import { useState, useEffect, useCallback, useMemo } from 'react';
import { 
  fetchIntegrations, 
  deleteIntegration, 
  testIntegration, 
  activateIntegration, 
  deactivateIntegration 
} from '../api/integrations';
import { IntegrationCard } from '../components/integrations/IntegrationCard';
import { IntegrationTable } from '../components/integrations/IntegrationTable';
import { IntegrationDrawer } from '../components/integrations/IntegrationDrawer';
import { IntegrationWizard } from '../components/integrations/IntegrationWizard';
import { 
  IconPlus, 
  IconSearch, 
  IconGrid, 
  IconTable, 
  IconRefreshCw, 
  IconCheckCircle, 
  IconAlertTriangle,
  IconZap
} from '../components/Icons';
import '../styles/integrations.css';

const STATUS_FILTERS = [
  { id: null, label: 'All Status' },
  { id: 'active', label: 'Active' },
  { id: 'inactive', label: 'Inactive' },
  { id: 'error', label: 'Errors' },
];

const EVIDENCE_CATEGORIES = [
  { id: 'all', label: 'All Categories' },
  { id: 'shipping', label: 'Shipping' },
  { id: 'delivery', label: 'Delivery' },
  { id: 'order', label: 'Order' },
  { id: 'payment', label: 'Payment' },
  { id: 'communication', label: 'Communication' },
  { id: 'refund', label: 'Refund' },
  { id: 'authentication', label: 'Auth' },
];

const ALL_DISPUTE_CATEGORIES = [
  'payment',
  'order',
  'shipping',
  'delivery',
  'communication',
  'refund',
  'authentication'
];

export function IntegrationsPage() {
  const [integrations, setIntegrations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState(null);
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [viewMode, setViewMode] = useState('grid'); // 'grid' | 'table'
  const [showWizard, setShowWizard] = useState(false);
  const [wizardPreset, setWizardPreset] = useState(null);
  const [selectedIntegrationId, setSelectedIntegrationId] = useState(null);
  const [error, setError] = useState(null);

  const loadIntegrations = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await fetchIntegrations({ status: statusFilter });
      setIntegrations(data.integrations || []);
    } catch (err) {
      setError(err.message);
      setIntegrations([]);
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    loadIntegrations();
  }, [loadIntegrations]);

  const handleDelete = async (id) => {
    if (!confirm('Are you sure you want to delete this integration connector?')) return;
    try {
      await deleteIntegration(id);
      if (selectedIntegrationId === id) setSelectedIntegrationId(null);
      loadIntegrations();
    } catch (err) {
      alert(`Delete failed: ${err.message}`);
    }
  };

  const handleTest = async (id) => {
    try {
      const result = await testIntegration(id);
      loadIntegrations();
      return result;
    } catch (err) {
      alert(`Test failed: ${err.message}`);
      return null;
    }
  };

  const handleToggleStatus = async (integration) => {
    try {
      if (integration.status === 'active') {
        await deactivateIntegration(integration.id);
      } else {
        await activateIntegration(integration.id);
      }
      loadIntegrations();
    } catch (err) {
      alert(`Status update failed: ${err.message}`);
    }
  };

  const handleWizardComplete = () => {
    setShowWizard(false);
    setWizardPreset(null);
    loadIntegrations();
  };

  // Filter integrations by search query and category
  const filteredIntegrations = useMemo(() => {
    return integrations.filter((item) => {
      const matchesCategory = categoryFilter === 'all' || item.evidence_category === categoryFilter;
      const q = searchQuery.toLowerCase().trim();
      const matchesSearch = !q || 
        item.name.toLowerCase().includes(q) ||
        (item.description && item.description.toLowerCase().includes(q)) ||
        item.integration_type.toLowerCase().includes(q) ||
        item.evidence_category.toLowerCase().includes(q);
      
      return matchesCategory && matchesSearch;
    });
  }, [integrations, categoryFilter, searchQuery]);

  // Compute stats
  const totalCount = integrations.length;
  const activeCount = integrations.filter((i) => i.status === 'active').length;
  const totalSyncs = integrations.reduce((acc, i) => acc + (i.sync_count || 0), 0);
  
  // Compute coverage of 7 dispute evidence categories
  const coveredCategories = useMemo(() => {
    const activeCats = new Set(
      integrations.filter((i) => i.status === 'active').map((i) => i.evidence_category)
    );
    return ALL_DISPUTE_CATEGORIES.map((cat) => ({
      id: cat,
      label: cat.charAt(0).toUpperCase() + cat.slice(1),
      isCovered: activeCats.has(cat),
    }));
  }, [integrations]);

  const coveragePercent = Math.round(
    (coveredCategories.filter((c) => c.isCovered).length / ALL_DISPUTE_CATEGORIES.length) * 100
  );

  return (
    <div className="page integrations-page-container">
      {/* Page Header */}
      <header className="page-header">
        <div className="page-header-left">
          <h1 className="integrations-title">Evidence Integrations Hub</h1>
          <p className="page-header-subtitle">
            Connect merchant databases, carrier APIs, webhooks, and communication logs to feed canonical evidence into investigations.
          </p>
        </div>
        <div className="page-header-actions">
          <button
            className="btn-primary"
            onClick={() => {
              setWizardPreset(null);
              setShowWizard(true);
            }}
          >
            <IconPlus size={16} />
            <span>Add Integration</span>
          </button>
        </div>
      </header>

      {/* Metrics Ribbon & Coverage Gauge */}
      <div className="integrations-metrics-ribbon">
        <div className="metric-stat-card">
          <div className="metric-stat-label">Total Connectors</div>
          <div className="metric-stat-val">{totalCount}</div>
          <div className="metric-stat-sub">
            <span className="text-success">{activeCount} active</span> · {totalCount - activeCount} paused
          </div>
        </div>

        <div className="metric-stat-card">
          <div className="metric-stat-label">Total Ingested Records</div>
          <div className="metric-stat-val">{totalSyncs.toLocaleString()}</div>
          <div className="metric-stat-sub">Across all evidence pipelines</div>
        </div>

        <div className="metric-stat-card">
          <div className="metric-stat-label">Evidence Category Coverage</div>
          <div className="metric-stat-val">
            {coveragePercent}%
            <span className="coverage-count">
              ({coveredCategories.filter((c) => c.isCovered).length}/{ALL_DISPUTE_CATEGORIES.length})
            </span>
          </div>
          <div className="coverage-mini-bar">
            <div 
              className="coverage-mini-bar-fill" 
              style={{ width: `${coveragePercent}%` }}
            ></div>
          </div>
        </div>

        <div className="metric-stat-card category-coverage-card">
          <div className="metric-stat-label">Dispute Pipeline Readiness</div>
          <div className="category-badges-row">
            {coveredCategories.map((c) => (
              <span 
                key={c.id} 
                className={`category-pill-status ${c.isCovered ? 'covered' : 'missing'}`}
                title={c.isCovered ? `${c.label}: Active pipeline` : `${c.label}: Missing integration`}
              >
                {c.isCovered ? <IconCheckCircle size={11} /> : <span className="uncovered-dot">○</span>}
                {c.label}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Control Bar: Search, Category Filter, Status Tabs & View Mode Switch */}
      <div className="integrations-control-bar">
        {/* Search */}
        <div className="search-input-wrapper">
          <IconSearch size={15} className="search-icon" />
          <input
            type="text"
            className="search-input"
            placeholder="Search integrations by name, provider, category..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button className="search-clear-btn" onClick={() => setSearchQuery('')}>×</button>
          )}
        </div>

        {/* Category Filter */}
        <div className="category-select-wrapper">
          <select 
            value={categoryFilter} 
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="category-select"
          >
            {EVIDENCE_CATEGORIES.map((cat) => (
              <option key={cat.id} value={cat.id}>{cat.label}</option>
            ))}
          </select>
        </div>

        {/* Status Filter Chips */}
        <div className="status-tabs-group">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.id || 'all'}
              className={`status-tab-btn ${statusFilter === f.id ? 'active' : ''}`}
              onClick={() => setStatusFilter(f.id)}
            >
              {f.label}
              {f.id === null && integrations.length > 0 && ` (${integrations.length})`}
            </button>
          ))}
        </div>

        {/* View Mode Toggle */}
        <div className="view-mode-toggle">
          <button
            className={`view-toggle-btn ${viewMode === 'grid' ? 'active' : ''}`}
            onClick={() => setViewMode('grid')}
            title="Grid Card View"
            aria-label="Grid View"
          >
            <IconGrid size={15} />
          </button>
          <button
            className={`view-toggle-btn ${viewMode === 'table' ? 'active' : ''}`}
            onClick={() => setViewMode('table')}
            title="Dense Table View"
            aria-label="Table View"
          >
            <IconTable size={15} />
          </button>
        </div>
      </div>

      {/* Error Notice */}
      {error && (
        <div className="integration-error-banner">
          <IconAlertTriangle size={18} className="error-icon" />
          <div>
            <strong>Unable to connect to server:</strong> {error}. Ensure backend is active on port 8000.
          </div>
        </div>
      )}

      {/* Loading State */}
      {loading && !error && (
        <div className="integrations-loading-box">
          <IconRefreshCw className="spin" size={26} />
          <p>Synchronizing active evidence connectors...</p>
        </div>
      )}

      {/* Clean Empty State */}
      {!loading && !error && integrations.length === 0 && !statusFilter && (
        <div className="integrations-empty-card">
          <div className="empty-icon-avatar">
            <IconZap size={28} />
          </div>
          <h2>No Evidence Integrations Configured</h2>
          <p className="empty-subtext">
            Connect your merchant systems — carrier APIs, SQL databases, proof-of-delivery CSVs, or webhooks — to automatically feed authoritative evidence into chargeback investigations.
          </p>
          <button
            className="btn-primary-lg"
            onClick={() => {
              setWizardPreset(null);
              setShowWizard(true);
            }}
          >
            <IconPlus size={18} />
            <span>Create Your First Integration</span>
          </button>
        </div>
      )}

      {/* Empty Filter Search State */}
      {!loading && !error && integrations.length > 0 && filteredIntegrations.length === 0 && (
        <div className="integrations-no-results">
          <p>No integrations matched your current filter criteria.</p>
          <button 
            className="btn-secondary-sm" 
            onClick={() => {
              setSearchQuery('');
              setCategoryFilter('all');
              setStatusFilter(null);
            }}
          >
            Reset Filters
          </button>
        </div>
      )}

      {/* Integration Grid / Table */}
      {!loading && filteredIntegrations.length > 0 && (
        <>
          {viewMode === 'grid' ? (
            <div className="integrations-grid">
              {filteredIntegrations.map((item) => (
                <IntegrationCard
                  key={item.id}
                  integration={item}
                  onDelete={() => handleDelete(item.id)}
                  onTest={() => handleTest(item.id)}
                  onToggleStatus={() => handleToggleStatus(item)}
                  onOpenDrawer={() => setSelectedIntegrationId(item.id)}
                />
              ))}

              {/* Add card button inside grid */}
              <div
                className="integration-add-placeholder-card"
                onClick={() => {
                  setWizardPreset(null);
                  setShowWizard(true);
                }}
                role="button"
                tabIndex={0}
              >
                <div className="add-icon-circle">
                  <IconPlus size={20} />
                </div>
                <span className="add-card-title">Add New Integration</span>
                <span className="add-card-subtitle">REST API · Database · CSV · Webhook</span>
              </div>
            </div>
          ) : (
            <IntegrationTable
              integrations={filteredIntegrations}
              onSelectIntegration={(id) => setSelectedIntegrationId(id)}
              onDelete={handleDelete}
              onTest={handleTest}
              onToggleStatus={handleToggleStatus}
            />
          )}
        </>
      )}

      {/* Slide-over Inspection Drawer */}
      {selectedIntegrationId && (
        <IntegrationDrawer
          integrationId={selectedIntegrationId}
          onClose={() => setSelectedIntegrationId(null)}
          onRefreshList={loadIntegrations}
        />
      )}

      {/* Add / Edit Wizard Modal */}
      {showWizard && (
        <IntegrationWizard
          preset={wizardPreset}
          onClose={() => {
            setShowWizard(false);
            setWizardPreset(null);
          }}
          onComplete={handleWizardComplete}
        />
      )}
    </div>
  );
}
