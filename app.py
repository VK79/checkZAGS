# app.py
from flask import Flask, render_template, request, jsonify, send_file
import json
import re
from typing import Dict, Optional
import csv
import os
from io import StringIO

app = Flask(__name__)

# === КОПИЯ ВАШЕЙ ФУНКЦИИ verify_zags и load_zags_spравочник ===
ZAGS_SPRAVKA = {}

def load_zags_spravochnik(filename: str = "1.2.643.5.1.13.13.99.2.832_3.6.json") -> Dict[str, Dict]:
    """Загружает справочник органов ЗАГС из JSON"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Ошибка загрузки: {e}")
        return {}

    spisok = {}

    def extract_info(obj: dict):
        info = {}
        for field in ['NAME', 'name', 'Наименование']:
            if field in obj and obj[field]:
                info['name'] = obj[field]
                break
        if 'data' in obj and isinstance(obj['data'], dict):
            info['address'] = obj['data'].get('AD', '')
        elif 'AD' in obj:
            info['address'] = obj['AD']
        for field in ['TEL', 'tel', 'Телефон']:
            if field in obj and obj[field]:
                info['tel'] = obj[field]
                break
        return info

    def find_organs(obj):
        if isinstance(obj, list):
            for item in obj:
                find_organs(item)
        elif isinstance(obj, dict):
            kod_field = None
            for key in ['Newkodorgan', 'New_kod_organ', 'New_kodorgan']:
                if key in obj:
                    kod_field = key
                    break
            if kod_field:
                kod = str(obj[kod_field])
                info = extract_info(obj)
                info['kod_organ'] = kod
                spisok[kod] = info
            for value in obj.values():
                find_organs(value)

    find_organs(data)
    print(f"📊 Всего загружено органов: {len(spisok)}")
    return spisok

ZAGS_SPRAVKA = load_zags_spravochnik()

def verify_zags(num_az: int, verbose: bool = False) -> Dict:
    """Расширенная верификация с детальной информацией"""
    s = f"{num_az:021d}"
    result = {
        "valid": False,
        "number": s,
        "details": {}
    }

    if len(s) != 21 or not s.isdigit():
        if verbose:
            result["details"]["error"] = "Номер должен состоять из 21 цифры"
        return result

    razryad = [int(d) for d in s]

    razdel = razryad[0]
    if razdel < 1:
        if verbose:
            result["details"]["error"] = f"Неверный раздел ЕГР: {razdel}"
        return result

    tip_zapisi = razryad[1]
    valid_tips = {1: "Рождение", 2: "Заключение брака", 3: "Расторжение брака",
                  4: "Установление отцовства", 5: "Усыновление", 6: "Перемена имени", 7: "Смерть"}
    if tip_zapisi not in valid_tips:
        if verbose:
            result["details"]["error"] = f"Неверный тип записи: {tip_zapisi}"
        return result

    god = int(''.join(map(str, razryad[2:5])))
    if god > 999:
        if verbose:
            result["details"]["error"] = f"Неверный год: {god}"
        return result

    kod_organa = ''.join(map(str, razryad[5:13]))
    poryadkovy_nomer = int(''.join(map(str, razryad[13:18])))
    dop_priznak = int(''.join(map(str, razryad[18:20])))
    valid_dop = {0, 10, 20}

    if dop_priznak not in valid_dop:
        if verbose:
            result["details"]["error"] = f"Неверный дополнительный признак: {dop_priznak}"
        return result

    koef = [1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2]
    control_sum = 0
    for i in range(20):
        prod = razryad[i] * koef[i]
        if prod > 9:
            prod -= 9
        control_sum += prod

    calculated_check = (10 - (control_sum % 10)) % 10
    actual_check = razryad[20]
    is_valid = calculated_check == actual_check

    organ = ZAGS_SPRAVKA.get(kod_organa, {})

    result["valid"] = is_valid
    result["details"] = {
        "razdel": razdel,
        "tip_zapisi": tip_zapisi,
        "tip_name": valid_tips[tip_zapisi],
        "god": god,
        "kod_organa": kod_organa,
        "poryadkovy_nomer": poryadkovy_nomer,
        "dop_priznak": dop_priznak,
        "calculated_check": calculated_check,
        "actual_check": actual_check,
        "organ_name": organ.get("name", "Не найден"),
        "organ_address": organ.get("address", "—"),
        "organ_tel": organ.get("tel", "—"),
    }
    return result


# === МАРШРУТЫ FLASK ===

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/verify_single', methods=['POST'])
def verify_single():
    data = request.get_json()
    num_str = data.get('number', '').strip()

    if not num_str.isdigit():
        return jsonify({"valid": False, "error": "Введите только цифры"})

    try:
        num = int(num_str)
        result = verify_zags(num, verbose=True)
        return jsonify(result)
    except Exception as e:
        return jsonify({"valid": False, "error": str(e)})

@app.route('/verify_multiple', methods=['POST'])
def verify_multiple():
    data = request.get_json()
    numbers_text = data.get('numbers', '')
    # Разделители: запятые, точки с запятой, переносы строк
    separators = r'[,;\n\r]+'
    num_list = re.split(separators, numbers_text.strip())
    results = []

    for n in num_list:
        n = n.strip()
        if not n:
            continue
        if not n.isdigit():
            results.append({"number": n, "valid": False, "error": "Не цифры"})
            continue
        try:
            num = int(n)
            res = verify_zags(num)
            results.append({
                "number": n,
                "valid": res["valid"]
            })
        except:
            results.append({"number": n, "valid": False})

    # Генерация CSV в памяти
    output = StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['Номер актовой записи', 'результат'])
    for r in results:
        writer.writerow([r['number'], 'True' if r['valid'] else 'False'])

    return jsonify({
        "results": results,
        "csv": output.getvalue()
    })

@app.route('/download_csv', methods=['POST'])
def download_csv():
    csv_data = request.form.get('csv_data', '')
    if not csv_data:
        return "No data", 400

    output = StringIO()
    output.write(csv_data)
    output.seek(0)

    return send_file(
        StringIO(output.getvalue()),
        mimetype='text/csv',
        as_attachment=True,
        download_name='verification_results.csv',
        etag=False
    )


if __name__ == '__main__':
    app.run(debug=True)