import json
import re
from typing import Dict, Optional


def verify_zags(num_az: int, verbose: bool = False) -> bool:
    """
    Верифицирует номер актовой записи ЗАГС.

    Args:
        num_az: Номер записи (21 цифра)
        verbose: Если True, выводит подробную информацию

    Returns:
        bool: True если номер валиден
    """
    # Преобразуем в строку и дополняем нулями до 21 цифры
    s = f"{num_az:021d}"
    if len(s) != 21 or not s.isdigit():
        if verbose:
            print("Ошибка: номер должен состоять из 21 цифры")
        return False

    # Извлекаем компоненты (нумерация разрядов с 1)
    razryad = [int(d) for d in s]

    # 1. Раздел ЕГР (1 разряд) - обычно 1, но проверим >0
    razdel = razryad[0]
    if razdel < 1:
        if verbose:
            print(f"Неверный раздел ЕГР: {razdel}")
        return False

    # 2. Тип записи (2 разряд)
    tip_zapisi = razryad[1]
    valid_tips = {1: "Рождение", 2: "Заключение брака", 3: "Расторжение брака",
                  4: "Установление отцовства", 5: "Усыновление", 6: "Перемена имени", 7: "Смерть"}
    if tip_zapisi not in valid_tips:
        if verbose:
            print(f"Неверный тип записи: {tip_zapisi}")
        return False

    # 3. Год (3-5 разряды) - последние 3 цифры года (000-999)
    god = int(''.join(map(str, razryad[2:5])))
    if god > 999:
        if verbose:
            print(f"Неверный год: {god}")
        return False

    # 4. Код органа ЗАГС (6-13 разряды) - 8 цифр
    kod_organa = ''.join(map(str, razryad[5:13]))

    # 5. Порядковый номер (14-18 разряды) - 5 цифр
    poryadkovy_nomer = int(''.join(map(str, razryad[13:18])))

    # 6. Дополнительный признак (19-20 разряды)
    dop_priznak = int(''.join(map(str, razryad[18:20])))
    valid_dop = {0, 10, 20}
    if dop_priznak not in valid_dop:
        if verbose:
            print(f"Неверный дополнительный признак: {dop_priznak}")
        return False
    dop_meaning = {0: "Стандартная запись", 10: "Временное отсутствие связи", 20: "Восстановленная запись"}

    # 7. Проверяем контрольную сумму
    koef = [1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2]  # для разрядов 1-20

    control_sum = 0
    for i in range(20):
        prod = razryad[i] * koef[i]
        if prod > 9:
            prod -= 9
        control_sum += prod

    calculated_check = (10 - (control_sum % 10)) % 10
    actual_check = razryad[20]

    is_valid = calculated_check == actual_check

    if verbose:
        print(f"\033[31m=== ИНФОРМАЦИЯ О ЗАПИСИ ===\033[0m")
        print(f"Номер записи: {num_az}")
        print(f"Раздел ЕГР: {razdel}")
        print(f"Тип записи: {valid_tips[tip_zapisi]} (код {tip_zapisi})")
        print(f"Год: 20{god if god >= 0 else '???'}{'' if god >= 24 else ' (до 2024?)'}")
        print(f"Код органа ЗАГС: {kod_organa}")
        organ = ZAGS_SPRAVKA.get(kod_organa)
        if organ:
            print(f"Наименование:  {organ.get('name', 'N/A')}")
            print(f"Адрес: {organ.get('address', 'N/A')}")
            print(f"Телефон: {organ.get('tel', 'N/A')}")
        else:
            print(f"Орган {kod_organa} не найден")
        print(f"Порядковый номер: {poryadkovy_nomer:05d}")
        print(f"Доп.признак: {dop_priznak} ({dop_meaning[dop_priznak]})")
        print(f"Контрольная сумма: рассчитано={calculated_check}, в номере={actual_check}")
        print(f"Валиден: {is_valid}")

    return is_valid


