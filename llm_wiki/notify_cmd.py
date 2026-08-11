"""`llm-wiki notify` — 검토 알림 (F4.5). 대기 0건이면 보내지 않는다.

채널은 config `notifications`로 설정. 기본은 콘솔 + macOS 알림.
cron 예: 매일 아침 `llm-wiki notify` (compile 야간 배치와 조합 = daily digest).
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request

from .core import frontmatter, require_project


def _pending(proj):
    drafts, disputed = [], []
    for p in proj.wiki_docs():
        fm = frontmatter(p.read_text(encoding="utf-8"))
        rel = str(p.relative_to(proj.root / "30_Wiki"))
        if fm.get("status") == "draft":
            drafts.append(rel)
        elif fm.get("status") == "disputed":
            disputed.append(rel)
    qa = list((proj.root / "10_Inbox" / "_qa").glob("*.md")) \
        if (proj.root / "10_Inbox" / "_qa").exists() else []
    reqs = list((proj.root / "10_Inbox" / "_requests").glob("*.md")) \
        if (proj.root / "10_Inbox" / "_requests").exists() else []
    return drafts, list(proj.proposals()), disputed, qa, reqs


def cmd_notify(args) -> None:
    proj = require_project()
    cfg = proj.config()
    drafts, props, disputed, qa, reqs = _pending(proj)
    total = len(drafts) + len(props) + len(disputed) + len(qa) + len(reqs)
    project = cfg.get("project", proj.root.name)

    if total == 0:
        print("검토 대기 0건 — 알림을 보내지 않습니다. ✓")
        return

    title = f"[LLM-Wiki] {project} 검토 대기 {total}건"
    lines = []
    if drafts:
        lines.append(f"신규 draft {len(drafts)}건: " + ", ".join(drafts[:3])
                     + (" 외" if len(drafts) > 3 else ""))
    if props:
        lines.append(f"변경 제안 {len(props)}건")
    if disputed:
        lines.append(f"disputed 판정 대기 {len(disputed)}건")
    if qa:
        lines.append(f"Q&A 승격 대기 {len(qa)}건")
    if reqs:
        lines.append(f"편찬 요청 {len(reqs)}건")
    lines.append("확인: llm-wiki review")
    body = "\n".join(lines)

    print(title + "\n" + body)  # 콘솔 채널 (항상)
    sent = ["console"]

    ncfg = cfg.get("notifications") or {}
    # macOS 알림 (기본 on, notifications.macos: false 로 끔)
    if sys.platform == "darwin" and ncfg.get("macos", True) and not args.dry_run:
        try:
            subprocess.run(["osascript", "-e",
                            f'display notification "{body[:120]}" with title "{title}"'],
                           capture_output=True, timeout=10)
            sent.append("macos")
        except Exception:
            pass
    # webhook (Slack/Discord 등)
    url = ncfg.get("webhook")
    if url and not args.dry_run:
        try:
            req = urllib.request.Request(
                url, data=json.dumps({"text": f"{title}\n{body}"}).encode(),
                headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10)
            sent.append("webhook")
        except Exception as e:
            print(f"webhook 실패 (편찬에는 영향 없음): {e}")
    # 이메일 (notifications.email_to + smtp_host 설정 시)
    to, host = ncfg.get("email_to"), ncfg.get("smtp_host")
    if to and host and not args.dry_run:
        try:
            import smtplib
            from email.mime.text import MIMEText
            msg = MIMEText(body, _charset="utf-8")
            msg["Subject"], msg["From"], msg["To"] = title, ncfg.get("smtp_from", to), to
            with smtplib.SMTP(host, int(ncfg.get("smtp_port", 587)), timeout=15) as s:
                s.starttls()
                if ncfg.get("smtp_user"):
                    s.login(ncfg["smtp_user"], ncfg.get("smtp_pass", ""))
                s.send_message(msg)
            sent.append("email")
        except Exception as e:
            print(f"이메일 실패 (편찬에는 영향 없음): {e}")

    proj.log("notify (CLI)", [f"{title} — 채널: {', '.join(sent)}"])
