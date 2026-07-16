"""Labeled evaluation corpus + query set for the agentic RAG pipeline.

METHODOLOGY NOTE (read before quoting any number from this):
  This is a SYNTHETIC benchmark. The corpus and the queries were authored by the
  same people who built the retriever, so the queries share lexical and structural
  priors with the chunker. That makes this a strong REGRESSION benchmark - it will
  catch a retrieval regression - but it is NOT evidence of real-world
  generalization. Absolute numbers here are optimistic.

  To make it defensible we do three things:
    1. n = 200 queries, so one query moves recall by 0.5pt (not 5pt as at n=20).
    2. A seeded, stratified DEV/TEST split. Tune on dev; report test ONCE with the
       config frozen. Never tune against test.
    3. Bootstrap confidence intervals, so a delta without error bars is never
       reported as an improvement.

  The corpus deliberately contains NEAR-DUPLICATE distractors (the same fact
  across India/USA/UK, and across adjacent seniority levels) so that a query like
  "senior salary in India" has several plausible-but-wrong neighbours. This is
  what makes the reranker's contribution measurable rather than trivial.
"""

# ---------------------------------------------------------------------------
# id -> chunk text (the knowledge base)
# ---------------------------------------------------------------------------
CORPUS: dict[str, str] = {
    # --- Seniority levels + shortlist thresholds (mutual distractors) ---
    "c01": "Intern (current student or recent graduate, 0 years): completes well-scoped tasks with guidance. Shortlist threshold 50.",
    "c02": "Junior Engineer (0-2 years): proficient in one language, knows core data structures, ships small features with code review. Shortlist threshold 55.",
    "c03": "Mid Engineer (2-5 years): owns features end to end independently, strong in one domain, writes clean testable code. Shortlist threshold 65.",
    "c04": "Senior Engineer (5-8 years): designs systems, leads technical decisions for a squad, mentors junior engineers, expert in distributed systems. Shortlist threshold 70.",
    "c05": "Staff Engineer (8+ years): cross-team technical leadership, drives org-wide architecture, writes RFCs, rarely writes production code. Shortlist threshold 78.",
    "c06": "Principal Engineer (10+ years): sets multi-year technical strategy across the org, the most senior individual-contributor track. Shortlist threshold 85.",
    "c07": "Engineering Manager: people leadership for one or two squads, owns delivery and career growth, not expected to write production code. Shortlist threshold 72.",
    "c08": "Director of Engineering: owns a department, sets org structure and multi-quarter roadmap, manages managers. Shortlist threshold 88.",

    # --- Compensation India (distractors vs USA/UK) ---
    "c09": "Compensation India (INR per annum): Junior 7 to 13 LPA, Mid 14 to 22 LPA.",
    "c10": "Compensation India (INR per annum): Senior 24 to 38 LPA, Staff 40 to 58 LPA.",
    "c11": "Compensation India (INR per annum): Principal 60 to 85 LPA, Director 90 to 120 LPA.",
    "c12": "Compensation India (INR per annum): Engineering Manager 35 to 52 LPA.",

    # --- Compensation USA ---
    "c13": "Compensation USA (USD per annum): Junior 80k to 100k, Mid 110k to 140k.",
    "c14": "Compensation USA (USD per annum): Senior 145k to 180k, Staff 185k to 230k.",
    "c15": "Compensation USA (USD per annum): Principal 240k to 300k, Director 310k to 380k.",
    "c16": "Compensation USA (USD per annum): Engineering Manager 175k to 215k.",

    # --- Compensation UK ---
    "c17": "Compensation UK (GBP per annum): Junior 45k to 60k, Mid 65k to 85k.",
    "c18": "Compensation UK (GBP per annum): Senior 90k to 115k, Staff 120k to 150k.",

    # --- Equity and bonuses ---
    "c19": "Equity: stock options (ESOPs) are granted for mid level and above, vesting over 4 years with a 1 year cliff.",
    "c20": "Equity refresh: additional option grants are issued annually for senior level and above, starting after two years of tenure.",
    "c21": "Joining bonus: up to one month of CTC for senior and above, plus notice-period buyout up to two months for strong candidates.",
    "c22": "Performance bonus: 10 to 15 percent of base salary annually, paid in March following the review cycle.",

    # --- Interview process ---
    "c23": "Interview process overview: an asynchronous take-home, a technical debrief, a system design round for senior and above, a culture/values round, and a founder chat for final candidates.",
    "c24": "Round 1 is an asynchronous take-home assignment of 2 to 3 hours, a practical problem relevant to the role, with no live interviewer.",
    "c25": "Round 2 is a 45 minute technical debrief where a senior engineer reviews the take-home and asks follow-up questions.",
    "c26": "Round 3 is a 60 minute system design interview for senior level and above, whiteboarding a real-world distributed system with a staff engineer or CTO.",
    "c27": "Round 4 is a 30 minute culture and values interview with the engineering manager or a peer.",
    "c28": "Round 5 is a 30 minute founder chat, held only for final candidates at senior level and above.",
    "c29": "Take-home submissions are graded blind: the candidate's name is removed and two independent reviewers score against the rubric.",
    "c30": "Interview scheduling: all rounds are completed within 10 business days, and interviewer feedback is submitted within 48 hours of each round.",

    # --- Bias rules ---
    "c31": "Bias rules: do not penalize candidates for employment gaps under 18 months or for short stints at failed startups.",
    "c32": "Bias rules: do not penalize candidates for bootcamp education or for foreign or non-prestigious university names.",
    "c33": "Bias rules: do not penalize career changers entering engineering from non-computer-science backgrounds.",
    "c34": "Blind resume review: names, photos, and ages are removed from resumes before the screening stage.",
    "c35": "Scoring discipline: every candidate must be scored against the structured rubric; free-form gut-feel notes are not accepted as evidence.",
    "c36": "All interviewers must complete unconscious-bias training annually before they are allowed on a panel.",

    # --- Work policy, benefits, time off ---
    "c37": "Work policy: fully remote within India and the USA, with quarterly optional team meetups. Core overlap hours are 11am to 4pm IST.",
    "c38": "Benefits: comprehensive health insurance for the employee and dependents, plus an annual wellness stipend.",
    "c39": "Benefits: an annual learning and development budget of USD 1500 for courses, books, and conferences.",
    "c40": "Time off: 24 days of paid leave per year plus public holidays, and a flexible unpaid sabbatical available after 4 years of tenure.",
    "c41": "Home office: a one-time setup stipend of USD 800, plus USD 200 per year for equipment refresh.",
    "c42": "Connectivity: internet and phone reimbursement of INR 2000 or USD 50 per month.",
    "c43": "Sick leave: 12 days per year, tracked separately from the paid leave allowance.",
    "c44": "Working hours are flexible outside the core overlap window; no mandatory standups are scheduled before 11am IST.",

    # --- Role requirements (exact-term recall) ---
    "c45": "Backend roles require strong Python or Node.js, PostgreSQL, Redis, and familiarity with AWS or GCP.",
    "c46": "Frontend roles require strong React and TypeScript, responsive design, and accessibility (WCAG) awareness.",
    "c47": "Data engineering roles require Spark, Airflow, dbt, and warehouse modeling on Snowflake or BigQuery.",
    "c48": "ML engineering roles require PyTorch, feature stores, model serving, and experiment tracking with MLflow.",
    "c49": "Mobile roles require Swift or Kotlin; React Native is a plus, along with app store release experience.",
    "c50": "DevOps and SRE roles require Kubernetes, Terraform, CI/CD pipelines, and observability with Prometheus and Grafana.",
    "c51": "QA roles require test automation with Playwright or Cypress, API testing, and performance testing experience.",
    "c52": "Security roles require threat modeling, SAST and DAST tooling, OWASP Top 10 knowledge, and incident response.",

    # --- Process / misc ---
    "c53": "Promotion: performance reviews run twice a year; promotion requires consistently operating at the next level for two review cycles.",
    "c54": "Hiring philosophy: we value ownership over activity, clear written communication, and prior product-company or startup experience.",
    "c55": "Referral bonus: INR 1 lakh or USD 2000, paid once the referred hire completes 6 months.",
    "c56": "Probation: 3 months from the start date, with confirmation on the manager's sign-off.",
    "c57": "Onboarding: a two-week ramp plan, an assigned buddy, and an expectation of a first merged pull request within week one.",
    "c58": "Offer validity: offers remain open for 7 calendar days; extensions are granted on request.",
    "c59": "Background check: performed post-offer, covering employment history and education verification.",
    "c60": "Relocation assistance is not offered; all roles are remote-first.",
}

