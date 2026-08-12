---
name: wiki-audit
description: Wiki 품질 감사 리포트를 생성한다. "감사", "품질 점검", "audit" 요청 시 사용.
---

`llm-wiki audit` 을 실행하고 결과를 해설하라.

- audit은 **보고만** 한다 — 발견한 문제를 임의로 고치지 않는다.
- 결과 보고: 끊어진 링크, 페이지 인용 불일치, status 이상, 충돌 사본 등.
- 사용자가 수정을 원하면 어떤 문서를 어떻게 고칠지 먼저 제안하고 동의를 받는다.
- CLI가 없는 환경이라면 `.llm-wiki/workflows/audit.md` 절차를 수행한다.
