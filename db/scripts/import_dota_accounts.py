"""Импорт Dota аккаунтов в базу данных."""

from db.scripts.add_dota import add_dota_account


ACCOUNTS = [
    {
        "login": "idcw9026",
        "password": "ZXCasdngfnrernf2",
        "profile_link": "https://steamcommunity.com/profiles/76561199882245432",
        "dota_id": 1921979704,
        "mmr": 1716,
        "behavior_score": 9600,
    },
    {
        "login": "ymtgdfae79hzelc",
        "password": "iwuoebfGW",
        "profile_link": "https://steamcommunity.com/profiles/76561198775679592/",
        "dota_id": 815413864,
        "mmr": 1831,
        "behavior_score": 7020,
    },
    {
        "login": "dg7b1xcl",
        "password": "GNgweg432",
        "profile_link": "https://steamcommunity.com/profiles/76561198777572266/",
        "dota_id": 817306538,
        "mmr": 2035,
        "behavior_score": 9300,
    },
    {
        "login": "fjfkwesl77000",
        "password": "weuf6FWE78",
        "profile_link": "https://steamcommunity.com/profiles/76561198766825725/",
        "dota_id": 806559997,
        "mmr": 1967,
        "behavior_score": 7800,
    },
    {
        "login": "iffqmkmt36tao",
        "password": "iggwGWE3",
        "profile_link": "https://steamcommunity.com/profiles/76561198766466770/",
        "dota_id": 806201042,
        "mmr": 1894,
        "behavior_score": 9600,
    },
    {
        "login": "efak91dueycrb",
        "password": "4tGREWasnooi",
        "profile_link": "https://steamcommunity.com/profiles/76561198766998148/",
        "dota_id": 806732420,
        "mmr": 1952,
        "behavior_score": 10065,
    },
    {
        "login": "epmcuicw463",
        "password": "gunrEGWROJN4",
        "profile_link": "https://steamcommunity.com/profiles/76561198769128177/",
        "dota_id": 808862449,
        "mmr": 962,
        "behavior_score": 11400,
    },
    {
        "login": "lwtjmqnr45ynb",
        "password": "owgruGOWRUIH2",
        "profile_link": "https://steamcommunity.com/profiles/76561198766856897/",
        "dota_id": 806591169,
        "mmr": 612,
        "behavior_score": 10000,
    },
    {
        "login": "nkizomri462",
        "password": "gwreuih23G",
        "profile_link": "https://steamcommunity.com/profiles/76561198767030148/",
        "dota_id": 806764420,
        "mmr": 450,
        "behavior_score": 10800,
    },
    {
        "login": "drhewnws61",
        "password": "CDzLdE4VA_8",
        "profile_link": "https://steamcommunity.com/profiles/76561198766574757/",
        "dota_id": 806309029,
        "mmr": 945,
        "behavior_score": 10600,
    },
    {
        "login": "ayoj05hauhdzg",
        "password": "iyyNF3xDLF-",
        "profile_link": "https://steamcommunity.com/profiles/76561198761623098/",
        "dota_id": 801357370,
        "mmr": 1540,
        "behavior_score": 8000,
    },
    {
        "login": "jrjnnhsx2094",
        "password": "1b7X_f_ycJ9",
        "profile_link": "https://steamcommunity.com/profiles/76561198768236638/",
        "dota_id": 807970910,
        "mmr": 1,
        "behavior_score": 8000,
    },
    {
        "login": "f798u8dq",
        "password": "_ZoSKppiG6",
        "profile_link": "https://steamcommunity.com/profiles/76561198777090354",
        "dota_id": 816824626,
        "mmr": 4,
        "behavior_score": 10740,
    },
]


def import_all():
    """Импортировать все аккаунты."""
    for acc in ACCOUNTS:
        try:
            add_dota_account(**acc)
            print(f"✓ {acc['login']}")
        except Exception as e:
            print(f"✗ {acc['login']}: {e}")


if __name__ == "__main__":
    import_all()
    print(f"\nДобавлено {len(ACCOUNTS)} аккаунтов!")

