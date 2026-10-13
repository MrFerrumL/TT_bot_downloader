# TT Bot Downloader

Локальный Telegram-бот на Python и aiogram для загрузки роликов из YouTube Shorts, TikTok и Instagram. Бот запускается на вашем ПК: вы отправляете ссылку, выбираете качество и получаете видео обратно в Telegram.

> Используйте проект только для видео, на которые у вас есть право доступа, скачивания, хранения и публикации. Закрытый контент доступен только при входе в аккаунт, которому разрешён просмотр.

## Возможности

- Загрузка одного ролика по ссылке из YouTube, TikTok или Instagram.
- Загрузка 5 или 10 последних роликов с YouTube-канала или TikTok-профиля.
- Поддержка YouTube Shorts, обычных YouTube-видео, TikTok-видео, Instagram Reels и публикаций.
- Три режима качества: низкое, среднее и высокое.
- Отправка скачанного видео в Telegram с увеличенным тайм-аутом для нестабильной сети.
- Сохранение файлов на ПК, если Telegram не смог принять видео.
- Автоудаление временных файлов после успешной отправки.
- Обработка собственных роликов: сжатие и водяной знак.
- Поддержка cookies из Chrome, Edge, Firefox и других браузеров для аккаунтов, к которым у вас есть доступ.
- Русское меню Telegram: `/start`, `/settings`, `/help`, `/cancel`.

## Поддерживаемые ссылки

```text
https://www.youtube.com/@channel/shorts
https://www.youtube.com/watch?v=VIDEO_ID
https://www.youtube.com/shorts/VIDEO_ID
https://www.tiktok.com/@user
https://www.tiktok.com/@user/video/VIDEO_ID
https://www.instagram.com/reel/POST_ID
https://www.instagram.com/p/POST_ID
```

## Быстрый запуск в Windows

1. Установите Python 3.11 или новее.
2. Откройте папку проекта в PyCharm.
3. Запустите `setup_windows.bat` двойным щелчком или выполните его в терминале PyCharm.
4. Скопируйте `.env.example` в `.env`.
5. Создайте бота через [@BotFather](https://t.me/BotFather) и вставьте его токен в `.env`.
6. Выберите интерпретатор проекта:

```text
.venv\Scripts\python.exe
```

7. Запустите `main.py`.

Можно выполнить установку вручную:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Настройки `.env`

```env
BOT_TOKEN=PASTE_YOUR_BOT_TOKEN_HERE
MAX_UPLOAD_MB=49
DOWNLOAD_DIR=downloads
DEFAULT_VIDEO_COUNT=5
DEFAULT_QUALITY=medium
CLEANUP_AFTER_SEND=true

# Необязательно: cookies.txt для контента, к которому у вас есть доступ.
YTDLP_COOKIES_FILE=

# Необязательно: браузер, в котором вы уже вошли в TikTok/Instagram.
# Примеры: chrome, edge, firefox, brave или chrome:Default
YTDLP_COOKIES_FROM_BROWSER=

# Необязательная обработка собственных роликов.
PROCESS_OWN_VIDEOS=false
WATERMARK_TEXT=

# Необязательно: прокси для соединения бота с Telegram.
TELEGRAM_PROXY=
```

## Как пользоваться

1. Откройте бота в Telegram и отправьте `/start`.
2. Отправьте ссылку на ролик, канал или профиль.
3. Для отдельного ролика нажмите `Скачать видео`.
4. Для профиля или канала выберите 5 или 10 последних видео.
5. Откройте `/settings`, чтобы изменить качество, очистку файлов или водяной знак.

## Доступ к закрытым аккаунтам

TikTok и Instagram могут не отдавать ролики гостевому запросу. Если вы уже вошли в аккаунт через браузер и он имеет доступ к нужному контенту, добавьте в `.env`:

```env
YTDLP_COOKIES_FROM_BROWSER=chrome
```

После изменения перезапустите `main.py`. Бот не обходит приватность аккаунтов и ограничения платформ.

## Ограничение Telegram

По умолчанию бот отправляет файлы до 49 МБ. Если размер видео больше, бот оставит его в папке `downloads` и покажет путь к файлу на ПК.

## Структура проекта

```text
app/
  bot.py          # Telegram-обработчики и интерфейс
  downloader.py   # Работа с yt-dlp
  video_tools.py  # Водяной знак и сжатие
  config.py       # Чтение настроек .env
main.py           # Точка запуска
requirements.txt  # Зависимости Python
```
