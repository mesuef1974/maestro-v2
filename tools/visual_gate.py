#!/usr/bin/env python3
"""البوّابةُ البصريّة قبل «جاهزٌ للمعاينة» (W-20261009-007، أمرُ المالك عند 0102).

الحرّاسُ تفحص حروفَ الرموز لا تركيبَ الصفحة: صفحةُ 0405 مرّت كلَّها بصفر مخالفةٍ ثمّ وجد المالكُ فيها المسافاتِ
والتخطيطَ والهويّةَ نفسَها. فهذه الأداةُ تفتح الصفحةَ في متصفّحٍ حقيقيّ (Playwright كما `tests/web_vitals.py`)،
وتلتقط ستَّ لقطاتٍ لكلّ صفحةٍ معلَنة (1920/1280/375 × نهار/ليل)، وتقيس الـDOM والأنماطَ المحسوبة، وتكتب الأدلّةَ:

    evidence/<بطاقة>/<رأس8>/manifest.json + اللقطات

    python visual_gate.py run --card W-... --pages pages.json [--head ab12cd34] [--base http://localhost:8500]
    python visual_gate.py check --card W-... --head ab12cd34          # يقرأ الأدلّةَ فقط (ما يستدعيه approval_check)

`pages.json`: قائمةٌ يعلنها المنفِّذ — `[{"path": "/dashboard/", "role": "principal", "justify": {"font": "سبب"}}]`.
القائمةُ الفارغةُ لبطاقة واجهةٍ تُرفض، وإيداعٌ جديدٌ يُبطل الأدلّةَ (المجلّدُ باسم الرأس).

**ما تفحصه** (كلُّ لقطة): تمريرٌ أفقيّ للصفحة، عنصرٌ يتجاوز العرض، تداخلٌ بين شقيقَين أو مع الترويسة الثابتة،
مسافاتُ البطاقات (margin وpadding وgap) على سلّم `--sp-*`، نصفُ قطر البطاقات على `--radius-*`، خطٌّ دون 12px،
جدولٌ أعرضُ من حاويته بلا `table-wrap`، وفراغٌ داخل بطاقةٍ فوق 2rem.

**ما لا تكشفه:** الذوقُ والتناسقُ العامّ ومعنى المحتوى — تبقى للمالك. وهي سقّاطةٌ لا مرآة: `BASELINE` أدناه
عدّاداتُ الصفحات القائمة المعتمَدة (لا تُزاد إلا بقرار)؛ وصفحةٌ جديدةٌ أو معدَّلةٌ بأيّ مخالفةٍ غيرِ مبرَّرةٍ تمنع.
الكلمةُ لا تُكتب هنا: `PREVIEW_ACCOUNTS_PASSWORD` من بيئة المضيف أو من `tools/.preview_accounts.env` غير المتتبَّع.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EVIDENCE_DIR = ROOT / "evidence"
REGISTRY = HERE / "preview_accounts_registry.json"
LOCAL_ENV = HERE / ".preview_accounts.env"
PASSWORD_VAR = "PREVIEW_ACCOUNTS_PASSWORD"  # اسمُ المتغيّر لا قيمتُه

VIEWPORTS = {"1920": (1920, 1080), "1280": (1280, 800), "375": (375, 812)}
THEMES = ("light", "dark")
SHOTS_PER_PAGE = len(VIEWPORTS) * len(THEMES)
PAGE_BUDGET_SECONDS = 60

#: سلّمُ `--sp-*` و`--radius-*` من static/css/custom/10-foundation.css (بالبكسل).
SPACING_SCALE = (0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 24, 32, 40, 48, 64)
RADIUS_SCALE = (0, 4, 6, 8, 10, 14, 16)
MIN_FONT_PX = 12
MAX_VOID_PX = 32  # 2rem

KINDS = ("hscroll", "overflow", "overlap", "spacing", "radius", "font", "table", "void")

#: عدّاداتُ المخالفات المقبولةُ للصفحات القائمة: `"<مسار>|<دور>": {"نوع": عدد}` — تُملأ بالمعايرة وتنقص ولا تزيد.
BASELINE: dict[str, dict[str, int]] = {}

CARD_SELECTOR = ".card-qatar, .section-card, .kpi, .kpi-card, [class*='card']"

MEASURE_JS = r"""
({sp, radius, minFont, maxVoid, cards}) => {
  const out = [];
  const near = (v, scale) => scale.some(s => Math.abs(Math.abs(v) - s) < 0.6);
  const vis = el => {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0';
  };
  const sel = el => {
    let s = el.tagName.toLowerCase();
    if (el.id) s += '#' + el.id;
    const c = [...el.classList].slice(0, 3);
    return s + (c.length ? '.' + c.join('.') : '');
  };
  const add = (kind, el, detail) => { if (out.length < 600) out.push({kind, selector: sel(el), detail}); };
  const clipped = el => {
    for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
      const o = getComputedStyle(a).overflowX;
      if (o === 'auto' || o === 'scroll' || o === 'hidden' || o === 'clip') return true;
    }
    return false;
  };
  const body = document.body, de = document.documentElement;
  if (de.scrollWidth > de.clientWidth + 1) add('hscroll', body, `scrollWidth ${de.scrollWidth} > ${de.clientWidth}`);

  const all = [...body.querySelectorAll('*')].filter(el => !['SCRIPT', 'STYLE', 'NOSCRIPT', 'LINK', 'META', 'TEMPLATE'].includes(el.tagName) && !el.closest('svg') && vis(el));
  const W = window.innerWidth;
  const flagged = new Set();
  for (const el of all) {
    const cs = getComputedStyle(el);
    if (cs.position === 'fixed' || el.closest('[aria-hidden="true"]') || clipped(el)) continue;
    const r = el.getBoundingClientRect();
    if ((r.right > W + 1 || r.left < -1) && !(el.parentElement && flagged.has(el.parentElement))) {
      flagged.add(el);
      add('overflow', el, `left ${Math.round(r.left)} right ${Math.round(r.right)} عرض ${W}`);
    }
  }

  const flow = el => { const p = getComputedStyle(el).position; return p !== 'absolute' && p !== 'fixed'; };
  for (const p of [body, ...all]) {
    const kids = [...p.children].filter(k => all.includes(k) && flow(k) && k.getBoundingClientRect().width * k.getBoundingClientRect().height > 16);
    for (let i = 0; i < kids.length; i++) for (let j = i + 1; j < kids.length; j++) {
      const a = kids[i].getBoundingClientRect(), b = kids[j].getBoundingClientRect();
      const w = Math.min(a.right, b.right) - Math.max(a.left, b.left), h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (w > 4 && h > 4) add('overlap', kids[j], `مع ${sel(kids[i])} (${Math.round(w)}×${Math.round(h)})`);
    }
  }
  const header = [...document.querySelectorAll('header, .site-nav, [role=banner]')].find(h => ['fixed', 'sticky'].includes(getComputedStyle(h).position) && vis(h));
  const main = document.querySelector('main, [role=main]');
  if (header && main && window.scrollY === 0) {
    const hb = header.getBoundingClientRect();
    for (const k of main.children) {
      if (!vis(k) || !flow(k) || header.contains(k)) continue;
      const r = k.getBoundingClientRect();
      if (r.top < hb.bottom - 4 && r.bottom > hb.top + 4 && Math.min(r.right, hb.right) - Math.max(r.left, hb.left) > 4)
        add('overlap', k, `تحت الترويسة ${sel(header)} بـ${Math.round(hb.bottom - r.top)}px`);
    }
  }

  const px = v => (/^-?[\d.]+px$/.test(v) ? parseFloat(v) : null);
  const cardEls = [...body.querySelectorAll(cards)].filter(el => all.includes(el));
  for (const el of cardEls) {
    const cs = getComputedStyle(el);
    for (const prop of ['margin-top', 'margin-right', 'margin-bottom', 'margin-left', 'padding-top', 'padding-right', 'padding-bottom', 'padding-left', 'row-gap', 'column-gap']) {
      const v = px(cs.getPropertyValue(prop));
      // margin:auto داخل flex/grid يُحسب px كبيراً — ليس مسافةً مكتوبة
      const pd = el.parentElement ? getComputedStyle(el.parentElement).display : '';
      if (prop.startsWith('margin') && v > 64 && /flex|grid/.test(pd)) continue;
      if (v !== null && !near(v, sp)) add('spacing', el, `${prop} ${v}px`);
    }
    for (const prop of ['border-top-left-radius', 'border-top-right-radius', 'border-bottom-left-radius', 'border-bottom-right-radius']) {
      const v = px(cs.getPropertyValue(prop));
      if (v !== null && v < 999 && !near(v, radius)) add('radius', el, `${prop} ${v}px`);
    }
    const kids = [...el.children].filter(k => all.includes(k) && flow(k));
    if (kids.length) {
      const r = el.getBoundingClientRect();
      const inner = r.bottom - parseFloat(cs.paddingBottom) - parseFloat(cs.borderBottomWidth);
      const free = inner - Math.max(...kids.map(k => k.getBoundingClientRect().bottom));
      if (free > maxVoid) add('void', el, `فراغٌ ${Math.round(free)}px أسفل المحتوى`);
    }
  }
  const gapped = [...body.querySelectorAll('main *, [role=main] *')].filter(el => all.includes(el) && /flex|grid/.test(getComputedStyle(el).display) && el.children.length > 1 && !cardEls.includes(el));
  for (const el of gapped) {
    const cs = getComputedStyle(el);
    for (const prop of ['row-gap', 'column-gap']) {
      const v = px(cs.getPropertyValue(prop));
      // margin:auto داخل flex/grid يُحسب px كبيراً — ليس مسافةً مكتوبة
      const pd = el.parentElement ? getComputedStyle(el.parentElement).display : '';
      if (prop.startsWith('margin') && v > 64 && /flex|grid/.test(pd)) continue;
      if (v !== null && !near(v, sp)) add('spacing', el, `${prop} ${v}px`);
    }
  }

  for (const el of all) {
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!own) continue;
    const fs = parseFloat(getComputedStyle(el).fontSize);
    if (fs > 0 && fs < minFont) add('font', el, `${fs}px`);
  }
  for (const t of body.querySelectorAll('table')) {
    if (!vis(t)) continue;
    let wrapped = false;
    for (let a = t.parentElement; a && a !== body; a = a.parentElement) {
      const o = getComputedStyle(a).overflowX;
      if (a.classList.contains('table-wrap') || o === 'auto' || o === 'scroll') { wrapped = true; break; }
    }
    const host = t.parentElement, r = t.getBoundingClientRect();
    if (!wrapped && (r.width > host.clientWidth + 1 || r.right > W + 1 || r.left < -1))
      add('table', t, `عرض الجدول ${Math.round(r.width)} > الحاوية ${host.clientWidth} بلا table-wrap`);
  }
  return out;
}
"""


def head8(repo: str | None = None) -> str:
    out = subprocess.run(
        ["git", "-C", repo or ".", "rev-parse", "--short=8", "HEAD"], capture_output=True, text=True, encoding="utf-8"
    )
    if out.returncode != 0:
        raise SystemExit("تعذّر قراءة رأس الإيداع: مرّر --head")
    return out.stdout.strip()


def slug(path: str, role: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", f"{path}-{role}").strip("-") or "root"


def measure(page: Any) -> list[dict[str, Any]]:
    """مخالفاتُ الصفحة المحمَّلة في `page` — مجمَّعةً بـ(نوع، عنصر، تفصيل) وعددِ تكرارها."""
    raw = page.evaluate(
        MEASURE_JS,
        {"sp": list(SPACING_SCALE), "radius": list(RADIUS_SCALE), "minFont": MIN_FONT_PX, "maxVoid": MAX_VOID_PX, "cards": CARD_SELECTOR},
    )
    grouped = Counter((v["kind"], v["selector"], v["detail"]) for v in raw)
    return [{"kind": k, "selector": s, "detail": d, "count": n} for (k, s, d), n in sorted(grouped.items())]


def kind_counts(violations: list[dict[str, Any]]) -> dict[str, int]:
    out: Counter[str] = Counter()
    for v in violations:
        out[v["kind"]] += v.get("count", 1)
    return dict(out)


def classify(page_key: str, violations: list[dict[str, Any]], justify: dict[str, str]) -> list[dict[str, Any]]:
    """يسم كلَّ مخالفةٍ `justified` إن برّرها المنفِّذُ بنوعها (بسببٍ مكتوب) أو سمح بها `BASELINE` للصفحة القائمة."""
    allowed = dict(BASELINE.get(page_key, {}))
    out = []
    for v in sorted(violations, key=lambda x: (x["kind"], x["selector"], x["detail"])):
        v = dict(v)
        reason = (justify.get(v["kind"]) or "").strip()
        if reason:
            v["justified"], v["reason"] = True, reason
        elif allowed.get(v["kind"], 0) >= v.get("count", 1):
            allowed[v["kind"]] -= v.get("count", 1)
            v["justified"], v["reason"] = True, "ضمن BASELINE للصفحة القائمة"
        else:
            v["justified"] = False
        out.append(v)
    return out


def read_password() -> str | None:
    value = os.environ.get(PASSWORD_VAR)
    if value:
        return value
    if LOCAL_ENV.exists():
        for line in LOCAL_ENV.read_text(encoding="utf-8").splitlines():
            if line.startswith(PASSWORD_VAR + "="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return None


def national_id_of(role: str) -> str | None:
    for row in json.loads(REGISTRY.read_text(encoding="utf-8")):
        if row.get("role") == role:
            return row.get("national_id")
    return None


def login_state(browser: Any, base: str, role: str, username: str | None = None) -> dict[str, Any] | None:
    """حالةُ جلسةٍ مسجَّلةٍ لدورٍ من حسابات المعاينة؛ `None` للزائر. الكلمةُ لا تُطبع ولا تُخزَّن."""
    if role in ("anonymous", "public", ""):
        return None
    national_id, password = username or national_id_of(role), read_password()
    if not national_id or not password:
        raise SystemExit(f"لا حسابَ معاينةٍ للدور {role!r} أو لا كلمةَ في {PASSWORD_VAR}")
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    page.goto(base.rstrip("/") + "/auth/login/", wait_until="load", timeout=30000)
    page.locator("form input[type=password]").first.fill(password)
    page.locator("form input:not([type=password]):not([type=hidden]):not([type=checkbox])").first.fill(national_id)
    page.locator("form button[type=submit]").first.click()
    page.wait_for_load_state("load", timeout=30000)
    if "/auth/login" in page.url:
        ctx.close()
        raise SystemExit(f"تعذّر الدخول بالدور {role!r}")
    state = ctx.storage_state()
    ctx.close()
    return state


ADMIN_SHELL_PATH = "/admin/"


def admin_shell_baseline(browser: Any, base: str, state: dict[str, Any] | None) -> set[tuple[str, str]]:
    """(نوع، محدِّد) مخالفات قشرة إدارة Django على الرأس نفسه: تُقاس في صفحة /admin/ الرئيسة بكل المقاسات والسمتين."""
    seen: set[tuple[str, str]] = set()
    for theme in THEMES:
        for _name, (w, h) in VIEWPORTS.items():
            ctx = browser.new_context(viewport={"width": w, "height": h}, storage_state=state, locale="ar")
            ctx.add_init_script(f"try{{localStorage.setItem('theme','{theme}')}}catch(e){{}}")
            page = ctx.new_page()
            try:
                page.goto(base.rstrip("/") + ADMIN_SHELL_PATH, wait_until="load", timeout=30000)
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                seen.update((v["kind"], v["selector"]) for v in measure(page))
            finally:
                ctx.close()
    return seen


def probe_unavailable(browser: Any, base: str, entry: dict[str, Any], state: dict[str, Any] | None) -> str | None:
    """سببُ عدم إتاحة الصفحة بهذا الدور (رمزٌ غيرُ 200، أو تحويلٌ لتسجيل الدخول، أو بلا علامة القالب)، وإلا None."""
    path, role = entry["path"], entry.get("role", "anonymous")
    ctx = browser.new_context(viewport={"width": 1280, "height": 800}, storage_state=state, locale="ar")
    try:
        page = ctx.new_page()
        resp = page.goto(base.rstrip("/") + path, wait_until="load", timeout=30000)
        code = resp.status if resp else 0
        if code != 200:
            return f"رمز الاستجابة {code} بدور {role}"
        if "/auth/login" in page.url and "/auth/login" not in path:
            return f"حوّلت إلى تسجيل الدخول بدور {role}"
        if page.locator(entry.get("expect") or "main, [role=main], h1").count() == 0:
            return "لا علامةَ للقالب المتوقَّع (main/h1) في الصفحة"
        return None
    finally:
        ctx.close()


def subtract_shell(violations: list[dict[str, Any]], shell: set[tuple[str, str]] | None) -> list[dict[str, Any]]:
    """يبرّر ما ظهر مثلُه في قشرة /admin/ على الرأس نفسه (قرار المالك 2026-10-19): الأصلُ من Django لا من الصفحة."""
    for v in violations:
        if shell and not v.get("justified") and (v["kind"], v["selector"]) in shell:
            v["justified"], v["reason"] = True, "خطّ أساس قشرة إدارة Django على الرأس نفسه (/admin/)"
    return violations


def capture_page(browser: Any, base: str, entry: dict[str, Any], outdir: Path, state: dict[str, Any] | None, shell: set[tuple[str, str]] | None = None) -> dict[str, Any]:
    path, role = entry["path"], entry.get("role", "anonymous")
    key = f"{path}|{role}"
    started = time.time()
    shots: list[str] = []
    violations: list[dict[str, Any]] = []
    why = probe_unavailable(browser, base, entry, state)
    if why:
        # 404/403/تحويلٌ لتسجيل الدخول = الصفحةُ غيرُ متاحةٍ بهذا الدور، لا مخالفةُ قالب (إنذار W-20261013-020 الكاذب)
        out = {"path": path, "role": role, "shots": [], "seconds": round(time.time() - started, 1), "over_budget": False,
               "violations": [], "unavailable": True, "unavailable_reason": why}
        if entry.get("suggest"):
            out["suggest"] = entry["suggest"]
        return out
    for theme in THEMES:
        for name, (w, h) in VIEWPORTS.items():
            ctx = browser.new_context(viewport={"width": w, "height": h}, storage_state=state, locale="ar")
            ctx.add_init_script(f"try{{localStorage.setItem('theme','{theme}')}}catch(e){{}}")
            page = ctx.new_page()
            page.goto(base.rstrip("/") + path, wait_until="load", timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:  # polling حيّ لا يهدأ — يكفي ما رُسم
                pass
            fname = f"{slug(path, role)}__{name}__{theme}.png"
            page.screenshot(path=str(outdir / fname), full_page=True)
            shots.append(fname)
            for v in measure(page):
                v["viewport"], v["theme"] = name, theme
                violations.append(v)
            ctx.close()
    # التجميعُ عبر المقاسات: المخالفةُ نفسُها في ستّ لقطاتٍ تُعدّ مرّةً وتُسجَّل أين ظهرت
    merged: dict[tuple, dict[str, Any]] = {}
    for v in violations:
        k = (v["kind"], v["selector"], v["detail"])
        cell = merged.setdefault(k, {"kind": v["kind"], "selector": v["selector"], "detail": v["detail"], "count": 0, "seen_in": []})
        cell["count"] = max(cell["count"], v["count"])
        cell["seen_in"].append(f"{v['viewport']}/{v['theme']}")
    elapsed = round(time.time() - started, 1)
    return {
        "path": path,
        "role": role,
        "shots": shots,
        "seconds": elapsed,
        "over_budget": elapsed > PAGE_BUDGET_SECONDS,
        "violations": subtract_shell(classify(key, list(merged.values()), entry.get("justify") or {}), shell),
    }


def build_manifest(card: str, head: str, base: str, pages: list[dict[str, Any]]) -> dict[str, Any]:
    bad = sum(1 for p in pages for v in p["violations"] if not v["justified"])
    return {
        "card": card,
        "head": head,
        "base": base,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "expected_shots_per_page": SHOTS_PER_PAGE,
        "pages": pages,
        "unjustified": bad,
        "kinds": dict(sum((Counter(kind_counts(p["violations"])) for p in pages), Counter())),
    }


def served_head(base: str, opener: Any = None) -> str:
    """commit الذي يعلنه `/health/` للخادم (فارغٌ إن تعذّر)."""
    import urllib.request

    try:
        with (opener or urllib.request.urlopen)(base.rstrip("/") + "/health/", timeout=8) as resp:
            body = resp.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 — خادمٌ مطفأ
        return ""
    m = re.search(r'"commit"\s*:\s*"([0-9a-f]{7,40})"', body)
    return m.group(1) if m else ""


def served_matches(base: str, head: str, opener: Any = None) -> tuple[bool, str]:
    """هل الخادم يخدم الرأسَ المطلوب؟ (قرار 0101 2026-10-19: لا دليلَ يُوسَم برأسٍ غير المخدوم)."""
    served = served_head(base, opener)
    if not served:
        return False, f"تعذّر قراءة commit من {base}/health/ — لا التقاطَ بلا تأكيد الرأس (--no-health-check للاستثناء)"
    n = min(len(served), len(head))
    if served[:n] != head[:n]:
        return False, f"الخادم يخدم {served[:8]} لا الرأسَ المطلوب {head[:8]} — لا التقاط"
    return True, served


def run(card: str, head: str, base: str, entries: list[dict[str, Any]], check_served: bool = True) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    if check_served:
        ok, msg = served_matches(base, head)
        if not ok:
            raise SystemExit("✘ " + msg)
    outdir = EVIDENCE_DIR / card / head
    outdir.mkdir(parents=True, exist_ok=True)
    pages: list[dict[str, Any]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        states: dict[str, Any] = {}
        shells: dict[Any, set[tuple[str, str]]] = {}
        for entry in entries:
            role = entry.get("role", "anonymous")
            who = (role, entry.get("username"))
            if who not in states:
                states[who] = login_state(browser, base, role, entry.get("username"))
            shell = None
            if entry["path"].startswith(ADMIN_SHELL_PATH) and entry["path"] != ADMIN_SHELL_PATH:
                if who not in shells:
                    shells[who] = admin_shell_baseline(browser, base, states[who])
                shell = shells[who]
            pages.append(capture_page(browser, base, entry, outdir, states[who], shell))
        browser.close()
    if check_served:
        ok, msg = served_matches(base, head)
        if not ok:
            raise SystemExit("✘ تبدّل المخدوم أثناء الالتقاط ولم يُكتب manifest: " + msg)
    manifest = build_manifest(card, head, base, pages)
    (outdir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


CONFIRMATIONS = ROOT / "owner_confirmations.md"
WAIVER_MARK = "إعفاء manifest"


def owner_waiver_line(card: str, head: str, confirmations: Path | None = None) -> str | None:
    """سطرُ المالك المسجَّل لإعفاء manifest هذا الزوجِ (بطاقة + رأس) بعينه، وإلا None."""
    f = confirmations or CONFIRMATIONS
    if not f.exists():
        return None
    lines = f.read_text(encoding="utf-8").splitlines()
    # ملحقُ الإلغاء «ملغى[بطاقة@رأس]» (كما في approval_check.confirmations_evidence) يُسقط السطرَ المقصود
    voided = re.findall(r"ملغى\[(\S+?)@(\w+)\]", chr(10).join(lines))
    card_re = re.escape(card) + r"(?!\w)"
    head_re = "@" + re.escape(head[:8]) + r"(?!\w)"
    for ln in lines:
        if "ملغى[" in ln:
            continue
        if any(re.search(re.escape(c) + r"\s*@" + re.escape(h), ln) for c, h in voided):
            continue
        if WAIVER_MARK in ln and re.search(card_re, ln) and re.search(head_re, ln):
            return ln.strip()
    return None


def waive(card: str, head: str, reason: str, by: str, evidence_dir: Path | None = None, confirmations: Path | None = None) -> str:
    """يسجّل إعفاءً بصريّاً لرأسٍ بعينه: لا يُكتب بلا سطر المالك المطابق في owner_confirmations.md، ولا يعمّ ما بعده."""
    head = head[:8]
    if not re.fullmatch(r"[0-9a-f]{8}", head):
        raise ValueError("--head8 غير صالح")
    if not reason.strip() or not by.strip():
        raise ValueError("السببُ والتوقيعُ لازمان")
    line = owner_waiver_line(card, head, confirmations)
    if not line:
        raise ValueError(f"لا سطرَ للمالك بـ«{WAIVER_MARK}» للبطاقة {card} @{head} في owner_confirmations.md")
    d = evidence_dir or EVIDENCE_DIR
    d.mkdir(parents=True, exist_ok=True)
    rec = {"card": card, "head": head, "by": by, "reason": reason, "owner_line": line, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with (d / "waivers.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + chr(10))
    return line


def waiver_for(card: str, head: str, evidence_dir: Path | None = None, confirmations: Path | None = None) -> dict | None:
    """إعفاءٌ ساري لهذا الزوجِ بعينه: سجلٌّ مطابقٌ وسطرُ المالك ما زال قائماً."""
    f = (evidence_dir or EVIDENCE_DIR) / "waivers.jsonl"
    if not f.exists():
        return None
    for ln in f.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if r.get("card") == card and r.get("head") == head[:8] and owner_waiver_line(card, head, confirmations):
            return r
    return None


def evidence_status(card: str, head: str, evidence_dir: Path | None = None, confirmations: Path | None = None) -> tuple[bool, str]:
    """(ناجح؟، رسالة) — هل للرأس أدلّةٌ بصريّةٌ كاملةٌ بلا مخالفةٍ غيرِ مبرَّرة. قراءةٌ فقط."""
    head = head[:8]
    folder = (evidence_dir or EVIDENCE_DIR) / card / head
    manifest_file = folder / "manifest.json"
    # الإعفاءُ يُقدَّم على فحص manifest: يُعفى الزوجُ (بطاقة+رأس) رغم وجود manifest بمخالفات
    w = waiver_for(card, head, evidence_dir, confirmations)
    if w:
        return True, f"إعفاءٌ بصريٌّ للرأس {head} بقول المالك (وقّع {w['by']}): {w['reason']}"
    if not manifest_file.exists():
        return False, f"لا أدلة بصرية للرأس {head}: لا manifest في {folder} (شغّلي visual_gate.py run)"
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except ValueError:
        return False, f"لا أدلة بصرية للرأس {head}: manifest تالف"
    if str(manifest.get("head", ""))[:8] != head:
        return False, f"لا أدلة بصرية للرأس {head}: الـmanifest لرأس {manifest.get('head')}"
    pages = manifest.get("pages") or []
    if not pages:
        return False, f"لا أدلة بصرية للرأس {head}: لا صفحةَ معلنة (القائمةُ الفارغة لبطاقة واجهةٍ مرفوضة)"
    avail = [p for p in pages if not p.get("unavailable")]
    if not avail:
        return False, f"لا أدلة بصرية للرأس {head}: كلُّ الصفحات غيرُ متاحةٍ بأدوارها"
    skipped = [p for p in pages if p.get("unavailable")]
    pages = avail
    for page in pages:
        missing = [s for s in page.get("shots", []) if not (folder / s).exists()]
        if len(page.get("shots", [])) != SHOTS_PER_PAGE or missing:
            return False, f"لا أدلة بصرية للرأس {head}: لقطاتُ {page.get('path')} ناقصة ({len(page.get('shots', []))}/{SHOTS_PER_PAGE})"
    bad = [(p["path"], v) for p in pages for v in p["violations"] if not v.get("justified")]
    if bad:
        first = "؛ ".join(f"{path} [{v['kind']}] {v['selector']} {v['detail']}" for path, v in bad[:3])
        return False, f"لا أدلة بصرية للرأس {head}: {len(bad)} مخالفةٌ غيرُ مبرَّرة — {first}"
    note = f" — وغيرُ متاحةٍ بدورها: {len(skipped)} ({'؛ '.join(p['path'] for p in skipped)})" if skipped else ""
    return True, f"أدلةٌ بصريّةٌ كاملةٌ للرأس {head}: {len(pages)} صفحةً × {SHOTS_PER_PAGE} لقطات، بلا مخالفةٍ غيرِ مبرَّرة{note}"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="يلتقط ويقيس ويكتب الأدلّة")
    r.add_argument("--card", required=True)
    r.add_argument("--pages", required=True, help="ملفّ JSON بالصفحات المعلنة")
    r.add_argument("--head", help="sha8 (وإلّا رأسُ --repo)")
    r.add_argument("--repo", default=".", help="مستودعُ الشجرة لقراءة الرأس")
    r.add_argument("--base", default="http://localhost:8500")
    r.add_argument("--no-health-check", action="store_true", help="استثناء: لا يُطابَق commit /health/ بالرأس (خوادمُ بلا /health/)")
    c = sub.add_parser("check", help="يتحقّق من الأدلّة المكتوبة")
    c.add_argument("--card", required=True)
    c.add_argument("--head", required=True)
    w = sub.add_parser("waive", help="إعفاءُ manifest لرأسٍ بعينه بسطر المالك المسجَّل")
    w.add_argument("--card", required=True)
    w.add_argument("--head8", required=True)
    w.add_argument("--reason", required=True)
    w.add_argument("--by", required=True)
    a = ap.parse_args()
    if a.cmd == "waive":
        try:
            line = waive(a.card, a.head8, a.reason, a.by)
        except ValueError as e:
            print("✘ " + str(e))
            return 2
        print(f"✔ أُعفي {a.card} @{a.head8[:8]} بتوقيع {a.by}؛ سطر المالك: {line[:100]}")
        return 0
    if a.cmd == "check":
        ok, msg = evidence_status(a.card, a.head)
        print(("✔ " if ok else "✘ ") + msg)
        return 0 if ok else 4
    entries = json.loads(Path(a.pages).read_text(encoding="utf-8"))
    if not entries:
        print("✘ لا صفحةَ معلنة: أعلني صفحةً واحدةً على الأقلّ (مسار + دور)")
        return 2
    head = (a.head or head8(a.repo))[:8]
    manifest = run(a.card, head, a.base, entries, check_served=not a.no_health_check)
    for p in manifest["pages"]:
        if p.get("unavailable"):
            print(f"{p['path']} [{p['role']}] — غير متاحة بهذا الدور: {p['unavailable_reason']}" + (f" (الحساب المقترح: {p['suggest']})" if p.get("suggest") else ""))
            continue
        print(f"{p['path']} [{p['role']}] {p['seconds']}s — {len(p['violations'])} مخالفة")
        for v in p["violations"]:
            mark = "≈" if v["justified"] else "✘"
            print(f"  {mark} {v['kind']}: {v['selector']} {v['detail']} ×{v['count']} ({', '.join(v['seen_in'][:3])})")
    print(f"الأدلّة: {EVIDENCE_DIR / a.card / head}")
    return 1 if manifest["unjustified"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
