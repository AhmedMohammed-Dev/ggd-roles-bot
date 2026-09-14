# -*- coding: utf-8 -*-
"""
اختبارات سريعة للبوت — لا تحتاج توكن ولا اتصالاً بالإنترنت.
التشغيل:  python -m unittest -v test_bot.py
"""

import asyncio
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import discord

import bot


class TestRolesData(unittest.TestCase):
    def test_requested_roles_exist(self):
        """الأدوار التي طلبها المستخدم يجب أن تكون موجودة."""
        for key in ("goose", "duck", "dodo", "sheriff", "pelican", "engineer"):
            self.assertIn(key, bot.ROLES, f"الدور {key} غير موجود في ROLES")

    def test_every_role_has_required_fields(self):
        required = {"name_ar", "name_en", "emoji", "team", "goal", "how", "tips"}
        for key, role in bot.ROLES.items():
            missing = required - role.keys()
            self.assertFalse(missing, f"الدور {key} ينقصه: {missing}")

    def test_team_is_valid(self):
        for key, role in bot.ROLES.items():
            self.assertIn(role["team"], bot.TEAMS, f"فئة غير معروفة في الدور {key}")

    def test_arabic_text_present(self):
        """كل دور له شرح عربي حقيقي (حروف عربية)."""
        arabic = re.compile(r"[\u0600-\u06FF]")
        for key, role in bot.ROLES.items():
            for field in ("name_ar", "goal", "how", "tips"):
                self.assertTrue(
                    arabic.search(role[field]), f"الحقل {field} في الدور {key} لا يحتوي نصاً عربياً"
                )

    def test_images_are_https_or_none(self):
        for key, role in bot.ROLES.items():
            image = role.get("image")
            if image is not None:
                self.assertTrue(image.startswith("https://"), f"رابط صورة غير آمن في الدور {key}")

    def test_role_keys_are_safe_identifiers(self):
        for key in bot.ROLES:
            self.assertRegex(key, r"^[a-z][a-z0-9_]{0,30}$")


class TestEmbeds(unittest.TestCase):
    def test_role_embed_has_name_color_and_image(self):
        embed = bot.build_role_embed("sheriff")
        role = bot.ROLES["sheriff"]
        self.assertIn(role["name_ar"], embed.title)
        self.assertIn(role["name_en"], embed.title)
        self.assertEqual(embed.color.value, bot.TEAMS["goose"]["color"])
        self.assertIsNotNone(embed.image.url)

    def test_team_colors_are_distinct(self):
        colors = {team["color"] for team in bot.TEAMS.values()}
        self.assertEqual(len(colors), len(bot.TEAMS), "ألوان الفئات يجب أن تكون مميزة")

    def test_every_embed_fits_discord_limits(self):
        """حدود ديسكورد: عنوان 256، شرح 4096، حقل 1024، والحجم الكلي 6000 حرف."""
        for key in bot.ROLES:
            embed = bot.build_role_embed(key)
            self.assertLessEqual(len(embed.title or ""), 256, key)
            self.assertLessEqual(len(embed.description or ""), 4096, key)
            for field in embed.fields:
                self.assertLessEqual(len(field.name), 256, key)
                self.assertLessEqual(len(field.value), 1024, f"حقل {field.name} في الدور {key} طويل جداً")
            self.assertLessEqual(len(embed), 6000, key)

    def test_role_without_image_is_handled(self):
        """الأدوار بلا صورة يجب أن تُبنى بدون أخطاء وبدون صورة (لا رابط مكسور)."""
        key = "goose"
        patched = {name: dict(role) for name, role in bot.ROLES.items()}
        patched[key]["image"] = None
        with mock.patch.dict(bot.ROLES, patched, clear=True):
            embed = bot.build_role_embed(key)
        self.assertIsNone(embed.image.url)

    def test_roles_without_image_say_so_in_the_card(self):
        """إن لم توجد صورة رسمية للدور، تُذكر الحقيقة بوضوح في البطاقة بدل صمت مربك."""
        missing = [key for key, role in bot.ROLES.items() if not role.get("image")]
        self.assertTrue(missing, "افتراض الاختبار: توجد أدوار بلا صورة رسمية على الويكي")
        self.assertIn("لا تتوفّر صورة", bot.build_role_embed(missing[0]).description)

    def test_maps_field_is_shown_when_present(self):
        """الأدوار المقصورة على خرائط معيّنة تُظهر ذلك في البطاقة."""
        restricted = [key for key, role in bot.ROLES.items() if role.get("maps")]
        self.assertTrue(restricted, "افتراض الاختبار: توجد أدوار مقصورة على خرائط")
        embed = bot.build_role_embed(restricted[0])
        self.assertIn("🗺️ متاح في", [field.name for field in embed.fields])


