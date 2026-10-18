The opportunity described in this YC video is to build an AI-native Financial Compliance Agent System that continuously monitors regulations, maps them to a company's obligations, detects compliance risks, and manages evidence and audit workflows.

The important distinction: don't build a chatbot that answers compliance questions. Build a system that executes compliance operations with traceable evidence and controlled human approval.

# 1. Proposed system: ComplianceOS

[PolicyPulse AI — Autonomous Compliance Monitoring Platform | By Mohamed Javid](https://images.openai.com/static-rsc-4/cuU2q63bvrBCR43df_kF-KjEYkKZvX07a_602ulde5KiPHL5QnF0g0SNX7zcfYucwmUZKu2yp2tT_nS234sp2WC8qaOYAP2XKNr1P7QFduC_WkM5KMiZSoksfmBRfQutVjZQNPrbTIEnX2ydZmAnSW-IQzKbGC2s7BFVdYfIiWM?purpose=inline)

[commudle.com](https://www.commudle.com/builds/policypulse-ai-autonomous-compliance-monitoring-platform?utm_source=chatgpt.com)

## ComplianceOS — AI agents for financial compliance

An autonomous compliance operations platform for companies operating across multiple jurisdictions.

The system should answer five questions continuously:

- What regulations apply to this company?
- What obligations must it satisfy?
- What has changed since the last review?
- Where are the compliance gaps and financial risks?
- What evidence proves that the company is compliant?

## 2. Multi-agent architecture

Compliance Control Center

Obligations · Risk scores · Deadlines · Approvals · Audit reports

Compliance Orchestrator

Plans tasks, routes work to agents, manages state, retries failures, and enforces permissions.

1\. Regulatory Intelligence

Collects regulations, detects amendments, tracks effective dates and jurisdictional differences.

2\. Obligation Mapping

Maps legal requirements to entities, licenses, business activities, and internal controls.

3\. Risk & Anomaly Detection

Analyzes transactions, accounting data, exceptions, and control failures.

4\. License & Deadline Agent

Tracks licensing, renewals, reporting deadlines, and outstanding tasks.

5\. Evidence & Audit Agent

Collects supporting documents, maintains evidence links, and prepares audit packages.

6\. Reporting Agent

Generates compliance reports, executive summaries, and remediation plans.

Shared Compliance Intelligence Layer

Regulatory knowledge base · Company policy graph · Evidence store · Rules engine · Immutable audit events · Human approvals

The agents should not operate as six independent chatbots. They should be specialized workers coordinated through a stateful workflow engine and a shared, versioned compliance data model.

## 3. How the system works in practice

Example: a US financial services company operates in 12 states.

1. Ingest regulatory changes

   The Regulatory Intelligence Agent retrieves updates from official state regulators and other authoritative sources. Each update is stored with its source, publication date, effective date, and version.
2. Determine applicability

   The Obligation Mapping Agent checks which legal entities, products, licenses, and business activities are affected. It distinguishes a potentially relevant change from a confirmed obligation.
3. Identify the compliance gap

   The system compares the new requirement against existing policies, controls, licenses, and documented evidence.
4. Assign remediation

   The workflow engine creates a task, assigns an owner, calculates a deadline using verified rules, and escalates overdue items.
5. Collect and validate evidence

   The Evidence Agent requests required documents, checks completeness, identifies missing information, and links every finding to its supporting evidence.
6. Generate the audit package

   The Reporting Agent assembles the requirement, source text, applicability decision, control evidence, remediation history, and reviewer approvals.

The result is a continuously updated compliance operation instead of a spreadsheet that becomes outdated after the next regulatory change.

## 4. Technical architecture

Given your existing experience with Python, FastAPI, LangGraph, PostgreSQL, and RAG, this is a practical architecture to implement.

Frontend

Next.js, TypeScript, React

Compliance dashboard, obligations, evidence review, risk queue, approvals.

Agent orchestration

Python, FastAPI, LangGraph

Stateful workflows, typed agent outputs, checkpoints, retries, human-in-the-loop approvals.

Data and retrieval

PostgreSQL, pgvector or Qdrant, object storage

Versioned regulatory documents, company records, semantic retrieval, evidence files, relational obligation tracking.

Deterministic compliance services

Rules engine, RBAC, policy checks, event logging

Deadline calculations, authorization, control validation, audit events, approval gates.

Integrations and background jobs

Celery or Temporal, webhooks, API connectors

Accounting platforms, document repositories, licensing systems, regulator feeds, scheduled monitoring.

### Important engineering decision

Use an LLM for interpreting unstructured regulatory language, extracting obligations, matching evidence, and drafting explanations.

Use deterministic code for calculations, permissions, deadline enforcement, validation, and workflow transitions.

Use retrieval-augmented generation (RAG) to ground decisions in authoritative documents. Store the precise document version and text passages that support every material conclusion. Vector similarity alone is not sufficient for determining legal applicability.

## 5. Core data model

These entities are the foundation of the product.

| Entity              | Purpose                                                      |
| ------------------- | ------------------------------------------------------------ |
| `Organization`      | Company profile and business activities                      |
| `LegalEntity`       | Subsidiaries and registered entities                         |
| `Jurisdiction`      | Countries, states, and regulatory regimes                    |
| `License`           | License status, conditions, expiry, renewal                  |
| `RegulationVersion` | Versioned source documents and amendments                    |
| `Obligation`        | Normalized requirement and applicability                     |
| `Control`           | Internal procedure intended to satisfy an obligation         |
| `Evidence`          | Documents, transactions, attestations, and source references |
| `ComplianceFinding` | Gap, anomaly, severity, and supporting evidence              |
| `RemediationTask`   | Owner, deadline, status, and resolution                      |
| `Approval`          | Reviewer, decision, timestamp, and rationale                 |
| `AuditEvent`        | Append-only history of actions and decisions                 |

The relationships matter more than the number of agents. For example, one regulation may create several obligations; one obligation may be satisfied by multiple controls; and one control may support obligations across multiple jurisdictions.

## 6. Build the first version around one narrow use case

Do not start by supporting every financial regulation, every country, and all six agents. That creates an enormous data and validation burden before you have a useful product.

[Business Licensing Service | Harbor Compliance | www.harborcompliance.com](https://images.openai.com/static-rsc-4/VpYjWiPVlWhxhph7nKpHLBQO3O67ul4RAOYhHvBcfVwWpBuYRQqgs7mQh0J1W6bE3oiLyZdqVDdUuqjpjQncCaRNnYEY5t5dJNwDM6E1CuYuXkY3ntHyvVq-CPV7TWLw7xH0YHak5Lx6kjbo9BnHbB3XlQKnM-D1C3F_zhtIS4I?purpose=inline)

MVP: License and regulatory deadline management

Recommended starting point

Track business licenses, renewal dates, jurisdiction-specific obligations, supporting documents, and escalation workflows for one customer segment.

[4CRisk.ai - Award-winning AI-powered products for Risk and Compliance](https://images.openai.com/static-rsc-4/d0KX2f-MhfcKHweXTBY10XBL96t3j_Bdt8WCA1QzRTg_6fopeptTndQL0RLMlig7qnddyGH9qbdRXrCP1bzNiKwb38wcldChg9nZDDylqCkX48YXZMuVYR10O1Y_ji_BJyNiM6qfroGztPbNoNRFaAkHEtWWltGPlbKnERon57s?purpose=inline)

Phase 2: Regulatory change monitoring Detect updates, compare versions, identify potentially affected obligations, and create review tasks with citations.

[AI Internal Audit Platform | Continuous Risk Monitoring](https://images.openai.com/static-rsc-4/TxiQVE7lu8yBmTTK9X72LPDF-wex5nAaeS70Q7MPYSiLx1vB-Zm6sGRaIUux8aXZjtJQerda2_cTZiDsAgpTVM0F5gLjITHzHnaDjW-t8RHDGS0OTieBl3ozgIxLajKQJd1dq0NbgtczUvkmEKRCCROiqUvYSBA-Ap8rXxXypNw?purpose=inline)

Phase 3: Evidence and controls Connect obligations to internal controls and evidence, identify gaps, and generate reviewable audit packages.

A license-management MVP is a more manageable starting point than autonomous transaction surveillance. It has clear entities, deadlines, workflows, and measurable outcomes. It also directly addresses the state-by-state licensing problem described in the video.

## 7. Safety and trust requirements

Financial compliance software must be designed around verifiability, not just agent autonomy.

- Source provenance: Every regulatory finding must link to the authoritative source and its version.
- No unsupported conclusions: Mark uncertain applicability for human review rather than presenting it as settled law.
- Human approval: Require authorized reviewers for consequential legal interpretations, filings, and changes to compliance status.
- Tenant isolation: Prevent one organization's documents, embeddings, or findings from leaking to another.
- Tamper-evident audit trail: Record the actor, action, timestamp, inputs, outputs, evidence, and approvals.
- Prompt-injection defense: Treat downloaded regulatory documents and uploaded files as untrusted data, never as instructions to agents.
- Evaluation: Test extraction accuracy, missed obligations, false alerts, citation correctness, and whether regulatory changes are detected in time.

## 8. What would make this a real business?

The differentiator is not simply multi-agent orchestration. Other compliance platforms already automate parts of monitoring, controls, and reporting.

The defensible product would combine a continuously updated regulation-to-obligation-to-control-to-evidence graph, reliable integrations, jurisdiction-specific workflows, and an auditable execution history. Over time, that creates operational value beyond a generic LLM interface.

Measure the product using concrete metrics: time to identify a regulatory change, time to prepare an audit package, missed renewal rate, false-positive rate, and hours of manual work eliminated.

My recommendation: Build a focused compliance operations platform for a specific industry and jurisdiction first. Make every result traceable, every workflow stateful, and every consequential action permission-controlled. Expand the agent system only after the underlying obligation and evidence model is reliable.
