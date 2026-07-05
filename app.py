import os
import json
import requests
from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = "rieltpro-secret-2026"

API_KEY   = os.getenv("YANDEX_API_KEY")
FOLDER_ID = os.getenv("FOLDER_ID")
URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

SYSTEM_PROMPT = """Ты — консультант по недвижимости и ипотеке в России. Помогаешь покупателям, продавцам, арендаторам и арендодателям.

Отвечай на вопросы про:
— ипотеку: семейную (6%, до 12 млн в Москве), IT-ипотеку (6%, до 9 млн, только новостройки вне Москвы и СПб), ипотеку для военнослужащих по НИС (взнос 411 185 руб/год), дальневосточную (2%, до 9 млн), арктическую, сельскую (0.1-3%, до 6 млн)
— ключевая ставка ЦБ июль 2026: 14.25%, рыночная ипотека от 16-19%
— минимальный срок ипотеки: 1 год, максимальный: 30 лет
— материнский капитал 2026: 728 921 руб на первого ребёнка, 963 243 руб на второго
— купля-продажа квартир: документы, этапы сделки, задаток vs аванс, налоги
— налог при продаже: 13% если владел менее 3 лет (единственное жильё) или 5 лет; вычет 260 тыс руб при покупке
— новостройки: ДДУ, эскроу-счёт, приёмка квартиры, проверка застройщика через наш.дом.рф
— аренда: договор, залог, права сторон, налоги самозанятого 4-6%
— ЖКХ: счётчики, управляющая компания, капремонт, права при затоплении
— законы: ФЗ-102 (ипотека), ФЗ-214 (ДДУ), ФЗ-218 (ЕГРН), ГК РФ ст.380-381 (задаток)
— застройщики России: ГК Самолёт (лидер, 4.95 млн м²), ПИК, Dogma, А101, ФСК
— ЖК Москвы: Остров (Донстрой), ХАЙ ЛАЙФ (PIONEER), Скандинавия (А101, Коммунарка)

Правила:
— Отвечай конкретно с цифрами
— Будь дружелюбен, общайся на вы
— Если точных данных нет — направь на banki.ru или наш.дом.рф
— Отвечай ТОЛЬКО на вопросы про недвижимость"""


@app.route("/")
def index():
    session.pop("history", None)
    return render_template("index.html")


@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json()
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "Пустой вопрос"}), 400

    # История диалога в сессии
    history = session.get("history", [])
    history.append({"role": "user", "text": user_message})

    # Оставляем только последние 10 сообщений чтобы не раздувать контекст
    if len(history) > 10:
        history = history[-10:]

    messages = [{"role": "system", "text": SYSTEM_PROMPT}]
    messages.extend(history)

    try:
        resp = requests.post(
            URL,
            headers={
                "Authorization": f"Api-Key {API_KEY}",
                "x-folder-id": FOLDER_ID,
                "Content-Type": "application/json"
            },
            json={
                "modelUri": f"gpt://{FOLDER_ID}/yandexgpt/latest",
                "completionOptions": {
                    "stream": False,
                    "temperature": 0.4,
                    "maxTokens": 2000
                },
                "messages": messages
            },
            timeout=30
        )
        resp.raise_for_status()
        result = resp.json()
        answer = result["result"]["alternatives"][0]["message"]["text"]

        # Сохраняем ответ в историю
        history.append({"role": "assistant", "text": answer})
        session["history"] = history

        return jsonify({"answer": answer})

    except Exception as e:
        print(f"[ERROR] {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/reset", methods=["POST"])
def reset():
    session.pop("history", None)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
