# llm-wiki — Usage Guide

A complete, example-driven guide to running a lab knowledge wiki with `llm-wiki`.
Every command, every status transition, every entry point (CLI, agent CLI, MCP), with real
terminal output.

For a short overview see [README.md](README.md). This document is the long form.

---

## Table of contents

1. [The mental model](#1-the-mental-model)
2. [Install once per machine](#2-install-once-per-machine)
3. [Choose your LLM](#3-choose-your-llm)
4. [Create a project](#4-create-a-project)
5. [Add source material — `ingest`](#5-add-source-material--ingest)
6. [Compile the wiki — `compile`](#6-compile-the-wiki--compile)
7. [The document lifecycle: draft → reviewed → approved](#7-the-document-lifecycle-draft--reviewed--approved)
8. [Proposals and `review apply`](#8-proposals-and-review-apply)
9. [Ask questions — `ask`](#9-ask-questions--ask)
10. [Search — `search` / `reindex`](#10-search--search--reindex)
11. [Comments](#11-comments)
12. [Edit requests from an assistant](#12-edit-requests-from-an-assistant)
13. [Quality audit — `audit`](#13-quality-audit--audit)
14. [Undo: `diff`, `rollback`, backups](#14-undo-diff-rollback-backups)
15. [Notifications — `notify`](#15-notifications--notify)
16. [Working with agent CLIs](#16-working-with-agent-clis)
17. [Working through MCP](#17-working-through-mcp)
18. [Output language (English / Korean)](#18-output-language-english--korean)
19. [A complete worked example](#19-a-complete-worked-example)
20. [Command reference](#20-command-reference)
21. [Configuration reference](#21-configuration-reference)
22. [Troubleshooting](#22-troubleshooting)
23. [Not implemented yet](#23-not-implemented-yet)

---

## 1. The mental model

Three sentences govern everything:

> **Humans own the source material. The AI compiles from evidence. Humans approve anything
> official.**

Concretely:

| Folder | Who writes it | Notes |
|---|---|---|
| `10_Inbox/` | **You** (drop files in) | Everything enters here. `ingest` moves files out |
| `20_Sources/` | `ingest` only | The AI never modifies source material |
| `30_Wiki/` | **The AI** (`draft` only) + you | The compiled knowledge base |
| `30_Wiki/_Proposals/` | `compile` | Change proposals awaiting your approval |
| `40_Decisions/`, `50_Outputs/`, `90_Archive/` | You | The AI does not write here |
| `00_Project/` | You | Scope, glossary, members — read by the compiler as context |
| `.llm-wiki/` | The tool | Config, manifest, backups, index, logs, metrics |

Five rules are enforced **in code**, not by prompting:

1. The AI can only ever write `status: draft`.
2. Writes outside `30_Wiki/` are blocked.
3. A document at `reviewed` or higher cannot be edited by the AI — it is demoted to a proposal.
4. The `## Comments` section is preserved verbatim on every update and merge.
5. Every run takes a backup first, and `rollback` restores it.

If a prompt ever tells the model to break one of these, the code still stops it.

---

## 2. Install once per machine

Requirement: **Python 3.12+** and pipx. Nothing else — the search database is Python's
built-in SQLite, and snapshots use a built-in backup, so Git is not required.

```console
$ pipx install "git+https://github.com/pilwonhur/llm-wiki.git"
$ llm-wiki --version
llm-wiki 0.7.0
```

If your default `python3` is older than 3.12, point pipx at a newer one:

```console
$ pipx install --python /opt/homebrew/bin/python3.12 "git+https://github.com/pilwonhur/llm-wiki.git"
```

Updating later:

```console
$ pipx reinstall llm-wiki
```

You install **once per machine**, not once per project. Creating projects is `llm-wiki init`.

### Optional pieces

| Install | When you need it |
|---|---|
| `claude` CLI (Claude Code) | Anthropic subscription (OAuth) as the compile backend |
| `codex` CLI | OpenAI subscription (OAuth) as the compile backend |
| `agy` CLI (Antigravity) | Antigravity subscription (OAuth) as the compile backend |
| `pipx inject llm-wiki anthropic` (or `openai`, `google-genai`) | API-key backends |
| Ollama | Local models — sensitive projects, offline work |
| `pipx inject llm-wiki pypdf` | Reading PDFs through API-key/Ollama/Antigravity backends |

You need **exactly one** compile backend. Everything else in this guide (`ingest`, `search`,
`audit`, `status`, `diff`, `rollback`, `notify`, `serve-mcp`) works with no LLM at all.

---

## 3. Choose your LLM

### See what you have right now

```console
$ llm-wiki models show
현재 유효 설정 — 프로젝트(Project-Exo)
  compile   claude-opus-5              [Anthropic] oauth-anthropic
  audit     claude-haiku-4-5           [Anthropic] oauth-anthropic
  metadata  claude-opus-5              [Anthropic] oauth-anthropic  (compile 값 상속)
  local     qwen3:32b
  인증 순서   oauth, api_key, ollama

공급자별 사용 가능 경로
  Anthropic        OAuth ○ (claude CLI)   API key × (ANTHROPIC_API_KEY 미설정 · anthropic 미설치)
  OpenAI           OAuth ○ (codex CLI)    API key × (OPENAI_API_KEY · openai 미설치)
  Google Gemini    OAuth × (개인 구독 종료 — Antigravity(agy) 사용)   API key ○
  Antigravity (agy) OAuth ○ (agy CLI)     API key × (지원 안 함 (구독 CLI 전용))
  Ollama (로컬)      × 미실행
```

Read it as: for each role, which model, which provider, which call path will actually be used,
and what is blocking the paths that are unavailable.

### Set a model

```console
# Interactive — pick provider, then model, then where to save
$ llm-wiki models use

# Direct
$ llm-wiki models use gpt-5.6-sol

# Default for every project on this machine
$ llm-wiki models use gemini-3.6-flash-high --global

# Mix per role to save money: heavy model for compiling, light model for auditing
$ llm-wiki models use claude-opus-5   --role compile
$ llm-wiki models use claude-haiku-4-5 --role audit
```

Settings live in two layers and the project layer always wins:

| Layer | File | Purpose |
|---|---|---|
| Global | `~/.llm-wiki/config.yaml` | This machine's default. `init` offers it as the default for new projects |
| Project | `<project>/.llm-wiki/config.yaml` | This project's choice. Anything unset is inherited from global |

So "set it once and keep using it" is the global layer; "this one project is different" is the
project layer. Both are editable by hand — `models use` only rewrites the keys it touches and
leaves your comments intact.

### Providers and auth paths

| Provider | OAuth (subscription) | API key |
|---|---|---|
| Anthropic | `claude` CLI | `ANTHROPIC_API_KEY` + `anthropic` |
| OpenAI | `codex` CLI | `OPENAI_API_KEY` + `openai` |
| Antigravity | `agy` CLI | — (subscription only) |
| Google Gemini | — (individual subscription discontinued) | `GEMINI_API_KEY` or `GOOGLE_API_KEY` + `google-genai` |
| Ollama | — | local `localhost:11434` |

The **model name picks the provider**. The registry is checked first, then a prefix heuristic:

```console
$ llm-wiki models list
anthropic: claude-fable-5, claude-opus-5, claude-sonnet-5, claude-haiku-4-5
openai: gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna
gemini: gemini-3.6-flash, gemini-3.1-pro-preview
antigravity: gemini-3.6-flash-high, claude-sonnet-4-6, gpt-oss-120b-medium, ...
ollama: (없음)

# A new model was released — register it and every project can use it
$ llm-wiki models add openai gpt-5.7-nova

# Ambiguous name? Force the provider with a prefix
$ llm-wiki models use openai/my-finetuned-model
```

### Auth order and automatic switching

```console
$ llm-wiki models auth "oauth,api_key,ollama"     # the default
$ llm-wiki models auth "api_key,oauth"            # prefer API keys
```

Every usable path is bundled **in order**. If the first one fails at run time — expired login,
subscription tier problem, rate limit — it switches to the next automatically and says so:

```console
  · kim2026_gait.pdf 편찬 중...
    ! oauth-gemini 실패 → api-gemini 로 전환
```

### Sensitive projects

```yaml
# .llm-wiki/config.yaml
external_llm_allowed: false
model:
  fallback_local: qwen3:32b
```

This is enforced in code: whatever model is configured, the project uses **only Ollama**. There
is no flag or prompt that overrides it. `models show` says so plainly:

```console
  ! external_llm_allowed: false — 민감 프로젝트라 설정 모델과 무관하게 로컬(Ollama)만 사용합니다 (N7)
```

---

## 4. Create a project

A project is just a folder. Three ways to create one; all produce the same result.

### Way 1 — terminal (most common)

```console
$ mkdir Project-Exo && cd Project-Exo
$ llm-wiki init

프로젝트를 설정합니다. Enter로 기본값 사용.

  프로젝트 정식 명칭 [Project-Exo]: Adaptive exoskeleton control for hemiplegic gait
  한 줄 목적: Develop an adaptive controller for a gait-assist exoskeleton
  구성원 (쉼표 구분): Pilwon Hur, Jane Kim, Daehak Lee
  Wiki reviewer 실명: Jane Kim
  Wiki 출력 언어 (ko=한국어 / en=English) [ko]: en
  외부 LLM 전송 허용? (IRB·산학 등 민감 자료면 n) [y]: y

  등록된 모델 (공급자별 — 사용 가능한 인증 경로 표시):
    Anthropic        [OAuth] claude-fable-5, claude-opus-5, claude-sonnet-5, claude-haiku-4-5
    OpenAI           [OAuth] gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna
    Antigravity      [OAuth] gemini-3.6-flash-high, claude-sonnet-4-6, ...
  편찬 모델 [claude-fable-5]: claude-opus-5

✓ 구조 생성 완료 (46개 파일)
✓ .llm-wiki/config.yaml 생성 (스냅샷: 내장 백업, Git 사용 안 함)
✓ AGENTS.md·CLAUDE.md·workflows·스킬 어댑터 설치
```

Non-interactive (for scripts): `llm-wiki init --yes` uses defaults for everything.
You can also init a different folder: `llm-wiki init /path/to/Project-X`.

### Way 2 — ask an agent in plain language

Open Claude Code, Codex, or Antigravity in an empty folder and say *"set up a wiki project
here."* The agent runs the onboarding as a conversation and calls `llm-wiki init` under the hood.

### Way 3 — the global `/wiki-init` skill

```console
$ llm-wiki setup-agent claude      # or codex / agy / all — once per machine
```

Then `/wiki-init` works from any folder in that agent.

### What init creates

```
Project-Exo/
├── 00_Project/         README.md, scope.md, glossary.md, members.md   ← you fill these in
├── 10_Inbox/           Pilwon Hur/, Jane Kim/, Daehak Lee/            ← one folder per member
├── 20_Sources/         Papers/ Meeting-Notes/ Experiments/ Datasets/
│                       Web-Clips/ QA-Sessions/ Proposals/
├── 30_Wiki/            Concepts/ Methods/ Findings/ People/ Equipment/
│                       Questions/ _Proposals/
├── 40_Decisions/  50_Outputs/  90_Archive/
├── AGENTS.md           agent rules (single source of truth)
├── CLAUDE.md           one import line pointing at AGENTS.md
├── .claude/skills/     /wiki-ingest, /wiki-compile, /wiki-audit
├── .agents/skills/     the same, for Antigravity
└── .llm-wiki/
    ├── config.yaml     project settings
    ├── manifest.json   every registered source: hash, type, uploader, processed flag
    ├── templates/      wiki-doc.md (chosen by language) + wiki-doc.ko.md / .en.md
    ├── workflows/      ingest.md, compile.md, audit.md (agent fallbacks)
    ├── backups/  index/  metrics/  audit/
    └── processing-log.md
```

`init` is **idempotent**. Running it in a folder that already has files never touches them, and
re-running only fills in what is missing. That is the supported way to pick up new templates
after a `pipx reinstall`.

### Fill in `00_Project/`

Not required to start, but the compiler reads `scope.md` and `glossary.md` as context, so
filling them improves output quality a lot:

- `scope.md` — what is in and out of scope, research questions
- `glossary.md` — preferred term for each concept, so the AI stops creating
  "가변 강성 구동기" and "Variable Stiffness Actuator" as two documents
- `members.md` — the member table; `ingest` warns about uploaders not listed here

---

## 5. Add source material — `ingest`

### Drop files into your own folder

```console
$ cp ~/Downloads/kim2026_adaptive_gait.pdf  Project-Exo/10_Inbox/Jane\ Kim/
$ cp meeting_2026-08-12.md                  Project-Exo/10_Inbox/Jane\ Kim/
```

The subfolder name is the **uploader attribution**. Files dropped at the top of `10_Inbox/`
still get processed but are recorded as `unknown`.

### Run ingest

```console
$ llm-wiki ingest
  Jane Kim/kim2026_adaptive_gait.pdf
    분류 [paper] (paper/meeting/experiment/dataset/webclip/qa/proposal, h=보류): ⏎
  Jane Kim/meeting_2026-08-12.md
    분류 [meeting] (paper/meeting/experiment/dataset/webclip/qa/proposal, h=보류): ⏎

✓ 등록 2 / 중복 0 / 보류 0
  - Jane Kim/kim2026_adaptive_gait.pdf → 20_Sources/Papers/kim2026_adaptive_gait.pdf (paper, Jane Kim)
  - Jane Kim/meeting_2026-08-12.md → 20_Sources/Meeting-Notes/meeting_2026-08-12.md (meeting, Jane Kim)
다음: `llm-wiki compile` 로 편찬하세요.
```

`--yes` accepts every guess without asking — that is what nightly batches use.

### What ingest does, in order

1. **Scan** `10_Inbox/` recursively (skipping `.gitkeep`, `.DS_Store`, dotfiles).
2. **Hash** each file (SHA-256) and check it against the manifest — a duplicate is reported and
   left in place, never registered twice.
3. **Guess a type** from the filename, then ask you (unless `--yes`).
4. **Normalize the filename**, stripping characters that break Obsidian wikilinks (`[ ] # ^ |`).
   The original name is preserved in the manifest as `original_name`.
5. **Move** the file into the matching `20_Sources/` subfolder.
6. **Register** it in `.llm-wiki/manifest.json` with `processed: false`.

### Types and destinations

| Type | Destination | Filename keywords that trigger the guess |
|---|---|---|
| `paper` | `20_Sources/Papers/` | (default) |
| `meeting` | `20_Sources/Meeting-Notes/` | 회의, meeting, minutes |
| `experiment` | `20_Sources/Experiments/` | 실험, experiment |
| `dataset` | `20_Sources/Datasets/` | dataset, 데이터셋 |
| `webclip` | `20_Sources/Web-Clips/` | `.html`, `.url`, "clip" |
| `proposal` | `20_Sources/Proposals/` | 계획서, proposal, 제안서, 별첨 |
| `qa` | `20_Sources/QA-Sessions/` | (set automatically for `_qa/` submissions) |

### Edge cases you will hit

| Situation | What happens |
|---|---|
| Same file added twice | Reported as duplicate by hash, left in the Inbox, not registered |
| A different file with a name already in `20_Sources/` | Held (never overwritten) — rename and re-run |
| You press `h` at the prompt | Held in the Inbox for later |
| Uploader folder not in `members.md` | Warning logged, registration proceeds |
| Filename has `[`, `]`, `#`, `^`, `|` | Normalized; original recorded in the manifest |
| Files in `10_Inbox/_qa/` | Registered as `qa`, attributed to the **asker named inside the file**, not the folder |
| Files in `10_Inbox/_requests/` | **Skipped** — these are edit requests, not source material (see §12) |

---

## 6. Compile the wiki — `compile`

```console
$ llm-wiki compile
✓ 백업 20260812-093015 | 백엔드 oauth-anthropic/claude-opus-5 | 대상 2건
  · kim2026_adaptive_gait.pdf 편찬 중...
  · meeting_2026-08-12.md 편찬 중...

✓ 편찬 완료 — 산출 5건, 실패 0건, 토큰 in 48213 / out 9871 / $0.4820
  - 생성: 30_Wiki/Concepts/Adaptive Impedance Control.md
  - 생성: 30_Wiki/Methods/Gait Phase Estimation.md
  - 생성: 30_Wiki/Findings/Ankle Stiffness 12 Nm-rad.md
  - 갱신: 30_Wiki/Concepts/Series Elastic Actuator.md
  - 제안: 30_Wiki/_Proposals/Ankle Stiffness 12 Nm-rad-20260812-093015.md
검토: `llm-wiki review` / 변경 확인: `llm-wiki diff 20260812-093015` / 복원: `llm-wiki rollback 20260812-093015`
```

### What compile does

1. Takes a **backup** of `30_Wiki/` (keeps the last 10 by default).
2. Processes unprocessed sources **one at a time**, in order. A failure on one file is isolated
   and reported; the rest continue.
3. For each source it builds a prompt containing the project context (`scope.md`, `glossary.md`),
   the current wiki index (to prevent duplicates), the source metadata, the document template,
   and either the source text or its path (agentic backends read the file themselves).
4. The model returns a JSON array of documents. **The code then validates and writes** —
   the model never touches the filesystem.
5. Marks the source `processed: true` in the manifest **after each file**, so an interrupted run
   resumes where it stopped.
6. Converts any pending edit requests into proposals (§12).
7. Records tokens and cost in `.llm-wiki/metrics/costs.jsonl`.

### What the code enforces on the model's output

| Model asks for | Code does |
|---|---|
| write outside `30_Wiki/` | **Blocked**, reported as `차단: 30_Wiki 밖 쓰기 시도` |
| `status: reviewed` | Rewritten to `draft` |
| update a `reviewed`/`approved` document | Demoted to a proposal in `_Proposals/` |
| replace a document that has comments | Existing `## Comments` section restored verbatim |

### Output document shape

```markdown
---
type: concept
project: "Adaptive exoskeleton control for hemiplegic gait"
status: draft
created: 2026-08-12
updated: 2026-08-12
reviewer:
aliases: [Adaptive impedance control, AIC]
sources: ["20_Sources/Papers/kim2026_adaptive_gait.pdf"]
generated_by: llm-wiki phase0
---

# Adaptive Impedance Control

## Summary
...

## Relevance to this project
...

## Sources
- [[20_Sources/Papers/kim2026_adaptive_gait.pdf#page=5]] — gist of the claim
- [[20_Sources/Meeting-Notes/meeting_2026-08-12.md#Decisions]] — gist

## Conflicting evidence
## Open questions
## Related documents
## Comments
```

Two conventions matter:

- **Page numbers are physical PDF pages** (what `#page=N` opens in a viewer), never the printed
  page number — printed numbers drift because of covers and front matter.
- Statements the model could not ground in a source get a callout:

  ```markdown
  > [!warning] Evidence needed
  > No direct evidence was found in the current material.
  ```

### Nothing to do?

```console
$ llm-wiki compile
처리할 자료가 없습니다 (manifest 전부 processed, 대기 중인 편찬 요청도 없음).
```

To re-compile a source, set its `processed` back to `false` in `.llm-wiki/manifest.json`.

---

## 7. The document lifecycle: draft → reviewed → approved

This is the core of the system, so read this section carefully.

```
        (compile)              (you)                    (you)
 source ────────▶ draft ──────────────▶ reviewed ──────────────▶ approved
                    │                       │
                    │                       ├──▶ disputed    (evidence conflicts)
                    └───────────────────────┴──▶ deprecated  (superseded)
```

| Status | Meaning | Who can set it |
|---|---|---|
| `draft` | Written by the AI. Unverified. | The AI (and only this one) |
| `reviewed` | A human checked every citation against the original. Accurate. | **Human only** |
| `approved` | Established lab knowledge. Quotable in papers and proposals. | **Human only** |
| `disputed` | Sources conflict; the question is open. | **Human only** |
| `deprecated` | Superseded, kept for history. | **Human only** |

### How to promote a document

There is **no CLI command for this, by design** — promotion is a human judgment, so it is a
human edit. Open the document in any editor (Obsidian is convenient) and change the
frontmatter:

```diff
 ---
 type: concept
 project: "Adaptive exoskeleton control for hemiplegic gait"
-status: draft
-reviewer:
+status: reviewed
+reviewer: Jane Kim
 created: 2026-08-12
-updated: 2026-08-12
+updated: 2026-08-13
 ---
```

That is the entire mechanism. The moment `status` is above `draft`, the code stops the AI from
editing that document directly — the next `compile` that wants to change it produces a proposal
instead.

### What "reviewing" actually means

Before you type `reviewed`, do this for each document:

1. Open every link in `## Sources`.
2. For a PDF citation `[[...pdf#page=5]]`, open page 5 and confirm the claim is really there.
3. Check that background knowledge is marked as such and not mixed into sourced statements.
4. Check the `> [!warning] Evidence needed` callouts — either find the evidence or leave the
   callout in place.

The `audit` command mechanically checks link targets and page ranges (§13), but it cannot check
whether page 5 actually says what the document claims. That part is yours.

### Finding what needs review

```console
$ llm-wiki review
검토 대기 draft 3건 (오래된 순):
  - Concepts/Adaptive Impedance Control.md (생성 2026-08-12)
  - Methods/Gait Phase Estimation.md (생성 2026-08-12)
  - Findings/Ankle Stiffness 12 Nm-rad.md (생성 2026-08-12)
변경 제안 1건 (30_Wiki/_Proposals/):
  - Ankle Stiffness 12 Nm-rad-20260812-093015.md
  → 승인: 제안 내용을 원문서에 반영 후 제안 파일 삭제 / 거부: 사유 남기고 삭제

검토 방법: 문서의 근거 링크를 원문과 대조 → frontmatter status를 reviewed로 편집
```

### Promoting reviewed → approved

Same edit, `status: approved`. Use it when the lab treats the content as settled — typically
after a group discussion, not by one person's reading. `approved` documents rank first in
search and in `ask`.

### disputed and deprecated

When two sources genuinely conflict, do **not** pick a winner silently. The compiler is
instructed to record both sides under `## Conflicting evidence`; you then set
`status: disputed` so the open question is visible. When a document is superseded, set
`deprecated` rather than deleting — the history stays useful.

---

## 8. Proposals and `review apply`

### Where proposals come from

Three sources, all landing in `30_Wiki/_Proposals/`:

1. **compile wanted to update a protected document** — the target is `reviewed` or higher, so
   the update was demoted automatically.
2. **compile decided it could not safely rewrite** — the model chose `propose` because it was
   unsure of the existing content.
3. **an edit request arrived through MCP** — see §12.

### Read the proposal first

```console
$ cat "30_Wiki/_Proposals/Ankle Stiffness 12 Nm-rad-20260812-093015.md"
---
target: 30_Wiki/Findings/Ankle Stiffness 12 Nm-rad.md
requested_by: Jane Kim
status_at_request: reviewed
created: 2026-08-12
source_request: 10_Inbox/_requests/2026-08-12-113000-요청.md
---

# 변경 제안: [[Ankle Stiffness 12 Nm-rad]]

## Current content
See the target document (status: reviewed).

## Proposed content
State explicitly that 12 Nm/rad comes from fatigue test round 2.

## Rationale
Without the condition, a later round with a different value makes this claim wrong.
```

### Apply one

```console
$ llm-wiki review apply "Ankle Stiffness"
✓ 반영 완료: 30_Wiki/Findings/Ankle Stiffness 12 Nm-rad.md (status reviewed 유지)
  확인: llm-wiki diff 20260812-101122 / 되돌리기: llm-wiki rollback 20260812-101122
```

The name argument is a substring match. If it matches more than one proposal, the command stops
and lists them rather than guessing:

```console
$ llm-wiki review apply "Ankle"
제안을 특정하지 못했습니다 (매칭 2건). 보유: Ankle Stiffness…-093015.md, Ankle Angle…-101500.md
```

### Apply everything

```console
$ llm-wiki review apply --all
다음 제안 3건을 모두 승인·반영합니다:
  - Ankle Stiffness 12 Nm-rad-20260812-093015.md
  - Gait Phase Estimation-20260812-093015.md
  - Series Elastic Actuator-20260812-093015.md
진행할까요? [y/N]: y

✓ 일괄 반영 3건
```

The list is always printed **before** the confirmation — you never approve something you have
not seen. Failures are isolated and counted.

### Reject one

```console
$ llm-wiki review reject "Series Elastic" --reason "Superseded by the 2026 revision"
✓ 거부·정리: Series Elastic Actuator-20260812-093015.md (사유: Superseded by the 2026 revision)
```

The reason is written to `.llm-wiki/processing-log.md` before the file is removed.

### What `apply` guarantees

The merge itself is done by the LLM (it has to read both documents and combine them), but the
code enforces the outcome:

- `status` and `reviewer` are restored from the **original** — a merge can never promote a
  document or change who reviewed it.
- The `## Comments` section is restored from the original verbatim.
- A backup is taken first; if the merge result is not a valid document, the original is left
  untouched.

---

## 9. Ask questions — `ask`

```console
$ llm-wiki ask "Why did we choose 12 Nm/rad for ankle stiffness?" --asker "Jane Kim"
근거 2건 · 백엔드 oauth-anthropic/claude-opus-5

The 12 Nm/rad value was adopted based on fatigue test round 2, where it produced 1.8x the
service life of the aluminum design [1]. The controller uses it as a fixed value during the
stance phase [2] (draft).

근거
  [1] 30_Wiki/Findings/Ankle Stiffness 12 Nm-rad.md  (reviewed)
  [2] 30_Wiki/Methods/Gait Phase Estimation.md  (draft)
  ! draft 근거가 포함됐습니다 — 미검토 내용입니다.

토큰 in 4210 / out 118
```

### What it does and does not do

- Evidence comes **only from compiled wiki documents** (`30_Wiki/`). It does not re-read source
  PDFs — that is what compiling was for.
- Every sentence carries a `[n]` citation, and the evidence list shows each document's status.
  A `draft` citation is flagged as unverified.
- The answer is **never written anywhere**. `ask` cannot modify the wiki.
- The query is logged with your name in `.llm-wiki/metrics/queries.jsonl`.

### Options

| Flag | Effect |
|---|---|
| `--asker <name>` | Attribution. Falls back to `$LLM_WIKI_ASKER`, then your login name |
| `--top N` | How many documents to use as evidence (default 5) |
| `--no-draft` | Use only `approved`/`reviewed` documents as evidence |
| `--save-qa` | Save background-knowledge items without asking |
| `--no-save-qa` | Never ask about saving |

Set your name once instead of typing it every time:

```console
$ export LLM_WIKI_ASKER="Jane Kim"      # add to ~/.zshrc
```

### When there is no evidence

```console
$ llm-wiki ask "What is the fatigue limit of the carbon layup?"
Wiki 근거 0건 · 백엔드 oauth-anthropic/claude-opus-5
(검색으로 관련 문서를 찾지 못했습니다 — 배경지식만으로 답합니다)

Wiki에 근거 문서가 없습니다.

## Model background knowledge (needs verification)
- Fatigue limits of carbon-fiber laminates depend strongly on layup orientation and resin system.
- The specific layup, test conditions, and results for this project are project-specific
  information I do not have.
```

Note what it refuses to do: it will not invent a project-specific number. A zero-evidence answer
is also a signal — it means the topic has not been compiled yet.

### Feeding answers back into the wiki

If the answer contains a `## Model background knowledge` section, `ask` offers to promote those
items — **and only those items**:

```console
위 답변의 '모델 배경지식' 2건은 Wiki 근거가 아닙니다.
원자료 후보로 저장하면 다음 편찬에서 검토를 거쳐 반영됩니다.
  저장할까요? [y/N] Fatigue limits of carbon-fiber laminates depend strongly on layup…
  > y
  저장할까요? [y/N] The specific layup, test conditions, and results for this project…
  > n

✓ 1건 저장: 10_Inbox/_qa/2026-08-13-142233-qa.md
  다음: `llm-wiki ingest` → `llm-wiki compile` 로 Wiki에 반영됩니다.
```

Content that was answered **from the wiki** is never offered for promotion. That is deliberate:
letting wiki summaries flow back in as "sources" would create an AI self-reference loop where
the system cites its own paraphrases as evidence.

The saved file then travels the normal path:

```console
$ llm-wiki ingest --yes
  - _qa/2026-08-13-142233-qa.md → 20_Sources/QA-Sessions/2026-08-13-142233-qa.md (qa, Jane Kim)
$ llm-wiki compile
```

---

## 10. Search — `search` / `reindex`

```console
$ llm-wiki search ankle stiffness
[approved] Ankle Stiffness 12 Nm-rad  (30_Wiki/Findings/Ankle Stiffness 12 Nm-rad.md)
    …adopted 12 Nm/rad for [ankle] [stiffness] based on fatigue test round 2…
[draft] Gait Phase Estimation  (30_Wiki/Methods/Gait Phase Estimation.md)
    …the controller holds [stiffness] constant during stance…

$ llm-wiki search ankle stiffness --no-draft    # approved/reviewed only
```

Results are ordered `approved` → `reviewed` → `draft` → `disputed` → `deprecated`.

The index rebuilds itself when documents change, so `reindex` is only for a corrupted index:

```console
$ llm-wiki reindex
✓ 인덱스 재구축 완료 (.llm-wiki/index/fts.sqlite)
```

**Natural-language questions work.** Both languages are normalized before searching — Korean
particles and verb endings are stripped, English plurals and tenses are stripped, and the stems
go out as prefix queries. So `actuators` finds `actuator`, and `제어기를 왜 바꿨나요?` finds
documents containing `제어기 교체`.

---

## 11. Comments

The `## Comments` section is a researcher notebook attached to each document. Two rules:

- **The compiler never edits it** and never uses it as evidence.
- **It is preserved verbatim** through updates and proposal merges.

### By hand

Open the document and append a line in this format:

```markdown
## Comments

- 2026-08-13 **Jane Kim**: Round 3 is scheduled for 8/20; this number may change.
- 2026-08-14 **Pilwon Hur**: Agreed. Keep as reviewed until then.
```

The date-and-bold-name format matters — `audit` flags lines that do not match it, so
attribution stays machine-checkable.

### Through an assistant (MCP)

> *"Leave a comment on the ankle stiffness document saying round 3 may change this."*

The assistant calls `wiki_add_comment`, which appends to the existing section (creating it only
if absent) and never touches the body.

### Comments do not change the wiki

A comment is a record, not a request. If you want the content changed, use an edit request
(§12) or edit the document yourself. The `#반영요청` tag mentioned in the template is a
convention for agents to notice — it is **not** processed by any command today.

---

## 12. Edit requests from an assistant

An external assistant cannot edit the wiki. It can only file a request, which then travels a
fixed path with a human at the end:

```
assistant → 10_Inbox/_requests/ → compile → 30_Wiki/_Proposals/ → you: review apply → document
```

### Filing one

> *"The ankle stiffness document should say the value is from fatigue test round 2. File that
> as an edit request."*

```
요청 접수: 10_Inbox/_requests/2026-08-13-113000-요청.md — 다음 compile에서 처리됩니다.
```

### Converting it

```console
$ llm-wiki compile
✓ 백업 20260813-114500 | 편찬 요청 1건

✓ 편찬 완료 — 산출 1건, 실패 0건, 토큰 in 0 / out 0
  편찬 요청: 제안 전환 1건
  - 요청→제안: 2026-08-13-113000-요청.md → 30_Wiki/_Proposals/Ankle Stiffness 12 Nm-rad-20260813-114500.md (Jane Kim)
```

Note `토큰 in 0 / out 0` — converting a request to a proposal is deterministic and costs
nothing. It also works with no LLM backend configured at all, and when there are no unprocessed
sources.

The original request moves to `90_Archive/_requests/` so it is never processed twice.

### If the target does not exist

```console
  편찬 요청: 제안 전환 0건, 보류 1건
  보류 요청은 10_Inbox/_requests/ 에 남습니다 — 대상 경로를 고치거나 파일을 지우세요.
  - 요청 보류: 2026-08-13-113500-요청.md — 대상 문서를 찾지 못함 (30_Wiki/Concepts/Nonexistent.md)
```

Requests can only target **existing** documents inside `30_Wiki/`. You cannot create a new
document by filing a request — put source material in the Inbox instead.

---

## 13. Quality audit — `audit`

```console
$ llm-wiki audit
✓ 감사 완료 — 발견 3건 (리포트: .llm-wiki/audit/2026-08-13-1530.md)
  [깨진 wikilink] 1건
    - Concepts/Adaptive Impedance Control.md → [[Gait Phase Estimator]]
  [페이지 범위 초과 인용] 1건
    - Findings/Ankle Stiffness 12 Nm-rad.md → kim2026_adaptive_gait.pdf#page=48 (총 32쪽)
  [장기 방치 draft (14일+)] 1건
    - Methods/Torque Sensing.md (18일)
```

Audit **reports only**. It never modifies a document.

| Check | What it means | What you do |
|---|---|---|
| 깨진 wikilink | A `[[link]]` points at a file that does not exist | Fix the link, or compile the missing document |
| 페이지 범위 초과 인용 | `#page=N` exceeds the PDF's page count | The citation is wrong — verify and correct |
| 출처 없는 문서 | No `## Sources` section with wikilinks | The document has no evidence; investigate |
| status 이상 | `status` is not one of the five valid values | Typo in the frontmatter |
| 장기 방치 draft | A draft older than `review.stale_draft_days` (default 14) | Review it or drop it |
| 코멘트 형식 오류 | A comment line missing the `- YYYY-MM-DD **Name**:` format | Fix the format so attribution stays checkable |
| 동기화 충돌 사본 | Dropbox/iCloud "conflicted copy" files | Merge and delete the copy |
| manifest 원자료 불일치 | A registered source file is missing from disk | Restore it or fix the manifest |
| 규칙 파일 이중화 | `CLAUDE.md` contains rules instead of a single import | Move the content to `AGENTS.md` |

The report also lists documents still carrying `Evidence needed` callouts. Those are **not**
errors — they mark statements waiting for source material.

On macOS, PDF page counts come from Spotlight automatically. On Windows and Linux, inject
`pypdf` once to enable that check: `pipx inject llm-wiki pypdf`.

Weekly is a good cadence:

```cron
0 4 * * 0  cd /path/Project-Exo && llm-wiki audit
```

---

## 14. Undo: `diff`, `rollback`, backups

Every `compile` and every `review apply` takes a backup of `30_Wiki/` first.

```console
$ llm-wiki diff                       # most recent run
기준: 백업 20260813-114500
  추가: 30_Wiki/Concepts/Adaptive Impedance Control.md
  변경: 30_Wiki/Findings/Ankle Stiffness 12 Nm-rad.md

$ llm-wiki diff 20260813-114500 -v    # with line-level diffs
$ llm-wiki rollback 20260813-114500   # restore that point
✓ 20260813-114500 시점으로 복원 완료 (직전 상태도 백업해 두었습니다)
```

Rollback itself takes a backup first, so an accidental rollback is also reversible. The last 10
runs are kept by default (`snapshot.backup_keep`).

**Git is not required.** A `git.enabled` key exists in the config for a future Git mode, but
there is no `llm-wiki git` command today — the built-in backups are the mechanism.

---

## 15. Notifications — `notify`

```console
$ llm-wiki notify --dry-run
[Project-Exo] 검토 대기 5건
- draft 3건, 변경 제안 1건, Q&A 제출 1건

$ llm-wiki notify
```

It counts drafts, proposals, disputed documents, pending Q&A submissions, and pending edit
requests. **If the total is zero it sends nothing** — no daily "all clear" noise.

Configure channels in `.llm-wiki/config.yaml`:

```yaml
notifications:
  macos: true                      # macOS notification (default on, macOS only)
  webhook: https://hooks.slack.com/services/XXX/YYY/ZZZ
  email_to: jane@gist.ac.kr
  smtp_host: smtp.gmail.com
  smtp_port: 587
  smtp_from: lab-wiki@gist.ac.kr
  smtp_user: lab-wiki@gist.ac.kr
  smtp_pass: "app-password"
```

Typical nightly batch:

```cron
0 3 * * *  cd /path/Project-Exo && llm-wiki ingest --yes && llm-wiki compile && llm-wiki notify
```

---

## 16. Working with agent CLIs

### What the slash commands actually are

`/wiki-compile` is **not MCP**. It is a prompt file that tells the agent to run the `llm-wiki`
CLI. The result is identical to typing the command yourself, and every code-level safeguard
applies. Install the global adapters once:

```console
$ llm-wiki setup-agent claude     # or: codex / agy / all
✓ Claude Code: 전역 /wiki-init 스킬 → ~/.claude/skills/wiki-init
```

| Agent | Rules (AGENTS.md) | Natural language | `/wiki-*` | `/wiki-init` |
|---|---|---|---|---|
| Claude Code | Immediate (`CLAUDE.md` imports it) | Immediate | Immediate (`.claude/skills/`) | `llm-wiki setup-agent claude` |
| Codex | Immediate | Immediate | `llm-wiki setup-agent codex` | Included |
| Antigravity (`agy`) | Immediate | Immediate | Immediate (`.agents/skills/`) | `llm-wiki setup-agent agy` |

```console
$ cd Project-Exo && claude
> /wiki-ingest                 # = llm-wiki ingest
> /wiki-compile                # = llm-wiki compile
> /wiki-audit                  # = llm-wiki audit
> /wiki-ask                    # = llm-wiki ask
> clean up the inbox and compile, then tell me what changed
```

Headless, for scripts:

```console
$ claude -p "/wiki-compile"
$ codex exec "/wiki-compile"
$ agy -p "/wiki-compile"
```

### The one thing to understand about safety

There are two different paths, and they have different guarantees:

| You type | What runs | Enforced by |
|---|---|---|
| `/wiki-compile` | `llm-wiki compile` | **Code** — lock, backup, path allowlist, draft forcing, comment preservation |
| "clean up the inbox and compile" | The agent *may* run the CLI, or may edit files itself | `AGENTS.md` rules — **prompt-level only** |

An agent with file-write access that ignores `AGENTS.md` has no code stopping it. If you want
the guaranteed path, name the command: *"run `llm-wiki compile`"*.

`AGENTS.md` is the single source of rules. Edit it there; `CLAUDE.md` is one import line.

---

## 17. Working through MCP

MCP is the doorway for assistants that should **read and submit, but never write**. It is the
right choice for students, collaborators, or any assistant you do not want to give filesystem
access.

### Register

**Claude Code** — run inside the project folder; the default scope is `local`, so the server is
visible only in that project:

```console
$ cd Project-Exo
$ claude mcp add llm-wiki -- llm-wiki serve-mcp
```

**Antigravity** — create `.agents/mcp_config.json` in the project root:

```json
{"mcpServers": {"llm-wiki": {"command": "llm-wiki", "args": ["serve-mcp"]}}}
```

**Codex** — `~/.codex/config.toml` (global only, so pass `--project`):

```toml
[mcp_servers.llm-wiki]
command = "llm-wiki"
args = ["serve-mcp", "--project", "/absolute/path/Project-Exo"]
```

> **Managing several projects.** Claude Code (`local` scope) and Antigravity
> (`.agents/mcp_config.json`) isolate servers per project, so only one is ever visible in a
> session. Codex has only a global config, so each registered project adds another copy of the
> same seven tools (~660 tokens each, and duplicate `wiki_search` names the model must
> disambiguate). Register only the projects you actively query from Codex.

### The seven tools

| Tool | Does | Write access |
|---|---|---|
| `wiki_search` | Full-text search; logs the query with the asker's real name | — |
| `wiki_read` | Read a document (`30_Wiki` only) | — |
| `wiki_status` | Project summary | — |
| `wiki_request_edit` | File an edit request → `_requests/` → compile → proposal → your approval | request only |
| `wiki_save_qa` | Submit consented new information → `_qa/` (web items require URLs) | submit only |
| `wiki_add_comment` | Append a comment | append only |
| `wiki_activity` | Per-member activity summary | — |

**There is no tool that edits wiki content.** That is the design, not an oversight.

### Conversation examples

> *"Search the wiki for what we know about gait phase estimation."*
> → `wiki_search`, logged as your query

> *"Read the ankle stiffness document and summarize the open questions."*
> → `wiki_search` + `wiki_read`

> *"That number should mention it's from round 2 — file an edit request."*
> → `wiki_request_edit` → appears in your next `compile` as a proposal

> *"I found a 2026 benchmark paper online that contradicts our finding. Save the relevant part
> as source material."*
> → `wiki_save_qa` — **web items are rejected without a URL**

> *"Leave a comment noting round 3 is scheduled."*
> → `wiki_add_comment`

> *"Who has uploaded and asked the most this month?"*
> → `wiki_activity`

---

## 18. Output language (English / Korean)

Pick `ko` or `en` during `init`. The choice controls the document body **and the section
headings**:

| Language | Template | Headings |
|---|---|---|
| `ko` | `wiki-doc.ko.md` | `## 요약` `## 근거` `## 코멘트` |
| `en` | `wiki-doc.en.md` | `## Summary` `## Sources` `## Comments` |

Section headings are prose for humans **and a schema for the code** — comment preservation, the
missing-source check, Q&A attribution, and request parsing all key off them. Writing uses your
configured language; parsing accepts both, so a mixed project never silently loses a safeguard.

Search handles both languages regardless of the setting, so a bilingual wiki works.

**Choose the language when you create the project and keep it.** Changing it later does not
break anything, but you end up with documents in two languages side by side.

---

## 19. A complete worked example

A realistic week, start to finish.

### Monday — set up

```console
$ mkdir Project-Exo && cd Project-Exo
$ llm-wiki init
  ... name, purpose, members: Pilwon Hur, Jane Kim / reviewer: Jane Kim
  ... language: en / external LLM: y / model: claude-opus-5

$ $EDITOR 00_Project/scope.md      # research questions, in/out of scope
$ $EDITOR 00_Project/glossary.md   # preferred terms
```

### Monday — first material

```console
$ cp ~/Downloads/kim2026_adaptive_gait.pdf "10_Inbox/Jane Kim/"
$ cp ~/Downloads/lee2025_sea_design.pdf    "10_Inbox/Jane Kim/"
$ llm-wiki ingest --yes
✓ 등록 2 / 중복 0 / 보류 0

$ llm-wiki compile
✓ 백업 20260817-101500 | 백엔드 oauth-anthropic/claude-opus-5 | 대상 2건
✓ 편찬 완료 — 산출 6건, 실패 0건, 토큰 in 51203 / out 10422 / $0.5133
```

### Tuesday — review

```console
$ llm-wiki review
검토 대기 draft 6건 (오래된 순): ...
```

Open each document, follow every `## Sources` link, confirm the claims. Two are accurate:

```diff
-status: draft
-reviewer:
+status: reviewed
+reviewer: Jane Kim
```

One cites page 12 but the claim is on page 14 — fix the citation, then mark it reviewed.
One has a claim you cannot find anywhere in the paper — leave it `draft` and add a comment:

```markdown
## Comments

- 2026-08-18 **Jane Kim**: Cannot locate the 40% figure in the source. Holding as draft.
```

### Wednesday — meeting

```console
$ cp meeting_2026-08-19.md "10_Inbox/Pilwon Hur/"
$ llm-wiki ingest --yes && llm-wiki compile
✓ 편찬 완료 — 산출 3건, 실패 0건
  - 생성: 30_Wiki/Findings/Carbon Patella Support.md
  - 제안: 30_Wiki/_Proposals/Series Elastic Actuator-20260819-140000.md
```

The proposal appeared because `Series Elastic Actuator` is already `reviewed` — the compiler
could not edit it directly.

```console
$ cat "30_Wiki/_Proposals/Series Elastic Actuator-20260819-140000.md"
$ llm-wiki review apply "Series Elastic"
✓ 반영 완료 (status reviewed 유지)
```

### Thursday — questions

```console
$ export LLM_WIKI_ASKER="Jane Kim"
$ llm-wiki ask "What did we decide about the patella support material?"
근거 1건 · 백엔드 oauth-anthropic/claude-opus-5

Carbon fiber was adopted, based on fatigue test round 2 showing 1.8x the service life of
aluminum [1] (draft).

근거
  [1] 30_Wiki/Findings/Carbon Patella Support.md  (draft)
  ! draft 근거가 포함됐습니다 — 미검토 내용입니다.
```

A new student asks something the wiki does not cover:

```console
$ llm-wiki ask "What are typical failure modes of carbon layups under cyclic load?" --asker "Daehak Lee"
Wiki 근거 0건 — 배경지식만으로 답합니다
...
  저장할까요? [y/N] Delamination is the dominant failure mode in cyclic loading of laminates…
  > y
✓ 1건 저장: 10_Inbox/_qa/2026-08-20-160212-qa.md
```

Zero-evidence answers are a knowledge-gap signal: that topic deserves source material.

### Friday — audit and close the loop

```console
$ llm-wiki ingest --yes            # picks up the Q&A submission
  - _qa/2026-08-20-160212-qa.md → 20_Sources/QA-Sessions/... (qa, Daehak Lee)
$ llm-wiki compile
$ llm-wiki audit
✓ 감사 완료 — 발견 1건
  [깨진 wikilink] 1건
    - Findings/Carbon Patella Support.md → [[Fatigue Test Protocol]]

$ llm-wiki status
프로젝트: Adaptive exoskeleton control for hemiplegic gait
원자료: 4건 (미처리 0건)
Wiki: draft 5, reviewed 4
제안 대기: 0건 / 백업: 4회분
```

### Later — promote to approved

After the group agrees the ankle stiffness finding is settled:

```diff
-status: reviewed
+status: approved
```

It now ranks first in `search` and in `ask`, and is quotable in proposals.

---

## 20. Command reference

| Command | Purpose | Needs an LLM |
|---|---|---|
| `init [path] [--yes]` | Create a project + onboarding (idempotent) | no |
| `ingest [--yes]` | Intake from Inbox: hash, duplicates, normalize, classify, register | no |
| `compile` | Compile the wiki; also converts pending edit requests | yes (unless requests only) |
| `review` | Show the review queue | no |
| `review apply <name>` / `--all` | Approve proposals and merge them | yes |
| `review reject <name> --reason <text>` | Reject a proposal, log the reason | no |
| `ask <question> [--asker N] [--top N] [--no-draft] [--save-qa\|--no-save-qa]` | Wiki-grounded Q&A | yes |
| `search <query> [--no-draft]` | Full-text search | no |
| `reindex` | Rebuild the search index | no |
| `audit` | Quality audit report (report only) | no |
| `status` | Project summary | no |
| `diff [run-id] [-v]` | Changes against a backup | no |
| `rollback [run-id]` | Restore a backup | no |
| `models use [model] [--role R] [--global]` | Choose the model | no |
| `models show` | Current settings and available auth paths | no |
| `models auth "<order>"` | Change auth priority | no |
| `models list\|add\|remove` | Model registry | no |
| `notify [--dry-run]` | Review-pending notification (silent at zero) | no |
| `serve-mcp [--project P]` | MCP stdio server | no |
| `setup-agent claude\|codex\|agy\|all` | Install global agent adapters | no |

`compile` accepts `--force`, but it currently has no effect.

---

## 21. Configuration reference

`<project>/.llm-wiki/config.yaml`, with `~/.llm-wiki/config.yaml` as the global fallback:

```yaml
project: "Adaptive exoskeleton control for hemiplegic gait"
language: en                       # ko | en — set at init, governs body and headings
external_llm_allowed: true         # false = Ollama only, enforced in code

model:
  compile: claude-opus-5           # the model that compiles
  audit: claude-haiku-4-5          # reserved — not read yet
  metadata: claude-haiku-4-5       # reserved — not read yet
  fallback_local: qwen3:32b        # used by the Ollama path

llm:
  auth_order: [oauth, api_key, ollama]
  cli_path_gemini: /opt/homebrew/bin/gemini    # opt-in for org accounts
  cli_args_antigravity: [--effort, high]       # extra CLI arguments per provider

review:
  reviewer: Jane Kim
  stale_draft_days: 14             # audit flags drafts older than this

snapshot:
  backup_keep: 10

git:
  enabled: false                   # reserved — no `llm-wiki git` command yet

notifications:
  macos: true
  webhook: https://hooks.slack.com/services/...
  email_to: jane@gist.ac.kr
  smtp_host: smtp.gmail.com
  smtp_port: 587
  smtp_from: lab-wiki@gist.ac.kr
  smtp_user: lab-wiki@gist.ac.kr
  smtp_pass: "app-password"
```

Other locations:

| Path | Contents |
|---|---|
| `~/.llm-wiki/config.yaml` | Global defaults (model, auth order) |
| `~/.llm-wiki/models.yaml` | Model registry per provider |
| `.llm-wiki/manifest.json` | Every source: hash, type, uploader, processed flag |
| `.llm-wiki/metrics/costs.jsonl` | Tokens and cost per run |
| `.llm-wiki/metrics/queries.jsonl` | Every query with asker and hit count |
| `.llm-wiki/processing-log.md` | Human-readable run log |
| `.llm-wiki/audit/` | Audit reports |
| `.llm-wiki/backups/` | Snapshots (last 10 by default) |

Environment variables: `LLM_WIKI_ASKER` (default asker name), `LLM_WIKI_FAKE` (test hook that
returns a file's contents instead of calling an LLM), plus provider keys
(`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` / `GOOGLE_API_KEY`).

---

## 22. Troubleshooting

**"llm-wiki 프로젝트가 아닙니다 (.llm-wiki 없음)"**
You are outside a project folder. `cd` into it, or run `llm-wiki init`. Note that your home
directory is deliberately not treated as a project even though `~/.llm-wiki/` exists.

**"'claude-opus-5' 을(를) 쓸 수 있는 백엔드가 없습니다"**
Run `llm-wiki models show` — it lists what is blocking each path. Install the CLI, set the API
key, start Ollama, or pick a different model with `llm-wiki models use`.

**PDF compile fails with a pypdf message**
API-key, Ollama, and Antigravity backends read PDF text locally, so they need
`pipx inject llm-wiki pypdf`. The `claude` and `codex` OAuth backends read files themselves and
do not need it.

**A compile run produced nothing and cost nothing**
If the backend is `agy`, a tool-permission denial returns success with an empty response;
llm-wiki turns that into an error and switches backends. Check the message and, if needed,
allow the tool in Antigravity's settings.

**Comments disappeared after an update**
They should not — preservation is enforced in both languages. If it happens, the heading was
probably altered (for example `## 코멘트 (메모)`). Restore from the backup:
`llm-wiki rollback <run-id>`, then fix the heading to match the template exactly.

**Dropbox "conflicted copy" files**
`audit` detects them. Merge by hand, keep the higher status, and delete the copy. When a project
folder is synced across machines, let the sync settle before running commands on the other
machine — and if the folder is a Git repo inside Dropbox, prefer waiting for sync over `git pull`.

**Two people ran compile at the same time**
A lock prevents it — the second run exits with
`오류: 다른 실행이 진행 중입니다 (compile, pid 12345)`. Wait for the first run to finish. If a
process died abnormally the stale lock is released automatically on the next run; if you need to
clear it by hand, delete `.llm-wiki/.lock`.

**An edit request never became a proposal**
The target must be an existing document inside `30_Wiki/`. Check the `- Target:` line in
`10_Inbox/_requests/`, fix the path, and re-run `compile`.

---

## 23. Not implemented yet

Documented honestly so you do not go looking:

| Thing | Status |
|---|---|
| `llm-wiki activity` CLI command | Only the MCP tool `wiki_activity` exists |
| `llm-wiki git enable/disable` | `git.enabled` config key exists, no command |
| Knowledge-gap detection → auto stub in `30_Wiki/Questions/` | Queries are logged; nothing consumes them yet |
| `model.audit` / `model.metadata` roles | Written by `init`, not read — `compile` is the only role in use |
| `#반영요청` comment tag → automatic proposal | Convention for agents only; no command processes it |
| LLM metadata extraction during `ingest` | Title/authors/year are filename-based placeholders |
| Scanned-PDF OCR | Not supported |
| `compile --force` | Flag is accepted but has no effect |

---

*Questions, bugs, and feature requests: [github.com/pilwonhur/llm-wiki](https://github.com/pilwonhur/llm-wiki)*
