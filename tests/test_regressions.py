"""회귀 테스트 — 실사용에서 나온 버그를 고정한다 (0.7.2~).

실행: `python -m unittest discover -s tests -v` (추가 의존성 없음).
CLI를 하위 프로세스로 돌린다. HOME을 임시 폴더로 바꿔 사용자의 `~/.llm-wiki` 전역 설정을
읽지도 쓰지도 않게 한다. LLM은 `LLM_WIKI_FAKE` 훅으로 대체한다.
"""
import json
import os
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def nfd(s: str) -> str:
    return unicodedata.normalize("NFD", s)


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


class ProjectCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name).resolve()
        self.home = base / "home"
        self.root = base / "proj"
        self.home.mkdir()
        self.root.mkdir()
        self.env = {**os.environ, "HOME": str(self.home), "PYTHONPATH": str(REPO),
                    "PYTHONIOENCODING": "utf-8"}
        self.env.pop("LLM_WIKI_FAKE", None)
        r = self.run_cli("init", "--yes")
        self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        self._tmp.cleanup()

    def run_cli(self, *args, stdin: str | None = None, fake: Path | None = None):
        env = dict(self.env)
        if fake:
            env["LLM_WIKI_FAKE"] = str(fake)
        return subprocess.run([sys.executable, "-m", "llm_wiki", *args], cwd=self.root,
                              env=env, capture_output=True, text=True,
                              input=stdin if stdin is not None else "",
                              timeout=120)

    def manifest(self) -> dict:
        return json.loads((self.root / ".llm-wiki" / "manifest.json").read_text(encoding="utf-8"))

    def inbox_files(self) -> list[str]:
        inbox = self.root / "10_Inbox"
        return sorted(nfc(p.name) for p in inbox.rglob("*")
                      if p.is_file() and not p.name.startswith("."))

    def put_inbox(self, name: str, body: str = "본문") -> None:
        d = self.root / "10_Inbox" / "홍길동"
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(body, encoding="utf-8")


class IngestTests(ProjectCase):
    def test_nfd_filename_is_classified_by_korean_keyword(self):
        """macOS·Dropbox가 돌려주는 NFD 파일명에서도 '회의'가 meeting으로 잡힌다."""
        from llm_wiki.ingest_cmd import _guess_type
        self.assertEqual(_guess_type(nfd("5차 기획회의 진행 계획.pdf")), "meeting")
        self.assertEqual(_guess_type(nfd("연구계획서_최종.pdf")), "proposal")

        self.put_inbox(nfd("5차 기획회의 진행 계획.md"))
        r = self.run_cli("ingest", "--yes")
        self.assertEqual(r.returncode, 0, r.stderr)
        src = self.manifest()["sources"]
        self.assertEqual([s["type"] for s in src], ["meeting"])
        self.assertTrue(src[0]["path"].startswith("20_Sources/Meeting-Notes/"))

    def test_input_cut_off_moves_nothing(self):
        """분류 질문 도중 입력이 끊기면(에이전트·cron) 이동·등록된 파일이 없어야 한다."""
        self.put_inbox("a-note.md", "하나")
        self.put_inbox("b-note.md", "둘")
        before = self.inbox_files()
        r = self.run_cli("ingest", stdin="meeting\n")  # 두 번째 질문에서 EOF
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.inbox_files(), before)
        self.assertEqual(self.manifest()["sources"], [])

    def test_piped_answers_still_work(self):
        """표준입력으로 분류 답을 넘기는 비대화형 사용은 그대로 동작한다."""
        self.put_inbox("a-note.md", "하나")
        self.put_inbox("b-note.md", "둘")
        r = self.run_cli("ingest", stdin="meeting\nproposal\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([s["type"] for s in self.manifest()["sources"]],
                         ["meeting", "proposal"])
        self.assertEqual(self.inbox_files(), [])