class TestRosterCompleteness(unittest.TestCase):
    """القائمة الكاملة لأدوار اللعبة — تفشل لو حُذف دور سهواً أو بقي دور ناقصاً.

    المصدر: القائمة الرسمية لأدوار Goose Goose Duck (الوضع الكلاسيكي + الأوضاع الخاصة).
    أضف المفتاح الجديد هنا مع أي دور تضيفه حتى يبقى الدليل كاملاً.
    """

    EXPECTED = (
        # إوز (30)
        "goose", "sheriff", "engineer", "vigilante", "detective", "canadian", "avenger",
        "astral", "stalker", "soldier", "scientist", "survivalist", "fortune_teller",
        "mortician", "birdwatcher", "medium", "gravy", "lover_goose", "mimic", "bodyguard",
        "politician", "locksmith", "celebrity", "adventurer", "street_urchin", "tracker",
        "lobbyist", "coroner", "sensor", "lucid_dreamer",
        # بط (30)
        "duck", "professional", "assassin", "morphling", "spy", "cannibal", "demolitionist",
        "identity_thief", "silencer", "party", "hitman", "snitch", "ninja", "undertaker",
        "invisibility", "serial_killer", "warlock", "esper", "preacher", "cupid", "drone",
        "mime", "clown", "looter", "sniper", "witch_doctor", "lost_duckling", "carrier",
        "parasite", "swordsman",
        # محايدون (10)
        "dodo", "pelican", "pigeon", "vulture", "falcon", "raven", "dueling_dodos", "hawk",
        "cuckoo", "magpie",
        # أدوار الأوضاع الخاصة (16)
        "inquisitor", "saint", "demon_hunter", "seamstress", "high_priest", "initiate",
        "sin_eater", "crow", "villager", "vampire", "thrall", "mummy", "camo_duck",
        "chicken", "spotter", "owl",
    )

    def test_no_role_is_missing(self):
        self.assertEqual(sorted(bot.ROLES), sorted(self.EXPECTED))

    def test_all_three_teams_are_represented(self):
        counts: dict = {}
        for role in bot.ROLES.values():
            counts[role["team"]] = counts.get(role["team"], 0) + 1
        self.assertEqual(sorted(counts), sorted(bot.TEAMS))
        for team, count in counts.items():
            self.assertGreater(count, 3, f"فريق {team} فيه {count} دوراً فقط")

    def test_modes_are_declared_and_known(self):
        """أي دور بوضع خاص يجب أن يكون وضعه معرفاً، والوضع الافتراضي لا يُكتب صراحة."""
        for key, role in bot.ROLES.items():
            mode = role.get("mode")
            if mode is None:
                continue
            self.assertIn(mode, bot.MODES, f"وضع غير معروف في الدور {key}")
            self.assertNotEqual(mode, "classic", f"الدور {key}: الوضع الكلاسيكي هو الافتراضي")

    def test_special_roles_show_their_mode_in_the_card(self):
        for key, role in bot.ROLES.items():
            if not role.get("mode"):
                continue
            self.assertIn(bot.MODES[role["mode"]]["label"], bot.build_role_embed(key).description, key)

    def test_english_names_are_unique(self):
        names = [role["name_en"] for role in bot.ROLES.values()]
        self.assertEqual(len(names), len(set(names)), "يوجد دوران بنفس الاسم الإنجليزي")

    def test_maps_field_is_arabic_when_present(self):
        arabic = re.compile(r"[\u0600-\u06FF]")
        for key, role in bot.ROLES.items():
            maps = role.get("maps")
            if maps is None:
                continue
            self.assertTrue(arabic.search(maps), f"حقل الخرائط في {key} بلا نص عربي")

    def test_roster_is_reachable_through_the_board(self):
        """كل دور في القائمة يمكن الوصول إليه بالتنقل بين الصفحات."""
        reachable = []
        for page in range(bot.total_pages()):
            reachable.extend(bot.page_roles(page))
        self.assertEqual(sorted(reachable), sorted(self.EXPECTED))


class TestBoardLayout(unittest.TestCase):
    def test_pages_cover_all_roles_without_duplicates(self):
        collected = []
        for page in range(bot.total_pages()):
            collected.extend(bot.page_roles(page))
        self.assertEqual(collected, bot.ordered_role_keys())
        self.assertEqual(sorted(collected), sorted(bot.ROLES.keys()))
        self.assertEqual(len(set(collected)), len(collected))

    def test_featured_roles_are_on_first_page(self):
        """الأدوار الشهيرة تظهر في الصفحة الأولى حتى يجدها المستخدم بسرعة."""
        first_page = bot.page_roles(0)
        for key in bot.FEATURED_ROLES:
            self.assertIn(key, first_page, f"الدور {key} ليس في الصفحة الأولى")

    def test_no_more_than_ten_buttons_per_page(self):
        for page in range(bot.total_pages()):
            self.assertLessEqual(len(bot.page_roles(page)), 10, f"صفحة {page}")

    def test_view_respects_discord_component_limits(self):
        """الحد الرسمي: 5 صفوف × 5 أزرار = 25 عنصراً لكل رسالة."""
        for page in range(bot.total_pages()):
            view = bot.RoleBoardView(page)
            self.assertLessEqual(len(view.children), 25, f"صفحة {page}")
            rows = [item.row for item in view.children]
            self.assertLessEqual(max(rows), 4, f"صفحة {page}: عدد الصفوف يتجاوز الحد")
            for row in set(rows):
                self.assertLessEqual(rows.count(row), 5, f"صفحة {page}: أكثر من 5 أزرار في الصف {row}")
            # لا صفوف فارغة في المنتصف (ديسكورد يرفض ذلك)
            self.assertEqual(sorted(set(rows)), list(range(max(rows) + 1)), f"صفحة {page}")

    def test_navigation_reaches_first_and_last_page(self):
        first = bot.RoleBoardView(0)
        last = bot.RoleBoardView(999)  # يجب أن تُقيَّد لآخر صفحة
        self.assertEqual(first.page, 0)
        self.assertEqual(last.page, bot.total_pages() - 1)
        labels = [item.label for item in first.children]
        self.assertIn("⬅️ السابق", labels)
        self.assertIn("🎲 دور عشوائي", labels)

    def test_custom_ids_are_unique_and_short(self):
        view = bot.RoleBoardView(0)
        ids = [item.custom_id for item in view.children if item.custom_id]
        self.assertEqual(len(ids), len(set(ids)))
        for custom_id in ids:
            self.assertLessEqual(len(custom_id), 100)

    def test_button_labels_fit_limit(self):
        for key in bot.ROLES:
            button = bot.RoleButton(key, row=0)
            self.assertLessEqual(len(button.label), 80, key)


