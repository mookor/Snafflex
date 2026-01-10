from typing import Optional
from rent.base_processor import BaseRentProcessor
from FunPayAPI.types import OrderShortcut
from FunPayAPI.account import Account
from FunPayAPI.common.exceptions import RequestFailedError
from db.database import RentDatabase
from rent.game_type import GameType
from db.rent_tables import RentalInfo
import time
import re
from lots_manager.manager import LotsManager
from auth.steam.steam_client import kick_user_from_account
from auth.steam.steam_client import get_steam_guard_code
from rent.dota.get_rank import get_rank
from rent.dota.config import DotaConfig
from logging_config import get_logger

logger = get_logger(__name__)

MIN_HOURS_PATTERN = re.compile(r"от\s*(\d+)\s*час", re.IGNORECASE)
DEFAULT_MIN_HOURS = 3


def _parse_min_hours(lot_description: str) -> int:
    """Парсит минимальное время аренды из описания лота (например, 'от 6 часов')"""
    match = MIN_HOURS_PATTERN.search(lot_description)
    if match:
        return int(match.group(1))
    return DEFAULT_MIN_HOURS


class DotaRentProcessor(BaseRentProcessor):
    def __init__(self, account: Account):
        super().__init__(account)
        self.game_type = GameType.DOTA

    def change_lots_status(self):
        last_429_time = 0
        consecutive_429_count = 0
        
        while True:
            try:
                all_lots = LotsManager.find_all_game_lots(self.account, self.game_type)
                # Сбрасываем счетчик при успешном получении списка
                consecutive_429_count = 0
            except RequestFailedError as e:
                if hasattr(e, 'status_code') and e.status_code == 429:
                    consecutive_429_count += 1
                    wait_time = min(60 * consecutive_429_count, 300)  # Максимум 5 минут
                    logger.warning(f"⚠️ 429 Too Many Requests при получении лотов. Ожидание {wait_time} секунд...")
                    time.sleep(wait_time)
                    last_429_time = time.time()
                    continue
                else:
                    logger.error(f"❌ Ошибка при получении списка лотов: {e}", exc_info=True)
                    time.sleep(10)
                    continue
            except Exception as e:
                logger.error(f"❌ Ошибка при получении списка лотов: {e}", exc_info=True)
                time.sleep(10)
                continue

            for lot in all_lots:
                try:
                    # Проверяем, не было ли недавно ошибки 429
                    if last_429_time > 0 and (time.time() - last_429_time) < 60:
                        # Увеличиваем задержку после 429
                        time.sleep(3)
                    else:
                        time.sleep(2)  # Обычная задержка между запросами
                    
                    login = lot.description.split("|")[-1].split(",")[0].strip().lower()
                    acc = self.db.get_account_by_login(login)
                    
                    if not acc:
                        logger.warning(f"⚠️ Аккаунт {login} не найден в БД для лота {lot.id}")
                        continue

                    status = not (acc.is_banned or acc.is_busy)
                    if lot.active == status:
                        continue
                    
                    # Пытаемся изменить статус лота с обработкой 429
                    retries = 3
                    success = False
                    for attempt in range(retries):
                        try:
                            if not status:
                                LotsManager.disable_lot(self.account, lot)
                            else:
                                LotsManager.enable_lot(self.account, lot)
                            logger.info(f"{'✅' if status else '❌'} Лот {acc.login}: {'вкл' if status else 'выкл'}")
                            success = True
                            consecutive_429_count = 0  # Сбрасываем счетчик при успехе
                            break
                        except RequestFailedError as e:
                            if hasattr(e, 'status_code') and e.status_code == 429:
                                consecutive_429_count += 1
                                wait_time = min(30 * consecutive_429_count, 180)  # Максимум 3 минуты
                                logger.warning(
                                    f"⚠️ 429 Too Many Requests при изменении статуса лота {lot.id} "
                                    f"(попытка {attempt + 1}/{retries}). Ожидание {wait_time} секунд..."
                                )
                                last_429_time = time.time()
                                time.sleep(wait_time)
                                if attempt < retries - 1:
                                    continue
                                else:
                                    logger.error(f"❌ Не удалось изменить статус лота {lot.id} после {retries} попыток")
                            else:
                                logger.error(f"❌ Ошибка при изменении статуса лота {lot.id} ({lot.description}): {e}", exc_info=True)
                                break
                        except Exception as e:
                            logger.error(f"❌ Ошибка при изменении статуса лота {lot.id} ({lot.description}): {e}", exc_info=True)
                            break
                    
                    if not success:
                        # Если не удалось изменить статус после всех попыток, пропускаем этот лот
                        continue
                        
                except Exception as e:
                    logger.error(f"❌ Ошибка при обработке лота {lot.id if lot else 'unknown'}: {e}", exc_info=True)
                    time.sleep(1)
            
            # Увеличиваем интервал между циклами, если были ошибки 429
            if last_429_time > 0 and (time.time() - last_429_time) < 300:
                sleep_time = 120  # 2 минуты после ошибки 429
            else:
                sleep_time = 60  # Обычный интервал
            time.sleep(sleep_time)

    def auto_reply(self, message):
        pass

    def create_missing_lots(self):
        last_429_time = 0
        consecutive_429_count = 0
        
        while True:
            try:
                all_accounts = self.db.get_accounts_by_game(self.game_type)
                consecutive_429_count = 0  # Сбрасываем счетчик при успешном получении аккаунтов
                
                for acc in all_accounts:
                    try:
                        # Проверяем, не было ли недавно ошибки 429
                        if last_429_time > 0 and (time.time() - last_429_time) < 60:
                            time.sleep(3)  # Увеличиваем задержку после 429
                        else:
                            time.sleep(2)  # Обычная задержка
                        
                        lot = LotsManager.find_lot_by_login(self.account, self.game_type, acc.login)
                        if not lot:
                            retries = 3
                            success = False
                            for attempt in range(retries):
                                try:
                                    LotsManager.create_dota_rent(self.account, acc.mmr, acc.login, not (acc.is_busy or acc.is_banned), acc.behavior_score)
                                    logger.info(f"✅ Создан лот: {acc.login}")
                                    success = True
                                    consecutive_429_count = 0
                                    break
                                except RequestFailedError as e:
                                    if hasattr(e, 'status_code') and e.status_code == 429:
                                        consecutive_429_count += 1
                                        wait_time = min(30 * consecutive_429_count, 180)
                                        logger.warning(
                                            f"⚠️ 429 Too Many Requests при создании лота для {acc.login} "
                                            f"(попытка {attempt + 1}/{retries}). Ожидание {wait_time} секунд..."
                                        )
                                        last_429_time = time.time()
                                        time.sleep(wait_time)
                                        if attempt < retries - 1:
                                            continue
                                    else:
                                        logger.error(f"❌ Ошибка при создании лота для {acc.login}: {e}", exc_info=True)
                                        break
                                except Exception as e:
                                    logger.error(f"❌ Ошибка при создании лота для {acc.login}: {e}", exc_info=True)
                                    break
                            
                            if not success:
                                logger.warning(f"⚠️ Не удалось создать лот для {acc.login} после {retries} попыток")
                    except RequestFailedError as e:
                        if hasattr(e, 'status_code') and e.status_code == 429:
                            consecutive_429_count += 1
                            wait_time = min(30 * consecutive_429_count, 180)
                            logger.warning(f"⚠️ 429 Too Many Requests при проверке лота для {acc.login}. Ожидание {wait_time} секунд...")
                            last_429_time = time.time()
                            time.sleep(wait_time)
                        else:
                            logger.error(f"❌ Ошибка при проверке/создании лота для аккаунта {acc.login if acc else 'unknown'}: {e}", exc_info=True)
                    except Exception as e:
                        logger.error(f"❌ Ошибка при проверке/создании лота для аккаунта {acc.login if acc else 'unknown'}: {e}", exc_info=True)

                # Увеличиваем интервал между циклами, если были ошибки 429
                if last_429_time > 0 and (time.time() - last_429_time) < 300:
                    sleep_time = 120
                else:
                    sleep_time = 60
                time.sleep(sleep_time)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.error(f"❌ Критическая ошибка в цикле создания лотов: {e}", exc_info=True)
                time.sleep(60)

    def get_code(self, login: str):
        try:
            code = get_steam_guard_code(login)
            if not code:
                logger.error(f"❌ Не удалось получить Steam Guard код: {login}")
            return code
        except Exception as e:
            logger.error(f"❌ Ошибка при получении Steam Guard кода для {login}: {e}", exc_info=True)
            return None

    def kick(self, login: str, password: str):
        try:
            result = kick_user_from_account(login, password)
            if not result:
                logger.error(f"❌ Не удалось выкинуть из аккаунта: {login}")
            else:
                logger.info(f"Успешно выкинули с аккаунта {login}")
        except Exception as e:
            logger.error(f"❌ Ошибка при отключении пользователя от аккаунта {login}: {e}", exc_info=True)




    def on_sale(self, order: OrderShortcut):
        try:
            login = order.description.split("|")[-1].strip().split(",")[0].strip()
            logger.info(f"🛒 Новый заказ {order.id}: {login}, {order.amount}ч, {order.price}₽")

            try:
                lot = LotsManager.find_lot_by_login(self.account, self.game_type, login)
            except RequestFailedError as e:
                if hasattr(e, 'status_code') and e.status_code == 429:
                    logger.warning(f"⚠️ 429 Too Many Requests при поиске лота для {login}. Ожидание 30 секунд...")
                    time.sleep(30)
                    # Повторная попытка
                    try:
                        lot = LotsManager.find_lot_by_login(self.account, self.game_type, login)
                    except Exception as e2:
                        logger.error(f"❌ Ошибка при повторном поиске лота для {login}: {e2}", exc_info=True)
                        self.on_return(
                            order.id, order.buyer_id,
                            message="Извините, произошла ошибка\nДеньги возвращены на ваш счет",
                            chat_id=order.chat_id,
                        )
                        return
                else:
                    logger.error(f"❌ Ошибка при поиске лота для {login}: {e}", exc_info=True)
                    self.on_return(
                        order.id, order.buyer_id,
                        message="Извините, произошла ошибка\nДеньги возвращены на ваш счет",
                        chat_id=order.chat_id,
                    )
                    return
            except Exception as e:
                logger.error(f"❌ Ошибка при поиске лота для {login}: {e}", exc_info=True)
                self.on_return(
                    order.id, order.buyer_id,
                    message="Извините, произошла ошибка\nДеньги возвращены на ваш счет",
                    chat_id=order.chat_id,
                )
                return

            if lot is None or not lot.active:
                logger.warning(f"⚠️ Лот {login} недоступен — возврат")
                self.on_return(
                    order.id, order.buyer_id,
                    message="Извините, произошла ошибка\nДеньги возвращены на ваш счет",
                    chat_id=order.chat_id,
                )
                return

            min_rent_hours = _parse_min_hours(order.description)
            if order.amount < min_rent_hours:
                logger.warning(f"⚠️ Мало времени: {order.amount}ч < {min_rent_hours}ч — возврат")
                message = (
                    f"⚠️ Минимальное время аренды — {min_rent_hours} часов.\n\n"
                    f"Вы заказали: {order.amount} ч.\n"
                    f"Пожалуйста, оформите заказ на {min_rent_hours} часов или больше.\n"
                    "💸 Средства возвращены автоматически."
                )
                self.on_return(order.id, order.buyer_id, message, chat_id=order.chat_id)
                return

            try:
                steam_account = self.db.get_account_by_login(login)
            except Exception as e:
                logger.error(f"❌ Ошибка при получении аккаунта {login} из БД: {e}", exc_info=True)
                self.on_return(
                    order.id, order.buyer_id,
                    message="Извините, произошла ошибка\nДеньги возвращены на ваш счет",
                    chat_id=order.chat_id,
                )
                return

            if steam_account is None or steam_account.is_banned:
                logger.error(f"❌ Аккаунт {login} недоступен — возврат")
                self.on_return(
                    order.id, order.buyer_id,
                    message="Извините, произошла ошибка\nДеньги возвращены на ваш счет",
                    chat_id=order.chat_id,
                )
                return

            try:
                LotsManager.disable_lot(self.account, lot)
            except RequestFailedError as e:
                if hasattr(e, 'status_code') and e.status_code == 429:
                    logger.warning(f"⚠️ 429 Too Many Requests при отключении лота {lot.id}. Ожидание 30 секунд...")
                    time.sleep(30)
                    try:
                        LotsManager.disable_lot(self.account, lot)
                    except Exception as e2:
                        logger.error(f"❌ Ошибка при повторном отключении лота {lot.id}: {e2}", exc_info=True)
                        # Продолжаем, даже если не удалось отключить лот
                else:
                    logger.error(f"❌ Ошибка при отключении лота {lot.id}: {e}", exc_info=True)
                    # Продолжаем, даже если не удалось отключить лот
            except Exception as e:
                logger.error(f"❌ Ошибка при отключении лота {lot.id}: {e}", exc_info=True)
                # Продолжаем, даже если не удалось отключить лот

            try:
                rental = RentalInfo(
                    buyer_id=order.buyer_id,
                    start_rent_time=time.time(),
                    end_rent_time=time.time() + order.amount * 3600,
                    order_id=order.id,
                    game_type=self.game_type,
                    account_login=login,
                    income=order.price,
                    amount=order.amount,
                )
                self.db.add_rental(rental)
                self.db.update_account_rented_by(login, order.buyer_id)
                self.db.set_account_busy(login, True)
            except Exception as e:
                logger.error(f"❌ Ошибка при добавлении аренды в БД для заказа {order.id}: {e}", exc_info=True)
                # Пытаемся вернуть деньги, если не удалось сохранить аренду
                try:
                    self.on_return(
                        order.id, order.buyer_id,
                        message="Извините, произошла ошибка при обработке заказа\nДеньги возвращены на ваш счет",
                        chat_id=order.chat_id,
                    )
                except:
                    pass
                return

            try:
                message = f"""Логин: {steam_account.login}
Пароль: {steam_account.password}
Для получения кода: !code {order.id}
🐓 При проблемах с аккаунтом: !ban {order.id} (возврат в течение 10 мин)
⏰ Узнать время: !время
📌 Продлить: !продлить {order.id}
⚠️ По истечению срока вы будете отключены!"""
                chat_id = order.chat_id
                self.account.send_message(chat_id, message)
                logger.info(f"✅ Заказ {order.id}: аккаунт {login} выдан")
            except Exception as e:
                logger.error(f"❌ Ошибка отправки данных аккаунта для заказа {order.id}: {e}", exc_info=True)
                # Аккаунт уже выдан в БД, но сообщение не отправлено - это не критично
        except Exception as e:
            logger.error(f"❌ Критическая ошибка при обработке заказа {order.id}: {e}", exc_info=True)
            # Пытаемся вернуть деньги при критической ошибке
            try:
                self.on_return(
                    order.id, order.buyer_id,
                    message="Извините, произошла критическая ошибка\nДеньги возвращены на ваш счет",
                    chat_id=order.chat_id if hasattr(order, 'chat_id') else None,
                )
            except:
                logger.error(f"❌ Не удалось вернуть деньги для заказа {order.id} после критической ошибки")

    def on_sale_extend(self, order: OrderShortcut, original_order_id):
        try:
            chat_id = order.chat_id
            try:
                self.db.extend_rental(original_order_id, order.amount * 60)
            except Exception as e:
                logger.error(f"❌ Ошибка при продлении аренды {original_order_id} в БД: {e}", exc_info=True)
                try:
                    self.account.send_message(chat_id, f"❌ Произошла ошибка при продлении аренды. Попробуйте позже или обратитесь к администратору.")
                except:
                    pass
                return

            try:
                rent = self.db.get_rental_by_order_id(original_order_id)
            except Exception as e:
                logger.error(f"❌ Ошибка при получении аренды {original_order_id}: {e}", exc_info=True)
                return

            if not rent:
                logger.error(f"❌ Продление: заказ {original_order_id} не найден")
                try:
                    self.account.send_message(chat_id, f"❌ Заказ {original_order_id} не найден.")
                except:
                    pass
                return

            # Ищем и удаляем лот продления по original_order_id
            try:
                extend_lot = LotsManager.find_extend_lot(self.account, original_order_id, rent.game_type)
                if extend_lot:
                    try:
                        self.account.delete_lot(extend_lot.id)
                        logger.info(f"✅ Удален лот продления {extend_lot.id} для заказа {original_order_id}")
                    except RequestFailedError as e:
                        if hasattr(e, 'status_code') and e.status_code == 429:
                            logger.warning(f"⚠️ 429 Too Many Requests при удалении лота продления {extend_lot.id}. Ожидание 30 секунд...")
                            time.sleep(30)
                            try:
                                self.account.delete_lot(extend_lot.id)
                                logger.info(f"✅ Удален лот продления {extend_lot.id} для заказа {original_order_id} (повторная попытка)")
                            except Exception as e2:
                                logger.error(f"❌ Ошибка при повторном удалении лота продления {extend_lot.id}: {e2}", exc_info=True)
                        else:
                            logger.error(f"❌ Ошибка при удалении лота продления {extend_lot.id}: {e}", exc_info=True)
                    except Exception as e:
                        logger.error(f"❌ Ошибка при удалении лота продления {extend_lot.id}: {e}", exc_info=True)
                else:
                    logger.warning(f"⚠️ Лот продления для заказа {original_order_id} не найден (возможно, уже удален)")
            except RequestFailedError as e:
                if hasattr(e, 'status_code') and e.status_code == 429:
                    logger.warning(f"⚠️ 429 Too Many Requests при поиске лота продления для заказа {original_order_id}. Ожидание 30 секунд...")
                    time.sleep(30)
                    try:
                        extend_lot = LotsManager.find_extend_lot(self.account, original_order_id, rent.game_type)
                        if extend_lot:
                            try:
                                self.account.delete_lot(extend_lot.id)
                                logger.info(f"✅ Удален лот продления {extend_lot.id} для заказа {original_order_id} (после повторного поиска)")
                            except Exception as e2:
                                logger.error(f"❌ Ошибка при удалении лота продления {extend_lot.id}: {e2}", exc_info=True)
                    except Exception as e2:
                        logger.error(f"❌ Ошибка при повторном поиске лота продления для заказа {original_order_id}: {e2}", exc_info=True)
                else:
                    logger.error(f"❌ Ошибка при поиске лота продления для заказа {original_order_id}: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"❌ Ошибка при поиске лота продления для заказа {original_order_id}: {e}", exc_info=True)

            try:
                self.account.send_message(chat_id, f"Аренда успешно продлена на {order.amount}ч.")
                logger.info(f"⏰ Продление: {original_order_id} +{order.amount}ч")
            except Exception as e:
                logger.error(f"❌ Ошибка отправки сообщения о продлении {original_order_id}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"❌ Критическая ошибка при обработке продления {original_order_id}: {e}", exc_info=True)

    def update_mmr(self):
        last_429_time = 0
        consecutive_429_count = 0
        
        while True:
            try:
                all_accounts = self.db.get_accounts_by_game(self.game_type)
                consecutive_429_count = 0  # Сбрасываем счетчик при успешном получении аккаунтов
                
                for acc in all_accounts:
                    try:
                        # Проверяем, не было ли недавно ошибки 429
                        if last_429_time > 0 and (time.time() - last_429_time) < 60:
                            time.sleep(3)
                        else:
                            time.sleep(2)
                        
                        new_mmr = get_rank(acc.dota_id)
                        if new_mmr != acc.mmr:
                            logger.info(f"📈 MMR {acc.login}: {acc.mmr} → {new_mmr}")
                            self.db.update_dota_account(acc.login, mmr=new_mmr)
                            
                            retries = 3
                            success = False
                            for attempt in range(retries):
                                try:
                                    lot = LotsManager.find_lot_by_login(self.account, self.game_type, acc.login)
                                    if lot:
                                        LotsManager.update_mmr(self.account, lot, new_mmr, acc.login)
                                    success = True
                                    consecutive_429_count = 0
                                    break
                                except RequestFailedError as e:
                                    if hasattr(e, 'status_code') and e.status_code == 429:
                                        consecutive_429_count += 1
                                        wait_time = min(30 * consecutive_429_count, 180)
                                        logger.warning(
                                            f"⚠️ 429 Too Many Requests при обновлении MMR лота для {acc.login} "
                                            f"(попытка {attempt + 1}/{retries}). Ожидание {wait_time} секунд..."
                                        )
                                        last_429_time = time.time()
                                        time.sleep(wait_time)
                                        if attempt < retries - 1:
                                            continue
                                    else:
                                        logger.error(f"❌ Ошибка при обновлении MMR лота для {acc.login}: {e}", exc_info=True)
                                        break
                                except Exception as e:
                                    logger.error(f"❌ Ошибка при обновлении MMR лота для {acc.login}: {e}", exc_info=True)
                                    break
                            
                            if not success:
                                logger.warning(f"⚠️ Не удалось обновить MMR лота для {acc.login} после {retries} попыток")
                    except RequestFailedError as e:
                        if hasattr(e, 'status_code') and e.status_code == 429:
                            consecutive_429_count += 1
                            wait_time = min(30 * consecutive_429_count, 180)
                            logger.warning(f"⚠️ 429 Too Many Requests при получении MMR для {acc.login}. Ожидание {wait_time} секунд...")
                            last_429_time = time.time()
                            time.sleep(wait_time)
                        else:
                            logger.error(f"❌ MMR ошибка {acc.login}: {e}", exc_info=True)
                    except Exception as e:
                        logger.error(f"❌ MMR ошибка {acc.login}: {e}", exc_info=True)
                
                # Увеличиваем интервал, если были ошибки 429
                if last_429_time > 0 and (time.time() - last_429_time) < 300:
                    sleep_time = DotaConfig.MMR_UPDATE_INTERVAL * 2
                else:
                    sleep_time = DotaConfig.MMR_UPDATE_INTERVAL
                time.sleep(sleep_time)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.error(f"❌ Критическая ошибка MMR: {e}", exc_info=True)
                time.sleep(DotaConfig.MMR_UPDATE_INTERVAL)
    
    def run_tasks(self):
        self.start_task(self.update_mmr)
        self.start_task(self.change_lots_status)
        self.start_task(self.create_missing_lots)
        logger.info("🚀 DotaRentProcessor: все задачи запущены")



if __name__ == "__main__":
    FUNPAY_TOKEN = "8nhu2drjgvf99h9509j7kftojpnd9w8c"
    FUNPAY_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    FUNPAY_ADMIN_NAME = "Mookor"

    account = Account(FUNPAY_TOKEN, FUNPAY_USER_AGENT).get()
    base_rent = DotaRentProcessor(account)
    chat_id = base_rent.get_chat_id(17798176)

    db = RentDatabase()

    rent = RentalInfo(
        buyer_id=17798176,
        start_rent_time=time.time(),
        end_rent_time=time.time() + 60 * 31,
        order_id="qqdq",
        game_type=GameType.DOTA,
        account_login="qqdq",
        income=123,
        amount=31,
    )
    db.add_rental(rent)
    base_rent.run_tasks()
    while True:
        time.sleep(0.1)
