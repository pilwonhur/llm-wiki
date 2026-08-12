---
name: wiki-ingest
description: 10_Inbox 자료를 접수·분류해 20_Sources에 등록한다. "인박스 정리", "자료 등록", "ingest" 요청 시 사용.
---

`llm-wiki ingest` 를 실행하고 결과를 해설하라.

- 실행 전 프로젝트 루트인지 확인한다 (`.llm-wiki/` 존재).
- 분류가 모호해 보류(h)된 항목이 있으면 사용자에게 물어 분류를 정하고 다시 실행한다.
- 결과 보고: 등록/중복/보류 건수, 업로더 귀속, 파일명 정규화 내역.
- CLI가 없는 환경이라면 `AGENTS.md` 절대 규칙을 지키며
  `.llm-wiki/workflows/ingest.md` 절차를 그대로 수행한다.
