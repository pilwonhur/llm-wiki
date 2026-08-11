"""llm-wiki CLI 진입점 (표준 라이브러리 argparse — 의존성 0)."""
from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="llm-wiki",
        description="GIST HURGroup LLM-Wiki — 연구실 프로젝트별 지식 편찬 시스템")
    from . import __version__
    p.add_argument("--version", action="version", version=f"llm-wiki {__version__}")
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("init", help="프로젝트 구조 생성 + 온보딩")
    sp.add_argument("path", nargs="?", help="프로젝트 폴더 (기본: 현재 폴더)")
    sp.add_argument("--yes", action="store_true", help="질문 없이 기본값으로")

    sp = sub.add_parser("ingest", help="10_Inbox 자료 접수·분류")
    sp.add_argument("--yes", action="store_true", help="분류 추정을 질문 없이 수용")

    sp = sub.add_parser("compile", help="Wiki 편찬 (백업 선행)")
    sp.add_argument("--force", action="store_true", help="미처리 자료가 없어도 실행")

    sub.add_parser("audit", help="품질 감사 리포트 생성 (수정 없음)")
    sp = sub.add_parser("review", help="검토 대기 목록 / 제안 승인·거부")
    sp.add_argument("action", nargs="?", choices=["apply", "reject"],
                    help="apply <제안> = 승인·반영 / reject <제안> = 거부·정리")
    sp.add_argument("proposal", nargs="?", help="제안 파일명 (일부만 써도 매칭)")
    sp.add_argument("--all", action="store_true", help="대기 중인 제안 전부 승인·반영")
    sp.add_argument("--reason", default="", help="거부 사유 (reject 시)")
    sub.add_parser("status", help="프로젝트 현황 요약")

    sp = sub.add_parser("rollback", help="백업 시점으로 복원")
    sp.add_argument("run_id", nargs="?", help="실행 ID (기본: 최근 백업)")

    sp = sub.add_parser("diff", help="백업 대비 변경 요약")
    sp.add_argument("run_id", nargs="?")
    sp.add_argument("-v", "--verbose", action="store_true")

    sp = sub.add_parser("models", help="모델 레지스트리 (~/.llm-wiki/models.yaml)")
    sp.add_argument("action", nargs="?", choices=["list", "add", "remove"], default="list")
    sp.add_argument("provider", nargs="?")
    sp.add_argument("model_id", nargs="?")

    sp = sub.add_parser("search", help="Wiki 전문 검색 (SQLite FTS5)")
    sp.add_argument("query", nargs="+")
    sp.add_argument("--no-draft", action="store_true", help="approved/reviewed만")

    sub.add_parser("reindex", help="검색 인덱스 재구축")
    sp = sub.add_parser("serve-mcp", help="MCP stdio 서버 (외부 AI 비서 연동)")
    sp.add_argument("--project", help="프로젝트 폴더 경로 (전역 등록 클라이언트용 — 미지정 시 현재 위치에서 탐색)")

    sp = sub.add_parser("setup-agent", help="전역 에이전트 어댑터 설치 (/wiki-init 등)")
    sp.add_argument("tool", choices=["claude", "codex", "all"], help="대상 도구")

    sp = sub.add_parser("notify", help="검토 대기 알림 발송 (0건이면 미발송)")
    sp.add_argument("--dry-run", action="store_true", help="콘솔 출력만")

    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if not args.cmd:
        build_parser().print_help()
        return
    from . import (audit_cmd, compile_cmd, ingest_cmd, init_cmd, mcp_cmd,
                   misc_cmd, notify_cmd, search_cmd)
    dispatch = {
        "init": init_cmd.cmd_init,
        "ingest": ingest_cmd.cmd_ingest,
        "compile": compile_cmd.cmd_compile,
        "audit": audit_cmd.cmd_audit,
        "review": misc_cmd.cmd_review,
        "status": misc_cmd.cmd_status,
        "rollback": misc_cmd.cmd_rollback,
        "diff": misc_cmd.cmd_diff,
        "models": misc_cmd.cmd_models,
        "search": search_cmd.cmd_search,
        "reindex": search_cmd.cmd_reindex,
        "serve-mcp": mcp_cmd.cmd_serve_mcp,
        "notify": notify_cmd.cmd_notify,
        "setup-agent": misc_cmd.cmd_setup_agent,
    }
    try:
        dispatch[args.cmd](args)
    except KeyboardInterrupt:
        sys.exit("\n중단됨")


if __name__ == "__main__":
    main()
