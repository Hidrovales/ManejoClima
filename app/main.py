import datetime
import os

import bcrypt
import requests
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from calculo.open_meteo import buscar_coordenadas

from .db import Base, engine, get_db
from .manejo import rodar_manejo, taxa_aplicacao
from .models import Camada, Cultura, Equipamento, FaseCultura, Fazenda, Lancamento, Parcela, Solo, User

# shortcut: create_all em vez de Alembic, adotar migrations quando o schema começar a mudar
Base.metadata.create_all(engine)

app = FastAPI(title="ManejoClima")
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SECRET_KEY", "dev-inseguro"), https_only=os.getenv("COOKIE_SECURE") == "1")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))


def render(request: Request, nome: str, **ctx):
    return templates.TemplateResponse(request, nome, ctx)


def usuario_atual(request: Request, db: Session = Depends(get_db)) -> User | None:
    uid = request.session.get("uid")
    return db.get(User, uid) if uid else None


def exige_login(user: User | None = Depends(usuario_atual)) -> User:
    if user is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


@app.get("/cadastro")
def cadastro_form(request: Request):
    return render(request, "cadastro.html", erro=None)


@app.post("/cadastro")
def cadastro(request: Request, nome: str = Form(...), email: str = Form(...), senha: str = Form(...),
             senha2: str = Form(...), db: Session = Depends(get_db)):
    email = email.strip().lower()
    erro = None
    if not nome.strip() or not email or not senha:
        erro = "Preencha todos os campos."
    elif len(senha) < 8:
        erro = "A senha precisa ter ao menos 8 caracteres."
    elif senha != senha2:
        erro = "As senhas não coincidem."
    elif db.scalar(select(User).where(User.email == email)):
        erro = "E-mail já cadastrado."
    if erro:
        return render(request, "cadastro.html", erro=erro)
    user = User(nome=nome.strip(), email=email, senha_hash=bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode())
    db.add(user)
    db.commit()
    request.session["uid"] = user.id
    return RedirectResponse("/", status_code=303)


@app.get("/login")
def login_form(request: Request):
    return render(request, "login.html", erro=None)


