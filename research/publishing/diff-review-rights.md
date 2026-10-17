# Complete staged rights/provenance diff review

Reviewed 2026-10-17 against **Git index bytes**, using `git show :path` for every assigned file. **Final result: PASS for this assigned scope.** Findings: **1 material attribution finding found and resolved in the index; 0 unresolved blocking findings; 0 additional actionable rights/portability findings.** No commit, push, skill command or application feature was executed by this reviewer.

## Exact coverage and method

Assigned and read: **105 files, 422,928 staged bytes**: 82 `.agents/**` files (79 Matt payload files and 3 license/notice records), 16 top-level `research/*.*` files and 7 `research/repositories/**` reports. The complete per-file coverage/hash inventory is below. All are staged additions. Later staging changes require checking affected files again.

Reviewed reports as their actual staged text, including historical governance framing, source/license distinctions, exact inspected repository revisions, limits and publication qualifiers. For every vendored skill blob, read the staged bytes, inspected metadata/rights/attribution/reference content and checked identity against the pinned installation manifest; do not interpret this rights review as a functional execution of every workflow. Templates and command examples remained inert data. Parsed all assigned JSON and checked staged path/text portability. The final two research-index/skills-record EOF-only trims were reread before this report.

Assigned-scope fingerprint: `0301caeda5c2c6fa5466fc92f5eb7e7b9158412c28047adeef352f2c0b299aa7`. Definition: SHA256 of sorted assigned-path records `path + NUL + staged-file-SHA256 + LF`. This is a precise scope identifier, not a commit SHA.

Additionally read/verified the three staged resolution files: `THIRD_PARTY_NOTICES.md`, `docs/third-party/HUMANLAYER-SHOW-ME-LICENSE.txt`, and `docs/third-party/humanlayer-show-me-provenance.md`. They do not change any vendored Matt payload bytes.

## Findings and resolution

**R1 — Missing complete attribution grant for copied PR visual guidance, resolved.** The staged `pr/CREDITS.md` expressly identifies copied HumanLayer/Dex Horthy show-me material. Its broad older link points at `humanlayer/humanlayer`, whose root has Apache terms; stronger precise `pr/SKILL.md` metadata names `humanlayer/skills/plugins/show-me/skills/show-me/SKILL.md`. Targeted verification resolved the actual named source to official `humanlayer/skills` revision `653b6411c1f70c275a18e37673b042ff99f67ceb`. That source is under an explicit MIT grant, copyright 2026 HumanLayer, rather than the older repository's Apache license.

The complete official recursive Git tree was not truncated and has no other LICENSE/COPYING/NOTICE in the named source ancestry/subtree. The show-me source and copied menu/examples correspond. [Pinned source and exact license evidence](../../docs/third-party/humanlayer-show-me-provenance.md) record both the conflict and its resolution; the original historical copied revision remains unknown rather than invented. The index now retains the complete HumanLayer MIT copyright/grant (1067 bytes; SHA256 `5f13c18ea00ea5c1384f41745feeca774079164f7f59a92e4ac0899ad217b26f`), original unchanged Matt credits, Matt's MIT license and a root third-party notice. **Resolved; no exclusion of the PR payload is required for this identified issue.**

## Checks that passed

