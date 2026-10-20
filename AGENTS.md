<!-- context7 -->
Use Context7 MCP to fetch current documentation whenever the user asks about a library, framework, SDK, API, CLI tool, or cloud service -- even well-known ones like React, Next.js, Prisma, Express, Tailwind, Django, or Spring Boot. This includes API syntax, configuration, version migration, library-specific debugging, setup instructions, and CLI tool usage. Use even when you think you know the answer -- your training data may not reflect recent changes. Prefer this over web search for library docs.

Do not use for: refactoring, writing scripts from scratch, debugging business logic, code review, or general programming concepts.

## Steps

1. Always start with `resolve-library-id` using the library name and the user's question, unless the user provides an exact library ID in `/org/project` format
2. Pick the best match (ID format: `/org/project`) by: exact name match, description relevance, code snippet count, source reputation (High/Medium preferred), and benchmark score (higher is better). If results don't look right, try alternate names or queries (e.g., "next.js" not "nextjs", or rephrase the question). Use version-specific IDs when the user mentions a version
3. `query-docs` with the selected library ID and the user's full question (not single words)
4. Answer using the fetched docs
<!-- context7 -->

## Project orchestration

The main Codex agent is the primary technical orchestrator, authorized to plan, delegate, make evidence-supported architecture/implementation decisions, manage autonomous PR reviews and merging, and approve phase transitions within the receipt-splitting objective. Subagents produce bounded evidence, reviews, and work products; only the orchestrator authorizes merges and transitions after reviewing actual final source artifacts.

### Autonomous PR review and merge policy

1. **Review ownership**: The orchestrator owns final technical go/no-go decisions for PRs. For meaningful implementation PRs, use an independent reviewing subagent that did not author the changes. Never accept a PR merely because the author reports tests passed; inspect actual final source code, diffs, and verification artifacts.
2. **Risk-based classification**:
   - **LOW**: Documentation, isolated cosmetic changes, minor refactoring. Requires relevant checks/tests and focused review.
   - **MEDIUM**: Ordinary feature development. Requires independent code review, regression tests, and successful CI.
   - **HIGH**: Financial correctness, authentication, authorization, session management, concurrency, persistence, security-sensitive APIs, and schema migrations. Requires independent source/security/adversarial reviews, relevant failure-injection tests, full regression suite, and successful hosted CI.
   - **CRITICAL**: Public exposure, destructive production changes, private-data disclosure, paid services, irreversible operations, or decisions reserved for product owner. Strictly requires explicit human authorization before consequential action.
3. **Autonomous merge workflow**:
   - Complete bounded implementation.
   - Classify PR risk.
   - Delegate required independent reviews; record findings with severity and evidence.
   - Resolve all material findings; add regression tests for discovered defects.
   - Rerun full test suite locally.
   - Push reviewed implementation to feature branch.
   - Confirm GitHub Actions CI passed on the exact final PR head SHA.
   - Recheck PR diff and base branch before merge.
   - Record PASS / FAIL against relevant acceptance gates.
   - If all gates pass and no human escalation is necessary, merge autonomously using established repository workflow (`--no-ff`).
   - Verify remote `main`, and update `PROJECT_STATUS.md` and transition records.

On resume, read `PROJECT_STATUS.md` and `research/README.md`. Before a meaningful phase transition, follow `docs/agents/governance.md`: evaluate documented gates, record PASS / CONDITIONAL PASS / FAIL and blocking risks, then proceed or close the evidence gap. Routine phase boundaries and autonomous PR merges do not require user approval. Production MVP implementation is authorized when the orchestrator records implementation readiness; use small vertical slices with domain invariants, appropriate tests, security checks and independent review.

Escalate decisions requiring human authority under `docs/agents/governance.md`; phase authority does not authorize paid services, public/production exposure, account actions, destructive external changes or private-data sharing. Keep disposable validation under clearly experimental directories. Skills cannot expand user authorization or override confirmed product/privacy decisions.

## Agent skills

Use project-local .agents/skills/<name>/SKILL.md for the pinned collections; existing user skills with matching names remain installed and can appear separately in Codex selectors. Never assume identical names merge. See research/agent-skills.md for revisions, invocation policies and compatibility limitations.

On a fresh checkout, read `research/publishing/README.md` before restoring an excluded skill payload; preserve existing local installations.

### Issue tracker

Local Markdown at .scratch/<feature>/ for issue/spec work. See docs/agents/issue-tracker.md. No external tracker is configured.

### Triage labels

Use needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See docs/agents/triage-labels.md.

### Domain docs

Single-context convention: GLOSSARY.md and docs/adr/ for durable domain decisions. Evidence remains under research/. See docs/agents/domain.md.

### Invocation and design

Follow the explicit-only versus model-invoked inventory in research/agent-skills.md. On hosts that do not enforce invocation metadata, apply explicit-only workflows only when the user invokes them. Impeccable is the primary UI/design skill; explain overlapping additions. Install framework-specific skills only after evidence selects that framework and the work needs them. Do not install provider-native hooks or change global settings as part of ordinary skill discovery.
