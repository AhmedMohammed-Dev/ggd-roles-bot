# -*- coding: utf-8 -*-
"""
🔍 فاحص الجاهزية — شغّله قبل تشغيل البوت أو قبل النشر
=====================================================
    python check_setup.py

يقوم بأربعة أشياء (ولا يحتاج أي مكتبة خارجية ولا يعرض التوكن في الشاشة):
  1. يتأكد أن إعدادات Python سليمة.
  2. يقرأ ملف .env ويتأكد أن التوكن موجود وبالشكل الصحيح.
  3. يتصل بديسكورد ويطبع اسم البوت (أفضل دليل أن التوكن شغّال).
  4. ينبّهك على أي إعداد ناقص للاستضافة 24/7.

لا يغيّر أي إعداد ولا يرسل أي رسالة — قراءة فقط.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent

OK = "✅"
BAD = "❌"
WARN = "⚠️ "

problems: list[str] = []
notes: list[str] = []


def line() -> None:
    print("-" * 62)


def load_env_file(path: Path) -> None:
    """نفس منطق bot.py: لا يستبدل متغيّراً موجوداً في البيئة."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        text = raw.strip()
        if not text or text.startswith("#"):
            continue
        if text.startswith("export"):
            text = text[len("export"):].lstrip()
        key, sep, value = text.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not key or not (key[0].isalpha() or key[0] == "_"):
            continue
        if not all(c.isalnum() or c == "_" for c in key):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].strip()
        os.environ.setdefault(key, value)


def mask(secret: str) -> str:
    """لا نطبع التوكن كاملاً أبداً — حتى لا يبقى في سجلّ الشاشة."""
    if len(secret) <= 12:
        return "*" * len(secret)
    return f"{secret[:6]}…{secret[-4:]} ({len(secret)} حرفاً)"


def valid_token_shape(token: str) -> bool:
    parts = token.split(".")
    if len(parts) != 3 or len(token) < 50:
        return False
    for part in parts:
        if not part or not part.isascii():
            return False
        if not part.replace("-", "").replace("_", "").isalnum():
            return False
    return True


