from seleniumbase import Driver
import time
import random

def rand_int(a, b):
    return random.randint(a, b)

def sleep(a, b=None):
    if b is None:
        time.sleep(a)
    else:
        time.sleep(random.uniform(a, b))

def safe_fill(driver, selector, value, timeout=12, retries=4):

    value_str = str(value)

    for attempt in range(1, retries + 1):
        try:
            driver.wait_for_element_visible(selector, timeout=timeout)

            ok = driver.execute_script("""
                const selector = arguments[0];
                const value = arguments[1];
                const el = document.querySelector(selector);
                if (!el) return false;

                el.focus();

                const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, "value"
                )?.set;

                if (!setter) {
                    el.value = value;
                } else {
                    setter.call(el, value);
                }

                el.dispatchEvent(new Event("input",  { bubbles: true }));
                el.dispatchEvent(new Event("change", { bubbles: true }));
                el.blur();

                return true;
            """, selector, value_str)

            sleep(0.12, 0.25)

            actual = driver.execute_script(
                "const el=document.querySelector(arguments[0]); return el?el.value:'';",
                selector
            )

            if str(actual).strip() == value_str.strip():
                return True

            print(f"[{attempt}/{retries}] Значение не закрепилось в {selector}. Было: {actual!r}")
            sleep(0.25, 0.55)

        except Exception as e:
            print(f"[{attempt}/{retries}] Не удалось заполнить {selector}: {e}")
            sleep(0.25, 0.55)

    return False


def safe_select(driver, selector, value, timeout=12):
    """
    Надёжная установка select + change/input events
    """
    driver.wait_for_element_visible(selector, timeout=timeout)
    driver.execute_script("""
        const sel = document.querySelector(arguments[0]);
        const value = arguments[1];
        if (!sel) return;
        sel.value = value;
        sel.dispatchEvent(new Event('input',  { bubbles: true }));
        sel.dispatchEvent(new Event('change', { bubbles: true }));
    """, selector, str(value))
    sleep(0.12, 0.25)


def click_germany_flag(driver):
    """
    Выбор Germany в react-tel-input:
    - открыть список флагов
    - кликнуть по data-country-code="de"
    fallback: попытка через поиск в списке
    """
    try:
        driver.js_click(".react-tel-input .selected-flag")
        sleep(0.5, 0.9)
    except Exception as e:
        print("Не смогла кликнуть по флагу:", e)
        return False

    # Прямой вариант
    try:
        driver.js_click('.react-tel-input .country-list li[data-country-code="de"]')
        sleep(0.4, 0.8)
        return True
    except:
        pass

    # Fallback через поиск
    try:
        driver.wait_for_element_visible(".react-tel-input .search-box", timeout=3)
        safe_fill(driver, ".react-tel-input .search-box", "Germany", retries=2)
        sleep(0.4, 0.8)
        driver.js_click('.react-tel-input .country-list li:contains("Germany")') 
        return True
    except:
        # Последний fallback: через JS по тексту
        try:
            driver.execute_script("""
                const items = document.querySelectorAll('.react-tel-input .country-list li');
                const el = [...items].find(x => (x.innerText || '').toLowerCase().includes('germany'));
                if (el) el.click();
            """)
            sleep(0.4, 0.8)
            return True
        except Exception as e:
            print("Не удалось выбрать Германию:", e)

    return False


def fill_phone(driver, national_digits="15510202339"):

    phone_sel = '.react-tel-input input[name="phone"]'

    driver.wait_for_element_visible(phone_sel, timeout=12)
    driver.click(phone_sel)
    sleep(0.15, 0.3)

    driver.press_keys(phone_sel, "\ue009" + "a")  # CTRL + A
    driver.press_keys(phone_sel, "\ue003")       # Backspace
    sleep(0.12, 0.25)
    driver.press_keys(phone_sel, "\ue009" + "a")  # ещё раз
    driver.press_keys(phone_sel, "\ue003")
    sleep(0.15, 0.3)

    for d in national_digits:
        driver.type(phone_sel, d)
        sleep(0.03, 0.07)

    sleep(0.4, 0.8)

    val = driver.execute_script(
        "const el=document.querySelector(arguments[0]); return el?el.value:'';",
        phone_sel
    )
    print("Phone input value after typing:", val)
    return True



def pick_region_berlin_or_first(driver):
    """
    Пытаемся выбрать Berlin в #stateDropdown, иначе первый валидный.
    """
    state_sel = "#stateDropdown"
    if not driver.is_element_present(state_sel):
        print("Region dropdown не найден (#stateDropdown).")
        return False

    # Подождём, пока появятся опции (после country change)
    sleep(0.7, 1.2)

    driver.execute_script("""
        const select = document.querySelector('#stateDropdown');
        if (!select) return;

        const options = Array.from(select.options).map(o => ({
            value: o.value,
            text: (o.textContent || '').trim()
        }));

        const berlin = options.find(o =>
            o.value && o.text.toLowerCase().includes('berlin')
        );

        const firstValid = options.find(o =>
            o.value &&
            o.value !== "0" &&
            o.text &&
            !o.text.toLowerCase().includes("state") &&
            !o.text.toLowerCase().includes("select")
        );

        if (berlin) {
            select.value = berlin.value;
            select.dispatchEvent(new Event('input',  { bubbles: true }));
            select.dispatchEvent(new Event('change', { bubbles: true }));
            console.log("Selected region:", berlin.text);
        } else if (firstValid) {
            select.value = firstValid.value;
            select.dispatchEvent(new Event('input',  { bubbles: true }));
            select.dispatchEvent(new Event('change', { bubbles: true }));
            console.log("Selected region (fallback):", firstValid.text);
        } else {
            console.log("No selectable region options found.");
        }
    """)
    sleep(0.3, 0.6)
    return True

