# -*- coding: utf-8 -*-
"""
🚀 نشر البوت تلقائياً على GitHub و Render — بدون أي أوامر يدوية
==============================================================
    python deploy.py --check     # يتأكد أن المفتاحين يعملان فقط (لا يغيّر أي شيء)
    python deploy.py             # يعمل كل شيء: ينشئ المستودع + يرفع الكود + ينشر على Render

يحتاج ملفاً واحداً اسمه .deploy_secrets (انسخه من .deploy_secrets.example) فيه مفتاحان:
    GITHUB_TOKEN      مفتاح GitHub
    RENDER_API_KEY    مفتاح Render API

🔒 أمان:
  • لا يُطبع أي مفتاح أو توكن في الشاشة إطلاقاً — كل سطر يُنقّى قبل عرضه.
  • يرفض الرفع لو وجد ملفاً سرّياً متتبَّعاً في Git (فحص إجباري قبل الـ push).
  • لا يحفظ أي مفتاح في الكود، ولا يكتب أي شيء في .env.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV_PATH = HERE / ".env"
SECRETS_PATH = HERE / ".deploy_secrets"

GITHUB_API = "https://api.github.com"
RENDER_API = "https://api.render.com/v1"

REPO_NAME = "ggd-roles-bot"
SERVICE_NAME = "ggd-roles-bot"
BRANCH = "main"
BUILD_COMMAND = "pip install --no-cache-dir -r requirements.txt"
START_COMMAND = "python -u bot.py"
HEALTH_CHECK_PATH = "/healthz"
PYTHON_VERSION = "3.12.6"

VALID_REGIONS = ("frankfurt", "oregon", "ohio", "virginia", "singapore")

# هذه الملفات لو ظهرت في `git ls-files` يتوقف النشر فوراً — قبل أي رفع
NEVER_PUSH = (".env", ".deploy_secrets", ".env.bak", ".env.local", "id_rsa", "id_ed25519", ".netrc")

# أنماط الأسرار داخل محتوى الملفات (مهم جداً لأن المستودع قد يكون عاماً)
SECRET_PATTERNS = (
    ("توكن بوت ديسكورد", re.compile(r"[MN][A-Za-z\d]{23,}\.[\w-]{6,}\.[\w-]{27,}")),
    ("مفتاح GitHub", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("مفتاح GitHub دقيق", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("مفتاح Render", re.compile(r"rnd_[A-Za-z0-9]{20,}")),
    ("مفتاح خاص", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)

OK, BAD, WARN, ARROW = "✅", "❌", "⚠️ ", "→"

# كل قيمة سرّية تُسجَّل هنا حتى تُحجب من أي نص نطبعه (بما فيه أخطاء Git)
_SECRET_VALUES: list[str] = []


# ───────────────────────────── أدوات مساعدة ─────────────────────────────


def redact(text: str) -> str:
    """يحجب أي مفتاح قد يتسرّب داخل نص (رسالة خطأ، مخرجات Git... إلخ)."""
    clean = str(text)
    for secret in _SECRET_VALUES:
        if len(secret) >= 8:
            clean = clean.replace(secret, "********")
    return clean


def say(message: str = "") -> None:
    print(redact(message), flush=True)


def step(number: int, total: int, title: str) -> None:
    say()
    say(f"── الخطوة {number} من {total}: {title} " + "─" * 12)


class DeployError(Exception):
    """خطأ مفهوم بالعربي مع اقتراح حلّ."""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


def is_secret_key(key: str) -> bool:
    upper = key.upper()
    return any(word in upper for word in ("TOKEN", "KEY", "SECRET", "PASSWORD", "PASSWD"))


def load_env_file(path: Path) -> None:
    """يقرأ ملفاً بصيغة KEY=VALUE (نفس منطق bot.py). لا يستبدل متغيّراً موجوداً في البيئة."""
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
        if not all(char.isalnum() or char == "_" for char in key):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].strip()
        if is_secret_key(key) and value:
            _SECRET_VALUES.append(value)
        os.environ.setdefault(key, value)


def setting(name: str, default: str = "") -> str:
    return os.getenv(name, "").strip() or default


def http_json(
    method: str,
    url: str,
    token: str | None = None,
    body: object | None = None,
    timeout: int = 45,
    accept: str = "application/json",
) -> tuple[int, object]:
    """طلب HTTP يرجّع (كود الحالة، المحتوى) بدل أن يرمي استثناء عند 4xx/5xx."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": accept, "User-Agent": "ggd-roles-bot-deploy/1.0"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
            return response.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", "replace")
        try:
            payload: object = json.loads(raw)
        except ValueError:
            payload = raw
        return error.code, payload
    except urllib.error.URLError as error:
        raise DeployError(f"تعذّر الاتصال بالإنترنت ({error.reason})") from None


