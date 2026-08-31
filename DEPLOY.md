# Запуск SAQ через Docker (self-hosted)

Ты запускаешь сам, одной командой на своей машине/сервере — никакого облака и автодеплоя.

## 1. Подготовь `.env`

```bash
cp .env.example .env
```

Открой `.env`, обязательно заполни `ANTHROPIC_API_KEY` (без него не работает Aqyl) и `JWT_SECRET` (сгенерируй: `python -c "import secrets; print(secrets.token_hex(32))"`). Остальное — опционально, см. комментарии в файле.

## 2. Собери и запусти

```bash
docker compose up --build -d
```

Первая сборка — пару минут (Python-зависимости + Next.js build). Дальше `docker compose up -d` стартует мгновенно.

- Сайт: `http://localhost:3000` (или `http://<IP-сервера>:3000`, если запускаешь не на локальной машине)
- API напрямую: `http://localhost:8000`

## 3. Сделай себя админом

Первый зарегистрированный пользователь через `/register` в UI, затем:

```bash
curl -X POST http://localhost:8000/admin/bootstrap -H "Authorization: Bearer <твой JWT после логина>"
```

(Эндпоинт одноразовый — сработает только пока в базе нет ни одного админа.)

## 4. Что не входит в контейнер (по умолчанию выключено)

`ENABLE_DARKNET_SEARCH`, `ENABLE_LOCAL_SEARXNG`, `ENABLE_CERTSTREAM_WATCHER` — требуют vendor/OnionClaw, vendor/searxng, vendor/certstream-server-go как отдельные процессы с Tor/своими зависимостями. Без них SAQ работает на всех бесплатных публичных источниках (OpenSanctions, DuckDuckGo, SEC EDGAR, GLEIF, реестры, блэклист АФМ РК). Включать — по README.md, раздел "Даркнет-модуль" / "Свой SearXNG".

## 5. Данные

SQLite-база и кэши живут в Docker volume `saq-data` — переживают `docker compose down` (но не `docker compose down -v`). Бэкап:

```bash
docker run --rm -v saq_saq-data:/data -v "$PWD":/backup alpine tar czf /backup/saq-data-backup.tar.gz -C /data .
```

## 6. Открыть доступ извне (для жюри/друзей)

Контейнеры слушают `0.0.0.0`, так что если у сервера есть публичный IP — просто открой порт 3000 в файрволе/роутере (port forwarding), либо прокинь через Cloudflare Tunnel / ngrok, если сервер за NAT (домашний ПК). Отдельно настраивать ничего в самом SAQ не нужно.
