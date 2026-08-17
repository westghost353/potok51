# Runbook: развёртывание «Поток 51» на сервере

Развёртывание — Docker Compose под управлением systemd. Юнит поднимает
сервис при загрузке машины, healthcheck перезапускает контейнер при зависании.

Правила этого проекта продиктованы отказами предыдущей инфраструктуры:
деплой только через git (никакого ручного rsync), сервисы только через systemd
(никакого `nohup`), секреты только в `.env` вне репозитория, логи с ротацией.

---

## 1. Предварительные требования

```bash
docker --version && docker compose version
```

Если Docker не установлен (Ubuntu 22.04/24.04):

```bash
curl -fsSL https://get.docker.com | sh
```

Проверить, что на машине есть swap — без него сборка образа на инстансе
с 1 ГБ памяти падает:

```bash
free -h
```

Если swap отсутствует:

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile && echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 2. Первая установка

```bash
sudo mkdir -p /opt/potok51 && sudo chown "$USER" /opt/potok51
git clone git@github.com:<владелец>/<репозиторий>.git /opt/potok51
```

Remote обязан быть SSH. HTTPS-remote с токеном в URL запрещён.

```bash
cp /opt/potok51/deploy/.env.example /opt/potok51/deploy/.env
```

Заполнить `.env`: задать `POTOK51_PORT` и пароль `POTOK51_BASIC_PASSWORD`.
Пустой пароль отключает авторизацию — допустимо только если порт закрыт
снаружи.

```bash
cd /opt/potok51/deploy && docker compose up -d --build
curl -s localhost:8051/healthz
```

## 3. Автозапуск через systemd

```bash
sudo cp /opt/potok51/deploy/potok51.service /etc/systemd/system/potok51.service
sudo systemctl daemon-reload && sudo systemctl enable --now potok51
systemctl status potok51 --no-pager
```

## 3a. Публикация за обратным прокси

Контейнер слушает только петлевой интерфейс (`127.0.0.1:${POTOK51_PORT}`),
наружу сервис отдаёт обратный прокси. Если сервис публикуется не в корне
домена, а под префиксом, префикс обязан быть указан приложению переменной
`POTOK51_BASE_PATH` — иначе редиректы и ссылки в интерфейсе уведут браузер
в корень домена.

Caddy, публикация под путём `/potok51/`:

```
example.org {
    handle_path /potok51/* {
        reverse_proxy 127.0.0.1:8051
    }
}
```

В `deploy/.env` при этом должно быть:

```
POTOK51_BASE_PATH=/potok51
```

Директива `handle_path` срезает префикс до приложения, поэтому маршруты
внутри сервиса остаются корневыми. Блок с префиксом размещается **выше**
общего `handle` того же сайта, иначе он не сработает.

nginx-эквивалент:

```
location /potok51/ {
    proxy_pass http://127.0.0.1:8051/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

## 4. Обновление версии

```bash
cd /opt/potok51 && git pull && sudo systemctl reload potok51
```

`reload` пересобирает образ и поднимает контейнер. Данные лежат на именованном
томе `potok51_data` и пересборку переживают.

## 5. Откат

```bash
cd /opt/potok51 && git log --oneline -10
git checkout <хеш> && sudo systemctl reload potok51
```

## 6. Диагностика

| Симптом | Команда | Что смотреть |
|---------|---------|--------------|
| Сервис не отвечает | `docker compose ps` | статус `healthy` |
| Ошибки приложения | `docker compose logs --tail=200 potok51` | трассировки |
| Занято место | `docker system df` | старые образы, `docker image prune -f` |
| Разбор файла падает | логи, строка `ReadError` | формат карточки |
| Юнит не стартует | `journalctl -u potok51 -n 100 --no-pager` | ошибки Compose |

## 7. Резервное копирование

```bash
docker run --rm -v potok51_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/potok51-data-$(date +%F).tar.gz -C /data .
```

Восстановление:

```bash
docker run --rm -v potok51_data:/data -v "$PWD":/backup alpine \
  sh -c "cd /data && tar xzf /backup/potok51-data-YYYY-MM-DD.tar.gz"
```

## 8. Чек-лист приёмки

1. `systemctl status potok51` — active (running).
2. `curl -s localhost:${POTOK51_PORT}/healthz` — `{"status":"ok",...}`.
3. Загрузка синтетического профиля через веб-форму — отчёт открывается.
4. `sudo reboot`, после загрузки повторить пункты 1–2 — сервис поднялся сам.
5. `docker compose logs --tail=5` — записи есть, файл логов ротируется
   (`max-size 10m`, `max-file 5`).
6. `docker compose down && docker compose up -d` — ранее сделанные анализы
   на месте.

## 9. Безопасность

Сервис обрабатывает карточки счетов, содержащие коммерческую тайну клиента.

- Приложение не делает исходящих сетевых запросов; при желании контейнер можно
  запускать с `network_mode` без доступа наружу.
- Файлы клиентов остаются на томе `potok51_data`. Срок хранения задаёт
  владелец: при необходимости добавить cron-очистку старше N дней.
- Публиковать порт наружу без Basic-авторизации и TLS нельзя. Рекомендуется
  reverse proxy (Caddy или nginx) с сертификатом.
