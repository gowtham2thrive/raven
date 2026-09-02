
const CANONICAL_FIELDS = {
  shipping: ['carrier', 'tracking_id', 'shipped_at', 'status', 'origin_city', 'destination_city'],
  delivery: ['delivered_at', 'signed_by', 'delivery_address', 'proof_type', 'photo_proof', 'source'],
  payment: ['payment_id', 'amount', 'currency', 'status', 'method', 'card_network', 'card_last4'],
  order: ['order_id', 'amount', 'receipt', 'status', 'item', 'quantity'],
  authentication: ['method', 'verified', 'device_known', 'ip_country'],
  communication: ['type', 'timestamp', 'channel', 'summary', 'direction'],
  refund: ['refund_id', 'amount', 'status', 'created_at'],
  service: ['service_type', 'status', 'description'],
  policy: ['policy_name', 'accepted_at', 'version'],
  device: ['device_id', 'fingerprint', 'ip_address', 'user_agent'],
  other: ['key', 'value', 'description'],
};

const TRANSFORMS = [
  { id: '', label: 'None' },
  { id: 'parse_date', label: 'Parse Date' },
  { id: 'to_lowercase', label: 'Lowercase' },
  { id: 'to_uppercase', label: 'Uppercase' },
  { id: 'strip', label: 'Trim Whitespace' },
  { id: 'to_int', label: 'To Integer' },
  { id: 'to_float', label: 'To Float' },
  { id: 'boolean', label: 'To Boolean' },
  { id: 'paise_to_rupees', label: 'Paise → Rupees' },
];

export function FieldMappingEditor({ sourceFields = [], mappings = [], onChange, evidenceCategory = 'shipping' }) {
  const targetFields = CANONICAL_FIELDS[evidenceCategory] || CANONICAL_FIELDS.other;

  const addMapping = () => {
    onChange([
      ...mappings,
      {
        source_field: sourceFields[0] || '',
        target_field: targetFields[0] || '',
        transform: null,
        is_required: false,
      },
    ]);
  };

  const updateMapping = (index, key, value) => {
    const updated = [...mappings];
    updated[index] = { ...updated[index], [key]: value };
    onChange(updated);
  };

  const removeMapping = (index) => {
    onChange(mappings.filter((_, i) => i !== index));
  };

  // Auto-suggest mappings based on field name similarity
  const autoMap = () => {
    const suggested = [];
    for (const source of sourceFields) {
      const sourceLower = source.toLowerCase().replace(/[^a-z0-9]/g, '_');
      const match = targetFields.find(t => {
        const targetLower = t.toLowerCase();
        return sourceLower === targetLower
          || sourceLower.includes(targetLower)
          || targetLower.includes(sourceLower);
      });
      if (match) {
        suggested.push({
          source_field: source,
          target_field: match,
          transform: null,
          is_required: false,
        });
      }
    }
    if (suggested.length > 0) {
      onChange(suggested);
    }
  };

  return (
    <div className="field-mapping-editor">
      <div className="field-mapping-header">
        <span>Source Field</span>
        <span>→ Target Field</span>
        <span>Transform</span>
        <span></span>
      </div>

      {mappings.length === 0 && (
        <div style={{
          padding: '1.5rem',
          textAlign: 'center',
          color: 'var(--text-tertiary, #52525b)',
          fontSize: '0.78rem',
        }}>
          No field mappings configured.
          {sourceFields.length > 0 && (
            <>
              {' '}
              <button
                onClick={autoMap}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--primary, #818cf8)',
                  cursor: 'pointer',
                  fontSize: '0.78rem',
                  textDecoration: 'underline',
                  fontFamily: 'inherit',
                }}
              >
                Auto-suggest mappings
              </button>
            </>
          )}
        </div>
      )}

      {mappings.map((mapping, index) => (
        <div key={index} className="field-mapping-row">
          {sourceFields.length > 0 ? (
            <select
              value={mapping.source_field}
              onChange={e => updateMapping(index, 'source_field', e.target.value)}
            >
              <option value="">Select source field</option>
              {sourceFields.map(f => (
                <option key={f} value={f}>{f}</option>
              ))}
            </select>
          ) : (
            <input
              type="text"
              placeholder="source.field.path"
              value={mapping.source_field}
              onChange={e => updateMapping(index, 'source_field', e.target.value)}
            />
          )}

          <select
            value={mapping.target_field}
            onChange={e => updateMapping(index, 'target_field', e.target.value)}
          >
            <option value="">Select target field</option>
            {targetFields.map(f => (
              <option key={f} value={f}>{f}</option>
            ))}
          </select>

          <select
            value={mapping.transform || ''}
            onChange={e => updateMapping(index, 'transform', e.target.value || null)}
          >
            {TRANSFORMS.map(t => (
              <option key={t.id} value={t.id}>{t.label}</option>
            ))}
          </select>

          <div className="field-mapping-actions">
            <button onClick={() => removeMapping(index)} title="Remove mapping">✕</button>
          </div>
        </div>
      ))}

      <button className="field-mapping-add" onClick={addMapping}>
        + Add Field Mapping
      </button>
    </div>
  );
}