class TestTeamFilters(unittest.TestCase):
    """أزرار تصفية الفئات: تعرض فئة واحدة فقط بكل أدوارها وبعدد صفحات أقل."""

    @staticmethod
    def _filter_buttons(view):
        labels = {label for _, label in bot.TEAM_FILTERS} | {"📖 كل الأدوار"}
        return [item for item in view.children if item.label in labels]

    def test_filtered_pages_hold_exactly_that_team(self):
        for team in bot.TEAMS:
            reached = []
            for page in range(bot.total_pages(team)):
                reached.extend(bot.page_roles(page, team))
            expected = [key for key, role in bot.ROLES.items() if role["team"] == team]
            self.assertEqual(sorted(reached), sorted(expected), f"فئة {team}")
            self.assertTrue(all(bot.ROLES[key]["team"] == team for key in reached))

    def test_filtering_needs_fewer_pages_than_the_whole_roster(self):
        for team in bot.TEAMS:
            self.assertLess(bot.total_pages(team), bot.total_pages(), f"فئة {team}")

    def test_exactly_one_filter_button_is_active(self):
        unfiltered = self._filter_buttons(bot.RoleBoardView(0))
        self.assertEqual([item.label for item in unfiltered if item.disabled], ["📖 كل الأدوار"])
        for team, label in bot.TEAM_FILTERS:
            view = bot.RoleBoardView(0, team)
            self.assertEqual([item.label for item in self._filter_buttons(view) if item.disabled], [label])

    def test_unknown_filter_falls_back_to_the_full_roster(self):
        view = bot.RoleBoardView(0, "not-a-real-team")
        self.assertIsNone(view.team)
        self.assertEqual(view.page, 0)

    def test_filtered_views_respect_component_limits(self):
        for team in bot.TEAMS:
            for page in range(bot.total_pages(team)):
                view = bot.RoleBoardView(page, team)
                self.assertLessEqual(len(view.children), 25, f"{team} صفحة {page}")
                rows = [item.row for item in view.children]
                self.assertLessEqual(max(rows), 4, f"{team} صفحة {page}")
                self.assertEqual(sorted(set(rows)), list(range(max(rows) + 1)), f"{team} صفحة {page}")

    def test_page_indicator_reflects_the_filter(self):
        filtered = bot.RoleBoardView(0, "goose")
        labels = [item.label for item in filtered.children]
        self.assertIn(f"📄 1/{bot.total_pages('goose')}", labels)
        self.assertIn(bot.TEAMS["goose"]["label"], bot.build_panel_embed(0, "goose").footer.text)

    def test_every_page_is_full_except_the_last(self):
        for team in (None, *bot.TEAMS):
            for page in range(bot.total_pages(team) - 1):
                self.assertEqual(len(bot.page_roles(page, team)), bot.PER_PAGE, f"{team} صفحة {page}")


class TestBoardLook(unittest.TestCase):
    """الشكل العام: البانر والشعار واللون وأدوار نفس الفئة داخل بطاقة الدور."""

    def test_panel_shows_the_game_banner_and_logo(self):
        panel = bot.build_panel_embed(0)
        self.assertEqual(panel.image.url, bot.BRAND["banner"])
        self.assertEqual(panel.author.icon_url, bot.BRAND["logo"])
        self.assertEqual(panel.footer.icon_url, bot.BRAND["logo"])
        self.assertTrue(bot.BRAND["banner"].startswith("https://"))
        self.assertTrue(bot.BRAND["logo"].startswith("https://"))

    def test_panel_counts_match_the_roster(self):
        panel = bot.build_panel_embed(0)
        self.assertIn(str(len(bot.ROLES)), panel.author.name)
        for team_key, team in bot.TEAMS.items():
            count = sum(1 for role in bot.ROLES.values() if role["team"] == team_key)
            field = next(f for f in panel.fields if f.name == team["label"])
            self.assertIn(str(count), field.value)

    def test_panel_lists_this_page_roles_in_two_columns(self):
        panel = bot.build_panel_embed(0)
        listing = [f for f in panel.fields if "أدوار هذه الصفحة" in f.name]
        self.assertEqual(len(listing), 1)
        continuation = [f for f in panel.fields if f.name == "\u200b"]
        self.assertEqual(len(continuation), 1)
        mentioned = "\n".join([listing[0].value, continuation[0].value])
        for key in bot.page_roles(0):
            self.assertIn(bot.ROLES[key]["name_ar"], mentioned, key)

    def test_every_panel_fits_discord_limits(self):
        for team in (None, *bot.TEAMS):
            for page in range(bot.total_pages(team)):
                panel = bot.build_panel_embed(page, team)
                self.assertLessEqual(len(panel), 6000, f"{team} صفحة {page}")
                for field in panel.fields:
                    self.assertLessEqual(len(field.name), 256)
                    self.assertLessEqual(len(field.value), 1024)

    def test_role_card_links_to_the_wiki_search(self):
        embed = bot.build_role_embed("sheriff")
        self.assertIn(bot.wiki_link(bot.ROLES["sheriff"]), embed.description)
        self.assertIn("goose-goose-duck.fandom.com", bot.wiki_link(bot.ROLES["sheriff"]))

    def test_role_card_offers_related_roles_from_the_same_team(self):
        for key in bot.ROLES:
            peers = bot.related_roles(key)
            self.assertTrue(peers, f"الدور {key} بلا أدوار مقترحة")
            self.assertLessEqual(len(peers), 3)
            self.assertNotIn(key, peers)
            for peer in peers:
                self.assertEqual(bot.ROLES[peer]["team"], bot.ROLES[key]["team"], peer)
            self.assertIn("🧭 أدوار من نفس الفئة", [f.name for f in bot.build_role_embed(key).fields], key)

    def test_related_roles_are_stable_between_calls(self):
        """لا عشوائية: نفس الدور يعطي نفس الاقتراحات في كل مرة."""
        for key in ("sheriff", "assassin", "dodo"):
            self.assertEqual(bot.related_roles(key), bot.related_roles(key))