def api_message(payload: object) -> str:
    """يستخرج رسالة الخطأ من ردّ GitHub أو Render."""
    if isinstance(payload, dict):
        for key in ("message", "error", "errors"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, list) and value:
                return "; ".join(str(item) for item in value)
    if isinstance(payload, str):
        return payload.splitlines()[0][:300]
    return ""


def mask(secret: str) -> str:
    """نطبع أول حروف فقط للتأكد بصرياً أن المفتاح الصحيح مأخوذ، بلا كشفه."""
    return f"{secret[:6]}… ({len(secret)} حرفاً)" if len(secret) > 6 else "*" * len(secret)


# ───────────────────────────── GitHub ─────────────────────────────


GITHUB_ACCEPT = "application/vnd.github+json"


def credential_manager_login() -> tuple[str, str]:
    """تسجيل دخول GitHub بضغطة واحدة في المتصفح — بلا أي مفتاح ولا ملف.

    Windows فيه Git Credential Manager مثبَّتاً مع Git أصلاً، فتفتح نافذة/صفحة
    تسجيل دخول GitHub رسمية، وبعد الموافقة يرجع (اسم المستخدم، المفتاح) ونتابع الباقي.
    المفتاح يُستخدم في الذاكرة فقط ولا يُطبع ولا يُحفظ في أي ملف.
    """
    if shutil.which("git") is None:
        raise DeployError("Git غير مثبَّت على الجهاز", "نزّله من https://git-scm.com/downloads")
    say("⏳ سأفتح الآن تسجيل دخول GitHub... وافق عليه في المتصفح/النافذة التي ستظهر.")
    try:
        result = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(HERE),
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        raise DeployError(
            "انتهت مدة انتظار تسجيل الدخول (٣ دقائق)",
            "إن لم تظهر لك نافذة تسجيل الدخول أصلاً، فاستخدم مسار المفتاح اليدوي: "
            "انسخ .deploy_secrets.example باسم .deploy_secrets واملأه (الشرح في STEPS.md).",
        ) from None
    fields = {
        key: value
        for line in (result.stdout or "").splitlines()
        if "=" in line
        for key, value in [line.split("=", 1)]
    }
    username, password = fields.get("username", "").strip(), fields.get("password", "").strip()
    if not username or not password:
        raise DeployError(
            "لم يكتمل تسجيل الدخول إلى GitHub",
            "عادةً بسبب إغلاق النافذة أو عدم الموافقة. أعد المحاولة، فإن استمرّت المشكلة "
            "استخدم مسار المفتاح اليدوي (.deploy_secrets) — الشرح في STEPS.md.",
        )
    _SECRET_VALUES.append(password)
    say(f"{OK} تم تسجيل الدخول إلى GitHub — الحساب: {username}")
    return username, password


def github_whoami(token: str) -> str:
    code, payload = http_json("GET", f"{GITHUB_API}/user", token, accept=GITHUB_ACCEPT)
    if code == 200 and isinstance(payload, dict) and payload.get("login"):
        return str(payload["login"])
    if code == 401:
        raise DeployError(
            "GitHub رفض المفتاح (401)",
            "تأكد أنك نسخت GITHUB_TOKEN كاملاً وبلا مسافات، وأنه لم تنتهِ صلاحيته.",
        )
    raise DeployError(f"GitHub ردّ بكود {code}", api_message(payload))


