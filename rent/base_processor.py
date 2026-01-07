from abc import ABC, abstractmethod
from FunPayAPI.types import OrderShortcut
from FunPayAPI.account import Account
from threading import Thread
from rent.game_type import GameType
import time
from db.database import RentDatabase
from db.rent_tables import RentalInfo
from lots_manager.manager import LotsManager
from rent.config import RentConfig
from logging_config import get_logger

logger = get_logger(__name__)


class BaseRentProcessor(ABC):
    def __init__(self, account: Account):
        self.account = account
        self.runned_tasks = {}
        self.db = RentDatabase()
        self.bot_id = RentConfig.BOT_ID
        self.game_type = GameType.NONE

    def get_chat_id(self, buyer_id: int):
        chat_id = f"users-{self.bot_id}-{buyer_id}"
        return chat_id

    @abstractmethod
    def create_missing_lots(self):
        pass

    @abstractmethod
    def change_lots_status(self):
        pass

    @abstractmethod
    def on_sale_extend(self, order: OrderShortcut):
        """
        Вызывается при покупке лота продления
        """
        pass

    @abstractmethod
    def on_sale(self, order: OrderShortcut):
        """
        Вызыватся при покупке лота аренды
        """
        pass

    def on_return(
        self, order_id: str, buyer_id: int, message, login = None
    ):
        try:
            self.account.refund(order_id)
            chat_id = self.get_chat_id(buyer_id)
            self.account.send_message(chat_id, message)
            if login:
                self.db.set_account_banned(login, True)
            logger.info(f"💰 Возврат: заказ {order_id}" + (f", аккаунт {login} заблокирован" if login else ""))
        except Exception as e:
            logger.error(f"❌ Ошибка возврата {order_id}: {e}")
            chat_id = self.get_chat_id(buyer_id)
            self.account.send_message(chat_id, "Возникла проблема, пожалуйста, дождитесь ответа администратора")

    def on_review(self, order_id: str):
        """
        Вызывается, когда оставили отзыв
        """
        rent = self.db.get_rental_by_order_id(order_id)

        if not rent:
            return

        chat_id = self.get_chat_id(rent.buyer_id)

        if not rent.in_rent:  # если уже кончилось игровое время
            self.account.send_message(
                chat_id,
                "🙏 Спасибо за отзыв!\n"
                "⏰ К сожалению, время вашей аренды истекло и мы не можем добавить вам подарочное время.\n"
                "💡 Вы можете удалить отзыв и снова оставить его во время активной аренды",
            )
            return
        if rent.feedback_bonus_given:  # если уже давали бонус
            self.account.send_message(
                chat_id,
                "🙏 Спасибо за отзыв!\n"
                f"✅ Бонус по заказу {rent.order_id} был начислен ранее",
            )
            return

        # когда все условия для бонуса соблюдены
        self.db.extend_rental(order_id, 60)
        self.db.set_feedback_bonus_given(order_id)
        self.account.send_message(
            chat_id,
            "🎉 Спасибо за отзыв!\n"
            "🎁 Мы начислили вам дополнительный час игрового времени!",
        )
        logger.info(f"🎁 Бонус за отзыв: {order_id} +1ч")

    def on_rental_expired(self, rent: RentalInfo):
        """
        Вызывается, когда кончилась аренда
        """
        order_id = rent.order_id
        buyer_id = rent.buyer_id
        logger.info(f"⏰ Аренда истекла: {order_id}, аккаунт {rent.account_login}")

        chat_id = self.get_chat_id(buyer_id)
        self.db.set_in_rent_false(order_id)
        self.db.set_account_busy(login=rent.account_login, is_busy=False)
        self.db.update_account_rented_by(rent.account_login, None)

        account = self.db.get_account_by_login(rent.account_login)
        self.kick(login=account.login, password=account.password)

        recreate_status = LotsManager.recreate_lot(
            account=self.account, game_type=rent.game_type, login=rent.account_login
        )
        if not recreate_status:
            logger.warning(f"⚠️ Не удалось пересоздать лот для {rent.account_login}")
            self.create_missing_lots()

        self.account.send_message(
            chat_id,
            f"⏰ Время аренды #{order_id} истекло! Аккаунт был освобождён.\n"
            "Вы были отключены от Steam аккаунта.\n"
            "Если хотите продлить аренду, оформите новый заказ.",
        )
        self.account.send_message(
            chat_id,
            f"Заказ выполнен. Пожалуйста, зайдите в раздел «Покупки», выберите его в списке и нажмите кнопку «Подтвердить выполнение заказа»",
        )

    @abstractmethod
    def get_code(self, login: str):
        pass

    def on_get_code(self, order_id: str, buyer_id: int):
        """
        Вызывается на команду !code order_id
        Выдает код аутентификатора
        """

        rent = self.db.get_rental_by_order_id(order_id)
        chat_id = self.get_chat_id(buyer_id)

        if not rent:
            self.account.send_message(
                chat_id,
                "❌ Заказ не найден. Правильное использование: !code <id заказа>",
            )
            return

        if rent.buyer_id != buyer_id:
            self.account.send_message(
                chat_id, f"❌ Вы не являетесь покупателем заказа {order_id}"
            )
            return

        steam_code = self.get_code(rent.account_login)

        self.account.send_message(chat_id, f"🔒 Код для входа в аккаунт: {steam_code}")

    def on_get_time(self, buyer_id):
        """
        Вызывается на команду !время
        """
        rents = self.db.get_rentals_by_buyer(buyer_id)
        chat_id = self.get_chat_id(buyer_id)
        if not len(rents):
            self.account.send_message(chat_id, "⏰ У вас нет активных аренд")
            return

        message = "⏱️ Ваши аренды:\n"
        for rent in rents:
            current_time = time.time()
            remaining_time = rent.end_rent_time - current_time

            if remaining_time <= 0:
                message += f"❌ Заказ {rent.order_id}: время истекло\n"
            else:
                hours = int(remaining_time // 3600)
                minutes = int((remaining_time % 3600) // 60)
                seconds = int(remaining_time % 60)
                
                if hours > 0:
                    message += f"📦 Заказ {rent.order_id}: {hours} ч. {minutes} мин.\n"
                elif minutes > 0:
                    message += f"📦 Заказ {rent.order_id}: {minutes} мин. {seconds} сек.\n"
                else:
                    message += f"📦 Заказ {rent.order_id}: {seconds} сек.\n"

        self.account.send_message(chat_id, message)

    def on_extend(self, order_id: str, buyer_id: int):
        """
        Вызывается на команду !продление order_id
        """
        rent = self.db.get_rental_by_order_id(order_id)
        chat_id = self.get_chat_id(buyer_id)
        if not rent:
            self.account.send_message(chat_id, f"❌ Заказ #{order_id} не найден.")
            return

        mean_price = rent.income / rent.amount

        if buyer_id != rent.buyer_id:
            self.account.send_message(
                chat_id, f"Ошибка - заказ {order_id} не пренадлежит вам"
            )
            return

        LotsManager.create_extend_lot(self.account, order_id, mean_price)

        extend_lot = LotsManager.find_extend_lot(self.account, order_id, rent.game_type)

        if not extend_lot:
            logger.error(f"❌ Не удалось создать лот продления: {order_id}")
            self.account.send_message(
                chat_id,
                "❌ Не удалось найти созданный лот продления. Попробуйте позже или обратитесь к администратору.",
            )
            return

        self.account.send_message(
            chat_id,
            f"✨ Лот на продление заказа {order_id} создан.\n"
            f"Ссылка для оплаты: {extend_lot.public_link}",
        )
        logger.info(f"📌 Создан лот продления: {order_id}")

    @abstractmethod
    def auto_reply(self, message):
        pass

    def run_tasks(self):
        pass

    def find_expired_rents(self):
        while True:
            expired_rents = self.db.get_expired_rentals()
            for rent in expired_rents:
                self.on_rental_expired(rent)

            rents_for_notify = self.db.get_rentals_expiring_soon(
                RentConfig.NOTIFY_TIME + 1
            )
            for rent in rents_for_notify:
                self.notify(rent)

            time.sleep(60)

    def notify(self, rent: RentalInfo):
        buyer_id = rent.buyer_id
        order_id = rent.order_id
        chat_id = self.get_chat_id(buyer_id)
        current_time = time.time()
        remaining_time = rent.end_rent_time - current_time
        hours = int(remaining_time // 3600)
        minutes = int((remaining_time % 3600) // 60)

        self.account.send_message(
            chat_id,
            f"⚠️ Внимание! До окончания аренды  {order_id} осталось ~{hours} часов {minutes} минут.\n"
            f"⚠️ Если хотите продолжить играть, оформите продление заказа.\n"
            f"⚠️ После окончания времени вы будете отключены от аккаунта. Продлить аренду уже не получится",
        )
        self.db.set_notified(order_id)
        logger.info(f"📢 Уведомление: {order_id} истекает через ~{hours}ч {minutes}мин")

    def start_task(self, task):
        task_thread = Thread(target=task, daemon=True)
        task_thread.start()
        self.runned_tasks[task.__name__] = task_thread

    @abstractmethod
    def kick(self, login: str, password: str):
        pass


if __name__ == "__main__":
    FUNPAY_TOKEN = "8nhu2drjgvf99h9509j7kftojpnd9w8c"
    FUNPAY_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    FUNPAY_ADMIN_NAME = "Mookor"

    account = Account(FUNPAY_TOKEN, FUNPAY_USER_AGENT).get()
    base_rent = BaseRentProcessor(account, GameType.DOTA, 1012581)

    db = RentDatabase()

    rent = RentalInfo(
        buyer_id=17798176,
        start_rent_time=time.time(),
        end_rent_time=time.time() + 60,
        order_id="qqdq",
        game_type=GameType.DOTA,
        account_login="qqdq",
        income=123,
        amount=1,
    )
    db.add_rental(rent)
    base_rent.run_tasks()
