import time
import base64
from pathlib import Path
import requests
import os

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# ----------------- КОНСТАНТЫ -----------------
URL = "https://poisondrop.com/"

ARTIFACTS_DIR = Path("artifacts")
ARTIFACTS_DIR.mkdir(exist_ok=True)
LOG_FILE = ARTIFACTS_DIR / "registration_log.txt"
MAX_ARTIFACT_FILES = 20

# CoreCluster
API_KEY = "623d4ead-74db-40d5-9716-e65a3f1ce6de"
SERVICE = "pod"      # PoisonDrop
COUNTRY = "43"       # Germany

# RuCaptcha
RUCAPTCHA_KEY = "cfaa520473f8a93cf94f69d0aec557c6"
RUCAPTCHA_IN = "http://rucaptcha.com/in.php"
RUCAPTCHA_RES = "http://rucaptcha.com/res.php"

# HTTP-прокси из задания
PROXY_HOST = "res-unlimited-9b50b01a.plainproxies.com"
PROXY_PORT = 8080
PROXY_USER = "Svt3H4Bnl7-country-DE-session-fxuoGqSWAj-lifetime-8"
PROXY_PASS = "jX6TD77KVzfrQ0O"
PROXY_URL = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"
PROXIES = {"http": PROXY_URL, "https": PROXY_URL}

MAX_PHONE_CYCLES = 100


# ----------------- ВСПОМОГАТЕЛЬНЫЕ -----------------

def cleanup_artifacts():
    files = sorted(
        ARTIFACTS_DIR.glob("*.*"),
        key=lambda p: p.stat().st_mtime,
    )
    if len(files) <= MAX_ARTIFACT_FILES:
        return
    # удаляем самые старые
    to_delete = files[0 : len(files) - MAX_ARTIFACT_FILES]
    for f in to_delete:
        try:
            f.unlink()
        except Exception as e:
            print(f"Не смог удалить {f}: {e}")

def log_result(number_id, phone, success, comment=""):
    """Записывает результат попытки в лог-файл"""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    status = "УСПЕХ" if success else "НЕУДАЧА"
    line = f"[{ts}] ID: {number_id} | Телефон: {phone} | Результат: {status}"
    if comment:
        line += f" | Комментарий: {comment}"
    line += "\n"
    
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)
    print(f"Записано в лог: {status} — {phone}")

def save_debug(driver, tag="debug"):
    ts = time.strftime("%Y%m%d_%H%M%S")
    png = ARTIFACTS_DIR / f"{tag}_{ts}.png"
    html = ARTIFACTS_DIR / f"{tag}_{ts}.html"
    driver.save_screenshot(str(png))
    html.write_text(driver.page_source, encoding="utf-8")
    print(f"🧷 Debug saved: {png} and {html}")


def js_click(driver, el):
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    driver.execute_script("arguments[0].click();", el)


def try_click_cookie(driver, wait):
    candidates = [
        (By.XPATH, "//button[contains(.,'Принять') or contains(.,'Соглас') or contains(.,'Accept')]"),
        (By.CSS_SELECTOR, "button#onetrust-accept-btn-handler"),
        (By.CSS_SELECTOR, "button[aria-label*='accept' i]"),
    ]
    for by, sel in candidates:
        try:
            btn = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((by, sel)))
            js_click(driver, btn)
            time.sleep(0.3)
            print("✅ Cookie banner accepted")
            return
        except Exception:
            pass


def create_proxy_auth_extension():
    manifest_json = """
    {
        "name": "Proxy Auth",
        "version": "1.0.0",
        "manifest_version": 3,
        "permissions": ["proxy", "webRequest", "webRequestAuthProvider", "storage"],
        "host_permissions": ["<all_urls>"],
        "background": {"service_worker": "background.js"}
    }
    """

    background_js = f"""
    chrome.proxy.settings.set({{
        value: {{ mode: "fixed_servers", rules: {{ singleProxy: {{ scheme: "http", host: "{PROXY_HOST}", port: {PROXY_PORT} }} }} }},
        scope: "regular"
    }});

    chrome.webRequest.onAuthRequired.addListener(
        () => {{ return {{ authCredentials: {{ username: "{PROXY_USER}", password: "{PROXY_PASS}" }} }}; }},
        {{ urls: ["<all_urls>"] }},
        ["blocking"]
    );
    """

    ext_dir = ARTIFACTS_DIR / "proxy_ext_v3"
    ext_dir.mkdir(exist_ok=True)
    (ext_dir / "manifest.json").write_text(manifest_json.strip(), encoding="utf-8")
    (ext_dir / "background.js").write_text(background_js, encoding="utf-8")
    return str(ext_dir)


