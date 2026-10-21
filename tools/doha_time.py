"""ساعةُ المشروع الواحدة: توقيتُ الدوحة (UTC+3) ثابتاً لا يتبع ساعةَ الجهاز ولا TZ في Git Bash."""
from datetime import datetime, timedelta, timezone

DOHA = timezone(timedelta(hours=3))


def now() -> datetime:
    """اللحظةُ الآن بتوقيت الدوحة (واعيةٌ بالمنطقة)."""
    return datetime.now(DOHA)


def to_doha(moment: datetime) -> datetime:
    """يحوّل أيَّ لحظةٍ واعيةٍ بالمنطقة (مثل UTC من GitHub) إلى الدوحة."""
    return moment.astimezone(DOHA)


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    print(now().isoformat(timespec="seconds"))
