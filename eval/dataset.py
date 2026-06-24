# id -> chunk text (the knowledge base)
CORPUS: dict[str, str] = {
    # Seniority definitions (distractors for salary/score queries)
    "c01": "Intern (current student or recent graduate, 0 years): completes well-scoped tasks with guidance. Shortlist threshold 50.",
    "c02": "Junior Engineer (0-2 years): proficient in one language, knows core data structures, ships small features with code review. Shortlist threshold 55.",
    "c03": "Mid Engineer (2-5 years): owns features end to end independently, strong in one domain, writes clean testable code. Shortlist threshold 65.",
    "c04": "Senior Engineer (5-8 years): designs systems, leads technical decisions for a squad, mentors junior engineers, expert in distributed systems. Shortlist threshold 70.",
    "c05": "Staff Engineer (8+ years): cross-team technical leadership, drives org-wide architecture, writes RFCs, rarely writes code. Shortlist threshold 78.",
    "c06": "Principal Engineer (10+ years): sets multi-year technical strategy across the org, the most senior individual-contributor track. Shortlist threshold 85.",

    # Interview process (multi-relevant for 'all rounds' queries)
    "c07": "Interview process overview: an asynchronous take-home, a technical debrief, a system design round for senior and above, and a culture/values round.",
    "c08": "Round 1 is an asynchronous take-home assignment of 2 to 3 hours, a practical problem relevant to the role, with no live interviewer.",
    "c09": "Round 2 is a 45 minute technical debrief where a senior engineer reviews the take-home and asks follow-up questions.",
    "c10": "Round 3 is a 60 minute system design interview for senior level and above, whiteboarding a real-world distributed system with a staff engineer or CTO.",
    "c11": "Round 4 is a 30 minute culture and values interview with the engineering manager or a peer.",

    # Compensation (multi-relevant for 'staff comp' queries; distractors across regions)
    "c12": "Compensation India (INR per annum): Junior 7 to 13 LPA, Mid 14 to 22 LPA.",
    "c13": "Compensation India (INR per annum): Senior 24 to 38 LPA, Staff 40 to 58 LPA.",
    "c14": "Compensation USA (USD per annum): Junior 80k to 100k, Mid 110k to 140k.",
    "c15": "Compensation USA (USD per annum): Senior 145k to 180k, Staff 185k to 230k.",
    "c16": "Equity: stock options (ESOPs) are granted for mid level and above, vesting over 4 years with a 1 year cliff.",
    "c17": "Joining bonus: up to one month of CTC for senior and above, plus notice-period buyout up to two months for strong candidates.",

    # Bias rules (paraphrase targets)
    "c18": "Bias rules: do not penalize candidates for employment gaps under 18 months or for short stints at failed startups.",
    "c19": "Bias rules: do not penalize candidates for bootcamp education or for foreign or non-prestigious university names.",

    # Policy and benefits
    "c20": "Work policy: fully remote within India and the USA, with quarterly optional team meetups. Core overlap hours are 11am to 4pm IST.",
    "c21": "Benefits: comprehensive health insurance for the employee and dependents, plus an annual wellness stipend.",
    "c22": "Benefits: an annual learning and development budget of USD 1500 for courses, books, and conferences.",
    "c23": "Time off: 24 days of paid leave per year plus public holidays, and a flexible unpaid sabbatical after 4 years.",

    # Role requirements (exact-term recall)
    "c24": "Backend roles require strong Python or Node.js, PostgreSQL, Redis, and familiarity with AWS or GCP.",
    "c25": "Frontend roles require strong React and TypeScript, responsive design, and accessibility (WCAG) awareness.",

    # Misc
    "c26": "Promotion: performance reviews run twice a year; promotion requires consistently operating at the next level for two review cycles.",
    "c27": "Hiring philosophy: we value ownership over activity, clear written communication, and prior product-company or startup experience.",
}

# query -> ground-truth relevant ids + failure-mode tag
QUERIES: list[dict] = [
    # --- single, clear ---
    {"query": "US salary band for a senior engineer",                 "relevant": {"c15"},               "type": "single"},
    {"query": "what is the shortlist threshold for a staff engineer",  "relevant": {"c05"},               "type": "single"},
    {"query": "how long is the system design interview",               "relevant": {"c10"},               "type": "single"},
    {"query": "what is the annual learning and development budget",     "relevant": {"c22"},               "type": "single"},
    {"query": "what are the core overlap hours for remote work",       "relevant": {"c20"},               "type": "single"},

    # --- distractor (definition vs the asked-for fact; reranker-sensitive) ---
    {"query": "salary for a senior engineer in India",                 "relevant": {"c13"},               "type": "distractor"},
    {"query": "what score does a mid level engineer need to shortlist", "relevant": {"c03"},               "type": "distractor"},

    # --- multi-relevant (precision@k becomes meaningful) ---
    {"query": "what total compensation does a staff engineer get",     "relevant": {"c13", "c15", "c16"}, "type": "multi"},
    {"query": "what are all the interview rounds and their format",    "relevant": {"c07", "c08", "c09", "c10", "c11"}, "type": "multi"},
    {"query": "what are the bias rules for screening candidates",      "relevant": {"c18", "c19"},        "type": "multi"},
    {"query": "what benefits and time off does the company offer",     "relevant": {"c21", "c22", "c23"}, "type": "multi"},

    # --- paraphrase (synonyms / different wording) ---
    {"query": "should I dock points for a candidate's career break",   "relevant": {"c18"},               "type": "paraphrase"},
    {"query": "do you penalize people who attended a coding bootcamp", "relevant": {"c19"},               "type": "paraphrase"},
    {"query": "how much vacation do employees get each year",          "relevant": {"c23"},               "type": "paraphrase"},

    # --- exact-term (specific skills; dense retrieval can miss) ---
    {"query": "is Redis required for backend roles",                   "relevant": {"c24"},               "type": "exact"},
    {"query": "do frontend roles need accessibility knowledge",        "relevant": {"c25"},               "type": "exact"},

    # --- negative / out-of-domain (must reject, not hallucinate) ---
    {"query": "what is the parental leave policy",                     "relevant": set(),                 "type": "negative"},
    {"query": "do you sponsor H1B visa applications",                  "relevant": set(),                 "type": "negative"},
    {"query": "what is the company's 401k retirement match",           "relevant": set(),                 "type": "negative"},
    {"query": "what is the office dress code",                         "relevant": set(),                 "type": "negative"},
]
