# C84 prose review — human/source judgement pending

Model: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed; phase: after

Integrity, output length and convergence are not prose quality scores.

## pub-4c960b9ee8744a98997f7bfde177d2d7

Prompt:
what are some good popular engines to develop web build games? list pros and cons of each, bonus points if it is unlikely to be outdated soon

Response:
# Popular Engines for Web (Browser) Games

## Godot
- **Pros:** Fully free & open-source (MIT), excellent 2D and capable 3D, exports to WebAssembly, huge and growing community, scriptable in GDScript (Python-like) or C#, active development under a non-profit foundation.
- **Cons:** Web export has performance limits (no multi-threading in browser, ~16ms frame budget), 3D on web is still rough, WASM builds can be large, mobile-web support is shaky.
- **Longevity:** ⭐ Very likely to stick around. Foundation-owned, no corporate acquisition risk.

## Phaser
- **Pros:** Purpose-built for 2D HTML5 games, huge plugin ecosystem, tons of tutorials/examples, lightweight, runs everywhere a browser runs, JS/TS friendly.
- **Cons:** 2D only, performance ceiling for very large scenes, API can feel dated in places, no built-in 3D or physics beyond basic.
- **Longevity:** ⭐ Community-driven open source, been around since 2013, very stable. Low risk of abandonment.

## PlayCanvas
- **Pros:** Web-native 3D engine (no export step), open source, in-browser editor, good for 3D browser games, no install needed, TypeScript support.
- **Cons:** Smaller community than Godot/Unity, 2D support is secondary, some features locked behind their cloud platform, less flexible for non-standard architectures.
- **Longevity:** ⭐ Company-backed (PlayCanvas Inc.) + open source. Has been around since 2013. Reasonably safe.

## Babylon.js
- **Pros:** Extremely powerful 3D, Microsoft-backed, excellent docs, TypeScript-first, huge feature set (PBR, particles, physics, XR), active development.
- **Cons:** Not a "game engine" per se — more a rendering/framework layer, you build your own game loop & systems, steeper learning curve, heavier for simple 2D games.
- **Longevity:** ⭐⭐ Microsoft-backed. Very unlikely to be discontinued.

## PixiJS
- **Pros:** Blazing-fast 2D/WebGL/WebGPU renderer, very lightweight, great for UI-heavy or particle-heavy games, huge community, TypeScript native.
- **Cons:** It's a *renderer*, not a full engine — no physics, no scene management, no asset pipeline. You build everything around it.
- **Longevity:** ⭐ Community-driven, very established. Low risk.

## Three.js
- **Pros:** The de-facto standard for 3D on the web, massive ecosystem, runs anywhere, great for stylized/creative 3D, huge community.
- **Cons:** Like Babylon, it's a rendering library not a game engine. No built-in game systems. Performance tuning is on you.
- **Longevity:** ⭐⭐ Extremely established, community-driven. Near-zero risk of disappearing.

## Construct 3
- **Pros:** No-code / visual scripting, runs entirely in the browser editor, instant web publishing, great for prototypes and casual games, very fast to get something playable.
- **Cons:** Subscription-based ($), limited to their platform, hard to escape for complex logic, 2D only, smaller ecosystem than code-based options.
- **Longevity:** ⭐ Company-backed (Scirra). Stable but you're locked into their ecosystem.

## Cocos Creator
- **Pros:** Designed specifically for web/mobile games, open source, good 2D and 3D, TypeScript, strong in the Asian market, lightweight builds.
- **Cons:** Smaller Western community, fewer tutorials in English, documentation quality is inconsistent, ecosystem is thinner.
- **Longevity:** ⭐ Backed by Cocos (Tencent-affiliated). Has been around a long time. Reasonably safe.

---

## Quick Recommendation Guide

| You want… | Go with |
|---|---|
| 2D browser game, JS/TS | **Phaser** or **PixiJS** |
| 3D browser game | **PlayCanvas** or **Babylon.js** |
| Full game (2D+3D), free, future-proof | **Godot** (web export) |
| No-code / quick prototype | **Construct 3** |
| Lightweight, max performance 2D | **PixiJS** + your own logic |

**Best "won't be outdated soon" picks:** Godot, Phaser, PixiJS, and Babylon.js are all open-source with strong communities and no single point of corporate failure. Unity's WebGL export is the one I'd avoid for web specifically — their licensing drama and the fact that they treat web as a second-class target make it the riskiest choice here.

Review factual support, instruction compliance, completeness, coherence and limitations. Compare paired before/after bodies after both phases; record a reasoned judgement.

## pub-e7e76d4bcf0342308ca6153634000a4a

Prompt:
Can you write a service catalogue for a Microsoft M365 consultancy focusing on Data, Data Management, Automation and A.I.  The focus should be on audits, roadmaps, advice and cutting edge technologies within the M365 ecosystem but not be its only focus

Response:
# Service Catalogue

## [Firm Name] — Data, Automation & AI Advisory

*Microsoft 365–centric. Not Microsoft-only.*

---

## How We Work

We are a specialist consultancy that helps organisations unlock the full potential of their data, automate their operations, and adopt AI responsibly. Our work is anchored in the Microsoft 365 and Azure ecosystem — the platform most enterprises already own — but we are pragmatic about tooling. Where an open-source, cross-platform, or best-of-breed solution serves your business better, we'll say so and build around it.