def github_ensure_repo(token: str, login: str, private: bool) -> bool:
    """ينشئ المستودع إن لم يكن موجوداً. يرجّع True لو أنشأه الآن."""
    code, payload = http_json(
        "GET", f"{GITHUB_API}/repos/{login}/{REPO_NAME}", token, accept=GITHUB_ACCEPT
    )
    if code == 200:
        say(f"{OK} المستودع موجود مسبقاً: {login}/{REPO_NAME}")
        return False
    if code != 404:
        raise DeployError(f"تعذّر قراءة حالة المستودع (كود {code})", api_message(payload))

    body = {
        "name": REPO_NAME,
        "private": private,
        "auto_init": False,
        "description": "بوت ديسكورد: دليل تفاعلي لأدوار Goose Goose Duck بالعربية",
    }
    code, payload = http_json("POST", f"{GITHUB_API}/user/repos", token, body, accept=GITHUB_ACCEPT)
    if code in (200, 201):
        kind = "خاص" if private else "عام"
        say(f"{OK} تم إنشاء المستودع ({kind}): {login}/{REPO_NAME}")
        return True
    if code in (403, 404):
        raise DeployError(
            f"GitHub رفض إنشاء المستودع (كود {code}): {api_message(payload)}",
            "الحل الأسهل: افتح https://github.com/new وأنشئ مستودعاً فارغاً اسمه "
            f"{REPO_NAME} (بلا README) ثم أعد تشغيل الأمر مرة أخرى.",
        )
    if code == 422:
        raise DeployError(
            f"اسم المستودع مرفوض أو مستخدَم (422): {api_message(payload)}",
            f"لديك مستودع بهذا الاسم؟ فالأمر سيرفع عليه الكود مباشرة عند إعادة التشغيل.",
        )
    raise DeployError(f"تعذّر إنشاء المستودع (كود {code})", api_message(payload))


def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(HERE),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        raise DeployError(
            f"فشل أمر Git: git {' '.join(args)}",
            (result.stderr or result.stdout).strip()[:400],
        )
    return result


def scan_text_for_secrets(text: str, label: str) -> None:
    """يفحص نصّاً واحداً بحثاً عن توكنات أو مفاتيح — ويرمى خطأً لو وجد شيئاً."""
    for description, pattern in SECRET_PATTERNS:
        found = pattern.search(text)
        if found:
            raise DeployError(
                f"توقّف الرفع: عثرت على ما يشبه «{description}» داخل الملف {label}",
                "هذا يمنع تسرّب التوكن إلى GitHub. امسح الملف من المفتاح ثم أعد المحاولة "
                "(والتوكن يبقى في .env أو في إعدادات المنصّة، لا في الكود).",
            )
    # أقوى فحص: القيمة الحقيقية نفسها التي في .env أو في مفاتيح النشر
    for value in _SECRET_VALUES:
        if len(value) >= 16 and value in text:
            raise DeployError(
                f"توقّف الرفع: مفتاح حقيقي موجود نصّاً داخل الملف {label}",
                "لن أرفع ملفاً يحتوي مفتاحاً حقيقياً — لا سيما إن كان المستودع عاماً.",
            )


def scan_tracked_files_for_secrets(tracked: list[str]) -> int:
    """يفحص محتوى الملفات المرفوعة. يرجّع عدد الملفات المفحوصة."""
    checked = 0
    for path in tracked:
        file = HERE / path
        try:
            if not file.is_file() or file.stat().st_size > 2_000_000:
                continue
            text = file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        scan_text_for_secrets(text, path)
        checked += 1
    return checked


def assert_no_secrets_tracked() -> None:
    """حاجز أمان مزدوج: لا ملفات سرّية متتبَّعة، ولا أسرار داخل محتوى الملفات."""
    tracked = [line.strip() for line in run_git("ls-files").stdout.splitlines() if line.strip()]
    exposed = [path for path in tracked if Path(path).name in NEVER_PUSH]
    if exposed:
        raise DeployError(
            "توقّف الرفع: هذه الملفات السرّية متتبَّعة في Git → " + ", ".join(exposed),
            "شغّل:  git rm --cached " + " ".join(exposed) + "   ثم أعد تشغيل النشر.",
        )
    checked = scan_tracked_files_for_secrets(tracked)
    say(
        f"{OK} فحص الأمان: {len(tracked)} ملفاً مرفوعاً، لا ملف سرّي بينها، "
        f"ولا مفتاح مخبّأ داخل {checked} ملفاً نصّياً"
    )


