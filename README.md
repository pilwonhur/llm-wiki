# GIST HUR Group LLM-Wiki

> **GIST 기계로봇공학과 HUR Group(허필원 교수 연구실)의 연구실 프로젝트별 지식 편찬 시스템** —
> 원자료(논문 PDF·회의록·연구계획서·Q&A)를 넣으면 AI가 **파일·페이지 단위 출처가 달린**
> Markdown Wiki를 편찬하고, 연구자가 검토·승인한다.

- **사람은 원자료를 관리하고, AI는 근거로 편찬하며, 공식 판단은 사람이 승인한다.**
- AI는 `draft`까지만 쓴다. `reviewed`/`approved`는 사람 전권이며, 검토된 문서는
  AI가 직접 수정할 수 없고 변경 **제안**만 할 수 있다 — 프롬프트가 아니라 코드가 강제한다.
- 정본은 언제나 사람이 읽을 수 있는 Markdown 파일. 인덱스·DB는 재구축 가능한 파생물.

설계 배경·요구사항·시나리오는 랩 문서(`PRD.md`, `SCENARIOS.md`) 참조.
GIST HURGroup(허필원 교수 연구실) 내부 사용 목적으로 개발되었다.

---

## 설치

필수는 **Python 3.12+** (와 pipx) 하나다. 검색 DB는 내장 SQLite, 스냅샷·롤백은 내장 백업 — Git 불필요.
설치는 **컴퓨터당 1회**다 — 프로젝트마다 다시 설치할 필요 없다 (프로젝트 생성은 `init`).

```console
# 일반 사용자: GitHub에서 바로 설치 (clone 불필요)
$ pipx install "git+https://github.com/pilwonhur/llm-wiki.git"

# 업데이트 (새 버전이 push되었을 때)
$ pipx reinstall llm-wiki

$ llm-wiki --help           # 확인
```

개발자는 clone 후 editable 설치를 쓴다 — 소스 수정이 즉시 반영된다:

```console
$ git clone https://github.com/pilwonhur/llm-wiki.git && cd llm-wiki
$ pipx install -e .
```

| 선택 설치 | 언제 |
|---|---|
| Claude Code (`claude`) | **편찬(compile) 백엔드** — OAuth 구독 (권장 기본) + 에이전트 입구·MCP 클라이언트 |
| Codex CLI (`codex`) | **에이전트 입구·MCP 클라이언트로 사용** (스킬 어댑터 동봉). 편찬 백엔드로는 아직 미지원 — 아래 참고 |
| `pipx inject llm-wiki anthropic` + `ANTHROPIC_API_KEY` | API key 편찬 백엔드 (Claude Code 없이) |
| Ollama | 로컬 LLM 편찬 백엔드 — 민감 프로젝트·오프라인 |
| `pipx inject llm-wiki pypdf` | API/Ollama 백엔드로 PDF를 처리할 때 (OAuth는 불필요) |

> Codex 참고: Codex로 대화하며 `/wiki-compile`을 실행하면 편찬 자체는 CLI가 설정된
> 백엔드(Claude OAuth/API key/Ollama)로 수행한다. OpenAI 구독(OAuth)을 편찬 백엔드로
> 쓰는 것은 백로그다 — 타사 구독 OAuth는 헤드리스 래핑의 안정성 검증 후 추가한다는
> 설계 방침(PRD §3.3)에 따른 것.

### Windows / Linux에서 사용

기능은 세 OS에서 동일하다 (경로·한글 파일명 NFC 정규화·검색·백업 전부 이식성 확보).
OS별로 다른 것은 설치 명령과 두 가지 보조 기능뿐:

```console
# Windows (PowerShell)
> winget install Python.Python.3.12
> python -m pip install --user pipx && python -m pipx ensurepath   # 새 터미널 열기
> pipx install "git+https://github.com/pilwonhur/llm-wiki.git"

# Linux (Ubuntu 예)
$ sudo apt install python3 pipx && pipx ensurepath
$ pipx install "git+https://github.com/pilwonhur/llm-wiki.git"
```

