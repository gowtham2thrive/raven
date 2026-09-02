/**
 * Generate a clean, professional PDF of the dispute defense package.
 *
 * Produces a structured document containing:
 * - Case identification and dispute metadata
 * - Assessment summary with confidence score
 * - Evidence verification matrix
 * - Contradictions (if any)
 * - Reconstructed timeline
 * - Full rebuttal letter
 * - Evidence enclosures summary
 *
 * Edge cases handled:
 * - Null/undefined/empty fields at every level
 * - Missing caseData or caseData.case entirely
 * - Empty evidence, timeline, contradictions arrays
 * - Missing assessment object
 * - Missing responseDraft
 * - Very long text content (multi-page wrapping)
 * - Unicode characters that jsPDF cannot render (e.g. ₹)
 * - Zero-amount disputes
 * - Missing timestamps / timezone information
 *
 * @param {object} params
 * @param {object} params.caseData - Full case data ({ case, evidence, timeline, contradictions, assessment })
 * @param {string} params.responseDraft - The compiled rebuttal text
 */
import { jsPDF } from 'jspdf';

/* ── Colors ─────────────────────────────────────────────────────── */
const C = {
  dark:       [15, 23, 42],
  body:       [51, 65, 85],
  muted:      [100, 116, 139],
  light:      [148, 163, 184],
  accent:     [37, 99, 235],
  green:      [22, 163, 74],
  red:        [220, 38, 38],
  amber:      [180, 110, 0],
  white:      [255, 255, 255],
  rowAlt:     [248, 250, 252],
  cardBg:     [243, 244, 246],
  border:     [226, 232, 240],
  headerBg:   [15, 23, 42],
  headerSub:  [148, 163, 184],
  warnBg:     [254, 252, 232],
};

/* ── Layout ─────────────────────────────────────────────────────── */
const ML = 18;                         // margin left
const MR = 18;                         // margin right
const PW = 210;                        // page width (A4)
const CW = PW - ML - MR;              // content width
const MT = 16;                         // margin top (after page break)
const PH = 297;                        // page height
const BOTTOM = PH - 16;               // usable bottom before footer

/* ── Helpers ────────────────────────────────────────────────────── */

/** Safely coerce any value to a display string. */
function s(value, fallback = '\u2014') {
  if (value === null || value === undefined || value === '') return fallback;
  return String(value);
}

