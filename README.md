# ManejoClima

Plataforma web para manejo de irrigação por balanço hídrico (FAO-56), com dados diários da Open-Meteo.
Cada produtor cadastra suas fazendas, solos, culturas, equipamentos e parcelas, roda o manejo e acompanha o balanço em gráficos.

## Estrutura

| Pasta | O que tem |
|---|---|
| `app/` | Aplicação FastAPI: telas (HTML + Bootstrap), banco (SQLAlchemy) e rotas |
| `calculo/` | Módulos de cálculo em Python: ETo (Penman-Monteith), Open-Meteo e balanço hídrico |
| `tests/` | Testes automáticos (`pytest`) |
| `colab/` | Notebook do Google Colab e os módulos originais usados nele |

## Rodar localmente

```
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Abra http://127.0.0.1:8000. Sem `DATABASE_URL` o app usa um sqlite local (`dev.db`), só para desenvolvimento.
Para dados de demonstração: `python seed_demo.py` (login `demo@exemplo.com`, senha `demo12345`; nunca rodar em produção).

## Testes

```
pytest
```

## Notebook (Colab)

O notebook e os módulos que ele usa estão em [`colab/`](colab/).
