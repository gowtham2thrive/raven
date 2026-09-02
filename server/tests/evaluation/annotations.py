"""
Ground Truth Annotations for RAVEN Evaluation.

Each case has a human-assigned expected outcome.
The evaluation runner compares RAVEN's actual output against these.

Ground truth fields:
    case_id:                    str
    expected_recommendation:    "contest" | "accept_loss" | "human_review"
    expected_contradictions:    int       (how many contradictions should be found)
    expected_missing:           list[str] (which evidence categories should be missing)
    contest_is_correct:         bool      (would contesting actually be the right call?)
    auto_submit_ok:             bool      (is auto-submit safe for this case?)
    notes:                      str

Profiles in synthetic data:
    CASE-00001..00015: A_STRONG        (strong evidence, all present)
    CASE-00016..00025: B_WEAK          (weak delivery proof)
    CASE-00026..00035: C_MISSING       (missing delivery/shipping)
    CASE-00036..00045: D_CONTRADICTORY (conflicting evidence)
    CASE-00046..00050: E_EDGE          (timezone/unusual data)
"""

from __future__ import annotations

ANNOTATIONS: list[dict] = [
    # ═══════════════════════════════════════════════════════════
    #  Profile A: STRONG — All evidence, signed delivery
    #  Expected: CONTEST, HIGH confidence, auto-submit OK
    # ═══════════════════════════════════════════════════════════
    {
        "case_id": "CASE-00001",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Perfect case: all evidence + signature + photo",
    },
    {
        "case_id": "CASE-00002",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Strong case with chronological timeline",
    },
    {
        "case_id": "CASE-00003",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Strong case — response draft should mention payment + delivery",
    },
    {
        "case_id": "CASE-00004",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Strong, mid-value case",
    },
    {
        "case_id": "CASE-00005",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Strong, higher-value case",
    },
    {
        "case_id": "CASE-00006",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Standard strong case",
    },
    {
        "case_id": "CASE-00007",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Standard strong case",
    },
    {
        "case_id": "CASE-00008",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Standard strong case",
    },
    {
        "case_id": "CASE-00009",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Standard strong case",
    },
    {
        "case_id": "CASE-00010",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Standard strong case",
    },
    {
        "case_id": "CASE-00011",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Standard strong case",
    },
    {
        "case_id": "CASE-00012",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Standard strong case",
    },
    {
        "case_id": "CASE-00013",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Standard strong case",
    },
    {
        "case_id": "CASE-00014",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Standard strong case",
    },
    {
        "case_id": "CASE-00015",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Standard strong case",
    },

    # ═══════════════════════════════════════════════════════════
    #  Profile B: WEAK — Delivery present but no signature
    #  Expected: CONTEST (score still high) but delivery unverified
    # ═══════════════════════════════════════════════════════════
    {
        "case_id": "CASE-00016",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,  # Weak delivery still gets high score with other evidence
        "notes": "Weak delivery proof but other evidence strong",
    },
    {
        "case_id": "CASE-00017",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Left at door, no signature",
    },
    {
        "case_id": "CASE-00018",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Weak delivery, standard case",
    },
    {
        "case_id": "CASE-00019",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Weak delivery, standard case",
    },
    {
        "case_id": "CASE-00020",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Weak delivery, standard case",
    },
    {
        "case_id": "CASE-00021",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Weak delivery, standard case",
    },
    {
        "case_id": "CASE-00022",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Weak delivery, standard case",
    },
    {
        "case_id": "CASE-00023",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Weak delivery, standard case",
    },
    {
        "case_id": "CASE-00024",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Weak delivery, standard case",
    },
    {
        "case_id": "CASE-00025",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Weak delivery, standard case",
    },

    # ═══════════════════════════════════════════════════════════
    #  Profile C: MISSING — No delivery or shipping evidence
    #  Expected: ACCEPT_LOSS or HUMAN_REVIEW, NOT auto-submit
    # ═══════════════════════════════════════════════════════════
    {
        "case_id": "CASE-00026",
        "expected_recommendation": "human_review",
        "expected_contradictions": 0,
        "expected_missing": ["delivery", "shipping"],
        "contest_is_correct": False,
        "auto_submit_ok": False,
        "notes": "No delivery/shipping — cannot prove delivery",
    },
    {
        "case_id": "CASE-00027",
        "expected_recommendation": "human_review",
        "expected_contradictions": 0,
        "expected_missing": ["delivery", "shipping"],
        "contest_is_correct": False,
        "auto_submit_ok": False,
        "notes": "Missing delivery gap",
    },
    {
        "case_id": "CASE-00028",
        "expected_recommendation": "human_review",
        "expected_contradictions": 0,
        "expected_missing": ["delivery", "shipping"],
        "contest_is_correct": False,
        "auto_submit_ok": False,
        "notes": "Missing key evidence",
    },
    {
        "case_id": "CASE-00029",
        "expected_recommendation": "human_review",
        "expected_contradictions": 0,
        "expected_missing": ["delivery", "shipping"],
        "contest_is_correct": False,
        "auto_submit_ok": False,
        "notes": "Missing key evidence",
    },
    {
        "case_id": "CASE-00030",
        "expected_recommendation": "human_review",
        "expected_contradictions": 0,
        "expected_missing": ["delivery", "shipping"],
        "contest_is_correct": False,
        "auto_submit_ok": False,
        "notes": "Missing key evidence",
    },
    {
        "case_id": "CASE-00031",
        "expected_recommendation": "human_review",
        "expected_contradictions": 0,
        "expected_missing": ["delivery", "shipping"],
        "contest_is_correct": False,
        "auto_submit_ok": False,
        "notes": "Missing key evidence",
    },
    {
        "case_id": "CASE-00032",
        "expected_recommendation": "human_review",
        "expected_contradictions": 0,
        "expected_missing": ["delivery", "shipping"],
        "contest_is_correct": False,
        "auto_submit_ok": False,
        "notes": "Missing key evidence",
    },
    {
        "case_id": "CASE-00033",
        "expected_recommendation": "human_review",
        "expected_contradictions": 0,
        "expected_missing": ["delivery", "shipping"],
        "contest_is_correct": False,
        "auto_submit_ok": False,
        "notes": "Missing key evidence",
    },
    {
        "case_id": "CASE-00034",
        "expected_recommendation": "human_review",
        "expected_contradictions": 0,
        "expected_missing": ["delivery", "shipping"],
        "contest_is_correct": False,
        "auto_submit_ok": False,
        "notes": "Missing key evidence",
    },
    {
        "case_id": "CASE-00035",
        "expected_recommendation": "human_review",
        "expected_contradictions": 0,
        "expected_missing": ["delivery", "shipping"],
        "contest_is_correct": False,
        "auto_submit_ok": False,
        "notes": "Missing key evidence",
    },

    # ═══════════════════════════════════════════════════════════
    #  Profile D: CONTRADICTORY — Conflicting evidence
    #  Expected: HUMAN_REVIEW, NOT auto-submit
    # ═══════════════════════════════════════════════════════════
    {
        "case_id": "CASE-00036",
        "expected_recommendation": "human_review",
        "expected_contradictions": 2,
        "expected_missing": [],
        "contest_is_correct": False,  # Contradictions make contest risky
        "auto_submit_ok": False,
        "notes": "Delivered vs returned_to_sender + customer confirmed then disputed",
    },
    {
        "case_id": "CASE-00037",
        "expected_recommendation": "human_review",
        "expected_contradictions": 2,
        "expected_missing": [],
        "contest_is_correct": False,
        "auto_submit_ok": False,
        "notes": "Contradictory evidence — human must review",
    },
    {
        "case_id": "CASE-00038",
        "expected_recommendation": "human_review",
        "expected_contradictions": 2,
        "expected_missing": [],
        "contest_is_correct": False,
        "auto_submit_ok": False,
        "notes": "Contradictory evidence",
    },
    {
        "case_id": "CASE-00039",
        "expected_recommendation": "human_review",
        "expected_contradictions": 2,
        "expected_missing": [],
        "contest_is_correct": False,
        "auto_submit_ok": False,
        "notes": "Contradictory evidence",
    },
    {
        "case_id": "CASE-00040",
        "expected_recommendation": "human_review",
        "expected_contradictions": 2,
        "expected_missing": [],
        "contest_is_correct": False,
        "auto_submit_ok": False,
        "notes": "Contradictory evidence",
    },
    {
        "case_id": "CASE-00041",
        "expected_recommendation": "human_review",
        "expected_contradictions": 2,
        "expected_missing": [],
        "contest_is_correct": False,
        "auto_submit_ok": False,
        "notes": "Contradictory evidence",
    },
    {
        "case_id": "CASE-00042",
        "expected_recommendation": "human_review",
        "expected_contradictions": 2,
        "expected_missing": [],
        "contest_is_correct": False,
        "auto_submit_ok": False,
        "notes": "Contradictory evidence",
    },
    {
        "case_id": "CASE-00043",
        "expected_recommendation": "human_review",
        "expected_contradictions": 2,
        "expected_missing": [],
        "contest_is_correct": False,
        "auto_submit_ok": False,
        "notes": "Contradictory evidence",
    },
    {
        "case_id": "CASE-00044",
        "expected_recommendation": "human_review",
        "expected_contradictions": 2,
        "expected_missing": [],
        "contest_is_correct": False,
        "auto_submit_ok": False,
        "notes": "Contradictory evidence",
    },
    {
        "case_id": "CASE-00045",
        "expected_recommendation": "human_review",
        "expected_contradictions": 2,
        "expected_missing": [],
        "contest_is_correct": False,
        "auto_submit_ok": False,
        "notes": "Contradictory evidence",
    },

    # ═══════════════════════════════════════════════════════════
    #  Profile E: EDGE — Timezone issues, unusual data
    #  Expected: varies, but investigation must complete
    # ═══════════════════════════════════════════════════════════
    {
        "case_id": "CASE-00046",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Edge case with timezone uncertainty — otherwise strong",
    },
    {
        "case_id": "CASE-00047",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Edge case — should still complete",
    },
    {
        "case_id": "CASE-00048",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Edge case — unusual but valid data",
    },
    {
        "case_id": "CASE-00049",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Edge case",
    },
    {
        "case_id": "CASE-00050",
        "expected_recommendation": "contest",
        "expected_contradictions": 0,
        "expected_missing": [],
        "contest_is_correct": True,
        "auto_submit_ok": True,
        "notes": "Edge case",
    },
]


def get_annotation(case_id: str) -> dict | None:
    """Look up ground truth for a case."""
    for a in ANNOTATIONS:
        if a["case_id"] == case_id:
            return a
    return None


def get_all_case_ids() -> list[str]:
    """Return all annotated case IDs."""
    return [a["case_id"] for a in ANNOTATIONS]
