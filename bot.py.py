import os
import json
import time
import unicodedata
import uuid
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_ID = os.environ.get("TELEGRAM_ADMIN_ID", "").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
MAX_AUDIO_BYTES = 20 * 1024 * 1024
BOT_VERSION = "Julieta voz 2026-09-23.2"

BASE_DIR = Path(__file__).resolve().parent
SEED_FILE = BASE_DIR / "knowledge_seed.json"
RUNTIME_FILE = BASE_DIR / "knowledge_runtime.json"

if not TOKEN:
    raise RuntimeError("A variável TELEGRAM_BOT_TOKEN não foi configurada.")

API = f"https://api.telegram.org/bot{TOKEN}/"


def api_call(method, data=None, timeout=70):
    data = data or {}
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(API + method, data=encoded)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # A URL do Telegram contém o token; nunca incluí-la nos logs.
        raise RuntimeError(f"Telegram {method}: HTTP {exc.code}") from None


def download_audio(file_id):
    result = api_call("getFile", {"file_id": file_id}).get("result", {})
    if result.get("file_size", 0) > MAX_AUDIO_BYTES:
        raise ValueError("O áudio excede o limite de 20 MB do Telegram.")
    file_path = result.get("file_path", "")
    if not file_path or file_path.startswith("/") or ".." in file_path.split("/"):
        raise ValueError("O Telegram não retornou um caminho de áudio válido.")
    url = f"https://api.telegram.org/file/bot{TOKEN}/{urllib.parse.quote(file_path, safe='/')}"
    try:
        with urllib.request.urlopen(url, timeout=90) as resp:
            content = resp.read(MAX_AUDIO_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Download do áudio: HTTP {exc.code}") from None
    if not content or len(content) > MAX_AUDIO_BYTES:
        raise ValueError("O áudio está vazio ou excede o limite de 20 MB.")
    return content


def transcribe_audio(content, extension):
    if not OPENAI_API_KEY:
        raise RuntimeError("A variável OPENAI_API_KEY não foi configurada.")
    media_types = {
        ".ogg": "audio/ogg", ".mp3": "audio/mpeg", ".m4a": "audio/mp4",
        ".mp4": "audio/mp4", ".wav": "audio/wav", ".webm": "audio/webm",
        ".flac": "audio/flac", ".mpeg": "audio/mpeg", ".mpga": "audio/mpeg",
    }
    if extension not in media_types:
        raise ValueError("Formato de áudio não compatível. Envie uma mensagem de voz ou MP3/M4A.")
    boundary = uuid.uuid4().hex
    prefix = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n"
        "gpt-4o-mini-transcribe\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\npt\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"audio{extension}\"\r\n"
        f"Content-Type: {media_types[extension]}\r\n\r\n"
    ).encode("utf-8")
    body = prefix + content + f"\r\n--{boundary}--\r\n".encode("ascii")
    request = urllib.request.Request(
        "https://api.openai.com/v1/audio/transcriptions", data=body,
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}",
                 "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as resp:
            transcript = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Não registrar corpos de erro ou cabeçalhos que possam conter dados sensíveis.
        raise RuntimeError(f"Transcrição: HTTP {exc.code}") from None
    return str(transcript.get("text", "")).strip()


def handle_audio(chat_id, user_id, audio, voice=False):
    if not is_admin(user_id) or str(chat_id) != str(user_id):
        send_message(chat_id, "Áudio disponível apenas no chat privado do administrador. Use /meuid para configurar o acesso.")
        return
    if not OPENAI_API_KEY:
        send_message(chat_id, "Para ativar os áudios, configure OPENAI_API_KEY no Railway.")
        return
    if audio.get("file_size", 0) > MAX_AUDIO_BYTES:
        send_message(chat_id, "Envie um áudio de até 20 MB.")
        return
    extension = ".ogg" if voice else Path(audio.get("file_name", "")).suffix.lower()
    if not extension:
        extension = {"audio/mpeg": ".mp3", "audio/mp4": ".m4a",
                     "audio/x-m4a": ".m4a", "audio/ogg": ".ogg",
                     "audio/wav": ".wav", "audio/webm": ".webm"}.get(
                         audio.get("mime_type", "").lower(), "")
    try:
        if not audio.get("file_id"):
            raise ValueError("O áudio não veio com um identificador de arquivo.")
        if extension not in (".ogg", ".mp3", ".m4a", ".mp4", ".wav", ".webm", ".flac", ".mpeg", ".mpga"):
            raise ValueError("Formato de áudio não compatível. Envie uma mensagem de voz ou MP3/M4A.")
        transcript = transcribe_audio(download_audio(audio["file_id"]), extension)
    except ValueError as exc:
        send_message(chat_id, str(exc))
        return
    except Exception as exc:
        print(f"Falha ao transcrever áudio: {type(exc).__name__}", flush=True)
        send_message(chat_id, "Não consegui transcrever este áudio. Tente novamente ou envie a mensagem por texto.")
        return
    if not transcript:
        send_message(chat_id, "Não identifiquei fala no áudio. Tente gravar novamente.")
        return
    # Usa as mesmas regras e a mesma base de conhecimento das mensagens escritas.
    handle_text(chat_id, user_id, transcript)