| 차이 | macOS | Windows / Linux |
|---|---|---|
| audit의 PDF 페이지 수 검사 | 자동 (Spotlight) | `pipx inject llm-wiki pypdf` 1회 주입 권장 (없으면 해당 검사만 생략) |
| 알림 채널 | 콘솔 + macOS 알림 + webhook/이메일 | 콘솔 + webhook/이메일 (동일 설정) |
| 야간 배치 | cron/launchd | Linux: cron / Windows: 작업 스케줄러 — `schtasks /Create /SC DAILY /ST 03:00 /TN llm-wiki /TR "cmd /c cd /d C:\path\Project-X && llm-wiki ingest --yes && llm-wiki compile"` |

Dropbox 등으로 프로젝트 폴더를 macOS↔Windows 간 공유해도 된다 — 한글 파일명
정규화(NFC/NFD)를 시스템이 처리한다.

## 빠른 시작

**템플릿 파일을 수동으로 복사할 필요가 없다** — 템플릿 팩(폴더 구조, AGENTS.md,
워크플로우, 문서 템플릿, 스킬 어댑터)이 패키지에 내장되어 있고 `init`이 전부 설치한다.

**init은 세 가지 방법 중 아무 것으로나 할 수 있다** (결과 동일):

| 방법 | 사용 |
|---|---|
| ① 터미널 | `mkdir Project-X && cd Project-X && llm-wiki init` — 대화형 온보딩 내장 (스크립트용 `--yes`) |
| ② 에이전트에게 자연어 | 새 폴더에서 Claude Code/Codex를 열고 **"여기에 위키 프로젝트 만들어줘"** — 에이전트가 온보딩을 대화로 진행하고 내부적으로 `llm-wiki init` 실행 |
| ③ 전역 스킬 `/wiki-init` | 아래 한 줄로 **한 번 등록**해 두면, 아무 폴더에서나 `/wiki-init`으로 시작: |

```console
# ③의 등록 (컴퓨터당 1회, 아무 위치에서나 실행 가능 — 파일이 패키지에 내장됨)
$ llm-wiki setup-agent claude      # Codex 사용자: llm-wiki setup-agent codex
```

```console
# ①의 예
$ mkdir Project-X && cd Project-X
$ llm-wiki init             # 대화형 온보딩 (이름·목적·구성원·reviewer·민감도·모델)
```

init이 만드는 것: `00_Project`~`90_Archive` 표준 구조, `.llm-wiki/`(config·manifest·
workflows·백업), `AGENTS.md`+`CLAUDE.md`(에이전트 규칙), `.claude/skills/`(스킬 어댑터),
구성원별 `10_Inbox/<이름>/` 폴더. 자료가 이미 있는 폴더에서 실행해도 기존 파일은
절대 건드리지 않으며, 재실행은 빠진 것만 보충한다(멱등).

## 일상 루프

```console
$ cp 논문.pdf 10_Inbox/홍길동/     # ① 자료는 자기 이름 폴더에 (업로더 귀속)
$ llm-wiki ingest                  # ② 해시·중복 검사·분류·등록 (--yes: 추정 수용)
$ llm-wiki compile                 # ③ 편찬 — 백업 선행, 자료당 순차, 비용 기록
$ llm-wiki review                  # ④ 검토 대기 목록 (draft·제안·disputed)
   → 사람: 근거 링크를 원문과 대조 후 frontmatter status를 reviewed로 편집
$ llm-wiki review apply --all      # ⑤ 변경 제안 일괄 승인 (목록 확인 후) — 낱개는 apply <이름>
$ llm-wiki audit                   # ⑥ 품질 감사 (링크·페이지·status·충돌 사본… 보고만)
```

문제가 생기면: `llm-wiki diff [실행ID]`로 변경 확인 → `llm-wiki rollback [실행ID]`로 복원.

---

## 활용 방법 3가지