class TestCustomEmojis(unittest.TestCase):
    """إيموجيات السيرفر: لو كانت مرفوعة من قبل تظهر صورة الدور على زرّه، وإلا الإيموجي العام.

    البوت لم يعد يرفع إيموجيات بنفسه (لا يوجد أمر ‎/إيموجيات‎) — يقرأ الخريطة المحفوظة
    من قبل ويعرضها، وهذا ما يتحقق منه هذا القسم.
    """

    def test_slugs_are_valid_unique_discord_emoji_names(self):
        slugs = [bot.emoji_slug(key) for key in bot.ROLES]
        self.assertEqual(len(slugs), len(set(slugs)), "أسماء إيموجيات مكرّرة")
        for slug in slugs:
            self.assertRegex(slug, r"^[a-z0-9_]{2,32}$")
            self.assertTrue(slug.startswith(bot.EMOJI_NAME_PREFIX))

    def test_falls_back_to_the_unicode_emoji_without_custom_ones(self):
        self.assertEqual(bot.icon_for("sheriff"), bot.ROLES["sheriff"]["emoji"])
        self.assertEqual(bot.icon_markup("sheriff"), bot.ROLES["sheriff"]["emoji"])
        self.assertIsNone(bot.custom_icon("sheriff", 12345))
        self.assertIn(bot.ROLES["sheriff"]["emoji"], bot.build_role_embed("sheriff").title)

    def test_uses_the_custom_icon_when_the_guild_has_it(self):
        mapping = {"123": {"sheriff": {"id": "999", "name": "ggd_sheriff", "animated": False}}}
        with mock.patch.dict(bot._emoji_map, mapping, clear=True):
            icon = bot.icon_for("sheriff", 123)
            self.assertIsInstance(icon, discord.PartialEmoji)
            self.assertEqual(icon.id, 999)
            self.assertEqual(bot.icon_markup("sheriff", 123), "<:ggd_sheriff:999>")

            button = bot.RoleButton("sheriff", row=0, guild_id=123)
            self.assertEqual(button.label, bot.ROLES["sheriff"]["name_ar"])
            self.assertEqual(button.emoji.id, 999)

            card = bot.build_role_embed("sheriff", 123)
            self.assertIn("999", card.author.icon_url or "")
            self.assertIn("<:ggd_sheriff:999>", card.title)

    def test_saved_map_is_read_from_disk(self):
        mapping = {"1": {"goose": {"id": "5", "name": "ggd_goose", "animated": False}}}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "role_emojis.json"
            path.write_text(json.dumps(mapping), encoding="utf-8")
            with mock.patch.object(bot, "EMOJI_MAP_PATH", path):
                self.assertEqual(bot.load_emoji_map(), mapping)

    def test_broken_emoji_map_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "role_emojis.json"
            path.write_text("{هذا ليس JSON}", encoding="utf-8")
            with mock.patch.object(bot, "EMOJI_MAP_PATH", path):
                self.assertEqual(bot.load_emoji_map(), {})

    def test_registered_commands(self):
        """‎/help‎ و‎/مساعدة‎ كلاهما مسجّل: من كتب help لا يجد الأمر غائباً، ومن كتب بالعربي يجده."""
        names = {command.name for command in bot.client.tree.get_commands()}
        self.assertIn("roles", names)
        self.assertIn("دور", names)
        self.assertIn("help", names, "‎/help‎ هو الاسم الذي يكتبه اللاعب تلقائياً")
        self.assertIn("مساعدة", names, "‎/مساعدة‎ لمن يكتب بالعربي")
        self.assertNotIn("إيموجيات", names, "أمر رفع الإيموجيات أُزيل بقرار من صاحب السيرفر")

    def test_help_description_is_arabic(self):
        """وصف الأمرين (الذي يظهر في قائمة ‎/‎) مكتوب بالعربي أيضاً."""
        commands = [c for c in bot.client.tree.get_commands() if c.name in ("help", "مساعدة")]
        self.assertEqual(len(commands), 2)
        for command in commands:
            self.assertRegex(command.description, r"[\u0600-\u06FF]", command.name)


class TestHelpCommand(unittest.TestCase):
    """بطاقة المساعدة (‎/help‎ و‎/مساعدة‎): تشرح للعضو الجديد بالعربي كيف يتعامل مع البوت."""

    def test_every_step_appears_in_the_card(self):
        embed = bot.build_help_embed()
        text = "\n".join(
            [embed.title or "", embed.description or "", embed.footer.text or ""]
            + [f"{field.name}\n{field.value}" for field in embed.fields]
        )
        for wanted in (
            "/help",
            "/roles",
            "/دور",
            "المحايدون",
            "عشوائي",
            "نسخة خاصة بك",
            "للمشرفين",
            "مساعدة",
        ):
            self.assertIn(wanted, text, wanted)

    def test_both_command_names_show_the_same_arabic_card(self):
        """الاسمان يؤديان لنفس البطاقة تماماً — لا نسخة إنجليزية ولا اختلاف في النص."""
        cards = []
        for command in (bot.help_slash, bot.help_ar_slash):
            interaction = FakeInteraction(ephemeral=False)
            asyncio.run(command.callback(interaction))
            cards.append(interaction.response.sent["embed"])
        self.assertEqual(cards[0].title, cards[1].title)
        self.assertEqual(
            [f.value for f in cards[0].fields], [f.value for f in cards[1].fields]
        )

    def test_the_card_is_written_in_arabic(self):
        """كل نصوص البطاقة عربية (بعد إيموجي أو رمز الخطوة) وبلا جمل إنجليزية.

        الاستثناء الوحيد: أسماء الأوامر نفسها (‎/help‎ و‎/roles‎) فتُكتب كما هي بالإنجليزية،
        لأن المستخدم لا يمكنه كتابتها بالعربي في خانة الأمر.
        """
        embed = bot.build_help_embed()
        arabic = re.compile(r"[\u0600-\u06FF]")
        parts = [embed.title or "", embed.description or "", embed.footer.text or ""]
        for field in embed.fields:
            self.assertTrue(arabic.search(field.name), f"عنوان الحقل ليس عربياً: {field.name}")
            self.assertTrue(arabic.search(field.value), f"نص الحقل ليس عربياً: {field.name}")
            parts.append(f"{field.name} {field.value}")
        self.assertTrue(arabic.search(parts[0]))
        latin = set(re.findall(r"[A-Za-z]{2,}", " ".join(parts)))
        self.assertEqual(latin - {"help", "roles"}, set(), f"كلمات إنجليزية غريبة: {latin}")

    def test_help_card_fits_discord_limits(self):
        embed = bot.build_help_embed()
        self.assertLessEqual(len(embed), 6000)
        self.assertLessEqual(len(embed.title or ""), 256)
        self.assertLessEqual(len(embed.description or ""), 4096)
        self.assertLessEqual(len(embed.fields), 25)
        for field in embed.fields:
            self.assertLessEqual(len(field.name), 256)
            self.assertLessEqual(len(field.value), 1024)
        self.assertEqual(embed.author.icon_url, bot.BRAND["logo"])

    def test_help_is_private_to_the_person_who_asks(self):
        interaction = FakeInteraction(ephemeral=False)
        asyncio.run(bot.help_slash.callback(interaction))
        self.assertTrue(interaction.response.sent["ephemeral"])
        card = interaction.response.sent["embed"]
        self.assertEqual(card.title, bot.build_help_embed().title)


