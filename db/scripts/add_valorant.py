from db.database import RentDatabase
from db.rent_tables import ValorantAccountInfo
from rent.game_type import GameType


def add_valorant_account(
    login: str,
    password: str,
    rank: str,
    profile_link: str,
    db_path: str = "rent.db"
) -> bool:
    """
    Добавить Valorant аккаунт в базу данных.
    
    Args:
        login: Логин аккаунта
        password: Пароль
        rank: Ранг (например "Immortal 3")
        profile_link: Ссылка на профиль
        db_path: Путь к базе данных
    
    Returns:
        True если успешно добавлен
    """
    db = RentDatabase(db_path)
    
    account = ValorantAccountInfo(
        login=login,
        password=password,
        rented_by=None,
        game_type=GameType.VALORANT,
        rank=rank,
        profile_link=profile_link
    )
    
    return db.add_account(account)


if __name__ == "__main__":
    # Пример использования
    add_valorant_account(
        login="example_login",
        password="example_pass",
        rank="Immortal 3",
        profile_link="https://tracker.gg/valorant/profile/riot/example"
    )
    print("Valorant аккаунт добавлен!")