같은 프로젝트를 세 입구로 쓸 수 있고, **어느 입구든 같은 안전장치(lock·백업·검증)를 거친다.**

### A. 터미널 CLI (기본 — 배치·스크립트·에이전트 없이)

전 명령:

| 명령 | 기능 |
|---|---|
| `init [경로] [--yes]` | 프로젝트 생성 + 온보딩 (멱등) |
| `ingest [--yes]` | Inbox 접수: 해시·중복·파일명 정규화·업로더 귀속·분류 |
| `compile` | 편찬: 백업 → 자료당 LLM 호출 → 코드 검증 → 쓰기 → 비용 기록 |
| `review` | 검토 대기 목록 |
| `review apply <이름>` / `apply --all` / `reject <이름> --reason` | 제안 승인·거부 |
| `audit` | 품질 감사 리포트 (`.llm-wiki/audit/`) |
| `search <질의> [--no-draft]` / `reindex` | 전문 검색 (approved>reviewed>draft 우선) |
| `status` | 현황 요약 |
| `diff [ID]` / `rollback [ID]` | 백업 대비 변경 확인 / 복원 |
| `models use [모델] [--role R] [--global]` | 사용할 LLM 선택 (인자 없으면 대화형) |
| `models show` / `models auth <순서>` | 현재 모델·인증 경로 확인 / 인증 우선순위 변경 |
| `models [list\|add\|remove]` | 모델 레지스트리 (`~/.llm-wiki/models.yaml`) |
| `notify [--dry-run]` | 검토 대기 알림 (0건이면 미발송) |
| `serve-mcp` | MCP stdio 서버 |
| `setup-agent claude\|codex\|all` | 전역 에이전트 어댑터 설치 (컴퓨터당 1회) |

야간 배치 (cron 예):

```cron
0 3 * * *  cd /path/Project-X && llm-wiki ingest --yes && llm-wiki compile && llm-wiki notify
0 4 * * 0  cd /path/Project-X && llm-wiki audit
```

### B. 에이전트 CLI (Claude Code / Codex — 대화하면서 작업)

**도구별 시작 준비** — "즉시"는 init된 프로젝트 폴더를 여는 것만으로 동작한다는 뜻:

| | 규칙 (AGENTS.md) | 자연어 작업 | `/wiki-*` 슬래시 명령 | `/wiki-init` (새 폴더용) |
|---|---|---|---|---|
| **Claude Code** | 즉시 (`CLAUDE.md`가 import) | 즉시 | 즉시 (`.claude/skills/` 자동 인식) | 1회: `llm-wiki setup-agent claude` |
| **Codex** | 즉시 (표준 파일 직접 읽음) | 즉시 | 1회: `llm-wiki setup-agent codex` (4개 명령 전부 설치) | 위 명령에 포함 |

즉 **Codex 사용자도 규칙·자연어는 준비 없이 바로 동작**하고, 슬래시 명령은
`llm-wiki setup-agent codex` **한 번**(컴퓨터당)이면 전 프로젝트에서 쓸 수 있다.
`setup-agent`는 아무 위치에서나 실행 가능하다 — 어댑터 파일이 패키지에 내장되어
있어 저장소 clone이나 상대경로가 필요 없다. 스킬/프롬프트는 내부적으로 CLI를
호출하므로 결과는 터미널과 동일하다.

```console
$ cd Project-X && claude
> /wiki-ingest                  # = llm-wiki ingest
> /wiki-compile                 # = llm-wiki compile
> /wiki-audit                   # = llm-wiki audit
> 인박스 정리하고 편찬해줘        # 자연어도 동일하게 동작
```

규칙 수정은 항상 `AGENTS.md` 한 곳에서만 한다 (`CLAUDE.md`는 import 한 줄).

**init도 대화로 할 수 있다** — `llm-wiki setup-agent claude`(또는 `codex`)로 전역
`/wiki-init`을 등록해 두면 아무 새 폴더에서나 대화형으로 시작할 수 있다. 등록 없이도
에이전트에게 "여기에 위키 프로젝트 만들어줘"라고 말하면 된다 — 에이전트가 온보딩을
대화로 진행하고 내부적으로 `llm-wiki init`을 실행한다.

