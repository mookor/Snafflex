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
        return int(match.group(1))
    return DEFAULT_MIN_HOURS


class DotaRentProcessor(BaseRentProcessor):
    def __init__(self, account: Account):
        super().__init__(account)
        self.game_type = GameType.DOTA

    def change_lots_status(self):
        while True:
            all_lots = LotsManager.find_all_game_lots(self.account, self.game_type)
            for lot in all_lots:
                login = lot.description.split("|")[-1].split(",")[0].strip().lower()
                acc = self.db.get_account_by_login(login)

                status = not (acc.is_banned or acc.is_busy)
                if lot.active == status:
                    continue
                try:
                    if not status:
                        LotsManager.disable_lot(self.account, lot)
                    else:
                        LotsManager.enable_lot(self.account, lot)
                except Exception as e:
                    logger.error(f"Ошибка - change_lots_status - {lot.description} , {lot.id}")
                    
                logger.info(f"{'✅' if status else '❌'} Лот {acc.login}: {'вкл' if status else 'выкл'}")
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
                    logger.info(f"✅ Создан лот: {acc.login}")
                time.sleep(1)
            time.sleep(60)

    def get_code(self, login: str):
        code = get_steam_guard_code(login)
        if not code:
            logger.error(f"❌ Не удалось получить Steam Guard код: {login}")
        return code

    def kick(self, login: str, password: str):
        try:
            result = kick_user_from_account(login, password)
            if not result:
                logger.error(f"❌ Не удалось выкинуть из аккаунта: {login}")
        except:
            logger.error(f"❌ Не удалось выкинуть из аккаунта: {login}")




    def on_sale(self, order: OrderShortcut):
        login = order.description.split("|")[-1].strip().split(",")[0].strip()
        logger.info(f"🛒 Новый заказ {order.id}: {login}, {order.amount}ч, {order.price}₽")

        lot = LotsManager.find_lot_by_login(self.account, self.game_type, login)
        if lot is None or not lot.active:
            logger.warning(f"⚠️ Лот {login} недоступен — возврат")
            self.on_return(
                order.id, order.buyer_id,
                message="Извините, произошла ошибка\nДеньги возвращены на ваш счет",
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
            self.on_return(order.id, order.buyer_id, message)
            return

        steam_account = self.db.get_account_by_login(login)
        if steam_account is None or steam_account.is_banned:
            logger.error(f"❌ Аккаунт {login} недоступен — возврат")
            self.on_return(
                order.id, order.buyer_id,
                message="Извините, произошла ошибка\nДеньги возвращены на ваш счет",
            )
            return

        LotsManager.disable_lot(self.account, lot)

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

    def on_sale_extend(self, order: OrderShortcut, original_order_id):
        chat_id = order.chat_id
        self.db.extend_rental(original_order_id, order.amount * 60)

        rent = self.db.get_rental_by_order_id(original_order_id)
        if not rent:
            logger.error(f"❌ Продление: заказ {original_order_id} не найден")
            return

        lot = LotsManager.find_lot_by_login(self.account, self.game_type, rent.account_login)
        if lot:
            self.account.delete_lot(lot.id)

        self.account.send_message(chat_id, f"Аренда успешно продлена на {order.amount}ч.")
        logger.info(f"⏰ Продление: {original_order_id} +{order.amount}ч")

    def update_mmr(self):
        while True:
            try:
                all_accounts = self.db.get_accounts_by_game(self.game_type)
                for acc in all_accounts:
                    try:
                        new_mmr = get_rank(acc.dota_id)
                        if new_mmr != acc.mmr:
                            logger.info(f"📈 MMR {acc.login}: {acc.mmr} → {new_mmr}")
                            self.db.update_dota_account(acc.login, mmr=new_mmr)
                            lot = LotsManager.find_lot_by_login(self.account, self.game_type, acc.login)
                            if lot:
                                LotsManager.update_mmr(self.account, lot, new_mmr, acc.login)
                    except Exception as e:
                        logger.error(f"❌ MMR ошибка {acc.login}: {e}")
                    time.sleep(1)
                time.sleep(DotaConfig.MMR_UPDATE_INTERVAL)
            except Exception as e:
                logger.error(f"❌ Критическая ошибка MMR: {e}")
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
