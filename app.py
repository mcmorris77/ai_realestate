import os
import time
import json
import requests
from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = "rieltpro-secret-2026"

API_KEY      = os.getenv("YANDEX_API_KEY")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")
FOLDER_ID    = os.getenv("FOLDER_ID")
BASE_URL     = "https://rest-assistant.api.cloud.yandex.net/assistants/v1"


def headers():
    return {
        "Authorization": f"Api-Key {API_KEY}",
        "Content-Type": "application/json",
        "x-folder-id": FOLDER_ID
    }


def parse_response(resp):
    """Парсим ответ — API иногда возвращает несколько JSON строк (NDJSON)"""
    text = resp.text.strip()
    # Берём первую непустую строку
    for line in text.splitlines():
        line = line.strip()
        if line:
            return json.loads(line)
    return {}


def create_thread():
    resp = requests.post(f"{BASE_URL}/threads", headers=headers(), json={
        "folderId": FOLDER_ID
    })
    resp.raise_for_status()
    data = parse_response(resp)
    thread_id = data["id"]
    print(f"[OK] Тред создан: {thread_id}")
    return thread_id


def send_message(thread_id, text):
    resp = requests.post(f"{BASE_URL}/messages", headers=headers(), json={
        "threadId": thread_id,
        "role": "USER",
        "content": {
            "content": [
                {"type": "TEXT", "text": {"content": text}}
            ]
        }
    })
    resp.raise_for_status()
    print(f"[OK] Сообщение отправлено")


def run_assistant(thread_id):
    resp = requests.post(f"{BASE_URL}/runs", headers=headers(), json={
        "threadId": thread_id,
        "assistantId": ASSISTANT_ID
    })
    resp.raise_for_status()
    data = parse_response(resp)
    run_id = data["id"]
    print(f"[OK] Run запущен: {run_id}")
    return run_id


def wait_for_result(run_id, max_wait=60):
    for i in range(max_wait):
        resp = requests.get(f"{BASE_URL}/runs/{run_id}", headers=headers())
        resp.raise_for_status()
        data = parse_response(resp)
        status = data.get("state", {}).get("status", "UNKNOWN")
        print(f"[wait] попытка {i+1}: status={status}")
        if status in ("COMPLETED", "SUCCEEDED"):
            return
        elif status in ("FAILED", "CANCELLED", "ERROR"):
            raise Exception(f"Run завершился с ошибкой: {status}")
        time.sleep(1)
    raise Exception("Агент не ответил за 60 секунд")


def get_last_message(thread_id):
    resp = requests.get(
        f"{BASE_URL}/messages",
        headers=headers(),
        params={"threadId": thread_id}
    )
    resp.raise_for_status()

    # API возвращает NDJSON — несколько JSON-объектов построчно
    # Парсим ВСЕ строки и ищем сообщение ассистента
    all_messages = []
    for line in resp.text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            # Каждая строка может быть отдельным сообщением или обёрткой
            if "result" in obj:
                all_messages.append(obj["result"])
            elif "messages" in obj:
                all_messages.extend(obj["messages"])
            elif obj.get("author", {}).get("role") or obj.get("role"):
                all_messages.append(obj)
        except Exception:
            continue

    print(f"[messages] всего найдено: {len(all_messages)}")

    # Ищем последнее сообщение ассистента
    for msg in reversed(all_messages):
        role = msg.get("author", {}).get("role") or msg.get("role", "")
        if role == "ASSISTANT":
            parts = msg.get("content", {}).get("content", [])
            for part in parts:
                if part.get("text"):
                    text = part["text"].get("content", "")
                    if text:
                        return text

    return "Агент не дал ответа"


@app.route("/")
def index():
    session.pop("thread_id", None)
    return render_template("index.html")


@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json()
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "Пустой вопрос"}), 400
    try:
        thread_id = session.get("thread_id")
        if not thread_id:
            thread_id = create_thread()
            session["thread_id"] = thread_id
        send_message(thread_id, user_message)
        run_id = run_assistant(thread_id)
        wait_for_result(run_id)
        answer = get_last_message(thread_id)
        return jsonify({"answer": answer})
    except Exception as e:
        print(f"[ERROR] {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/reset", methods=["POST"])
def reset():
    session.pop("thread_id", None)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