def solve_and_submit_captcha(driver, wait):
    captcha_base64 = ""
    for inner_attempt in range(6):
        try:
            img = WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".captcha__img img"))
            )
            src = img.get_attribute("src") or ""
            if src.startswith("data:image/"):
                captcha_base64 = src.split(",", 1)[1]
                img_bytes = base64.b64decode(captcha_base64)
                bytes_len = len(img_bytes)
                print(f"  ↳ Внутренняя попытка {inner_attempt + 1}: {bytes_len} байт")

                debug_path = ARTIFACTS_DIR / f"captcha_inner_{inner_attempt + 1}.jpg"
                debug_path.write_bytes(img_bytes)

                if bytes_len > 500:
                    print("  ✅ Получили хорошую картинку капчи")
                    break
        except Exception as e:
            print(f"  Ошибка получения картинки: {e}")

        if inner_attempt < 5:
            try:
                update_btn = driver.find_element(
                    By.XPATH,
                    "//a[contains(., 'update captcha') or contains(@class, 'captcha__refresh')]"
                )
                js_click(driver, update_btn)
                print("  🔄 Обновляем капчу...")
                time.sleep(2)
            except Exception:
                time.sleep(2)

    if len(captcha_base64) <= 200:
        print("  ❌ Не удалось получить нормальную капчу")
        return False

    img_bytes = base64.b64decode(captcha_base64)

    files = {"file": ("captcha.jpg", img_bytes, "image/jpeg")}
    data = {"key": RUCAPTCHA_KEY, "json": 1}

    try:
        resp = requests.post(RUCAPTCHA_IN, data=data, files=files, proxies=PROXIES, timeout=30).json()
    except Exception as e:
        print(f"  ❌ Сеть до RuCaptcha: {e}")
        return False

    if resp.get("status") != 1:
        print(f"  ❌ Ошибка отправки на RuCaptcha: {resp}")
        return False

    task_id = resp["request"]
    print(f"  📤 Капча отправлена, ID: {task_id}")

    captcha_text = None
    for _ in range(60):
        time.sleep(4)
        try:
            res = requests.get(
                RUCAPTCHA_RES,
                params={"key": RUCAPTCHA_KEY, "action": "get", "id": task_id, "json": 1},
                proxies=PROXIES,
                timeout=30,
            ).json()
        except Exception as e:
            print(f"  Ошибка запроса результата RuCaptcha: {e}")
            return False

        if res.get("status") == 1:
            captcha_text = res["request"].upper().strip()
            print(f"  ✅ RuCaptcha вернул: {captcha_text}")
            break
        elif res.get("request") == "CAPCHA_NOT_READY":
            continue
        else:
            print(f"  Промежуточный ответ RuCaptcha: {res}")
            break

    if not captcha_text:
        print("  ❌ Таймаут решения капчи")
        return False

    try:
        captcha_input = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//div[contains(@class,'captcha')]//input[@type='text']")
            )
        )
        captcha_input.clear()
        captcha_input.send_keys(captcha_text)
        time.sleep(0.5)

        continue_btn = wait.until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue')]",
                )
            )
        )
        js_click(driver, continue_btn)
        print("  📨 Ввели код и нажали continue")
    except Exception as e:
        print(f"  ❌ Ошибка ввода/клика: {e}")
        return False

    return True


def get_corecluster_number():
    url = "https://app.corecluster.pro/stubs/handler_api.php"
    params = {
        "api_key": API_KEY,
        "action": "getNumber",
        "service": SERVICE,
        "country": COUNTRY,
    }
    try:
        resp = requests.get(url, params=params, proxies=PROXIES, timeout=20)
        text = resp.text.strip()
        print(f"Ответ от CoreCluster: {text}")
        if text.startswith("ACCESS_NUMBER:"):
            parts = text.split(":")
            return parts[1], parts[2]
        else:
            print(f"❌ Не удалось взять номер: {text}")
            return None, None
    except Exception as e:
        print(f"❌ Сетевая ошибка CoreCluster getNumber: {e}")
        return None, None


def set_corecluster_status(number_id, status):
    url = "https://app.corecluster.pro/stubs/handler_api.php"
    params = {
        "api_key": API_KEY,
        "action": "setStatus",
        "id": number_id,
        "status": str(status),
    }
    try:
        resp = requests.get(url, params=params, proxies=PROXIES, timeout=10)
        print(f"setStatus({status}) → {resp.text.strip()}")
    except Exception as e:
        print(f"Ошибка setStatus: {e}")