@app.post("/login")
def login(request: Request, email: str = Form(...), senha: str = Form(...), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if not user or not bcrypt.checkpw(senha.encode(), user.senha_hash.encode()):
        return render(request, "login.html", erro="E-mail ou senha inválidos.")
    request.session["uid"] = user.id
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/")
def home(request: Request, user: User = Depends(exige_login)):
    return render(request, "fazendas.html", user=user, fazendas=user.fazendas, erro=None)


@app.post("/fazendas")
def criar_fazenda(request: Request, nome: str = Form(...), proprietario: str = Form(""), estado: str = Form(""),
                  cidade: str = Form(""), latitude: float | None = Form(None), longitude: float | None = Form(None),
                  altitude: float | None = Form(None), user: User = Depends(exige_login), db: Session = Depends(get_db)):
    if not nome.strip():
        return render(request, "fazendas.html", user=user, fazendas=user.fazendas, erro="Informe o nome da fazenda.")
    if latitude is not None and not -90 <= latitude <= 90 or longitude is not None and not -180 <= longitude <= 180:
        return render(request, "fazendas.html", user=user, fazendas=user.fazendas, erro="Latitude/longitude fora do intervalo válido.")
    db.add(Fazenda(user_id=user.id, nome=nome.strip(), proprietario=proprietario.strip() or None,
                   estado=estado.strip() or None, cidade=cidade.strip() or None,
                   latitude=latitude, longitude=longitude, altitude=altitude))
    db.commit()
    return RedirectResponse("/", status_code=303)


@app.get("/api/coordenadas")
def coordenadas(cidade: str, user: User = Depends(exige_login)):
    try:
        return buscar_coordenadas(cidade)
    except ValueError as e:
        return JSONResponse({"erro": str(e)}, status_code=404)
    except Exception:
        return JSONResponse({"erro": "Falha ao consultar o serviço de geocodificação."}, status_code=502)


def pagina_solos(request: Request, user: User, erro: str | None = None):
    solos = [s for f in user.fazendas for s in f.solos]
    return render(request, "solos.html", user=user, fazendas=user.fazendas, solos=solos, erro=erro)


@app.get("/solos")
def solos(request: Request, user: User = Depends(exige_login)):
    return pagina_solos(request, user)


@app.post("/solos")
def criar_solo(request: Request, fazenda_id: int = Form(...), nome: str = Form(...), espessura: list[float] = Form(...),
               theta_fc: list[float] = Form(...), theta_wp: list[float] = Form(...),
               user: User = Depends(exige_login), db: Session = Depends(get_db)):
    if fazenda_id not in {f.id for f in user.fazendas}:  # só fazendas do próprio usuário
        return pagina_solos(request, user, "Fazenda inválida.")
    if not nome.strip():
        return pagina_solos(request, user, "Informe o nome do solo.")
    if not len(espessura) == len(theta_fc) == len(theta_wp):
        return pagina_solos(request, user, "Preencha todos os campos de cada camada.")
    for i, (e, fc, wp) in enumerate(zip(espessura, theta_fc, theta_wp), 1):
        if e <= 0:
            return pagina_solos(request, user, f"Camada {i}: a espessura deve ser maior que zero.")
        if not 0 < wp < fc <= 1:
            return pagina_solos(request, user, f"Camada {i}: use 0 < ponto de murcha < capacidade de campo ≤ 1 (m³/m³).")
    db.add(Solo(fazenda_id=fazenda_id, nome=nome.strip(),
                camadas=[Camada(espessura=e, theta_fc=fc, theta_wp=wp) for e, fc, wp in zip(espessura, theta_fc, theta_wp)]))
    db.commit()
    return RedirectResponse("/solos", status_code=303)


def pagina_culturas(request: Request, user: User, erro: str | None = None):
    culturas = [c for f in user.fazendas for c in f.culturas]
    return render(request, "culturas.html", user=user, fazendas=user.fazendas, culturas=culturas, fases=FASES, erro=erro)


@app.get("/culturas")
def culturas(request: Request, user: User = Depends(exige_login)):
    return pagina_culturas(request, user)


@app.post("/culturas")
# shortcut: async só para ler o form; as consultas síncronas bloqueiam o loop, ok para poucos usuários
async def criar_cultura(request: Request, user: User = Depends(exige_login), db: Session = Depends(get_db)):
    f = await request.form()

    def erro(msg):
        return pagina_culturas(request, user, msg)

    def num(v):
        return float(v) if v not in (None, "") else None

    try:
        fazenda_id, p = int(f["fazenda_id"]), float(f["p"])
        fases = {k: {"duracao": int(f[f"dur_{k}"]), "kc": num(f.get(f"kc_{k}")), "z": num(f.get(f"z_{k}")),
                     "area_sombreada": num(f.get(f"area_{k}")), "constante": f.get(f"const_{k}") == "on"}
                 for k in FASES}
    except (KeyError, ValueError):
        return erro("Preencha todos os campos obrigatórios com valores numéricos válidos.")
    nome = f.get("nome", "").strip()

    if fazenda_id not in {fz.id for fz in user.fazendas}:  # só fazendas do próprio usuário
        return erro("Fazenda inválida.")
    if not nome:
        return erro("Informe o nome da cultura.")
    if not 0 < p < 1:
        return erro("O fator p deve estar entre 0 e 1 (sem incluir o 1).")
    if min(x["duracao"] for x in fases.values()) < 1:
        return erro("Cada fase deve durar ao menos 1 dia.")
    for k in ("inicial", "media", "final"):  # o desenvolvimento não tem Kc/raízes próprios: é interpolado
        if fases[k]["kc"] is None or fases[k]["z"] is None or fases[k]["kc"] <= 0 or fases[k]["z"] <= 0:
            return erro(f"Fase {FASES[k]}: informe Kc e profundidade das raízes maiores que zero.")
    if any(x["area_sombreada"] is not None and not 0 <= x["area_sombreada"] <= 100 for x in fases.values()):
        return erro("A área sombreada deve estar entre 0 e 100 (%).")
    # o cálculo (interpolacao) só aceita estas combinações para as fases fixas
    if not fases["inicial"]["constante"] or not fases["media"]["constante"]:
        return erro("As fases Inicial e Média devem ser constantes.")
    if fases["desenvolvimento"]["constante"]:
        return erro("A fase Desenvolvimento não pode ser constante: ela é interpolada entre a Inicial e a Média.")
    db.add(Cultura(fazenda_id=fazenda_id, nome=nome, p=p, fases=[FaseCultura(fase=k, **v) for k, v in fases.items()]))
    db.commit()
    return RedirectResponse("/culturas", status_code=303)


TIPOS_EQUIPAMENTO = ["Aspersor", "Microaspersor", "Gotejador", "Pivô central", "Linear", "Autopropelido"]


def pagina_equipamentos(request: Request, user: User, erro: str | None = None):
    equipamentos = [e for f in user.fazendas for e in f.equipamentos]
    return render(request, "equipamentos.html", user=user, fazendas=user.fazendas, equipamentos=equipamentos,
                  tipos=TIPOS_EQUIPAMENTO, erro=erro)


@app.get("/equipamentos")
def equipamentos(request: Request, user: User = Depends(exige_login)):
    return pagina_equipamentos(request, user)


@app.post("/equipamentos")
def criar_equipamento(request: Request, fazenda_id: int = Form(...), tipo: str = Form(...), nome: str = Form(...),
                      vazao: float = Form(...), eficiencia: float = Form(...),
                      user: User = Depends(exige_login), db: Session = Depends(get_db)):
    if fazenda_id not in {f.id for f in user.fazendas}:  # só fazendas do próprio usuário
        return pagina_equipamentos(request, user, "Fazenda inválida.")
    if tipo not in TIPOS_EQUIPAMENTO:
        return pagina_equipamentos(request, user, "Tipo de equipamento inválido.")
    if not nome.strip():
        return pagina_equipamentos(request, user, "Informe o nome do equipamento.")
    if vazao <= 0:
        return pagina_equipamentos(request, user, "A vazão deve ser maior que zero.")
    if not 0 < eficiencia <= 100:
        return pagina_equipamentos(request, user, "A eficiência deve estar entre 0 e 100 (%).")
    db.add(Equipamento(fazenda_id=fazenda_id, tipo=tipo, nome=nome.strip(), vazao=vazao, eficiencia=eficiencia))
    db.commit()
    return RedirectResponse("/equipamentos", status_code=303)


FASES = {"inicial": "Inicial", "desenvolvimento": "Desenvolvimento", "media": "Média", "final": "Final"}


def pagina_parcelas(request: Request, user: User, erro: str | None = None):
    fz = user.fazendas
    return render(request, "parcelas.html", user=user, fazendas=fz, fases=FASES, erro=erro,
                  culturas=[c for f in fz for c in f.culturas], solos=[s for f in fz for s in f.solos],
                  equipamentos=[e for f in fz for e in f.equipamentos], parcelas=[p for f in fz for p in f.parcelas])


@app.get("/parcelas")
def parcelas(request: Request, user: User = Depends(exige_login)):
    return pagina_parcelas(request, user)


@app.post("/parcelas")
def criar_parcela(request: Request, fazenda_id: int = Form(...), nome: str = Form(...), area_ha: float = Form(...),
                  data_plantio: datetime.date = Form(...), cultura_id: int = Form(...), fase: str = Form(...),
                  data_inicio_fase: datetime.date = Form(...), solo_id: int = Form(...),
                  umidade_inicial: float = Form(...), equipamento_id: int = Form(...),
                  espacamento_x: float = Form(...), espacamento_y: float = Form(...),
                  manejo_inicio: datetime.date = Form(...), manejo_fim: datetime.date = Form(...),
                  user: User = Depends(exige_login), db: Session = Depends(get_db)):
    def erro(msg):
        return pagina_parcelas(request, user, msg)

    cultura, solo, equip = db.get(Cultura, cultura_id), db.get(Solo, solo_id), db.get(Equipamento, equipamento_id)
    # fazenda do usuário e cultura/solo/equipamento da MESMA fazenda
    if fazenda_id not in {f.id for f in user.fazendas} or not all(
            o and o.fazenda_id == fazenda_id for o in (cultura, solo, equip)):
        return erro("Fazenda, cultura, solo ou equipamento inválido.")
    if not nome.strip():
        return erro("Informe o nome da parcela.")
    if area_ha <= 0 or espacamento_x <= 0 or espacamento_y <= 0:
        return erro("Área e espaçamento devem ser maiores que zero.")
    if fase not in FASES:
        return erro("Fase inválida.")
    # limites do perfil inteiro; o limite exato (na profundidade das raízes) é conferido ao rodar o manejo
    wp, fc = min(c.theta_wp for c in solo.camadas), max(c.theta_fc for c in solo.camadas)
    if not wp <= umidade_inicial <= fc:
        return erro(f"A umidade inicial deve ficar entre o ponto de murcha ({wp}) e a capacidade de campo ({fc}) do solo.")
    if data_inicio_fase < data_plantio or manejo_inicio < data_inicio_fase:
        return erro("As datas da fase e do manejo não podem ser anteriores ao plantio, e o manejo não pode começar antes da fase.")
    if manejo_fim < manejo_inicio:
        return erro("A data final do manejo deve ser igual ou posterior à inicial.")
    db.add(Parcela(fazenda_id=fazenda_id, nome=nome.strip(), area_ha=area_ha, data_plantio=data_plantio,
                   cultura_id=cultura_id, fase=fase, data_inicio_fase=data_inicio_fase, solo_id=solo_id,
                   umidade_inicial=umidade_inicial, equipamento_id=equipamento_id, espacamento_x=espacamento_x,
                   espacamento_y=espacamento_y, manejo_inicio=manejo_inicio, manejo_fim=manejo_fim))
    db.commit()
    return RedirectResponse("/parcelas", status_code=303)


def pagina_manejo(request: Request, user: User, erro: str | None = None, msg: str | None = None):
    return render(request, "manejo.html", user=user, parcelas=[p for f in user.fazendas for p in f.parcelas],
                  erro=erro, msg=msg)


@app.get("/manejo")
def manejo(request: Request, user: User = Depends(exige_login)):
    return pagina_manejo(request, user)


def parcela_do_usuario(user: User, parcela_id: int) -> Parcela:
    parcela = next((p for f in user.fazendas for p in f.parcelas if p.id == parcela_id), None)
    if parcela is None:
        raise HTTPException(status_code=404)
    return parcela


@app.post("/manejo/{parcela_id}")
def rodar(request: Request, parcela_id: int, user: User = Depends(exige_login), db: Session = Depends(get_db)):
    parcela = parcela_do_usuario(user, parcela_id)
    try:
        msg = rodar_manejo(db, parcela)
    except ValueError as e:
        db.rollback()
        return pagina_manejo(request, user, erro=str(e))
    except requests.RequestException:
        db.rollback()
        return pagina_manejo(request, user, erro="Falha ao consultar a Open-Meteo. Tente novamente em instantes.")
    return pagina_manejo(request, user, msg=msg)


@app.get("/manejo/{parcela_id}")
def grafico(request: Request, parcela_id: int, user: User = Depends(exige_login)):
    parcela = parcela_do_usuario(user, parcela_id)
    dias = parcela.resultados
    dados = {"datas": [r.data.strftime("%d/%m/%y") for r in dias]}
    for k in ("eto", "etca", "precipitacao", "irrigacao", "dp", "ua", "fc", "f", "pmp"):
        dados[k] = [round(r.valores[k], 2) for r in dias]
    dados["kc"] = [round(r.valores["kc"], 3) for r in dias]
    itn = None  # irrigação necessária no último dia calculado, com o tempo equivalente no equipamento da parcela
    if dias:
        v = dias[-1].valores
        mm = v.get("irrigacao_recomendada", v["irrigacao"])
        itn = {"data": dias[-1].data, "mm": mm, "min": mm / taxa_aplicacao(parcela) * 60}
    return render(request, "grafico.html", user=user, parcela=parcela, dias=dias, dados=dados, itn=itn, erro=None)


LIMITE_LANCAMENTO = {"tempo": 1440, "lamina": 300}  # min/dia e mm/dia, só para barrar valor absurdo


def pagina_lancamentos(request: Request, user: User, erro: str | None = None, msg: str | None = None):
    parcelas = [p for f in user.fazendas for p in f.parcelas]
    return render(request, "lancamentos.html", user=user, parcelas=parcelas, hoje=datetime.date.today(),
                  erro=erro, msg=msg)


@app.get("/lancamentos")
def lancamentos(request: Request, user: User = Depends(exige_login)):
    return pagina_lancamentos(request, user)


@app.post("/lancamentos")
def criar_lancamento(request: Request, parcela_id: int = Form(...), data: datetime.date = Form(...),
                     tipo: str = Form(...), valor: float = Form(...),
                     user: User = Depends(exige_login), db: Session = Depends(get_db)):
    def erro(msg):
        return pagina_lancamentos(request, user, erro=msg)

    parcela = next((p for f in user.fazendas for p in f.parcelas if p.id == parcela_id), None)
    if parcela is None:
        return erro("Parcela inválida.")
    if tipo not in LIMITE_LANCAMENTO:
        return erro("Informe a irrigação por tempo ou por lâmina.")
    if not parcela.manejo_inicio <= data <= min(parcela.manejo_fim, datetime.date.today()):
        return erro("A data deve estar dentro do período do manejo e não pode ser futura.")
    if not 0 <= valor <= LIMITE_LANCAMENTO[tipo]:
        return erro(f"O valor deve estar entre 0 e {LIMITE_LANCAMENTO[tipo]} ({'minutos' if tipo == 'tempo' else 'mm'}).")
    lamina = valor / 60 * taxa_aplicacao(parcela) if tipo == "tempo" else valor  # lâmina informada = a que chegou ao solo
    atual = next((x for x in parcela.lancamentos if x.data == data), None)
    if atual:  # um lançamento por dia: o novo substitui o anterior
        atual.tipo, atual.valor, atual.lamina_mm = tipo, valor, lamina
    else:
        parcela.lancamentos.append(Lancamento(data=data, tipo=tipo, valor=valor, lamina_mm=lamina))
    db.commit()
    return pagina_lancamentos(request, user, msg="Lançamento salvo. Rode o manejo para atualizar o balanço.")


@app.post("/lancamentos/{lancamento_id}/excluir")
def excluir_lancamento(request: Request, lancamento_id: int, user: User = Depends(exige_login),
                       db: Session = Depends(get_db)):
    lanc = next((x for f in user.fazendas for p in f.parcelas for x in p.lancamentos if x.id == lancamento_id), None)
    if lanc is None:
        raise HTTPException(status_code=404)
    db.delete(lanc)
    db.commit()
    return pagina_lancamentos(request, user, msg="Lançamento excluído. Rode o manejo para atualizar o balanço.")