def git_commit_pending() -> None:
    run_git("add", "-A")
    staged = run_git("status", "--porcelain").stdout.strip()
    if not staged:
        say(f"{OK} لا يوجد تغييرات جديدة — الكود محفوظ مسبقاً")
        return
    run_git(
        "-c", "user.name=Buffy",
        "-c", "user.email=buffy@users.noreply.github.com",
        "commit", "-m", "تحديث ملفات البوت قبل النشر",
    )
    say(f"{OK} تم حفظ التغييرات الجديدة في Git")


def git_push(token: str, login: str) -> None:
    if shutil.which("git") is None:
        raise DeployError(
            "Git غير مثبَّت على الجهاز",
            "نزّله من https://git-scm.com/downloads ثم أعد التشغيل (بدون إعادة تشغيل الكمبيوتر غالباً).",
        )
    if not (HERE / ".git").is_dir():
        run_git("init", "-b", BRANCH)
    assert_no_secrets_tracked()
    git_commit_pending()

    clean_url = f"https://github.com/{login}/{REPO_NAME}.git"
    run_git("remote", "remove", "origin", check=False)
    run_git("remote", "add", "origin", clean_url)

    # الرفع برابط مؤقت يحمل المفتاح، فلا يُحفظ المفتاح داخل إعدادات المستودع
    push_url = f"https://x-access-token:{token}@github.com/{login}/{REPO_NAME}.git"
    result = run_git(
        "-c", "credential.helper=",
        "-c", "core.askPass=",
        "push", push_url, f"HEAD:refs/heads/{BRANCH}",
        check=False,
    )
    if result.returncode != 0:
        output = redact((result.stderr or "") + (result.stdout or ""))
        if "rejected" in output or "non-fast-forward" in output:
            raise DeployError(
                "الرفع مرفوض لأن المستودع على GitHub يحتوي تعديلات أحدث من جهازك",
                "افتح المستودع على GitHub وتحقق من محتواه، أو ارفع يدوياً مرة واحدة ثم أعد المحاولة.",
            )
        raise DeployError("فشل رفع الكود إلى GitHub", output.strip()[:400])
    say(f"{OK} تم رفع الكود إلى {clean_url} (الفرع {BRANCH})")


# ───────────────────────────── Render ─────────────────────────────


def one_click_render_url(repo_url: str) -> str:
    """رابط «Deploy to Render» الرسمي: يفتح Render على إعدادات المستودع مباشرةً."""
    return f"https://render.com/deploy?repo={repo_url}"


def render_pick_workspace(api_key: str, wanted: str) -> dict:
    code, payload = http_json("GET", f"{RENDER_API}/owners?limit=20", api_key)
    if code == 401:
        raise DeployError(
            "Render رفض المفتاح (401)",
            "أنشئ مفتاحاً جديداً من https://dashboard.render.com/u/settings#api-keys "
            "وانسخه كاملاً في RENDER_API_KEY.",
        )
    if code != 200 or not isinstance(payload, list) or not payload:
        raise DeployError(f"تعذّر قراءة مساحات العمل في Render (كود {code})", api_message(payload))

    owners = [item.get("owner", {}) for item in payload if isinstance(item, dict)]
    if wanted:
        for owner in owners:
            if owner.get("id") == wanted:
                return owner
        raise DeployError(
            f"لم أجد مساحة العمل {wanted} في حسابك",
            "المساحات المتاحة: " + ", ".join(f"{o.get('name')} ({o.get('id')})" for o in owners),
        )
    return owners[0]


