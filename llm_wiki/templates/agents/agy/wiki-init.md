---
name: wiki-init
description: 현재 폴더를 llm-wiki 프로젝트로 초기화한다. "위키 프로젝트 만들어줘", "llm-wiki 시작", "wiki init" 요청 시 사용.
---

현재 폴더를 GIST HUR Group LLM-Wiki 프로젝트로 초기화하라. 절차:

1. `llm-wiki` 명령이 설치되어 있는지 확인한다 (`which llm-wiki`). 없으면
   `pipx install "git+https://github.com/pilwonhur/llm-wiki.git"` 를 안내한다 (Python 3.12+ 필요).
2. 온보딩 정보를 **대화로** 수집한다 (모르면 물어보고, 건너뛰기 허용):
   프로젝트 정식 명칭, 한 줄 목적, 구성원(쉼표 구분), reviewer 실명,
   출력 언어(기본 한국어), 외부 LLM 전송 허용 여부(IRB·산학 등 민감 자료면 아니오), 편찬 모델.
3. `llm-wiki init --yes` 를 실행한다 (구조·규칙·스킬 어댑터 자동 설치, 멱등).
4. 수집한 답을 반영한다: `.llm-wiki/config.yaml`의 project·reviewer·language·
   external_llm_allowed·model, `00_Project/README.md`, `00_Project/members.md`,
   구성원별 `10_Inbox/<이름>/` 폴더 생성.
5. 편찬에 쓸 모델을 정한다: `llm-wiki models show` 로 현황을 보이고,
   Antigravity 구독을 쓸 거면 `llm-wiki models use gemini-3.6-flash-high` 처럼 안내한다.
6. 완료 보고: 구조 요약 + 다음 단계 ("자료를 10_Inbox/<이름>/에 넣고 /wiki-ingest").

주의: 기존 파일은 절대 덮어쓰지 않는다 (init은 멱등).
