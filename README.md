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
| Claude Code (`claude`) | OAuth 구독으로 편찬할 때 (권장 기본) |
| `pipx inject llm-wiki anthropic` + `ANTHROPIC_API_KEY` | API key 백엔드 |
| Ollama | 로컬 LLM — 민감 프로젝트·오프라인 |
| `pipx inject llm-wiki pypdf` | API/Ollama 백엔드로 PDF를 처리할 때 (OAuth는 불필요) |

## 빠른 시작

**템플릿 파일을 수동으로 복사할 필요가 없다** — 템플릿 팩(폴더 구조, AGENTS.md,
워크플로우, 문서 템플릿, 스킬 어댑터)이 패키지에 내장되어 있고 `init`이 전부 설치한다.

```console
$ mkdir Project-X && cd Project-X
$ llm-wiki init             # 대화형 온보딩 (이름·목적·구성원·reviewer·민감도·모델)
                            # 스크립트용: llm-wiki init --yes
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
| `models [add\|list\|remove]` | 모델 레지스트리 (`~/.llm-wiki/models.yaml`) |
| `notify [--dry-run]` | 검토 대기 알림 (0건이면 미발송) |
| `serve-mcp` | MCP stdio 서버 |

야간 배치 (cron 예):

```cron
0 3 * * *  cd /path/Project-X && llm-wiki ingest --yes && llm-wiki compile && llm-wiki notify
0 4 * * 0  cd /path/Project-X && llm-wiki audit
```

### B. 에이전트 CLI (Claude Code / Codex — 대화하면서 작업)

프로젝트 폴더에서 에이전트를 열면 `AGENTS.md` 규칙과 스킬 어댑터가 자동 적용된다
(init이 설치). 스킬은 내부적으로 CLI를 호출하므로 결과는 터미널과 동일하다.

```console
$ cd Project-X && claude
> /wiki-ingest                  # = llm-wiki ingest
> /wiki-compile                 # = llm-wiki compile
> /wiki-audit                   # = llm-wiki audit
> 인박스 정리하고 편찬해줘        # 자연어도 동일하게 동작
```

Codex: `adapters/codex/*.md`를 `~/.codex/prompts/`로 복사하면 같은 `/wiki-*` 명령 사용.
규칙 수정은 항상 `AGENTS.md` 한 곳에서만 한다 (`CLAUDE.md`는 import 한 줄).

### C. MCP (외부 AI 비서 — 질의·Q&A·코멘트)

Claude Code·Codex·Gemini CLI·OpenClaw 등 MCP 클라이언트가 Wiki에 접속하는 도구 중립 창구.

```console
$ cd Project-X
$ claude mcp add llm-wiki -- llm-wiki serve-mcp     # Claude Code 등록 (한 번만)
```

OpenClaw 등 다른 클라이언트: command `llm-wiki`, args `["serve-mcp"]`, cwd는 프로젝트 폴더.

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

`compile`·`review apply`는 아래 순서로 사용 가능한 백엔드를 자동 선택한다
(config `llm.auth_order`로 변경 가능):

1. **OAuth** — `claude` CLI 설치·로그인 시 (구독 한도 내, 별도 과금 없음)
2. **API key** — `ANTHROPIC_API_KEY` + `anthropic` 패키지
3. **Ollama** — `localhost:11434` 응답 시 (`model.fallback_local`)

민감 프로젝트는 `.llm-wiki/config.yaml`에서 `external_llm_allowed: false`로 잠그면
**코드 수준에서 Ollama만 허용**된다. 모델명은 하드코딩되지 않는다 —
`llm-wiki models add claude claude-fable-5.1`처럼 등록하면 전 프로젝트에서 선택 가능.

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
