import { useState, useEffect, useRef } from 'react';
import { fetchModels } from '../api/client';
import { IconCpu, IconCheck, IconChevronDown } from './Icons';

export function ModelPicker({ selectedModel, onSelectModel }) {
  const [models, setModels] = useState([]);
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  useEffect(() => {
    fetchModels()
      .then(data => {
        if (data?.models?.length) {
          setModels(data.models);
          if (!selectedModel && data.default && onSelectModel) {
            onSelectModel(data.default);
          }
        }
      })
      .catch(console.error);
  }, [selectedModel, onSelectModel]);

  useEffect(() => {
    function handleClickOutside(e) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const active = models.find(m => m.id === selectedModel) || models[0] || {
    id: selectedModel || 'gemini-3.6-flash',
    name: 'Gemini 3.6 Flash',
    tier: 'Free / Economy',
    badge: 'Recommended',
    price: 'Free Tier / $0.10',
    speed: 'Ultra Fast (~1.5s)',
  };

  const getBadgeClass = (badge) => {
    if (badge === 'Recommended') return 'model-option-badge-recommended';
    if (badge === 'Lowest Cost') return 'model-option-badge-budget';
    if (badge === 'Next-Gen') return 'model-option-badge-nextgen';
    if (badge === 'High Value') return 'model-option-badge-value';
    return 'model-option-badge-recommended';
  };

  const cleanText = (str) => {
    if (!str) return '';
    return str.replace(/[\u{1F300}-\u{1F9FF}]|[\u{2600}-\u{26FF}]|[\u{2700}-\u{27BF}]/gu, '').trim();
  };

  return (
    <div className={`model-picker-wrapper ${isOpen ? 'open' : ''}`} ref={dropdownRef}>
      <button
        type="button"
        className="model-select-btn"
        onClick={() => setIsOpen(!isOpen)}
        title="Select AI Model according to speed, price & reasoning capability"
      >
        <IconCpu className="model-select-btn-icon" size={16} />
        <span>{active.name}</span>
        <span className={`model-option-badge ${getBadgeClass(active.badge)}`}>
          {active.tier}
        </span>
        <IconChevronDown className="model-select-btn-chevron" size={12} />
      </button>

      {isOpen && (
        <div className="model-dropdown">
          <div className="model-dropdown-header">
            <div className="model-dropdown-title">
              <span>Select Investigation Model</span>
              <span className="model-dropdown-live">Live API</span>
            </div>
            <div className="model-dropdown-subtitle">
              Choose reasoning model according to cost & dispute complexity
            </div>
          </div>

          <div className="model-options-list">
            {models.map(m => (
              <div
                key={m.id}
                className={`model-option ${m.id === selectedModel ? 'selected' : ''}`}
                onClick={() => {
                  onSelectModel(m.id);
                  setIsOpen(false);
                }}
              >
                <div className="model-option-header">
                  <span className="model-option-name">
                    {m.id === selectedModel && <IconCheck size={14} color="var(--brand-primary)" />}
                    <span>{m.name}</span>
                  </span>
                  <span className={`model-option-badge ${getBadgeClass(m.badge)}`}>
                    {m.badge}
                  </span>
                </div>

                <div className="model-option-meta">
                  <span className="model-option-price">{m.price}</span>
                  <span>•</span>
                  <span className="model-option-speed">{cleanText(m.speed)}</span>
                </div>

                <div className="model-option-desc">
                  {cleanText(m.description)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
