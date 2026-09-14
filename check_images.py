# -*- coding: utf-8 -*-
"""
فحص روابط صور الأدوار — يتأكد أن كل رابط داخل قاموس ROLES يعمل فعلاً.

لماذا هذا السكربت؟
-------------------
روابط صور ويكي اللعبة تحتوي على مسار مجزّأ لا يمكن تخمينه (مثل ‎/5/56/‎)،
فخطأ حرفي واحد يعني صورة مكسورة في بطاقة الدور — وهذا لا يظهر إطلاقاً في
الاختبارات العادية لأنها تعمل بدون إنترنت. هذا السكربت يقرأ القاموس من
bot.py ويفحص كل رابط على الشبكة الحقيقية ثم يطبع النتيجة.

⚠️ يحتاج اتصالاً بالإنترنت. لا يُستدعى تلقائياً مع الاختبارات.

التشغيل:
    python check_images.py
    python check_images.py --all      # يعرض كل رابط ونتيجته، وليس المكسورة فقط

الرمز الترجيعي: 0 = كل الصور سليمة، 1 = توجد صور مكسورة.
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Tuple

import bot

# ترويسات متصفح حقيقي: شبكة ويكي اللعبة ترفض الطلبات بلا وكيل مستخدم معروف.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Referer": "https://goose-goose-duck.fandom.com/",
    "Accept": "image/avif,image/webp,image/png,image/*,*/*;q=0.8",
}
TIMEOUT_SECONDS = 30


def check_one(item: Tuple[str, str]) -> Tuple[str, str, str]:
    """يفحص رابطاً واحداً ويُرجع (المفتاح، الحالة، سبب الفشل إن وُجد)."""
    key, url = item
    try:
        request = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            content_type = response.headers.get("Content-Type", "")
            head = response.read(16)
        if response.status != 200:
            return key, f"HTTP {response.status}", url
        if not content_type.startswith("image"):
            return key, f"ليس صورة ({content_type})", url
        if len(head) < 8:
            return key, "ملف فارغ", url
        return key, "OK", url
    except urllib.error.HTTPError as error:
        return key, f"HTTP {error.code}", url
    except Exception as error:  # noqa: BLE001 - نريد عرض السبب كما هو للمستخدم
        return key, f"{type(error).__name__}: {error}"[:120], url


def main(argv: List[str]) -> int:
    show_all = "--all" in argv
    urls: Dict[str, str] = {
        key: role["image"] for key, role in bot.ROLES.items() if role.get("image")
    }
    without_image = [key for key, role in bot.ROLES.items() if not role.get("image")]

    print(f"إجمالي الأدوار: {len(bot.ROLES)}")
    print(f"أدوار لها صورة: {len(urls)}  |  أدوار بلا صورة رسمية: {len(without_image)}")
    print("جارٍ فحص الروابط على الإنترنت...\n")

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(check_one, urls.items()))

    broken = [(key, reason) for key, reason, _ in results if reason != "OK"]
    for key, reason, _ in results:
        if show_all or reason != "OK":
            print(f"  {'✅' if reason == 'OK' else '❌'} {key:<16} {reason}")

    print("\n" + "─" * 52)
    if broken:
        print(f"❌ توجد {len(broken)} صورة مكسورة — صحّح روابطها في قاموس ROLES داخل bot.py:")
        for key, reason in broken:
            print(f"   • {key}: {reason}")
        return 1
    print("✅ كل روابط الصور تعمل بشكل صحيح.")
    if without_image:
        print(f"ℹ️  {len(without_image)} دوراً بلا صورة رسمية (تظهر البطاقة بدونه): "
              + "، ".join(without_image))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
