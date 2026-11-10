#!/usr/bin/env python3
"""المشغّل الحيّ: صفحةٌ مستقلّة تعرض رحلةَ البطاقة في المشغّل لحظةً بلحظة (D-519م).

بصفر توكنز: تقرأ الدفترَ (ledger/events.jsonl) والقفلَ وowner_queue.md فقط، ولا تكتب شيئاً.
مستقلّةٌ عن صفحة «رسم الأتمتة» في ميزان، وبهويّته (النحاسيّ، Noto Kufi/Naskh، Inter، نهاراً وليلاً).

    python tools/runner_live.py                 يفتح http://127.0.0.1:8791 في تبويبٍ جديد
    python tools/runner_live.py --port 8792     منفذٌ آخر
    python tools/runner_live.py --no-open       بلا فتح المتصفّح (للجدولة عند الدخول)
"""

from __future__ import annotations

import argparse
import json
import re
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EVENTS = ROOT / "ledger" / "events.jsonl"
LOCK = ROOT / "ledger" / "runner.lock"
BEAT = ROOT / "ledger" / "runner.beat"


def beat_age():
    """ثوانٍ منذ آخر نبضٍ للمشغّل؛ None إن لم يُكتب نبضٌ بعد."""
    try:
        return max(0, int(time.time() - int(BEAT.read_text(encoding="utf-8").strip())))
    except (OSError, ValueError):
        return None
QUEUE = ROOT / "owner_queue.md"
CONFIG = ROOT / "runner_config.json"
PAGE = HERE / "runner_live.html"

RUN_RE = re.compile(r"\[مشغّل\]\s*(.+?):\s*كلفة=([\d.]+)\$\s*أدوار=(\d+)")
STAGES = ["ready", "model", "verify", "gate", "deploy", "published"]
DEFAULT_SIZES = {"صغير": "haiku", "متوسط": "sonnet", "كبير": "sonnet", "تصميم": "opus"}
ACTIVE = {"model", "verify", "gate", "deploy"}


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _models() -> dict[str, str]:
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        sizes = cfg.get("sizes") or {}
        return {**DEFAULT_SIZES, **{k: (v[0] if isinstance(v, list) else v) for k, v in sizes.items()}}
    except (OSError, ValueError):
        return dict(DEFAULT_SIZES)


class Card:
    __slots__ = ("id", "problem", "impact", "size", "priority", "source", "runner", "stage", "reached",
                 "stage_ts", "cycle_start", "ended", "runs", "cycle_runs", "pr", "hold", "referral",
                 "waiting", "log", "last_ts", "attempts")

    def __init__(self, cid: str):
        self.id = cid
        self.problem = self.impact = self.size = self.priority = self.source = ""
        self.runner = False
        self.stage = "ready"
        self.reached = 0
        self.stage_ts = self.cycle_start = self.ended = self.last_ts = ""
        self.runs: list[dict] = []
        self.cycle_runs: list[dict] = []
        self.pr = None
        self.hold = False
        self.referral = ""
        self.waiting = ""
        self.log: list[dict] = []
        self.attempts = 0

    def go(self, stage: str, ts: str) -> None:
        if stage != self.stage:
            self.stage, self.stage_ts = stage, ts
        if stage == "ready":
            self.reached = 0
        elif stage in STAGES:
            self.reached = max(self.reached, STAGES.index(stage))

    def as_dict(self, models: dict[str, str]) -> dict:
        return {
            "id": self.id, "problem": self.problem, "impact": self.impact, "size": self.size,
            "model": models.get(self.size, ""), "priority": self.priority, "stage": self.stage,
            "reached": self.reached, "stage_ts": self.stage_ts, "cycle_start": self.cycle_start,
            "ended": self.ended, "pr": self.pr, "hold": self.hold, "referral": self.referral,
            "waiting": self.waiting, "attempts": self.attempts, "last_ts": self.last_ts,
            "runs": self.cycle_runs, "all_runs": len(self.runs),
            "cost_cycle": round(sum(r["cost"] for r in self.cycle_runs), 4),
            "cost_total": round(sum(r["cost"] for r in self.runs), 4),
            "turns_cycle": sum(r["turns"] for r in self.cycle_runs),
            "log": self.log[-40:][::-1],
        }


