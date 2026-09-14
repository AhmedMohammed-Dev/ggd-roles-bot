# -*- coding: utf-8 -*-
"""
معاينة شكل اللوحة في المتصفح — بلا ديسكورد وبلا إعادة تشغيل البوت.

لماذا هذه الأداة؟
-----------------
أي تعديل في شكل اللوحة أو بطاقة الدور كان لا يُرى إلا بعد إعادة تشغيل البوت وكتابة
‎/roles‎ في السيرفر. هذه الأداة تبني نفس الرسائل من نفس دوال bot.py وترسمها كصفحة
HTML تشبه عرض ديسكورد، فترى النتيجة فوراً قبل أي نشر.

⚠️ لا علاقة لها بعمل البوت: لا تُستورد من bot.py ولا تُستدعى أثناء تشغيله.

التشغيل:   python preview_board.py
الناتج :   _board_preview.html  (افتحه في أي متصفح)
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import List

import discord

import bot

OUT = Path(__file__).resolve().parent / "_board_preview.html"


def esc(text: str) -> str:
    return html.escape(text or "")


def md(text: str) -> str:
    """تحويل ماركداون ديسكورد البسيط إلى HTML (عريض/مائل/كود/روابط)."""
    out = esc(text)
    out = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2" target="_blank">\1</a>', out)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*", r"<i>\1</i>", out)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    return out.replace("\n", "<br>")


def icon(url: str | None, cls: str) -> str:
    return f'<img class="{cls}" src="{esc(url)}">' if url else ""


def button_emoji(item) -> str:
    """إيموجي الزر كما يراه المستخدم في ديسكورد (إيموجي عام أو اسم إيموجي مخصص)."""
    emoji = getattr(item, "emoji", None)
    if emoji is None:
        return ""
    if isinstance(emoji, discord.PartialEmoji):
        # ديسكورد يحوّل الإيموجي العام أيضاً إلى PartialEmoji بلا معرّف
        if emoji.id is None:
            return esc(emoji.name or "") + " "
        return f":{esc(emoji.name or '')}: "
    return esc(str(emoji)) + " "


def fields_html(fields) -> str:
    """حقول ديسكورد: الحقول المضمّنة (inline) تُصفّ ثلاثة في صف، وغيرها يأخذ صفاً كاملاً."""
    rows: List[str] = []
    pending: List[str] = []

    def flush() -> None:
        if pending:
            cols = "".join(f'<div class="field" style="flex:1 1 0">{cell}</div>' for cell in pending)
            rows.append(f'<div class="field-row">{cols}</div>')
            pending.clear()

    for field in fields:
        header = "&nbsp;" if not field.name.strip("\u200b \u00a0") else md(field.name)
        cell = f'<div class="field-name">{header}</div><div class="field-value">{md(field.value)}</div>'
        if field.inline:
            pending.append(cell)
            if len(pending) == 3:
                flush()
        else:
            flush()
            rows.append(f'<div class="field-row"><div class="field" style="flex:1 1 100%">{cell}</div></div>')
    flush()
    return "".join(rows)


def embed_html(embed) -> str:
    color = f"#{embed.color.value:06x}" if embed.color else "#4f545c"
    parts = [f'<div class="embed" style="border-left-color:{color}">']
    if embed.author:
        parts.append(f'<div class="author">{icon(embed.author.icon_url, "author-icon")}{md(embed.author.name)}</div>')
    if embed.title:
        parts.append(f'<div class="title">{md(embed.title)}</div>')
    if embed.description:
        parts.append(f'<div class="desc">{md(embed.description)}</div>')
    parts.append(fields_html(embed.fields))
    if embed.image and embed.image.url:
        parts.append(f'<img class="embed-image" src="{esc(embed.image.url)}">')
    if embed.footer:
        parts.append(f'<div class="footer">{icon(embed.footer.icon_url, "footer-icon")}{md(embed.footer.text)}</div>')
    parts.append("</div>")
    return "".join(parts)


BUTTON_CLASS = {"success": "b-green", "danger": "b-red", "primary": "b-blue", "secondary": "b-grey"}


def buttons_html(view) -> str:
    rows: dict = {}
    for item in view.children:
        rows.setdefault(item.row or 0, []).append(item)
    out = []
    for row in sorted(rows):
        cells = "".join(
            f'<span class="btn {BUTTON_CLASS.get(str(item.style).split(".")[-1], "b-grey")}'
            f'{" disabled" if item.disabled else ""}">{button_emoji(item)}{esc(item.label)}</span>'
            for item in rows[row]
        )
        out.append(f'<div class="btn-row">{cells}</div>')
    return "".join(out)


def page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html dir="rtl" lang="ar"><head><meta charset="utf-8"><title>{esc(title)}</title>
<style>
  body {{ background:#313338; color:#dbdee1; font-family:"Segoe UI","Noto Naskh Arabic",sans-serif;
         margin:0; padding:24px; }}
  h2 {{ font-size:14px; color:#949ba4; font-weight:600; letter-spacing:.02em; margin:26px 0 8px; }}
  .embed {{ background:#2b2d31; border-left:4px solid #4f545c; border-radius:6px;
            padding:12px 14px; max-width:520px; margin-inline-start:auto; }}
  .author {{ display:flex; align-items:center; gap:6px; font-size:13px; font-weight:600;
             color:#f2f3f5; margin-bottom:4px; }}
  .author-icon {{ width:20px; height:20px; border-radius:50%; object-fit:cover; }}
  .title {{ font-size:16px; font-weight:700; color:#f2f3f5; margin-bottom:6px; }}
  .desc {{ font-size:14px; line-height:1.4; }}
  .desc a, .field-value a {{ color:#00a8fc; text-decoration:none; }}
  code {{ background:#1e1f22; border-radius:4px; padding:1px 4px; font-size:12px; }}
  .field-row {{ display:flex; gap:10px; margin-top:8px; }}
  .field {{ min-width:0; font-size:14px; line-height:1.35; }}
  .field-name {{ font-weight:700; color:#f2f3f5; margin-bottom:2px; }}
  .field-value {{ color:#dbdee1; }}
  .embed-image {{ width:100%; border-radius:4px; margin-top:10px; display:block; }}
  .footer {{ display:flex; align-items:center; gap:6px; font-size:12px; color:#b5bac1; margin-top:10px; }}
  .footer-icon {{ width:16px; height:16px; border-radius:50%; }}
  /* ديسكورد يرتب الأزرار من اليسار لليمين دائماً (حتى مع نص عربي) */
  .btn-row {{ display:flex; gap:8px; margin-top:8px; flex-wrap:wrap; max-width:520px; direction:ltr; }}
  .btn {{ background:#4e5058; color:#fff; font-size:14px; padding:8px 12px; border-radius:8px;
          white-space:nowrap; display:inline-flex; align-items:center; gap:6px; }}
  .b-green {{ background:#248046; }} .b-red {{ background:#da373c; }}
  .b-blue {{ background:#5865f2; }} .disabled {{ opacity:.45; }}
  .wrap {{ display:flex; gap:24px; flex-wrap:wrap; align-items:flex-start; }}
  .ephemeral-note {{ font-size:12px; color:#b5bac1; background:#2b2d31; border-radius:6px 6px 0 0;
                     padding:6px 12px; max-width:520px; }}
</style></head><body>{body}</body></html>"""