def wait_sms_code(number_id, max_minutes=2):
    sms_code = None
    attempts = int(max_minutes * 60 / 6)
    print(f"Ждём SMS до {max_minutes} минут...")

    url = "https://app.corecluster.pro/stubs/handler_api.php"

    for attempt in range(1, attempts + 1):
        time.sleep(6)
        try:
            resp = requests.get(
                url,
                params={"api_key": API_KEY, "action": "getStatus", "id": number_id},
                proxies=PROXIES,
                timeout=20,
            )
            status_text = resp.text.strip()
            print(f"  Попытка {attempt}: {status_text}")

            if status_text.startswith("STATUS_OK:"):
                sms_code = status_text.split(":", 1)[1]
                print(f"✅ SMS-код от CoreCluster: {sms_code}")
                break
            elif status_text in ("STATUS_WAIT", "STATUS_WAIT_CODE"):
                continue
            elif status_text in ("STATUS_CANCEL", "NO_NUMBERS"):
                print(f"❌ Проблема с номером: {status_text}")
                break
            else:
                print("Неизвестный статус — продолжаем ждать")

        except Exception as e:
            print(f"Ошибка запроса статуса: {e}")

    return sms_code


# ----------------- ОСНОВНОЙ ЦИКЛ -----------------
def run_cycle():
    cleanup_artifacts()
    options = webdriver.ChromeOptions()
    proxy_ext_path = create_proxy_auth_extension()
    options.add_argument(f"--load-extension={proxy_ext_path}")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 25)

    success = False
    number_id = None
    phone_for_site = None
    fail_reason = "Неизвестная ошибка"

    try:
        # 0. Номер из CoreCluster
        number_id, phone_for_site = get_corecluster_number()
        if not number_id:
            fail_reason = "Не удалось получить номер от CoreCluster"  # ← ИЗМЕНИТЬ
            log_result(number_id, phone_for_site, False, fail_reason)  # ← ДОБАВИТЬ
            return False


        # 1. Открываем сайт
        driver.get(URL)
        wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
        time.sleep(1.0)
        try_click_cookie(driver, wait)

        # 2. Кликаем по профилю
        profile_selectors = [
            (By.CSS_SELECTOR, "button[aria-label*='profile' i], button[aria-label*='account' i]"),
            (By.XPATH, "//span[contains(@class,'header-top__icon-button')][.//*[name()='use' and @href='#icon-profile']]"),
            (By.XPATH, "//*[contains(@class,'header')]//*[contains(@class,'profile') or contains(@class,'account') or contains(@class,'user')]"),
            (By.XPATH, "//a[contains(@href,'login') or contains(@href,'auth') or contains(@href,'account')]"),
        ]

        clicked = False
        last_err = None
        for by, sel in profile_selectors:
            try:
                el = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((by, sel)))
                js_click(driver, el)
                time.sleep(1.0)
                clicked = True
                print(f"✅ Кликнули профиль по селектору: {sel}")
                break
            except Exception as e:
                last_err = e
                print(f"Не сработал селектор {sel}: {e}")

        if not clicked:
            save_debug(driver, "no_profile_icon")
            raise RuntimeError(f"Не нашли/не кликнули иконку профиля. Последняя ошибка: {last_err}")

        # 3. Поле телефона (номер из CoreCluster)
        input_selectors = [
            (By.CSS_SELECTOR, "input#authLogin"),
            (By.CSS_SELECTOR, "input[name='phone']"),
            (By.CSS_SELECTOR, "div.vue-tel-input input.vti__input"),
            (By.XPATH, "//input[@type='tel' and (contains(@class,'vti__input') or @name='phone')]"),
        ]

        phone_input = None
        for by, sel in input_selectors:
            try:
                phone_input = wait.until(EC.presence_of_element_located((by, sel)))
                break
            except Exception:
                pass

        if not phone_input:
            save_debug(driver, "no_phone_input")
            raise TimeoutException("Не нашёл поле телефона")

        # Исправляем формат номера: добавляем + если его нет
        if phone_for_site and not phone_for_site.startswith("+"):
            phone_for_site = "+" + phone_for_site

        print(f"📱 Ввели номер (с +): {phone_for_site}")

        # Вводим номер (clear() + паузы для валидации)
        phone_input.click()
        time.sleep(0.5)            # чуть больше паузы
        try:
            phone_input.clear()    # лучше clear(), чем Ctrl+A + Backspace
        except Exception:
            # fallback, если clear() не работает на кастомном инпуте
            phone_input.send_keys(Keys.CONTROL, "a")
            phone_input.send_keys(Keys.BACKSPACE)

        time.sleep(0.2)
        phone_input.send_keys(phone_for_site)

        time.sleep(1.0) 

        # 4. Согласие
        try:
            agree = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'label[for="agreementPrivacyLoyalty"]'))
            )
            js_click(driver, agree)
            time.sleep(0.3)
        except Exception as e:
            print(f"❌ Не удалось кликнуть согласие: {e}")
            save_debug(driver, "no_agree_checkbox")
            raise

        # 5. Кнопка "получить код"

        btn_selectors = [
            (By.CSS_SELECTOR, "button.login-or-register__button"),
            (By.XPATH, "//button[contains(., 'Получить') or contains(., 'Get code') or contains(., 'Отправить')]"),
        ]

        get_code_btn = None
        for by, sel in btn_selectors:
            try:
                get_code_btn = wait.until(EC.presence_of_element_located((by, sel)))
                break
            except Exception:
                pass

        if not get_code_btn:
            save_debug(driver, "no_get_code_btn")
            raise TimeoutException("Кнопка 'получить код' не найдена")

        # ждём, что она реально активна (не disabled)
        wait.until(lambda d: get_code_btn.is_displayed() and get_code_btn.is_enabled())

        # клик (обычный -> js fallback)
        try:
            get_code_btn.click()
        except Exception:
            js_click(driver, get_code_btn)

        print("✅ Нажали 'получить код'")

        # 6. Капча
        MAX_CAPTCHA_TRIES = 6
        captcha_success = False
        for main_attempt in range(1, MAX_CAPTCHA_TRIES + 1):
            print(f"\n🔁 Главная попытка решения капчи #{main_attempt}/{MAX_CAPTCHA_TRIES}")
            if not solve_and_submit_captcha(driver, wait):
                print("⚠️ Не удалось решить/отправить капчу на этой итерации")
                continue
            time.sleep(4)
            try:
                driver.find_element(By.CSS_SELECTOR, "div.captcha")
                print("❌ Блок капчи всё ещё на экране")
            except Exception:
                print("🎉 Блок капчи исчез — успех! Переходим к SMS...")
                captcha_success = True
                break

        if not captcha_success:
            raise RuntimeError("Не удалось пройти капчу")

        # 7. Ожидаем SMS
        sms_code = wait_sms_code(number_id, max_minutes=2)
        if not sms_code:
            print("⚠️ SMS не пришло в отведённое время")
            return False

        # 8. Ввод SMS‑кода
        print(f"Вводим SMS-код на сайт: {sms_code}")
        code_digits = [d for d in sms_code if d.isdigit()][:4]

        try:
            inputs = driver.find_elements(
                By.XPATH,
                "//input[@type='tel' or @type='text'][contains(@inputmode, 'numeric') or contains(@pattern, '[0-9]*') or contains(@class, 'code')]",
            )
            if len(inputs) >= 4 and len(code_digits) >= 4:
                for i, digit in enumerate(code_digits[:4]):
                    inputs[i].clear()
                    inputs[i].send_keys(digit)
                    time.sleep(0.4)
                print("✅ Код введён по отдельным полям")
            else:
                raise Exception("Не найдено 4 поля для кода или мало цифр")
        except Exception:
            try:
                code_input = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//input[contains(@placeholder, 'code') or contains(@class, 'verification')]")
                    )
                )
                code_input.clear()
                code_input.send_keys("".join(code_digits))
                print("✅ Код введён в одно поле")
            except Exception as e:
                print(f"Ошибка ввода SMS-кода: {e}")
                save_debug(driver, "sms_input_failed")
                return False

        save_debug(driver, "registration_success")
        success = True
        fail_reason = "Регистрация завершена успешно"  
        
        # ЛОГИРУЕМ УСПЕХ СРАЗУ
        log_result(number_id, phone_for_site, True, fail_reason) 
        set_corecluster_status(number_id, 6)  
        return True

    except Exception as e:
        fail_reason = str(e)[:100]  # ← НОВЫЙ БЛОК
        print(f"❌ Ошибка цикла: {fail_reason}")
        save_debug(driver, "exception_cycle")
        
        # ✅ ЛОГИРУЕМ НЕУДАЧУ СРАЗУ
        log_result(number_id, phone_for_site, False, fail_reason)  # ← ДОБАВИТЬ
        if number_id:
            set_corecluster_status(number_id, 8)  # ← ДОБАВИТЬ
        return False


    finally:
        try:
            driver.quit()
        except Exception as e:
            print(f"⚠️ Ошибка при закрытии драйвера: {e}")



def main():
    total_ok = 0
    total_fail = 0

    for i in range(1, MAX_PHONE_CYCLES + 1):
        print(f"\n================ ЦИКЛ #{i} ================")
        ok = run_cycle()
        if ok:
            total_ok += 1
        else:
            total_fail += 1
        print(f"Статистика сейчас: успешных {total_ok}, неуспешных {total_fail}")
        time.sleep(5)

    print("\n=== ИТОГОВЫЙ ОТЧЁТ ===")
    print(f"Успешных номеров:   {total_ok}")
    print(f"Неуспешных номеров: {total_fail}")


if __name__ == "__main__":
    main()