- **All 79 Matt payload files match their manifest SHA256 exactly**, without even needing CRLF normalization. They cover the complete 27 published entries at pinned Matt revision `49dd158d1076134a641b33efb035946536778336`; no unexpected vendored payload and no missing published file. The MIT grant/copyright is retained. This verifies staged identity against the prior pinned inspection record; it does not claim a fresh complete upstream history audit.
- All 27 `agents/openai.yaml` files and skill frontmatter remain unchanged. Explicit-only invocation policies were not dropped or merged; provider-specific command syntax remains an upstream compatibility limitation, already qualified in the skill record. No vendor instruction was invoked merely by reading it.
- **No `.agents/skills/impeccable/` payload is staged.** Only its Apache license and NOTICE are staged as provenance records. The record clearly distinguishes preserved complete local installation from excluded Git payload and links restore notes. No executable or bundled browser dependency is silently redistributed under a top-level license assumption.
- Seven repository reports are independent analytical prose, not upstream application source/archives. Unlicensed/ambiguous candidates remain reference-only; MIT candidates do not receive blanket dependency/model/fixture clearance. Versions/activity/test presence are qualified, including tests read versus executed and conflicting upstream coverage claims.
- Top-level research records retain facts versus inferences/unknowns, historical phase authorization context, source SHAs and current-index pointers. Historical Next/cloud/one-editor alternatives do not silently override later selected constraints. The current index records SettleTable naming while preserving historical synthetic labels and the technical module namespace.
- Manifest destinations are project-relative. All assigned files are UTF-8 text; no NUL/binary payload, Windows-reserved pathname or case-colliding pathname was found. No absolute user/workspace path or private Notion locator was flagged in assigned bytes. Historical Windows separators in the excluded-source inventory describe source paths, not a promised executable cross-platform installation command.
- Raw OCR images/models/receipt transcriptions are not part of this assigned staged set. The index's publication note explicitly explains local raw inputs, historical hashes and reduced public reproducibility. Deliberately local evidence is a documented publication boundary, not a claim that the benchmark feature is missing from the project objective.

## Limits and responsibility

This scope excludes phase-specific experiment/implementation/publishing documents assigned to other reviewers. It is not a complete secret scan, legal opinion, dependency SBOM, implementation review or remote checkpoint verification. The orchestrator must integrate all reviewers, inspect final staging and verify remote refs separately. No project-wide open-source license is inferred from the third-party grants. This report itself contains no credentials, private destinations or account identifiers.

## Per-file staged coverage

Each row means the actual staged blob was read and included in this scope. Hashes identify those reviewed bytes, not a working-tree substitute.

