from typing import Optional
from rent.base_processor import BaseRentProcessor
from FunPayAPI.types import OrderShortcut
from FunPayAPI.account import Account
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
        hours = int(match.group(1))
        logger.debug(f"Извлечено минимальное время аренды: {hours} часов")
        return hours
    logger.debug(f"Минимальное время не найдено, используется значение по умолчанию: {DEFAULT_MIN_HOURS} часов")
    return DEFAULT_MIN_HOURS


class DotaRentProcessor(BaseRentProcessor):
    def __init__(self, account: Account):
        super().__init__(account)
        self.game_type = GameType.DOTA
        logger.info(f"✅ Инициализирован DotaRentProcessor для аккаунта {account.username}")

    def change_lots_status(self):
        while True:
            all_lots = LotsManager.find_all_game_lots(self.account, self.game_type)
            for lot in all_lots:
                login = lot.description.split("|")[-1].split(",")[0].strip().lower()
                acc = self.db.get_account_by_login(login)

                status =  not ( acc.is_banned or acc.is_busy)
                if lot.active == status:
                    continue

                if not status:
                    LotsManager.disable_lot(self.account, lot)
                    logger.info(f"❌ лот для аккаунта {acc.login} деактивирован")
                else:
                    LotsManager.enable_lot(self.account, lot)
                    logger.info(f"✅ лот для аккаунта {acc.login} активирован")
                time.sleep(1)
            time.sleep(60)

    def auto_reply(self, message):
        pass

    def create_missing_lots(self):
        while True:
            all_accounts = self.db.get_accounts_by_game(self.game_type)
            for acc in all_accounts:
                lot = LotsManager.find_lot_by_login(self.account, self.game_type, acc.login)
                if not lot:
                    LotsManager.create_dota_rent(self.account, acc.mmr, acc.login, not (acc.is_busy or acc.is_banned), acc.behavior_score)
                    logger.info(f"✅ Создан лот для аккаунта {acc.login}")
                time.sleep(1)
            time.sleep(60)

    def get_code(self, login: str):
        logger.info(f"🔐 Запрос Steam Guard кода для аккаунта: {login}")
        code = get_steam_guard_code(login)
        if code:
            logger.info(f"✅ Steam Guard код получен для {login}")
        else:
            logger.error(f"❌ Не удалось получить Steam Guard код для {login}")
        return code

    def kick(self, login: str, password: str):
        logger.info(f"🔄 Начинаем процесс выкидывания пользователя из аккаунта: {login}")
        result = kick_user_from_account(login, password)
        if result:
            logger.info(f"✅ Пользователь успешно выкинут из аккаунта: {login}")
        else:
            logger.error(f"❌ Не удалось выкинуть пользователя из аккаунта: {login}")
        return result



    def on_sale(self, order: OrderShortcut):
        logger.info(f"🛒 Обработка нового заказа {order.id}, покупатель: {order.buyer_id}, сумма: {order.price}₽")
        
        login = order.description.split("|")[-1].strip().split(",")[0].strip()
        logger.info(f"📝 Извлечен логин из описания заказа: {login}")

        lot = LotsManager.find_lot_by_login(self.account, self.game_type, login)
        if lot is None or not lot.active:
            logger.warning(f"⚠️ Лот для аккаунта {login} не найден или неактивен (lot_id: {lot.id if lot else None})")
            self.on_return(
                order.id, order.buyer_id,
                message="Извините, произошла ошибка\nДеньги возвращены на ваш счет",
            )
            return

        logger.info(f"✅ Лот найден для аккаунта {login} (lot_id: {lot.id})")
        
        min_rent_hours = _parse_min_hours(order.description)
        logger.info(f"⏰ Минимальное время аренды: {min_rent_hours} часов, заказано: {order.amount} часов")
        
        if order.amount < min_rent_hours:
            logger.warning(f"⚠️ Недостаточное время аренды: заказано {order.amount} часов, требуется минимум {min_rent_hours} часов")
            message = (
                f"⚠️ Минимальное время аренды — {min_rent_hours} часов.\n\n"
                f"Вы заказали: {order.amount} ч.\n"
                f"Пожалуйста, оформите заказ на {min_rent_hours} часов или больше.\n"
                "💸 Средства возвращены автоматически."
            )
            self.on_return(order.id, order.buyer_id, message)
            return

        steam_account = self.db.get_account_by_login(login)
        if steam_account is None or steam_account.is_banned:
            status = "не найден" if steam_account is None else "заблокирован"
            logger.error(f"❌ Аккаунт {login} {status}, возврат средств")
            self.on_return(
                order.id, order.buyer_id,
                message="Извините, произошла ошибка\nДеньги возвращены на ваш счет",
            )
            return

        logger.info(f"✅ Аккаунт {login} найден и доступен для аренды")
        logger.info(f"🔒 Деактивация лота {lot.id} для аккаунта {login}")
        LotsManager.disable_lot(self.account, lot)
        logger.info(f"✅ Лот {lot.id} деактивирован")

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
        logger.info(f"💾 Создание записи об аренде: заказ {order.id}, аккаунт {login}, время: {order.amount} часов")
        self.db.add_rental(rental)
        logger.info(f"✅ Запись об аренде добавлена в БД")
        
        logger.info(f"👤 Обновление информации об арендаторе для аккаунта {login}: покупатель {order.buyer_id}")
        self.db.update_account_rented_by(login, order.buyer_id)
        self.db.set_account_busy(login, True)
        logger.info(f"✅ Аккаунт {login} помечен как занятый")

        message = f"""Логин: {steam_account.login}
Пароль: {steam_account.password}
Для получения кода: !code {order.id}
🐓 При проблемах с аккаунтом: !ban {order.id} (возврат в течение 10 мин)
⏰ Узнать время: !время
📌 Продлить: !продлить {order.id}
⚠️ По истечению срока вы будете отключены!"""
        chat_id = self.get_chat_id(order.buyer_id)
        logger.info(f"📨 Отправка данных аккаунта покупателю {order.buyer_id} в чат {chat_id}")
        self.account.send_message(chat_id, message)
        logger.info(f"✅ Данные аккаунта отправлены покупателю {order.buyer_id}")
        logger.info(f"🎉 Заказ {order.id} успешно обработан, аккаунт {login} выдан покупателю {order.buyer_id}")

    def on_sale_extend(self, order: OrderShortcut, original_order_id):
        chat_id = self.get_chat_id(order.buyer_id)
        logger.info(f"⏰ Продление аренды: заказ продления {order.id}, оригинальный заказ {original_order_id}, время: {order.amount} часов")
        
        self.db.extend_rental(original_order_id, order.amount * 60)
        logger.info(f"✅ Аренда продлена на {order.amount} часов для заказа {original_order_id}")

        rent = self.db.get_rental_by_order_id(original_order_id)
        if not rent:
            logger.error(f"❌ Не найдена аренда для заказа {original_order_id}")
            return
        
        logger.info(f"🔍 Поиск лота для аккаунта {rent.account_login}")
        lot = LotsManager.find_lot_by_login(self.account, self.game_type, rent.account_login)
        if not lot:
            logger.warning(f"⚠️ Лот не найден для аккаунта {rent.account_login}")
            return

        logger.info(f"🗑️ Удаление лота {lot.id} для аккаунта {rent.account_login}")
        self.account.delete_lot(lot.id)
        logger.info(f"✅ Лот {lot.id} удален")
        logger.info(f"🎉 Продление аренды для заказа {original_order_id} завершено")
        self.account.send_message(chat_id, f"Аренда успешно продлена на {order.amount}ч.")

    def update_mmr(self):
        logger.info(f"🔄 Запуск задачи обновления MMR для всех Dota аккаунтов")
        while True:
            try:
                logger.info(f"📊 Начало цикла обновления MMR")
                all_accounts = self.db.get_accounts_by_game(self.game_type)
                logger.info(f"📋 Найдено {len(all_accounts)} аккаунтов Dota для проверки")
                
                updated_count = 0
                for acc in all_accounts:
                    try:
                        new_mmr = get_rank(acc.dota_id)
                        
                        if new_mmr != acc.mmr:
                            logger.info(f"📈 Обнаружено изменение MMR для {acc.login}: {acc.mmr} → {new_mmr}")
                            
                            self.db.update_dota_account(acc.login, mmr=new_mmr)
                            
                            lot = LotsManager.find_lot_by_login(self.account, self.game_type, acc.login)
                            if lot:
                                LotsManager.update_mmr(self.account, lot, new_mmr, acc.login)
                                updated_count += 1
                            else:
                                logger.info(f"⚠️ Лот не найден для аккаунта {acc.login}, обновление только в БД")
                        else:
                            logger.info(f"✓ MMR для аккаунта {acc.login} не изменился: {acc.mmr}")
                    except Exception as e:
                        logger.error(f"❌ Ошибка при обновлении MMR для аккаунта {acc.login}: {e}")
                        continue
                    time.sleep(1)
                
                logger.info(f"✅ Цикл обновления MMR завершен. Обновлено аккаунтов: {updated_count}/{len(all_accounts)}")
                logger.info(f"⏳ Ожидание {DotaConfig.MMR_UPDATE_INTERVAL} секунд до следующего обновления")
                time.sleep(DotaConfig.MMR_UPDATE_INTERVAL)
            except Exception as e:
                logger.error(f"❌ Критическая ошибка в цикле обновления MMR: {e}")
                logger.info(f"⏳ Ожидание {DotaConfig.MMR_UPDATE_INTERVAL} секунд перед повтором")
                time.sleep(DotaConfig.MMR_UPDATE_INTERVAL)
    
    def run_tasks(self):
        
        self.start_task(self.find_expired_rents)
        logger.info(f"🚀 Запуск задач DotaRentProcessor")
        logger.info(f"📋 Запуск задачи обновления MMR")
        self.start_task(self.update_mmr)

        logger.info(f"📋 Запуск задачи активации/деактивации лотов")
        self.start_task(self.change_lots_status)

        logger.info(f"📋 Запуск задачи создания отсутсвующих лотов")
        self.start_task(self.create_missing_lots)
        logger.info(f"✅ Все задачи DotaRentProcessor запущены")



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
