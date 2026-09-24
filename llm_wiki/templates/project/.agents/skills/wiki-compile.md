---
name: wiki-compile
description: 미처리 원자료를 근거로 30_Wiki 문서를 편찬한다. "위키 만들어줘", "편찬", "compile" 요청 시 사용.
---

`llm-wiki compile` 을 실행하고 결과를 해설하라. 백업 없이 시작하지 않는다.

- 편찬은 CLI가 수행한다 (백업·lock·쓰기 경로 제한·status draft 강제가 코드로 걸려 있다).
- 실행 전 `llm-wiki models show` 로 어떤 백엔드가 쓰일지 확인해 사용자에게 알린다.
- 결과 보고: 생성·갱신·제안 문서 목록, 실패 건, 토큰·비용.
- 결정 후보(`_Proposals/decisions-…`)가 있으면 후보마다 저장 명령 한 줄을 준다:
  `llm-wiki review apply "<후보 파일명>"` — 사람에게 `40_Decisions` 파일을 직접 만들게 하지 않는다.
- 완료 후 다음 단계 안내: `llm-wiki review` 로 검토.
- CLI가 없는 환경이라면 `AGENTS.md` 절대 규칙을 지키며
  `.llm-wiki/workflows/compile.md` 절차를 그대로 수행한다.