/** Format paise to INR. Uses "Rs." because jsPDF cannot render the ₹ glyph. */
function rupees(paise) {
  if (paise === null || paise === undefined || isNaN(paise)) return '\u2014';
  const r = Number(paise) / 100;
  return `Rs. ${r.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
}

/** Format an ISO date string to readable format. */
function fmtDate(v, time = false) {
  if (!v) return '\u2014';
  try {
    const d = new Date(v);
    if (isNaN(d.getTime())) return '\u2014';
    const o = { day: 'numeric', month: 'short', year: 'numeric' };
    if (time) { o.hour = '2-digit'; o.minute = '2-digit'; }
    return d.toLocaleDateString('en-IN', o);
  } catch { return '\u2014'; }
}

/** Make raw status strings human-readable: "not_applicable" → "N/A", etc. */
function prettyStatus(raw) {
  if (!raw) return '\u2014';
  const map = {
    available: 'Available',
    missing: 'Missing',
    conflicting: 'Conflicting',
    unverified: 'Unverified',
    not_applicable: 'N/A',
    ingestion_error: 'Error',
    created: 'Created',
    under_review: 'Under Review',
    approved: 'Approved',
    submitted: 'Submitted',
    auto_submitted: 'Auto-Submitted',
    completed: 'Completed',
    failed: 'Failed',
  };
  const key = String(raw).toLowerCase().trim();
  return map[key] || raw.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

/** Wrap text to fit maxWidth. */
function wrap(doc, text, maxWidth) {
  if (!text) return [''];
  return doc.splitTextToSize(String(text), maxWidth);
}

/** Color for evidence status. */
function statusColor(raw) {
  const key = String(raw || '').toLowerCase();
  if (key === 'available') return C.green;
  if (key === 'missing') return C.red;
  if (key === 'conflicting' || key === 'unverified') return C.amber;
  return C.muted;
}

/* ── Page management ────────────────────────────────────────────── */

function footer(doc, caseId) {
  const n = doc.internal.getNumberOfPages();
  doc.setDrawColor(...C.border);
  doc.setLineWidth(0.15);
  doc.line(ML, PH - 11, PW - MR, PH - 11);
  doc.setFontSize(6.5);
  doc.setTextColor(...C.light);
  doc.text(`RAVEN Defense Package${caseId ? ` \u2014 ${caseId}` : ''}`, ML, PH - 7);
  doc.text(`Page ${n}`, PW - MR, PH - 7, { align: 'right' });
}

function ensure(doc, y, need, caseId) {
  if (y + need > BOTTOM) {
    doc.addPage();
    footer(doc, caseId);
    return MT;
  }
  return y;
}

/* ── Drawing primitives ─────────────────────────────────────────── */

function sectionTitle(doc, title, y, caseId) {
  y = ensure(doc, y, 14, caseId);
  doc.setFillColor(...C.accent);
  doc.rect(ML, y, 2, 6, 'F');
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(10.5);
  doc.setTextColor(...C.dark);
  doc.text(s(title), ML + 6, y + 5);
  return y + 12;
}

function divider(doc, y) {
  doc.setDrawColor(...C.border);
  doc.setLineWidth(0.15);
  doc.line(ML, y, PW - MR, y);
  return y + 5;
}

function kvPair(doc, label, value, x, y, lw = 30) {
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(8);
  doc.setTextColor(...C.muted);
  doc.text(s(label), x, y);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(8);
  doc.setTextColor(...C.dark);
  doc.text(s(value), x + lw, y);
}

/* ═══════════════════════════════════════════════════════════════════
   Main Export
   ═══════════════════════════════════════════════════════════════════ */

export function generateDefensePdf({ caseData, responseDraft }) {
  const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });

  const ci = caseData?.case || {};
  const evidence = Array.isArray(caseData?.evidence) ? caseData.evidence : [];
  const timeline = Array.isArray(caseData?.timeline) ? caseData.timeline : [];
  const contradictions = Array.isArray(caseData?.contradictions) ? caseData.contradictions : [];
  const assessment = caseData?.assessment || null;
  const assessData = assessment?.data || null;
  const available = evidence.filter(e => e?.status === 'available');
  const caseId = s(ci.case_id, '');
  const draft = s(responseDraft, '');

  let y = MT;
  footer(doc, caseId);

  // ── HEADER ─────────────────────────────────────────────────────
  const HH = 28;
  doc.setFillColor(...C.headerBg);
  doc.rect(0, 0, PW, HH, 'F');

  doc.setFont('helvetica', 'bold');
  doc.setFontSize(13);
  doc.setTextColor(...C.white);
  doc.text('DISPUTE DEFENSE PACKAGE', ML, 12);

  doc.setFont('helvetica', 'normal');
  doc.setFontSize(7.5);
  doc.setTextColor(...C.headerSub);
  doc.text('Evidence-Based Rebuttal for Chargeback Representment', ML, 18);

  if (caseId) {
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(8.5);
    doc.setTextColor(...C.white);
    doc.text(caseId, PW - MR, 12, { align: 'right' });
  }
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(7);
  doc.setTextColor(...C.headerSub);
  doc.text(`Generated ${fmtDate(new Date(), true)}`, PW - MR, 18, { align: 'right' });

  doc.setFillColor(...C.accent);
  doc.rect(0, HH, PW, 0.6, 'F');

  y = HH + 8;

  // ── CASE IDENTIFICATION ────────────────────────────────────────
  y = sectionTitle(doc, 'Case Identification', y, caseId);

  const half = CW / 2;
  const pairs = [
    ['Case ID',      s(ci.case_id),            'Dispute ID',   s(ci.rzp_dispute_id)],
    ['Payment ID',   s(ci.rzp_payment_id),     'Order ID',     s(ci.rzp_order_id)],
    ['Amount',       rupees(ci.amount),         'Currency',     s(ci.currency, 'INR')],
    ['Reason Code',  s(ci.reason_code),         'Phase',        prettyStatus(ci.dispute_phase)],
    ['Status',       prettyStatus(ci.status),   'Respond By',   fmtDate(ci.respond_by)],
  ];

  pairs.forEach(([lL, vL, lR, vR]) => {
    y = ensure(doc, y, 6, caseId);
    kvPair(doc, lL, vL, ML, y);
    kvPair(doc, lR, vR, ML + half, y);
    y += 5.5;
  });

  // Customer claim
  const claim = s(ci.reason_description, '');
  if (claim && claim !== '\u2014') {
    y += 1;
    y = ensure(doc, y, 12, caseId);
    const lines = wrap(doc, `\u201C${claim}\u201D`, CW - 10);
    const bh = lines.length * 3.8 + 4;
    doc.setFillColor(...C.cardBg);
    doc.roundedRect(ML, y - 1.5, CW, bh, 1.5, 1.5, 'F');
    doc.setFont('helvetica', 'italic');
    doc.setFontSize(8);
    doc.setTextColor(...C.body);
    lines.forEach((line, i) => doc.text(line, ML + 5, y + 2 + i * 3.8));
    y += bh + 2;
  }

  y += 3;
  y = divider(doc, y);

  // ── ASSESSMENT ─────────────────────────────────────────────────
  if (assessment) {
    y = sectionTitle(doc, 'Investigation Assessment', y, caseId);

    // Badge
    y = ensure(doc, y, 10, caseId);
    const rec = s(assessment.recommendation, 'unknown');
    const badges = {
      contest:      { text: 'CONTEST',              color: C.green },
      accept_loss:  { text: 'ACCEPT LOSS',           color: C.red },
      human_review: { text: 'HUMAN REVIEW REQUIRED', color: C.amber },
    };
    const badge = badges[rec] || { text: rec.toUpperCase(), color: C.muted };
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(7.5);
    const bw = Math.max(doc.getTextWidth(badge.text) + 10, 30);
    doc.setFillColor(...badge.color);
    doc.roundedRect(ML, y - 1.5, bw, 7, 1.2, 1.2, 'F');
    doc.setTextColor(...C.white);
    doc.text(badge.text, ML + 5, y + 3);
    y += 11;

    // Metrics
    const score = assessment.score != null ? `${(assessment.score * 100).toFixed(0)}%` : '\u2014';
    const strength = prettyStatus(assessment.strength);
    const coverage = `${available.length} / ${evidence.length}`;
    const mw = CW / 3;

    y = ensure(doc, y, 12, caseId);
    [['Confidence Score', score], ['Case Strength', strength], ['Evidence Coverage', coverage]].forEach(([lab, val], i) => {
      const mx = ML + i * mw;
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(7);
      doc.setTextColor(...C.muted);
      doc.text(lab, mx, y);
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(10);
      doc.setTextColor(...C.dark);
      doc.text(val, mx, y + 5.5);
    });
    y += 12;

    // Reasons
    const reasons = assessData?.reasons || [];
    if (reasons.length > 0) {
      reasons.forEach(r => {
        const txt = s(r, '');
        if (!txt || txt === '\u2014') return;
        const lines = wrap(doc, txt, CW - 8);
        lines.forEach(line => {
          y = ensure(doc, y, 4.5, caseId);
          doc.setFont('helvetica', 'normal');
          doc.setFontSize(7.5);
          doc.setTextColor(...C.body);
          doc.text(`\u2022  ${line}`, ML + 2, y);
          y += 3.8;
        });
      });
      y += 2;
    }

    y = divider(doc, y);
  }

  // ── EVIDENCE TABLE ─────────────────────────────────────────────
  if (evidence.length > 0) {
    y = sectionTitle(doc, 'Evidence Verification', y, caseId);

    // Column widths — give Status less room since we shortened the labels
    const cw = [28, 26, 18, CW - 72];
    const hdr = ['Category', 'Source', 'Status', 'Summary'];

    y = ensure(doc, y, 8, caseId);
    doc.setFillColor(...C.headerBg);
    doc.rect(ML, y - 1.5, CW, 6.5, 'F');
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(7);
    doc.setTextColor(...C.white);
    let hx = ML + 2;
    hdr.forEach((h, i) => { doc.text(h, hx, y + 2.5); hx += cw[i]; });
    y += 7;

    evidence.forEach((ev, idx) => {
      if (!ev) return;
      const cat = s(ev.category).toUpperCase();
      const src = s(ev.source_system);
      const st = prettyStatus(ev.status);
      const sum = s(ev.summary);

      const sumLines = wrap(doc, sum, cw[3] - 4);
      const rh = Math.max(5.5, sumLines.length * 3.5 + 1.5);

      y = ensure(doc, y, rh + 0.5, caseId);

      if (idx % 2 === 0) {
        doc.setFillColor(...C.rowAlt);
        doc.rect(ML, y - 1.5, CW, rh, 'F');
      }

      doc.setFontSize(7);
      let rx = ML + 2;

      doc.setFont('helvetica', 'bold');
      doc.setTextColor(...C.dark);
      doc.text(cat.substring(0, 16), rx, y + 1.5);
      rx += cw[0];

      doc.setFont('helvetica', 'normal');
      doc.setTextColor(...C.body);
      doc.text(src.substring(0, 16), rx, y + 1.5);
      rx += cw[1];

      doc.setFont('helvetica', 'bold');
      doc.setTextColor(...statusColor(ev.status));
      doc.text(st, rx, y + 1.5);
      rx += cw[2];

      doc.setFont('helvetica', 'normal');
      doc.setTextColor(...C.body);
      sumLines.forEach((line, li) => doc.text(line, rx, y + 1.5 + li * 3.5));

      y += rh;
    });

    y += 4;
    y = divider(doc, y);
  }

  // ── CONTRADICTIONS ─────────────────────────────────────────────
  if (contradictions.length > 0) {
    y = sectionTitle(doc, 'Cross-Source Contradictions', y, caseId);

    contradictions.forEach((c, idx) => {
      if (!c) return;
      y = ensure(doc, y, 18, caseId);

      const impact = s(c.impact, 'unknown').toUpperCase();
      doc.setFillColor(...C.warnBg);
      doc.roundedRect(ML, y - 1.5, CW, 6, 1, 1, 'F');
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(7.5);
      doc.setTextColor(...C.red);
      doc.text(`#${idx + 1}  ${impact} IMPACT`, ML + 3, y + 2);
      y += 7;

      const desc = s(c.description, '');
      if (desc && desc !== '\u2014') {
        const lines = wrap(doc, desc, CW - 8);
        lines.forEach(line => {
          y = ensure(doc, y, 4, caseId);
          doc.setFont('helvetica', 'normal');
          doc.setFontSize(7.5);
          doc.setTextColor(...C.body);
          doc.text(line, ML + 3, y);
          y += 3.5;
        });
        y += 1;
      }

      // Claims comparison
      const a = s(c.evidence_a_claim, '');
      const b = s(c.evidence_b_claim, '');
      if ((a && a !== '\u2014') || (b && b !== '\u2014')) {
        y = ensure(doc, y, 10, caseId);
        const aLines = wrap(doc, `A: ${a}`, CW - 14);
        const bLines = wrap(doc, `B: ${b}`, CW - 14);
        const blockH = (aLines.length + bLines.length) * 3.5 + 4;
        doc.setFillColor(...C.cardBg);
        doc.roundedRect(ML + 2, y - 1, CW - 4, blockH, 1, 1, 'F');
        doc.setFont('helvetica', 'normal');
        doc.setFontSize(7);
        doc.setTextColor(...C.body);
        [...aLines, ...bLines].forEach(line => {
          doc.text(line, ML + 5, y + 1.5);
          y += 3.5;
        });
        y += 2;
      }

      if (c.requires_human_review) {
        y = ensure(doc, y, 5, caseId);
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(6.5);
        doc.setTextColor(...C.amber);
        doc.text('Requires human review', ML + 3, y);
        y += 4;
      }
      y += 2;
    });

    y = divider(doc, y);
  }

  // ── TIMELINE ───────────────────────────────────────────────────
  if (timeline.length > 0) {
    y = sectionTitle(doc, 'Reconstructed Timeline', y, caseId);

    timeline.forEach((ev, idx) => {
      if (!ev) return;
      const label = s(ev.label || ev.event);
      const ts = fmtDate(ev.timestamp_utc || ev.timestamp, true);
      const src = s(ev.source_system || ev.source, '');

      const labelLines = wrap(doc, label, CW - 60);
      const rh = Math.max(5, labelLines.length * 3.5 + 1);

      y = ensure(doc, y, rh + 2, caseId);

      // Dot + connector
      doc.setFillColor(...C.accent);
      doc.circle(ML + 2, y + 1, 0.8, 'F');
      if (idx < timeline.length - 1) {
        doc.setDrawColor(...C.border);
        doc.setLineWidth(0.2);
        doc.line(ML + 2, y + 2.2, ML + 2, y + rh + 1);
      }

      // Timestamp
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(6.5);
      doc.setTextColor(...C.muted);
      doc.text(ts, ML + 6, y + 1.5);

      // Label
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(7.5);
      doc.setTextColor(...C.dark);
      labelLines.forEach((line, li) => doc.text(line, ML + 42, y + 1.5 + li * 3.5));

      // Source
      if (src && src !== '\u2014') {
        doc.setFontSize(6);
        doc.setTextColor(...C.light);
        doc.text(`[${src}]`, PW - MR, y + 1.5, { align: 'right' });
      }

      if (ev.timezone_confident === false) {
        doc.setFont('helvetica', 'italic');
        doc.setFontSize(5.5);
        doc.setTextColor(...C.amber);
        doc.text('timezone uncertain', ML + 42, y + 1.5 + labelLines.length * 3.5);
      }

      y += rh + 1.5;
    });

    y += 3;
    y = divider(doc, y);
  }

  // ── REBUTTAL ───────────────────────────────────────────────────
  if (draft && draft !== '\u2014') {
    y = sectionTitle(doc, 'Rebuttal Statement', y, caseId);

    const paras = draft.split('\n\n');
    paras.forEach(p => {
      const t = p.trim();
      if (!t) return;
      const isSub = /^[A-Z][A-Z _]+:/.test(t);
      const lines = wrap(doc, t, CW - 4);
      lines.forEach((line, li) => {
        y = ensure(doc, y, 4.5, caseId);
        if (isSub && li === 0) {
          doc.setFont('helvetica', 'bold');
          doc.setFontSize(8.5);
          doc.setTextColor(...C.dark);
        } else {
          doc.setFont('helvetica', 'normal');
          doc.setFontSize(8);
          doc.setTextColor(...C.body);
        }
        doc.text(line, ML + 2, y);
        y += 3.8;
      });
      y += 2;
    });

    y += 1;
    y = divider(doc, y);
  }

  // ── ENCLOSURES ─────────────────────────────────────────────────
  if (available.length > 0) {
    y = ensure(doc, y, 12, caseId);
    y = sectionTitle(doc, `Evidence Enclosures (${available.length})`, y, caseId);

    available.forEach(ev => {
      if (!ev) return;
      y = ensure(doc, y, 5.5, caseId);

      doc.setFont('helvetica', 'bold');
      doc.setFontSize(7);
      doc.setTextColor(...C.green);
      doc.text('\u2713', ML + 2, y);

      doc.setTextColor(...C.dark);
      doc.text(s(ev.category, '').toUpperCase(), ML + 7, y);

      doc.setFont('helvetica', 'normal');
      doc.setTextColor(...C.body);
      const sum = s(ev.summary, '');
      doc.text(sum.length > 55 ? sum.substring(0, 52) + '...' : sum, ML + 35, y);

      const ref = s(ev.source_record_id || ev.evidence_id, '');
      if (ref && ref !== '\u2014') {
        doc.setFontSize(6);
        doc.setTextColor(...C.light);
        doc.text(ref, PW - MR, y, { align: 'right' });
      }

      y += 4.5;
    });
  }

  // ── CLOSING STAMP ──────────────────────────────────────────────
  y += 4;
  y = ensure(doc, y, 12, caseId);
  y = divider(doc, y);

  doc.setFont('helvetica', 'italic');
  doc.setFontSize(6.5);
  doc.setTextColor(...C.light);
  doc.text(
    'This defense package was compiled by RAVEN and verified against canonical merchant records.',
    ML, y
  );
  y += 3;
  doc.text(
    'All evidence references are traceable to source systems. Intended for chargeback representment.',
    ML, y
  );

  // ── Save ──
  doc.save(`RAVEN_Defense_${caseId || 'unknown'}_${new Date().toISOString().slice(0, 10)}.pdf`);
}