def js_click_by_text(driver, text):
    """JS-клик по кнопке, содержащей text (частичное совпадение)"""
    return driver.execute_script("""
        const text = String(arguments[0]).toLowerCase().trim();
        const buttons = Array.from(document.querySelectorAll('button'));
        const target = buttons.find(b => (b.innerText || '').toLowerCase().includes(text));
        if (target) {
            target.scrollIntoView({ block: "center" });
            target.click();
            return true;
        }
        return false;
    """, text)



# ----------------- MAIN -----------------

if __name__ == "__main__":
    # Данные
    ts = int(time.time())
    data = {
        "firstName": "Elena",
        "lastName": "Test",
        "email": f"hel.test.{ts}{rand_int(100, 999)}@gmail.com",
        "password": f"Qw!{rand_int(100000, 999999)}_Aa",
        "phoneDigitsNoPlus": "4915510203739",  # для react-tel-input обычно лучше без '+'
        "dobMonthValue": "5",
        "dobDay": "12",
        "dobYear": "1995",
        "countryValue": "92",  # Germany 
        "zip": "10115",
    }

    # Driver: uc=True помогает с cloudflare/детектом
    driver = Driver(uc=True, headless=False, incognito=True)

    try:
        print(" Открываем xtrm.com...")
        driver.uc_open_with_reconnect("https://www.xtrm.com/personalSignup/", reconnect_time=3)
        driver.maximize_window()

        # Даем странице ожить
        sleep(3.5, 5.5)

        # Ждём первый инпут
        driver.wait_for_element_visible("#ctl00_MainContent_txtFirstName", timeout=30)
        sleep(0.3, 0.9)

        print("✍ Заполняем личные данные...")
        safe_fill(driver, "#ctl00_MainContent_txtFirstName", data["firstName"])
        sleep(0.15, 0.4)
        safe_fill(driver, "#ctl00_MainContent_txtLastName", data["lastName"])
        sleep(0.15, 0.4)
        safe_fill(driver, "#ctl00_MainContent_txtEmail", data["email"])
        sleep(0.15, 0.4)
        safe_fill(driver, "#txtPassword", data["password"])
        sleep(0.2, 0.6)

        print("Выбираем Германию и вводим телефон...")
        ok_flag = click_germany_flag(driver)
        if not ok_flag:
            print("Germany flag не выбран, продолжаем всё равно.")
        sleep(0.25, 0.55)
        fill_phone(driver, data["phoneDigitsNoPlus"])

        print("Дата рождения...")
        safe_select(driver, "#monthDropdown", data["dobMonthValue"])
        sleep(0.15, 0.35)
        safe_fill(driver, 'input[placeholder="Day"]', data["dobDay"])
        sleep(0.15, 0.35)
        safe_fill(driver, 'input[placeholder="Year"]', data["dobYear"])
        sleep(0.2, 0.6)

        print("Страна + подгрузка регионов...")
        safe_select(driver, "#countryDropdown", data["countryValue"])

        # Иногда апдейтпанель/ajax может занять дольше
        sleep(1.0, 1.6)

        print("Регион (Berlin / fallback)...")
        pick_region_berlin_or_first(driver)

        print("ZIP...")
        safe_fill(driver, "#ctl00_MainContent_txtZipcode", data["zip"])
        sleep(0.3, 0.8)

        print("Все поля заполнены.")
        print("Email:", data["email"])
        print("Password:", data["password"])

        print("Форма заполнена.")

        sleep(1)

        for i in range(3):
            if js_click_by_text(driver, "continue"):
                print("Кнопка Continue нажата!")
                break
            else:
                print("Continue не нажалась, скроллю вниз и пробую ещё раз...")
                driver.scroll_to("bottom")
                sleep(1)

        # --- ОЖИДАНИЕ СТРАНИЦЫ Verify Email ---
        print("Ждем перехода на страницу Verify Email...")
        driver.wait_for_element_visible("//button[contains(., 'Verify Email')]", timeout=60)
        sleep(0.8, 1.2)

        # --- НАЖАТИЕ VERIFY EMAIL (их способ) ---
        if js_click_by_text(driver, "verify email"):
            print("Кнопка Verify Email нажата!")
        else:
            print("Не удалось нажать Verify Email (кнопка не найдена).")



        input("Нажми Enter, чтобы закрыть браузер...")

    finally:
        driver.quit()