def load_zags_spравочник(filename: str = "1.2.643.5.1.13.13.99.2.832_3.6.json") -> Dict[str, Dict]:
    """
    Корректно загружает справочник по реальной структуре JSON.
    """
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Ошибка загрузки: {e}")
        return {}

    spisok = {}

    def extract_info(obj: dict, kod: str):
        """Извлекает NAME, AD, TEL из объекта"""
        info = {}

        # Поля наименования (разные варианты)
        for field in ['NAME', 'name', 'Наименование']:
            if field in obj and obj[field]:
                info['name'] = obj[field]
                break

        # Адрес (AD или data.AD)
        if 'data' in obj and isinstance(obj['data'], dict):
            info['address'] = obj['data'].get('AD', '')
        elif 'AD' in obj:
            info['address'] = obj['AD']

        # Телефон
        for field in ['TEL', 'tel', 'Телефон']:
            if field in obj and obj[field]:
                info['tel'] = obj[field]
                break

        return info

    # Поиск по всему JSON (массив объектов)
    def find_organs(obj, path=""):
        if isinstance(obj, list):
            for i, item in enumerate(obj):
                find_organs(item, f"{path}[{i}]")
        elif isinstance(obj, dict):
            # Ищем Newkodorgan / New_kod_organ (с разными вариантами написания)
            kod_field = None
            for key in ['Newkodorgan', 'New_kod_organ', 'New_kodorgan']:
                if key in obj:
                    kod_field = key
                    break

            if kod_field:
                kod = f"{obj[kod_field]}"
                info = extract_info(obj, kod)
                info['kod_organ'] = kod
                spisok[kod] = info
                # print(f"✅ Загружен орган {kod}: {info.get('name', 'N/A')}")

            # Рекурсивный поиск
            for key, value in obj.items():
                find_organs(value, f"{path}.{key}")

    find_organs(data)
    print(f"📊 Всего загружено органов: {len(spisok)}")
    return spisok


# Глобальный справочник
ZAGS_SPRAVKA = load_zags_spравочник()


# def verify_zags(num_az: int, verbose: bool = False) -> bool:
#     """Верификация с корректным поиском органа ЗАГС"""
#     s = f"{num_az:021d}"
#     if len(s) != 21 or not s.isdigit():
#         if verbose: print("❌ Неверный формат: 21 цифра")
#         return False
#
#     razryad = [int(d) for d in s]
#
#     # Извлечение компонентов
#     razdel = razryad[0]
#     tip_zapisi = razryad[1]
#     god = int(''.join(map(str, razryad[2:5])))
#     kod_organa = ''.join(map(str, razryad[5:13]))  # 8 цифр!
#
#     valid_tips = {1: "Рождение", 2: "Брак", 3: "Развод", 4: "Отцовство",
#                   5: "Усыновление", 6: "Имя", 7: "Смерть"}
#
#     if tip_zapisi not in valid_tips:
#         if verbose: print(f"❌ Неверный тип: {tip_zapisi}")
#         return False
#
#     # Контрольная сумма (без изменений)
#     koef = [1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2]
#     control_sum = sum(
#         (razryad[i] * koef[i] - 9 if razryad[i] * koef[i] > 9 else razryad[i] * koef[i]) for i in range(20))
#     calculated_check = (10 - (control_sum % 10)) % 10
#     is_valid = calculated_check == razryad[20]
#
#     if verbose:
#         print("═" * 60)
#         print("АКТОВЫЙ НОМЕР ЗАГС")
#         print("═" * 60)
#         print(f"📋 Раздел: {razdel} | Тип: {valid_tips[tip_zapisi]} ({tip_zapisi})")
#         print(f"📅 Год: 20{god} | Код ЗАГС: {kod_organa}")
#
#         organ = ZAGS_SPRAVKA.get(kod_organa)
#         if organ:
#             print(f"🏛️  {organ.get('name', 'N/A')}")
#             print(f"📍 {organ.get('address', 'N/A')}")
#             print(f"📞 {organ.get('tel', 'N/A')}")
#         else:
#             print(f"❓ Орган {kod_organa} не найден")
#
#         print(f"✅ Контрольная сумма: {calculated_check} == {razryad[20]} → {'ВАЛИДЕН' if is_valid else 'НЕВАЛИДЕН'}")
#         print("═" * 60)
#
#     return is_valid