class TestRoleSearch(unittest.TestCase):
    """البحث السريع بالاسم — اللي يشغّل أمر ‎/دور‎ واقتراحاته التلقائية."""

    def test_finds_roles_by_arabic_name(self):
        self.assertEqual(bot.find_role("شريف"), "sheriff")
        self.assertEqual(bot.find_role("السفاح"), "assassin")
        self.assertEqual(bot.find_role("الكندي"), "canadian")

    def test_ignores_diacritics_and_alef_variants(self):
        self.assertEqual(bot.find_role("الشَّريف"), "sheriff")
        self.assertEqual(bot.find_role("اوز"), bot.find_role("إوز"))
        self.assertEqual(bot.find_role("الحالم الواعى"), "lucid_dreamer")

    def test_works_with_english_names_and_keys(self):
        self.assertEqual(bot.find_role("sheriff"), "sheriff")
        self.assertEqual(bot.find_role("lover_goose"), "lover_goose")
        self.assertEqual(bot.find_role("lucid dreamer"), "lucid_dreamer")
        self.assertEqual(bot.find_role("LUCID DREAMER"), "lucid_dreamer")

    def test_exact_match_ranks_before_partial_ones(self):
        first, _ = bot.search_roles("الإوزة")[0]
        self.assertEqual(first, "goose")

    def test_empty_query_offers_the_first_page(self):
        hits = bot.search_roles("")
        self.assertEqual(hits[0][0], "goose")
        self.assertEqual([key for key, _ in hits][: bot.PER_PAGE], bot.page_roles(0))

    def test_choices_fit_discord_limits(self):
        for query in ("", "goose", "ا", "role"):
            hits = bot.search_roles(query)
            self.assertLessEqual(len(hits), 25, query)
            for key, label in hits:
                self.assertIn(key, bot.ROLES)
                self.assertIn(bot.ROLES[key]["name_ar"], label)
                self.assertLessEqual(len(label), 100)
                self.assertNotEqual(label.strip(), "")

    def test_unknown_query_returns_nothing(self):
        self.assertEqual(bot.search_roles("zzzzzz"), [])
        self.assertIsNone(bot.find_role("zzzzzz"))


class FakeResponse:
    """رد تفاعل مزيّف: يسجّل هل أرسلنا رسالة جديدة أم عدّلنا الموجودة."""

    def __init__(self) -> None:
        self.sent = None
        self.edited = None

    async def send_message(self, content=None, **kwargs) -> None:
        self.sent = dict(kwargs, content=content)

    async def edit_message(self, **kwargs) -> None:
        self.edited = kwargs


class FakeInteraction:
    """تفاعل مزيّف يكفي لاختبار منطق اللوحات بلا اتصال بديسكورد."""

    def __init__(self, ephemeral: bool) -> None:
        self.response = FakeResponse()
        self.message = mock.Mock()
        self.message.flags.ephemeral = ephemeral
        self.user = mock.Mock(id=1)
        # السيرفر المسموح من الإعدادات (أو أي معرّف إن لم تُفعَّل القائمة البيضاء)
        guild_id = next(iter(bot.ALLOWED_GUILD_IDS), 2)
        self.guild = mock.Mock(id=guild_id)
        self.guild_id = guild_id


class TestPrivateNavigation(unittest.TestCase):
    """اللوحة العامة يجب ألا تتغير بضغطات الآخرين — كل تنقل يفتح نسخة خاصة بالضاغط.

    هذه هي المشكلة التي حدثت فعلاً: اثنان يضغطان «التالي» في نفس اللحظة فيتبدّل شكل
    اللوحة على الروم كله. الاختبارات هنا تمنع رجوعها.
    """

    def _press(self, view, method: str, interaction) -> None:
        asyncio.run(getattr(view, method)(interaction))

    def _filter_button(self, view, label: str):
        return next(item for item in view.children if item.label == label)

    def test_navigation_on_the_public_board_opens_a_private_copy(self):
        interaction = FakeInteraction(ephemeral=False)
        self._press(bot.RoleBoardView(0), "_go_next", interaction)
        self.assertIsNotNone(interaction.response.sent, "يجب إرسال نسخة جديدة خاصة بالضاغط")
        self.assertTrue(interaction.response.sent["ephemeral"])
        self.assertIsNone(interaction.response.edited, "اللوحة العامة يجب ألا تُعدّل") 
        self.assertIn("نسخة خاصة بك", interaction.response.sent["embed"].footer.text)

    def test_navigation_inside_the_private_copy_edits_it_in_place(self):
        interaction = FakeInteraction(ephemeral=True)
        self._press(bot.RoleBoardView(1), "_go_prev", interaction)
        self.assertIsNone(interaction.response.sent, "لا نرسل رسالة جديدة داخل النسخة الخاصة")
        self.assertIsNotNone(interaction.response.edited)
        self.assertTrue(interaction.response.edited["embed"].footer.text.startswith("صفحة 1"))

    def test_filter_button_on_the_public_board_opens_a_private_copy(self):
        view = bot.RoleBoardView(0)
        interaction = FakeInteraction(ephemeral=False)
        asyncio.run(self._filter_button(view, "🟢 الإوز").callback(interaction))
        sent = interaction.response.sent
        self.assertTrue(sent["ephemeral"])
        self.assertIn("الإوز", sent["embed"].footer.text)
        self.assertEqual(sent["view"].team, "goose")

    def test_public_board_tells_visitors_their_clicks_are_private(self):
        self.assertIn("نسخة خاصة بك", bot.build_panel_embed(0).description)
        self.assertNotIn("نسخة خاصة بك", bot.build_panel_embed(0, private=True).description)

    def test_private_copy_still_offers_every_button(self):
        private = bot.RoleBoardView(2, "duck")
        labels = [item.label for item in private.children]
        for wanted in ("⬅️ السابق", "التالي ➡️", "🎲 دور عشوائي", "🟢 الإوز", "📖 كل الأدوار"):
            self.assertIn(wanted, labels)


