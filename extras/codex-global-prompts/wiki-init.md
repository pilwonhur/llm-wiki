현재 폴더를 GIST HUR Group LLM-Wiki 프로젝트로 초기화하라. 절차:
1. `which llm-wiki`로 설치 확인 — 없으면 `pipx install "git+https://github.com/pilwonhur/llm-wiki.git"` 안내.
2. 온보딩 정보를 대화로 수집: 프로젝트 정식 명칭, 한 줄 목적, 구성원(쉼표), reviewer 실명,
   출력 언어(기본 한국어), 외부 LLM 전송 허용 여부(민감 자료면 아니오), 편찬 모델(기본 claude-fable-5).
3. `llm-wiki init --yes` 실행 (멱등 — 기존 파일 불가침).
4. 수집한 답을 반영: .llm-wiki/config.yaml (project/reviewer/language/external_llm_allowed/model),
   00_Project/README.md·members.md, 구성원별 10_Inbox/<이름>/ 폴더.
5. 구조 요약과 다음 단계 안내 ("자료를 10_Inbox/<이름>/에 넣고 /wiki-ingest").
