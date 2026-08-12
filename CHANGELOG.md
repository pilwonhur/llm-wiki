# Changelog

GIST HUR Group LLM-Wiki의 버전별 변경 이력. 형식은 [Keep a Changelog](https://keepachangelog.com/ko/)를 따르고,
버전은 [유의적 버전](https://semver.org/lang/ko/)(주.부.수)을 따른다.

- **주(major)**: 프로젝트 폴더 구조·manifest 등 데이터 형식이 바뀌어 마이그레이션이 필요할 때
- **부(minor)**: 명령·기능 추가 (기존 프로젝트 그대로 사용 가능)
- **수(patch)**: 버그 수정·문서 정비

업데이트: `pipx reinstall llm-wiki` / 버전 확인: `llm-wiki --version`

## [0.7.1] — 2026-08-12

### Added
- **`/wiki-ask` 스킬을 Claude Code·Codex에도 설치** — 0.5.0에서 Antigravity에만 만들어
  도구별로 명령 수가 어긋나 있었다. 이제 네 도구 모두 프로젝트 명령 4종
  (`/wiki-ingest`·`/wiki-compile`·`/wiki-audit`·`/wiki-ask`) + 전역 `/wiki-init` 로 동일
- `USAGE.md` §16을 에이전트 CLI 실사용 예시로 전면 확장 — 세션 시작, 명령 4종의 실제
  대화, 검토 세션(근거 대조 → 승격은 사람이), 제안 처리, 자연어와 슬래시 명령의
  안전장치 차이, Codex·Antigravity, 대화형 프로젝트 생성, 헤드리스 배치

## [0.7.0] — 2026-08-12

출력 언어(한국어 / English)를 실제로 지원한다. 그동안 `init`이 묻고 config에 저장만 하던
`language` 값이 어디에서도 읽히지 않았다.

### Added
- **`language: ko|en` 을 코드가 사용한다** — `compile`·`ask`·`review apply` 프롬프트가
  설정 언어로 지시하고, `init`이 언어에 맞는 문서 템플릿과 `AGENTS.md` 출력 언어 줄을 설치한다
- 문서 템플릿 2벌: `wiki-doc.ko.md` / `wiki-doc.en.md` (init이 `wiki-doc.md` 로 설치)
- **섹션 제목을 `core.HEADINGS` 상수로 일원화** — 템플릿·프롬프트·파서가 같은 값을 본다.
  쓸 때는 설정 언어로, **읽을 때는 두 언어를 모두 허용**해 언어가 섞여도 안전장치가 유지된다
- `init` 의 언어 질문이 선택지를 제시하고(`ko=한국어 / en=English`) "한국어"·"English"
  같은 답도 받아준다
- 영어 검색 처리 — 복수형·시제 접미사를 떼어 접두 검색으로 넘긴다. 한국어와 동일한 구조
  (접미사 사전, 의존성 0). 토큰별로 한/영을 판별해 혼용 문서도 처리한다
- README를 영어 우선 + 한국어 병기로 재구성

### Fixed
- **영어로 편찬하면 안전장치가 조용히 풀리던 문제** — 코드가 `## 코멘트`·`## 근거` 같은
  한국어 제목을 파싱하는데 영어 문서는 `## Comments`·`## Sources` 를 쓴다. 그 결과:
  - `compile`·`review apply` 가 **연구자 코멘트를 통째로 유실** (F12.1 위반, 경고도 없음)
  - `wiki_add_comment` 가 코멘트 섹션을 **중복 생성**
  - `audit` 이 출처가 멀쩡한 문서를 전부 "출처 없음"으로 보고
  - Q&A 실명 귀속(`- 질문자:`)·편찬 요청 파싱(`- 요청자:`/`## 제안`)이 전부 실패
  파싱 지점 9곳을 언어 무관 패턴으로 교체했다
- 영어 질의가 검색에서 거의 걸리지 않던 문제 — `the`·`is` 같은 불용어가 그대로 검색어가
  되고 `actuators` 로 물으면 본문의 `actuator` 를 놓쳤다

### Notes
- 기존 한국어 프로젝트는 그대로 동작한다 (`language` 미설정 시 `ko`). 회귀 확인 완료
- 언어는 프로젝트 생성 시점에 정하는 값이다 — 중간에 바꾸면 이미 편찬된 문서와 섞인다
  (안전장치는 유지되지만 문서 언어가 혼재)

## [0.6.0] — 2026-08-12

편찬 요청(`_requests`) 환류를 이었다 — 이제 MCP의 세 제출 창구가 모두 Wiki까지 도달한다.

### Added
- **`compile`이 `10_Inbox/_requests/` 를 처리한다** — MCP `wiki_request_edit` 로 들어온
  변경 요청을 `30_Wiki/_Proposals/` 제안서로 변환하고, 원본 요청은
  `90_Archive/_requests/` 로 옮겨 재처리를 막는다. 이후는 기존 경로 그대로:
  사람이 `llm-wiki review apply` 로 승인해야 본문에 반영된다
  - **LLM을 부르지 않는다** — 제안서는 결정적으로 만들고, 병합은 `review apply`의 몫.
    덕분에 백엔드가 없어도 요청 처리가 되고, 미처리 원자료가 0건이어도 compile이 돈다
  - 대상은 `30_Wiki` 안의 **기존** 문서여야 한다 (요청으로 새 문서를 만들지 않는다).
    대상이 없거나 밖이면 보류하고 요청 파일을 남긴다
  - 제안서 frontmatter에 `target`·`requested_by`·`status_at_request`·`source_request` 기록

### Fixed
- **같은 초에 들어온 제출물이 서로를 덮어쓰던 문제** — Q&A(`_qa`)·편찬 요청(`_requests`)
  파일명이 초 단위라 연속 제출이 조용히 유실됐다. `unique_path()` 로 `-2`, `-3` 을 붙인다
  (MCP `wiki_save_qa`·`wiki_request_edit`, `ask --save-qa` 모두 해당)
- 같은 문서에 요청이 여러 건이면 제안서도 파일명이 겹쳐 하나만 남던 문제 (같은 원인)

## [0.5.1] — 2026-08-12

### Changed
- **Gemini CLI(`gemini`)를 기본 OAuth 경로에서 제외** — 개인 구독이 종료됐다
  (`IneligibleTierError: no longer supported for Gemini Code Assist for individuals`
  → Antigravity로 이관). Gemini 구독 경로는 Antigravity(`agy`)를 쓰고,
  `gemini-3.6-flash` 같은 직접 호출은 API key 경로로 남는다.
  조직 계정 등으로 아직 쓸 수 있으면 config `llm.cli_path_gemini` 로 켠다
- OAuth 경로가 없는 공급자를 API key 경로가 없는 공급자(antigravity)와 대칭으로 처리 —
  `oauth_backend()` 도입. `models show`는 "개인 구독 종료 — Antigravity(agy) 사용"으로,
  `plan()`은 막힌 이유에 대안을 함께 표시한다

## [0.5.0] — 2026-08-12

Antigravity CLI(`agy`) 지원 — 네 번째 공급자이자 네 번째 에이전트 입구.

### Added
- **`antigravity` 공급자** — `agy -p --output-format json` 헤드리스 편찬 백엔드.
  구독 OAuth 전용(API key 경로 없음)이며 토큰 사용량을 기록한다. 모델 ID가 자체
  체계(`gemini-3.6-flash-high`·`claude-sonnet-4-6`·`gpt-oss-120b-medium` …)라
  레지스트리에 `antigravity:` 로 기본 등록했고, `agy/<모델>` 로 강제 지정도 가능
- **`setup-agent agy`** — `/wiki-init`·`/wiki-ingest`·`/wiki-compile`·`/wiki-audit`·
  `/wiki-ask` 스킬을 `~/.gemini/antigravity-cli/skills/` 에 설치 (컴퓨터당 1회)
- `init`이 프로젝트 스킬을 `.agents/skills/` 에도 설치 — agy가 프로젝트 스킬을 읽는 경로
- `llm.cli_path_<provider>` — CLI 실행 파일 경로를 직접 지정 (자동 탐색 실패 시)
- README: agy용 MCP 등록법 (`.agents/mcp_config.json` 프로젝트 스코프 /
  `~/.gemini/config/mcp_config.json` 전역)과 다중 프로젝트 시 도구 누적 주의

### Fixed
- 레지스트리가 파일에 없는 **신규 공급자만** 기본값으로 채우도록 변경 — 기존
  `models.yaml`을 가진 사용자가 업그레이드해도 새 공급자를 다시 등록할 필요가 없다
  (이게 없으면 `gemini-3.6-flash-high` 가 접두사 추정으로 gemini 직접 호출로 잘못 라우팅됐다)

### Notes
- **agy 백엔드는 에이전트형이 아니다** (`agentic=False`). 헤드리스에서는 도구 권한을
  물어볼 수 없어 파일 읽기가 자동 거부되고, 그때 `status: SUCCESS` 인데 응답만 비어
  돌아온다. 그래서 원자료 본문을 프롬프트에 넣어 도구 없이 답하게 하고, 빈 응답은
  오류로 올려 다음 백엔드로 넘긴다. PDF 원자료를 쓰면 `pypdf` 가 필요하다
- PATH의 `agy` 는 Antigravity **IDE 런처**(Electron)일 수 있다 — `-p` 를 무시하고 창을
  띄운다. 실제 CLI(`~/.local/bin/agy`)를 우선하고 `.app` 번들 경로는 걸러낸다

## [0.4.0] — 2026-08-12

질문하기 — Wiki에 근거해 답하고, 답변 중 배경지식만 동의를 거쳐 원자료로 되돌린다.

### Added
- **`llm-wiki ask <질문>`** — 편찬된 Wiki를 근거로 답하는 질의응답. MCP 클라이언트 없이
  터미널에서 바로 쓴다. 문장마다 `[번호]` 인용을 붙이고, 근거 목록과 draft 여부를 함께 출력
  - `--asker`(또는 `$LLM_WIKI_ASKER`)로 질의를 실명 귀속해 `queries.jsonl`에 기록 (F11.1)
  - `--top N` 근거 문서 수, `--no-draft` approved/reviewed만 근거로
  - 근거를 못 찾으면 그 사실을 먼저 말하고 배경지식만으로 답한다 (프로젝트 고유 사실은
    모른다고 답하도록 프롬프트에서 강제)
  - 답변의 '모델 배경지식' 항목만 **항목별 동의** 후 `10_Inbox/_qa/`에 저장 (`--save-qa`로
    일괄, `--no-save-qa`로 생략). Wiki 근거로 답한 본문은 저장 후보에 오르지 않는다 —
    Wiki 요약의 원자료 재유입(AI 자기 참조 순환)을 코드에서 차단
- 검색의 한국어 처리 — 조사·용언 어미를 떼고 접두 검색으로 넘긴다. 문장형 질문이
  거의 0건이던 문제 해소 ("제어기 A안을 채택한 근거가 뭐야?" → `제어기* AND A안* AND
  채택* AND 근거*`). 형태소 분석기 없이 접미사 사전으로 근사 — 의존성 0 유지

### Fixed
- **Q&A 환류가 끊겨 있던 문제** — `ingest`가 `10_Inbox/_qa/`를 건너뛰어, MCP
  `wiki_save_qa`가 저장한 Q&A가 아무도 읽지 않는 곳에 쌓이기만 했다 ("ingest 후 편찬 시
  반영됩니다"라는 안내가 사실이 아니었음). 이제 `type: qa`로 등록해
  `20_Sources/QA-Sessions/`로 옮기고 다음 compile이 편찬한다. 귀속은 폴더명이 아니라
  파일에 적힌 질문자를 따른다. `_requests/`는 원자료가 아니므로 계속 제외
- README가 소개하던 미구현 명령 정리 — `llm-wiki ask`는 이번에 구현했고,
  `llm-wiki activity`(MCP `wiki_activity`로만 존재)와 질의 패턴 기반 지식 공백 자동
  탐지는 백로그로 명시

## [0.3.1] — 2026-08-12

### Fixed
- **설치본에서 `init`이 죽던 치명 버그** — 프로젝트 템플릿의 `.llm-wiki/` 폴더가
  wheel에 통째로 빠져 있었다 (config.yaml·manifest.json·wiki-doc.md 템플릿·
  workflows 프롬프트 3종). package-data 글롭은 점으로 시작하는 폴더 *안쪽*을
  포함하지 못하는데 `.claude`만 예외 규칙이 있었다. pip/pipx로 설치한 사용자는
  `llm-wiki init`에서 FileNotFoundError로 중단됐다 (소스 트리에서 실행할 때는
  파일이 있어 드러나지 않던 문제). MANIFEST.in graft + include-package-data로 해결
- `save_config`·`save_manifest`가 `.llm-wiki/`를 직접 만들도록 보강 — 템플릿 복사가
  실패해도 프로젝트 생성이 절반만 된 채 끝나지 않는다

## [0.3.0] — 2026-08-12

LLM 선택권을 사용자에게. 공급자·인증 방식을 자유롭게 고르고, 한 번 정하면 유지되며,
언제든 바꿀 수 있다.

### Added
- **다중 공급자 백엔드** — Anthropic 외에 OpenAI·Google Gemini를 OAuth(구독 CLI)와
  API key 양쪽으로 지원. `codex exec`(OpenAI), `gemini -p`(Gemini) 헤드리스 호출과
  `openai`·`google-genai` SDK 경로 추가. 셋 다 토큰 사용량을 기록한다
- **`models use`** — 사용할 모델 설정. 인자 없이 실행하면 공급자·모델·저장 위치를
  고르는 대화형. `--role`로 역할별(compile/audit/metadata) 분리, `--global`로 전 프로젝트 기본값
- **`models show`** — 현재 유효 설정, 각 역할의 실제 호출 경로, 공급자별로 지금 쓸 수
  있는 인증 수단(OAuth ○/× · API key ○/×)과 막힌 이유를 한 화면에
- **`models auth <순서>`** — 인증 우선순위(`llm.auth_order`) 변경
- **전역 기본 설정 `~/.llm-wiki/config.yaml`** — 프로젝트마다 다시 고르지 않아도 되도록.
  프로젝트 설정이 항목 단위로 덮어쓰며, `init`은 전역값을 기본값으로 제시한다
- **모델→공급자 자동 판별** — 레지스트리 조회 후 접두사 추정. 판별이 안 되면
  `openai/<모델명>` 접두사 또는 `models add`로 해결 (새 모델 출시에 코드 수정 불필요)
- **실행 중 자동 전환** — `auth_order`로 만든 후보를 묶어 두고, 앞의 경로가 실패하면
  (로그인 만료·구독 등급 문제 등) 다음 경로로 넘어간다. 설치 여부만 보던 기존 판정의 한계 해소
- extras 분리: `[anthropic]`·`[openai]`·`[gemini]`·`[all]` (OAuth만 쓰면 설치 불필요)

### Changed
- `init`의 모델 질문이 공급자별 등록 모델과 사용 가능한 인증 경로를 보여주고,
  새로 입력한 모델명을 레지스트리에 저장한다 (README에 적혀 있었으나 미구현이던 동작)
- `models` 기본 동작이 `list` → `show`
- 백엔드 이름 `oauth-claude` → `oauth-anthropic`. 에이전트형 여부를 이름 하드코딩 대신
  `Backend.agentic` 속성으로 판정 (codex·gemini CLI도 원자료를 직접 읽는다)
- 모델 레지스트리가 실제로 쓰인다 — 종전에는 기록만 하고 아무도 읽지 않았음.
  공급자 별칭(`claude`→`anthropic`, `google`→`gemini`) 정규화

### Fixed
- `find_project_root`가 홈 디렉터리를 프로젝트로 오인하던 문제 — `~/.llm-wiki`가
  전역 설정 보관소라, 홈 아래 아무 폴더에서나 홈이 프로젝트 루트로 잡혔다
- `BackendError`가 `SystemExit` 상속이라 `compile`의 자료별 실패 격리(`except Exception`)를
  통과해 실행 전체를 중단시키던 문제 — `RuntimeError` 상속으로 바꾸고 CLI 최상단에서 안내 출력
- 설정 변경이 `config.yaml`을 통째로 다시 쓰면서 주석·순서를 날리던 문제 —
  해당 키만 교체하는 `update_yamlish` 도입

## [0.2.1] — 2026-08-12

### Fixed
- **Windows 치명 버그**: lock의 프로세스 생존 확인이 os.kill(pid, 0)을 사용했는데,
  Windows에서 이는 확인이 아니라 프로세스 종료다 — stale lock 검사가 실행 중인
  편찬을 죽일 수 있었음. Windows에서는 OpenProcess 조회로 교체

### Added
- README: Windows/Linux 사용 안내 (설치 명령, OS별 차이 표, 작업 스케줄러 예시)

## [0.2.0] — 2026-08-12

온보딩·타 도구 연동 정비 (사용자 검수 문답에서 발굴된 공백들의 해소).

### Added
- `setup-agent claude|codex|all` — 전역 에이전트 어댑터 설치 명령.
  Claude 전역 `/wiki-init` 스킬, Codex `/wiki-init`·`ingest`·`compile`·`audit` 프롬프트 4종을
  위치 무관으로 1회 설치 (기존의 경로 기반 cp 안내는 pipx URL 설치 사용자에게 원본 파일이
  없어 실행 불가능했던 문제의 근본 해결)
- `serve-mcp --project <경로>` — 전역 설정으로 서버를 등록하는 MCP 클라이언트
  (Codex config.toml, Gemini CLI settings.json, Antigravity, OpenClaw) 지원
- `--version` 플래그, 버전 단일 소스화 (pyproject가 패키지 버전을 읽음)
- 전역 어댑터를 패키지 데이터(`templates/agents/`)로 내장

### Changed
- README 전면 정비: GitHub 주소 설치 방식 기본화, init 3입구(터미널/자연어/전역 스킬) 표,
  도구별 시작 준비 표(Claude Code/Codex), 클라이언트별 MCP 등록 예시, Codex의 역할
  명시(에이전트 입구·MCP 클라이언트 — 편찬 백엔드는 백로그)

### Removed
- `extras/` 폴더 (전역 어댑터가 패키지 데이터로 이동)

## [0.1.0] — 2026-08-11

최초 공개 — Phase 0 파일럿(project-a, FEP 착용형 보행보조 로봇 과제)으로 검증된
워크플로우·템플릿을 Python CLI로 이관.

### Added
- 명령 13종: `init`(대화형 온보딩·멱등) / `ingest`(해시·중복·파일명 정규화·업로더 귀속·분류) /
  `compile`(내장 편찬 파이프라인) / `audit` / `review`(+`apply`·`reject`·`--all`) / `status` /
  `search`(SQLite FTS5) / `reindex` / `serve-mcp` / `notify` / `rollback` / `diff` / `models`
- LLM 백엔드 추상화: OAuth(Claude CLI) → API key(anthropic) → Ollama 자동 폴백,
  민감 프로젝트(`external_llm_allowed: false`)는 Ollama 코드 강제
- 코드 수준 안전장치 (적대 테스트 통과): AI 산출물 status는 draft 강제, 쓰기 경로
  화이트리스트(30_Wiki 한정), reviewed 이상 문서 수정 시도는 제안(`_Proposals`)으로 자동
  강등, 코멘트 섹션 불가침, lock(이중 실행 방지·stale 자동 해제), 실행 전 자동 백업·롤백,
  `review apply` 병합 시 status·reviewer 원문 복원
- MCP stdio 서버 (표준 라이브러리 구현): wiki_search / wiki_read / wiki_status /
  wiki_request_edit / wiki_add_comment / wiki_save_qa / wiki_activity — 질의 실명 로그
- 실행별 토큰·비용 기록 (`metrics/costs.jsonl`)
- 템플릿 팩 내장 (init이 설치): 표준 폴더 구조, AGENTS.md·CLAUDE.md, 워크플로우 3종,
  문서 템플릿, 프로젝트 스킬·Codex 어댑터
- 테스트 훅 `LLM_WIKI_FAKE` (LLM 없이 파이프라인 검증)
- 코어 의존성 0 (Python 3.12+ 표준 라이브러리만), 선택 extras `[pdf]`·`[llm]`