Every engagement is advisory-first. We audit, we advise, we roadmap, and then — if you want us to — we build.

---

## 1 · Data

### 1.1 Data Maturity & Governance Audit
A structured assessment of how your organisation captures, stores, classifies, and protects data across Microsoft 365 (SharePoint, OneDrive, Teams, Exchange, Viva) and beyond.

- Discovery of all data stores, shadow IT, and unmanaged repositories
- Classification and sensitivity labelling review (Microsoft Purview, or equivalent)
- Data lineage and ownership mapping
- Compliance gap analysis (GDPR, DPA, sector-specific regulations)
- Risk register and prioritised remediation plan

**Deliverable:** Data Maturity Report + 90-Day Remediation Roadmap

### 1.2 Data Strategy & Roadmap
A forward-looking blueprint for where your data estate should be in 12–36 months.

- Business-capability-to-data-requirement mapping
- Platform selection (M365 / Azure / AWS / GCP / on-prem — whatever fits)
- Migration and consolidation strategy
- Data model design (lakehouse, warehouse, operational stores)
- Cost and licensing model (per-user vs. per-GB vs. hybrid)

**Deliverable:** Data Strategy Document + Phased Implementation Roadmap

### 1.3 Data Architecture Advisory
Ongoing or fixed-term advisory for teams building data platforms.

- Architecture reviews (lakehouse, data mesh, data fabric patterns)
- Tooling selection: Azure Synapse, Fabric, Databricks, Snowflake, BigQuery, or open-source (Apache Spark, Delta Lake, Iceberg)
- Integration patterns across M365 and non-Microsoft systems
- Performance, scalability, and cost-optimisation guidance

**Engagement model:** Fractional CDO / Principal Architect (part-time, retainer, or per-sprint)

---

## 2 · Data Management

### 2.1 Information Management & Records Audit
Assessment of how information is managed across the enterprise, with emphasis on Microsoft Purview, SharePoint, and OneDrive, but extending to any system in scope.

- Records retention and legal-hold configuration review
- Auto-classification and sensitivity policy effectiveness
- Lifecycle management (creation → active → archive → disposition)
- E-discovery and litigation-readiness assessment
- Cross-platform records management (M365 + legacy systems)

**Deliverable:** Information Management Audit Report + Policy & Configuration Recommendations

### 2.2 Data Platform Build & Migration
Hands-on delivery for teams that need to move, consolidate, or modernise their data estate.

- Migration from on-prem / legacy to Azure, Fabric, or M365-native stores
- Data integration and ETL/ELT pipeline design (Azure Data Factory, Fabric Pipelines, ADF alternatives, Airflow, dbt)
- SharePoint / OneDrive content consolidation and modernisation
- Data quality frameworks and stewardship tooling

**Engagement model:** Fixed-scope project or embedded delivery team

### 2.3 Data Stewardship & Operations Advisory
Helping organisations run their data as a product, not a by-product.

- Data stewardship model design (centralised, federated, domain-based)
- Data quality monitoring and SLA frameworks
- Self-service data access and cataloguing (Purview, Alation, Atlan, DataHub)
- Training and enablement for business data owners

**Engagement model:** Advisory retainer or enablement workshops

---

## 3 · Automation

### 3.1 Automation Opportunity Audit
A systematic scan of your business processes to identify, score, and prioritise automation targets.

- Process discovery across M365 (Teams, Outlook, SharePoint, Forms, Lists) and adjacent systems (ERP, CRM, HR, finance)
- Automation maturity scoring (manual → assisted → automated → intelligent)
- ROI and effort modelling per opportunity
- Tooling fit assessment: Power Automate, Azure Logic Apps, n8n, Zapier, custom code, or RPA (UiPath, Automation Anywhere, Power Automate Desktop)

**Deliverable:** Automation Opportunity Register + Prioritised Roadmap

### 3.2 Automation Strategy & Roadmap
A 12–24 month plan to scale automation from pilot to operational norm.

- Centre-of-excellence / community-of-practice design
- Governance, security, and compliance framework for automation (including M365 Copilot and Power Platform governance)
- Developer vs. citizen-developer model
- Integration architecture (API-first, event-driven, M365 Graph, Azure Service Bus, or platform-neutral)
- Change management and adoption strategy

**Deliverable:** Automation Strategy + Phased Roadmap + Governance Framework

### 3.3 Automation Build & Delivery
Hands-on design and build of automation solutions.

- Power Platform solutions (Flows, Apps, Pages, Dataflows)
- Azure-native automation (Functions, Logic Apps, Event Grid, Durable Functions)
- Cross-platform orchestration (n8n, Apache Airflow, Temporal, custom Python/.NET)
- Integration with non-Microsoft systems via APIs, webhooks, or middleware
- CI/CD and DevOps pipelines for automation artefacts

**Engagement model:** Fixed-scope build, embedded squad, or fractional engineering

### 3.4 Intelligent Process Automation (IPA)
Where automation meets AI — not just "if this then that," but systems that reason, adapt, and learn.