def build_env_vars(public_url: str) -> list[dict[str, str]]:
    """متغيّرات البيئة التي سيرسلها Render إلى البوت (نفس قيم .env المحلّي)."""
    discord_token = setting("DISCORD_TOKEN")
    if not discord_token:
        raise DeployError(
            "لا يوجد DISCORD_TOKEN في ملف .env",
            "الصق توكن البوت في .env ثم أعد التشغيل.",
        )

    variables: dict[str, str] = {
        "DISCORD_TOKEN": discord_token,
        "PYTHON_VERSION": setting("PYTHON_VERSION", PYTHON_VERSION),
        "ENABLE_PREFIX_COMMANDS": setting("ENABLE_PREFIX_COMMANDS", "false"),
        "SELF_PING_SECONDS": setting("SELF_PING_SECONDS", "600"),
        "ACTION_COOLDOWN_SECONDS": setting("ACTION_COOLDOWN_SECONDS", "1"),
    }
    guild_id = setting("GUILD_ID")
    if guild_id:
        variables["GUILD_ID"] = guild_id
    # القفل الأمني: يستخدم ALLOWED_GUILD_IDS إن وُجد، وإلا يرث GUILD_ID حتى لا يبقى البوت مفتوحاً
    allowed = setting("ALLOWED_GUILD_IDS") or guild_id
    if allowed:
        variables["ALLOWED_GUILD_IDS"] = allowed
    health_token = setting("HEALTH_TOKEN")
    if health_token:
        variables["HEALTH_TOKEN"] = health_token
    if public_url:
        variables["PUBLIC_URL"] = public_url

    return [{"key": key, "value": value} for key, value in variables.items()]


def render_find_service(api_key: str) -> dict | None:
    code, payload = http_json(
        "GET", f"{RENDER_API}/services?name={SERVICE_NAME}&limit=20", api_key
    )
    if code != 200:
        raise DeployError(f"تعذّر قراءة خدمات Render (كود {code})", api_message(payload))
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and item.get("service"):
                return item["service"]
    return None


def render_create_service(
    api_key: str,
    owner_id: str,
    repo_url: str,
    env_vars: list[dict[str, str]],
    region: str,
    auto_deploy: bool,
) -> dict:
    body = {
        "type": "web_service",
        "name": SERVICE_NAME,
        "ownerId": owner_id,
        "repo": repo_url,
        "branch": BRANCH,
        "autoDeploy": "yes" if auto_deploy else "no",
        "serviceDetails": {
            "runtime": "python",
            "plan": "free",
            "region": region,
            "healthCheckPath": HEALTH_CHECK_PATH,
            "envSpecificDetails": {
                "buildCommand": BUILD_COMMAND,
                "startCommand": START_COMMAND,
            },
        },
        "envVars": env_vars,
    }
    code, payload = http_json("POST", f"{RENDER_API}/services", api_key, body)
    if code in (200, 201) and isinstance(payload, dict) and payload.get("service"):
        return payload["service"]
    if code == 402:
        raise DeployError(
            "Render رفض الخطة المجانية (402)",
            "تأكد أن حسابك على Render مفعّل (أحياناً يطلب بطاقة للتحقق فقط دون خصم).",
        )
    if code == 409:
        raise DeployError(
            f"يوجد تعارض في الأسماء داخل Render (409): {api_message(payload)}",
            f"احذف أي خدمة باسم {SERVICE_NAME} من لوحة Render ثم أعد التشغيل.",
        )
    raise DeployError(
        f"تعذّر إنشاء الخدمة على Render (كود {code}): {api_message(payload)}",
        "إن كان المستودع خاصاً (private) فلازم تسمح لـ Render بالوصول إليه أولاً: "
        "https://dashboard.render.com → New + → Web Service → اربط GitHub مرة واحدة، ثم أعد التشغيل.",
    )


def render_set_env_vars(api_key: str, service_id: str, env_vars: list[dict[str, str]]) -> None:
    code, payload = http_json(
        "PUT", f"{RENDER_API}/services/{service_id}/env-vars", api_key, env_vars
    )
    if code not in (200, 201):
        raise DeployError(
            f"تعذّر ضبط متغيّرات البيئة على Render (كود {code})", api_message(payload)
        )


def render_service_url(api_key: str, service: dict) -> str:
    details = service.get("serviceDetails") or {}
    url = str(details.get("url") or "").strip()
    if url:
        return url
    code, payload = http_json("GET", f"{RENDER_API}/services/{service.get('id')}", api_key)
    if code == 200 and isinstance(payload, dict):
        return str((payload.get("serviceDetails") or {}).get("url") or "").strip()
    slug = str(service.get("slug") or SERVICE_NAME)
    return f"https://{slug}.onrender.com"