def send_message(chat_id, text):
    text = str(text).strip()
    if not text:
        return
    # Telegram aceita até 4096 caracteres por mensagem.
    chunks = [text[i:i+3900] for i in range(0, len(text), 3900)]
    for chunk in chunks:
        api_call("sendMessage", {
            "chat_id": chat_id,
            "text": chunk
        })


def normalize(text):
    text = str(text or "").lower()
    text = "".join(
        ch for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )
    return " ".join(text.split())


def load_json(path, default):
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as exc:
        print(f"Erro ao ler {path.name}: {exc}", flush=True)
    return default


def save_json(path, data):
    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as exc:
        print(f"Erro ao salvar {path.name}: {exc}", flush=True)
        return False


seed = load_json(SEED_FILE, {})
runtime = load_json(RUNTIME_FILE, {"ensinamentos": []})


def refresh_knowledge():
    global seed, runtime
    seed = load_json(SEED_FILE, {})
    runtime = load_json(RUNTIME_FILE, {"ensinamentos": []})


def flatten(obj, path=""):
    """Transforma qualquer JSON em pares (caminho, texto), sem exigir um formato específico."""
    rows = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_path = f"{path} > {k}" if path else str(k)
            rows.extend(flatten(v, new_path))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            rows.extend(flatten(item, path))
    else:
        value = str(obj).strip()
        if value:
            rows.append((path, value))
    return rows


def pretty_node(obj, title=None, level=0):
    """Converte um trecho do JSON em texto legível."""
    lines = []
    if title:
        lines.append(str(title))
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                lines.append(f"\n{k}:")
                nested = pretty_node(v, None, level + 1)
                if nested:
                    lines.append(nested)
            else:
                lines.append(f"• {k}: {v}")
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                nested = pretty_node(item, None, level + 1)
                if nested:
                    lines.append(nested)
            else:
                lines.append(f"• {item}")
    else:
        lines.append(str(obj))
    return "\n".join(lines).strip()


def find_direct_topic(query, obj):
    """Tenta achar primeiro um tópico pelo nome da chave, como EVOLUT, NOVA ou Check-up Day."""
    nq = normalize(query)
    if isinstance(obj, dict):
        for key, value in obj.items():
            nk = normalize(key)
            if nk and (nk in nq or nq in nk):
                return key, value
        for key, value in obj.items():
            found = find_direct_topic(query, value)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = find_direct_topic(query, item)
            if found:
                return found
    return None


STOPWORDS = {
    "a","o","as","os","um","uma","uns","umas","de","da","do","das","dos","e","em",
    "no","na","nos","nas","para","por","com","que","qual","quais","me","voce","voces",
    "sabe","sobre","isso","essa","esse","isto","como","eu","meu","minha","meus","minhas",
    "julieta","doutor","antonio","dr"
}


def useful_tokens(query):
    return [
        t for t in normalize(query).replace("?", " ").replace("!", " ").split()
        if len(t) >= 3 and t not in STOPWORDS
    ]


def search_knowledge(query):
    refresh_knowledge()

    # 1) Busca pelo nome exato/semelhante de um tópico.
    direct = find_direct_topic(query, seed)
    if direct:
        key, value = direct
        return pretty_node(value, title=key)

    # 2) Busca pelos ensinamentos feitos no Telegram.
    tokens = useful_tokens(query)
    learned_hits = []
    for item in runtime.get("ensinamentos", []):
        blob = normalize(f"{item.get('tema','')} {item.get('texto','')}")
        score = sum(1 for t in tokens if t in blob)
        if score:
            learned_hits.append((score, item))
    learned_hits.sort(key=lambda x: x[0], reverse=True)

    # 3) Busca em qualquer parte do knowledge_seed.json.
    rows = flatten(seed)
    hits = []
    for path, value in rows:
        blob = normalize(f"{path} {value}")
        score = sum(1 for t in tokens if t in blob)
        if score:
            hits.append((score, path, value))
    hits.sort(key=lambda x: x[0], reverse=True)

    parts = []
    for _, item in learned_hits[:3]:
        tema = item.get("tema", "Ensinamento")
        texto = item.get("texto", "")
        parts.append(f"{tema}: {texto}")

    seen = set()
    for _, path, value in hits:
        marker = (path, value)
        if marker in seen:
            continue
        seen.add(marker)
        parts.append(f"{path}: {value}" if path else value)
        if len(parts) >= 6:
            break

    if parts:
        return "\n".join(f"• {p}" for p in parts)

    return (
        "Ainda não encontrei essa informação na minha base. "
        "O Dr. Antônio pode me ensinar usando /ensinar tema: informação."
    )


def is_admin(user_id):
    if not ADMIN_ID:
        return False
    return str(user_id) == ADMIN_ID


