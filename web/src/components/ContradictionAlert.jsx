import { Badge } from './Badge';
import { IconAlertTriangle } from './Icons';

export function ContradictionAlert({ contradictions }) {
  if (!contradictions || contradictions.length === 0) return null;

  return (
    <section className="card card-danger">
      <h2 className="card-title" style={{ color: 'var(--color-danger)', borderBottomColor: 'var(--color-danger-border)' }}>
        <IconAlertTriangle className="card-title-icon" style={{ color: 'var(--color-danger)' }} />
        <span>Cross-Source Contradictions Detected ({contradictions.length})</span>
      </h2>
      {contradictions.map((c, i) => (
        <div key={i} className="contradiction-item">
          <div className="contradiction-header">
            <Badge type="danger">{c.impact?.toUpperCase() || 'HIGH'} IMPACT</Badge>
            {c.requires_human_review && (
              <Badge type="warning">Human Review Required</Badge>
            )}
          </div>
          <p className="contradiction-desc"><strong>{c.description}</strong></p>
          <div className="contradiction-claims">
            <div>
              <strong>Record A ({c.evidence_a_id}):</strong> {c.evidence_a_claim}
            </div>
            <div>
              <strong>Record B ({c.evidence_b_id}):</strong> {c.evidence_b_claim}
            </div>
          </div>
        </div>
      ))}
    </section>
  );
}