def render_wait_until_live(api_key: str, service_id: str, timeout: int = 420) -> None:
    """ينتظر انتهاء أول عملية نشر. الفشل لا يوقف النشر — يطبع الحالة فقط."""
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        code, payload = http_json(
            "GET", f"{RENDER_API}/services/{service_id}/deploys?limit=1", api_key
        )
        status = ""
        if code == 200 and isinstance(payload, list) and payload:
            latest = payload[0]
            if isinstance(latest, dict):
                status = str((latest.get("deploy") or {}).get("status") or "")
        if status and status != last:
            say(f"   {ARROW} حالة النشر: {status}")
            last = status
        if status == "live":
            say(f"{OK} الخدمة تعمل الآن على Render")
            return
        if status and ("failed" in status or "canceled" in status or "cancelled" in status):
            say(f"{WARN}النشر لم ينجح (الحالة: {status}) — راجع السجلات في لوحة Render")
            return
        time.sleep(10)
    say(f"{WARN}لم ينتهِ النشر خلال {timeout // 60} دقائق — تابعه من لوحة Render")


# ───────────────────────────── البرنامج الرئيسي ─────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="نشر بوت Goose Goose Duck على GitHub و Render بأمر واحد",
    )
    parser.add_argument("--check", action="store_true", help="فحص المفتاحين فقط دون أي تغيير")
    parser.add_argument("--github-only", action="store_true", help="ارفع الكود فقط بلا Render")
    parser.add_argument("--render-only", action="store_true", help="أنشئ خدمة Render فقط")
    parser.add_argument(
        "--git-login",
        action="store_true",
        help="سجّل الدخول إلى GitHub بضغطة في المتصفح بدل أي مفتاح (بلا ملف .deploy_secrets)",
    )
    parser.add_argument("--public", action="store_true", help="اجعل المستودع عاماً")
    parser.add_argument("--private", action="store_true", help="اجعل المستودع خاصاً")
    parser.add_argument("--no-wait", action="store_true", help="لا تنتظر انتهاء البناء")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    say()
    say("=" * 62)
    say("  🚀 نشر بوت أدوار Goose Goose Duck تلقائياً")
    say("=" * 62)

    load_env_file(ENV_PATH)
    load_env_file(SECRETS_PATH)

    github_token = setting("GITHUB_TOKEN")
    render_key = setting("RENDER_API_KEY")
    discord_token = setting("DISCORD_TOKEN")

    missing: list[str] = []
    if not github_token and not args.git_login:
        missing.append("GITHUB_TOKEN (مفتاح GitHub) أو خيار --git-login")
    if not render_key and not args.github_only and not args.git_login:
        missing.append("RENDER_API_KEY (مفتاح Render)")
    if missing:
        say()
        say(f"{BAD} ينقصني: " + " و ".join(missing))
        say()
        say("أسرع طريق بلا أي مفتاح:")
        say("    python deploy.py --git-login     ← يفتح تسجيل دخول GitHub في المتصفح بضغطة،")
        say("                                        ثم يرفع الكود ويعطيك رابط نشر Render بنقرة أيضاً.")
        say()
        say("أو الطريق الكامل: انسخ  .deploy_secrets.example  باسم  .deploy_secrets")
        say("واملأ فيه المفتاحين — الشرح خطوة بخطوة في STEPS.md قسم «⚡ الطريق السريع».")
        return 1

    # التوكن مطلوب فقط عندما نضبط إعدادات Render بأنفسنا؛
    # أما في المسار التفاعلي (--git-login) فأنت تكتبه في لوحة Render مباشرةً.
    if not discord_token and not (args.github_only or args.git_login):
        say(f"{BAD} ملف .env لا يحتوي DISCORD_TOKEN — أضفه أولاً (هو توكن البوت نفسه).")
        return 1

    say()
    if discord_token:
        say(f"{OK} DISCORD_TOKEN مقروء من .env ({mask(discord_token)})")
    if github_token:
        say(f"{OK} GITHUB_TOKEN مقروء ({mask(github_token)})")
    if render_key:
        say(f"{OK} RENDER_API_KEY مقروء ({mask(render_key)})")

    try:
        # 1) تسجيل الدخول / التحقق من المفاتيح
        step(1, 3, "تسجيل الدخول والتحقق")
        login = ""
        if args.git_login:
            login, github_token = credential_manager_login()
        else:
            login = github_whoami(github_token)
            say(f"{OK} GitHub يعمل — الحساب: {login}")
        owner: dict = {}
        if render_key:
            owner = render_pick_workspace(render_key, setting("RENDER_OWNER_ID"))
            say(f"{OK} Render يعمل — مساحة العمل: {owner.get('name')} ({owner.get('id')})")

        if args.check:
            say()
            say(f"{OK} المفاتيح سليمة. لا شيء تغيّر — احذف --check للتشغيل الفعلي.")
            return 0

        # 2) GitHub
        if args.public:
            private = False
        elif args.private:
            private = True
        else:
            private = setting("REPO_VISIBILITY", "private").lower() != "public"

        repo_url = f"https://github.com/{login}/{REPO_NAME}"

        if not args.render_only:
            step(2, 3, "إنشاء المستودع ورفع الكود")
            github_ensure_repo(github_token, login, private)
            git_push(github_token, login)
        else:
            step(2, 3, "تخطّي GitHub (بطلب منك)")
            repo_url = setting("REPO_URL", repo_url)

        if args.github_only or args.git_login:
            say()
            say(f"{OK} تم رفع الكود: {repo_url}")
            say()
            say("   الخطوة الأخيرة (نقرة واحدة): افتح هذا الرابط للنشر على Render")
            say(f"   {one_click_render_url(repo_url)}")
            say("   ستراه يقرأ render.yaml ويطلب منك حقلاً واحداً فقط: DISCORD_TOKEN")
            return 0

        # 3) Render
        step(3, 3, "إنشاء الخدمة على Render")
        region = setting("RENDER_REGION", "frankfurt")
        if region not in VALID_REGIONS:
            say(f"{WARN}منطقة غير معروفة ({region}) — سأستخدم frankfurt")
            region = "frankfurt"

        predicted_url = f"https://{SERVICE_NAME}.onrender.com"
        existing = render_find_service(render_key)
        if existing:
            service = existing
            say(f"{OK} الخدمة موجودة مسبقاً على Render — سأحدّث متغيّرات البيئة فقط")
            render_set_env_vars(render_key, str(service.get("id")), build_env_vars(predicted_url))
        else:
            service = render_create_service(
                render_key, str(owner.get("id")), repo_url, build_env_vars(predicted_url),
                region, auto_deploy=private,
            )
            say(f"{OK} تم إنشاء الخدمة (خطة مجانية، منطقة {region})")

        service_id = str(service.get("id"))
        service_url = render_service_url(render_key, service) or predicted_url

        # رابط الخدمة الحقيقي قد يختلف عن المتوقّع (لو كان الاسم محجوزاً) → نصحّحه
        if service_url != predicted_url:
            say(f"   {ARROW} الرابط الفعلي مختلف عن المتوقّع — أضبط PUBLIC_URL عليه")
            render_set_env_vars(render_key, service_id, build_env_vars(service_url))

        if not args.no_wait:
            say("⏳ أنتظر انتهاء أول عملية بناء (٢–٤ دقائق عادةً)...")
            render_wait_until_live(render_key, service_id)

        say()
        say("=" * 62)
        say(f"{OK} تم النشر بنجاح")
        say("=" * 62)
        say(f"   رابط التطبيق   : {service_url}")
        say(f"   فحص الصحة      : {service_url}{HEALTH_CHECK_PATH}")
        say(f"   لوحة التحكم    : {service.get('dashboardUrl', 'https://dashboard.render.com')}")
        say(f"   الكود على GitHub: {repo_url}")
        say(f"   إعادة النشر    : {one_click_render_url(repo_url)}")
        say()
        say("   الآن افتح ديسكورد واكتب في أي روم:  /roles")
        say()
        return 0

    except DeployError as error:
        say()
        say(f"{BAD} {error.message}")
        if error.hint:
            say(f"   {ARROW} {error.hint}")
        return 1
    except KeyboardInterrupt:
        say()
        say(f"{WARN}توقّفت بأمر منك. لا شيء تلف — أعد التشغيل لإكمال ما بقي.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