def handle_text(chat_id, user_id, text):
    raw = (text or "").strip()
    cmd = raw.split()[0].lower() if raw else ""

    if cmd == "/versao":
        send_message(chat_id, BOT_VERSION)
        return

    if cmd in ("/start", "/start@julietadrantoniobot"):
        send_message(
            chat_id,
            "Olá! Eu sou a Julieta, assistente do Dr. Antônio Vitoriano. "
            "Estou online e já consigo consultar a minha base de informações.\n\n"
            "Você pode perguntar, por exemplo:\n"
            "• O que você sabe sobre o EVOLUT?\n"
            "• O que é o Check-up Day?\n"
            "• O que é a NOVA?\n\n"
            "O administrador também pode enviar áudio no chat privado.\n"
            "Para o Dr. Antônio: /meuid mostra o ID necessário para liberar o modo de treinamento."
        )
        return

    if cmd == "/ajuda":
        send_message(
            chat_id,
            "Comandos:\n"
            "/start — iniciar\n"
            "/ajuda — mostrar ajuda\n"
            "/meuid — mostrar seu ID do Telegram\n"
            "/versao — conferir o código ativo\n"
            "Áudios — disponíveis no chat privado do administrador\n"
            "/ensinar tema: informação — ensinar algo novo (somente administrador)\n"
            "/aprendido — listar os últimos ensinamentos (somente administrador)"
        )
        return

    if cmd == "/meuid":
        send_message(
            chat_id,
            f"Seu Telegram ID é: {user_id}\n\n"
            "No Railway, crie a variável TELEGRAM_ADMIN_ID com esse número para liberar o /ensinar somente para você."
        )
        return

    if raw.lower().startswith("/ensinar"):
        if not is_admin(user_id):
            send_message(
                chat_id,
                "O modo de treinamento ainda não está liberado para este usuário. "
                "Envie /meuid e configure esse número no Railway como TELEGRAM_ADMIN_ID."
            )
            return

        content = raw[len("/ensinar"):].strip()
        if ":" not in content:
            send_message(
                chat_id,
                "Use assim:\n/ensinar EVOLUT: informação que você quer que eu aprenda"
            )
            return

        tema, texto_novo = content.split(":", 1)
        tema = tema.strip()
        texto_novo = texto_novo.strip()

        if not tema or not texto_novo:
            send_message(
                chat_id,
                "Faltou o tema ou a informação. Exemplo:\n"
                "/ensinar EVOLUT: acompanhamento estruturado do paciente."
            )
            return

        runtime.setdefault("ensinamentos", []).append({
            "tema": tema,
            "texto": texto_novo,
            "autor_id": str(user_id),
            "timestamp": int(time.time())
        })

        if save_json(RUNTIME_FILE, runtime):
            send_message(
                chat_id,
                f"Aprendi sobre {tema}: {texto_novo}\n\n"
                "Observação: esse aprendizado fica no armazenamento local do serviço e pode ser perdido se o Railway recriar o container. "
                "Depois podemos ligar uma base persistente para não perder nada."
            )
        else:
            send_message(chat_id, "Não consegui salvar esse ensinamento agora.")
        return

    if cmd == "/aprendido":
        if not is_admin(user_id):
            send_message(chat_id, "Esse comando é exclusivo do administrador.")
            return
        items = runtime.get("ensinamentos", [])
        if not items:
            send_message(chat_id, "Ainda não há ensinamentos adicionais salvos.")
            return
        last = items[-10:]
        text_out = "\n".join(
            f"• {x.get('tema','')}: {x.get('texto','')}" for x in last
        )
        send_message(chat_id, "Últimos ensinamentos:\n" + text_out)
        return

    # Não realiza diagnóstico, prescrição ou conduta clínica.
    medical_terms = (
        "diagnostico", "prescreva", "prescricao", "dose", "posologia",
        "tratamento para", "qual remedio", "qual medicamento"
    )
    nraw = normalize(raw)
    if any(term in nraw for term in medical_terms):
        send_message(
            chat_id,
            "Posso ajudar com informações administrativas e com a base do Dr. Antônio, "
            "mas não devo dar diagnóstico, prescrição ou definir conduta médica pelo Telegram. "
            "Posso orientar o contato com a equipe."
        )
        return

    answer = search_knowledge(raw)
    send_message(chat_id, answer)


def main():
    print("Julieta iniciada.", flush=True)
    offset = None

    while True:
        try:
            params = {"timeout": 50}
            if offset is not None:
                params["offset"] = offset

            result = api_call("getUpdates", params, timeout=60)

            for update in result.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message") or update.get("edited_message")
                if not msg:
                    continue

                chat = msg.get("chat", {})
                sender = msg.get("from", {})
                text = msg.get("text")

                if text:
                    handle_text(chat.get("id"), sender.get("id"), text)
                elif msg.get("voice"):
                    handle_audio(chat.get("id"), sender.get("id"), msg["voice"], voice=True)
                elif msg.get("audio"):
                    handle_audio(chat.get("id"), sender.get("id"), msg["audio"])

        except Exception as exc:
            print(f"Erro no loop: {exc}", flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
