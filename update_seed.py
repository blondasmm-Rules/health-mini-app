"""
Утренний скрипт: обновляет данные в HTML дашборде (const Y = {...})
данными из Garmin Connect и FatSecret, потом загружает на GitHub Pages.

Запуск: source ~/venv/bin/activate && python3 ~/update_seed.py
Cron (6 утра по Bangkok UTC+7 = 23:00 UTC):
  0 23 * * * /home/assistant/venv/bin/python3 /home/assistant/update_seed.py >> /home/assistant/update_seed.log 2>&1
"""
import base64, json, os, re, sys
from datetime import date, timedelta
import urllib.request

def _load_env(path):
    vals = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    vals[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return vals

_cfg = _load_env(os.path.expanduser("~/update_seed.env"))
GITHUB_TOKEN = _cfg.get("GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO  = "blondasmm-Rules/health-mini-app"
GITHUB_FILE  = "index.html"
GITHUB_API   = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"

sys.path.insert(0, os.path.expanduser("~"))


def get_garmin_yesterday():
    from garmin_client import get_garmin_data
    yesterday = date.today() - timedelta(days=1)
    return get_garmin_data(yesterday)


def get_garmin_sleep_today():
    from garmin_client import get_garmin_data
    return get_garmin_data(date.today())


def get_fatsecret_yesterday():
    from fatsecret_client import get_diary
    yesterday = date.today() - timedelta(days=1)
    result = get_diary(yesterday)
    totals = result.get("totals", {})
    return {
        "kcal":    round(totals.get("calories", 0)),
        "protein": round(totals.get("protein", 0)),
        "fat":     round(totals.get("fat", 0)),
        "carbs":   round(totals.get("carbohydrate", 0)),
    }


def github_get_file():
    req = urllib.request.Request(
        GITHUB_API,
        headers={"Authorization": f"token {GITHUB_TOKEN}", "User-Agent": "update-seed"}
    )
    with urllib.request.urlopen(req) as r:
        d = json.loads(r.read())
    content = base64.b64decode(d["content"]).decode("utf-8")
    sha = d["sha"]
    return content, sha


def github_put_file(content: str, sha: str, message: str):
    payload = json.dumps({
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode(),
        "sha": sha,
    }).encode()
    req = urllib.request.Request(
        GITHUB_API,
        data=payload,
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "update-seed",
        },
        method="PUT",
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def update_html(html: str, Y: dict) -> str:
    new_y = (
        f"const Y = {{ kcal:{Y['kcal']}, protein:{Y['protein']}, "
        f"fat:{Y['fat']}, carbs:{Y['carbs']}, steps:{Y['steps']}, "
        f"sleep:{Y['sleep']}, sleepScore:{Y['sleepScore']}, "
        f"stress:{Y['stress']}, restingHr:{Y['restingHr']}, weight:{Y['weight']} }};"
    )
    # Заменяем строку с const Y
    updated = re.sub(r"const Y\s*=\s*\{[^}]+\};", new_y, html)
    if updated == html:
        raise ValueError("Не нашёл const Y = {...} в HTML — паттерн не совпал")
    return updated


def main():
    today_str = date.today().isoformat()
    print(f"=== update_seed.py запущен {today_str} ===")

    print("Загружаю данные Garmin за вчера...")
    g_yesterday = get_garmin_yesterday()
    print("  шаги:", g_yesterday.get("steps"), "| стресс:", g_yesterday.get("avg_stress"), "| ЧСС:", g_yesterday.get("resting_hr"))

    print("Загружаю сон из Garmin за сегодня...")
    g_today = get_garmin_sleep_today()
    sleep_h = g_today.get("sleep_hours") or g_yesterday.get("sleep_hours") or 0
    sleep_score = g_today.get("sleep_score") or g_yesterday.get("sleep_score") or 0
    print("  сон:", sleep_h, "ч | score:", sleep_score)

    print("Загружаю КБЖУ из FatSecret за вчера...")
    fs = get_fatsecret_yesterday()
    print("  ккал:", fs["kcal"], "Б:", fs["protein"], "Ж:", fs["fat"], "У:", fs["carbs"])

    Y = {
        "kcal":       fs["kcal"],
        "protein":    fs["protein"],
        "fat":        fs["fat"],
        "carbs":      fs["carbs"],
        "steps":      g_yesterday.get("steps") or 0,
        "sleep":      round(sleep_h, 2),
        "sleepScore": sleep_score or 0,
        "stress":     g_yesterday.get("avg_stress") or 0,
        "restingHr":  g_yesterday.get("resting_hr") or 0,
        "weight":     62.5,  # TODO: добавить ручной ввод веса
    }
    print("Y =", Y)

    print("Скачиваю HTML с GitHub...")
    html, sha = github_get_file()

    print("Обновляю const Y...")
    new_html = update_html(html, Y)

    print("Загружаю на GitHub...")
    result = github_put_file(new_html, sha, f"Auto-update SEED {today_str}")
    print("✅ Готово:", result.get("content", {}).get("html_url", "OK"))


if __name__ == "__main__":
    main()
