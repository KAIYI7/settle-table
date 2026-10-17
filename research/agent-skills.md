# Agent skills: inspection and installation record

Publication note2026-10-17: the complete local installations described here are preserved. Git includes Matt's MIT collection and provenance/license records, while the Impeccable payload is locally installed but excluded pending redistribution-notice review. Follow [portable restore notes](publishing/README.md); installation destinations in the public manifest are project-relative.

> Historical authorization context: this report predates the user's orchestrator delegation on 2026-10-16. Requirements for user approval of numbered phases in this snapshot are superseded by [current governance](../docs/agents/governance.md) and the [transition ledger](../docs/agents/phase-transitions.md). Evidence and capability limitations remain valid to the extent stated; private-data, spending and product-policy consent are still separate.

Access date: 2026-10-16. Status: upstream inspection, installation and user-approved project configuration complete.

## Verified upstream snapshots
| Collection | Official upstream | Exact inspected revision | Declared version | License |
|---|---|---|---|---|
| Matt Pocock | https://github.com/mattpocock/skills | `49dd158d1076134a641b33efb035946536778336` | package/plugin 1.3.1 | MIT |
| Impeccable | https://github.com/pbakaus/impeccable | `5bf0a069dc857e1b5f4b090e004d9d5b231416ca` | package/skill 4.6.0; engine tracked separately | Apache-2.0 |

Matt's `.claude-plugin/plugin.json` explicitly publishes the collection. Installation is enumerated dynamically from that manifest, not a remembered skill count. Repository `skills/misc` and `skills/in-progress` contain additional non-published experiments; these are inventoried separately and excluded, including framework-specific setup experiments. The complete published manifest has 27 entries at this revision. See [discovery inventory](skill-discovery.json).

## Conflicts reported before installation
All 27 Matt names already exist under `~/.agents/skills/`; each existing SKILL.md has different bytes from the fetched upstream copy. Existing `impeccable` reports 4.5.2, versus upstream 4.6.0. Existing provenance/commit is unknown: do not label those user copies obsolete or replace them. No project skill directory existed initially.

Resolution: install pinned project-local copies at `.agents/skills/<name>` and preserve every user installation in place. Codex documentation says identical skill names are not merged and both can appear in selectors; do not assume project scope silently wins. Project guidance must identify the project-local path for this project. Global disabling/removal is not performed. Existing files therefore remain their own preservation copy; no destructive migration requires a backup.

## Compatibility (verified documentation; runtime activation still to check)
- Both current Codex and Antigravity IDE document workspace `.agents/skills/<name>/SKILL.md`. Antigravity also supports legacy `.agent/skills`; no duplicate compatibility tree is needed.
- Codex supports explicit skill mentions and description-based selection. Matt's `agents/openai.yaml` encodes explicit-only policy; preserve it. Antigravity's documented metadata does not establish enforcement of this Codex policy or Claude `disable-model-invocation`; follow the invocation inventory conservatively.
- Antigravity documents slash commands; Codex CLI documents `$name` and `/skills`. Do not assume slash-command spelling, hook support, or Claude/Gemini-specific tool calls are portable.
- Impeccable has a provider-neutral generated copy under upstream `.agents/skills/impeccable`; use that instead of its Claude plugin build. It bundles Windows `.cmd` and Unix launchers. Native hooks and browser integrations are separate provider capabilities.
- Codex can show duplicate names and can truncate a large initial skill catalogue. Explicit path selection is the reliable fallback. Discovery after installation should be checked next turn; a restart may be needed.

