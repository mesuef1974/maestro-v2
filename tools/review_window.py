#!/usr/bin/env python3
"""مولّدُ نافذة المراجعة والتقاطُ ردّ المالك (المرحلة 6): بنودٌ محدودةٌ مرتَّبةٌ بـWSJF ← ردٌّ بكلمةٍ ← أحداثُ اعتمادٍ في السجلّ.

    python review_window.py render [--level normal|elevated] [--window "15:30"]
    python review_window.py apply --window ledger/windows/<file>.json --text "اعتمد: 1 2 | ملاحظات: 3 (..)"

الاعتمادُ لا يُلحَق إلا بقول المالك (نصٌّ يمرّره المايسترو من محادثته)؛ لا يعتمد المولّدُ شيئاً بنفسه.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402

HERE = Path(__file__).resolve().parent
DOHA = timezone(timedelta(hours=3))
CAPS = json.loads((HERE.parent / "projects" / "schoolos" / "thresholds.json").read_text(encoding="utf-8"))["owner_capacity"]
LIGHT = "light"
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def build_bundles(items: list[dict]) -> list[dict]:
    """حزمةٌ لكلّ (فئة×مجال)، والخفيفةُ كلُّها حزمةٌ واحدة؛ مرتَّبةً بأعلى WSJF ثمّ الأقدم."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for it in items:
        key = ("light", "light") if it.get("tier") == LIGHT else (it.get("category", "?"), it.get("area", "?"))
        groups[key].append(it)
    bundles = []
    for (cat, area), members in groups.items():
        bundles.append({
            "category": cat, "area": area, "light": cat == "light",
            "tier": LIGHT if cat == "light" else max((m.get("tier", "low") for m in members), key=["light", "low", "medium", "high"].index),
            "items": [m["id"] for m in members], "prs": sorted(m["pr"] for m in members if m.get("pr")),
            "score": max(ledger.wsjf(m) for m in members),
            "oldest": min(m.get("state_ts") or m["created"] for m in members),
            "urgent": any(m.get("urgent") for m in members),
        })
    bundles.sort(key=lambda b: (not b["urgent"], -b["score"], b["oldest"]))
    return bundles


def render(items: list[dict], level: str = "normal", window: str = "", flow_version: str = "v2.1", save_dir: Path | None = None) -> tuple[str, dict]:
    caps = CAPS[level]
    bundles = build_bundles(items)
    shown, overflow = bundles[: caps["per_window"]], bundles[caps["per_window"]:]
    now = datetime.now(DOHA)
    label = window or f"{now:%H:%M}"
    lines = [
        f"# نافذةُ المراجعة — {now:%Y-%m-%d} {label}",
        f"**فلو:** {flow_version} · **السعة:** {level} ({caps['per_window']} بنودٍ للنافذة؛ {caps['decisions_per_day']} قراراً و{caps['minutes_per_day']} د يوميّاً)",
        "",
        "## ردٌّ سريع (انسخ وعدّل)",
        "```",
        "اعتمد: " + " ".join(str(i + 1) for i in range(len(shown))) + " | ملاحظات: — | أجّل: —",
        "```",
        "",
    ]
    mapping, high = {}, []
    for n, b in enumerate(shown, 1):
        mapping[str(n)] = b["items"]
        if b["tier"] == "high":
            high.append(n)
        title = "الحزمةُ الخفيفة (وثائق/اختبارات/أدوات/مزامنة) — اعتمادٌ بكلمة" if b["light"] else f"{b['category']} · {b['area']}"
        lines += [
            f"## {n}. {title}" + (" ⚡ استعجال" if b["urgent"] else "") + (" ⚠ خطورةٌ عالية — تُعتمد بذكر رقمها صراحةً" if b["tier"] == "high" else ""),
            f"- **الطلبات:** {', '.join('#' + str(p) for p in b['prs']) or '—'} ({len(b['items'])})",
            f"- **الخطورة:** {b['tier']} · **WSJF:** {b['score']} · **ينتظر منذ:** {b['oldest'][:16]}",
            "- **القرارُ المطلوب:** اعتماد / ملاحظات — التفاصيلُ في حزمة الأدلّة لكلّ طلب",
            "",
        ]
    if overflow:
        lines += [f"## للنافذة التالية ({len(overflow)} حزمة)", *(f"- {b['category']}·{b['area']}: {len(b['items'])} بنداً" for b in overflow[:10]), ""]
    md = "\n".join(lines)
    if save_dir is not None:
        save_dir.mkdir(parents=True, exist_ok=True)
        (save_dir / f"{now:%Y%m%d-%H%M%S}.json").write_text(json.dumps({"level": level, "mapping": mapping, "high": high}, ensure_ascii=False, indent=2), encoding="utf-8")
    return md, mapping


