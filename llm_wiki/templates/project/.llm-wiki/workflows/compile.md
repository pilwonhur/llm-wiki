# Workflow: compile — Wiki 편찬

목표: manifest에서 `processed: false`인 원자료를 근거로 `30_Wiki` 문서를 생성·갱신한다. 시작 전 `AGENTS.md` 규칙을 준수한다.

## 사전 준비

1. `.llm-wiki/manifest.json`에서 `processed: false` 항목을 목록화한다. 없으면 "처리할 자료 없음"을 보고하고 종료한다.
2. **백업**: 실행 ID를 `YYYYMMDD-HHMM` 형식으로 정하고, `30_Wiki`의 기존 문서 전체를 `.llm-wiki/backups/<실행ID>/`로 복사한다. 백업 없이는 편찬을 시작하지 않는다.
3. `00_Project/scope.md`와 `glossary.md`를 읽어 프로젝트 범위와 용어 기준을 파악한다.

## 자료별 처리 (한 번에 한 파일씩, 순서대로)

1. 원자료를 읽고 핵심 요소를 추출한다: 개념(Concepts), 방법(Methods), 인물(People), 장비(Equipment), 결과·발견(Findings), 미해결 질문(Questions).
2. 각 요소에 대해 기존 `30_Wiki` 전체를 검색한다 — 제목·frontmatter `aliases`·glossary를 대조하고, 같은 개념의 **다른 표기(영문/국문/약어)** 를 특히 주의한다.
3. 문서 생성/갱신을 결정한다:
   - **기존 문서 없음** → `.llm-wiki/templates/wiki-doc.md` 템플릿대로 새 문서 생성 (`status: draft`), 대응 하위 폴더에 배치
   - **기존 문서가 `draft`** → 직접 갱신: 근거 추가, 본문 보강, `updated` 갱신. `## 코멘트` 섹션은 그대로 보존
   - **기존 문서가 `reviewed`/`approved`** → 본문을 건드리지 않고 `30_Wiki/_Proposals/<문서명>-<실행ID>.md`에 제안 작성 (현재 내용 / 제안 내용 / 근거)
4. **출처**: 모든 핵심 주장에 `[[경로#page=N]]` 또는 `[[경로#heading]]`을 단다. PDF 페이지는 **항상 PDF 물리 페이지 번호**(뷰어의 #page=N 기준)를 사용한다 — 문서에 인쇄된 페이지 번호는 표지·서문 때문에 어긋날 수 있으므로 사용 금지. 인용 전 해당 페이지를 실제로 열어 내용을 확인한다. 근거를 못 찾은 서술은 warning callout 처리.
5. **모순 처리**: 새 자료가 기존 Wiki 내용과 상충하면 임의로 한쪽을 고르지 않는다. 해당 문서의 `## 상충하는 근거`에 양측을 출처와 함께 기록하고, 실행 보고에 disputed 후보로 올린다.
6. **회의록인 경우**: 논의 내용은 위 절차대로 처리하고, 결정사항 후보는 별도로 `30_Wiki/_Proposals/decisions-<실행ID>.md`에 모은다 (`40_Decisions`에 직접 쓰지 않는다).
7. **Q&A 세션인 경우**: 유형 태그를 확인한다 — 연구자 의견은 1차 진술로 인용, 웹 정보는 기록된 URL을 출처로, AI 사전지식 태그 내용은 warning callout을 유지한 채 반영한다. Q&A에서 유래한 내용의 근거 인용에는 질문자 실명을 병기한다.
8. 처리를 마친 자료는 manifest에서 `processed: true`로 갱신한다.
9. 한 파일 처리에 실패하면 사유를 기록하고 다음 파일로 진행한다 (전체 중단 금지).

## 마무리

- `.llm-wiki/processing-log.md`에 append: 실행 ID, 처리 파일, 생성/갱신 문서 목록, 제안 건수, disputed 후보, 실패와 사유.
- 사람에게 요약 보고: **검토가 필요한 것**을 앞세운다 — 새 draft n건, 변경 제안 n건, disputed 후보 n건, 질문 n건. 각 항목에 파일 경로를 병기한다.

## 금지

- `status`는 `draft`만 쓴다. 원자료·코멘트 섹션 수정 금지. 사람이 편집한 흔적이 있는 문서(백업본과 비교해 당신이 만들지 않은 변경이 있는 문서)는 덮어쓰지 말고 제안으로 전환한다.
