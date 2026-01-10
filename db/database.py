import sqlite3
import time
from typing import Optional, List, Union
from contextlib import contextmanager

from db.rent_tables import (
    RentalInfo, 
    AccountInfo, 
    DotaAccountInfo, 
    ValorantAccountInfo, 
    LolAccountInfo,
    PayedStatus
)
from rent.game_type import GameType


class RentDatabase:
    def __init__(self, db_path: str = "rent.db"):
        self.db_path = db_path
        self._create_tables()
    
    @contextmanager
    def _get_connection(self):
        """Контекстный менеджер для работы с соединением."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _create_tables(self):
        """Создание всех таблиц в базе данных."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Таблица аренд
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rentals (
                    order_id TEXT PRIMARY KEY,
                    buyer_id INTEGER NOT NULL,
                    start_rent_time REAL NOT NULL,
                    end_rent_time REAL NOT NULL,
                    game_type INTEGER NOT NULL,
                    account_login TEXT NOT NULL,
                    income REAL NOT NULL DEFAULT 0,
                    amount INTEGER NOT NULL DEFAULT 0,
                    notifed INTEGER NOT NULL DEFAULT 0,
                    feedback_bonus_given INTEGER NOT NULL DEFAULT 0,
                    in_rent INTEGER NOT NULL DEFAULT 1,
                    payed INTEGER NOT NULL DEFAULT 1
                )
            """)
            
            # Миграция: добавляем колонку amount, если её нет (для существующих БД)
            try:
                cursor.execute("ALTER TABLE rentals ADD COLUMN amount INTEGER NOT NULL DEFAULT 0")
            except sqlite3.OperationalError:
                # Колонка уже существует, игнорируем ошибку
                pass
            
            # Миграция: добавляем колонку chat_id, если её нет (для существующих БД)
            try:
                cursor.execute("ALTER TABLE rentals ADD COLUMN chat_id TEXT")
            except sqlite3.OperationalError:
                # Колонка уже существует, игнорируем ошибку
                pass
            
            # Базовая таблица аккаунтов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    login TEXT PRIMARY KEY,
                    password TEXT NOT NULL,
                    rented_by INTEGER,
                    game_type INTEGER NOT NULL,
                    is_busy INTEGER NOT NULL DEFAULT 0,
                    is_banned INTEGER NOT NULL DEFAULT 0
                )
            """)
            
            # Таблица для Dota аккаунтов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dota_accounts (
                    login TEXT PRIMARY KEY,
                    behavior_score INTEGER NOT NULL,
                    dota_id INTEGER NOT NULL,
                    mmr INTEGER NOT NULL,
                    profile_link TEXT NOT NULL,
                    FOREIGN KEY (login) REFERENCES accounts(login) ON DELETE CASCADE
                )
            """)
            
            # Таблица для Valorant аккаунтов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS valorant_accounts (
                    login TEXT PRIMARY KEY,
                    rank TEXT NOT NULL,
                    profile_link TEXT NOT NULL,
                    FOREIGN KEY (login) REFERENCES accounts(login) ON DELETE CASCADE
                )
            """)
            
            # Таблица для LoL аккаунтов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS lol_accounts (
                    login TEXT PRIMARY KEY,
                    rank TEXT NOT NULL,
                    profile_link TEXT NOT NULL,
                    FOREIGN KEY (login) REFERENCES accounts(login) ON DELETE CASCADE
                )
            """)
    
    # ==================== Методы для работы с арендами ====================
    
    def get_expired_rentals(self) -> List[RentalInfo]:
        """2.1) Получить аренды у которых истекло время end_rent_time."""
        current_time = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM rentals WHERE end_rent_time <= ? AND in_rent = 1",
                (current_time,)
            )
            rows = cursor.fetchall()
            return [self._row_to_rental(row) for row in rows]
    
    def add_rental(self, rental: RentalInfo) -> bool:
        """2.2) Добавить аренду аккаунта."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO rentals (
                    order_id, buyer_id, start_rent_time, end_rent_time, 
                    game_type, account_login, income, amount, notifed, 
                    feedback_bonus_given, in_rent, payed, chat_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rental.order_id,
                rental.buyer_id,
                rental.start_rent_time,
                rental.end_rent_time,
                rental.game_type.value,
                rental.account_login,
                rental.income,
                rental.amount,
                int(rental.notifed),
                int(rental.feedback_bonus_given),
                int(rental.in_rent),
                rental.payed.value,
                str(rental.chat_id) if rental.chat_id is not None else None
            ))
            return cursor.rowcount > 0
    
    def delete_rental(self, order_id: str) -> bool:
        """2.3) Удалить аренду."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM rentals WHERE order_id = ?", (order_id,))
            return cursor.rowcount > 0
    
    def extend_rental(self, order_id: str, minutes: int) -> bool:
        """2.4) Продлить аренду на N минут."""
        seconds = minutes * 60
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE rentals SET end_rent_time = end_rent_time + ? WHERE order_id = ?",
                (seconds, order_id)
            )
            return cursor.rowcount > 0
    
    def get_rentals_expiring_soon(self, minutes: int) -> List[RentalInfo]:
        """2.5) Получить список аренд, у которых осталось не более N минут."""
        current_time = time.time()
        threshold_time = current_time + (minutes * 60)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM rentals 
                   WHERE end_rent_time <= ? AND end_rent_time > ? AND in_rent = 1 AND notifed = 0""",
                (threshold_time, current_time)
            )
            rows = cursor.fetchall()
            return [self._row_to_rental(row) for row in rows]
    
        
    def get_rentals_by_buyer(self, buyer_id: int) -> List[RentalInfo]:
        """Получить список аренд по  покупателю"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM rentals 
                   WHERE buyer_id = ? AND in_rent = 1""",
                (buyer_id,)
            )
            rows = cursor.fetchall()
            return [self._row_to_rental(row) for row in rows]


    def set_notified(self, order_id: str) -> bool:
        """2.7) Проставить в True поле notifed."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE rentals SET notifed = 1 WHERE order_id = ?",
                (order_id,)
            )
            return cursor.rowcount > 0
    
    def set_feedback_bonus_given(self, order_id: str) -> bool:
        """2.8) Проставить в True поле feedback_bonus_given."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE rentals SET feedback_bonus_given = 1 WHERE order_id = ?",
                (order_id,)
            )
            return cursor.rowcount > 0
    
    def set_in_rent_false(self, order_id: str) -> bool:
        """2.9) Проставить в False поле in_rent."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE rentals SET in_rent = 0 WHERE order_id = ?",
                (order_id,)
            )
            return cursor.rowcount > 0
    
    def set_payed_status(self, order_id: str, status: PayedStatus) -> bool:
        """2.10) Установить статус оплаты (PayedStatus.BUYED/PAYED/REFUND)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE rentals SET payed = ? WHERE order_id = ?",
                (status.value, order_id)
            )
            return cursor.rowcount > 0
    
    def add_income(self, order_id: str, amount: float) -> bool:
        """2.11) Сделать += к полю income."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE rentals SET income = income + ? WHERE order_id = ?",
                (amount, order_id)
            )
            return cursor.rowcount > 0
    
    # ==================== Методы для работы с аккаунтами ====================
    
    def get_account_by_login(self, login: str) -> Optional[Union[DotaAccountInfo, ValorantAccountInfo, LolAccountInfo, AccountInfo]]:
        """2.6) Получить данные аккаунта по логину."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Получаем базовую информацию об аккаунте
            cursor.execute("SELECT * FROM accounts WHERE login = ?", (login,))
            account_row = cursor.fetchone()
            
            if not account_row:
                return None
            
            game_type = GameType(account_row['game_type'])
            
            # Проверяем специфичные таблицы в зависимости от типа игры
            if game_type == GameType.DOTA:
                cursor.execute("SELECT * FROM dota_accounts WHERE login = ?", (login,))
                extra_row = cursor.fetchone()
                if extra_row:
                    return DotaAccountInfo(
                        login=account_row['login'],
                        password=account_row['password'],
                        rented_by=account_row['rented_by'],
                        game_type=game_type,
                        is_busy=bool(account_row['is_busy']),
                        is_banned=bool(account_row['is_banned']),
                        behavior_score=extra_row['behavior_score'],
                        dota_id=extra_row['dota_id'],
                        mmr=extra_row['mmr'],
                        profile_link=extra_row['profile_link']
                    )
            
            elif game_type == GameType.VALORANT:
                cursor.execute("SELECT * FROM valorant_accounts WHERE login = ?", (login,))
                extra_row = cursor.fetchone()
                if extra_row:
                    return ValorantAccountInfo(
                        login=account_row['login'],
                        password=account_row['password'],
                        rented_by=account_row['rented_by'],
                        game_type=game_type,
                        is_busy=bool(account_row['is_busy']),
                        is_banned=bool(account_row['is_banned']),
                        rank=extra_row['rank'],
                        profile_link=extra_row['profile_link']
                    )
            
            elif game_type == GameType.LOL:
                cursor.execute("SELECT * FROM lol_accounts WHERE login = ?", (login,))
                extra_row = cursor.fetchone()
                if extra_row:
                    return LolAccountInfo(
                        login=account_row['login'],
                        password=account_row['password'],
                        rented_by=account_row['rented_by'],
                        game_type=game_type,
                        is_busy=bool(account_row['is_busy']),
                        is_banned=bool(account_row['is_banned']),
                        rank=extra_row['rank'],
                        profile_link=extra_row['profile_link']
                    )
            
            # Возвращаем базовый AccountInfo для других типов
            return AccountInfo(
                login=account_row['login'],
                password=account_row['password'],
                rented_by=account_row['rented_by'],
                game_type=game_type,
                is_busy=bool(account_row['is_busy']),
                is_banned=bool(account_row['is_banned'])
            )
    
    def add_account(self, account: Union[DotaAccountInfo, ValorantAccountInfo, LolAccountInfo, AccountInfo]) -> bool:
        """Добавить аккаунт в базу данных."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Добавляем в базовую таблицу
            cursor.execute("""
                INSERT INTO accounts (login, password, rented_by, game_type, is_busy, is_banned)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                account.login,
                account.password,
                account.rented_by,
                account.game_type.value,
                int(account.is_busy),
                int(account.is_banned)
            ))
            
            # Добавляем в специфичную таблицу
            if isinstance(account, DotaAccountInfo):
                cursor.execute("""
                    INSERT INTO dota_accounts (login, behavior_score, dota_id, mmr, profile_link)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    account.login,
                    account.behavior_score,
                    account.dota_id,
                    account.mmr,
                    account.profile_link
                ))
            
            elif isinstance(account, ValorantAccountInfo):
                cursor.execute("""
                    INSERT INTO valorant_accounts (login, rank, profile_link)
                    VALUES (?, ?, ?)
                """, (
                    account.login,
                    account.rank,
                    account.profile_link
                ))
            
            elif isinstance(account, LolAccountInfo):
                cursor.execute("""
                    INSERT INTO lol_accounts (login, rank, profile_link)
                    VALUES (?, ?, ?)
                """, (
                    account.login,
                    account.rank,
                    account.profile_link
                ))
            
            return True
    
    def update_account_rented_by(self, login: str, rented_by: Optional[int]) -> bool:
        """Обновить поле rented_by у аккаунта."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE accounts SET rented_by = ? WHERE login = ?",
                (rented_by, login)
            )
            return cursor.rowcount > 0
    
    def update_dota_account(self, login: str, mmr: Optional[int] = None, behavior_score: Optional[int] = None) -> bool:
        """Обновить MMR и/или behavior_score для аккаунта Dota по логину.
        
        Args:
            login: Логин аккаунта (обязательно)
            mmr: Новое значение MMR (опционально, если None - не обновляется)
            behavior_score: Новое значение behavior_score (опционально, если None - не обновляется)
        
        Returns:
            True если обновление прошло успешно, False если аккаунт не найден
        """
        if mmr is None and behavior_score is None:
            return False  # Нет полей для обновления
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Проверяем, существует ли аккаунт
            cursor.execute("SELECT login FROM dota_accounts WHERE login = ?", (login,))
            if not cursor.fetchone():
                return False
            
            # Формируем запрос обновления только для указанных полей
            update_parts = []
            params = []
            
            if mmr is not None:
                update_parts.append("mmr = ?")
                params.append(mmr)
            
            if behavior_score is not None:
                update_parts.append("behavior_score = ?")
                params.append(behavior_score)
            
            if update_parts:
                params.append(login)  # Добавляем login в конец для WHERE
                query = f"UPDATE dota_accounts SET {', '.join(update_parts)} WHERE login = ?"
                cursor.execute(query, params)
                return cursor.rowcount > 0
        
        return False
    def set_account_busy(self, login: str, is_busy: bool) -> bool:
        """Установить статус занятости аккаунта."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE accounts SET is_busy = ? WHERE login = ?",
                (int(is_busy), login)
            )
            return cursor.rowcount > 0
    
    def set_account_banned(self, login: str, is_banned: bool) -> bool:
        """Установить статус бана аккаунта."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE accounts SET is_banned = ? WHERE login = ?",
                (int(is_banned), login)
            )
            return cursor.rowcount > 0
    
    def get_rental_by_order_id(self, order_id: str) -> Optional[RentalInfo]:
        """Получить аренду по order_id."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rentals WHERE order_id = ?", (order_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_rental(row)
            return None
    
    def get_active_rentals(self) -> List[RentalInfo]:
        """Получить все активные аренды."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rentals WHERE in_rent = 1")
            rows = cursor.fetchall()
            return [self._row_to_rental(row) for row in rows]
    
    def get_all_rentals(self) -> List[RentalInfo]:
        """Получить все аренды."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rentals")
            rows = cursor.fetchall()
            return [self._row_to_rental(row) for row in rows]
    
    def get_rentals_by_game(self, game_type: GameType) -> List[RentalInfo]:
        """Получить все аренды по конкретной игре."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM rentals WHERE game_type = ?",
                (game_type.value,)
            )
            rows = cursor.fetchall()
            return [self._row_to_rental(row) for row in rows]
    
    def get_all_accounts(self) -> List[Union[DotaAccountInfo, ValorantAccountInfo, LolAccountInfo, AccountInfo]]:
        """Получить все аккаунты."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT login FROM accounts")
            rows = cursor.fetchall()
            return [self.get_account_by_login(row['login']) for row in rows]
    
    def get_accounts_by_game(self, game_type: GameType) -> List[Union[DotaAccountInfo, ValorantAccountInfo, LolAccountInfo, AccountInfo]]:
        """Получить все аккаунты по конкретной игре."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT login FROM accounts WHERE game_type = ?",
                (game_type.value,)
            )
            rows = cursor.fetchall()
            return [self.get_account_by_login(row['login']) for row in rows]
    
    # ==================== Вспомогательные методы ====================
    
    def _row_to_rental(self, row: sqlite3.Row) -> RentalInfo:
        """Преобразовать строку БД в объект RentalInfo."""
        # Получаем chat_id с обработкой отсутствия колонки (для обратной совместимости)
        chat_id = None
        if 'chat_id' in row.keys() and row['chat_id'] is not None:
            chat_id_value = row['chat_id']
            # Пытаемся преобразовать в int, если это число, иначе оставляем строкой
            try:
                if isinstance(chat_id_value, str) and chat_id_value.isdigit():
                    chat_id = int(chat_id_value)
                elif isinstance(chat_id_value, (int, str)):
                    chat_id = chat_id_value
            except (ValueError, TypeError):
                chat_id = chat_id_value
        
        return RentalInfo(
            buyer_id=row['buyer_id'],
            start_rent_time=row['start_rent_time'],
            end_rent_time=row['end_rent_time'],
            order_id=row['order_id'],
            game_type=GameType(row['game_type']),
            account_login=row['account_login'],
            income=row['income'],
            amount=row['amount'],  # Используем get для обратной совместимости
            notifed=bool(row['notifed']),
            feedback_bonus_given=bool(row['feedback_bonus_given']),
            in_rent=bool(row['in_rent']),
            payed=PayedStatus(row['payed']),
            chat_id=chat_id
        )