class Ledger:
    """يقرأ الدفترَ تزايديّاً: الأسطرُ الكاملة فقط، ومن آخر موضعٍ قُرئ."""

    def __init__(self, path: Path = EVENTS):
        self.path = path
        self.pos = 0
        self.cards: dict[str, Card] = {}
        self.mutex = threading.Lock()

    def refresh(self) -> None:
        with self.mutex:
            try:
                size = self.path.stat().st_size
            except OSError:
                return
            if size < self.pos:  # دُوِّر الملفّ أو أُعيد بناؤه
                self.pos, self.cards = 0, {}
            if size == self.pos:
                return
            with open(self.path, "rb") as f:
                f.seek(self.pos)
                chunk = f.read(size - self.pos)
            end = chunk.rfind(b"\n")
            if end < 0:
                return
            self.pos += end + 1
            for raw in chunk[: end + 1].splitlines():
                try:
                    ev = json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    continue
                if isinstance(ev, dict) and ev.get("id"):
                    self.apply(ev)

    def apply(self, ev: dict) -> None:
        cid, kind, ts = ev["id"], ev.get("kind"), str(ev.get("ts", ""))
        data = ev.get("data") or {}
        text = str(data.get("text", ""))
        by_runner = data.get("by") == "runner" or text.startswith("[مشغّل]")
        c = self.cards.get(cid)
        if kind == "created":
            c = c or self.cards.setdefault(cid, Card(cid))
            c.problem = str(data.get("problem", ""))[:160]
            c.impact = str(data.get("impact", ""))[:300]
            c.priority = str(data.get("priority", ""))
            c.source = str(data.get("source", ""))
            if data.get("runner_size"):
                c.size, c.runner = str(data["runner_size"]), True
                c.go("ready", ts)
                self._log(c, ts, "intake", "أُنشئت من طلب المالك" if c.source == "owner" else "أُنشئت")
            c.last_ts = ts
            return
        if c is None:
            if not by_runner:
                return
            c = self.cards.setdefault(cid, Card(cid))
        if not (c.runner or by_runner):
            return
        c.runner = True
        c.last_ts = ts
        if kind == "update" and "runner_size" in data:
            c.size = str(data["runner_size"])
        if kind == "state":
            st = data.get("state")
            if st == "in_progress" and data.get("by") == "runner":
                c.cycle_start, c.cycle_runs, c.referral, c.waiting, c.ended = ts, [], "", "", ""
                c.attempts += 1
                c.reached = 0
                c.go("model", ts)
                self._log(c, ts, "model", f"التقطها المشغّل (المحاولة {c.attempts})؛ النموذج يكتب")
            elif st == "merged":
                c.waiting = ""
                c.go("deploy", ts)
                self._log(c, ts, "deploy", "دُمجت؛ النشر ثمّ فحص الصحّة")
            elif st == "published":
                c.ended = ts
                c.go("published", ts)
                self._log(c, ts, "published", "منشورة وسليمة")
            elif st == "closed":
                if c.stage != "referred":
                    c.ended = ts
                    c.stage, c.stage_ts = "referred", ts
            elif st == "routed":
                if c.stage != "referred" and not c.hold:
                    c.go("ready", ts)
                    self._log(c, ts, "ready", "في الطابور")
        elif kind == "note":
            m = RUN_RE.search(text)
            if m:
                run = {"label": m.group(1), "cost": float(m.group(2)), "turns": int(m.group(3)), "ts": ts}
                c.runs.append(run)
                c.cycle_runs.append(run)
                c.go("verify", ts)
                self._log(c, ts, "verify", f"{run['label']}: {run['turns']} دوراً، {run['cost']:.4f}$؛ الفحص في الحاوية")
            elif "أُحيلت" in text or "أُغلقت بتقرير" in text:
                c.referral = text.replace("[مشغّل]", "").replace("أُحيلت:", "").replace("أُغلقت بتقرير:", "").strip()[:300]
                c.ended = ts
                c.stage, c.stage_ts = "referred", ts
                self._log(c, ts, "referred", "أُغلقت بتقرير: " + c.referral[:140])
            elif "نافذة النشر" in text:
                c.waiting = "خارج نافذة النشر؛ ينتظر الدورة التالية"
                c.go("gate", ts)
                self._log(c, ts, "gate", c.waiting)
            elif by_runner:
                self._log(c, ts, "note", text.replace("[مشغّل]", "").strip()[:160])
        elif kind == "update":
            if "pr" in data:
                c.pr = data["pr"]
            if data.get("pr"):
                c.go("gate", ts)
                self._log(c, ts, "gate", f"فُتح طلب الدمج #{c.pr}؛ البوّابة ونافذة النشر")
            rr = data.get("runner_resume")
            if isinstance(rr, dict) and rr.get("pr") and c.stage in ("ready", "model", "verify"):  # استئنافٌ بعد إغلاق: الطلبُ مفتوحٌ فالمرحلةُ البوّابة لا «النموذج يكتب» (005، 2026-11-10)
                c.pr = rr["pr"]
                c.go("gate", ts)
                self._log(c, ts, "gate", f"الطلب #{c.pr} مفتوح؛ الفحوص والمعاينة")
            if "waiting" in data:  # سببُ الانتظار الذي يكتبه المشغّل عند تغيّر المرحلة
                w = data["waiting"]
                c.waiting = str(w.get("text", ""))[:160] if isinstance(w, dict) else ""
            if "runner_hold" in data:
                c.hold = bool(data["runner_hold"])
                if not c.hold and c.stage == "referred":
                    c.stage, c.stage_ts = "ready", ts
                    self._log(c, ts, "ready", "أُعيدت إلى الطابور")

    @staticmethod
    def _log(c: Card, ts: str, kind: str, text: str) -> None:
        c.log.append({"ts": ts, "kind": kind, "text": text})
        if len(c.log) > 120:
            del c.log[:40]

    def snapshot(self) -> dict:
        self.refresh()
        models = _models()
        with self.mutex:
            cards = [c for c in self.cards.values() if c.runner]
        cards.sort(key=lambda c: c.last_ts, reverse=True)
        active = [c for c in cards if c.stage in ACTIVE]
        current = max(active, key=lambda c: c.cycle_start) if active else (cards[0] if cards else None)
        today = datetime.now().astimezone().date().isoformat()
        started_today = [c for c in cards if c.cycle_start[:10] == today]
        runs_today = [r for c in cards for r in c.runs if r["ts"][:10] == today]
        published_today = [c for c in cards if c.stage == "published" and c.ended[:10] == today]
        referred_today = [c for c in cards if c.stage == "referred" and c.ended[:10] == today]
        cost_today = sum(r["cost"] for r in runs_today)
        pub_costs = [sum(r["cost"] for r in c.cycle_runs) for c in cards if c.stage == "published"]
        try:
            lock_age = max(0, int(time.time() - LOCK.stat().st_mtime))
            lock = True
        except OSError:
            lock_age, lock = None, False
        try:
            queue = [ln.strip("- ").strip() for ln in QUEUE.read_text(encoding="utf-8").splitlines() if ln.startswith("- ")][-6:][::-1]
        except OSError:
            queue = []
        return {
            "now": _now_iso(),
            "runner": {"lock": lock, "lock_age_s": lock_age, "beat_age_s": beat_age(), "last_ts": cards[0].last_ts if cards else ""},
            "current": current.as_dict(models) if current else None,
            "queue_ready": [c.id for c in cards if c.stage == "ready" and not c.hold and c is not current],
            "recent": [c.as_dict(models) | {"log": []} for c in cards[:12]],
            "kpis": {
                "started_today": len(started_today), "published_today": len(published_today),
                "referred_today": len(referred_today), "cost_today": round(cost_today, 4),
                "runs_today": len(runs_today),
                "avg_published": round(sum(pub_costs) / len(pub_costs), 4) if pub_costs else None,
            },
            "owner_queue": queue,
        }


LEDGER = Ledger()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            try:
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            except OSError:
                self._send(500, "runner_live.html مفقود بجانب السكربت".encode(), "text/plain; charset=utf-8")
        elif path == "/api/state":
            body = json.dumps(LEDGER.snapshot(), ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def log_message(self, *_args) -> None:  # صامت
        return


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="المشغّل الحيّ")
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args(argv)
    LEDGER.refresh()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"المشغّل الحيّ: {url}  (Ctrl+C للإيقاف)", flush=True)
    if not a.no_open:
        threading.Timer(0.6, lambda: webbrowser.open_new_tab(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
