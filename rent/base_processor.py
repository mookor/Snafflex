from abc import ABC, abstractmethod
from FunPayAPI.types import OrderShortcut
from FunPayAPI.account import Account
from FunPayAPI.common.exceptions import RequestFailedError
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
        self, order_id: str, buyer_id: int, message, login = None, chat_id: int | str | None = None
    ):
        try:
            self.account.refund(order_id)
            if chat_id is None:
                chat_id = self.get_chat_id(buyer_id)
            try:
                self.account.send_message(chat_id, message)
            except Exception as e:
                logger.error(f"❌ Ошибка отправки сообщения при возврате {order_id}: {e}")
            
            if login:
                try:
                    self.db.set_account_banned(login, True)
                except Exception as e:
                    logger.error(f"❌ Ошибка при блокировке аккаунта {login}: {e}", exc_info=True)
            
            logger.info(f"💰 Возврат: заказ {order_id}" + (f", аккаунт {login} заблокирован" if login else ""))
        except Exception as e:
            logger.error(f"❌ Ошибка возврата {order_id}: {e}", exc_info=True)
            try:
                if chat_id is None:
                    chat_id = self.get_chat_id(buyer_id)
                self.account.send_message(chat_id, "Возникла проблема, пожалуйста, дождитесь ответа администратора")
            except Exception as e2:
                logger.error(f"❌ Критическая ошибка: не удалось отправить сообщение об ошибке возврата {order_id}: {e2}", exc_info=True)

    def on_review(self, order_id: str, chat_id: int | str | None = None):
        """
        Вызывается, когда оставили отзыв
        """
        try:
            rent = self.db.get_rental_by_order_id(order_id)

            if not rent:
                return

            if chat_id is None:
                # Используем chat_id из аренды, если он есть, иначе вычисляем
                chat_id = rent.chat_id if rent.chat_id is not None else self.get_chat_id(rent.buyer_id)

            if not rent.in_rent:  # если уже кончилось игровое время
                try:
                    self.account.send_message(
                        chat_id,
                        "🙏 Спасибо за отзыв!\n"
                        "⏰ К сожалению, время вашей аренды истекло и мы не можем добавить вам подарочное время.\n"
                        "💡 Вы можете удалить отзыв и снова оставить его во время активной аренды",
                    )
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки сообщения об отзыве (истекло время): {e}")
                return
            if rent.feedback_bonus_given:  # если уже давали бонус
                try:
                    self.account.send_message(
                        chat_id,
                        "🙏 Спасибо за отзыв!\n"
                        f"✅ Бонус по заказу {rent.order_id} был начислен ранее",
                    )
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки сообщения об отзыве (бонус уже дан): {e}")
                return

            # когда все условия для бонуса соблюдены
            try:
                self.db.extend_rental(order_id, 60)
                self.db.set_feedback_bonus_given(order_id)
                self.account.send_message(
                    chat_id,
                    "🎉 Спасибо за отзыв!\n"
                    "🎁 Мы начислили вам дополнительный час игрового времени!",
                )
                logger.info(f"🎁 Бонус за отзыв: {order_id} +1ч")
            except Exception as e:
                logger.error(f"❌ Ошибка при начислении бонуса за отзыв {order_id}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"❌ Критическая ошибка при обработке отзыва {order_id}: {e}", exc_info=True)

    def on_rental_expired(self, rent: RentalInfo, chat_id: int | str | None = None):
        """
        Вызывается, когда кончилась аренда
        """
        order_id = rent.order_id
        buyer_id = rent.buyer_id
        logger.info(f"⏰ Аренда истекла: {order_id}, аккаунт {rent.account_login}")

        try:
            if chat_id is None:
                # Используем chat_id из аренды, если он есть, иначе вычисляем
                chat_id = rent.chat_id if rent.chat_id is not None else self.get_chat_id(buyer_id)
            
            try:
                self.db.set_in_rent_false(order_id)
                self.db.set_account_busy(login=rent.account_login, is_busy=False)
                self.db.update_account_rented_by(rent.account_login, None)
            except Exception as e:
                logger.error(f"❌ Ошибка обновления БД при истечении аренды {order_id}: {e}", exc_info=True)

            try:
                account = self.db.get_account_by_login(rent.account_login)
                if account:
                    # Если это CommonRentProcessor, нужно получить правильный процессор
                    # Для этого используем прямое определение типа
                    if hasattr(self, 'game_type') and self.game_type == GameType.NONE:
                        # Это CommonRentProcessor, нужно найти правильный процессор
                        # Импортируем здесь, чтобы избежать циклических импортов
                        from rent.common.processor import CommonRentProcessor
                        if isinstance(self, CommonRentProcessor):
                            # Получаем правильный процессор через game_type
                            processor = self._get_processor_by_game_type(rent.game_type)
                            if processor:
                                processor.kick(login=account.login, password=account.password)
                            else:
                                logger.warning(f"⚠️ Процессор для {rent.game_type} не найден, используем прямой вызов")
                                # Фолбэк: используем прямой импорт функции
                                from auth.steam.steam_client import kick_user_from_account
                                try:
                                    result = kick_user_from_account(account.login, account.password)
                                    if result:
                                        logger.info(f"✅ Успешно выкинули с аккаунта {account.login} (прямой вызов)")
                                    else:
                                        logger.error(f"❌ Не удалось выкинуть из аккаунта {account.login} (прямой вызов)")
                                except Exception as e:
                                    logger.error(f"❌ Ошибка при прямом вызове kick_user_from_account: {e}", exc_info=True)
                        else:
                            self.kick(login=account.login, password=account.password)
                    else:
                        # Это специфичный процессор (DotaRentProcessor и т.д.), используем его метод
                        self.kick(login=account.login, password=account.password)
                else:
                    logger.error(f"❌ Аккаунт {rent.account_login} не найден в БД")
                    
            except Exception as e:
                logger.error(f"❌ Ошибка при отключении пользователя от аккаунта {rent.account_login}: {e}", exc_info=True)

            try:
                recreate_status = LotsManager.recreate_lot(
                    account=self.account, game_type=rent.game_type, login=rent.account_login
                )
                if not recreate_status:
                    logger.warning(f"⚠️ Не удалось пересоздать лот для {rent.account_login}")
                    try:
                        self.create_missing_lots()
                    except Exception as e:
                        logger.error(f"❌ Ошибка при создании отсутствующих лотов: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"❌ Ошибка при пересоздании лота для {rent.account_login}: {e}", exc_info=True)

            try:
                self.account.send_message(
                    chat_id,
                    f"⏰ Время аренды #{order_id} истекло! Аккаунт был освобождён.\n"
                    "Вы были отключены от Steam аккаунта.\n"
                    "Если хотите продлить аренду, оформите новый заказ.",
                )
            except Exception as e:
                logger.error(f"❌ Ошибка отправки сообщения об истечении аренды {order_id}: {e}")

            try:
                self.account.send_message(
                    chat_id,
                    f"Заказ выполнен. Пожалуйста, зайдите в раздел «Покупки», выберите его в списке и нажмите кнопку «Подтвердить выполнение заказа»",
                )
            except Exception as e:
                logger.error(f"❌ Ошибка отправки сообщения о подтверждении заказа {order_id}: {e}")
        except Exception as e:
            logger.error(f"❌ Критическая ошибка при обработке истечения аренды {order_id}: {e}", exc_info=True)
    
    def _get_processor_by_game_type(self, game_type: GameType):
        """
        Вспомогательный метод для получения процессора по game_type.
        Переопределяется в CommonRentProcessor для доступа к процессорам.
        """
        return None

    @abstractmethod
    def get_code(self, login: str):
        pass

    def on_get_code(self, order_id: str, buyer_id: int, chat_id: int | str | None = None):
        """
        Вызывается на команду !code order_id
        Выдает код аутентификатора
        """
        try:
            rent = self.db.get_rental_by_order_id(order_id)
            if chat_id is None:
                # Используем chat_id из аренды, если он есть, иначе вычисляем
                chat_id = rent.chat_id if rent and rent.chat_id is not None else self.get_chat_id(buyer_id)

            if not rent:
                try:
                    self.account.send_message(
                        chat_id,
                        "❌ Заказ не найден. Правильное использование: !code <id заказа>",
                    )
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки сообщения об отсутствии заказа: {e}")
                return

            if rent.buyer_id != buyer_id:
                try:
                    self.account.send_message(
                        chat_id, f"❌ Вы не являетесь покупателем заказа {order_id}"
                    )
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки сообщения о правах на заказ: {e}")
                return

            try:
                steam_code = self.get_code(rent.account_login)
                if steam_code:
                    self.account.send_message(chat_id, f"🔒 Код для входа в аккаунт: {steam_code}")
                else:
                    self.account.send_message(chat_id, "❌ Не удалось получить код. Попробуйте позже.")
                    logger.error(f"❌ Не удалось получить Steam Guard код для {rent.account_login}")
            except Exception as e:
                logger.error(f"❌ Ошибка при получении кода для {rent.account_login}: {e}", exc_info=True)
                try:
                    self.account.send_message(chat_id, "❌ Произошла ошибка при получении кода. Попробуйте позже.")
                except:
                    pass
        except Exception as e:
            logger.error(f"❌ Критическая ошибка при обработке команды !code {order_id}: {e}", exc_info=True)
            try:
                if chat_id is None:
                    chat_id = self.get_chat_id(buyer_id)
                self.account.send_message(chat_id, "❌ Произошла ошибка при обработке команды.")
            except:
                pass

    def on_get_time(self, buyer_id: int, chat_id: int | str | None = None):
        """
        Вызывается на команду !время
        """
        try:
            rents = self.db.get_rentals_by_buyer(buyer_id)
            if chat_id is None:
                chat_id = self.get_chat_id(buyer_id)
            if not len(rents):
                try:
                    self.account.send_message(chat_id, "⏰ У вас нет активных аренд")
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки сообщения о времени: {e}")
                return

            message = "⏱️ Ваши аренды:\n"
            for rent in rents:
                try:
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
                except Exception as e:
                    logger.error(f"❌ Ошибка при обработке аренды {rent.order_id if rent else 'unknown'} для команды !время: {e}")

            try:
                self.account.send_message(chat_id, message)
            except Exception as e:
                logger.error(f"❌ Ошибка отправки сообщения о времени аренды: {e}")
        except Exception as e:
            logger.error(f"❌ Критическая ошибка при обработке команды !время: {e}", exc_info=True)
            try:
                if chat_id is None:
                    chat_id = self.get_chat_id(buyer_id)
                self.account.send_message(chat_id, "❌ Произошла ошибка при получении времени аренды.")
            except:
                pass

    def on_extend(self, order_id: str, buyer_id: int, chat_id: int | str | None = None):
        """
        Вызывается на команду !продление order_id
        """
        try:
            rent = self.db.get_rental_by_order_id(order_id)
            if chat_id is None:
                # Используем chat_id из аренды, если он есть, иначе вычисляем
                chat_id = rent.chat_id if rent and rent.chat_id is not None else self.get_chat_id(buyer_id)
            if not rent:
                try:
                    self.account.send_message(chat_id, f"❌ Заказ #{order_id} не найден.")
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки сообщения о продлении: {e}")
                return

            try:
                mean_price = rent.income / rent.amount
            except ZeroDivisionError:
                logger.error(f"❌ Деление на ноль при вычислении средней цены для заказа {order_id}")
                try:
                    self.account.send_message(chat_id, f"❌ Ошибка: некорректные данные заказа {order_id}.")
                except:
                    pass
                return

            if buyer_id != rent.buyer_id:
                try:
                    self.account.send_message(
                        chat_id, f"Ошибка - заказ {order_id} не пренадлежит вам"
                    )
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки сообщения о правах на продление: {e}")
                return

            try:
                # Пытаемся создать лот продления с обработкой 429
                retries = 3
                extend_lot = None
                for attempt in range(retries):
                    try:
                        LotsManager.create_extend_lot(self.account, order_id, mean_price)
                        extend_lot = LotsManager.find_extend_lot(self.account, order_id, rent.game_type)
                        if extend_lot:
                            break
                    except RequestFailedError as e:
                        if hasattr(e, 'status_code') and e.status_code == 429:
                            wait_time = 30 * (attempt + 1)
                            logger.warning(
                                f"⚠️ 429 Too Many Requests при создании лота продления {order_id} "
                                f"(попытка {attempt + 1}/{retries}). Ожидание {wait_time} секунд..."
                            )
                            time.sleep(wait_time)
                            if attempt < retries - 1:
                                continue
                            else:
                                logger.error(f"❌ Не удалось создать лот продления {order_id} после {retries} попыток из-за 429")
                                try:
                                    self.account.send_message(
                                        chat_id,
                                        "❌ Слишком много запросов к серверу. Попробуйте через несколько минут.",
                                    )
                                except:
                                    pass
                                return
                        else:
                            raise

                if not extend_lot:
                    logger.error(f"❌ Не удалось создать лот продления: {order_id}")
                    try:
                        self.account.send_message(
                            chat_id,
                            "❌ Не удалось найти созданный лот продления. Попробуйте позже или обратитесь к администратору.",
                        )
                    except Exception as e:
                        logger.error(f"❌ Ошибка отправки сообщения об ошибке создания лота: {e}")
                    return

                try:
                    self.account.send_message(
                        chat_id,
                        f"✨ Лот на продление заказа {order_id} создан.\n"
                        f"Ссылка для оплаты: {extend_lot.public_link}",
                    )
                    logger.info(f"📌 Создан лот продления: {order_id}")
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки сообщения о создании лота продления: {e}")
            except RequestFailedError as e:
                if hasattr(e, 'status_code') and e.status_code == 429:
                    logger.warning(f"⚠️ 429 Too Many Requests при создании лота продления {order_id}")
                    try:
                        self.account.send_message(chat_id, "❌ Слишком много запросов к серверу. Попробуйте через несколько минут.")
                    except:
                        pass
                else:
                    logger.error(f"❌ Ошибка при создании лота продления {order_id}: {e}", exc_info=True)
                    try:
                        self.account.send_message(chat_id, "❌ Произошла ошибка при создании лота продления. Попробуйте позже.")
                    except:
                        pass
            except Exception as e:
                logger.error(f"❌ Ошибка при создании лота продления {order_id}: {e}", exc_info=True)
                try:
                    self.account.send_message(chat_id, "❌ Произошла ошибка при создании лота продления. Попробуйте позже.")
                except:
                    pass
        except Exception as e:
            logger.error(f"❌ Критическая ошибка при обработке команды !продлить {order_id}: {e}", exc_info=True)
            try:
                if chat_id is None:
                    chat_id = self.get_chat_id(buyer_id)
                self.account.send_message(chat_id, "❌ Произошла ошибка при обработке команды продления.")
            except:
                pass

    @abstractmethod
    def auto_reply(self, message):
        pass

    def run_tasks(self):
        pass

    def find_expired_rents(self):
        while True:
            try:
                expired_rents = self.db.get_expired_rentals()
                for rent in expired_rents:
                    try:
                        self.on_rental_expired(rent)
                    except Exception as e:
                        logger.error(f"❌ Ошибка при обработке истекшей аренды {rent.order_id if rent else 'unknown'}: {e}", exc_info=True)

                try:
                    rents_for_notify = self.db.get_rentals_expiring_soon(
                        RentConfig.NOTIFY_TIME + 1
                    )
                    for rent in rents_for_notify:
                        try:
                            self.notify(rent)
                        except Exception as e:
                            logger.error(f"❌ Ошибка при отправке уведомления для {rent.order_id if rent else 'unknown'}: {e}", exc_info=True)
                except Exception as e:
                    logger.error(f"❌ Ошибка при получении аренд для уведомления: {e}", exc_info=True)

                time.sleep(60)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.error(f"❌ Критическая ошибка в цикле проверки истекших аренд: {e}", exc_info=True)
                time.sleep(60)  # Продолжаем работу даже при ошибке

    def notify(self, rent: RentalInfo):
        try:
            buyer_id = rent.buyer_id
            order_id = rent.order_id
            # Используем chat_id из аренды, если он есть, иначе вычисляем
            chat_id = rent.chat_id if rent.chat_id is not None else self.get_chat_id(buyer_id)
            current_time = time.time()
            remaining_time = rent.end_rent_time - current_time
            hours = int(remaining_time // 3600)
            minutes = int((remaining_time % 3600) // 60)

            try:
                self.account.send_message(
                    chat_id,
                    f"⚠️ Внимание! До окончания аренды  {order_id} осталось ~{hours} часов {minutes} минут.\n"
                    f"⚠️ Если хотите продолжить играть, оформите продление заказа.\n"
                    f"⚠️ После окончания времени вы будете отключены от аккаунта. Продлить аренду уже не получится",
                )
                self.db.set_notified(order_id)
                logger.info(f"📢 Уведомление: {order_id} истекает через ~{hours}ч {minutes}мин")
            except Exception as e:
                logger.error(f"❌ Ошибка отправки уведомления для {order_id}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"❌ Ошибка при подготовке уведомления: {e}", exc_info=True)

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