class TestButtonEmojiSafety(unittest.TestCase):
    """إيموجي زر واحد يرفضه ديسكورد يُسقط رسالة اللوحة **كاملة**، فيتعطّل «التالي» بلا سبب ظاهر.

    هذا ما حدث فعلاً: دور «الغراب (المتحوّل)» كان بإيموجي مركّب برابط ZWJ (🐦‍⬛)، وديسكورد
    يرفض هذا الشكل داخل الأزرار (خطأ 50035)، فكانت آخر صفحة من تصفية «المحايدون» لا تُفتح أبداً.
    """

    @staticmethod
    def _emoji_name(emoji) -> str:
        return emoji if isinstance(emoji, str) else (emoji.name or "")

    def test_no_role_uses_a_zwj_emoji(self):
        for key, role in bot.ROLES.items():
            self.assertNotIn("\u200d", role["emoji"], f"الدور {key} بإيموجي مركّب يرفضه ديسكورد")

    def test_every_role_button_emoji_is_component_safe(self):
        for key in bot.ROLES:
            name = self._emoji_name(bot.RoleButton(key, row=0).emoji)
            self.assertTrue(name.strip(), key)
            self.assertNotIn("\u200d", name, key)
            self.assertLessEqual(len(name), 32, f"اسم إيموجي {key} أطول من حدّ ديسكورد")

    def test_no_page_payload_carries_a_zwj_emoji(self):
        """أقرب فحص للواقع: نُسلسل كل صفحة (وكل تصفية) كما يستلمها ديسكورد فعلاً.

        الاختبار السابق يفحص الإيموجي واحداً واحداً؛ هذا يفحص الحمولة النهائية للصفحة
        كلها، فهو يلتقط أي إيموجي مركّب يضيفه الدور الجديد تلقائياً قبل أن يصل للسيرفر.
        """
        for team in (None, *bot.TEAMS):
            for page in range(bot.total_pages(team)):
                payload = json.dumps(
                    bot.RoleBoardView(page, team).to_components(), ensure_ascii=False
                )
                self.assertNotIn("\u200d", payload, f"{team} صفحة {page}")
                self.assertNotIn('"name": ""', payload, f"{team} صفحة {page}")

    def test_zwj_sequences_are_trimmed_to_the_base_emoji(self):
        self.assertEqual(bot.safe_component_emoji("🐦‍⬛"), "🐦")
        self.assertEqual(bot.safe_component_emoji("🏳️‍🌈"), "🏳️")
        self.assertEqual(bot.safe_component_emoji("🦆"), "🦆")

    def test_broken_saved_emoji_falls_back_to_the_general_one(self):
        """خريطة قديمة أو محذوفة (أو من سيرفر آخر) لا يجب أن تُسقط اللوحة."""
        mapping = {
            "7": {
                "crow": {"id": "ليس رقماً", "name": "ggd_crow"},  # معرّف غير صالح
                "raven": {"id": "12", "name": "اسم غير صالح!"},   # اسم غير صالح
                "owl": "مدخل تالف",                                 # ليس قاموساً
            }
        }
        with mock.patch.dict(bot._emoji_map, mapping, clear=True):
            for key in ("crow", "raven", "owl"):
                self.assertIsNone(bot.custom_icon(key, 7), key)
                self.assertEqual(bot.button_emoji(key, 7), bot.ROLES[key]["emoji"], key)

    @staticmethod
    def _guild_emoji(name: str):
        emoji = mock.Mock()
        emoji.name = name
        return emoji

    def test_stale_map_entries_are_dropped_against_the_real_guild_emojis(self):
        """خريطة فيها إيموجي محذوف تُسقط الرسالة كاملة — فننظّفها عند التشغيل."""
        mapping = {
            "3": {
                "goose": {"id": "10", "name": "ggd_goose"},
                "sheriff": {"id": "11", "name": "ggd_sheriff"},  # حُذف من السيرفر
                "duck": "مدخل تالف",                              # ليس قاموساً
            }
        }
        guild = mock.Mock(id=3, emojis=[self._guild_emoji("ggd_goose")])
        with mock.patch.dict(bot._emoji_map, mapping, clear=True):
            self.assertEqual(bot.prune_missing_emojis([guild]), 2)
            self.assertEqual(sorted(bot._emoji_map["3"]), ["goose"])

    def test_pruning_is_skipped_when_the_guild_emojis_are_not_visible(self):
        """قائمة إيموجيات فارغة تعني أن البوت لا يراها — لا نخسر صور الأزرار بلا دليل."""
        mapping = {"3": {"goose": {"id": "10", "name": "ggd_goose"}}}
        guild = mock.Mock(id=3, emojis=[])
        with mock.patch.dict(bot._emoji_map, mapping, clear=True):
            self.assertEqual(bot.prune_missing_emojis([guild]), 0)
            self.assertEqual(bot._emoji_map["3"], mapping["3"])

    def test_role_card_is_retried_without_guild_emojis(self):
        """بطاقة الدور أيضاً: لو رفضها ديسكورد بسبب إيموجي قديم، نعرضها بالإيموجي العام."""

        class RejectingOnce(FakeResponse):
            def __init__(self) -> None:
                super().__init__()
                self.cards = []

            async def send_message(self, content=None, **kwargs) -> None:
                self.cards.append(kwargs.get("embed"))
                if len(self.cards) == 1:
                    raise discord.HTTPException(
                        mock.Mock(status=400, reason="Bad Request"),
                        {"code": 10014, "message": "Unknown Emoji"},
                    )
                await super().send_message(content, **kwargs)

        interaction = FakeInteraction(ephemeral=True)
        interaction.response = RejectingOnce()
        mapping = {str(interaction.guild_id): {"sheriff": {"id": "5", "name": "ggd_sheriff"}}}
        with mock.patch.dict(bot._emoji_map, mapping, clear=True):
            asyncio.run(bot.send_role_card(interaction, "sheriff"))

        self.assertEqual(len(interaction.response.cards), 2)
        self.assertIn("<:ggd_sheriff:5>", interaction.response.cards[0].title)
        self.assertNotIn("ggd_sheriff", interaction.response.cards[1].title)

    def test_an_emoji_discord_rejected_is_retried_without_guild_emojis(self):
        """لو رفض ديسكورد الرسالة بسبب إيموجي مخصص، نعيد المحاولة بالإيموجي العام."""

        class RejectingOnce(FakeResponse):
            def __init__(self) -> None:
                super().__init__()
                self.edits = 0

            async def edit_message(self, **kwargs) -> None:
                self.edits += 1
                if self.edits == 1:
                    raise discord.HTTPException(
                        mock.Mock(status=400, reason="Bad Request"),
                        {"code": 50035, "message": "Invalid Form Body"},
                    )
                await super().edit_message(**kwargs)

        interaction = FakeInteraction(ephemeral=True)
        interaction.response = RejectingOnce()
        with mock.patch.dict(bot._emoji_map, {"2": {"crow": {"id": "5", "name": "ggd_crow"}}}, clear=True):
            asyncio.run(bot.RoleBoardView(0, "neutral")._go_next(interaction))

        self.assertEqual(interaction.response.edits, 2)
        sent_view = interaction.response.edited["view"]
        self.assertIsNone(sent_view.guild_id, "المحاولة الثانية يجب ألا تستخدم إيموجيات السيرفر")
        self.assertEqual(sent_view.page, 1)


