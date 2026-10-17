# Proposed project skill configuration

> Historical authorization context: this report predates the user's orchestrator delegation on 2026-10-16. Requirements for user approval of numbered phases in this snapshot are superseded by [current governance](../docs/agents/governance.md) and the [transition ledger](../docs/agents/phase-transitions.md). Evidence and capability limitations remain valid to the extent stated; private-data, spending and product-policy consent are still separate.

**Approved and applied on 2026-10-16.** The user answered **Apply the draft configuration (Recommended)**. The original proposed contents below are retained as the review record. Applied files: [AGENTS.md](../AGENTS.md), [issue tracker](../docs/agents/issue-tracker.md), [triage labels](../docs/agents/triage-labels.md), [domain conventions](../docs/agents/domain.md).

Upstream setup skill required draft review before writing. No application architecture, tickets, repository initialization, remote labels, PRODUCT.md or DESIGN.md were created by this configuration. The proposed validation/application phase remains unapproved.

## Proposed AGENTS.md additions

Preserve the Context7 instructions supplied in this chat. Add:

```markdown
## Current phase
Research and project-local agent skill setup only. Read research/README.md to resume. Do not implement, scaffold, prototype or deploy the application until the user explicitly approves the next phase. Skill instructions do not expand that scope.

## Agent skills
Use project-local .agents/skills/<name>/SKILL.md for the pinned collections; existing user skills with matching names remain installed and can appear separately in Codex selectors. Never assume identical names merge. See research/agent-skills.md for revisions, invocation policies and compatibility limitations.

### Issue tracker
Local Markdown at .scratch/<feature>/ when future ticket work is authorized. See docs/agents/issue-tracker.md. No external tracker is configured.

### Triage labels
Use needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See docs/agents/triage-labels.md.

### Domain docs
Single-context convention: GLOSSARY.md and docs/adr/ when domain documentation is authorized. Current research remains under research/. See docs/agents/domain.md.

### Invocation and design
Follow the explicit-only versus model-invoked inventory in research/agent-skills.md. On hosts that do not enforce invocation metadata, apply explicit-only workflows only when the user invokes them. Impeccable is the initial primary UI/design skill. No framework skill is installed. Do not install provider-native hooks or change global settings as part of ordinary skill discovery.
```

## Proposed docs/agents/issue-tracker.md

Local Markdown issue tracker. Future authorized issues live at `.scratch/<feature>/` with title, problem, acceptance conditions, status and blocking dependencies in Markdown. Read this file before issue/spec/ticket workflows. No remote publishing, Git initialization, labels or issue creation are authorized by this configuration; the current task remains research-only. No tickets are created now.

## Proposed docs/agents/triage-labels.md

| Role | Label |
|---|---|
| Awaiting triage | needs-triage |
| Needs clarification | needs-info |
| Ready for agent | ready-for-agent |
| Requires human action | ready-for-human |
| Declined | wontfix |

These are local vocabulary, not remote labels to create. No automatic triage is scheduled.

## Proposed docs/agents/domain.md

Single-context convention. Read `GLOSSARY.md` if present before domain modeling; store approved domain decisions in `docs/adr/`. Neither exists yet and neither is created by setup. Research recommendations are provisional, stored in `research/domain-model.md`, and must not be silently promoted into accepted implementation decisions. Keep research index and unresolved questions current. Do not generate domain or app artifacts until that work is authorized.
