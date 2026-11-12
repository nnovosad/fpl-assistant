# fpl-assistant

Скрипт-помощник для подбора трансферов и капитана в официальном
Fantasy Premier League. Берёт ваш текущий состав и статистику напрямую
из официального API fantasy.premierleague.com (без логина, без базы данных),
считает ожидаемые очки (xP) по официальным правилам скоринга FPL и
предлагает лучший вариант трансферов + капитана на ближайший тур.

## Установка

```bash
pip install -r requirements.txt
```

## Настройка

Скопируйте `.env.example` в `.env` и при необходимости укажите:

- `FPL_TEAM_ID` — ID вашей команды (из URL `fantasy.premierleague.com/entry/<ID>/...`).
- `ODDS_API_KEY` — ключ [The Odds API](https://the-odds-api.com/) (опционально,
  уточняет прогноз клиншитов через букмекерские коэффициенты; без ключа скрипт
  работает на статистике FPL).

## Запуск

```bash
python main.py
# или с другим ID команды:
python main.py 7335846
```

## Что внутри (`fpl_assistant/`)

- `config.py` — константы, официальный скоринг FPL (включая defensive contribution).
- `fpl_api.py` — клиент официального FPL API.
- `odds_client.py` — клиент The Odds API с graceful fallback.
- `models.py` — датаклассы Player/Team/Fixture/Recommendation.
- `scoring.py` — расчёт ожидаемых очков (xP) с байесовским сглаживанием.
- `transfers.py` — подсчёт свободных трансферов из публичной истории команды.
- `optimizer.py` — перебор трансферов, выбор старт-11 и капитана.
- `report.py` — форматирование текстового отчёта.
