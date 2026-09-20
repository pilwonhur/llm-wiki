"""0.7.2 회귀 테스트 — 첫 실사용에서 나온 버그를 고정한다.

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


class CompileTests(ProjectCase):
    DOC = ("---\ntype: concept\nproject: \"모델이 추측한 이름\"\nstatus: approved\n"
           "reviewer: 아무개\ngenerated_by: llm-wiki phase0\n---\n\n# 제목\n\n본문\n")

    def compile_with(self, items: list) -> subprocess.CompletedProcess:
        self.put_inbox("source-note.md", "원자료")
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
