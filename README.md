# Telegram bot for YouTube Shorts and TikTok profiles

Локальный Python-бот на aiogram. Вы запускаете его на своем ПК, отправляете боту ссылку на YouTube-канал/Shorts или TikTok-профиль, выбираете 5 или 10 последних роликов, бот скачивает их через yt-dlp и отправляет в Telegram.

> Используйте бот только для контента, который вы имеете право скачивать, хранить, изменять и публиковать. В проекте нет функций обхода авторских проверок или блокировок платформ.

## Что умеет

- Ссылки YouTube: `https://www.youtube.com/@channel`, `https://www.youtube.com/@channel/shorts`, `https://www.youtube.com/channel/...`
- Ссылки TikTok: `https://www.tiktok.com/@user`
- Выбор 5 или 10 последних видео.
- Переключение качества: `low`, `medium`, `high`.
- Автоудаление временных файлов после отправки.
- Опциональная обработка ваших собственных видео: сжатие и водяной знак, если установлен `ffmpeg`.
- Поддержка `cookies.txt` для аккаунтов/контента, к которому у вас есть доступ.

## Установка в PyCharm

1. Откройте папку проекта `shorts_tiktok_bot` в PyCharm.
2. Создайте виртуальное окружение Python 3.11+.
3. В терминале PyCharm выполните:

```bash
pip install -r requirements.txt
```

4. Скопируйте `.env.example` в `.env`.
5. Создайте бота через Telegram `@BotFather` и вставьте токен в `.env`:

```env
BOT_TOKEN=123456789:YOUR_TOKEN
```

6. Запустите `main.py`.

## Настройки `.env`

```env
BOT_TOKEN=...
MAX_UPLOAD_MB=49
DOWNLOAD_DIR=downloads
DEFAULT_VIDEO_COUNT=5
DEFAULT_QUALITY=medium
CLEANUP_AFTER_SEND=true
YTDLP_COOKIES_FILE=
PROCESS_OWN_VIDEOS=false
WATERMARK_TEXT=
```

`PROCESS_OWN_VIDEOS=true` включает законную обработку ваших собственных роликов: уменьшение размера и, если задан `WATERMARK_TEXT`, добавление водяного знака. Для этого должен быть установлен `ffmpeg`.

## Команды бота

- `/start` - старт и текущие настройки.
- `/settings` - кнопки настроек.
- `/help` - помощь.
- `/cancel` - отменить ожидающую ссылку.

## Как пользоваться

1. Запустите `main.py`.
2. Откройте своего бота в Telegram.
3. Отправьте ссылку на канал/профиль.
4. Нажмите `Download 5` или `Download 10`.

## Если YouTube или TikTok не скачивается

- Обновите yt-dlp:

```bash
pip install -U "yt-dlp[default,curl-cffi]"
```

- Проверьте, что ссылка открывается в браузере.
- Для контента, который доступен только вашему аккаунту, экспортируйте cookies в `cookies.txt` и укажите путь в `YTDLP_COOKIES_FILE`.
- TikTok иногда меняет защиту и может временно требовать обновления yt-dlp.

## Ограничение размера Telegram

Если файл больше `MAX_UPLOAD_MB`, бот не отправит его как видео, а покажет локальный путь и ссылку на исходник. Для коротких роликов обычно хватает качества `medium` или `low`.