- Assessment of process suitability for AI-augmented automation
- Design of agentic workflows (Azure AI Agent Service, Copilot Studio, or open-source agent frameworks like LangGraph, CrewAI, AutoGen)
- Human-in-the-loop governance and exception handling
- Performance monitoring and continuous improvement loops

**Deliverable:** IPA Design Blueprint + Pilot Build

---

## 4 · Artificial Intelligence

### 4.1 AI Readiness & Maturity Audit
A grounded assessment of whether, how, and where AI can create value in your organisation.

- Assessment of data readiness (quality, volume, accessibility, governance)
- Workforce readiness (skills, culture, change appetite)
- Regulatory and ethical risk review (EU AI Act, UK AI regulation, sector-specific rules)
- Tooling landscape review: M365 Copilot, Azure AI Foundry, open-source LLMs, and everything between
- Use-case discovery and feasibility scoring

**Deliverable:** AI Readiness Report + Risk Register + Use-Case Prioritisation Matrix

### 4.2 AI Strategy & Roadmap
A pragmatic, phased plan for AI adoption — from first pilot to enterprise-scale deployment.

- Use-case portfolio design (assistive, augmentative, autonomous)
- Platform and model selection (Azure OpenAI, Copilot Studio, on-prem / self-hosted models, multi-cloud)
- Data and infrastructure prerequisites
- Governance, evaluation, and responsible-AI framework
- Cost modelling (token economics, infrastructure, licensing)
- Change management and adoption plan

**Deliverable:** AI Strategy Document + 12/24/36-Month Roadmap + Governance Framework

### 4.3 Copilot & Power Platform AI Advisory
Specialist guidance on the M365 Copilot and Power Platform AI surface, with honest assessment of what it can and can't do.

- Copilot rollout strategy (Teams, Word, Excel, PowerPoint, Outlook, Search, Viva)
- Custom Copilot and Copilot Studio solution design
- Power Platform AI Builder integration
- Prompt engineering and evaluation practices
- Security, DLP, and data-boundary configuration
- Honest scoping: where Copilot helps, where it doesn't, and what to build instead

**Engagement model:** Advisory retainer, workshop series, or fixed-scope assessment

### 4.4 AI Solution Design & Build
Hands-on design and delivery of AI-powered solutions, built on the right stack for the problem.

- Generative AI applications (RAG pipelines, fine-tuning, prompt engineering, evaluation)
- Agentic AI systems (Azure AI Agent Service, LangGraph, CrewAI, AutoGen, or custom)
- Computer vision, speech, and NLP solutions (Azure AI Services, ONNX, open-source)
- MLOps and model lifecycle management (Azure ML, MLflow, or platform-neutral)
- Integration into M365 workflows and non-Microsoft systems

**Engagement model:** Fixed-scope project, embedded AI engineering squad, or fractional AI architect

### 4.5 Responsible AI & Governance
Helping you adopt AI without creating legal, ethical, or operational risk.

- AI governance framework design (aligned to NIST AI RMF, EU AI Act, ISO 42001)
- Model risk management and evaluation strategy
- Bias, fairness, and transparency testing
- Human oversight and escalation design
- Audit trail and explainability requirements
- Policy, training, and organisational enablement

**Deliverable:** Responsible AI Framework + Governance Playbook + Training Programme

---

## 5 · Cross-Cutting Capabilities

### 5.1 Technology Landscape Advisory
Not every problem needs a Microsoft answer. We assess the full landscape and recommend the best tool for the job.

- Cross-platform architecture reviews (Azure, AWS, GCP, on-prem, SaaS)
- Vendor and tooling evaluation
- Licensing and cost-optimisation analysis
- Build-vs-buy-vs-partner recommendations

### 5.2 Enablement & Training
Practical, role-specific training to make your teams self-sufficient.

- Data literacy for business teams
- Power Platform and automation training (citizen and professional developers)
- AI and Copilot adoption workshops
- Data engineering and platform training (Azure, Fabric, open-source)
- Executive and board-level AI literacy sessions

### 5.3 Fractional Leadership
Embed a senior specialist in your organisation without a full-time hire.

- Fractional CDO / Head of Data
- Fractional AI Architect
- Fractional Automation / Digital Transformation Lead
- Fractional Data Platform Engineer

**Engagement model:** 1–3 days/week retainer, 3-month minimum

---

## Engagement Models

| Model | Best For | Typical Duration |
|---|---|---|
| **Audit & Assessment** | Understanding where you are | 2–6 weeks |
| **Strategy & Roadmap** | Knowing where you're going | 4–10 weeks |
| **Advisory Retainer** | Ongoing guidance and unblocking | 3–12 months |
| **Build & Delivery** | Implementing solutions | Fixed-scope or embedded |
| **Enablement & Training** | Upskilling your teams | 1–8 weeks |
| **Fractional Leadership** | Senior expertise without full-time cost | 3+ months |

Most clients start with an **Audit** or **Assessment**, move to a **Strategy & Roadmap**, and then engage us for **Build** or **Advisory** work. There is no obligation to continue, and we will always tell you if you don't need us.

---

## What Makes Us Different