class SourceTypeTests(ProjectCase):
    """0.8.0 — 참고자료(reference) 분류 + 확신 없는 추정은 paper가 아니라 보류."""

    def test_guess_from_field_filenames(self):
        from llm_wiki.ingest_cmd import HOLD, _guess_type
        cases = {  # 2026-09-20·24 실사용에서 사람이 확정한 분류
            "회의록.pdf": "meeting",
            "회의자료 송부 메일.pdf": "meeting",
            "과제 소개 자료.pdf": "proposal",
            "기획 과제 최종 보고서 양식.pdf": "proposal",
            "참여기업 회사소개서.pdf": "reference",
            "제품 카탈로그 2026.pdf": "reference",
            "kim2026_adaptive_gait.pdf": "paper",
            "2401.12345v2.pdf": "paper",
            "협업 요청 메일.pdf": HOLD,    # 예전에는 paper로 떨어졌다
            "딥리서치 보고서.md": HOLD,
        }
        for name, want in cases.items():
            with self.subTest(name=name):
                self.assertEqual(_guess_type(nfd(name)), want)

    def test_guess_uses_text_head(self):
        from llm_wiki.ingest_cmd import HOLD, _guess_type
        self.assertEqual(_guess_type("notes.md", "---\ntags: [project, meeting-minutes]\n---\n"),
                         "meeting")
        self.assertEqual(_guess_type("a.md", "---\nsource: https://example.com/x\n---\n"),
                         "webclip")
        self.assertEqual(_guess_type("a.md", "Abstract\n...\ndoi: 10.1000/xyz"), "paper")
        mail = "From: a@x.com\nTo: b@y.com\nSubject: 자료\n\ndoi: 10.1000/xyz"
        self.assertEqual(_guess_type("a.md", mail), HOLD)

    def test_yes_holds_unclassifiable_file(self):
        """--yes(야간 배치)에서 추정할 수 없는 파일은 옮기지 않는다."""
        self.put_inbox("회의 메모.md", "하나")
        self.put_inbox("무제 문서.md", "둘")
        r = self.run_cli("ingest", "--yes")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([s["type"] for s in self.manifest()["sources"]], ["meeting"])
        self.assertEqual(self.inbox_files(), ["무제 문서.md"])
        self.assertIn("분류 미정", r.stdout)

    def test_reference_goes_to_references_even_without_folder(self):
        """References/ 폴더가 없는 기존 프로젝트에서도 reference로 등록된다."""
        folder = self.root / "20_Sources" / "References"
        for p in folder.iterdir():
            p.unlink()
        folder.rmdir()
        self.put_inbox("무제 문서.md")
        r = self.run_cli("ingest", stdin="reference\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        src = self.manifest()["sources"]
        self.assertEqual([s["type"] for s in src], ["reference"])
        self.assertTrue(src[0]["path"].startswith("20_Sources/References/"))

    def test_enter_on_hold_default_and_unknown_answer_hold(self):
        self.put_inbox("무제 문서.md", "하나")
        self.put_inbox("무제 문서2.md", "둘")
        r = self.run_cli("ingest", stdin="\nrefrence\n")  # Enter(기본 h), 오타
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.manifest()["sources"], [])
        self.assertEqual(len(self.inbox_files()), 2)

    def test_compile_prompt_marks_reference_claims(self):
        from llm_wiki.compile_cmd import _build_prompt
        from llm_wiki.core import Project
        proj = Project(self.root)
        args = ("", "", "", False, "본문")
        ref = _build_prompt(proj, {"path": "20_Sources/References/x.pdf", "type": "reference"}, *args)
        paper = _build_prompt(proj, {"path": "20_Sources/Papers/x.pdf", "type": "paper"}, *args)
        self.assertIn("주체를 밝혀", ref)
        self.assertNotIn("주체를 밝혀", paper)


class CompileTests(ProjectCase):
    DOC = ("---\ntype: concept\nproject: \"모델이 추측한 이름\"\nstatus: approved\n"
           "reviewer: 아무개\ngenerated_by: llm-wiki phase0\n---\n\n# 제목\n\n본문\n")

    def compile_with(self, items: list) -> subprocess.CompletedProcess:
        self.put_inbox("meeting-note.md", "원자료")
        r = self.run_cli("ingest", "--yes")
        self.assertEqual(r.returncode, 0, r.stderr)
        fake = Path(self._tmp.name) / "fake.json"
        fake.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        return self.run_cli("compile", fake=fake)

    def test_sibling_folder_with_wiki_prefix_is_blocked(self):
        """`30_Wiki_x/` 같은 형제 폴더는 30_Wiki 안이 아니다 (N1)."""
        r = self.compile_with([
            {"action": "create", "path": "30_Wiki_x/evil.md", "content": self.DOC},
            {"action": "create", "path": "30_Wiki/../00_Project/evil.md", "content": self.DOC},
            {"action": "create", "path": "30_Wiki/Concepts/ok.md", "content": self.DOC},
        ])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.root / "30_Wiki_x").exists())
        self.assertFalse((self.root / "00_Project" / "evil.md").exists())
        self.assertTrue((self.root / "30_Wiki" / "Concepts" / "ok.md").exists())
        self.assertEqual(r.stdout.count("차단"), 2)

    def test_frontmatter_provenance_is_enforced(self):
        """status·reviewer·project·generated_by는 모델 출력이 아니라 코드가 정한다."""
        cfg = self.root / ".llm-wiki" / "config.yaml"
        text = cfg.read_text(encoding="utf-8")
        lines = ['project: "정식 과제명"' if ln.startswith("project:") else ln
                 for ln in text.splitlines()]
        cfg.write_text("\n".join(lines) + "\n", encoding="utf-8")

        r = self.compile_with([
            {"action": "create", "path": "30_Wiki/Concepts/doc.md", "content": self.DOC}])
        self.assertEqual(r.returncode, 0, r.stderr)
        out = (self.root / "30_Wiki" / "Concepts" / "doc.md").read_text(encoding="utf-8")
        self.assertIn("\nstatus: draft\n", out)
        self.assertIn("\nreviewer:\n", out)
        self.assertIn('\nproject: "정식 과제명"\n', out)
        self.assertNotIn("phase0", out)
        self.assertRegex(out, r"\ngenerated_by: llm-wiki \d+\.\d+\.\d+ / fake\S* / run \S+\n")
        self.assertIn("# 제목\n\n본문", out)  # 본문은 그대로


if __name__ == "__main__":
    unittest.main()
