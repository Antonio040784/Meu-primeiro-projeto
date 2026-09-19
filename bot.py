import os
import time
import requests

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Defina a variável TELEGRAM_BOT_TOKEN no Railway.")

API = f"https://api.telegram.org/bot{TOKEN}"

def send_message(chat_id, text):
    requests.post(
        f"{API}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=30,
    ).raise_for_status()

def main():
    print("JulietaBot iniciado.")
    offset = None

    while True:
        try:
            params = {"timeout": 30}
            if offset is not None:
                params["offset"] = offset

            r = requests.get(f"{API}/getUpdates", params=params, timeout=40)
            r.raise_for_status()
            data = r.json()

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                message = update.get("message") or {}
                chat = message.get("chat") or {}
                chat_id = chat.get("id")
                text = (message.get("text") or "").strip()

                if not chat_id or not text:
                    continue

                if text == "/start":
                    reply = (
                        "Olá! Eu sou a Julieta, assistente do Dr. Antônio Vitoriano. "
                        "Estou online e funcionando."
                    )
                else:
                    reply = f"Recebi sua mensagem: {text}"

                send_message(chat_id, reply)

        except Exception as e:
            print("Erro:", repr(e))
            time.sleep(5)

if __name__ == "__main__":
    main()