- **M365-native, not M365-captive.** We know the Microsoft stack deeply, but we'll recommend Azure, AWS, open-source, or a SaaS tool when it's the right answer.
- **Advisory-first.** We earn trust by being honest about what a platform can and can't do before we sell you a build.
- **Cross-disciplinary by design.** Data, automation, and AI are not separate problems. We solve them together.
- **Responsible by default.** Governance, ethics, and risk are built into every engagement, not bolted on.

---

*This catalogue is a living document. Engagements are tailored to your organisation, sector, and maturity. The structure above is a menu, not a script.*

---

Want me to adjust the tone, add pricing tiers, restructure the sections, tailor it to a specific industry (e.g., healthcare, finance, public sector), or produce this as a formatted PDF-ready document?

Review factual support, instruction compliance, completeness, coherence and limitations. Compare paired before/after bodies after both phases; record a reasoned judgement.

## pub-ef1fe5ad746d4d8db235204f7421260d

Prompt:
Make a scope and limitation for a research about investigating and defining the tool's effectiveness in promoting accurate and consistent drilling centers across many repeated trials. This includes examining the alignment guides' functionality and assessing its performance in maintaining precision across a range of workpiece dimensions and different materials. The study seeks to establish the tool's limitations and capabilities, providing valuable insights into its practical utility in various drilling scenarios.

Response:
# Scope and Limitations

## Scope

This study investigates and defines the effectiveness of a specialized drilling alignment tool in promoting accurate and consistent drilling centers across a large number of repeated trials. The research is bounded by the following parameters:

**1. Tool Performance Evaluation**
The study examines the tool's capacity to produce repeatable, centered holes under controlled conditions. Effectiveness is quantified through measurable metrics, including positional deviation (in millimeters), concentricity error, and the coefficient of variation across successive trials. A minimum of [X] repeated trials per test condition will be conducted to establish statistical reliability in the tool's consistency.

**2. Alignment Guide Functionality**
The investigation includes a detailed functional assessment of the tool's alignment guides—evaluating how the guide geometry, clamping mechanism, and reference surfaces contribute to hole-center accuracy. The study examines both the static alignment (initial positioning) and dynamic alignment (maintenance of alignment under drilling forces) of the guides.

**3. Workpiece Dimensional Range**
The tool's precision-maintenance capability is assessed across a defined range of workpiece dimensions, including variations in plate thickness, diameter, and overall geometry. This encompasses both small and moderately sized workpieces within the tool's stated operational envelope.

**4. Material Variability**
The study evaluates tool performance across a selected range of materials, including but not limited to mild steel, stainless steel, aluminum alloys, and selected plastics/composites. The focus is on how material hardness, machinability, and thermal behavior influence the tool's ability to maintain drilling-center accuracy.

**5. Practical Utility Assessment**
The research seeks to establish the tool's practical applicability in common workshop and production drilling scenarios, providing actionable insights into its capabilities, optimal operating parameters, and the boundaries within which it delivers reliable performance.

---

## Limitations

The following constraints define the boundaries of this study and must be considered when interpreting its findings:

**1. Material Selection**
The study is limited to a predefined set of materials. It does not encompass every available substrate (e.g., titanium alloys, ceramics, hardened tool steels, or exotic composites). Findings regarding material-dependent performance cannot be universally extrapolated to untested materials.

**2. Workpiece Dimensional Boundaries**
The dimensional range of workpieces tested is constrained by the tool's physical design and the laboratory's available specimens. Extremely large, thin, or irregularly shaped workpieces fall outside the study's scope, and conclusions regarding precision maintenance are valid only within the tested dimensional envelope.

**3. Drill Bit and Speed Parameters**
The investigation employs a specific set of drill bit diameters, geometries, and cutting speeds. It does not exhaustively cover all possible bit sizes, coatings, or feed-rate combinations. Performance under untested cutting parameters may differ from the reported results.

**4. Environmental and Operational Conditions**
Trials are conducted under controlled laboratory conditions. The study does not account for the full spectrum of real-world workshop variables such as ambient temperature fluctuations, vibration from adjacent machinery, dust contamination, or inconsistent power supply, all of which may affect alignment accuracy in practice.

**5. Operator Variability**
While the tool is designed to reduce operator-dependent error, the study acknowledges that setup technique, clamping force application, and operator experience can introduce variability. The study controls for this within its protocol but does not eliminate it entirely, and results may vary with less experienced users.

**6. Tool Wear and Long-Term Durability**
The study assesses performance over a defined number of trials. It does not evaluate the tool's long-term degradation over thousands of cycles, nor does it address maintenance intervals, guide-surface wear, or the need for recalibration over extended service life.

**7. Single-Tool Focus**
The research is specific to the particular tool model and design under investigation. Findings are not intended as a comparative benchmark against all available drilling alignment solutions on the market, nor do they generalize to differently designed tools.

**8. Statistical Sample Size**
Although repeated trials are conducted to ensure consistency, the total number of trials per condition is finite. Statistical conclusions are drawn within the confidence levels established by the sample size and may not capture rare, outlier performance events.

**9. Exclusion of Multi-Axis and Complex Drilling**
The study focuses on single-axis, perpendicular drilling operations. It does not address angled drilling, multi-hole pattern drilling, or compound drilling sequences, which may impose different demands on the alignment guides.

---

*By clearly delineating both the scope and the limitations, this study provides a transparent and reproducible framework for evaluating the tool's practical utility, while acknowledging the conditions under which its conclusions are valid and the areas requiring further investigation.*

