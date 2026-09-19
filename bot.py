import json
import os
import time
import requests
from pathlib import Path

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not TOKEN:
    raise RuntimeError("Defina a variável TELEGRAM_BOT_TOKEN no Railway.")

if not OPENAI_API_KEY:
    raise RuntimeError("Defina a variável OPENAI_API_KEY no Railway.")

API = f"https://api.telegram.org/bot{TOKEN}"
FILE_API = f"https://api.telegram.org/file/bot{TOKEN}"

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
        json={
            "chat_id": chat_id,
            "text": text
        },
        timeout=30,
    ).raise_for_status()


def transcribe_voice(file_id):
    # Descobre onde o Telegram armazenou o áudio
    r = requests.get(
        f"{API}/getFile",
        params={"file_id": file_id},
        timeout=30,
    )
    r.raise_for_status()

    file_path = r.json()["result"]["file_path"]

    # Baixa o áudio do Telegram
    audio = requests.get(
        f"{FILE_API}/{file_path}",
        timeout=60,
    )
    audio.raise_for_status()

    # Envia o áudio para a OpenAI transcrever
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }

    files = {
        "file": (
            "voz.ogg",
            audio.content,
            "audio/ogg"
        )
    }

    data = {
        "model": "gpt-4o-mini-transcribe",
        "language": "pt"
    }

    response = requests.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers=headers,
        files=files,
        data=data,
        timeout=120,
    )

    response.raise_for_status()

    result = response.json()

    return (result.get("text") or "").strip()


def answer_from_knowledge(text, knowledge):
    t = text.lower().strip()

    if t == "/start":
        return (
            "Olá! Eu sou Julieta, assistente do Dr. Antônio Vitoriano. "
            "Posso orientar sobre EVOLUT, Check-up Day, NOVA, consultas "
            "e cardio-oncologia. Você também pode falar comigo por áudio."
        )

    if t in {
        "/ajuda",
        "ajuda",
        "o que você sabe fazer?",
        "o que voce sabe fazer?"
    }:
        return (
            "Posso orientar sobre:\n"
            "• EVOLUT\n"
            "• Check-up Day\n"
            "• NOVA: Treinamentos e Consultoria\n"
            "• organização de consultas\n"
            "• acompanhamento cardio-oncológico\n\n"
            "Você pode escrever ou me enviar uma mensagem de voz."
        )

    projects = knowledge.get("projects", {})

    if "evolut" in t:
        info = projects.get("EVOLUT", {})
        desc = info.get(
            "description",
            "Programa de acompanhamento cardiovascular e metabólico."
        )
        notes = info.get("notes", [])
        extra = "\n".join(f"• {x}" for x in notes)
        return f"{desc}\n{extra}".strip()

    if "check-up" in t or "check up" in t or "checkup" in t:
        info = projects.get("Check-up Day", {})
        desc = info.get(
            "description",
            "Programa estruturado de check-up cardiovascular."
        )
        notes = info.get("notes", [])
        extra = "\n".join(f"• {x}" for x in notes)
        return f"{desc}\n{extra}".strip()

    if "nova" in t and (
        "trein" in t
        or "consult" in t
        or t == "nova"
    ):
        info = projects.get("NOVA", {})
        desc = info.get(
            "description",
            "NOVA: Treinamentos e Consultoria."
        )
        notes = info.get("notes", [])
        extra = "\n".join(f"• {x}" for x in notes)
        return f"{desc}\n{extra}".strip()

    if (
        "oncol" in t
        or "cardiotox" in t
        or "quimio" in t
        or "câncer" in t
        or "cancer" in t
    ):
        return (
            "Pacientes oncológicos, especialmente os expostos a terapias "
            "potencialmente cardiotóxicas, merecem atenção especial e "
            "acompanhamento cardio-oncológico conforme orientação médica. "
            "Eu posso ajudar a organizar o contato e o seguimento, "
            "mas não substituo avaliação médica."
        )

    if "consulta" in t or "agendar" in t or "marcar" in t:
        guidance = knowledge.get(
            "consultation_plan",
            {}
        ).get("guidance", [])

        if guidance:
            return (
                "Sobre consultas:\n"
                + "\n".join(f"• {x}" for x in guidance)
            )

        return (
            "Posso ajudar a organizar solicitações de consulta "
            "e retorno com a equipe do Dr. Antônio."
        )

    return (
        "Entendi sua mensagem. Ainda estou em treinamento. "
        "Você pode me perguntar sobre EVOLUT, Check-up Day, "
        "NOVA, consultas ou cardio-oncologia."
    )


def main():
    print("Julieta v3 com áudio iniciada.")

    knowledge = load_knowledge()
    offset = None

    while True:
        try:
            params = {"timeout": 30}

            if offset is not None:
                params["offset"] = offset

            r = requests.get(
                f"{API}/getUpdates",
                params=params,
                timeout=40,
            )

            r.raise_for_status()
            data = r.json()

            for update in data.get("result", []):
                offset = update["update_id"] + 1

                message = update.get("message") or {}
                chat = message.get("chat") or {}
                chat_id = chat.get("id")

                if not chat_id:
                    continue

                # Mensagem escrita
                text = (message.get("text") or "").strip()

                if text:
                    reply = answer_from_knowledge(
                        text,
                        knowledge
                    )

                    send_message(
                        chat_id,
                        reply
                    )

                    continue

                # Mensagem de voz do Telegram
                voice = message.get("voice")

                if voice:
                    try:
                        file_id = voice.get("file_id")

                        send_message(
                            chat_id,
                            "🎤 Recebi seu áudio. Um instante..."
                        )

                        transcription = transcribe_voice(file_id)

                        if not transcription:
                            send_message(
                                chat_id,
                                "Não consegui entender esse áudio. "
                                "Pode tentar novamente?"
                            )
                            continue

                        print(
                            "Áudio transcrito:",
                            transcription
                        )

                        reply = answer_from_knowledge(
                            transcription,
                            knowledge
                        )

                        send_message(
                            chat_id,
                            reply
                        )

                    except Exception as e:
                        print(
                            "Erro ao processar áudio:",
                            repr(e)
                        )

                        send_message(
                            chat_id,
                            "Não consegui processar seu áudio agora. "
                            "Pode tentar novamente em alguns instantes."
                        )

        except Exception as e:
            print("Erro:", repr(e))
            time.sleep(5)


if __name__ == "__main__":
    main()