def _nums(text: str) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", text.translate(_DIGITS))]


def parse_reply(text: str, n_bundles: int, high: set[int] | None = None) -> dict:
    """«اعتمد: 1 2 | ملاحظات: 3 (لون الزر)، 4 (…) | أجّل: 5» ← {approve, notes, defer}. «اعتمد الكلّ [عدا 3]» مدعوم،
    ولا يشمل الحزمَ عاليةَ الخطورة (high): تُعتمد بذكر رقمها صراحةً فقط."""
    high = high or set()
    text = text.translate(_DIGITS)
    out = {"approve": [], "notes": {}, "defer": []}
    for seg in re.split(r"[|\n؛;]", text):
        seg = seg.strip()
        if not seg:
            continue
        m = re.match(r"^(اعتمد|اعتماد|موافق|ملاحظات|ملاحظة|تغذية|أجّل|أجل|تأجيل|أجّلوا)\s*[:：]?\s*(.*)$", seg)
        if not m:
            continue
        key, rest = m.group(1), m.group(2)
        if key in ("اعتمد", "اعتماد", "موافق"):
            if re.match(r"^(الكل|الكلّ|كلّها|كلها)", rest):
                except_nums = _nums(rest.split("عدا", 1)[1]) if "عدا" in rest else []
                out["approve"] = [i for i in range(1, n_bundles + 1) if i not in except_nums and i not in high]
            else:
                out["approve"] += _nums(rest)
        elif key in ("ملاحظات", "ملاحظة", "تغذية"):
            for num, paren, colon in re.findall(r"(\d+)\s*(?:\(([^)]*)\)|[:：]\s*([^,،]*))?", rest):
                if 1 <= int(num) <= n_bundles:
                    out["notes"][int(num)] = (paren or colon or "").strip()
        else:
            out["defer"] += _nums(rest)
    out["approve"] = sorted({i for i in out["approve"] if 1 <= i <= n_bundles and i not in out["notes"] and i not in out["defer"]})
    out["defer"] = sorted({i for i in out["defer"] if 1 <= i <= n_bundles and i not in out["notes"]})
    return out


def apply_reply(reply: dict, mapping: dict, path=None, via: str = "maestro") -> dict:
    """يُلحق أحداثَ الاعتماد/الملاحظات/التأجيل بأثرٍ يمكن تتبّعُه (وقت، قناة). لا يدفع ولا يدمج."""
    done = {"approved": [], "notes": [], "deferred": []}
    for n in reply["approve"]:
        for item_id in mapping.get(str(n), []):
            ledger.append_event("approval", item_id, {"by": "owner", "via": via, "bundle": n}, path)
            ledger.append_event("state", item_id, {"state": "approved"}, path)
            done["approved"].append(item_id)
    for n, text in reply["notes"].items():
        for item_id in mapping.get(str(n), []):
            ledger.append_event("note", item_id, {"text": ledger.check_text("note", text or "ملاحظة بلا نصّ"), "by": "owner", "bundle": n}, path)
            ledger.append_event("state", item_id, {"state": "notes"}, path)
            done["notes"].append(item_id)
    for n in reply["defer"]:
        for item_id in mapping.get(str(n), []):
            ledger.append_event("state", item_id, {"state": "deferred"}, path)
            done["deferred"].append(item_id)
    return done


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render"); r.add_argument("--level", default="normal", choices=list(k for k in CAPS if k in ("normal", "elevated"))); r.add_argument("--window", default="")
    a = sub.add_parser("apply"); a.add_argument("--window", required=True); a.add_argument("--text", required=True)
    args = ap.parse_args()
    if args.cmd == "render":
        items = [i for i in ledger.reduce_state(ledger.load_events()).values() if i["state"] == "ready_for_review"]
        md, _ = render(items, args.level, args.window, save_dir=ledger.ROOT / "ledger" / "windows")
        print(md)
    else:
        saved = json.loads(Path(args.window).read_text(encoding="utf-8"))
        reply = parse_reply(args.text, len(saved["mapping"]), set(saved.get("high", [])))
        print(json.dumps({"reply": reply, "applied": apply_reply(reply, saved["mapping"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
