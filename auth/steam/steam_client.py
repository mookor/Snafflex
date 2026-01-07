import subprocess
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

from logging_config import get_logger

logger = get_logger(__name__)


def get_steam_guard_code(login: str = None, passkey: str = "qqdq", exe_path: str = "steamguard") -> str:
    """
    Запускает steamguard.exe и возвращает Steam Guard код.
    
    :param login: Логин Steam аккаунта (передается через флаг -u)
    :param passkey: Пароль шифрования (по умолчанию "qqdq")
    :param exe_path: Путь к steamguard.exe (по умолчанию в текущей папке)
    :return: Steam Guard код (например, "DQKRV")
    """
    try:
        # Формируем команду
        cmd = [exe_path, "-p", passkey]
        if login:
            cmd.extend(["-u", login])
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15
        )
        
        output = result.stdout + result.stderr
        lines = [line.strip() for line in output.strip().split("\n") if line.strip()]
        
        if lines:
            for line in reversed(lines):
                if len(line) == 5 and line.isalnum() and line.isupper():
                    return line
            return lines[-1]
        else:
            logger.error(f"Не удалось получить код. Output: {output}")
            return ""
            
    except subprocess.TimeoutExpired:
        logger.error("Таймаут при получении Steam Guard кода")
        return ""
    except FileNotFoundError:
        logger.error(f"Файл {exe_path} не найден")
        return ""
    except Exception as e:
        logger.error(f"Ошибка при получении Steam Guard кода: {e}")
        return ""