class TestKeepAlive(unittest.TestCase):
    def _get(self, path):
        """طلب GET مع مفتاح الفحص إن كان مفعّلاً في هذه البيئة."""
        headers = {"X-Health-Key": bot.HEALTH_TOKEN} if bot.HEALTH_TOKEN else {}
        return bot.flask_app.test_client().get(path, headers=headers)

    def test_port_is_always_usable(self):
        """منفذ غير صالح (مثل PORT=0) كان سيُفتح به منفذ عشوائي ويكسر فحص الصحة عند النشر."""
        self.assertGreaterEqual(bot.PORT, 1)
        self.assertLessEqual(bot.PORT, 65535)
        self.assertTrue(bot.KEEPALIVE_PATH.startswith("/"))

    def test_health_endpoint_responds(self):
        response = self._get(bot.KEEPALIVE_PATH)
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ok")
        # عدد الأدوار يظهر في الفحص، فنستطيع التأكد من النسخة المنشورة على السيرفر مباشرةً
        self.assertEqual(payload["roles"], len(bot.ROLES))
        # لا يجب أن تكشف نقطة الفحص أي معلومة حسّاسة
        self.assertNotIn("token", response.get_data(as_text=True).lower())

    def test_unknown_path_is_404(self):
        self.assertEqual(self._get("/admin").status_code, 404)

    def test_health_token_protects_endpoint(self):
        if not bot.HEALTH_TOKEN:
            self.skipTest("HEALTH_TOKEN غير مُفعّل في هذه البيئة")

        client = bot.flask_app.test_client()
        self.assertEqual(client.get(bot.KEEPALIVE_PATH).status_code, 403)
        self.assertEqual(
            client.get(bot.KEEPALIVE_PATH, headers={"X-Health-Key": bot.HEALTH_TOKEN}).status_code,
            200,
        )


class TestEnvLoading(unittest.TestCase):
    """ملف .env هو الطريقة التي تُمرّر بها التوكن محلياً — فيجب أن يعمل بأمان."""

    def setUp(self):
        self._saved = dict(os.environ)
        self.addCleanup(self._restore)

    def _restore(self):
        os.environ.clear()
        os.environ.update(self._saved)

    def _write_env(self, text, names):
        for name in names:
            os.environ.pop(name, None)
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".env", delete=False, encoding="utf-8"
        )
        handle.write(text)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_missing_file_is_harmless(self):
        self.assertEqual(bot.load_dotenv("no-such-file.env"), 0)

    def test_parses_values_quotes_comments_and_export(self):
        names = ["DISCORD_TOKEN", "GUILD_ID", "PUBLIC_URL", "SELF_PING_SECONDS", "PORT", "1BAD"]
        path = self._write_env(
            "# تعليق\n"
            "\n"
            "DISCORD_TOKEN=abc123\n"
            'GUILD_ID="123456789012345678"\n'
            "PUBLIC_URL='https://example.onrender.com'\n"
            "export SELF_PING_SECONDS=600\n"
            "PORT=8080  # تعليق في نهاية السطر\n"
            "سطر غير صالح بدون علامة يساوي\n"
            "1BAD=value\n",
            names,
        )
        self.assertEqual(bot.load_dotenv(path), 5)
        self.assertEqual(os.environ["DISCORD_TOKEN"], "abc123")
        self.assertEqual(os.environ["GUILD_ID"], "123456789012345678")
        self.assertEqual(os.environ["PUBLIC_URL"], "https://example.onrender.com")
        self.assertEqual(os.environ["SELF_PING_SECONDS"], "600")
        self.assertEqual(os.environ["PORT"], "8080")
        self.assertNotIn("1BAD", os.environ, "اسم متغيّر غير صالح يجب أن يُتجاهل")

    def test_platform_variables_always_win(self):
        """متغيّرات Render/Koyeb البيئية لا يجب أن يطغى عليها ملف .env المحلي."""
        path = self._write_env("DISCORD_TOKEN=from-file\n", ["DISCORD_TOKEN"])
        os.environ["DISCORD_TOKEN"] = "from-platform"
        self.assertEqual(bot.load_dotenv(path), 0)
        self.assertEqual(os.environ["DISCORD_TOKEN"], "from-platform")

    def test_example_file_is_loadable(self):
        example = Path(bot.__file__).resolve().parent / ".env.example"
        self.assertTrue(example.is_file())
        self.assertIsInstance(bot.load_dotenv(str(example)), int)

