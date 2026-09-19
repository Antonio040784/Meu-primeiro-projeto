import json
import os
import time
import requests
from pathlib import Path

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Defina a variável TELEGRAM_BOT_TOKEN no Railway.")

API = f"https://api.telegram.org/bot{TOKEN}"
BASE_DIR = Path(__file__).resolve().parent
SEED_FILE = BASE_DIR / "knowledge_seed.json"

def load_knowledge():
    if not SEED_FILE.exists():
        return {}
    try:
        with SEED_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("Erro ao carregar knowledge_seed.json:", repr(e))
        return {}

def send_message(chat_id, text):
    requests.post(
        f"{API}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=30,
    ).raise_for_status()

def answer_from_knowledge(text, knowledge):
    t = text.lower().strip()

    if t == "/start":
        return (
            "Olá! Eu sou a Julieta, assistente do Dr. Antônio Vitoriano. "
            "Posso orientar sobre EVOLUT, Check-up Day, NOVA, consultas e cardio-oncologia."
        )

    if t in {"/ajuda", "ajuda", "o que você sabe fazer?", "o que voce sabe fazer?"}:
        return (
            "Posso orientar sobre:\n"
            "• EVOLUT\n"
            "• Check-up Day\n"
            "• NOVA: Treinamentos e Consultoria\n"
            "• organização de consultas\n"
            "• acompanhamento cardio-oncológico\n\n"
            "Também posso registrar orientações do Dr. Antônio quando o modo de treinamento estiver habilitado."
        )

    projects = knowledge.get("projects", {})

    if "evolut" in t:
        info = projects.get("EVOLUT", {})
        desc = info.get("description", "Programa de acompanhamento cardiovascular e metabólico.")
        notes = info.get("notes", [])
        extra = "\n".join(f"• {x}" for x in notes)
        return f"{desc}\n{extra}".strip()

    if "check-up" in t or "check up" in t or "checkup" in t:
        info = projects.get("Check-up Day", {})
        desc = info.get("description", "Programa estruturado de check-up cardiovascular.")
        notes = info.get("notes", [])
        extra = "\n".join(f"• {x}" for x in notes)
        return f"{desc}\n{extra}".strip()

    if "nova" in t and ("trein" in t or "consult" in t or t == "nova"):
        info = projects.get("NOVA", {})
        desc = info.get("description", "NOVA: Treinamentos e Consultoria.")
        notes = info.get("notes", [])
        extra = "\n".join(f"• {x}" for x in notes)
        return f"{desc}\n{extra}".strip()

    if "oncol" in t or "cardiotox" in t or "quimio" in t or "câncer" in t or "cancer" in t:
        return (
            "Pacientes oncológicos, especialmente os expostos a terapias potencialmente cardiotóxicas, "
            "merecem atenção especial e acompanhamento cardio-oncológico conforme orientação médica. "
            "Eu posso ajudar a organizar o contato e o seguimento, mas não substituo avaliação médica."
        )

    if "consulta" in t or "agendar" in t or "marcar" in t:
        guidance = knowledge.get("consultation_plan", {}).get("guidance", [])
        if guidance:
            return "Sobre consultas:\n" + "\n".join(f"• {x}" for x in guidance)
        return "Posso ajudar a organizar solicitações de consulta e retorno com a equipe do Dr. Antônio."

    return (
        "Entendi sua mensagem. Ainda estou em treinamento. "
        "Você pode me perguntar sobre EVOLUT, Check-up Day, NOVA, consultas ou cardio-oncologia."
    )

def main():
    print("Julieta v2 iniciada.")
    knowledge = load_knowledge()
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

                reply = answer_from_knowledge(text, knowledge)
                send_message(chat_id, reply)

        except Exception as e:
            print("Erro:", repr(e))
            time.sleep(5)

if __name__ == "__main__":
    main()
