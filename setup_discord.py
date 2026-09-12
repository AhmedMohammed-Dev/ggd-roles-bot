# -*- coding: utf-8 -*-
"""
⚙️ ضبط إعدادات ديسكورد تلقائياً — شغّله بعد أن تضع التوكن في .env
================================================================
    python setup_discord.py            # يتأكد من التوكن ويضبط GUILD_ID تلقائياً
    python setup_discord.py --lock     # زيادةً: يقفل البوت على سيرفراتك فقط (أمان أعلى)

ما يفعله (كل شيء قراءة فقط ما عدا سطر GUILD_ID داخل .env):
  1. يتأكد أن التوكن يعمل فعلاً على ديسكورد.
  2. يجيب اسم البوت ومعرّفه ويبني رابط الدعوة الصحيح.
  3. لو البوت في سيرفر واحد فقط: يكتب معرّفه في GUILD_ID ليظهر أمر /roles فوراً.
  4. لو البوت ليس في أي سيرفر: يطبع لك رابط الدعوة الجاهز.

⚠️ لا يطبع التوكن أبداً في الشاشة.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV_PATH = HERE / ".env"

# صلاحيات الدعوة: عرض الروم + إرسال الرسائل + إدراج الروابط (Embed). بلا Administrator.
PERMISSIONS = 19456
API = "https://discord.com/api/v10"

OK, BAD, WARN = "✅", "❌", "⚠️ "


def load_env_file(path: Path) -> None:
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


def write_env_value(key: str, value: str) -> bool:
    """يحدّث سطراً واحداً في .env دون المساس بالتعليقات أو بقية الملف."""
    if not ENV_PATH.is_file():
        return False
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    for index, raw in enumerate(lines):
        stripped = raw.strip()
        if stripped.startswith(f"{key}=") or stripped.startswith(f"export {key}="):
            if stripped.split("=", 1)[1].strip() == value:
                return False
            lines[index] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def api_get(path: str, token: str) -> object:
    request = urllib.request.Request(
        API + path,
        headers={"Authorization": f"Bot {token}", "User-Agent": "ggd-roles-bot-setup/1.0"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def mask(secret: str) -> str:
    return f"{secret[:6]}…{secret[-4:]}" if len(secret) > 12 else "*" * len(secret)


def main() -> int:
    print()
    print("=" * 62)
    print("  ⚙️  ضبط إعدادات ديسكورد للبوت")
    print("=" * 62)

    load_env_file(ENV_PATH)
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        print(f"{BAD} لا يوجد توكن — افتح .env وضع التوكن أمام DISCORD_TOKEN=")
        return 1
    print(f"{OK} التوكن مقروء من .env ({mask(token)})")

    try:
        me = api_get("/users/@me", token)
        guilds = api_get("/users/@me/guilds", token)
    except urllib.error.HTTPError as error:
        if error.code == 401:
            print(f"{BAD} ديسكورد رفض التوكن (401) — خذ توكناً جديداً من Reset Token")
        else:
            print(f"{BAD} ديسكورد رد بكود {error.code}")
        return 1
    except urllib.error.URLError as error:
        print(f"{BAD} تعذّر الاتصال بالإنترنت ({error.reason})")
        return 1

    bot_id = str(me.get("id", ""))
    print(f"{OK} التوكن يعمل — البوت: {me.get('username')} (المعرّف: {bot_id})")

    invite = (
        f"https://discord.com/api/oauth2/authorize?client_id={bot_id}"
        f"&permissions={PERMISSIONS}&scope=bot%20applications.commands"
    )

    assert isinstance(guilds, list)
    print(f"{OK} البوت موجود في {len(guilds)} سيرفر:")
    for guild in guilds:
        print(f"     • {guild.get('name')}  (المعرّف: {guild.get('id')})")

    if not guilds:
        print()
        print(f"{WARN}البوت ليس في أي سيرفر بعد. أضفه من هذا الرابط ثم أعد تشغيل هذا السكربت:")
        print(f"     {invite}")
        return 0

    # اختيار السيرفر: إن كان واحداً نضبطه تلقائياً، وإن كان أكثر نطلب التحديد يدوياً
    if len(guilds) == 1:
        chosen = str(guilds[0].get("id"))
    else:
        current = os.getenv("GUILD_ID", "").strip()
        found = [g for g in guilds if str(g.get("id")) == current]
        if found:
            chosen = current
        else:
            print()
            print(f"{WARN}البوت في أكثر من سيرفر — اختر واحداً وضعه في GUILD_ID داخل .env:")
            for guild in guilds:
                print(f"     GUILD_ID={guild.get('id')}    # {guild.get('name')}")
            print(f"     (الحالي في .env: {current or 'فارغ'})")
            return 0

    if write_env_value("GUILD_ID", chosen):
        name = next((g.get("name") for g in guilds if str(g.get("id")) == chosen), "")
        print(f"{OK} تم ضبط GUILD_ID={chosen}  ({name}) — أمر /roles سيظهر فوراً")
    else:
        print(f"{OK} GUILD_ID مضبوط مسبقاً على {chosen}")

    # خيار أمني اختياري: قصر البوت على هذه السيرفرات فقط
    if "--lock" in sys.argv:
        allowed = ",".join(str(g.get("id")) for g in guilds)
        if write_env_value("ALLOWED_GUILD_IDS", allowed):
            print(f"{OK} تم تفعيل القفل الأمني — البوت يعمل في هذه السيرفرات فقط:")
            for guild in guilds:
                print(f"     • {guild.get('name')}")
            print("     (لو أضفت البوت لسيرفر جديد لاحقاً، أضف معرّفه لنفس السطر وأعد التشغيل)")
    else:
        print()
        print(f"{WARN}نصيحة أمنية: لتقصر البوت على سيرفراتك وحدها (يخرج من أي سيرفر غريب)")
        print("     شغّل:  python setup_discord.py --lock")

    print()
    print(f"{OK} الخطوة التالية:  python bot.py    أو اضغط START.bat")
    print(f"     رابط دعوة البوت (لو احتجت): {invite}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
