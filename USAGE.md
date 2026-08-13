<a id="english"></a>

# llm-wiki — Usage Guide

> **Language / 언어:** **English** · [한국어 →](#korean)

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
llm-wiki 0.7.1
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

Everything in the previous sections can be done conversationally from Claude Code, Codex, or
Antigravity. This section shows what those sessions actually look like.

### 16.1 What the slash commands actually are

`/wiki-compile` is **not MCP**. It is a prompt file that tells the agent to run the `llm-wiki`
CLI. The result is identical to typing the command yourself, and every code-level safeguard
applies. The agent's job is the conversation around it: explaining results, deciding what to do
next, and doing the reading you would otherwise do by hand.

| Agent | Rules (AGENTS.md) | Natural language | `/wiki-*` commands | `/wiki-init` (new folders) |
|---|---|---|---|---|
| Claude Code | Immediate (`CLAUDE.md` imports it) | Immediate | Immediate (`.claude/skills/`, installed by `init`) | `llm-wiki setup-agent claude` |
| Codex | Immediate | Immediate | `llm-wiki setup-agent codex` | Included in that command |
| Antigravity (`agy`) | Immediate | Immediate | Immediate (`.agents/skills/`, installed by `init`) | `llm-wiki setup-agent agy` |

Four project commands are installed by `init`: `/wiki-ingest`, `/wiki-compile`, `/wiki-audit`,
`/wiki-ask`. `/wiki-init` is global because new folders have no project skills yet:

```console
$ llm-wiki setup-agent claude     # or: codex / agy / all — once per machine
✓ Claude Code: 전역 /wiki-init 스킬 → ~/.claude/skills/wiki-init
설치는 컴퓨터당 1회면 충분합니다. 업데이트 후에는 다시 실행하면 갱신됩니다.
```

### 16.2 Starting a session

Log in to Claude Code once (`claude` walks you through it), then open the project folder:

```console
$ cd ~/research/Project-Exo
$ claude
```

The agent reads `CLAUDE.md` (one line importing `AGENTS.md`) on start, so it already knows the
project rules — source material is untouchable, it may only write `draft`, reviewed documents
get proposals, the comment section is off limits, and it must not leave the project folder.

Ask it to orient itself:

```
> what's the state of this project?

I'll check the project status.

  llm-wiki status

프로젝트: Adaptive exoskeleton control for hemiplegic gait
원자료: 4건 (미처리 2건)
Wiki: draft 5, reviewed 4
제안 대기: 1건 / 백업: 3회분

Here's where things stand:

- **2 sources waiting to be compiled** — they were ingested but `compile` hasn't run yet
- **5 drafts need your review**, 4 documents are already reviewed
- **1 proposal is waiting** for approval — that means compile wanted to change a
  reviewed document and was blocked, so it filed a proposal instead

Want me to compile the two pending sources first, or look at the proposal?
```

### 16.3 The four project commands

**`/wiki-ingest`** — intake:

```
> /wiki-ingest

  llm-wiki ingest --yes

✓ 등록 2 / 중복 1 / 보류 0
  - Jane Kim/kim2026_adaptive_gait.pdf → 20_Sources/Papers/kim2026_adaptive_gait.pdf (paper, Jane Kim)
  - Jane Kim/meeting_2026-08-19.md → 20_Sources/Meeting-Notes/meeting_2026-08-19.md (meeting, Jane Kim)
  중복(미이동): Jane Kim/lee2025_sea_design.pdf (기존: 20_Sources/Papers/lee2025_sea_design.pdf)

Registered 2 files, both attributed to Jane Kim.

One duplicate: `lee2025_sea_design.pdf` is already in the wiki (matched by hash, not
filename), so it was left in the Inbox rather than registered twice. You can delete that
copy safely.

Next step is `/wiki-compile` to turn the two new sources into wiki documents.
```

**`/wiki-compile`** — compile:

```
> /wiki-compile

  llm-wiki compile

✓ 백업 20260819-140322 | 백엔드 oauth-anthropic/claude-opus-5 | 대상 2건
  · kim2026_adaptive_gait.pdf 편찬 중...
  · meeting_2026-08-19.md 편찬 중...

✓ 편찬 완료 — 산출 4건, 실패 0건, 토큰 in 52104 / out 11233 / $0.5240
  - 생성: 30_Wiki/Concepts/Adaptive Impedance Control.md
  - 생성: 30_Wiki/Findings/Carbon Patella Support.md
  - 갱신: 30_Wiki/Methods/Gait Phase Estimation.md
  - 제안: 30_Wiki/_Proposals/Series Elastic Actuator-20260819-140322.md

Compiled both sources for $0.52. Three things to know:

1. **Two new documents** from the paper and the meeting notes.
2. **`Gait Phase Estimation` was updated in place** — it was still `draft`, so the compiler
   could edit it directly.
3. **`Series Elastic Actuator` produced a proposal instead of an edit.** That document is
   `reviewed`, so the compiler is not allowed to touch it. The proposal is waiting for you.

A backup was taken before any of this (`20260819-140322`), so `llm-wiki rollback
20260819-140322` undoes the whole run.
```

**`/wiki-audit`** — quality check:

```
> /wiki-audit

  llm-wiki audit

✓ 감사 완료 — 발견 2건 (리포트: .llm-wiki/audit/2026-08-19-1412.md)
  [깨진 wikilink] 1건
    - Concepts/Adaptive Impedance Control.md → [[Gait Phase Estimator]]
  [페이지 범위 초과 인용] 1건
    - Findings/Carbon Patella Support.md → kim2026_adaptive_gait.pdf#page=48 (총 32쪽)

Two issues, and they're different in kind:

**The broken link is cosmetic.** The document links `[[Gait Phase Estimator]]` but the actual
document is `Gait Phase Estimation`. I can fix that wording — it doesn't change any claim.

**The page citation is a real problem.** It cites page 48 of a 32-page PDF, which means the
citation is wrong and the claim behind it is unverified. That needs you to open the paper and
find the real page — I shouldn't guess which page it meant.

Want me to fix the link, and leave the citation for you?
```

**`/wiki-ask`** — grounded questions:

```
> /wiki-ask why did we pick carbon for the patella support?

  llm-wiki ask "why did we pick carbon for the patella support?" --asker "Jane Kim"

근거 1건 · 백엔드 oauth-anthropic/claude-opus-5

Carbon fiber was adopted based on fatigue test round 2, which showed 1.8x the service life
of the aluminum design [1] (draft).

근거
  [1] 30_Wiki/Findings/Carbon Patella Support.md  (draft)
  ! draft 근거가 포함됐습니다 — 미검토 내용입니다.

The answer rests on a **draft** document — compiled from the 8/19 meeting notes but not yet
verified against the original by a human. Treat the 1.8x figure as unconfirmed until someone
reviews that document.
```

### 16.4 A full review session

Reviewing is where an agent earns its place — it can open every cited page and cross-check for
you, which is the tedious part of promoting `draft` to `reviewed`.

```
> I want to review the drafts. Start with the newest one and walk me through the evidence.

  llm-wiki review

검토 대기 draft 5건 (오래된 순): ...

I'll take `Findings/Carbon Patella Support.md` (created today). Reading the document and its
cited source.

  Read 30_Wiki/Findings/Carbon Patella Support.md
  Read 20_Sources/Meeting-Notes/meeting_2026-08-19.md

Here's the check, claim by claim:

| Claim in the document | Cited source | Verdict |
|---|---|---|
| Patella support switches aluminum → carbon | meeting 8/19, "Decisions" | ✓ stated verbatim |
| 1.8x fatigue life vs aluminum | meeting 8/19, "Decisions" | ✓ stated verbatim |
| Round 2 of fatigue testing | meeting 8/19 | ✓ stated |
| "improves overall durability and reliability" | — | ⚠ not in the source |

The first three are solid. The last sentence is an inference the compiler added — reasonable,
but not something the meeting notes say. Two options: delete that sentence, or keep it and
mark it as background knowledge.

> delete it, then mark the document reviewed under my name

I'll remove the unsupported sentence. I can't set the status myself — `reviewed` is
human-only and the code would reject it from me — so I'll make the edit and show you the
exact frontmatter change to make.

  Edit 30_Wiki/Findings/Carbon Patella Support.md

Removed: "This change improves overall durability and reliability of the assembly."

Now change the frontmatter yourself (three lines):

  status: draft      →  status: reviewed
  reviewer:          →  reviewer: Jane Kim
  updated: 2026-08-19 →  updated: 2026-08-19

Open it in your editor, or say the word and I'll make that edit too — but understand that
when I do it, it's your judgment being recorded, not mine.
```

That last exchange is the point of the whole design. The agent can *do* the edit — it has file
access — but the system is built so that promotion is a human act. Let the agent gather evidence
and prepare the change; you decide.

### 16.5 Handling a proposal conversationally

```
> there's a proposal waiting. what does it want to change?

  Read 30_Wiki/_Proposals/Series Elastic Actuator-20260819-140322.md

The proposal targets `30_Wiki/Concepts/Series Elastic Actuator.md`, which is currently
`reviewed`, and comes from the 8/19 meeting notes.

**What it proposes**: add that the SEA spring constant was re-measured at 4.2 kN/m in
round 2, replacing the 3.8 kN/m figure currently in the document.

**Why it's a proposal and not an edit**: the target is `reviewed`, so the compiler is blocked
from editing it directly. This is rule 3.

This one changes a number in a reviewed document, so I'd suggest checking the meeting notes
before approving.

  Read 20_Sources/Meeting-Notes/meeting_2026-08-19.md

Confirmed — the notes say "spring constant re-measured: 4.2 kN/m (round 2, replaces 3.8)".
The proposal is faithful to the source.

> apply it

  llm-wiki review apply "Series Elastic"

✓ 반영 완료: 30_Wiki/Concepts/Series Elastic Actuator.md (status reviewed 유지)
  확인: llm-wiki diff 20260819-142905 / 되돌리기: llm-wiki rollback 20260819-142905

Applied. The document kept `status: reviewed` and its original reviewer — the merge cannot
promote or demote a document, and your comment section came through untouched.

If the merge went wrong, `llm-wiki rollback 20260819-142905` restores it.
```

### 16.6 Natural language, and where it differs

The agent also works without slash commands:

```
> two new papers are in my inbox. process them and tell me if anything conflicts with
> what we already have.
```

A capable agent will run `llm-wiki ingest`, then `llm-wiki compile`, then read the new
documents against the existing ones and report conflicts. That is genuinely more than the CLI
does on its own.

But there is one difference worth internalizing:

| You type | What runs | Enforced by |
|---|---|---|
| `/wiki-compile` | `llm-wiki compile` | **Code** — lock, backup, path allowlist, draft forcing, comment preservation |
| "process the inbox and compile" | The agent *may* run the CLI, or may do the work by editing files itself | `AGENTS.md` — **prompt-level only** |

The `.llm-wiki/workflows/*.md` files exist so an agent can perform the pipeline by hand when the
CLI is not installed. That fallback is why an agent might edit files directly. When it does, the
code-level guarantees do not apply — only the rules in `AGENTS.md`, which are instructions, not
enforcement.

**So: to get the guaranteed path, name the command.** *"Run `llm-wiki compile`"* is unambiguous;
*"compile the wiki"* is not. The skills are written to prefer the CLI (*"if the llm-wiki CLI is
installed, run it instead of performing the procedure"*), which is why slash commands are the
safer habit.

### 16.7 Codex and Antigravity

Same model, same commands, different setup step:

```console
# Codex — install the prompts once, then use them anywhere
$ llm-wiki setup-agent codex
✓ Codex: /wiki-ask /wiki-audit /wiki-compile /wiki-ingest /wiki-init 프롬프트 → ~/.codex/prompts

$ cd Project-Exo && codex
> /wiki-compile
```

```console
# Antigravity — project skills come from init; global ones once
$ llm-wiki setup-agent agy
✓ Antigravity(agy): /wiki-ask /wiki-audit /wiki-compile /wiki-ingest /wiki-init 스킬
  → ~/.gemini/antigravity-cli/skills

$ cd Project-Exo && agy
> /wiki-compile
```

All three read `AGENTS.md` directly — that file is the single source of rules, and `CLAUDE.md`
is just one import line pointing at it. Edit rules in `AGENTS.md` only.

### 16.8 Creating a project by conversation

New folders have no project skills yet, which is why `/wiki-init` is installed globally:

```console
$ mkdir Project-Neuro && cd Project-Neuro && claude
```

```
> /wiki-init

I'll set up an llm-wiki project here. First, a few questions:

1. Full project name?
2. One-line purpose?
3. Members (comma separated)?
4. Who is the Wiki reviewer?
5. Output language — Korean or English?
6. Is any material sensitive (IRB, industry NDA)? If so I'll lock it to local LLMs only.
7. Which model should compile?

> Neural correlates of gait adaptation / studying cortical activity during split-belt
> walking / Pilwon Hur, Daehak Lee / Daehak Lee / English / not sensitive / claude-opus-5

  llm-wiki init --yes
  ... then applying your answers to config.yaml, 00_Project/, and member folders

✓ Project created. Structure: 00_Project through 90_Archive, .llm-wiki/ (config, manifest,
workflows, backups), AGENTS.md + CLAUDE.md, skill adapters, and Inbox folders for
Pilwon Hur and Daehak Lee.

Two things worth doing before you add material:
- Fill in `00_Project/scope.md` — the compiler reads it to judge relevance
- Fill in `00_Project/glossary.md` — it prevents the same concept being filed twice under
  different names

Then drop files into `10_Inbox/<your name>/` and run `/wiki-ingest`.
```

Without the global skill you can still just ask: *"set up a wiki project here"* — the agent runs
the same onboarding conversationally.

### 16.9 Headless and batch

Slash commands work non-interactively, which makes them usable in cron:

```console
$ claude -p "/wiki-compile"
$ codex exec "/wiki-compile"
$ agy -p "/wiki-compile"
```

For unattended batches, prefer the plain CLI — it is faster, cheaper, and has no agent in the
loop to improvise:

```cron
0 3 * * *  cd /path/Project-Exo && llm-wiki ingest --yes && llm-wiki compile && llm-wiki notify
```

Use the agent when you want judgment (review, conflict-checking, explanation); use the CLI when
you want a deterministic pipeline.

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

[↑ Table of contents](#table-of-contents) · [한국어 버전 →](#korean)

---

<a id="korean"></a>

# llm-wiki — 사용 설명서 (한국어)

> **Language / 언어:** [← English](#english) · **한국어**

`llm-wiki`로 연구실 지식 위키를 운영하는 방법을 예제 중심으로 정리한 완전판 안내서입니다.
모든 명령어, 모든 상태 전이, 모든 진입점(CLI, 에이전트 CLI, MCP)을 실제 터미널 출력과 함께 다룹니다.

짧은 개요는 [README.md](README.md)를 보세요. 이 문서는 긴 버전입니다.

---

## 목차

1. [사고 모델](#ko-1)
2. [머신당 한 번만 설치](#ko-2)
3. [LLM 선택](#ko-3)
4. [프로젝트 만들기](#ko-4)
5. [원자료 추가 — `ingest`](#ko-5)
6. [위키 편찬 — `compile`](#ko-6)
7. [문서 생애주기: draft → reviewed → approved](#ko-7)
8. [변경 제안과 `review apply`](#ko-8)
9. [질문하기 — `ask`](#ko-9)
10. [검색 — `search` / `reindex`](#ko-10)
11. [코멘트](#ko-11)
12. [어시스턴트가 보내는 편집 요청](#ko-12)
13. [품질 감사 — `audit`](#ko-13)
14. [되돌리기: `diff`, `rollback`, 백업](#ko-14)
15. [알림 — `notify`](#ko-15)
16. [에이전트 CLI와 함께 쓰기](#ko-16)
17. [MCP로 연결하기](#ko-17)
18. [출력 언어 (영어 / 한국어)](#ko-18)
19. [전체 시나리오 예제](#ko-19)
20. [명령어 레퍼런스](#ko-20)
21. [설정 레퍼런스](#ko-21)
22. [문제 해결](#ko-22)
23. [아직 구현되지 않은 것](#ko-23)

---

<a id="ko-1"></a>

## 1. 사고 모델

세 문장이 전체를 지배합니다.

> **원자료는 사람이 소유한다. AI는 근거로부터 편찬한다. 공식적인 것은 사람이 승인한다.**

구체적으로는 이렇습니다.

| 폴더 | 누가 쓰는가 | 비고 |
|---|---|---|
| `10_Inbox/` | **당신** (파일을 넣는다) | 모든 자료는 여기로 들어옵니다. `ingest`가 밖으로 옮깁니다 |
| `20_Sources/` | `ingest`만 | AI는 원자료를 절대 수정하지 않습니다 |
| `30_Wiki/` | **AI**(`draft`만) + 당신 | 편찬된 지식 베이스 |
| `30_Wiki/_Proposals/` | `compile` | 승인 대기 중인 변경 제안 |
| `40_Decisions/`, `50_Outputs/`, `90_Archive/` | 당신 | AI는 여기에 쓰지 않습니다 |
| `00_Project/` | 당신 | 범위·용어집·구성원 — 편찬기가 컨텍스트로 읽습니다 |
| `.llm-wiki/` | 도구 | 설정, 매니페스트, 백업, 인덱스, 로그, 메트릭 |

다섯 가지 규칙은 프롬프트가 아니라 **코드로** 강제됩니다.

1. AI는 오직 `status: draft`만 쓸 수 있습니다.
2. `30_Wiki/` 밖으로의 쓰기는 차단됩니다.
3. `reviewed` 이상인 문서는 AI가 편집할 수 없고, 변경 제안으로 강등됩니다.
4. `## Comments` 섹션은 갱신·병합할 때마다 원문 그대로 보존됩니다.
5. 모든 실행은 먼저 백업을 뜨고, `rollback`으로 복원할 수 있습니다.

프롬프트가 이 규칙을 어기라고 지시하더라도 코드가 막습니다.

---

<a id="ko-2"></a>

## 2. 머신당 한 번만 설치

필요한 것은 **Python 3.12 이상**과 pipx뿐입니다. 검색 DB는 파이썬 내장 SQLite이고 스냅샷도 내장
백업을 쓰므로 Git은 필요 없습니다.

```console
$ pipx install "git+https://github.com/pilwonhur/llm-wiki.git"
$ llm-wiki --version
llm-wiki 0.7.1
```

기본 `python3`가 3.12보다 낮으면 pipx에 새 인터프리터를 지정하세요.

```console
$ pipx install --python /opt/homebrew/bin/python3.12 "git+https://github.com/pilwonhur/llm-wiki.git"
```

나중에 업데이트할 때는 이렇게 합니다.

```console
$ pipx reinstall llm-wiki
```

설치는 **프로젝트마다가 아니라 머신마다 한 번**입니다. 프로젝트 생성은 `llm-wiki init`입니다.

### 선택 구성 요소

| 설치 대상 | 필요한 상황 |
|---|---|
| `claude` CLI (Claude Code) | Anthropic 구독(OAuth)을 편찬 백엔드로 쓸 때 |
| `codex` CLI | OpenAI 구독(OAuth)을 편찬 백엔드로 쓸 때 |
| `agy` CLI (Antigravity) | Antigravity 구독(OAuth)을 편찬 백엔드로 쓸 때 |
| `pipx inject llm-wiki anthropic` (또는 `openai`, `google-genai`) | API 키 백엔드 |
| Ollama | 로컬 모델 — 민감한 프로젝트, 오프라인 작업 |
| `pipx inject llm-wiki pypdf` | API 키/Ollama/Antigravity 백엔드에서 PDF를 읽을 때 |

편찬 백엔드는 **정확히 하나만** 있으면 됩니다. 이 문서의 나머지 기능(`ingest`, `search`,
`audit`, `status`, `diff`, `rollback`, `notify`, `serve-mcp`)은 LLM 없이도 동작합니다.

---

<a id="ko-3"></a>

## 3. LLM 선택

### 지금 무엇이 설정돼 있는지 보기

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

읽는 법: 역할별로 어떤 모델, 어떤 공급자, 실제로 어떤 호출 경로가 쓰이는지, 그리고 쓸 수 없는
경로는 무엇이 막고 있는지를 보여줍니다.

### 모델 설정하기

```console
# 대화형 — 공급자, 모델, 저장 위치를 차례로 고릅니다
$ llm-wiki models use

# 직접 지정
$ llm-wiki models use gpt-5.6-sol

# 이 머신의 모든 프로젝트 기본값으로
$ llm-wiki models use gemini-3.6-flash-high --global

# 역할별로 섞어서 비용 절약: 편찬은 무거운 모델, 감사는 가벼운 모델
$ llm-wiki models use claude-opus-5   --role compile
$ llm-wiki models use claude-haiku-4-5 --role audit
```

설정은 두 계층으로 나뉘고, 항상 프로젝트 계층이 이깁니다.

| 계층 | 파일 | 용도 |
|---|---|---|
| 전역 | `~/.llm-wiki/config.yaml` | 이 머신의 기본값. `init`이 새 프로젝트의 기본값으로 제안합니다 |
| 프로젝트 | `<project>/.llm-wiki/config.yaml` | 이 프로젝트의 선택. 설정하지 않은 값은 전역에서 상속됩니다 |

즉 "한 번 정해두고 계속 쓰기"는 전역 계층이고, "이 프로젝트만 다르게"는 프로젝트 계층입니다.
둘 다 직접 편집할 수 있습니다 — `models use`는 건드리는 키만 다시 쓰고 주석은 그대로 둡니다.

### 공급자와 인증 경로

| 공급자 | OAuth (구독) | API 키 |
|---|---|---|
| Anthropic | `claude` CLI | `ANTHROPIC_API_KEY` + `anthropic` |
| OpenAI | `codex` CLI | `OPENAI_API_KEY` + `openai` |
| Antigravity | `agy` CLI | — (구독 전용) |
| Google Gemini | — (개인 구독 종료) | `GEMINI_API_KEY` 또는 `GOOGLE_API_KEY` + `google-genai` |
| Ollama | — | 로컬 `localhost:11434` |

**모델 이름이 공급자를 결정합니다.** 먼저 레지스트리를 확인하고, 없으면 접두사 휴리스틱을 씁니다.

```console
$ llm-wiki models list
anthropic: claude-fable-5, claude-opus-5, claude-sonnet-5, claude-haiku-4-5
openai: gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna
gemini: gemini-3.6-flash, gemini-3.1-pro-preview
antigravity: gemini-3.6-flash-high, claude-sonnet-4-6, gpt-oss-120b-medium, ...
ollama: (없음)

# 새 모델이 나왔다면 등록해 두면 모든 프로젝트가 쓸 수 있습니다
$ llm-wiki models add openai gpt-5.7-nova

# 이름이 모호하다면 접두사로 공급자를 강제합니다
$ llm-wiki models use openai/my-finetuned-model
```

### 인증 순서와 자동 전환

```console
$ llm-wiki models auth "oauth,api_key,ollama"     # 기본값
$ llm-wiki models auth "api_key,oauth"            # API 키 우선
```

사용 가능한 경로는 **순서대로** 묶입니다. 실행 중에 첫 경로가 실패하면(로그인 만료, 구독 등급
문제, 레이트 리밋) 자동으로 다음 경로로 전환하고 그 사실을 알려줍니다.

```console
  · kim2026_gait.pdf 편찬 중...
    ! oauth-gemini 실패 → api-gemini 로 전환
```

### 민감한 프로젝트

```yaml
# .llm-wiki/config.yaml
external_llm_allowed: false
model:
  fallback_local: qwen3:32b
```

이 설정은 코드로 강제됩니다. 어떤 모델이 설정돼 있든 프로젝트는 **오직 Ollama만** 사용합니다.
이를 무시하는 플래그나 프롬프트는 없습니다. `models show`도 이를 분명히 알려줍니다.

```console
  ! external_llm_allowed: false — 민감 프로젝트라 설정 모델과 무관하게 로컬(Ollama)만 사용합니다 (N7)
```

---

<a id="ko-4"></a>

## 4. 프로젝트 만들기

프로젝트는 그냥 폴더 하나입니다. 만드는 방법은 세 가지이고, 결과는 모두 같습니다.

### 방법 1 — 터미널 (가장 흔함)

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

스크립트용 비대화형 실행은 `llm-wiki init --yes`이고, 모든 항목에 기본값을 씁니다.
다른 폴더를 초기화할 수도 있습니다: `llm-wiki init /path/to/Project-X`.

### 방법 2 — 에이전트에게 평범한 말로 부탁하기

빈 폴더에서 Claude Code, Codex, Antigravity를 열고 *"여기에 위키 프로젝트 세팅해줘"* 라고
말하면 됩니다. 에이전트가 온보딩을 대화로 진행하면서 내부적으로 `llm-wiki init`을 호출합니다.

### 방법 3 — 전역 `/wiki-init` 스킬

```console
$ llm-wiki setup-agent claude      # 또는 codex / agy / all — 머신당 한 번
```

이후 그 에이전트에서는 어느 폴더에서든 `/wiki-init`이 동작합니다.

### init이 만드는 것

```
Project-Exo/
├── 00_Project/         README.md, scope.md, glossary.md, members.md   ← 당신이 채웁니다
├── 10_Inbox/           Pilwon Hur/, Jane Kim/, Daehak Lee/            ← 구성원별 폴더
├── 20_Sources/         Papers/ Meeting-Notes/ Experiments/ Datasets/
│                       Web-Clips/ QA-Sessions/ Proposals/
├── 30_Wiki/            Concepts/ Methods/ Findings/ People/ Equipment/
│                       Questions/ _Proposals/
├── 40_Decisions/  50_Outputs/  90_Archive/
├── AGENTS.md           에이전트 규칙 (단일 진실 원천)
├── CLAUDE.md           AGENTS.md를 가리키는 import 한 줄
├── .claude/skills/     /wiki-ingest, /wiki-compile, /wiki-audit
├── .agents/skills/     Antigravity용 동일 스킬
└── .llm-wiki/
    ├── config.yaml     프로젝트 설정
    ├── manifest.json   등록된 모든 원자료: 해시, 유형, 업로더, 처리 여부
    ├── templates/      wiki-doc.md (언어에 따라 선택) + wiki-doc.ko.md / .en.md
    ├── workflows/      ingest.md, compile.md, audit.md (에이전트 대체 절차)
    ├── backups/  index/  metrics/  audit/
    └── processing-log.md
```

`init`은 **멱등적**입니다. 이미 파일이 있는 폴더에서 실행해도 기존 파일은 건드리지 않고, 빠진
것만 채웁니다. `pipx reinstall` 후 새 템플릿을 받아 오는 공식적인 방법이 바로 이것입니다.

### `00_Project/` 채우기

시작하는 데 필수는 아니지만, 편찬기가 `scope.md`와 `glossary.md`를 컨텍스트로 읽기 때문에
채워 두면 출력 품질이 크게 좋아집니다.

- `scope.md` — 무엇이 범위 안이고 밖인지, 연구 질문
- `glossary.md` — 개념별 선호 용어. 이게 있어야 AI가 "가변 강성 구동기"와
  "Variable Stiffness Actuator"를 두 개의 문서로 만들지 않습니다
- `members.md` — 구성원 표. `ingest`는 여기에 없는 업로더에 대해 경고합니다

---

<a id="ko-5"></a>

## 5. 원자료 추가 — `ingest`

### 자기 폴더에 파일 넣기

```console
$ cp ~/Downloads/kim2026_adaptive_gait.pdf  Project-Exo/10_Inbox/Jane\ Kim/
$ cp meeting_2026-08-12.md                  Project-Exo/10_Inbox/Jane\ Kim/
```

하위 폴더 이름이 곧 **업로더 귀속**입니다. `10_Inbox/` 최상위에 놓인 파일도 처리되지만
`unknown`으로 기록됩니다.

### ingest 실행

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

`--yes`는 모든 추측을 묻지 않고 그대로 받아들입니다. 야간 배치가 쓰는 방식입니다.

### ingest가 하는 일, 순서대로

1. `10_Inbox/`를 재귀적으로 **스캔**합니다(`.gitkeep`, `.DS_Store`, 점 파일은 제외).
2. 각 파일을 **해시**(SHA-256)해 매니페스트와 대조합니다. 중복은 보고만 하고 그 자리에 두며,
   절대 두 번 등록하지 않습니다.
3. 파일명으로 **유형을 추측**한 뒤 물어봅니다(`--yes`가 아니면).
4. Obsidian 위키링크를 깨뜨리는 문자(`[ ] # ^ |`)를 제거해 **파일명을 정규화**합니다.
   원래 이름은 매니페스트에 `original_name`으로 보존됩니다.
5. 해당 `20_Sources/` 하위 폴더로 파일을 **이동**합니다.
6. `.llm-wiki/manifest.json`에 `processed: false`로 **등록**합니다.

### 유형과 목적지

| 유형 | 목적지 | 추측을 유발하는 파일명 키워드 |
|---|---|---|
| `paper` | `20_Sources/Papers/` | (기본값) |
| `meeting` | `20_Sources/Meeting-Notes/` | 회의, meeting, minutes |
| `experiment` | `20_Sources/Experiments/` | 실험, experiment |
| `dataset` | `20_Sources/Datasets/` | dataset, 데이터셋 |
| `webclip` | `20_Sources/Web-Clips/` | `.html`, `.url`, "clip" |
| `proposal` | `20_Sources/Proposals/` | 계획서, proposal, 제안서, 별첨 |
| `qa` | `20_Sources/QA-Sessions/` | (`_qa/` 제출물에 자동 지정) |

### 실제로 마주치게 될 경우들

| 상황 | 어떻게 되는가 |
|---|---|
| 같은 파일을 두 번 추가 | 해시로 중복 판정, Inbox에 그대로 두고 등록하지 않음 |
| `20_Sources/`에 이미 있는 이름의 다른 파일 | 보류(절대 덮어쓰지 않음) — 이름을 바꿔 다시 실행 |
| 프롬프트에서 `h`를 누름 | Inbox에 보류 |
| 업로더 폴더가 `members.md`에 없음 | 경고를 남기고 등록은 진행 |
| 파일명에 `[`, `]`, `#`, `^`, `\|`가 있음 | 정규화하고 원래 이름은 매니페스트에 기록 |
| `10_Inbox/_qa/`의 파일 | `qa`로 등록하고, 폴더가 아니라 **파일 안에 적힌 질문자**에게 귀속 |
| `10_Inbox/_requests/`의 파일 | **건너뜀** — 원자료가 아니라 편집 요청입니다 (§12) |

---

<a id="ko-6"></a>

## 6. 위키 편찬 — `compile`

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

### compile이 하는 일

1. `30_Wiki/`를 **백업**합니다(기본값으로 최근 10개 보관).
2. 미처리 원자료를 **한 번에 하나씩**, 순서대로 처리합니다. 한 파일이 실패해도 격리해서 보고하고
   나머지는 계속 진행합니다.
3. 각 원자료마다 프로젝트 컨텍스트(`scope.md`, `glossary.md`), 현재 위키 인덱스(중복 방지용),
   원자료 메타데이터, 문서 템플릿, 그리고 원문 텍스트 또는 그 경로(에이전트형 백엔드는 파일을
   직접 읽습니다)를 담은 프롬프트를 만듭니다.
4. 모델은 문서들의 JSON 배열을 반환합니다. **검증하고 파일로 쓰는 것은 코드**이고,
   모델은 파일 시스템을 건드리지 않습니다.
5. **파일마다** 매니페스트의 원자료를 `processed: true`로 표시하므로, 중간에 끊긴 실행도
   멈춘 지점부터 이어집니다.
6. 대기 중인 편집 요청을 변경 제안으로 전환합니다 (§12).
7. 토큰과 비용을 `.llm-wiki/metrics/costs.jsonl`에 기록합니다.

### 코드가 모델 출력에 강제하는 것

| 모델이 요청한 것 | 코드가 하는 일 |
|---|---|
| `30_Wiki/` 밖에 쓰기 | **차단**, `차단: 30_Wiki 밖 쓰기 시도`로 보고 |
| `status: reviewed` | `draft`로 다시 씀 |
| `reviewed`/`approved` 문서 갱신 | `_Proposals/`의 변경 제안으로 강등 |
| 코멘트가 있는 문서 교체 | 기존 `## Comments` 섹션을 원문 그대로 복원 |

### 산출 문서의 형태

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

두 가지 관례가 중요합니다.

- **쪽 번호는 PDF의 물리적 페이지**입니다(뷰어에서 `#page=N`이 여는 그 페이지). 인쇄된 쪽
  번호는 표지와 앞부속 때문에 어긋나므로 절대 쓰지 않습니다.
- 모델이 원자료에 근거를 대지 못한 문장에는 콜아웃이 붙습니다.

  ```markdown
  > [!warning] Evidence needed
  > No direct evidence was found in the current material.
  ```

### 할 일이 없을 때

```console
$ llm-wiki compile
처리할 자료가 없습니다 (manifest 전부 processed, 대기 중인 편찬 요청도 없음).
```

원자료를 다시 편찬하려면 `.llm-wiki/manifest.json`에서 그 항목의 `processed`를 `false`로
되돌리면 됩니다.

---

<a id="ko-7"></a>

## 7. 문서 생애주기: draft → reviewed → approved

이 시스템의 핵심이므로 이 절은 특히 꼼꼼히 읽으세요.

```
        (compile)              (사람)                   (사람)
 원자료  ────────▶ draft ──────────────▶ reviewed ──────────────▶ approved
                    │                       │
                    │                       ├──▶ disputed    (근거 충돌)
                    └───────────────────────┴──▶ deprecated  (대체됨)
```

| 상태 | 의미 | 누가 지정할 수 있는가 |
|---|---|---|
| `draft` | AI가 작성. 미검증. | AI (그리고 오직 이 상태만) |
| `reviewed` | 사람이 모든 인용을 원문과 대조 확인함. 정확함. | **사람만** |
| `approved` | 확립된 연구실 지식. 논문·제안서에 인용 가능. | **사람만** |
| `disputed` | 근거가 충돌함. 열린 질문. | **사람만** |
| `deprecated` | 대체됐지만 이력으로 보존. | **사람만** |

### 문서를 승격하는 방법

**의도적으로 CLI 명령이 없습니다.** 승격은 사람의 판단이므로 사람의 편집이어야 합니다.
아무 에디터(Obsidian이 편합니다)로 문서를 열고 frontmatter를 바꾸세요.

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

이게 전부입니다. `status`가 `draft`보다 높아지는 순간 코드는 AI가 그 문서를 직접 편집하지
못하게 막고, 그 문서를 바꾸려는 다음 `compile`은 대신 변경 제안을 만듭니다.

### "검토한다"는 게 실제로 뜻하는 것

`reviewed`라고 적기 전에 문서마다 이걸 하세요.

1. `## Sources`의 모든 링크를 엽니다.
2. PDF 인용 `[[...pdf#page=5]]`는 5쪽을 열어 그 주장이 실제로 거기 있는지 확인합니다.
3. 배경지식이 근거 있는 서술과 뒤섞이지 않고 그렇다고 표시돼 있는지 확인합니다.
4. `> [!warning] Evidence needed` 콜아웃을 확인합니다 — 근거를 찾거나, 콜아웃을 그대로 둡니다.

`audit` 명령은 링크 대상과 쪽 범위를 기계적으로 검사하지만(§13), 5쪽이 정말 그 주장을
담고 있는지는 검사할 수 없습니다. 그 부분은 당신 몫입니다.

### 검토가 필요한 것 찾기

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

### reviewed → approved 승격

같은 방식으로 `status: approved`로 바꿉니다. 연구실이 그 내용을 확정된 것으로 다룰 때
쓰세요 — 보통 한 사람의 판단이 아니라 그룹 논의 후입니다. `approved` 문서는 검색과 `ask`에서
가장 먼저 순위에 오릅니다.

### disputed와 deprecated

두 원자료가 진짜로 충돌할 때는 **조용히 승자를 고르지 마세요.** 편찬기는 양쪽을
`## Conflicting evidence`에 기록하도록 지시받습니다. 그다음 `status: disputed`로 설정해
열린 질문임을 드러내세요. 문서가 대체됐을 때는 삭제하지 말고 `deprecated`로 두세요 —
이력은 계속 유용합니다.

---

<a id="ko-8"></a>

## 8. 변경 제안과 `review apply`

### 변경 제안은 어디서 오는가

세 경로가 있고, 모두 `30_Wiki/_Proposals/`에 도착합니다.

1. **compile이 보호된 문서를 갱신하려 했을 때** — 대상이 `reviewed` 이상이라 갱신이 자동으로
   강등됐습니다.
2. **compile이 안전하게 다시 쓸 수 없다고 판단했을 때** — 기존 내용이 확실치 않아 모델이
   `propose`를 선택했습니다.
3. **MCP를 통해 편집 요청이 들어왔을 때** — §12 참조.

### 먼저 제안을 읽으세요

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

### 하나 반영하기

```console
$ llm-wiki review apply "Ankle Stiffness"
✓ 반영 완료: 30_Wiki/Findings/Ankle Stiffness 12 Nm-rad.md (status reviewed 유지)
  확인: llm-wiki diff 20260812-101122 / 되돌리기: llm-wiki rollback 20260812-101122
```

이름 인자는 부분 문자열 매칭입니다. 둘 이상과 매칭되면 추측하지 않고 멈춘 뒤 목록을 보여줍니다.

```console
$ llm-wiki review apply "Ankle"
제안을 특정하지 못했습니다 (매칭 2건). 보유: Ankle Stiffness…-093015.md, Ankle Angle…-101500.md
```

### 전부 반영하기

```console
$ llm-wiki review apply --all
다음 제안 3건을 모두 승인·반영합니다:
  - Ankle Stiffness 12 Nm-rad-20260812-093015.md
  - Gait Phase Estimation-20260812-093015.md
  - Series Elastic Actuator-20260812-093015.md
진행할까요? [y/N]: y

✓ 일괄 반영 3건
```

목록은 항상 확인 프롬프트 **앞에** 출력됩니다 — 보지 않은 것을 승인하는 일은 없습니다.
실패는 격리되고 개수로 집계됩니다.

### 하나 거부하기

```console
$ llm-wiki review reject "Series Elastic" --reason "Superseded by the 2026 revision"
✓ 거부·정리: Series Elastic Actuator-20260812-093015.md (사유: Superseded by the 2026 revision)
```

사유는 파일이 삭제되기 전에 `.llm-wiki/processing-log.md`에 기록됩니다.

### `apply`가 보장하는 것

병합 자체는 LLM이 수행하지만(두 문서를 읽고 합쳐야 하므로), 결과는 코드가 강제합니다.

- `status`와 `reviewer`는 **원본**에서 복원됩니다 — 병합이 문서를 승격시키거나 검토자를
  바꿀 수 없습니다.
- `## Comments` 섹션은 원본에서 원문 그대로 복원됩니다.
- 먼저 백업을 뜹니다. 병합 결과가 유효한 문서가 아니면 원본은 그대로 남습니다.

---

<a id="ko-9"></a>

## 9. 질문하기 — `ask`

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

### 하는 일과 하지 않는 일

- 근거는 **편찬된 위키 문서(`30_Wiki/`)에서만** 나옵니다. 원본 PDF를 다시 읽지 않습니다 —
  그건 편찬이 이미 한 일입니다.
- 모든 문장에 `[n]` 인용이 붙고, 근거 목록은 각 문서의 상태를 보여줍니다. `draft` 인용은
  미검증으로 표시됩니다.
- 답변은 **어디에도 저장되지 않습니다.** `ask`는 위키를 수정할 수 없습니다.
- 질의는 질문자 이름과 함께 `.llm-wiki/metrics/queries.jsonl`에 기록됩니다.

### 옵션

| 플래그 | 효과 |
|---|---|
| `--asker <name>` | 귀속. 없으면 `$LLM_WIKI_ASKER`, 그다음 로그인 계정명 |
| `--top N` | 근거로 쓸 문서 개수 (기본 5) |
| `--no-draft` | `approved`/`reviewed` 문서만 근거로 사용 |
| `--save-qa` | 배경지식 항목을 묻지 않고 저장 |
| `--no-save-qa` | 저장 여부를 묻지 않음 |

매번 이름을 타이핑하는 대신 한 번 설정해 두세요.

```console
$ export LLM_WIKI_ASKER="Jane Kim"      # ~/.zshrc 에 추가
```

### 근거가 없을 때

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

무엇을 거부하는지 보세요. 프로젝트 고유의 수치를 지어내지 않습니다. 근거 0건 답변 자체도
신호입니다 — 그 주제가 아직 편찬되지 않았다는 뜻이니까요.

### 답변을 다시 위키로 넣기

답변에 `## Model background knowledge` 섹션이 있으면, `ask`는 **그 항목들만** 원자료 후보로
저장할지 물어봅니다.

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

**위키에서** 나온 내용은 저장 대상으로 제시되지 않습니다. 의도적입니다. 위키 요약이 "원자료"로
되돌아 들어오면 시스템이 자기 요약을 근거로 인용하는 AI 자기참조 루프가 생기니까요.

저장된 파일은 평범한 경로를 따라갑니다.

```console
$ llm-wiki ingest --yes
  - _qa/2026-08-13-142233-qa.md → 20_Sources/QA-Sessions/2026-08-13-142233-qa.md (qa, Jane Kim)
$ llm-wiki compile
```

---

<a id="ko-10"></a>

## 10. 검색 — `search` / `reindex`

```console
$ llm-wiki search ankle stiffness
[approved] Ankle Stiffness 12 Nm-rad  (30_Wiki/Findings/Ankle Stiffness 12 Nm-rad.md)
    …adopted 12 Nm/rad for [ankle] [stiffness] based on fatigue test round 2…
[draft] Gait Phase Estimation  (30_Wiki/Methods/Gait Phase Estimation.md)
    …the controller holds [stiffness] constant during stance…

$ llm-wiki search ankle stiffness --no-draft    # approved/reviewed 만
```

결과는 `approved` → `reviewed` → `draft` → `disputed` → `deprecated` 순으로 정렬됩니다.

문서가 바뀌면 인덱스는 스스로 다시 만들어지므로, `reindex`는 인덱스가 손상됐을 때만 씁니다.

```console
$ llm-wiki reindex
✓ 인덱스 재구축 완료 (.llm-wiki/index/fts.sqlite)
```

**자연어 질문도 동작합니다.** 검색 전에 두 언어 모두 정규화됩니다 — 한국어는 조사와 어미를,
영어는 복수형과 시제를 떼어 내고, 그 어간을 접두사 질의로 보냅니다. 그래서 `actuators`가
`actuator`를 찾고, `제어기를 왜 바꿨나요?`가 `제어기 교체`를 담은 문서를 찾습니다.

---

<a id="ko-11"></a>

## 11. 코멘트

`## Comments` 섹션은 각 문서에 붙는 연구자 노트입니다. 규칙은 둘입니다.

- **편찬기는 절대 편집하지 않고**, 근거로도 쓰지 않습니다.
- 갱신과 제안 병합을 거쳐도 **원문 그대로 보존됩니다.**

### 직접 쓰기

문서를 열고 이 형식으로 한 줄 추가하세요.

```markdown
## Comments

- 2026-08-13 **Jane Kim**: Round 3 is scheduled for 8/20; this number may change.
- 2026-08-14 **Pilwon Hur**: Agreed. Keep as reviewed until then.
```

날짜와 굵은 이름 형식이 중요합니다 — `audit`이 이 형식에 맞지 않는 줄을 지적하므로,
귀속이 기계적으로 검증 가능한 상태로 유지됩니다.

### 어시스턴트를 통해 (MCP)

> *"발목 강성 문서에 3차 시험에서 값이 바뀔 수 있다고 코멘트 남겨줘."*

어시스턴트가 `wiki_add_comment`를 호출하고, 이는 기존 섹션에 덧붙입니다(없을 때만 새로
만듭니다). 본문은 건드리지 않습니다.

### 코멘트는 위키를 바꾸지 않는다

코멘트는 기록이지 요청이 아닙니다. 내용을 바꾸고 싶다면 편집 요청(§12)을 쓰거나 직접
문서를 고치세요. 템플릿에 나오는 `#반영요청` 태그는 에이전트가 알아채라고 만든 관례일 뿐,
현재 **어떤 명령도 처리하지 않습니다.**

---

<a id="ko-12"></a>

## 12. 어시스턴트가 보내는 편집 요청

외부 어시스턴트는 위키를 편집할 수 없습니다. 요청만 접수할 수 있고, 그 요청은 끝에 사람이
있는 정해진 경로를 따라갑니다.

```
어시스턴트 → 10_Inbox/_requests/ → compile → 30_Wiki/_Proposals/ → 당신: review apply → 문서
```

### 요청 접수

> *"발목 강성 문서에 그 값이 피로시험 2차에서 나온 거라고 적혀야 해. 편집 요청으로 넣어줘."*

```
요청 접수: 10_Inbox/_requests/2026-08-13-113000-요청.md — 다음 compile에서 처리됩니다.
```

### 요청 전환

```console
$ llm-wiki compile
✓ 백업 20260813-114500 | 편찬 요청 1건

✓ 편찬 완료 — 산출 1건, 실패 0건, 토큰 in 0 / out 0
  편찬 요청: 제안 전환 1건
  - 요청→제안: 2026-08-13-113000-요청.md → 30_Wiki/_Proposals/Ankle Stiffness 12 Nm-rad-20260813-114500.md (Jane Kim)
```

`토큰 in 0 / out 0`을 보세요 — 요청을 제안으로 전환하는 것은 결정론적이고 비용이 들지
않습니다. LLM 백엔드가 전혀 설정돼 있지 않아도, 미처리 원자료가 하나도 없어도 동작합니다.

원래 요청은 `90_Archive/_requests/`로 옮겨져 두 번 처리되지 않습니다.

### 대상 문서가 없을 때

```console
  편찬 요청: 제안 전환 0건, 보류 1건
  보류 요청은 10_Inbox/_requests/ 에 남습니다 — 대상 경로를 고치거나 파일을 지우세요.
  - 요청 보류: 2026-08-13-113500-요청.md — 대상 문서를 찾지 못함 (30_Wiki/Concepts/Nonexistent.md)
```

요청은 `30_Wiki/` 안에 **이미 있는** 문서만 대상으로 삼을 수 있습니다. 요청으로 새 문서를
만들 수는 없습니다 — 그럴 때는 원자료를 Inbox에 넣으세요.

---

<a id="ko-13"></a>

## 13. 품질 감사 — `audit`

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

감사는 **보고만** 합니다. 문서를 절대 수정하지 않습니다.

| 검사 항목 | 의미 | 해야 할 일 |
|---|---|---|
| 깨진 wikilink | `[[link]]`가 존재하지 않는 파일을 가리킴 | 링크를 고치거나, 없는 문서를 편찬 |
| 페이지 범위 초과 인용 | `#page=N`이 PDF 쪽 수를 초과 | 인용이 틀렸습니다 — 확인해서 정정 |
| 출처 없는 문서 | 위키링크가 있는 `## Sources` 섹션이 없음 | 근거가 없는 문서입니다. 조사하세요 |
| status 이상 | `status`가 다섯 유효 값 중 하나가 아님 | frontmatter 오타 |
| 장기 방치 draft | `review.stale_draft_days`(기본 14)보다 오래된 draft | 검토하거나 폐기 |
| 코멘트 형식 오류 | `- YYYY-MM-DD **Name**:` 형식이 아닌 코멘트 줄 | 귀속을 검증 가능하게 형식을 고치세요 |
| 동기화 충돌 사본 | Dropbox/iCloud "conflicted copy" 파일 | 병합하고 사본을 삭제 |
| manifest 원자료 불일치 | 등록된 원자료 파일이 디스크에 없음 | 복원하거나 매니페스트를 수정 |
| 규칙 파일 이중화 | `CLAUDE.md`가 import 한 줄 대신 규칙을 담고 있음 | 내용을 `AGENTS.md`로 옮기세요 |

리포트는 아직 `Evidence needed` 콜아웃을 달고 있는 문서도 나열합니다. 그건 **오류가 아니라**
원자료를 기다리는 문장 표시입니다.

macOS에서는 PDF 쪽 수를 Spotlight에서 자동으로 가져옵니다. Windows와 Linux에서는 이 검사를
쓰려면 `pypdf`를 한 번 주입하세요: `pipx inject llm-wiki pypdf`.

주 1회 정도가 적당합니다.

```cron
0 4 * * 0  cd /path/Project-Exo && llm-wiki audit
```

---

<a id="ko-14"></a>

## 14. 되돌리기: `diff`, `rollback`, 백업

모든 `compile`과 모든 `review apply`는 먼저 `30_Wiki/`를 백업합니다.

```console
$ llm-wiki diff                       # 가장 최근 실행
기준: 백업 20260813-114500
  추가: 30_Wiki/Concepts/Adaptive Impedance Control.md
  변경: 30_Wiki/Findings/Ankle Stiffness 12 Nm-rad.md

$ llm-wiki diff 20260813-114500 -v    # 줄 단위 차이까지
$ llm-wiki rollback 20260813-114500   # 그 시점으로 복원
✓ 20260813-114500 시점으로 복원 완료 (직전 상태도 백업해 두었습니다)
```

rollback 자체도 먼저 백업을 뜨므로, 실수로 한 rollback도 되돌릴 수 있습니다. 기본적으로
최근 10회분이 보관됩니다(`snapshot.backup_keep`).

**Git은 필요 없습니다.** 설정에 `git.enabled` 키가 있지만 이는 향후 Git 모드를 위한
자리이고, 오늘 `llm-wiki git` 명령은 없습니다 — 내장 백업이 그 역할을 합니다.

---

<a id="ko-15"></a>

## 15. 알림 — `notify`

```console
$ llm-wiki notify --dry-run
[Project-Exo] 검토 대기 5건
- draft 3건, 변경 제안 1건, Q&A 제출 1건

$ llm-wiki notify
```

draft, 변경 제안, disputed 문서, 대기 중인 Q&A 제출물, 대기 중인 편집 요청을 셉니다.
**합계가 0이면 아무것도 보내지 않습니다** — 매일 "이상 없음" 소음이 쌓이지 않습니다.

채널은 `.llm-wiki/config.yaml`에서 설정합니다.

```yaml
notifications:
  macos: true                      # macOS 알림 (기본 켜짐, macOS 전용)
  webhook: https://hooks.slack.com/services/XXX/YYY/ZZZ
  email_to: jane@gist.ac.kr
  smtp_host: smtp.gmail.com
  smtp_port: 587
  smtp_from: lab-wiki@gist.ac.kr
  smtp_user: lab-wiki@gist.ac.kr
  smtp_pass: "app-password"
```

전형적인 야간 배치는 이렇습니다.

```cron
0 3 * * *  cd /path/Project-Exo && llm-wiki ingest --yes && llm-wiki compile && llm-wiki notify
```

---

<a id="ko-16"></a>

## 16. 에이전트 CLI와 함께 쓰기

앞 절의 모든 작업은 Claude Code, Codex, Antigravity에서 대화로 할 수 있습니다. 이 절은
그런 세션이 실제로 어떻게 보이는지를 보여줍니다.

### 16.1 슬래시 명령의 정체

`/wiki-compile`은 **MCP가 아닙니다.** 에이전트에게 `llm-wiki` CLI를 실행하라고 지시하는
프롬프트 파일입니다. 결과는 직접 명령을 치는 것과 동일하고, 코드 수준의 모든 안전장치가
그대로 적용됩니다. 에이전트의 몫은 그 주변의 대화입니다 — 결과를 설명하고, 다음에 뭘 할지
정하고, 원래 당신이 손으로 했을 읽기 작업을 대신 해 주는 것.

| 에이전트 | 규칙 (AGENTS.md) | 자연어 | `/wiki-*` 명령 | `/wiki-init` (새 폴더용) |
|---|---|---|---|---|
| Claude Code | 즉시 (`CLAUDE.md`가 import) | 즉시 | 즉시 (`init`이 설치한 `.claude/skills/`) | `llm-wiki setup-agent claude` |
| Codex | 즉시 | 즉시 | `llm-wiki setup-agent codex` | 그 명령에 포함됨 |
| Antigravity (`agy`) | 즉시 | 즉시 | 즉시 (`init`이 설치한 `.agents/skills/`) | `llm-wiki setup-agent agy` |

`init`이 설치하는 프로젝트 명령은 넷입니다: `/wiki-ingest`, `/wiki-compile`, `/wiki-audit`,
`/wiki-ask`. `/wiki-init`이 전역인 이유는 새 폴더에는 아직 프로젝트 스킬이 없기 때문입니다.

```console
$ llm-wiki setup-agent claude     # 또는: codex / agy / all — 머신당 한 번
✓ Claude Code: 전역 /wiki-init 스킬 → ~/.claude/skills/wiki-init
설치는 컴퓨터당 1회면 충분합니다. 업데이트 후에는 다시 실행하면 갱신됩니다.
```

### 16.2 세션 시작하기

Claude Code에 한 번 로그인한 뒤(`claude`가 안내합니다) 프로젝트 폴더를 엽니다.

```console
$ cd ~/research/Project-Exo
$ claude
```

에이전트는 시작할 때 `CLAUDE.md`(`AGENTS.md`를 import하는 한 줄)를 읽으므로, 프로젝트
규칙을 이미 알고 있습니다 — 원자료는 건드릴 수 없고, `draft`만 쓸 수 있고, reviewed 문서는
제안으로 처리하고, 코멘트 섹션은 금지 구역이며, 프로젝트 폴더를 벗어나면 안 된다는 것.

먼저 상황 파악을 시켜 보세요.

```
> 이 프로젝트 지금 상태가 어때?

프로젝트 상태를 확인하겠습니다.

  llm-wiki status

프로젝트: Adaptive exoskeleton control for hemiplegic gait
원자료: 4건 (미처리 2건)
Wiki: draft 5, reviewed 4
제안 대기: 1건 / 백업: 3회분

정리하면 이렇습니다.

- **편찬 대기 중인 원자료 2건** — ingest는 됐지만 아직 `compile`이 실행되지 않았습니다
- **검토가 필요한 draft 5건**, 이미 검토된 문서는 4건입니다
- **승인 대기 중인 변경 제안 1건** — compile이 reviewed 문서를 바꾸려다 막혀서
  대신 제안을 낸 것입니다

대기 중인 원자료 2건을 먼저 편찬할까요, 아니면 제안부터 볼까요?
```

### 16.3 네 개의 프로젝트 명령

**`/wiki-ingest`** — 자료 접수:

```
> /wiki-ingest

  llm-wiki ingest --yes

✓ 등록 2 / 중복 1 / 보류 0
  - Jane Kim/kim2026_adaptive_gait.pdf → 20_Sources/Papers/kim2026_adaptive_gait.pdf (paper, Jane Kim)
  - Jane Kim/meeting_2026-08-19.md → 20_Sources/Meeting-Notes/meeting_2026-08-19.md (meeting, Jane Kim)
  중복(미이동): Jane Kim/lee2025_sea_design.pdf (기존: 20_Sources/Papers/lee2025_sea_design.pdf)

2건을 등록했고 둘 다 Jane Kim에게 귀속됐습니다.

중복이 하나 있습니다. `lee2025_sea_design.pdf`는 이미 위키에 있어서(파일명이 아니라 해시로
매칭됩니다) 두 번 등록하지 않고 Inbox에 그대로 뒀습니다. 그 사본은 지워도 됩니다.

다음 단계는 `/wiki-compile`로 새 원자료 2건을 위키 문서로 만드는 것입니다.
```

**`/wiki-compile`** — 편찬:

```
> /wiki-compile

  llm-wiki compile

✓ 백업 20260819-140322 | 백엔드 oauth-anthropic/claude-opus-5 | 대상 2건
  · kim2026_adaptive_gait.pdf 편찬 중...
  · meeting_2026-08-19.md 편찬 중...

✓ 편찬 완료 — 산출 4건, 실패 0건, 토큰 in 52104 / out 11233 / $0.5240
  - 생성: 30_Wiki/Concepts/Adaptive Impedance Control.md
  - 생성: 30_Wiki/Findings/Carbon Patella Support.md
  - 갱신: 30_Wiki/Methods/Gait Phase Estimation.md
  - 제안: 30_Wiki/_Proposals/Series Elastic Actuator-20260819-140322.md

두 원자료를 $0.52에 편찬했습니다. 알아 두실 게 셋 있습니다.

1. **새 문서 2건**이 논문과 회의록에서 나왔습니다.
2. **`Gait Phase Estimation`은 제자리에서 갱신됐습니다** — 아직 `draft`라서 편찬기가
   직접 편집할 수 있었습니다.
3. **`Series Elastic Actuator`는 편집 대신 제안이 나왔습니다.** 그 문서는 `reviewed`라
   편찬기가 손댈 수 없습니다. 제안이 당신을 기다리고 있습니다.

이 모든 작업 전에 백업(`20260819-140322`)을 떴으므로,
`llm-wiki rollback 20260819-140322`로 전체 실행을 되돌릴 수 있습니다.
```

**`/wiki-audit`** — 품질 점검:

```
> /wiki-audit

  llm-wiki audit

✓ 감사 완료 — 발견 2건 (리포트: .llm-wiki/audit/2026-08-19-1412.md)
  [깨진 wikilink] 1건
    - Concepts/Adaptive Impedance Control.md → [[Gait Phase Estimator]]
  [페이지 범위 초과 인용] 1건
    - Findings/Carbon Patella Support.md → kim2026_adaptive_gait.pdf#page=48 (총 32쪽)

두 건인데 성격이 다릅니다.

**깨진 링크는 표기 문제입니다.** 문서는 `[[Gait Phase Estimator]]`를 링크했지만 실제 문서명은
`Gait Phase Estimation`입니다. 이건 제가 고쳐도 됩니다 — 어떤 주장도 바뀌지 않으니까요.

**쪽 인용은 진짜 문제입니다.** 32쪽짜리 PDF의 48쪽을 인용했다는 건 인용이 틀렸고 그 뒤의
주장이 미검증이라는 뜻입니다. 논문을 열어 실제 쪽을 찾는 건 당신이 해야 합니다 — 어느 쪽을
가리키려 했는지 제가 추측해선 안 됩니다.

링크는 제가 고치고 인용은 남겨 둘까요?
```

**`/wiki-ask`** — 근거 기반 질문:

```
> /wiki-ask 슬개골 지지대에 왜 카본을 골랐지?

  llm-wiki ask "슬개골 지지대에 왜 카본을 골랐지?" --asker "Jane Kim"

근거 1건 · 백엔드 oauth-anthropic/claude-opus-5

피로시험 2차에서 알루미늄 설계 대비 수명이 1.8배로 나와 카본 파이버를 채택했습니다 [1] (draft).

근거
  [1] 30_Wiki/Findings/Carbon Patella Support.md  (draft)
  ! draft 근거가 포함됐습니다 — 미검토 내용입니다.

이 답변은 **draft** 문서에 기대고 있습니다. 8/19 회의록에서 편찬됐지만 아직 사람이 원문과
대조하지 않았습니다. 누군가 그 문서를 검토하기 전까지 1.8배라는 수치는 미확정으로 다루세요.
```

### 16.4 전체 검토 세션

검토는 에이전트가 값을 하는 지점입니다 — 인용된 쪽을 전부 열어 대조해 주는데, 그게 draft를
`reviewed`로 승격시킬 때 가장 고된 부분이니까요.

```
> draft들을 검토하고 싶어. 가장 최근 것부터 시작해서 근거를 하나씩 짚어줘.

  llm-wiki review

검토 대기 draft 5건 (오래된 순): ...

`Findings/Carbon Patella Support.md`(오늘 생성)부터 보겠습니다. 문서와 인용된 원자료를
읽습니다.

  Read 30_Wiki/Findings/Carbon Patella Support.md
  Read 20_Sources/Meeting-Notes/meeting_2026-08-19.md

주장별로 대조한 결과입니다.

| 문서의 주장 | 인용된 원자료 | 판정 |
|---|---|---|
| 슬개골 지지대를 알루미늄 → 카본으로 변경 | 8/19 회의록, "Decisions" | ✓ 그대로 명시됨 |
| 알루미늄 대비 피로수명 1.8배 | 8/19 회의록, "Decisions" | ✓ 그대로 명시됨 |
| 피로시험 2차 | 8/19 회의록 | ✓ 명시됨 |
| "전반적인 내구성과 신뢰성을 향상시킨다" | — | ⚠ 원자료에 없음 |

앞의 셋은 확실합니다. 마지막 문장은 편찬기가 덧붙인 추론입니다 — 그럴듯하지만 회의록이 한
말은 아닙니다. 선택지는 둘입니다. 그 문장을 지우거나, 남기되 배경지식으로 표시하거나.

> 지워줘. 그리고 내 이름으로 reviewed 표시해줘.

근거 없는 문장을 지우겠습니다. 상태는 제가 직접 바꿀 수 없습니다 — `reviewed`는 사람 전용이고
코드가 제 요청을 거부합니다 — 그래서 편집만 하고 바꿔야 할 frontmatter를 정확히 보여 드리겠습니다.

  Edit 30_Wiki/Findings/Carbon Patella Support.md

삭제함: "This change improves overall durability and reliability of the assembly."

이제 frontmatter를 직접 바꾸세요 (세 줄):

  status: draft      →  status: reviewed
  reviewer:          →  reviewer: Jane Kim
  updated: 2026-08-19 →  updated: 2026-08-19

에디터에서 여시거나, 말씀하시면 제가 그 편집까지 하겠습니다 — 다만 제가 할 때도 기록되는
판단은 제 것이 아니라 당신 것이라는 점을 알고 계세요.
```

마지막 대화가 이 설계 전체의 핵심입니다. 에이전트는 그 편집을 *할 수* 있습니다 — 파일 접근
권한이 있으니까요. 하지만 시스템은 승격이 사람의 행위가 되도록 만들어져 있습니다. 에이전트에게
근거를 모으고 변경을 준비하게 하되, 결정은 당신이 하세요.

### 16.5 변경 제안을 대화로 처리하기

```
> 제안이 하나 대기 중이던데, 뭘 바꾸자는 거야?

  Read 30_Wiki/_Proposals/Series Elastic Actuator-20260819-140322.md

제안 대상은 `30_Wiki/Concepts/Series Elastic Actuator.md`이고 현재 `reviewed` 상태입니다.
출처는 8/19 회의록입니다.

**제안 내용**: SEA 스프링 상수를 2차에서 4.2 kN/m로 재측정했다는 사실을 추가하고, 문서에 있는
3.8 kN/m 값을 대체하자는 것입니다.

**왜 편집이 아니라 제안인가**: 대상이 `reviewed`라서 편찬기가 직접 편집할 수 없습니다.
규칙 3입니다.

reviewed 문서의 수치를 바꾸는 건이니 승인 전에 회의록을 확인하시길 권합니다.

  Read 20_Sources/Meeting-Notes/meeting_2026-08-19.md

확인했습니다 — 회의록에 "spring constant re-measured: 4.2 kN/m (round 2, replaces 3.8)"이라고
적혀 있습니다. 제안은 원자료에 충실합니다.

> 반영해줘

  llm-wiki review apply "Series Elastic"

✓ 반영 완료: 30_Wiki/Concepts/Series Elastic Actuator.md (status reviewed 유지)
  확인: llm-wiki diff 20260819-142905 / 되돌리기: llm-wiki rollback 20260819-142905

반영됐습니다. 문서는 `status: reviewed`와 원래 검토자를 유지했습니다 — 병합은 문서를 승격하거나
강등할 수 없고, 코멘트 섹션도 그대로 넘어왔습니다.

병합이 잘못됐다면 `llm-wiki rollback 20260819-142905`로 복원됩니다.
```

### 16.6 자연어, 그리고 무엇이 다른가

에이전트는 슬래시 명령 없이도 동작합니다.

```
> 인박스에 새 논문 두 편 있어. 처리하고, 기존 내용과 충돌하는 게 있으면 알려줘.
```

괜찮은 에이전트라면 `llm-wiki ingest`, `llm-wiki compile`을 차례로 실행한 뒤 새 문서를 기존
문서와 대조해 충돌을 보고할 것입니다. 그건 CLI 혼자서는 못 하는 일이 맞습니다.

다만 반드시 이해해야 할 차이가 하나 있습니다.

| 당신이 입력한 것 | 실제로 실행되는 것 | 무엇이 강제하는가 |
|---|---|---|
| `/wiki-compile` | `llm-wiki compile` | **코드** — 락, 백업, 경로 허용목록, draft 강제, 코멘트 보존 |
| "인박스 처리하고 편찬해줘" | 에이전트가 CLI를 실행할 *수도* 있고, 직접 파일을 편집할 수도 있음 | `AGENTS.md` — **프롬프트 수준만** |

`.llm-wiki/workflows/*.md` 파일이 있는 이유는 CLI가 설치돼 있지 않을 때 에이전트가 파이프라인을
손으로 수행할 수 있게 하기 위함입니다. 에이전트가 파일을 직접 편집할 수 있는 것도 그래서입니다.
그렇게 할 때는 코드 수준 보장이 적용되지 않고, `AGENTS.md`의 규칙만 남습니다 — 그건 지시이지
강제가 아닙니다.

**그러니 보장된 경로를 원한다면 명령 이름을 말하세요.** *"`llm-wiki compile` 실행해줘"*는
모호하지 않고, *"위키 편찬해줘"*는 모호합니다. 스킬은 CLI를 우선하도록 작성돼 있고
(*"llm-wiki CLI가 설치돼 있으면 절차를 수행하지 말고 그것을 실행하라"*), 그래서 슬래시
명령이 더 안전한 습관입니다.

### 16.7 Codex와 Antigravity

같은 모델, 같은 명령, 설치 단계만 다릅니다.

```console
# Codex — 프롬프트를 한 번 설치하면 어디서든 쓸 수 있습니다
$ llm-wiki setup-agent codex
✓ Codex: /wiki-ask /wiki-audit /wiki-compile /wiki-ingest /wiki-init 프롬프트 → ~/.codex/prompts

$ cd Project-Exo && codex
> /wiki-compile
```

```console
# Antigravity — 프로젝트 스킬은 init이 설치하고, 전역 스킬은 한 번만
$ llm-wiki setup-agent agy
✓ Antigravity(agy): /wiki-ask /wiki-audit /wiki-compile /wiki-ingest /wiki-init 스킬
  → ~/.gemini/antigravity-cli/skills

$ cd Project-Exo && agy
> /wiki-compile
```

셋 다 `AGENTS.md`를 직접 읽습니다 — 그 파일이 규칙의 단일 진실 원천이고, `CLAUDE.md`는 그것을
가리키는 import 한 줄일 뿐입니다. 규칙은 `AGENTS.md`에서만 고치세요.

### 16.8 대화로 프로젝트 만들기

새 폴더에는 아직 프로젝트 스킬이 없고, 그래서 `/wiki-init`은 전역으로 설치됩니다.

```console
$ mkdir Project-Neuro && cd Project-Neuro && claude
```

```
> /wiki-init

여기에 llm-wiki 프로젝트를 설정하겠습니다. 먼저 몇 가지 여쭙겠습니다.

1. 프로젝트 정식 명칭은?
2. 한 줄 목적은?
3. 구성원은? (쉼표 구분)
4. Wiki reviewer는 누구인가요?
5. 출력 언어 — 한국어인가요, 영어인가요?
6. 민감한 자료가 있나요(IRB, 산학 NDA)? 있다면 로컬 LLM만 쓰도록 잠그겠습니다.
7. 어떤 모델로 편찬할까요?

> Neural correlates of gait adaptation / 분리형 트레드밀 보행 중 피질 활동 연구 /
> Pilwon Hur, Daehak Lee / Daehak Lee / 영어 / 민감하지 않음 / claude-opus-5

  llm-wiki init --yes
  ... 이후 답변을 config.yaml, 00_Project/, 구성원 폴더에 반영합니다

✓ 프로젝트를 만들었습니다. 구조: 00_Project부터 90_Archive까지, .llm-wiki/(설정, 매니페스트,
workflows, 백업), AGENTS.md + CLAUDE.md, 스킬 어댑터, 그리고 Pilwon Hur와 Daehak Lee의
Inbox 폴더.

자료를 넣기 전에 해 두면 좋은 두 가지입니다.
- `00_Project/scope.md`를 채우세요 — 편찬기가 관련성을 판단할 때 읽습니다
- `00_Project/glossary.md`를 채우세요 — 같은 개념이 다른 이름으로 두 번 등록되는 걸 막습니다

그다음 `10_Inbox/<본인 이름>/`에 파일을 넣고 `/wiki-ingest`를 실행하세요.
```

전역 스킬이 없어도 그냥 *"여기에 위키 프로젝트 세팅해줘"* 라고 하면 됩니다 — 에이전트가 같은
온보딩을 대화로 진행합니다.

### 16.9 헤드리스와 배치

슬래시 명령은 비대화형으로도 동작하므로 cron에서 쓸 수 있습니다.

```console
$ claude -p "/wiki-compile"
$ codex exec "/wiki-compile"
$ agy -p "/wiki-compile"
```

무인 배치라면 순수 CLI를 권합니다 — 더 빠르고, 더 싸고, 중간에서 즉흥적으로 판단할 에이전트가
없습니다.

```cron
0 3 * * *  cd /path/Project-Exo && llm-wiki ingest --yes && llm-wiki compile && llm-wiki notify
```

판단이 필요할 때(검토, 충돌 확인, 설명) 에이전트를 쓰고, 결정론적 파이프라인이 필요할 때
CLI를 쓰세요.

<a id="ko-17"></a>

## 17. MCP로 연결하기

MCP는 **읽고 제출하되 절대 쓰지는 못하게** 해야 할 어시스턴트를 위한 통로입니다. 학생,
공동연구자, 또는 파일 시스템 접근권을 주고 싶지 않은 모든 어시스턴트에게 맞는 선택입니다.

### 등록

**Claude Code** — 프로젝트 폴더 안에서 실행하세요. 기본 스코프가 `local`이라 서버가 그
프로젝트에서만 보입니다.

```console
$ cd Project-Exo
$ claude mcp add llm-wiki -- llm-wiki serve-mcp
```

**Antigravity** — 프로젝트 루트에 `.agents/mcp_config.json`을 만듭니다.

```json
{"mcpServers": {"llm-wiki": {"command": "llm-wiki", "args": ["serve-mcp"]}}}
```

**Codex** — `~/.codex/config.toml` (전역만 가능하므로 `--project`를 넘기세요).

```toml
[mcp_servers.llm-wiki]
command = "llm-wiki"
args = ["serve-mcp", "--project", "/absolute/path/Project-Exo"]
```

> **여러 프로젝트를 관리할 때.** Claude Code(`local` 스코프)와 Antigravity
> (`.agents/mcp_config.json`)는 서버를 프로젝트별로 격리하므로 한 세션에 하나만 보입니다.
> Codex는 전역 설정만 있어서, 등록한 프로젝트마다 같은 도구 7개가 복사됩니다(각 ~660 토큰,
> 게다가 `wiki_search` 이름이 중복돼 모델이 구분해야 합니다). Codex에서는 실제로 질의하는
> 프로젝트만 등록하세요.

### 일곱 개의 도구

| 도구 | 하는 일 | 쓰기 권한 |
|---|---|---|
| `wiki_search` | 전문 검색. 질의를 질문자 실명과 함께 기록 | — |
| `wiki_read` | 문서 읽기 (`30_Wiki`만) | — |
| `wiki_status` | 프로젝트 요약 | — |
| `wiki_request_edit` | 편집 요청 접수 → `_requests/` → compile → 제안 → 당신의 승인 | 요청만 |
| `wiki_save_qa` | 동의된 신규 정보 제출 → `_qa/` (웹 항목은 URL 필수) | 제출만 |
| `wiki_add_comment` | 코멘트 덧붙이기 | 덧붙이기만 |
| `wiki_activity` | 구성원별 활동 요약 | — |

**위키 내용을 편집하는 도구는 없습니다.** 누락이 아니라 설계입니다.

### 대화 예시

> *"보행 위상 추정에 대해 우리가 아는 걸 위키에서 찾아줘."*
> → `wiki_search`, 당신의 질의로 기록됨

> *"발목 강성 문서를 읽고 열린 질문들을 요약해줘."*
> → `wiki_search` + `wiki_read`

> *"그 수치는 2차 시험에서 나왔다는 걸 명시해야 해 — 편집 요청 넣어줘."*
> → `wiki_request_edit` → 다음 `compile`에서 제안으로 나타남

> *"우리 결과와 배치되는 2026년 벤치마크 논문을 온라인에서 찾았어. 관련 부분을 원자료로
> 저장해줘."*
> → `wiki_save_qa` — **웹 항목은 URL이 없으면 거부됩니다**

> *"3차 시험이 예정돼 있다고 코멘트 남겨줘."*
> → `wiki_add_comment`

> *"이번 달에 누가 가장 많이 올리고 가장 많이 질문했어?"*
> → `wiki_activity`

---

<a id="ko-18"></a>

## 18. 출력 언어 (영어 / 한국어)

`init` 때 `ko` 또는 `en`을 고릅니다. 이 선택은 문서 본문뿐 아니라 **섹션 제목**까지
결정합니다.

| 언어 | 템플릿 | 섹션 제목 |
|---|---|---|
| `ko` | `wiki-doc.ko.md` | `## 요약` `## 근거` `## 코멘트` |
| `en` | `wiki-doc.en.md` | `## Summary` `## Sources` `## Comments` |

섹션 제목은 사람이 읽는 산문이면서 **코드가 쓰는 스키마**이기도 합니다 — 코멘트 보존,
출처 누락 검사, Q&A 귀속, 요청 파싱이 모두 이 제목을 기준으로 동작합니다. 쓰기는 설정된
언어를 따르지만 파싱은 두 언어를 모두 받아들이므로, 언어가 섞인 프로젝트에서도 안전장치가
조용히 사라지는 일은 없습니다.

검색은 설정과 무관하게 두 언어를 모두 처리하므로 이중 언어 위키도 잘 동작합니다.

**언어는 프로젝트를 만들 때 정하고 그대로 유지하세요.** 나중에 바꿔도 고장 나지는 않지만,
두 언어의 문서가 나란히 남게 됩니다.

---

<a id="ko-19"></a>

## 19. 전체 시나리오 예제

현실적인 한 주를 처음부터 끝까지.

### 월요일 — 설정

```console
$ mkdir Project-Exo && cd Project-Exo
$ llm-wiki init
  ... 명칭, 목적, 구성원: Pilwon Hur, Jane Kim / reviewer: Jane Kim
  ... 언어: en / 외부 LLM: y / 모델: claude-opus-5

$ $EDITOR 00_Project/scope.md      # 연구 질문, 범위 안/밖
$ $EDITOR 00_Project/glossary.md   # 선호 용어
```

### 월요일 — 첫 자료

```console
$ cp ~/Downloads/kim2026_adaptive_gait.pdf "10_Inbox/Jane Kim/"
$ cp ~/Downloads/lee2025_sea_design.pdf    "10_Inbox/Jane Kim/"
$ llm-wiki ingest --yes
✓ 등록 2 / 중복 0 / 보류 0

$ llm-wiki compile
✓ 백업 20260817-101500 | 백엔드 oauth-anthropic/claude-opus-5 | 대상 2건
✓ 편찬 완료 — 산출 6건, 실패 0건, 토큰 in 51203 / out 10422 / $0.5133
```

### 화요일 — 검토

```console
$ llm-wiki review
검토 대기 draft 6건 (오래된 순): ...
```

문서를 하나씩 열고 `## Sources`의 링크를 모두 따라가 주장을 확인합니다. 두 건은 정확합니다.

```diff
-status: draft
-reviewer:
+status: reviewed
+reviewer: Jane Kim
```

한 건은 12쪽을 인용했는데 주장은 14쪽에 있습니다 — 인용을 고친 뒤 reviewed로 표시합니다.
한 건은 논문 어디에서도 찾을 수 없는 주장을 담고 있습니다 — `draft`로 두고 코멘트를 답니다.

```markdown
## Comments

- 2026-08-18 **Jane Kim**: Cannot locate the 40% figure in the source. Holding as draft.
```

### 수요일 — 회의

```console
$ cp meeting_2026-08-19.md "10_Inbox/Pilwon Hur/"
$ llm-wiki ingest --yes && llm-wiki compile
✓ 편찬 완료 — 산출 3건, 실패 0건
  - 생성: 30_Wiki/Findings/Carbon Patella Support.md
  - 제안: 30_Wiki/_Proposals/Series Elastic Actuator-20260819-140000.md
```

`Series Elastic Actuator`가 이미 `reviewed`라서 제안이 나왔습니다 — 편찬기가 직접 편집할 수
없었으니까요.

```console
$ cat "30_Wiki/_Proposals/Series Elastic Actuator-20260819-140000.md"
$ llm-wiki review apply "Series Elastic"
✓ 반영 완료 (status reviewed 유지)
```

### 목요일 — 질문

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

새로 온 학생이 위키가 다루지 않는 것을 묻습니다.

```console
$ llm-wiki ask "What are typical failure modes of carbon layups under cyclic load?" --asker "Daehak Lee"
Wiki 근거 0건 — 배경지식만으로 답합니다
...
  저장할까요? [y/N] Delamination is the dominant failure mode in cyclic loading of laminates…
  > y
✓ 1건 저장: 10_Inbox/_qa/2026-08-20-160212-qa.md
```

근거 0건 답변은 지식 공백 신호입니다. 그 주제에는 원자료가 필요합니다.

### 금요일 — 감사하고 고리 닫기

```console
$ llm-wiki ingest --yes            # Q&A 제출물을 가져옵니다
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

### 이후 — approved로 승격

발목 강성 발견이 확정됐다고 그룹이 합의한 뒤:

```diff
-status: reviewed
+status: approved
```

이제 `search`와 `ask`에서 가장 먼저 순위에 오르고, 제안서에 인용할 수 있습니다.

---

<a id="ko-20"></a>

## 20. 명령어 레퍼런스

| 명령 | 용도 | LLM 필요 |
|---|---|---|
| `init [path] [--yes]` | 프로젝트 생성 + 온보딩 (멱등적) | 아니오 |
| `ingest [--yes]` | Inbox 접수: 해시, 중복, 정규화, 분류, 등록 | 아니오 |
| `compile` | 위키 편찬. 대기 중인 편집 요청도 전환 | 예 (요청만 있으면 불필요) |
| `review` | 검토 대기 목록 표시 | 아니오 |
| `review apply <name>` / `--all` | 제안 승인·병합 | 예 |
| `review reject <name> --reason <text>` | 제안 거부, 사유 기록 | 아니오 |
| `ask <question> [--asker N] [--top N] [--no-draft] [--save-qa\|--no-save-qa]` | 위키 근거 기반 Q&A | 예 |
| `search <query> [--no-draft]` | 전문 검색 | 아니오 |
| `reindex` | 검색 인덱스 재구축 | 아니오 |
| `audit` | 품질 감사 리포트 (보고 전용) | 아니오 |
| `status` | 프로젝트 요약 | 아니오 |
| `diff [run-id] [-v]` | 백업 대비 변경점 | 아니오 |
| `rollback [run-id]` | 백업 복원 | 아니오 |
| `models use [model] [--role R] [--global]` | 모델 선택 | 아니오 |
| `models show` | 현재 설정과 사용 가능 인증 경로 | 아니오 |
| `models auth "<order>"` | 인증 우선순위 변경 | 아니오 |
| `models list\|add\|remove` | 모델 레지스트리 | 아니오 |
| `notify [--dry-run]` | 검토 대기 알림 (0건이면 침묵) | 아니오 |
| `serve-mcp [--project P]` | MCP stdio 서버 | 아니오 |
| `setup-agent claude\|codex\|agy\|all` | 전역 에이전트 어댑터 설치 | 아니오 |

`compile`은 `--force`를 받지만 현재 아무 효과가 없습니다.

---

<a id="ko-21"></a>

## 21. 설정 레퍼런스

`<project>/.llm-wiki/config.yaml`이고, 전역 폴백은 `~/.llm-wiki/config.yaml`입니다.

```yaml
project: "Adaptive exoskeleton control for hemiplegic gait"
language: en                       # ko | en — init에서 설정, 본문과 제목을 지배
external_llm_allowed: true         # false = Ollama 전용, 코드로 강제

model:
  compile: claude-opus-5           # 편찬하는 모델
  audit: claude-haiku-4-5          # 예약 — 아직 읽지 않음
  metadata: claude-haiku-4-5       # 예약 — 아직 읽지 않음
  fallback_local: qwen3:32b        # Ollama 경로가 사용

llm:
  auth_order: [oauth, api_key, ollama]
  cli_path_gemini: /opt/homebrew/bin/gemini    # 기관 계정용 옵트인
  cli_args_antigravity: [--effort, high]       # 공급자별 추가 CLI 인자

review:
  reviewer: Jane Kim
  stale_draft_days: 14             # 이보다 오래된 draft를 audit이 표시

snapshot:
  backup_keep: 10

git:
  enabled: false                   # 예약 — 아직 `llm-wiki git` 명령 없음

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

그 밖의 위치:

| 경로 | 내용 |
|---|---|
| `~/.llm-wiki/config.yaml` | 전역 기본값 (모델, 인증 순서) |
| `~/.llm-wiki/models.yaml` | 공급자별 모델 레지스트리 |
| `.llm-wiki/manifest.json` | 모든 원자료: 해시, 유형, 업로더, 처리 여부 |
| `.llm-wiki/metrics/costs.jsonl` | 실행별 토큰과 비용 |
| `.llm-wiki/metrics/queries.jsonl` | 모든 질의 (질문자, 히트 수 포함) |
| `.llm-wiki/processing-log.md` | 사람이 읽는 실행 로그 |
| `.llm-wiki/audit/` | 감사 리포트 |
| `.llm-wiki/backups/` | 스냅샷 (기본 최근 10개) |

환경 변수: `LLM_WIKI_ASKER`(기본 질문자 이름), `LLM_WIKI_FAKE`(LLM 호출 대신 파일 내용을
돌려주는 테스트 훅), 그리고 공급자 키(`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`GEMINI_API_KEY` / `GOOGLE_API_KEY`).

---

<a id="ko-22"></a>

## 22. 문제 해결

**"llm-wiki 프로젝트가 아닙니다 (.llm-wiki 없음)"**
프로젝트 폴더 밖에 있습니다. 폴더로 `cd` 하거나 `llm-wiki init`을 실행하세요. 참고로 홈
디렉터리는 `~/.llm-wiki/`가 있더라도 의도적으로 프로젝트로 취급하지 않습니다.

**"'claude-opus-5' 을(를) 쓸 수 있는 백엔드가 없습니다"**
`llm-wiki models show`를 실행하면 각 경로를 무엇이 막고 있는지 보여줍니다. CLI를 설치하거나,
API 키를 설정하거나, Ollama를 켜거나, `llm-wiki models use`로 다른 모델을 고르세요.

**PDF 편찬이 pypdf 메시지와 함께 실패**
API 키, Ollama, Antigravity 백엔드는 PDF 텍스트를 로컬에서 읽으므로
`pipx inject llm-wiki pypdf`가 필요합니다. `claude`와 `codex` OAuth 백엔드는 파일을 직접
읽으므로 필요 없습니다.

**편찬 실행이 아무것도 만들지 않고 비용도 0**
백엔드가 `agy`라면, 도구 권한 거부가 성공으로 반환되면서 응답이 비어 옵니다. llm-wiki는 이를
오류로 바꾸고 백엔드를 전환합니다. 메시지를 확인하고, 필요하면 Antigravity 설정에서 해당
도구를 허용하세요.

**갱신 후 코멘트가 사라짐**
그럴 리 없습니다 — 보존은 두 언어 모두에서 강제됩니다. 그런 일이 생겼다면 제목이 바뀌었을
가능성이 큽니다(예: `## 코멘트 (메모)`). 백업에서 복원하세요:
`llm-wiki rollback <run-id>` 후 제목을 템플릿과 정확히 일치하게 고치세요.

**Dropbox "conflicted copy" 파일**
`audit`이 찾아냅니다. 손으로 병합하고, 더 높은 상태를 유지하고, 사본을 삭제하세요. 프로젝트
폴더를 여러 머신에서 동기화한다면, 다른 머신에서 명령을 실행하기 전에 동기화가 끝나길
기다리세요 — 그리고 그 폴더가 Dropbox 안의 Git 저장소라면 `git pull`보다 동기화를 기다리는
쪽이 낫습니다.

**두 사람이 동시에 compile을 실행함**
락이 막습니다 — 두 번째 실행은
`오류: 다른 실행이 진행 중입니다 (compile, pid 12345)`로 종료됩니다. 첫 실행이 끝날 때까지
기다리세요. 프로세스가 비정상 종료됐다면 다음 실행에서 stale 락이 자동으로 해제됩니다.
직접 지워야 한다면 `.llm-wiki/.lock`을 삭제하세요.

**편집 요청이 제안이 되지 않음**
대상은 `30_Wiki/` 안에 이미 있는 문서여야 합니다. `10_Inbox/_requests/`의 `- Target:` 줄을
확인해 경로를 고치고 `compile`을 다시 실행하세요.

---

<a id="ko-23"></a>

## 23. 아직 구현되지 않은 것

찾아 헤매지 않도록 솔직히 적어 둡니다.

| 항목 | 상태 |
|---|---|
| `llm-wiki activity` CLI 명령 | MCP 도구 `wiki_activity`만 존재 |
| `llm-wiki git enable/disable` | `git.enabled` 설정 키만 있고 명령은 없음 |
| 지식 공백 탐지 → `30_Wiki/Questions/`에 자동 스텁 생성 | 질의는 기록되지만 소비하는 곳이 없음 |
| `model.audit` / `model.metadata` 역할 | `init`이 쓰지만 읽지는 않음 — 실제로 쓰이는 역할은 `compile`뿐 |
| `#반영요청` 코멘트 태그 → 자동 제안 | 에이전트용 관례일 뿐, 처리하는 명령 없음 |
| `ingest` 중 LLM 메타데이터 추출 | 제목·저자·연도는 파일명 기반 자리표시자 |
| 스캔 PDF OCR | 미지원 |
| `compile --force` | 플래그를 받지만 효과 없음 |

---

*질문·버그·기능 요청: [github.com/pilwonhur/llm-wiki](https://github.com/pilwonhur/llm-wiki)*

[↑ 목차로](#목차) · [English version →](#english)