| Staged path | Bytes | SHA256 |
|---|---:|---|
| `.agents/skills/IMPECCABLE-LICENSE.txt` | 10766 | `02bb8c3b4e70190e3986c0404ad2fd8d639b4f534252d82379cc1b502b6d1812` |
| `.agents/skills/IMPECCABLE-NOTICE.md` | 503 | `c60a093c2845fd9fb82f9c6f742ece31f379f8190b535309d32d66c45ccffdcb` |
| `.agents/skills/MATTPOCOCK-LICENSE.txt` | 1068 | `0e7ac423bf2c6e223b7c5b156f8cf72da49d748e56a1641402c31f22ad07dbb5` |
| `.agents/skills/ask-matt/PHASE-BOUNDARIES.md` | 4249 | `a8aa20158609ef39e2b308b6ba0660c91066838d07a867202e63a7744a88a3ed` |
| `.agents/skills/ask-matt/SKILL.md` | 12594 | `1371f5ce005de0992a44b137748bfb960a56948aa9871b405fe9d90b24332e3c` |
| `.agents/skills/ask-matt/agents/openai.yaml` | 137 | `bdffbc5a0a99ed1b6ef3253d251d755fd18162b9845972e380007f844b09b05c` |
| `.agents/skills/code-review/SKILL.md` | 6670 | `09eb147f793e4647949edd32dbad278f0554dfb56e0d46b699cd4c2c55bf0357` |
| `.agents/skills/code-review/agents/openai.yaml` | 100 | `8229ca854e11dc8e6aef2131ee03f31fb1561cf905fab9ccc325180cf3331352` |
| `.agents/skills/codebase-design/DEEPENING.md` | 2553 | `f3dd099ce99289bd213914d8ee3e2429b78309c3957ca4583f7659551b1d53c1` |
| `.agents/skills/codebase-design/DESIGN-IT-TWICE.md` | 2665 | `52b52e75655a27aea59c6966b410bac82448968ad46ef1ebb9f07c274e3ae010` |
| `.agents/skills/codebase-design/SKILL.md` | 6446 | `2c20617f87ec8af6a434859f381b2f061a69b530444e74eb39e78bb016a6d1e2` |
| `.agents/skills/codebase-design/agents/openai.yaml` | 102 | `edebc9e4fcfe102114012575eaa9600b9b5fd08c311664f389c36e7bc717740f` |
| `.agents/skills/diagnosing-bugs/SKILL.md` | 8664 | `849198df88cdb65fd0d97236604c1fca7ff2f22d2f705f9724a800d0266b118d` |
| `.agents/skills/diagnosing-bugs/agents/openai.yaml` | 103 | `3e430dbe4334a87597488c060cb3dc3786bb00c9182877d6f5ec41f62490e90b` |
| `.agents/skills/diagnosing-bugs/scripts/hitl-loop.template.sh` | 1316 | `35103539fc36873eea36074769ad454f9379d6fc8b2dc0e26ce987fd3bfe5503` |
| `.agents/skills/domain-modeling/ADR-FORMAT.md` | 2733 | `944c92aa790e8fbdc9199640b170979abb8a34ba8d0fe18c2a01a63bce140ca0` |
| `.agents/skills/domain-modeling/GLOSSARY-FORMAT.md` | 2300 | `21dcc40cdec8e151a829b98ab1517c1867bc444e3665134a98c6983411996801` |
| `.agents/skills/domain-modeling/SKILL.md` | 3346 | `7b925d7b1e341a2eeae33ad68a8a8c0ab889a38ddd22a7598e4c240e5a7556a3` |
| `.agents/skills/domain-modeling/agents/openai.yaml` | 101 | `f6bf2aa996c6e6f53fdd0708e18a0d16a56aed8322cca59fedbe3c0d2c75f06b` |
| `.agents/skills/grill-me/SKILL.md` | 157 | `caaf8b8de1684f96e26b28f3c29189db5c89cce4b73e1c93d86164f66ef88637` |
| `.agents/skills/grill-me/agents/openai.yaml` | 137 | `c061e39c3e0f9d865fb1b97556d485704af2a8a58f4b8221a8917a5c2074a32b` |
| `.agents/skills/grill-with-docs/SKILL.md` | 247 | `7de372c13488f1ee96cc11cd8907b56b6809cc93eef776eeddd37de6b6cbe3fe` |
| `.agents/skills/grill-with-docs/agents/openai.yaml` | 145 | `94cd0ab161fb468a836349f5ed482ba58ce8e709a05c57ce533d739dbd35cca9` |
| `.agents/skills/grilling/SKILL.md` | 2049 | `befdff1e27a1dfe2a294d5871169ac1afe16d983911daa4f32627514a48c1e15` |
| `.agents/skills/grilling/agents/openai.yaml` | 113 | `1411d7df7d99b7e621a1ff8283c8133cc2464be63d064e52d8ce169c6800ee9b` |
| `.agents/skills/handoff/SKILL.md` | 940 | `4cbb043950dad2ffd3662ff1a5a0b51ae676004b5cae10e3787e8ee7a4ee69d3` |
| `.agents/skills/handoff/agents/openai.yaml` | 141 | `5c479fd562c691851690e8b18c8501045bef0943c10743d636b2fae26add1d28` |
| `.agents/skills/implement-spec/SKILL.md` | 2780 | `7a22dd2e60b8fcece478ced9d2533582adf3520d695acd3ab715341535c9e56d` |
| `.agents/skills/implement-spec/agents/openai.yaml` | 168 | `fd41efb42c60c96320d6531be7e4bf15cbf5518cd652d57dff27ccffa46988e9` |
| `.agents/skills/implement/SKILL.md` | 622 | `483bdc4ccf4ac31d86ac7beeaa0d0db80313e71e120bb8c59b3196ae5decd53d` |
| `.agents/skills/implement/agents/openai.yaml` | 139 | `8970a8596ade0c28ab427f41a4ea242d6bdf6186c59ebf55e1238dbecaab79dc` |
| `.agents/skills/improve-codebase-architecture/HTML-REPORT.md` | 6641 | `581e8bb5a521e46bbda8ca7e19b15948bed882187108092ebb90c62513b77528` |
| `.agents/skills/improve-codebase-architecture/SKILL.md` | 6000 | `552240a5ab5cec6b67c15dd1ad6e9f6962b1bca6ce870059a8c2713760c20392` |
| `.agents/skills/improve-codebase-architecture/agents/openai.yaml` | 166 | `c8cb20f68ebf0edb4e497bc11ae5fcaa196004e661cd189015b04f4109ced7f1` |
| `.agents/skills/pr/CREDITS.md` | 604 | `a7a087127665d7298a72280ef6e19c41ad8404523712a788c8dc3ab414bc2497` |
| `.agents/skills/pr/SKILL.md` | 4169 | `ab63f1cf78647389edcd386c9427c5dfca27ed2836930c24773ffee834c19bcd` |
| `.agents/skills/pr/agents/openai.yaml` | 93 | `2295b586624db4ef546f3fd4695492f039d941a46d8a1593a702ce3ca511b8ad` |
| `.agents/skills/prototype/LOGIC.md` | 6036 | `f61c7d249e786a79ef289018901c348271e1798dd0b0bc5607b5c6f4d4a01ab9` |
| `.agents/skills/prototype/SKILL.md` | 2931 | `714de632d116bb73f65cdb5a882db15b9369a6713b9a47c0fad827848f0bfbe3` |
| `.agents/skills/prototype/UI.md` | 6913 | `723211e878acbc7b6ff09755263f3295cde724ba902ff0064da41eed51d45ad3` |
| `.agents/skills/prototype/agents/openai.yaml` | 100 | `5af65e43ab41a350436697b81e27b7f848d36782043b73c322bb2c9fa9cc55dc` |
| `.agents/skills/research/SKILL.md` | 794 | `985569f15739c713d6784887c3d186d4ef9ac85bec5ad9c068d25bf0739928e4` |
| `.agents/skills/research/agents/openai.yaml` | 94 | `9b4c470d63221c1f68f22df70b83e2f12401b317babe0d1b7b5f24a974474d0d` |
| `.agents/skills/retro/SKILL.md` | 4369 | `33fbc28568e3146f20fd908b12998bc0ab30aa4f4c87288199a40793efa94696` |
| `.agents/skills/retro/agents/openai.yaml` | 146 | `cb6fb9d7e6b4be5975f41f6def1dd00a1255bad5d9b02696b124c924a8b8745c` |
| `.agents/skills/setup-matt-pocock-skills/SKILL.md` | 6978 | `f148858ffb7f63c03c06fca06e6fdb1d91a35c6b293244b8fdfacd5f4cc028c4` |
| `.agents/skills/setup-matt-pocock-skills/agents/openai.yaml` | 152 | `9527de0110541c45712319025155aeab8dc7d77c6ed6e5e83271bab1851ab939` |
| `.agents/skills/setup-matt-pocock-skills/domain.md` | 2042 | `593a7042218689f1d24df89df14eaf0a20e19e0d0a7d479a01947ac78f0784b9` |
| `.agents/skills/setup-matt-pocock-skills/issue-tracker-github.md` | 4117 | `f0653fe106dd8ee7b33be27bd7fe3104b40555896cb45f61997aed20467020c3` |
| `.agents/skills/setup-matt-pocock-skills/issue-tracker-gitlab.md` | 3816 | `591a9e7057382aaccdfbed3f7ea3f2ad07e0cd29f012d18b82ee4e485fd81e24` |
| `.agents/skills/setup-matt-pocock-skills/issue-tracker-local.md` | 1810 | `7dcda20a2eb4bdc89b95d1143423c0691309921cadae3132e6424f371030506e` |
| `.agents/skills/setup-matt-pocock-skills/triage-labels.md` | 1057 | `ae512af838c78b8750471c42cd2b20fa32319553e61d84c9a23d171b40ce14aa` |
| `.agents/skills/tdd/SKILL.md` | 3629 | `5505d25bbaa8fc14a79e4d20163936958992a2995b7f1dd1d6197edc9ed722e0` |
| `.agents/skills/tdd/agents/openai.yaml` | 87 | `ea6f01cf1b8c06a4b0f5b649d74b1b8ce8685e72af1b38d70d877693e092af0b` |
| `.agents/skills/tdd/mocking.md` | 1481 | `3ceb807fdf4a47d6a93d4d9a891e5ba6d362a6247bd08adc451feebfc17361ef` |
| `.agents/skills/tdd/tests.md` | 2214 | `859f9e592c188fda4fc7277dd180e4ce9c7a2e13f6efe1f6f29eccc9d28c106a` |
| `.agents/skills/teach/GLOSSARY-FORMAT.md` | 2122 | `9b99859ec28437668130d8f2ce5a342938970f8a1ed4fd38c3eab4f4b5fff210` |
| `.agents/skills/teach/LEARNING-RECORD-FORMAT.md` | 2747 | `701fa34b6748aa89e6c960ffb815257f481a7d77fb2900f9028f7edf3fdd6052` |
| `.agents/skills/teach/MISSION-FORMAT.md` | 1540 | `8cacbb3c0644d3ae0ea4965564797099401a6930a23f7cf462918576587f2418` |
| `.agents/skills/teach/RESOURCES-FORMAT.md` | 1924 | `e9cacf34026e11a8d1c8f9de88abe5bcbf654f4ebdb25cae8c0de0d5f48f44ec` |
| `.agents/skills/teach/SKILL.md` | 9733 | `550482c2d674b085c9043b87bfdc14a8f2ec453c736119e7fcbb1e9332bffeba` |
| `.agents/skills/teach/agents/openai.yaml` | 139 | `5856f3ae8aec742f1499c640aecdd5f1d6af5fa210a7c6ec794de8263a6f733f` |
| `.agents/skills/to-questionnaire/SKILL.md` | 2904 | `b5eb929842ee0e93d867c5e906d183d350f2f2d149eaeaa86967d94d8eda1d3b` |
| `.agents/skills/to-questionnaire/agents/openai.yaml` | 166 | `9e8a06c38c8842eea8d4922cb9d1ead8e3ace647bab259b943c994a1b4742bc2` |
| `.agents/skills/to-spec/SKILL.md` | 3043 | `43ad9cf318e5e7d3d1fa360253a37021796dc87a0c2e595ad262661a10f85088` |
| `.agents/skills/to-spec/agents/openai.yaml` | 135 | `1c5b4d1e3d8e52287ef19cc2742fdbbfae1914ac75d33af3e4c8174f08cc55bb` |
| `.agents/skills/to-tickets/SKILL.md` | 5812 | `56ec23c5b2782785d4e65bff9e315b6d3aeb4ef977c174a219e99489fada1995` |
| `.agents/skills/to-tickets/agents/openai.yaml` | 146 | `21bc6215fffcd7614e9f772bb1760e87cc5fc7dcc707e7d282bc9414267a6090` |
| `.agents/skills/triage/AGENT-BRIEF.md` | 7942 | `7f5f87fed3033df1b06e083c480f3e847b1fbb0647746b8a4c6a50f9f26ef44f` |
| `.agents/skills/triage/OUT-OF-SCOPE.md` | 4667 | `1fbf9b432130c6380aa65813b55553cfda150309b27c595e183f8e335b8a190d` |
| `.agents/skills/triage/SKILL.md` | 6558 | `917b0baf74be583e74f110857ed45df2766617f75c00baf61fd136d7af515edf` |
| `.agents/skills/triage/agents/openai.yaml` | 135 | `2e683717720cf456d165d0bb1a68bb600d0b6a8ccb61841c172e50d26f95351c` |
| `.agents/skills/wait-what/SKILL.md` | 396 | `d961bb37defd975c539427edb8f450cdbccdcdd552e213c1ece46676a7970905` |
| `.agents/skills/wait-what/agents/openai.yaml` | 158 | `b41faadf741d51e4ea184148b2d1854d93f947aaf754c7844f70a00f04194999` |
| `.agents/skills/wayfinder/SKILL.md` | 12380 | `9be7b478c389605a24517d27752f278933588da97a1b5921b165f455edf4c5b7` |
| `.agents/skills/wayfinder/agents/openai.yaml` | 144 | `88bc81a11a6d52ac67aeaa76b8b619e387020d47c5133a4dd4927fd15c4ad073` |
| `.agents/skills/wizard/SKILL.md` | 4123 | `bdf31d48211ea559878f95a4f344aeabf8d85897488ba564382bab0b000daac1` |
| `.agents/skills/wizard/agents/openai.yaml` | 96 | `98f44d682d58e262f160dc59a8befc365e0aa65820dd0261864af26aa8e59d83` |
| `.agents/skills/wizard/template.sh` | 9498 | `6566f147299bc6f1d941e64591ed04385416d543e11f96f564c7228f5018d0ed` |
| `.agents/skills/writing-for-agents/SKILL-MECHANICS.md` | 2629 | `c768e6307c7c10728c401c213f2c4ba71c542127eeb7ad2956aabd15a0fa0059` |
| `.agents/skills/writing-for-agents/SKILL.md` | 10886 | `551adca942227b44192edba88acd4e8db911f0121ce58ad16944ccf6a896a74a` |
| `.agents/skills/writing-for-agents/agents/openai.yaml` | 102 | `eacb24b2a618cfb81dacb0416f4fdd75ddf3a8060f8ddb99aae1b1e301907e4b` |
| `research/README.md` | 8070 | `343b10ec54a8684ab8e1c4afa2d26b59069ee7cc7402dc29ed1d0222104d9159` |
| `research/additional-candidates.md` | 1301 | `71fad7e36f10b2b3642a460a1fab2c02e3dd02e784d2ac4d4ea6ccea9e916a95` |
| `research/agent-skills.md` | 9820 | `1d973b86e0c98e3073c738ac8c255c145539d516657abaeb5fac6c2fdada5fc0` |
| `research/costs-and-risks.md` | 7344 | `31f8a7aac2cd2a303cd608e712fca57373499959074b51c1210c79f7c8680f1f` |
| `research/domain-model.md` | 13489 | `fb57746bdb3e8e3cfb527282170834d505793249caa49097b9f28a6caca27874` |
| `research/final-recommendation.md` | 9305 | `e6a8523d6e362166c2ecd5f3b8a43a375e80736cec7b51fe6a744807a3515512` |
| `research/licensing-and-reuse.md` | 4477 | `7d34b7046bf16bfb564e4e113ed151b73a210f06041285f65040e5d3a5dadde6` |
| `research/notion-architecture.md` | 9913 | `6bd1c1ab9b70882fe58bca7b5f8164d3a70f08afc077395c2fa1d8465cf5ae5c` |
| `research/ocr-evaluation.md` | 16046 | `366b5cc21055b118dfdb382a98bdb66d02f2c33a5abd3acdd0d9cb62f620343c` |
| `research/repositories/ai-bill-splitter.md` | 8669 | `b46cefa86c7b60f4fa1f9ee5a58fdc919789b684809e1d74f9af9ff80f8e20a8` |
| `research/repositories/billsplit.md` | 8074 | `acda4c141c9e2b68cffd91b8a80767595de4812acc34667ab7976fce99964456` |
| `research/repositories/malaysian-receipt-splitter.md` | 6985 | `df7cac6c282b012b19655ddcebbb3c81f3137f4b65ab601b26f1e8e9c5ff1156` |
| `research/repositories/notion-expense-automation.md` | 11083 | `01ed7a27cfe93659f6e26f1da5ce5d886050ce5afd85f5af3c1113bc2b382eee` |
| `research/repositories/receiptiq.md` | 8499 | `46776976cd6b1dbad1ae37c97a04f5bc52768263575be8d096c0da4521bc3f7d` |
| `research/repositories/spliit.md` | 10682 | `79633ad38fad2ef000b96464e9f5d87fd8311968207cb2dcd71ecd8806b796ac` |
| `research/repositories/split-pro.md` | 11624 | `ce9d24c8cd7380aefa3c858cfe63618f100e2ec98428ff3ff44ab040bec06a92` |
| `research/repository-comparison.md` | 4016 | `fdaf59420b0a5e19664be28dafb50780280aa410f1d257d7936bbcf4beba98fd` |
| `research/skill-configuration-draft.md` | 3985 | `e1d9cf3e6344a6094828f5d8ac841dfecde1ed57bddde58f56848bc4eba90366` |
| `research/skill-discovery.json` | 4329 | `4ac99319bd1d6e6217a9b3e0ba49117bf69133aead3fd74b028601d1060ef36a` |
| `research/skill-excluded-inventory.txt` | 469 | `7a8b18ea21865f9dd68f4611da9a4fcca9cfbe947334158686ad131fd5cee7a5` |
| `research/skill-installation-manifest.json` | 22422 | `2f11700a220cff4f602a1a26da11b19d36d8c210a29c91a6f458d005660bccd7` |
| `research/technology-options.md` | 7099 | `2cbae984c18520a332c72c1831cc2d2a582903e057e04967dca0d1c0c5389baf` |
| `research/verification.md` | 4609 | `128a0a0afe9fa05aac544aa1ba580ac88a9600161cb6b4b60cae488e0e69b8aa` |
