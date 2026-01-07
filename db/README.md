# Database Module

Модуль для работы с базой данных аренд и аккаунтов.

## Использование

```python
from db.database import RentDatabase

db = RentDatabase("rent.db")
```

## Методы

### Аренды

| Метод | Параметры | Описание |
|-------|-----------|----------|
| `get_expired_rentals()` | - | Получить аренды с истекшим временем |
| `add_rental(rental)` | `RentalInfo` | Добавить аренду |
| `delete_rental(order_id)` | `str` | Удалить аренду |
| `extend_rental(order_id, minutes)` | `str`, `int` | Продлить аренду на N минут |
| `get_rentals_expiring_soon(minutes)` | `int` | Аренды, истекающие через N минут |
| `get_rental_by_order_id(order_id)` | `str` | Получить аренду по order_id |
| `get_active_rentals()` | - | Все активные аренды |
| `get_all_rentals()` | - | Все аренды |
| `get_rentals_by_game(game_type)` | `GameType` | Все аренды по игре |
| `set_notified(order_id)` | `str` | notifed = True |
| `set_feedback_bonus_given(order_id)` | `str` | feedback_bonus_given = True |
| `set_in_rent_false(order_id)` | `str` | in_rent = False |
| `set_payed_status(order_id, status)` | `str`, `PayedStatus` | Установить PayedStatus |
| `add_income(order_id, amount)` | `str`, `float` | income += amount |

### Аккаунты

| Метод | Параметры | Описание |
|-------|-----------|----------|
| `get_account_by_login(login)` | `str` | Получить аккаунт по логину |
| `get_all_accounts()` | - | Все аккаунты |
| `get_accounts_by_game(game_type)` | `GameType` | Все аккаунты по игре |
| `add_account(account)` | `AccountInfo` | Добавить аккаунт |
| `update_account_rented_by(login, rented_by)` | `str`, `int\|None` | Обновить rented_by |
| `update_dota_account(login, mmr, behavior_score)` | `str`, `int\|None`, `int\|None` | Обновить MMR и/или behavior_score для Dota аккаунта |
| `set_account_busy(login, is_busy)` | `str`, `bool` | Установить is_busy |
| `set_account_banned(login, is_banned)` | `str`, `bool` | Установить is_banned |

## Скрипты добавления аккаунтов

```python
from db.scripts import add_dota_account, add_valorant_account, add_lol_account

# Dota
add_dota_account(
    login="login",
    password="pass",
    behavior_score=10000,
    dota_id=123456789,
    mmr=5000,
    profile_link="https://dotabuff.com/players/123"
)

# Valorant
add_valorant_account(
    login="login",
    password="pass",
    rank="Immortal 3",
    profile_link="https://tracker.gg/valorant/profile/riot/name"
)

# LoL
add_lol_account(
    login="login",
    password="pass",
    rank="Diamond 1",
    profile_link="https://op.gg/summoners/euw/name"
)
```