Sources: [Codex skill documentation](https://learn.chatgpt.com/docs/build-skills), [Antigravity IDE skills](https://antigravity.google/docs/skills?app=antigravity-ide), upstream READMEs, manifests, SKILL.md and agents/openai.yaml at the revisions above. No Antigravity session is available here to verify runtime activation.

## Scope and configuration
Impeccable is the primary design skill. No second UI/design collection or framework skill is installed initially. Installing a skill does not authorize its application implementation commands. User scope overrides any skill that asks to build, prototype, commit, open issues, or deploy.

The upstream `/setup-matt-pocock-skills` workflow asks for tracker, labels and domain-document conventions, plus review before writing. The user approved the concrete research-only draft, and project-local configuration is now applied in `AGENTS.md` and `docs/agents/`. No remote tracker action or application/domain scaffold was created. Runtime design initialization is not application work authorized in this phase.

## Installed skill invocation inventory

All Matt entries share upstream/version/revision above and install at `.agents/skills/<name>/`; no per-skill semantic version is declared. `Explicit` means upstream Codex policy denies implicit invocation. `Both` means explicit or description-triggered invocation.

| Skill | Invocation | Upstream path |
|---|---|---|
| ask-matt | Explicit | `./skills/engineering/ask-matt` |
| diagnosing-bugs | Both | `./skills/engineering/diagnosing-bugs` |
| grill-with-docs | Explicit | `./skills/engineering/grill-with-docs` |
| triage | Explicit | `./skills/engineering/triage` |
| improve-codebase-architecture | Explicit | `./skills/engineering/improve-codebase-architecture` |
| setup-matt-pocock-skills | Explicit | `./skills/engineering/setup-matt-pocock-skills` |
| tdd | Both | `./skills/engineering/tdd` |
| to-spec | Explicit | `./skills/engineering/to-spec` |
| to-tickets | Explicit | `./skills/engineering/to-tickets` |
| wayfinder | Explicit | `./skills/engineering/wayfinder` |
| implement | Explicit | `./skills/engineering/implement` |
| implement-spec | Explicit | `./skills/engineering/implement-spec` |
| prototype | Both | `./skills/engineering/prototype` |
| research | Both | `./skills/engineering/research` |
| domain-modeling | Both | `./skills/engineering/domain-modeling` |
| codebase-design | Both | `./skills/engineering/codebase-design` |
| code-review | Both | `./skills/engineering/code-review` |
| pr | Both | `./skills/engineering/pr` |
| retro | Explicit | `./skills/engineering/retro` |
| wizard | Both | `./skills/engineering/wizard` |
| grill-me | Explicit | `./skills/productivity/grill-me` |
| grilling | Both | `./skills/productivity/grilling` |
| handoff | Explicit | `./skills/productivity/handoff` |
| teach | Explicit | `./skills/productivity/teach` |
| to-questionnaire | Explicit | `./skills/productivity/to-questionnaire` |
| wait-what | Explicit | `./skills/productivity/wait-what` |
| writing-for-agents | Both | `./skills/productivity/writing-for-agents` |
| impeccable | Both; commands explicit or clearly requested | `.agents/skills/impeccable` |

## Installation verification

Completed 2026-10-16 using the bundled skill-installer helper with explicit `--ref` SHA and project `--dest`; it refuses existing destinations. 27 manifest-listed Matt skills plus one provider-neutral Impeccable skill installed. No published manifest entry was skipped. The eleven SKILL.md entries under misc/in-progress are listed in [excluded inventory](skill-excluded-inventory.txt); their presence in source is not inclusion in the published plugin collection. No framework-specific experiment was installed.

Impeccable Windows x64 engine channel **0.1.15** (upstream `scripts/VERSION`) downloaded from official `engine-v0.1.15` release; SHA-256 **981324ea15cc3c107d46b8133b5be77f639dbcd22e671f1eb7d8c69136e9693b** matched its published sidecar. Installed at `.agents/skills/impeccable/scripts/bin/windows-x64/impeccable.exe`; direct `--version` reports **4.6.0**. Engine channel tag and product version are different identifiers, not a contradiction. No global binary/cache was overwritten. Unix/non-Windows binaries are not installed; the preserved launcher can provision the appropriate platform later.

MIT/Apache license copies retained as `.agents/skills/MATTPOCOCK-LICENSE.txt` and `IMPECCABLE-LICENSE.txt`, plus any upstream NOTICE. Installed-file hashes and comparison results are recorded in `skill-installation-manifest.json`. No native hooks, browser extension, runtime design context, PRODUCT.md or DESIGN.md initialized; those are not necessary for skill discovery in this research-only phase. Existing global and project duplicates remain visible rather than silently removed. On the next turn these skills should be available; refresh/restart the host if discovery has not updated.

Configuration approval: the user answered **Apply the draft configuration (Recommended)** on 2026-10-16. Applied the [approved draft](skill-configuration-draft.md) as [AGENTS.md](../AGENTS.md), [issue tracker](../docs/agents/issue-tracker.md), [triage labels](../docs/agents/triage-labels.md) and [domain conventions](../docs/agents/domain.md). Context7 instructions were preserved. No tickets, remote labels, glossary, ADRs or app files created. This satisfies the upstream setup skill's draft-review checkpoint; it does not approve the proposed validation or application phase.

The following turn's host skill catalogue now resolves installed model-invoked skill entries to this project's `.agents/skills`, confirming project discovery in Codex. Explicit-only selector invocation and Antigravity runtime behavior were not exercised. Existing global skills remain preserved.