class TestSecurity(unittest.TestCase):
    SOURCE = Path(bot.__file__).read_text(encoding="utf-8")

    def test_no_hardcoded_discord_token(self):
        """التوكن لا يُكتب في الكود أبداً — يُقرأ من متغيّر البيئة فقط."""
        patterns = [
            r"[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27,}",  # بوت
            r"mfa\.[\w-]{80,}",  # مستخدم
        ]
        for pattern in patterns:
            self.assertIsNone(re.search(pattern, self.SOURCE), "يوجد توكن مكتوب داخل الكود!")

    def test_flask_is_not_in_debug_mode(self):
        self.assertNotIn("debug=True", self.SOURCE)
        self.assertNotIn("use_reloader=True", self.SOURCE)

    def test_no_dangerous_calls(self):
        for bad in ("eval(", "exec(", "pickle.loads", "os.system", "subprocess"):
            self.assertNotIn(bad, self.SOURCE, f"استدعاء خطير في الكود: {bad}")

    def test_token_read_from_environment(self):
        self.assertIn('env_str("DISCORD_TOKEN")', self.SOURCE)

    def test_env_file_is_gitignored(self):
        """أهم اختبار أمني: التأكد أن التوكن لا يمكن أن يُرفع إلى GitHub بالخطأ."""
        project = Path(bot.__file__).resolve().parent
        rules = (project / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn(".env", [rule.strip() for rule in rules])
        self.assertIn("!.env.example", [rule.strip() for rule in rules])


class TestPublicUrlResolution(unittest.TestCase):
    """البوت يجد رابط نفسه تلقائياً بدل أن تكتبه يدوياً (وتكتبه خطأً)."""

    KEYS = ("PUBLIC_URL", "RENDER_EXTERNAL_URL")

    def resolve(self, **values: str) -> str:
        env = {key: values.get(key, "") for key in self.KEYS}
        with mock.patch.dict(os.environ, env, clear=True):
            return bot.resolve_public_url()

    def test_explicit_public_url_wins(self):
        self.assertEqual(
            self.resolve(PUBLIC_URL="https://mine.example.com",
                        RENDER_EXTERNAL_URL="https://render-provided.onrender.com"),
            "https://mine.example.com",
        )

    def test_falls_back_to_the_variable_render_sets_itself(self):
        """Render تضبط RENDER_EXTERNAL_URL، فوُجد الرابط بلا أي إعداد يدوي."""
        self.assertEqual(
            self.resolve(RENDER_EXTERNAL_URL="https://myapp.onrender.com"),
            "https://myapp.onrender.com",
        )

    def test_missing_scheme_is_added(self):
        """أشهر خطأ في النسخ: وضع النطاق بلا https:// فيفشل القرع الذاتي."""
        self.assertEqual(self.resolve(PUBLIC_URL="myapp.onrender.com"), "https://myapp.onrender.com")

    def test_trailing_slash_is_removed(self):
        self.assertEqual(
            self.resolve(PUBLIC_URL="https://myapp.onrender.com/"), "https://myapp.onrender.com"
        )

    def test_empty_when_nothing_is_configured(self):
        self.assertEqual(self.resolve(), "")

    def test_blank_values_are_ignored(self):
        self.assertEqual(self.resolve(PUBLIC_URL="   "), "")


class TestFailVisible(unittest.TestCase):
    """عند فشل التوكن يجب أن يعرف المستخدم السبب من الرابط — لا خدمة معلّقة بلا تفسير."""

    def _get(self):
        headers = {"X-Health-Key": bot.HEALTH_TOKEN} if bot.HEALTH_TOKEN else {}
        return bot.flask_app.test_client().get(bot.KEEPALIVE_PATH, headers=headers)

    def test_missing_token_explains_itself(self):
        with mock.patch.object(bot, "TOKEN", ""):
            self.assertIn("DISCORD_TOKEN", bot.token_problem())

    def test_malformed_token_explains_itself(self):
        with mock.patch.object(bot, "TOKEN", "ضع_التوكن_هنا"):
            self.assertIn("لا تبدو توكن", bot.token_problem())

    def test_healthy_token_reports_no_problem(self):
        fake = "M" + "a" * 23 + "." + "b" * 6 + "." + "c" * 27
        with mock.patch.object(bot, "TOKEN", fake):
            self.assertEqual(bot.token_problem(), "")

    def test_health_shows_the_reason_when_the_bot_cannot_run(self):
        with mock.patch.object(bot, "BOT_PROBLEM", "التوكن غير موجود — DISCORD_TOKEN فارغ"):
            response = self._get()
            payload = response.get_json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["bot"], "offline")
        self.assertIn("التوكن غير موجود", payload["reason"])
        # نُبقي الرمز 200 حتى يتاح لصاحب البوت قراءة السبب في المتصفح
        self.assertEqual(response.status_code, 200)

    def test_hosting_platform_is_detected_but_a_local_machine_is_not(self):
        with mock.patch.dict(os.environ, {"RENDER_EXTERNAL_URL": "https://x.onrender.com"}, clear=True):
            self.assertTrue(bot.running_on_hosting_platform())
        with mock.patch.dict(os.environ, {"KOYEB_APP_NAME": "ggd"}, clear=True):
            self.assertTrue(bot.running_on_hosting_platform())
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(bot.running_on_hosting_platform())


if __name__ == "__main__":
    unittest.main(verbosity=2)