def discord_get(path: str, token: str) -> dict:
    request = urllib.request.Request(
        "https://discord.com/api/v10" + path,
        headers={
            "Authorization": f"Bot {token}",
            "User-Agent": "ggd-roles-bot-setup-check/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    print()
    line()
    print("  🔍 فاحص جاهزية بوت أدوار Goose Goose Duck")
    line()

    # 1) نسخة بايثون
    version = sys.version_info
    if version >= (3, 10):
        print(f"{OK} نسخة Python: {version.major}.{version.minor}.{version.micro}")
    else:
        print(f"{BAD} نسخة Python قديمة ({version.major}.{version.minor}) — المطلوب 3.10 أو أحدث")
        problems.append("ثبّت Python 3.10 أو أحدث من python.org")

    # 2) ملف .env
    env_path = HERE / ".env"
    if env_path.is_file():
        print(f"{OK} ملف .env موجود وتمت قراءته")
        load_env_file(env_path)
    else:
        print(f"{WARN}لا يوجد ملف .env — إن كنت على منصّة استضافة فتجاهل هذا السطر")
        notes.append("محلياً: انسخ .env.example باسم .env ثم الصق التوكن فيه")

    # 3) التوكن
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        print(f"{BAD} التوكن غير موجود — لم أجد DISCORD_TOKEN")
        problems.append("الصق التوكن أمام السطر DISCORD_TOKEN= داخل ملف .env")
    elif not valid_token_shape(token):
        print(f"{BAD} قيمة DISCORD_TOKEN غير صحيحة الشكل: {mask(token)}")
        print("     التوكن نصّ طويل يحوي نقطتين — تأكد أنك نسخته كاملاً من زر Copy")
        problems.append("أعد نسخ التوكن من Discord Developer Portal → Bot → Reset Token")
    else:
        print(f"{OK} شكل التوكن سليم: {mask(token)}")

        # 4) الاتصال الفعلي بديسكورد (أفضل إثبات أن التوكن يعمل)
        print("⏳ أتحقق من التوكن مع ديسكورد...")
        try:
            me = discord_get("/users/@me", token)
            print(f"{OK} التوكن يعمل — اسم البوت: {me.get('username')} (المعرّف: {me.get('id')})")
        except urllib.error.HTTPError as error:
            if error.code == 401:
                print(f"{BAD} ديسكورد رفض التوكن (401) — التوكن خاطئ أو تم إعادة تعيينه")
                problems.append("خذ توكناً جديداً من Reset Token وضعه في .env")
            elif error.code == 403:
                print(f"{BAD} التوكن صحيح لكن ممنوع من الوصول (403)")
                problems.append("تأكد أن التطبيق يعمل وأن الحساب غير موقوف")
            else:
                print(f"{WARN}رد ديسكورد بكود {error.code} — أعد المحاولة لاحقاً")
        except urllib.error.URLError as error:
            print(f"{WARN}تعذّر الاتصال بالإنترنت ({error.reason}) — تخطّيت هذا الفحص")
            notes.append("لا مشكلة إن كان الإنترنت مقطوعاً الآن، لكن البوت يحتاجه ليعمل")
        except (OSError, ValueError) as error:
            print(f"{WARN}تعذّر إكمال فحص الاتصال: {error}")

    # 5) إعدادات الاستضافة 24/7
    public_url = os.getenv("PUBLIC_URL", "").strip()
    guild_id = os.getenv("GUILD_ID", "").strip()
    ping_seconds = os.getenv("SELF_PING_SECONDS", "").strip() or "600"

    if guild_id.isdigit():
        print(f"{OK} GUILD_ID مضبوط — أمر /roles سيظهر فوراً في سيرفرك")
    elif guild_id:
        print(f"{BAD} GUILD_ID ليس رقماً — انسخه بزر الفأرة الأيمن على السيرفر → Copy Server ID")
        problems.append("GUILD_ID يجب أن يكون أرقاماً فقط (أو اتركه فارغاً)")
    else:
        print(f"{WARN}GUILD_ID فارغ — الأمر السلاش العالمي قد يتأخّر ظهوره حتى ساعة")
        notes.append("لظهور فوري: فعّل Developer Mode في ديسكورد ثم Copy Server ID وضعه في GUILD_ID")

    if public_url.startswith("https://"):
        print(f"{OK} PUBLIC_URL مضبوط — القرع الذاتي سيمنع نوم السيرفر المجاني")
    else:
        print(f"{WARN}PUBLIC_URL غير مضبوط — بعد النشر ضعه ليعمل القرع الذاتي (أو استخدم UptimeRobot)")
        notes.append("مثال: PUBLIC_URL=https://your-app.onrender.com")

    if ping_seconds.isdigit() and int(ping_seconds) < 900:
        print(f"{OK} SELF_PING_SECONDS = {ping_seconds} ثانية (أقل من 15 دقيقة، مناسب)")
    else:
        print(f"{WARN}SELF_PING_SECONDS = {ping_seconds} — اجعله أقل من 900 ثانية")
        notes.append("السيرفرات المجانية تنام بعد 15 دقيقة خمول، فاجعل القيمة 600 أو أقل")

    if os.getenv("ENABLE_PREFIX_COMMANDS", "").strip().lower() in {"1", "true", "yes", "on", "y"}:
        notes.append("لأمر !roles: تأكد من تفعيل Message Content Intent في لوحة المطوّرين")

    # 6) الخلاصة
    line()
    if problems:
        print(f"{BAD} يوجد {len(problems)} أمر يجب إصلاحه:")
        for item in problems:
            print(f"   • {item}")
    else:
        print(f"{OK} كل شيء جاهز — شغّل البوت الآن:  python bot.py")
    if notes:
        print()
        for item in notes:
            print(f"{WARN}{item}")
    line()
    print()
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
