# AI Cost Governor — Backend

One image, three roles:

| Role | Command |
|---|---|
| gateway (proxy + admin API) | `uvicorn app.main:app --port 8000` |
| usage-worker | `python -m app.workers.usage_worker` |
| alert-worker | `python -m app.workers.alert_worker` |

The settings live in `.env`; see `app/config.py` and `docs/DISTRIBUTED_SYSTEMS.md`
for what each one does. Without `REDIS_URL` the gateway runs alone in `sync` mode.

```bash
pip install -r requirements-dev.txt
python seed_data.py            # demo org, admin@test.com / demo123
uvicorn app.main:app --reload --port 8000
python -m pytest -q
```
