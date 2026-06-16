"""
Harbor & Vine — Document classification engine.

Pattern-matches incoming real-estate document filenames against the
common doc taxonomy. Functional, not stubbed — used by the Documents
tab to bucket uploads + by the transaction coordinator's morning brief.
"""

import os
import re

# Order matters: more specific patterns first.
DOC_PATTERNS = [
    ("contract", [
        r"\bcontract\b", r"\bpurchase[_\-\s]?agreement\b",
        r"\bsales[_\-\s]?agreement\b", r"\bpsa\b",
    ]),
    ("disclosure", [
        r"\bdisclosure\b", r"\bseller[_\-\s]?disclosure\b",
        r"\blead[_\-\s]?paint\b", r"\bnhd\b", r"\bsphd\b",
    ]),
    ("inspection", [
        r"\binspection\b", r"\bhome[_\-\s]?inspection\b",
        r"\bpest[_\-\s]?report\b", r"\btermite\b", r"\bappraisal\b",
    ]),
    ("addendum", [
        r"\baddendum\b", r"\bamendment\b", r"\bcounter[_\-\s]?offer\b",
        r"\baddenda\b",
    ]),
    ("listing_agreement", [
        r"\blisting[_\-\s]?agreement\b", r"\bexclusive[_\-\s]?right\b",
    ]),
    ("escrow", [
        r"\bescrow\b", r"\btitle[_\-\s]?report\b", r"\bcd\b",
        r"\bclosing[_\-\s]?disclosure\b",
    ]),
    ("commission", [
        r"\bcommission\b", r"\bsplit\b", r"\b1099\b",
    ]),
    ("identification", [
        r"\bid\b", r"\bdriver[_\-\s]?license\b", r"\bw\-?9\b", r"\bw\-?2\b",
    ]),
]


class DocumentEngine:
    def __init__(self):
        # Pre-compile patterns once for speed.
        self._compiled = [
            (cat, [re.compile(p, re.IGNORECASE) for p in pats])
            for cat, pats in DOC_PATTERNS
        ]

    def classify(self, filename):
        """Return a category string for the given filename.

        Categories: contract, disclosure, inspection, addendum,
        listing_agreement, escrow, commission, identification, unknown.
        """
        if not filename:
            return "unknown"
        # Use just the base name so paths don't confuse the matcher.
        base = os.path.basename(filename)
        for cat, patterns in self._compiled:
            for p in patterns:
                if p.search(base):
                    return cat
        return "unknown"

    def classify_batch(self, filenames):
        """Classify a list. Returns dict {category: [filenames]}."""
        out = {}
        for fn in filenames:
            cat = self.classify(fn)
            out.setdefault(cat, []).append(fn)
        return out


def is_enabled():
    return True


if __name__ == "__main__":
    e = DocumentEngine()
    samples = [
        "248_cliffside_purchase_agreement.pdf",
        "lead_paint_disclosure_signed.pdf",
        "Bayview-home-inspection-report.pdf",
        "counter-offer-addendum-2.pdf",
        "agent_W9.pdf",
        "random_notes.txt",
    ]
    for s in samples:
        print(f"  {s} -> {e.classify(s)}")
