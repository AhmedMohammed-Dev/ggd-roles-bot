# صورة جاهزة للنشر على Koyeb / Render / Fly.io / Railway / أي خادم VPS
FROM python:3.12-slim

# تشغيل التطبيق بمستخدم غير جذري (حماية: لو اختُرق لا يحصل المهاجم على root)
RUN useradd --create-home --shell /usr/sbin/nologin botuser

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY --chown=botuser:botuser bot.py .

USER botuser
EXPOSE 8080

# فحص صحة الحاوية (صيغة exec لتجنّب مشاكل التنصيص في الشِل)
HEALTHCHECK --interval=60s --timeout=10s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import os,urllib.request as u; u.urlopen('http://127.0.0.1:'+os.getenv('PORT','8080')+os.getenv('KEEPALIVE_PATH','/healthz'),timeout=5).read()"]

CMD ["python", "-u", "bot.py"]
