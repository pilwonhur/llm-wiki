# Workflow: ingest — 10_Inbox 자료 접수

목표: `10_Inbox`의 새 파일을 등록·분류해 `20_Sources`로 이동한다. 시작 전 `AGENTS.md` 규칙을 준수한다.

## 절차

1. `10_Inbox/`를 재귀적으로 스캔한다 (숨김 파일과 `*-회의록초안.md` 제외). **업로더 귀속 규약**: `10_Inbox/<멤버명>/` 하위폴더의 파일은 그 멤버의 업로드로 기록한다 (`added_by: <멤버명>`, members.md와 대조). Inbox 최상위에 직접 놓인 파일은 `added_by: unknown`으로 등록하고 질문 목록에 "업로더 확인"을 올린다.
2. 각 파일에 대해 순서대로:
   1. **해시 계산**: SHA-256 (macOS/Linux `shasum -a 256`, Windows `certutil -hashfile <파일> SHA256`).
   2. **중복 검사**: `.llm-wiki/manifest.json`에서 동일 해시 검색. 있으면 이동하지 않고 로그에 "중복 (기존: <경로>)"으로 기록하고 다음 파일로 넘어간다. 파일은 삭제하지 않는다 (사람이 결정).
   3. **메타데이터 추출**: 내용을 읽고 제목, 저자, 연도, 자료 종류를 파악한다. 종류: `paper`(논문) / `meeting`(회의록·회의자료) / `experiment`(실험 기록) / `dataset`(데이터셋 설명) / `webclip`(웹 자료) / `qa`(Q&A 세션) / `proposal`(연구계획서·제안서·과제 문서).
   4. **분류·이동**: 종류가 명확하면 대응 폴더로 이동한다 — Papers / Meeting-Notes / Experiments / Datasets / Web-Clips / QA-Sessions / Proposals. 파일명은 유지한다. **종류가 불명확하면 이동하지 않고** 질문 목록에 "어느 분류인지" 기록한다.
   5. **manifest 등록**: `.llm-wiki/manifest.json`의 `sources` 배열에 추가:
      ```json
      {"path": "20_Sources/Papers/파일명.pdf", "hash": "...", "title": "...",
       "authors": "...", "year": 2026, "type": "paper",
       "added": "YYYY-MM-DD", "added_by": "<멤버명|unknown>", "processed": false}
      ```
3. **녹취록 특례**: 파일이 회의 녹취록(전사문)이면 이동하지 않는다. 대신 회의록 정리본 초안을 `10_Inbox/<원본명>-회의록초안.md`로 생성하고 (일시·참석자·논의·결정사항 후보·액션 아이템), 사람 확인 후 다시 ingest하도록 요청 목록에 기록한다.
4. **텍스트 추출이 안 되는 파일** (스캔본 PDF, 손상 파일, 미지원 형식): 이동하지 않고 사유와 함께 보고 목록에 기록한다. 실패한 파일 때문에 나머지 처리를 멈추지 않는다.
5. **로그**: `.llm-wiki/processing-log.md`에 append — 실행 일시, 처리/중복/보류 파일 목록, 질문 목록.
6. **보고**: 사람에게 요약 — 등록 n건, 중복 n건, 분류 질문 n건, 녹취록 초안 n건, 실패 n건.

## 금지

- `20_Sources` 기존 파일 수정 금지. 어떤 파일도 삭제 금지. 분류 확신이 없으면 추측으로 이동하지 말고 물어볼 것.
