# صورةُ فحص prepush للمضخّة (W-20261023-016): صورة المعاينة المحلية + git وradon وفاحص الأنواع بإصدارات CI نفسِها
# (quality-gate.yml: radon==6.0.1؛ requirements-mypy.txt في المنصّة: mypy 1.10.0 وstubs). إن تغيّرت الإصدارات في المنصّة
# سقط حارسُ mypy بـ«إصدارات غير ما تحكم به البوّابة» (فشلٌ لا نجاحٌ زائف) حتى تُعاد بناءُ الصورة بالإصدارات الجديدة.
# تُبنى مرّةً بشبكة:  docker build -t maestro-prepush:1 tools/prepush_image
FROM schoolos-preview:latest
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && find /var/lib/apt/lists -type f -delete \
    && pip install --no-cache-dir radon==6.0.1 mypy==1.10.0 django-stubs==5.0.2 djangorestframework-stubs==3.15.0
# متصفّح chromium لسقّاطة axe (tests/test_a11y_axe_ratchet.py) كما في وظيفة axe-a11y في CI؛ المسارُ خارج HOME فلا يضيع مع HOME=/tmp
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
RUN playwright install --with-deps chromium \
    && find /var/lib/apt/lists -type f -delete \
    && chmod -R a+rX /opt/ms-playwright
USER appuser
