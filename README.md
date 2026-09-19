# JulietaBot

Bot básico do Telegram pronto para deploy no Railway.

## Arquivos
- `bot.py`: código do bot
- `requirements.txt`: dependência Python
- `railway.json`: comando de inicialização no Railway

## Configuração no Railway
Crie uma variável de ambiente:

`TELEGRAM_BOT_TOKEN=SEU_TOKEN_NOVO_DO_BOTFATHER`

IMPORTANTE: não coloque o token diretamente no código nem envie o token para o GitHub.

Depois do deploy, envie `/start` para o bot no Telegram.
