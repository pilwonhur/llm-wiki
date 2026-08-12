# Changelog

GIST HUR Group LLM-Wiki의 버전별 변경 이력. 형식은 [Keep a Changelog](https://keepachangelog.com/ko/)를 따르고,
버전은 [유의적 버전](https://semver.org/lang/ko/)(주.부.수)을 따른다.

- **주(major)**: 프로젝트 폴더 구조·manifest 등 데이터 형식이 바뀌어 마이그레이션이 필요할 때
- **부(minor)**: 명령·기능 추가 (기존 프로젝트 그대로 사용 가능)
- **수(patch)**: 버그 수정·문서 정비

업데이트: `pipx reinstall llm-wiki` / 버전 확인: `llm-wiki --version`

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
