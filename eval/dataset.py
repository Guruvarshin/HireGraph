"""Labeled evaluation dataset for the RAG layer.

A small synthetic corpus of company-rubric chunks plus queries with
ground-truth relevant document ids. This lets us measure retrieval quality
(recall@k, precision@k, MRR) against a known answer key, and generation
quality (faithfulness, answer relevance) via an LLM judge.
"""

# id -> chunk text (the "knowledge base")
CORPUS: dict[str, str] = {
    "d1": "Senior Engineer (5+ years): designs systems, leads technical decisions for a squad, "
          "mentors junior engineers, deep expertise in distributed systems. Shortlist threshold 70.",
    "d2": "Junior Engineer (0-2 years): proficient in at least one language, understands core data "
          "structures, can ship small features with code review. Shortlist threshold 55.",
    "d3": "Mid Engineer (2-5 years): owns features end to end independently, strong in one domain, "
          "writes clean testable code. Shortlist threshold 65.",
    "d4": "Interview process: Round 1 technical screen 45 min, Round 2 system design 60 min for "
          "senior and above, Round 3 behavioral 45 min, Round 4 hiring manager 30 min.",
    "d5": "Compensation India (INR per annum): Junior 7-13 LPA, Mid 14-22 LPA, Senior 24-38 LPA, "
          "Staff 40-58 LPA. ESOPs granted for mid level and above.",
    "d6": "Compensation USA (USD per annum): Junior 80-100k, Mid 110-140k, Senior 145-180k, "
          "Staff 185-230k. Stock options vest over 4 years with a 1 year cliff.",
    "d7": "Bias rules: do not penalize candidates for employment gaps under 18 months, bootcamp "
          "education, foreign university names, or short stints at failed startups.",
    "d8": "Staff Engineer (8+ years): cross-team technical leadership, drives architecture decisions "
          "org-wide, writes RFCs, rarely writes code. Shortlist threshold 78.",
}

# query -> set of ground-truth relevant doc ids
QUERIES: list[dict] = [
    {"query": "What is the salary band for a senior engineer in the US?",        "relevant": {"d6"}},
    {"query": "interview rounds and format for a senior backend engineer",        "relevant": {"d4"}},
    {"query": "what score does a mid level engineer need to be shortlisted",       "relevant": {"d3"}},
    {"query": "should I penalize a candidate for an employment gap or bootcamp",   "relevant": {"d7"}},
    {"query": "compensation for a staff engineer in India",                        "relevant": {"d5"}},
    {"query": "expectations and shortlist bar for a junior engineer",              "relevant": {"d2"}},
]