Review factual support, instruction compliance, completeness, coherence and limitations. Compare paired before/after bodies after both phases; record a reasoned judgement.

## dom-15

Prompt:
Propose a research agenda for reducing hallucinated citations in language-model outputs. Structure it as three to five concrete experiments with hypotheses, datasets or how you would build them, metrics, expected outcomes, and what each result would change about the next step.

Response:
# Research Agenda: Reducing Hallucinated Citations in LLM Outputs

## Framing

"Hallucinated citation" is not one failure. Before fixing it, the agenda distinguishes three sub-failures that demand different interventions:

- **Type A – Phantom reference.** The citation does not exist anywhere (fake title, fake author, or a real title paired with a nonexistent author/year).
- **Type B – Wrong metadata.** The paper exists, but the model got the year, journal, volume, or DOI wrong.
- **Type C – Unsupported claim.** The paper exists and the metadata is correct, but it does not actually support the sentence it is attached to.

Most published evaluations conflate these. The agenda below treats them as separate targets and sequences experiments so that each one's result gates the next.

---

## Experiment 1 – Build and validate a citation-hallucination benchmark

**Hypothesis.** A single, well-constructed benchmark stratified by Type A / B / C failure, by domain, and by citation format (inline vs. reference list) will reveal that current models fail at very different rates on each subtype, and that the dominant subtype shifts with domain.

