import { useState } from 'react';
import { 
  IconCopy, 
  IconCheck, 
  IconSend, 
  IconShieldCheck, 
  IconFileText, 
  IconCheckCircle, 
  IconLayers,
  IconLock,
  IconDownload
} from './Icons';
import { generateDefensePdf } from '../utils/generateDefensePdf';

export function ResponsePackageCard({ 
  caseData, 
  responseDraft, 
  onSubmitContest = null, 
  actionLoading = false 
}) {
  const [copied, setCopied] = useState(false);

  const copyResponseDraft = () => {
    if (responseDraft) {
      navigator.clipboard.writeText(responseDraft);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const caseInfo = caseData?.case;
  const evidence = caseData?.evidence || [];
  const availableEvidence = evidence.filter(e => e.status === 'available');
  const amountFormatted = caseInfo ? `₹${((caseInfo.amount || 0) / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : '—';

  return (
    <section className="card response-package-card">
      {/* Official Rebuttal Header */}
      <div className="rebuttal-header">
        <div className="rebuttal-header-left">
          <div className="rebuttal-tag">
            <IconShieldCheck size={14} />
            <span>Dispute Rebuttal Document</span>
          </div>
          <h2 className="rebuttal-title" style={{ margin: '4px 0 6px' }}>Evidence Defense Package</h2>
          <div className="rebuttal-meta-row">
            <span>Case: <strong>{caseInfo?.case_id}</strong></span>
            <span>•</span>
            <span>Gateway ID: <strong>{caseInfo?.rzp_dispute_id || 'disp_unassigned'}</strong></span>
            <span>•</span>
            <span>Disputed: <strong>{amountFormatted}</strong></span>
          </div>
        </div>

        <div className="rebuttal-header-actions">
          {responseDraft && (
            <>
              <button
                type="button"
                className="btn btn-outline btn-sm"
                onClick={() => generateDefensePdf({ caseData, responseDraft })}
                title="Download defense package as PDF"
              >
                <IconDownload size={14} />
                <span>Download PDF</span>
              </button>
              <button
                type="button"
                className={`btn btn-primary btn-sm ${copied ? 'copied' : ''}`}
                onClick={copyResponseDraft}
                title="Copy rebuttal draft to clipboard"
              >
                {copied ? <IconCheck size={14} /> : <IconCopy size={14} />}
                <span>{copied ? 'Copied' : 'Copy Rebuttal Text'}</span>
              </button>
            </>
          )}
        </div>
      </div>

      {/* Formal Defense Letter Body */}
      {responseDraft ? (
        <div className="rebuttal-body-paper">
          <div className="rebuttal-letter-content">
            {responseDraft.split('\n\n').map((paragraph, index) => (
              <p key={index} className="rebuttal-paragraph">
                {paragraph}
              </p>
            ))}
          </div>

          {/* Enclosure References Table */}
          {availableEvidence.length > 0 && (
            <div className="rebuttal-enclosures">
              <div className="rebuttal-enclosures-title">
                <IconLayers size={14} />
                <span>Verified Evidentiary Enclosures ({availableEvidence.length})</span>
              </div>
              <div className="rebuttal-enclosures-list">
                {availableEvidence.map((ev) => (
                  <div key={ev.evidence_id} className="rebuttal-enclosure-item">
                    <IconCheckCircle size={14} className="rebuttal-enclosure-icon" />
                    <div className="rebuttal-enclosure-details">
                      <span className="rebuttal-enclosure-name">{ev.category.toUpperCase()}: {ev.summary}</span>
                      <span className="rebuttal-enclosure-id">Ref #{ev.source_record_id || ev.evidence_id}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Submission Sign-off */}
          <div className="rebuttal-signoff">
            <div className="rebuttal-signoff-left">
              <IconLock size={15} />
              <span>Compiled rebuttal package verified against canonical merchant records for Razorpay representment.</span>
            </div>
            {caseInfo?.status === 'approved' && onSubmitContest && (
              <button
                type="button"
                className="btn btn-success btn-sm"
                onClick={onSubmitContest}
                disabled={actionLoading}
              >
                <IconSend size={14} />
                <span>{actionLoading ? 'Submitting...' : 'Submit to Razorpay Gateway'}</span>
              </button>
            )}
          </div>
        </div>
      ) : (
        <div className="empty-response-box">
          <IconFileText size={32} style={{ opacity: 0.4, margin: '0 auto 12px' }} />
          <p>No response draft compiled yet. Run an investigation to generate a formal rebuttal document.</p>
        </div>
      )}
    </section>
  );
}