# ---------------------------------------------------------------------------
# query -> ground-truth relevant ids + failure-mode tag
#   single      : one clear gold chunk
#   distractor  : near-duplicate neighbours exist (region/level confusion)
#   multi       : several gold chunks (precision@k becomes meaningful)
#   paraphrase  : natural wording, no lexical overlap with the chunk
#   exact       : specific technical term, dense retrieval can miss
#   negative    : NOT in the corpus - must reject and abstain
# ---------------------------------------------------------------------------
QUERIES: list[dict] = [
    # ================= single (60) =================
    {"query": "US salary band for a senior engineer", "relevant": {"c14"}, "type": "single"},
    {"query": "what is the shortlist threshold for a staff engineer", "relevant": {"c05"}, "type": "single"},
    {"query": "how long is the system design interview", "relevant": {"c26"}, "type": "single"},
    {"query": "what is the annual learning and development budget", "relevant": {"c39"}, "type": "single"},
    {"query": "what are the core overlap hours for remote work", "relevant": {"c37"}, "type": "single"},
    {"query": "how many days of paid leave per year", "relevant": {"c40"}, "type": "single"},
    {"query": "what is the referral bonus amount", "relevant": {"c55"}, "type": "single"},
    {"query": "how long is the probation period", "relevant": {"c56"}, "type": "single"},
    {"query": "how long does an offer stay open", "relevant": {"c58"}, "type": "single"},
    {"query": "what is the shortlist threshold for an intern", "relevant": {"c01"}, "type": "single"},
    {"query": "how many years of experience is a mid engineer", "relevant": {"c03"}, "type": "single"},
    {"query": "what does a principal engineer do", "relevant": {"c06"}, "type": "single"},
    {"query": "engineering manager shortlist threshold", "relevant": {"c07"}, "type": "single"},
    {"query": "director of engineering shortlist threshold", "relevant": {"c08"}, "type": "single"},
    {"query": "India salary for a junior engineer", "relevant": {"c09"}, "type": "single"},
    {"query": "UK salary band for a staff engineer", "relevant": {"c18"}, "type": "single"},
    {"query": "USA principal engineer compensation", "relevant": {"c15"}, "type": "single"},
    {"query": "India engineering manager salary", "relevant": {"c12"}, "type": "single"},
    {"query": "USA engineering manager salary", "relevant": {"c16"}, "type": "single"},
    {"query": "when is the performance bonus paid out", "relevant": {"c22"}, "type": "single"},
    {"query": "how long is the take-home assignment", "relevant": {"c24"}, "type": "single"},
    {"query": "who reviews the take-home in round 2", "relevant": {"c25"}, "type": "single"},
    {"query": "who conducts the culture and values round", "relevant": {"c27"}, "type": "single"},
    {"query": "is there a founder interview round", "relevant": {"c28"}, "type": "single"},
    {"query": "how many reviewers grade the take-home", "relevant": {"c29"}, "type": "single"},
    {"query": "how quickly must interviewers submit feedback", "relevant": {"c30"}, "type": "single"},
    {"query": "what is the equity vesting schedule", "relevant": {"c19"}, "type": "single"},
    {"query": "when do equity refresh grants start", "relevant": {"c20"}, "type": "single"},
    {"query": "how much is the joining bonus", "relevant": {"c21"}, "type": "single"},
    {"query": "what is the home office setup stipend", "relevant": {"c41"}, "type": "single"},
    {"query": "what is the internet reimbursement amount", "relevant": {"c42"}, "type": "single"},
    {"query": "how many sick days per year", "relevant": {"c43"}, "type": "single"},
    {"query": "what databases do backend roles need", "relevant": {"c45"}, "type": "single"},
    {"query": "what do frontend roles require", "relevant": {"c46"}, "type": "single"},
    {"query": "what tools do data engineering roles use", "relevant": {"c47"}, "type": "single"},
    {"query": "what ML frameworks are required", "relevant": {"c48"}, "type": "single"},
    {"query": "what languages do mobile roles need", "relevant": {"c49"}, "type": "single"},
    {"query": "what do DevOps and SRE roles require", "relevant": {"c50"}, "type": "single"},
    {"query": "what QA tooling is expected", "relevant": {"c51"}, "type": "single"},
    {"query": "what security skills are required", "relevant": {"c52"}, "type": "single"},
    {"query": "how often are performance reviews held", "relevant": {"c53"}, "type": "single"},
    {"query": "what is the company hiring philosophy", "relevant": {"c54"}, "type": "single"},
    {"query": "what happens during onboarding", "relevant": {"c57"}, "type": "single"},
    {"query": "is there a background check", "relevant": {"c59"}, "type": "single"},
    {"query": "is relocation assistance offered", "relevant": {"c60"}, "type": "single"},
    {"query": "is bias training mandatory for interviewers", "relevant": {"c36"}, "type": "single"},
    {"query": "are names removed from resumes before screening", "relevant": {"c34"}, "type": "single"},
    {"query": "is a structured scoring rubric required", "relevant": {"c35"}, "type": "single"},
    {"query": "what wellness benefit is offered", "relevant": {"c38"}, "type": "single"},
    {"query": "after how many years can you take a sabbatical", "relevant": {"c40"}, "type": "single"},
    {"query": "what is the notice period buyout limit", "relevant": {"c21"}, "type": "single"},
    {"query": "how many years of experience is a staff engineer", "relevant": {"c05"}, "type": "single"},
    {"query": "how many years of experience is a senior engineer", "relevant": {"c04"}, "type": "single"},
    {"query": "what is the junior engineer shortlist threshold", "relevant": {"c02"}, "type": "single"},
    {"query": "what is round 1 of the interview process", "relevant": {"c24"}, "type": "single"},
    {"query": "what is round 4 of the interview process", "relevant": {"c27"}, "type": "single"},
    {"query": "how long is the technical debrief round", "relevant": {"c25"}, "type": "single"},
    {"query": "India principal engineer salary", "relevant": {"c11"}, "type": "single"},
    {"query": "UK junior engineer salary", "relevant": {"c17"}, "type": "single"},
    {"query": "what percentage is the performance bonus", "relevant": {"c22"}, "type": "single"},

    # ================= distractor (35) =================
    {"query": "salary for a senior engineer in India", "relevant": {"c10"}, "type": "distractor"},
    {"query": "what score does a mid level engineer need to shortlist", "relevant": {"c03"}, "type": "distractor"},
    {"query": "junior engineer salary in the USA", "relevant": {"c13"}, "type": "distractor"},
    {"query": "junior engineer salary in India", "relevant": {"c09"}, "type": "distractor"},
    {"query": "staff engineer salary in India", "relevant": {"c10"}, "type": "distractor"},
    {"query": "staff engineer salary in the USA", "relevant": {"c14"}, "type": "distractor"},
    {"query": "senior engineer salary in the UK", "relevant": {"c18"}, "type": "distractor"},
    {"query": "mid engineer salary in the UK", "relevant": {"c17"}, "type": "distractor"},
    {"query": "principal engineer salary in India", "relevant": {"c11"}, "type": "distractor"},
    {"query": "principal engineer salary in the USA", "relevant": {"c15"}, "type": "distractor"},
    {"query": "engineering manager pay in India", "relevant": {"c12"}, "type": "distractor"},
    {"query": "engineering manager pay in the USA", "relevant": {"c16"}, "type": "distractor"},
    {"query": "director compensation in India", "relevant": {"c11"}, "type": "distractor"},
    {"query": "director compensation in the USA", "relevant": {"c15"}, "type": "distractor"},
    {"query": "mid engineer salary in India", "relevant": {"c09"}, "type": "distractor"},
    {"query": "mid engineer salary in the USA", "relevant": {"c13"}, "type": "distractor"},
    {"query": "what threshold does a senior engineer need", "relevant": {"c04"}, "type": "distractor"},
    {"query": "what threshold does a principal engineer need", "relevant": {"c06"}, "type": "distractor"},
    {"query": "how long is round 3", "relevant": {"c26"}, "type": "distractor"},
    {"query": "how long is round 4", "relevant": {"c27"}, "type": "distractor"},
    {"query": "how long is round 2", "relevant": {"c25"}, "type": "distractor"},
    {"query": "how long is round 5", "relevant": {"c28"}, "type": "distractor"},
    {"query": "how long is the equity cliff", "relevant": {"c19"}, "type": "distractor"},
    {"query": "how many sick days, not paid leave days", "relevant": {"c43"}, "type": "distractor"},
    {"query": "how many paid leave days, not sick days", "relevant": {"c40"}, "type": "distractor"},
    {"query": "which cloud providers do backend roles need", "relevant": {"c45"}, "type": "distractor"},
    {"query": "which infrastructure tooling do DevOps roles need", "relevant": {"c50"}, "type": "distractor"},
    {"query": "who runs the system design whiteboarding round", "relevant": {"c26"}, "type": "distractor"},
    {"query": "who takes the founder chat", "relevant": {"c28"}, "type": "distractor"},
    {"query": "do junior engineers receive stock options", "relevant": {"c19"}, "type": "distractor"},
    {"query": "which levels are eligible for equity refresh", "relevant": {"c20"}, "type": "distractor"},
    {"query": "UK staff engineer pay range", "relevant": {"c18"}, "type": "distractor"},
    {"query": "India staff engineer pay range", "relevant": {"c10"}, "type": "distractor"},
    {"query": "USA staff engineer pay range", "relevant": {"c14"}, "type": "distractor"},
    {"query": "how many years of experience does an intern have", "relevant": {"c01"}, "type": "distractor"},

    # ================= multi (30) =================
    {"query": "what are all the interview rounds and their format", "relevant": {"c23", "c24", "c25", "c26", "c27", "c28"}, "type": "multi"},
    {"query": "what are the bias rules for screening candidates", "relevant": {"c31", "c32", "c33", "c34", "c35", "c36"}, "type": "multi"},
    {"query": "what benefits and time off does the company offer", "relevant": {"c38", "c39", "c40", "c43"}, "type": "multi"},
    {"query": "full compensation package for a senior engineer in India", "relevant": {"c10", "c19", "c22"}, "type": "multi"},
    {"query": "full compensation package for a senior engineer in the USA", "relevant": {"c14", "c19", "c22"}, "type": "multi"},
    {"query": "all salary bands in India", "relevant": {"c09", "c10", "c11", "c12"}, "type": "multi"},
    {"query": "all salary bands in the USA", "relevant": {"c13", "c14", "c15", "c16"}, "type": "multi"},
    {"query": "all salary bands in the UK", "relevant": {"c17", "c18"}, "type": "multi"},
    {"query": "what equity do employees receive", "relevant": {"c19", "c20"}, "type": "multi"},
    {"query": "what bonuses does the company pay", "relevant": {"c21", "c22", "c55"}, "type": "multi"},
    {"query": "what are the remote work policies", "relevant": {"c37", "c44", "c60"}, "type": "multi"},
    {"query": "what stipends and reimbursements are provided", "relevant": {"c41", "c42"}, "type": "multi"},
    {"query": "what types of leave exist", "relevant": {"c40", "c43"}, "type": "multi"},
    {"query": "list all seniority levels and their thresholds", "relevant": {"c01", "c02", "c03", "c04", "c05", "c06", "c07", "c08"}, "type": "multi"},
    {"query": "what happens after an offer is accepted", "relevant": {"c56", "c57", "c58", "c59"}, "type": "multi"},
    {"query": "backend and devops technical requirements", "relevant": {"c45", "c50"}, "type": "multi"},
    {"query": "frontend and mobile technical requirements", "relevant": {"c46", "c49"}, "type": "multi"},
    {"query": "data engineering and ML technical requirements", "relevant": {"c47", "c48"}, "type": "multi"},
    {"query": "how is the take-home assignment handled and graded", "relevant": {"c24", "c29"}, "type": "multi"},
    {"query": "what fairness measures exist in the hiring process", "relevant": {"c34", "c35", "c36"}, "type": "multi"},
    {"query": "which interview rounds are only for senior and above", "relevant": {"c26", "c28"}, "type": "multi"},
    {"query": "what health and learning benefits are offered", "relevant": {"c38", "c39"}, "type": "multi"},
    {"query": "what is the interview timeline and process", "relevant": {"c23", "c30"}, "type": "multi"},
    {"query": "what individual contributor levels are above senior", "relevant": {"c05", "c06"}, "type": "multi"},
    {"query": "what management levels exist", "relevant": {"c07", "c08"}, "type": "multi"},
    {"query": "what does a new joiner go through", "relevant": {"c56", "c57"}, "type": "multi"},
    {"query": "what compensation applies to an engineering manager", "relevant": {"c12", "c16"}, "type": "multi"},
    {"query": "what are the promotion and confirmation policies", "relevant": {"c53", "c56"}, "type": "multi"},
    {"query": "QA and security role requirements", "relevant": {"c51", "c52"}, "type": "multi"},
    {"query": "what are the equity and bonus policies", "relevant": {"c19", "c20", "c21", "c22"}, "type": "multi"},

    # ================= paraphrase (30) =================
    {"query": "should I dock points for a candidate's career break", "relevant": {"c31"}, "type": "paraphrase"},
    {"query": "do you penalize people who attended a coding bootcamp", "relevant": {"c32"}, "type": "paraphrase"},
    {"query": "how much vacation do employees get each year", "relevant": {"c40"}, "type": "paraphrase"},
    {"query": "can someone switching from a non-technical career apply", "relevant": {"c33"}, "type": "paraphrase"},
    {"query": "are resumes anonymised before anyone looks at them", "relevant": {"c34"}, "type": "paraphrase"},
    {"query": "can interviewers just go with their gut feeling", "relevant": {"c35"}, "type": "paraphrase"},
    {"query": "do interviewers get trained on fairness", "relevant": {"c36"}, "type": "paraphrase"},
    {"query": "how much does the company chip in for me to learn things", "relevant": {"c39"}, "type": "paraphrase"},
    {"query": "what do you pay a fresher in Bangalore", "relevant": {"c09"}, "type": "paraphrase"},
    {"query": "how long does the take home test take", "relevant": {"c24"}, "type": "paraphrase"},
    {"query": "how much time off do I get when I'm unwell", "relevant": {"c43"}, "type": "paraphrase"},
    {"query": "when do my share options actually become mine", "relevant": {"c19"}, "type": "paraphrase"},
    {"query": "do I get money to set up my desk at home", "relevant": {"c41"}, "type": "paraphrase"},
    {"query": "will you cover my broadband bill", "relevant": {"c42"}, "type": "paraphrase"},
    {"query": "how soon do I hear back after an interview", "relevant": {"c30"}, "type": "paraphrase"},
    {"query": "what kind of people do you look for", "relevant": {"c54"}, "type": "paraphrase"},
    {"query": "how do I move up a level here", "relevant": {"c53"}, "type": "paraphrase"},
    {"query": "do you pay me for recommending a friend", "relevant": {"c55"}, "type": "paraphrase"},
    {"query": "how long until I'm made permanent", "relevant": {"c56"}, "type": "paraphrase"},
    {"query": "how long do I have to make up my mind on the offer", "relevant": {"c58"}, "type": "paraphrase"},
    {"query": "will you check up on my previous employers", "relevant": {"c59"}, "type": "paraphrase"},
    {"query": "will you help me move to another city", "relevant": {"c60"}, "type": "paraphrase"},
    {"query": "what time do I actually need to be online", "relevant": {"c37"}, "type": "paraphrase"},
    {"query": "do I have to wake up early for a daily meeting", "relevant": {"c44"}, "type": "paraphrase"},
    {"query": "what's the pay for someone just starting out in the states", "relevant": {"c13"}, "type": "paraphrase"},
    {"query": "what do you give experienced engineers in London", "relevant": {"c18"}, "type": "paraphrase"},
    {"query": "is there extra cash when I join", "relevant": {"c21"}, "type": "paraphrase"},
    {"query": "what yearly payout do I get for doing well", "relevant": {"c22"}, "type": "paraphrase"},
    {"query": "who speaks to me last in the hiring process", "relevant": {"c28"}, "type": "paraphrase"},
    {"query": "how long can I take an unpaid break for", "relevant": {"c40"}, "type": "paraphrase"},

    # ================= exact-term (25) =================
    {"query": "is Redis required for backend roles", "relevant": {"c45"}, "type": "exact"},
    {"query": "do frontend roles need accessibility knowledge", "relevant": {"c46"}, "type": "exact"},
    {"query": "is Airflow used by data engineers", "relevant": {"c47"}, "type": "exact"},
    {"query": "is PyTorch required for ML roles", "relevant": {"c48"}, "type": "exact"},
    {"query": "is Kotlin needed for mobile roles", "relevant": {"c49"}, "type": "exact"},
    {"query": "is Terraform required for DevOps", "relevant": {"c50"}, "type": "exact"},
    {"query": "is Playwright used in QA", "relevant": {"c51"}, "type": "exact"},
    {"query": "is OWASP Top 10 knowledge required", "relevant": {"c52"}, "type": "exact"},
    {"query": "is PostgreSQL required for backend roles", "relevant": {"c45"}, "type": "exact"},
    {"query": "is TypeScript required for frontend roles", "relevant": {"c46"}, "type": "exact"},
    {"query": "is dbt part of the data stack", "relevant": {"c47"}, "type": "exact"},
    {"query": "is MLflow used for experiment tracking", "relevant": {"c48"}, "type": "exact"},
    {"query": "is Swift required for mobile roles", "relevant": {"c49"}, "type": "exact"},
    {"query": "is Kubernetes required", "relevant": {"c50"}, "type": "exact"},
    {"query": "is Cypress an accepted QA tool", "relevant": {"c51"}, "type": "exact"},
    {"query": "is SAST tooling required for security roles", "relevant": {"c52"}, "type": "exact"},
    {"query": "is Snowflake used for warehouse modeling", "relevant": {"c47"}, "type": "exact"},
    {"query": "is Prometheus used for observability", "relevant": {"c50"}, "type": "exact"},
    {"query": "is React Native a plus for mobile", "relevant": {"c49"}, "type": "exact"},
    {"query": "is WCAG mentioned in the frontend requirements", "relevant": {"c46"}, "type": "exact"},
    {"query": "is GCP acceptable for backend roles", "relevant": {"c45"}, "type": "exact"},
    {"query": "is BigQuery part of the data requirements", "relevant": {"c47"}, "type": "exact"},
    {"query": "is Grafana used", "relevant": {"c50"}, "type": "exact"},
    {"query": "is threat modeling required", "relevant": {"c52"}, "type": "exact"},
    {"query": "is feature store experience needed for ML", "relevant": {"c48"}, "type": "exact"},

    # ================= negative / out-of-domain (20) =================
    {"query": "what is the parental leave policy", "relevant": set(), "type": "negative"},
    {"query": "do you sponsor H1B visa applications", "relevant": set(), "type": "negative"},
    {"query": "what is the company's 401k retirement match", "relevant": set(), "type": "negative"},
    {"query": "what is the office dress code", "relevant": set(), "type": "negative"},
    {"query": "is there a free lunch or meal allowance", "relevant": set(), "type": "negative"},
    {"query": "do you reimburse gym or fitness memberships", "relevant": set(), "type": "negative"},
    {"query": "is pet insurance included", "relevant": set(), "type": "negative"},
    {"query": "what is the bereavement leave policy", "relevant": set(), "type": "negative"},
    {"query": "how much jury duty leave is allowed", "relevant": set(), "type": "negative"},
    {"query": "is there a company pension scheme", "relevant": set(), "type": "negative"},
    {"query": "do you offer childcare or daycare support", "relevant": set(), "type": "negative"},
    {"query": "what is the overtime pay rate", "relevant": set(), "type": "negative"},
    {"query": "is there an on-call compensation stipend", "relevant": set(), "type": "negative"},
    {"query": "are commuter or transit benefits provided", "relevant": set(), "type": "negative"},
    {"query": "when was the company founded", "relevant": set(), "type": "negative"},
    {"query": "how many employees does the company have", "relevant": set(), "type": "negative"},
    {"query": "who is the CEO of the company", "relevant": set(), "type": "negative"},
    {"query": "does the company have an IPO planned", "relevant": set(), "type": "negative"},
    {"query": "is a company car provided", "relevant": set(), "type": "negative"},
    {"query": "what is the company's carbon offset policy", "relevant": set(), "type": "negative"},
]
