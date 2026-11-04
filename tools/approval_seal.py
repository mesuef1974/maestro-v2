#!/usr/bin/env python3
"""ختمُ هويّة اعتماد 0101 (W-20261103-011، قرار المالك 2026-11-03 «توثيق هويّة 0101»).

المشكلة: `--by 0101` ادّعاءٌ نصّيّ يكتبه أيّ أحد، فكان تفويضُ 0101 على ملفّات قاعدة الاعتماد نفسِها (ledger/approval_check/flow_pump) يمرّ بسطرٍ واحد.
الحلّ: حدثُ التفويض `approval` بـ`by=0101` يُختم بـHMAC-SHA256 على (البطاقة، الرأس، المُعتمِد، الزمن) بمفتاحٍ محلّيٍّ خارج المستودع
(`~/.claude/maestro_seal.key` أو `MAESTRO_SEAL_KEY`)، ويتحقّق منه `approval_check.delegation_evidence` فتُرفض الأحداثُ غيرُ المختومة أو المزوَّرة.

الترحيل بلا قفل: لا إلزامَ ما لم يوجد `ledger/seal_enforce_from` (سطرٌ ISO بتوقيت الدوحة)؛ قبله وضعُ الظلّ (يسجّل في `ledger/seal_shadow.log` ولا يرفض)،
وبعده تُقبل الأحداثُ الأقدم من ذلك التاريخ بلا ختم (أحداثٌ قديمة) وما بعدَه يلزمه ختمٌ صالح.

حدٌّ صريح: المفتاحُ ملفٌّ في حساب المستخدم نفسِه، فجلسةٌ تقرؤه عمداً تستطيع الختم؛ الختمُ يرفع الحاجزَ من «كتابة اسم» إلى «قراءة سرٍّ تمنع بطاقاتُ الأدوار قراءتَه»
ويجعل كلَّ تفويضٍ مزوَّرٍ أثراً قابلاً للكشف، ولا يُغني عن حارسٍ على قراءة الملفّ (يلزم إذنُ المالك لتسجيله في settings.json).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DOHA = timezone(timedelta(hours=3))
SEALED_BY = frozenset({"0101"})
SEAL_LEN = 32


def key_path() -> Path:
    return Path(os.environ.get("MAESTRO_SEAL_KEY") or Path.home() / ".claude" / "maestro_seal.key")


def load_key(create: bool = False) -> bytes | None:
    p = key_path()
    try:
        raw = p.read_bytes().strip()
        if len(raw) >= 32:
            return raw
    except OSError:
        pass
    if not create:
        return None
    p.parent.mkdir(parents=True, exist_ok=True)
    raw = secrets.token_hex(32).encode()
    p.write_bytes(raw)
    return raw


def _payload(card: str, head: str, by: str, ts: str) -> bytes:
    return f"{card}|{str(head)[:8]}|{by}|{ts}".encode()


def seal(card: str, head: str, by: str, ts: str, key: bytes | None = None) -> str | None:
    """الختمُ لحدث تفويض؛ None إن لم يوجد مفتاحٌ ولا يجوز إنشاؤه هنا (الإنشاءُ عند أوّل ختمٍ فعليّ بـ`seal_event`)."""
    key = key or load_key(create=True)
    return hmac.new(key, _payload(card, head, by, ts), hashlib.sha256).hexdigest()[:SEAL_LEN] if key else None


def verify(card: str, head: str, by: str, ts: str, seal_hex: str | None, key: bytes | None = None) -> bool:
    key = key or load_key()
    if not key or not seal_hex:
        return False
    want = hmac.new(key, _payload(card, head, by, ts), hashlib.sha256).hexdigest()[:SEAL_LEN]
    return hmac.compare_digest(want, str(seal_hex))


def enforce_since(ledger_dir: Path | None = None) -> str | None:
    """زمنُ بدء الإلزام (ISO) من `ledger/seal_enforce_from`؛ None = وضعُ الظلّ."""
    p = (ledger_dir or ROOT / "ledger") / "seal_enforce_from"
    try:
        text = p.read_text(encoding="utf-8").strip()
        datetime.fromisoformat(text)
        return text
    except (OSError, ValueError):
        return None


def problem(approval: dict, card: str, ledger_dir: Path | None = None, key: bytes | None = None) -> str | None:
    """سببُ رفض حدث التفويض (`approval` من show) أو None إن صحّ/وضعُ الظلّ. approval فيه ts وby وhead وseal."""
    by = str(approval.get("by") or "")
    if by not in SEALED_BY:
        return None
    ts = str(approval.get("ts") or "")
    ok = verify(card, str(approval.get("head") or ""), by, ts, approval.get("seal"), key)
    if ok:
        return None
    since = enforce_since(ledger_dir)
    why = "بلا ختم هويّة" if not approval.get("seal") else "ختمُ هويّةٍ غيرُ صالح (مزوَّر أو بمفتاحٍ آخر)"
    if since is None or ts < since:
        _shadow(card, approval, why, ledger_dir)
        return None
    return why


def _shadow(card: str, approval: dict, why: str, ledger_dir: Path | None) -> None:
    try:
        d = ledger_dir or ROOT / "ledger"
        d.mkdir(parents=True, exist_ok=True)
        with (d / "seal_shadow.log").open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now(DOHA).isoformat(timespec='seconds')} {card} {str(approval.get('head') or '')[:8]} {approval.get('ts', '')}: {why}\n")
    except OSError:
        pass