def main() -> None:
    body = (
        '<h2>١) اللوحة العامة (تُرسل بـ /roles) — ثابتة ولا تتغير بضغطات الآخرين</h2>'
        f'<div>{embed_html(bot.build_panel_embed(0))}{buttons_html(bot.RoleBoardView(0))}</div>'
        '<h2>٢) بطاقة الدور: مع صورة رسمية، وبطاقة دور بلا صورة</h2>'
        f'<div class="wrap">{embed_html(bot.build_role_embed("sheriff"))}'
        f'{embed_html(bot.build_role_embed("medium"))}</div>'
        '<h2>٣) النسخة الخاصة بالضاغط بعد تصفية «🟢 الإوز» — واللوحة العامة لم تتغيّر</h2>'
        '<div class="ephemeral-note">👁️ رسالة تراها أنت وحدك (ephemeral) — تنقلاتك فيها لا يراها أحد</div>'
        f'<div>{embed_html(bot.build_panel_embed(0, "goose", private=True))}'
        f'{buttons_html(bot.RoleBoardView(0, "goose"))}</div>'
        '<h2>٤) آخر صفحة من تصفية «🟡 المحايدون» — أصغر لوحة ممكنة (3 أدوار)</h2>'
        f'<div>{embed_html(bot.build_panel_embed(bot.total_pages("neutral") - 1, "neutral", private=True))}'
        f'{buttons_html(bot.RoleBoardView(bot.total_pages("neutral") - 1, "neutral"))}</div>'
        '<h2>٥) بطاقة ‎/help‎ — شرح استخدام البوت للعضو الجديد</h2>'
        f'<div>{embed_html(bot.build_help_embed())}</div>'
    )

    OUT.write_text(page("معاينة لوحة الأدوار", body), encoding="utf-8")
    print(f"✅ تم إنشاء المعاينة: {OUT}")


if __name__ == "__main__":
    main()