### C. MCP (외부 AI 비서 — 질의·Q&A·코멘트)

Claude Code·Codex·Gemini CLI·OpenClaw 등 MCP 클라이언트가 Wiki에 접속하는 도구 중립 창구.

서버는 표준 MCP stdio라서 **MCP를 지원하는 어떤 클라이언트든** 붙는다. 클라이언트가
프로젝트 폴더 밖에서 서버를 띄우는 경우(전역 설정 등록)에는 `--project`로 경로를 지정한다.

**Claude Code** (프로젝트 폴더에서 등록):

```console
$ cd Project-X
$ claude mcp add llm-wiki -- llm-wiki serve-mcp
```

**Codex** (`~/.codex/config.toml`에 추가):

```toml
[mcp_servers.llm-wiki]
command = "llm-wiki"
args = ["serve-mcp", "--project", "/절대/경로/Project-X"]
```

**Gemini CLI** (`~/.gemini/settings.json`에 추가):

```json
{"mcpServers": {"llm-wiki": {
  "command": "llm-wiki",
  "args": ["serve-mcp", "--project", "/절대/경로/Project-X"]}}}
```

**Antigravity / OpenClaw 등**: 각 도구의 MCP 설정 화면에서 command `llm-wiki`,
args `["serve-mcp", "--project", "<프로젝트 경로>"]`로 등록 — 형식은 위와 동일하다.
프로젝트가 여러 개면 프로젝트마다 서버를 하나씩(이름을 다르게) 등록한다.

| MCP 도구 | 기능 | 쓰기 권한 |
|---|---|---|
| `wiki_search` | 전문 검색 (질의는 실명과 함께 관심도 로그에 기록) | — |
| `wiki_read` | 문서 읽기 (30_Wiki 한정) | — |
| `wiki_status` | 현황 요약 | — |
| `wiki_request_edit` | 변경 요청 제출 → `10_Inbox/_requests/` | 요청만 |
| `wiki_save_qa` | 사람이 동의한 Q&A 신규 정보 제출 → `10_Inbox/_qa/` (web 유형은 URL 필수) | 제출만 |
| `wiki_add_comment` | 코멘트 append (기록 전용 — 편찬 근거로 안 쓰임) | append만 |
| `wiki_activity` | 구성원 활동 요약 (업로드·질의·검토·코멘트) | — |

**설계상 Wiki 본문을 직접 수정하는 MCP 도구는 없다** — 외부 비서는 읽고, 요청하고,
기록할 수만 있다. 대화 예: *"위키에서 위상 변수 검색해줘"*, *"이 문서에 코멘트 남겨줘"*,
*"방금 웹에서 찾은 내용을 원자료로 저장해줘"* (항목별 동의 후 저장).

---

## LLM 백엔드와 모델

**모델은 사용자가 정한다.** 공급자(Anthropic·OpenAI·Google Gemini·Ollama)와 인증
방식(구독 OAuth·API key)을 자유롭게 조합할 수 있고, 한 번 정하면 계속 유지되며
언제든 바꿀 수 있다.

```bash
$ llm-wiki models use                    # 대화형 — 공급자·모델·저장 위치를 골라서 설정
$ llm-wiki models use gpt-5.6-sol        # 바로 지정
$ llm-wiki models use gemini-3.6-flash --global   # 이 컴퓨터의 모든 프로젝트 기본값
$ llm-wiki models use claude-haiku-4-5 --role audit  # 역할별로 섞기 (비용 절약)
$ llm-wiki models show                   # 현재 설정 + 지금 쓸 수 있는 인증 경로
$ llm-wiki models auth "api_key,oauth"   # 인증 우선순위 변경
```

설정은 두 층이다. 프로젝트 값이 항상 이긴다.