**Dataset construction.**
1. Sample 2,000 factual claims from three domains: biomedical (PubMed abstracts), computer science (arXiv abstracts), and social science (JSTOR abstracts). Each claim is a single sentence from a real paper, with the *correct* citation recorded.
2. For each claim, prompt a panel of four frontier models (e.g., GPT-4o, Claude, Gemini, Llama-3-70B) to produce a citation in a fixed format (author, title, venue, year, DOI).
3. Verify every generated citation programmatically:
   - *Existence:* resolve the DOI via CrossRef; if no DOI, fuzzy-match title+author against the Semantic Scholar and OpenAlex APIs.
   - *Metadata:* compare returned fields against the API record.
   - *Support:* for citations that do exist, use a judge model (a strong model with the cited paper's abstract full-text in context) to label whether the paper supports the claim. Human-annotate a 250-claim stratified subset to calibrate the judge.
4. Tag every (claim, model, citation) tuple with its failure type.

**Metrics.**
- Hallucination rate per 100 citations, broken into Type A, B, C.
- Existence rate, metadata-accuracy rate, and claim-support rate as separate axes.
- Calibration: does the model's verbalized confidence ("I'm fairly sure this is from *Nature* 2019") predict actual correctness?

**Expected outcomes.**
- Type A (phantom) and Type C (unsupported) will dominate over Type B, but the ratio will differ by domain (biomedical likely has more Type C because models confuse similar-sounding studies).
- Judge-model agreement with human labels will land around 0.80–0.88 on the support axis, confirming it is usable for larger-scale evaluation but not for the final metric.

**What the result changes.**
- If Type C dominates, Experiments 2 and 3 must optimize *claim-citation alignment*, not just retrieval accuracy. If Type A dominates, the problem is closer to a knowledge-grounding issue and retrieval may not help enough.
- The benchmark becomes the shared evaluation harness for every subsequent experiment. If the judge model disagrees with humans on more than 15 % of the calibration set, Experiment 1 gets a second round with a stronger judge or a human-only subset before anything else proceeds.

---

## Experiment 2 – Retrieval-grounded citation generation (RAG for citations)

**Hypothesis.** Replacing the model's parametric memory with a retrieval step over a citation index (CrossRef / OpenAlex / Semantic Scholar) will cut Type A hallucinations by >70 % and Type B by >50 %, but will *increase* Type C errors because the model will cite the most textually similar paper rather than the most *supportive* one.

**Dataset.** The Experiment 1 benchmark, plus a larger 10,000-claim set drawn the same way, to give power for the Type C measurement.

**Method.**
- For each claim, retrieve the top-20 candidate references from OpenAlex (title + abstract + citation context) using a dense retriever (e.g., a fine-tuned BGE or a ColBERT-style model).
- Prompt the model to select one or more retrieved references and write the citation, with instructions to output "I could not verify a supporting source" when none of the candidates clearly support the claim.
- Compare three prompt variants: (a) retrieve-then-select, (b) retrieve-then-verify-then-select (model must state *why* the candidate supports the claim before citing it), (c) retrieve-then-select with a refusal option.

**Metrics.**
- Same three-axis breakdown as Experiment 1 (existence, metadata accuracy, claim support), per variant.
- Refusal rate and its precision: when the model says "no supporting source," is it actually correct?
- Latency and API cost per citation.

**Expected outcomes.**
- Type A drops sharply (the model can only cite what retrieval returns). Type B drops moderately (metadata comes from the index, not the model's memory). Type C *rises* or stays flat in variant (a) because retrieval surfaces topically similar but non-supportive papers.
- Variant (b) recovers some of the Type C loss at the cost of higher refusal rates and latency.

**What the result changes.**
- If Type C is the residual bottleneck (likely), Experiment 3 must target the *support judgment* specifically, not general retrieval quality.
- If the refusal option in variant (c) achieves high precision (>85 %) at an acceptable recall cost, it becomes a viable production fallback and the agenda shifts toward *when to refuse* rather than *how to retrieve better*.
- If retrieval quality (MRR@20) is the binding constraint, a sub-experiment to fine-tune the retriever on citation-support pairs precedes Experiment 3.

---

## Experiment 3 – Train a lightweight citation-support verifier

**Hypothesis.** A small (1–3 B parameter) cross-encoder fine-tuned on (claim, retrieved-abstract, support-label) triples can classify whether a specific paper supports a specific claim with ≥90 % accuracy, and when deployed as a post-hoc filter on Experiment 2's outputs, it removes most Type C hallucinations without removing correct citations.

**Dataset construction.**
1. From Experiment 2's retrieval results, collect 150,000 (claim, candidate-paper-abstract) pairs.
2. Label 30,000 of them with the judge model from Experiment 1; human-annotate 3,000 for calibration and to build a gold test set of 2,000 held-out pairs.
3. Augment with hard negatives: papers that share keywords with the claim but address a different question (sampled from the same journal/year window).

**Method.**
- Fine-tune a cross-encoder (e.g., a 1.5 B encoder like `microsoft/MiniLM` or a small Llama-based encoder) to output a support score.
- Deploy as a filter: after the LLM generates a citation, the verifier scores the (claim, cited-abstract) pair; scores below a threshold trigger either a re-retrieval or a refusal.
- Ablate: threshold sweep, single-pass vs. two-pass (re-retrieve if filtered), and a variant where the verifier's score is fed back into the LLM as a prompt signal ("the cited paper's support score is 0.3; reconsider").

**Metrics.**
- Verifier AUC and accuracy on the gold test set; confusion matrix stratified by failure type.
- Downstream: Type C rate after filtering, measured on the Experiment 1 benchmark.
- False-refusal rate: fraction of *correct* citations the verifier rejects.
- Added latency per citation.

**Expected outcomes.**
- Verifier AUC ≥ 0.92 on the gold set. Filtering at a threshold that keeps 95 % of correct citations removes ~60–70 % of Type C hallucinations.
- The two-pass re-retrieval variant recovers some of the false-refusal losses.
- The prompt-feedback variant (giving the score back to the LLM) helps modestly but is less reliable than hard filtering.

**What the result changes.**
- If the verifier's false-refusal rate is too high (>10 %), the agenda adds a second, larger verifier (7–13 B) or a cascade (small verifier → large verifier on uncertain cases) before moving to Experiment 4.
- If the verifier is strong enough, Experiment 4 can use it to generate *training signal* (RL reward, DPO preference pairs) rather than only acting as a post-hoc filter.
- If AUC is below 0.88, the support-judgment task is harder than assumed, and Experiment 4 pivots toward improving the *retrieval* side (Experiment 2) rather than the verification side.

---

## Experiment 4 – Training-time intervention: preference optimization with citation-accuracy rewards

**Hypothesis.** Fine-tuning the base model with Direct Preference Optimization (DPO) or RLHF using the Experiment 3 verifier as a reward signal will reduce Type A and Type C hallucinations in the model's *parametric* output (i.e., without retrieval), bringing un-retrieved citation accuracy within 10–15 percentage points of the retrieval-grounded system, at the cost of some coverage.

**Dataset construction.**
1. Generate 50,000 (claim, citation) pairs from the base model without retrieval.
2. Score each pair with the Experiment 3 verifier and the CrossRef existence check.
3. Form preference pairs: for each claim, pair a high-scoring citation (chosen) with a low-scoring one (rejected). Discard pairs where both scores are high or both low.
4. Reserve 5,000 claims as a held-out test set (the Experiment 1 benchmark).

**Method.**
- Run DPO (or GRPO / RLOO if compute allows) on a 7–13 B open model (e.g., Llama-3-8B, Mistral-7B).
- Reward function: +1 if the citation exists (CrossRef), +0.5 if metadata matches, +1 if the verifier support score > 0.8, −1 if any check fails.
- Ablate: (a) DPO only, (b) DPO + a small supervised pre-training pass on 100k verified (claim → correct citation) pairs, (c) DPO with a *refusal* option in the output space.

**Metrics.**
- Same three-axis hallucination breakdown on the held-out benchmark.
- Coverage: fraction of claims for which the model produces *any* citation vs. refuses.
- Calibration of the model's stated confidence.
- Qualitative: does the model learn to hedge ("this may be from a 2019 study, possibly *Smith et al.*") rather than fabricate?

**Expected outcomes.**
- Type A drops significantly (the model learns that fabricated references are penalized). Type C drops modestly because the verifier reward is noisy. Type B improves because correct metadata is reinforced.
- The refusal option (ablation c) is key: without it, the model learns to always emit *some* citation and the hallucination rate plateaus. With it, the model trades ~15–20 % coverage for a large hallucination-rate drop.
- The supervised pre-training pass (ablation b) helps most on Type B (metadata memorization) and least on Type C.

**What the result changes.**
- If the trained model with refusal matches or beats the retrieval-grounded system (Experiment 2) on Type A + C combined, the agenda can skip the retrieval infrastructure for low-stakes use cases and reserve RAG for high-stakes ones.
- If the trained model still hallucinates Type C at >20 %, the verifier signal was too noisy to teach fine-grained support judgment, and the agenda invests in a *larger* verifier or a multi-step reasoning chain for the reward model before re-running.
- If coverage drops below 70 %, the refusal behavior is too aggressive, and the next iteration adjusts the reward to penalize refusal on claims that *do* have a retrievable source.

---

## Experiment 5 – Compositional system and ablation

**Hypothesis.** A pipeline of *retrieval (Exp 2) → verifier filter (Exp 3) → trained generator with refusal (Exp 4)*, with the verifier score fed back as a prompt signal, achieves a hallucination rate below 5 % per 100 citations across all three types while maintaining ≥85 % coverage, and no single component accounts for more than 40 % of the total improvement.

**Dataset.** The full Experiment 1 benchmark (2,000 claims × 3 domains) plus a new 5,000-claim set from a fourth domain (law, using Westlaw/HeinOnline abstracts) to test generalization.

**Method.**
- Assemble the full pipeline. Ablate each component:
  - No retrieval (parametric only, trained model)
  - Retrieval only (no verifier, no training)
  - Retrieval + verifier (no training)
  - Trained model only (no retrieval, no verifier)
  - Full system
- For the full system, test two routing strategies: (a) always run the full pipeline, (b) the trained model first attempts a citation; the verifier checks it; only if the verifier score is below threshold does the system fall back to retrieval.
- Measure cost (API calls, tokens, latency) per citation for each configuration.

**Metrics.**
- Three-axis hallucination rate, coverage, refusal precision/recall, latency (p50, p95), and cost per 1,000 citations.
- Domain generalization: does the system's performance on the law domain match its performance on the three training domains?
- Human evaluation on 300 outputs: a blind study where annotators rate citation usefulness on a 1–5 scale, to catch failures that automated metrics miss (e.g., a real paper cited for a tangentially related claim).

**Expected outcomes.**
- The full system hits <5 % hallucination rate; the single best component (likely retrieval + verifier) gets to ~12–15 %.
- The routing strategy (b) cuts cost by 40–60 % versus always running retrieval, at a small hallucination-rate increase (~1–2 pp).
- Domain generalization is imperfect: the law domain shows a 3–5 pp higher hallucination rate because the verifier was trained on scientific abstracts.

**What the result changes.**
- This is the terminal experiment, but its ablation table determines the *deployment* architecture: if retrieval is the dominant contributor, the team invests in retrieval infrastructure (index freshness, coverage of paywalled sources). If the trained model's refusal behavior is the dominant contributor, the team invests in better reward modeling.
- If the law-domain gap is large, the agenda spawns a follow-up round: retrain the verifier on a domain-specific corpus and re-run the ablation.
- The human-evaluation results feed back into Experiment 1's benchmark design for the next iteration, closing the loop.

---

## Cross-cutting notes

- **Ground-truth freshness.** CrossRef and OpenAlex records lag by weeks to months. Any citation published in the last 90 days is unverifiable by these APIs. The benchmark must stratify by publication recency, and the metrics must report a separate "unverifiable" bucket rather than counting recent citations as hallucinations.
- **Judge-model circularity.** Using a frontier model to label support (Exp 1, 3) and then training a verifier that the same model's outputs are evaluated against (Exp 4) risks self-reinforcement. Mitigate by using a *different* model family for the judge than the one being trained, and by keeping the human-annotated gold set as the final arbiter.
- **Ethical and legal dimension.** In legal and medical domains, a hallucinated citation is not just an accuracy metric—it can mislead a clinician or litigant. The agenda should include a risk-stratified evaluation: report hallucination rates separately for high-stakes vs. low-stakes claims, and treat the refusal rate as a *feature* (the system should say "I don't have a verified source" rather than guess) rather than a failure.

Review factual support, instruction compliance, completeness, coherence and limitations. Compare paired before/after bodies after both phases; record a reasoned judgement.

## dom-09

Prompt:
A proposed metric defines "effective context length" as the longest context at which a model still answers a retrieval question correctly. Critique it and propose a better definition that separates retrieval depth from reasoning depth, including how each curve should be measured and what threshold semantics to use.

Response:
# Critique and Redesign of "Effective Context Length"

## Critique of the Proposed Metric

The metric—*the longest context at which a model still answers a retrieval question correctly*—has five structural problems.

**1. A single binary data point dressed up as a measurement.**
One question at one context length yields one bit. The "longest context" is the maximum of a noisy Bernoulli trial. Swap the question for a harder one and the number shifts by thousands of tokens. You are reporting an order statistic of a one-sample estimate, which is maximally sensitive to the specific item, not the model.

**2. It conflates three distinct failure modes.**
At a long context the model can fail because:
- it cannot *attend* to the token that holds the answer (retrieval / attention-range failure),
- it retrieves the right token but cannot *integrate* it with other context to form the answer (reasoning / working-memory failure),
- the added irrelevant content *distracts* or *confuses* it (noise-robustness failure).

A single "did it get the answer right?" bit cannot tell these apart, so the number is uninterpretable as a capability claim.

**3. No control for question difficulty or distractor density.**
A 4 K-token context with three near-duplicate facts about the same entity is harder than a 1 K context with one unique fact. As context grows, distractor count grows, so the accuracy curve is a mixture of "position got farther" and "haystack got noisier." The metric attributes all degradation to length.

**4. "Retrieval question" is undefined.**
Single-fact lookup, multi-hop, aggregation, and contradiction-detection all collapse into one label. Each stresses a different model subsystem.

**5. No partial credit, no confidence, no distribution.**
Binary correct/incorrect discards the model's uncertainty, and reporting a single threshold hides whether degradation is a cliff or a slope.

---

## Proposed Framework: Two Axes, Two Curves

Replace the single scalar with two curves measured under controlled conditions.

### Axis 1 — Retrieval Depth (RD)

**What it measures.** The maximum *distance* (in tokens, or as a fraction of context length) between the question and the single relevant fact, at which the model can still locate and extract that fact. This isolates the attention / encoding range.

**Construction.**
- Fix a context length *L* (e.g., 4 K, 8 K, 16 K, 32 K, 64 K, 128 K).
- Embed **one** unambiguous, unique fact (the "needle") at a controlled position *p* ∈ {0.05, 0.15, 0.30, 0.50, 0.70, 0.85, 0.95} of the context.
- Fill the rest of the context with *calibrated distractors*: plausible but false facts about the same entity/topic, so that a model that merely pattern-matches on keywords will be penalised. Hold distractor density constant across *p* and *L*.
- The question is always a single-fact lookup: *"What is the value of X?"* No synthesis, no multi-hop.
- Run *n* ≥ 30 independently generated items per (L, p) cell.

**The curve.** For each *L*, plot accuracy *A(L, p)* versus position fraction *p*. You get a family of curves, one per context length.

**Threshold semantics.** Do **not** report "the longest *L* where accuracy = 1." Instead:
- Report the full *A(L, p)* surface.
- If a single scalar is required, define **RD₉₀(L)** = the largest position fraction *p* at which accuracy ≥ 90 % over the item distribution, with a Wilson confidence interval from the *n* items. Then report RD₉₀ as a function of *L*. A model with a flat RD₉₀ ≈ 0.95 across all *L* has full-range retrieval; a model whose RD₉₀ collapses to 0.20 at 64 K has a genuine attention-range limit.
- The *shape* of the curve matters: a smooth decline from *p* = 0.5 → 0.95 indicates gradual attention degradation; a cliff at *p* = 0.50 indicates a hard positional boundary (e.g., a RoPE or positional-encoding limit).

### Axis 2 — Reasoning Depth (RSp)

**What it measures.** The maximum *span* of context that must be held in working memory and integrated to answer correctly, independent of how far any single fact sits from the question. This isolates composition / multi-hop reasoning.

**Construction.**
- Fix context length *L* as above.
- Embed **k** relevant facts (k = 1, 2, 3, 4, 6, 8) at *randomised* positions spread across the context. The question requires combining all *k* facts (e.g., *"Given A, B, and C, what is the result?"* or a multi-hop chain).
- **Critical control:** keep the *span* (distance between the first and last relevant fact) constant across *k* by adjusting spacing, or conversely keep *k* constant and vary span. This lets you separate "more facts to hold" from "facts farther apart."
- Distractor density is held constant as in the RD protocol.
- *n* ≥ 30 items per (L, k, span) cell.

**The curve.** Two families:
- *A(L, k)* at fixed span → how many facts can be integrated?
- *A(L, span)* at fixed *k* → how far apart can the facts be?

**Threshold semantics.**
- **RSp₉₀(L)** = the largest *k* (or span, in tokens) at which accuracy ≥ 90 %, again with a confidence interval.
- Report it as a function of *L*. A model that handles k = 8 at L = 4 K but drops to k = 2 at L = 64 K has a working-memory bottleneck that grows with context, even if its retrieval range is fine.

### Why the separation matters in practice

| Failure mode | RD curve | RSp curve |
|---|---|---|
| Attention range limit (e.g., positional encoding) | Collapses at high *p* for all *L* | Flat (facts are randomised in position) |
| Working-memory / composition limit | Flat (single fact, easy to find) | Collapses as *k* or span grows |
| Distractor confusion | Degrades with *L* even at low *p* | Degrades with *L* even at low *k* |
| Model is simply bad at the task | Low everywhere | Low everywhere |

The original metric would report one number for all four rows. The two-curve framework localises the bottleneck.

---

## Summary of Threshold-Semantics Rules

1. **Never use a hard binary cutoff** ("longest length where correct"). Use a probabilistic operating point (90 % or 95 % accuracy) with a confidence interval over ≥ 30 items per cell.
2. **Report curves, not scalars.** The shape (cliff vs. slope) is as informative as the threshold value.
3. **Control the nuisance variable.** Distractor density, fact uniqueness, and question type must be held constant so that the only free variable is the one you are measuring (position, or span, or k).
4. **Use two independent thresholds** (RD₉₀ and RSp₉₀) as a function of *L*, and present them as a pair. A model's "effective context length" is then a *region* in the (RD, RSp) plane, not a point on the length axis.

Review factual support, instruction compliance, completeness, coherence and limitations. Compare paired before/after bodies after both phases; record a reasoned judgement.
