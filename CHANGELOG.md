# Changelog

GIST HUR Group LLM-Wiki의 버전별 변경 이력. 형식은 [Keep a Changelog](https://keepachangelog.com/ko/)를 따르고,
버전은 [유의적 버전](https://semver.org/lang/ko/)(주.부.수)을 따른다.

- **주(major)**: 프로젝트 폴더 구조·manifest 등 데이터 형식이 바뀌어 마이그레이션이 필요할 때
- **부(minor)**: 명령·기능 추가 (기존 프로젝트 그대로 사용 가능)
- **수(patch)**: 버그 수정·문서 정비

업데이트: `pipx reinstall llm-wiki` / 버전 확인: `llm-wiki --version`

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