| 위치 | 파일 | 역할 |
|---|---|---|
| 전역 | `~/.llm-wiki/config.yaml` | 이 컴퓨터의 기본 모델·인증 순서 (`--global`). `init` 때 기본값으로 제시된다 |
| 프로젝트 | `.llm-wiki/config.yaml` | 이 프로젝트만의 선택 — 없는 항목은 전역값을 물려받는다 |

**모델명이 공급자를 결정한다.** 레지스트리(`~/.llm-wiki/models.yaml`)를 먼저 찾고,
없으면 접두사로 추정한다. 판단이 안 되면 `openai/내-파인튜닝-모델`처럼 앞에 붙이거나
`llm-wiki models add openai <모델명>`으로 등록하면 된다 — 새 모델이 나와도 코드 수정은 필요 없다.

공급자별 호출 경로:

| 공급자 | OAuth (구독) | API key |
|---|---|---|
| Anthropic | `claude` CLI (Claude Code 헤드리스) | `ANTHROPIC_API_KEY` + `anthropic` |
| OpenAI | `codex` CLI (`codex exec`) | `OPENAI_API_KEY` + `openai` |
| Google Gemini | `gemini` CLI (`gemini -p`) | `GEMINI_API_KEY`(또는 `GOOGLE_API_KEY`) + `google-genai` |
| Ollama | — | 로컬 `localhost:11434` |

`llm.auth_order`(기본 `[oauth, api_key, ollama]`) 순서로 **쓸 수 있는 경로를 모두 묶어 두고**,
실행 중 앞의 경로가 실패하면(로그인 만료·구독 등급 문제 등) 다음 경로로 자동 전환한다.
OAuth 경로만 쓸 거라면 Python 패키지는 하나도 설치할 필요가 없다. API key 경로는 필요한 것만:

```bash
$ pipx inject llm-wiki openai        # 또는 anthropic / google-genai
$ pipx install "llm-wiki[all]"       # 전부
```

민감 프로젝트는 `.llm-wiki/config.yaml`에서 `external_llm_allowed: false`로 잠그면
설정된 모델과 **무관하게 코드 수준에서 Ollama만 허용**된다 (`model.fallback_local`).

## 안전장치 (전부 코드 수준 강제, 적대 테스트 통과)

| 규칙 | 강제 방식 |
|---|---|
| AI는 `status: draft`만 | 생성·갱신 문서의 status를 코드가 draft로 치환 |
| 원자료 불가침 | 쓰기 경로 화이트리스트 (30_Wiki 밖 쓰기 차단) |
| 검토 문서 보호 | reviewed 이상 대상의 update를 제안(`_Proposals`)으로 자동 강등 |
| 코멘트 불가침 | 갱신·병합 시 기존 `## 코멘트` 섹션 원본 보존 |
| 이중 실행 방지 | lock 파일 (stale lock 자동 해제) |
| 되돌리기 | 실행 전 자동 백업 (기본 10회 보관) + `rollback` |
| 승인 무결성 | `review apply` 병합 시 status·reviewer를 원문 값으로 복원 |
| 비용 가시성 | 실행별 토큰·비용을 `metrics/costs.jsonl`에 기록 |

## 개발

```console
$ pipx install -e .                          # editable 설치
$ LLM_WIKI_FAKE=응답.json llm-wiki compile    # LLM 없이 파이프라인 테스트
```

- 코어 의존성 0 — 표준 라이브러리만. 선택 extras: `[pdf]`, `[llm]`
- 구조: `core.py`(경로·해시·manifest·lock·백업) / `*_cmd.py`(명령) /
  `backends.py`(LLM) / `templates/project/`(init이 설치하는 템플릿 팩)
- 테스트 기준: 랩 문서 `SCENARIOS.md`의 P0 시나리오 54개
- 버전: 유의적 버전(주.부.수) — 이력은 `CHANGELOG.md`, 확인은 `llm-wiki --version`,
  릴리스마다 git 태그(`v0.x.y`)