class Steam:
    """Класс для работы со Steam через Selenium"""
    
    LOGIN_URL = "https://store.steampowered.com/login/"
    TWOFACTOR_MANAGE_URL = "https://store.steampowered.com/twofactor/manage"
    
    def __init__(self, login: str, password: str, headless: bool = True):
        """
        Инициализация Steam клиента.
        
        :param login: Логин Steam
        :param password: Пароль Steam
        :param headless: Запускать браузер в фоновом режиме
        """
        self.login = login
        self.password = password
        self.headless = headless
        self.driver = None
        self.logged_in = False
    
    def _init_driver(self):
        """Инициализация веб-драйвера Edge"""
        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        options.add_argument("--log-level=3")  # Минимум логов
        options.add_argument("--remote-debugging-port=9222")
        
        # Отключаем логи
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        
        # Selenium 4.6+ автоматически скачивает драйвер
        self.driver = webdriver.Chrome(options=options)
        self.driver.implicitly_wait(10)
    
    def _close_driver(self):
        """Закрытие драйвера"""
        if self.driver:
            self.driver.quit()
            self.driver = None
    
    def authenticate(self, steam_guard_code: str) -> bool:
        """
        Авторизация в Steam через браузер.
        
        :param steam_guard_code: Код Steam Guard
        :return: True если авторизация успешна
        """
        try:
            logger.info("🌐 Открываем страницу логина Steam...")
            self.driver.get(self.LOGIN_URL)
            time.sleep(3)
            
            wait = WebDriverWait(self.driver, 30)
            
            # Ищем форму логина (не поле поиска!)
            logger.info("📝 Ищем форму логина...")
            
            # Ждём пока форма появится
            form_container = wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div[class*='newlogindialog'], div[class*='LoginDialog'], form")
            ))
            
            # Ввод логина - ищем внутри формы
            logger.info("📝 Вводим логин...")
            login_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='text']")
            login_input = None
            for inp in login_inputs:
                # Пропускаем поле поиска
                placeholder = inp.get_attribute("placeholder") or ""
                if "search" in placeholder.lower() or "поиск" in placeholder.lower():
                    continue
                if inp.is_displayed():
                    login_input = inp
                    break
            
            if not login_input:
                logger.error("Поле логина не найдено")
                self.driver.save_screenshot("debug_login.png")
                return False
                
            login_input.clear()
            login_input.send_keys(self.login)
            time.sleep(0.5)
            
            # Ввод пароля
            logger.info("🔒 Вводим пароль...")
            password_input = wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, "input[type='password']")
            ))
            password_input.clear()
            password_input.send_keys(self.password)
            time.sleep(0.5)
            
            # Нажимаем кнопку входа
            logger.info("🔘 Нажимаем 'Войти'...")
            login_button = wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button.DjSvCZoKKfoNSmarsEcTS[type='submit']")
            ))
            login_button.click()
            time.sleep(4)
            
            # Вводим Steam Guard код
            logger.info(f"🔐 Ищем поля для Steam Guard кода...")
            try:
                # Ждем появления полей для кода (5 отдельных input'ов)
                code_inputs = wait.until(EC.presence_of_all_elements_located(
                    (By.CSS_SELECTOR, "input._3xcXqLVteTNHmk-gh9W65d")
                ))
                
                if code_inputs and len(code_inputs) >= 5:
                    logger.info(f"🔐 Вводим Steam Guard код: {steam_guard_code}")
                    # Вводим каждый символ в соответствующее поле
                    for i, char in enumerate(steam_guard_code[:5]):
                        code_inputs[i].send_keys(char)
                        time.sleep(0.3)
                    
                    time.sleep(2)
                    
                    # Пробуем найти и нажать кнопку подтверждения
                    logger.info("🔘 Ищем кнопку подтверждения...")
                    try:
                        confirm_buttons = self.driver.find_elements(By.CSS_SELECTOR, "button[type='submit'], button")
                        for btn in confirm_buttons:
                            if btn.is_displayed() and btn.is_enabled():
                                text = btn.text.lower()
                                if any(word in text for word in ["submit", "confirm", "войти", "продолжить", "continue", "ok"]):
                                    logger.info(f"🔘 Нажимаем: {btn.text}")
                                    btn.click()
                                    break
                    except:
                        pass
                    
                    time.sleep(5)
                else:
                    logger.warning("Поля Steam Guard не найдены")
                
            except Exception as e:
                logger.warning(f"Steam Guard: {e}")
            
            # Проверяем успешность входа
            time.sleep(3)
            current_url = self.driver.current_url
            logger.debug(f"Текущий URL: {current_url}")
            
            if "login" not in current_url.lower() or "store.steampowered.com" in current_url.lower():
                self.logged_in = True
                logger.info("✅ Авторизация успешна!")
                return True
            else:
                logger.error("Авторизация не удалась")
                self.driver.save_screenshot("debug_auth.png")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка при авторизации: {e}")
            self.driver.save_screenshot("debug_error.png")
            return False
    
    def deauthorize_all_devices(self) -> bool:
        """
        Выйти на всех устройствах.
        
        :return: True если успешно
        """
        if not self.logged_in:
            logger.error("Сначала необходимо авторизоваться")
            return False
        
        try:
            logger.info("🔍 Переходим на страницу управления Steam Guard...")
            self.driver.get(self.TWOFACTOR_MANAGE_URL)
            time.sleep(3)
            
            wait = WebDriverWait(self.driver, 20)
            
            # Проверяем, что мы на правильной странице
            if "login" in self.driver.current_url.lower():
                logger.error("Не авторизованы, редирект на логин")
                return False
            
            # Ищем кнопку "Выйти на всех устройствах"
            logger.info("🔍 Ищем кнопку 'Выйти на всех устройствах'...")
            
            deauth_button = None
            
            # Ищем span с onclick="ConfirmDeauthorizeAll()"
            try:
                deauth_button = wait.until(EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "span[onclick='ConfirmDeauthorizeAll()']")
                ))
            except:
                pass
            
            # Альтернатива - ищем по классу родителя и тексту
            if not deauth_button:
                try:
                    deauth_button = self.driver.find_element(
                        By.XPATH, "//a[contains(@class, 'btn_blue_white_innerfade')]//span[contains(text(), 'Выйти на всех')]"
                    )
                except:
                    pass
            
            # Ещё вариант - по тексту
            if not deauth_button:
                try:
                    deauth_button = self.driver.find_element(
                        By.XPATH, "//*[contains(text(), 'Выйти на всех устройствах')]"
                    )
                except:
                    pass
            
            if deauth_button:
                logger.info("🔘 Нажимаем кнопку деавторизации...")
                deauth_button.click()
                time.sleep(2)
                
                # Диалог подтверждения - кнопка "Продолжить"
                logger.info("🔘 Ищем кнопку подтверждения 'Продолжить'...")
                try:
                    confirm_button = wait.until(EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "div.btn_green_steamui.btn_medium")
                    ))
                    confirm_button.click()
                    logger.info("🔘 Нажали 'Продолжить'")
                    time.sleep(2)
                except:
                    # Альтернативный поиск
                    try:
                        confirm_button = self.driver.find_element(
                            By.XPATH, "//span[contains(text(), 'Продолжить')]/.."
                        )
                        confirm_button.click()
                        logger.info("🔘 Нажали 'Продолжить'")
                        time.sleep(2)
                    except:
                        pass
                
                logger.info("✅ Выход на всех устройствах выполнен!")
                return True
            else:
                logger.error("Кнопка деавторизации не найдена")
                # Сохраним скриншот для отладки
                self.driver.save_screenshot("debug_screenshot.png")
                logger.info("📸 Скриншот сохранен в debug_screenshot.png")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка при выходе на всех устройствах: {e}")
            return False
    
    def kick_all_sessions(self) -> bool:
        """
        Полный процесс: авторизация + выход на всех устройствах.
        
        :return: True если успешно
        """
        logger.info(f"🔄 Начинаем процесс выкидывания из аккаунта {self.login}...")
        
        try:
            # Инициализируем драйвер
            logger.info("🚀 Запускаем браузер...")
            self._init_driver()
            
            # Получаем Steam Guard код
            code = get_steam_guard_code(login=self.login)
            if not code:
                logger.error("Не удалось получить Steam Guard код")
                return False
            
            logger.info(f"🔐 Получен Steam Guard код: {code}")
            
            # Авторизуемся
            if not self.authenticate(code):
                return False
            
            # Небольшая пауза
            time.sleep(2)
            
            # Выходим на всех устройствах
            return self.deauthorize_all_devices()
            
        finally:
            # Закрываем браузер
            logger.info("🔚 Закрываем браузер...")
            self._close_driver()


def kick_user_from_account(login: str, password: str, headless: bool = True) -> bool:
    """
    Удобная функция для выкидывания пользователя из аккаунта.
    
    :param login: Логин Steam
    :param password: Пароль Steam
    :param headless: Запускать браузер в фоновом режиме
    :return: True если успешно
    """
    steam = Steam(login, password, headless=headless)
    return steam.kick_all_sessions()


if __name__ == "__main__":
    from logging_config import setup_logging
    setup_logging()
    
    # Тест получения кода
    code = get_steam_guard_code(login="idcw9026")
    logger.info(f"Steam Guard код: {code}")
    
    # Пример использования (headless=True - браузер в фоне, headless=False - видимый)
    steam = Steam("idcw9026", "ZXCasdngfnrernf2", headless=True)
    steam.kick_all_sessions()
