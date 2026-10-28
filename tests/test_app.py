import datetime
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app


@pytest.fixture()
def c():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return TestClient(app, follow_redirects=False)


def cadastra(c, email="a@x.com", senha="senha1234"):
    return c.post("/cadastro", data={"nome": "Ana", "email": email, "senha": senha, "senha2": senha})


def test_home_exige_login(c):
    assert c.get("/").headers["location"] == "/login"


def test_cadastro_login_e_fazenda_isolada(c):
    assert cadastra(c).status_code == 303
    assert c.post("/fazendas", data={"nome": "Faz A", "latitude": "-10.5"}).status_code == 303
    assert "Faz A" in c.get("/").text
    c.post("/logout")
    cadastra(c, "b@x.com")
    assert "Faz A" not in c.get("/").text  # outro usuário não vê


def test_validacoes(c):
    assert "não coincidem" in c.post("/cadastro", data={"nome": "A", "email": "a@x.com", "senha": "senha1234", "senha2": "x"}).text
    cadastra(c)
    assert "já cadastrado" in cadastra(c).text
    assert "fora do intervalo" in c.post("/fazendas", data={"nome": "F", "latitude": "95"}).text
    c.post("/logout")
    assert "inválidos" in c.post("/login", data={"email": "a@x.com", "senha": "errada123"}).text


def test_solo(c):
    cadastra(c)
    c.post("/fazendas", data={"nome": "Faz A"})
    solo = {"fazenda_id": "1", "nome": "Argiloso", "espessura": "0.4", "theta_fc": "0.35", "theta_wp": "0.2"}
    assert c.post("/solos", data=solo).status_code == 303
    assert "Argiloso" in c.get("/solos").text
    assert "0 &lt; ponto de murcha" in c.post("/solos", data={**solo, "theta_wp": "0.5"}).text  # murcha > campo
    duas = {**solo, "nome": "Duas camadas", "espessura": ["0.3", "0.4"], "theta_fc": ["0.3", "0.35"], "theta_wp": ["0.15", "0.2"]}
    assert c.post("/solos", data=duas).status_code == 303
    assert "Duas camadas" in c.get("/solos").text
    assert "Camada 2: a espessura" in c.post("/solos", data={**duas, "espessura": ["0.3", "0"]}).text
    assert "maior que zero" in c.post("/solos", data={**solo, "espessura": "0"}).text
    c.post("/logout")
    cadastra(c, "b@x.com")
    assert "inválida" in c.post("/solos", data=solo).text  # fazenda de outro usuário
    assert "Argiloso" not in c.get("/solos").text


CULT = {"fazenda_id": "1", "nome": "Milho", "p": "0.55",
        "dur_inicial": "20", "dur_desenvolvimento": "35", "dur_media": "40", "dur_final": "30",
        "kc_inicial": "0.3", "kc_media": "1.2", "kc_final": "0.6",
        "z_inicial": "0.2", "z_media": "0.9", "z_final": "0.9",
        "const_inicial": "on", "const_media": "on"}


def test_cultura(c):
    cadastra(c)
    c.post("/fazendas", data={"nome": "Faz A"})
    assert c.post("/culturas", data={**CULT, "area_final": "30", "const_final": "on"}).status_code == 303
    assert "Milho" in c.get("/culturas").text
    assert "entre 0 e 1" in c.post("/culturas", data={**CULT, "p": "1.5"}).text
    assert "ao menos 1 dia" in c.post("/culturas", data={**CULT, "dur_desenvolvimento": "0"}).text
    assert "maiores que zero" in c.post("/culturas", data={**CULT, "kc_media": "0"}).text
    assert "entre 0 e 100" in c.post("/culturas", data={**CULT, "area_inicial": "150"}).text
    assert "valores numéricos" in c.post("/culturas", data={**CULT, "dur_final": "abc"}).text
    assert "devem ser constantes" in c.post("/culturas", data={k: v for k, v in CULT.items() if k != "const_inicial"}).text
    assert "não pode ser constante" in c.post("/culturas", data={**CULT, "const_desenvolvimento": "on"}).text
    c.post("/logout")
    cadastra(c, "b@x.com")
    assert "inválida" in c.post("/culturas", data=CULT).text
    assert "Milho" not in c.get("/culturas").text


EQUIP = {"fazenda_id": "1", "tipo": "Aspersor", "nome": "Aspersor 1", "vazao": "12", "eficiencia": "85"}


def test_equipamento(c):
    cadastra(c)
    c.post("/fazendas", data={"nome": "Faz A"})
    assert c.post("/equipamentos", data=EQUIP).status_code == 303
    assert "Aspersor 1" in c.get("/equipamentos").text
    assert c.post("/equipamentos", data={**EQUIP, "tipo": "Autopropelido", "nome": "Carretel 1"}).status_code == 303
    assert c.post("/equipamentos", data={**EQUIP, "tipo": "Gotejamento", "nome": "Antigo"}).status_code != 303  # tipo retirado da lista
    assert "Tipo de equipamento inválido" in c.post("/equipamentos", data={**EQUIP, "tipo": "Foguete"}).text
    assert "vazão deve ser" in c.post("/equipamentos", data={**EQUIP, "vazao": "0"}).text
    assert "entre 0 e 100" in c.post("/equipamentos", data={**EQUIP, "eficiencia": "120"}).text
    c.post("/logout")
    cadastra(c, "b@x.com")
    assert "Fazenda inválida" in c.post("/equipamentos", data=EQUIP).text
    assert "Aspersor 1" not in c.get("/equipamentos").text


PARC = {"fazenda_id": "1", "nome": "Parcela 1", "area_ha": "2.5", "data_plantio": "2026-10-01", "cultura_id": "1",
        "fase": "inicial", "data_inicio_fase": "2026-10-01", "solo_id": "1", "umidade_inicial": "0.3",
        "equipamento_id": "1", "espacamento_x": "12", "espacamento_y": "12",
        "manejo_inicio": "2026-10-01", "manejo_fim": "2026-12-01"}


def prepara_parcela(c):
    cadastra(c)
    c.post("/fazendas", data={"nome": "Faz A", "latitude": "-9.4", "longitude": "-40.5", "altitude": "370"})
    c.post("/fazendas", data={"nome": "Faz B"})
    c.post("/solos", data={"fazenda_id": "1", "nome": "Argiloso", "espessura": "0.4", "theta_fc": "0.35", "theta_wp": "0.2"})
    c.post("/culturas", data=CULT)
    c.post("/culturas", data={**CULT, "fazenda_id": "2", "nome": "Soja"})  # cultura id 2, da fazenda B
    c.post("/equipamentos", data=EQUIP)


def test_parcela(c):
    prepara_parcela(c)
    assert c.post("/parcelas", data=PARC).status_code == 303
    assert "Parcela 1" in c.get("/parcelas").text
    for campo, valor, msg in [("umidade_inicial", "0.5", "umidade inicial deve"),
                              ("manejo_fim", "2026-09-01", "final do manejo"),
                              ("data_inicio_fase", "2026-09-01", "anteriores ao plantio"),
                              ("fase", "x", "Fase inválida"),
                              ("espacamento_x", "0", "maiores que zero"),
                              ("cultura_id", "2", "inválido")]:  # cultura de outra fazenda
        assert msg in c.post("/parcelas", data={**PARC, campo: valor}).text, campo
    c.post("/logout")
    cadastra(c, "b@x.com")
    assert "inválido" in c.post("/parcelas", data=PARC).text
    assert "Parcela 1" not in c.get("/parcelas").text


def _simula(umidade, irrigacoes=None):
    from calculo.balanco import simular
    periodo = {"inicial": 20, "desenvolvimento": 35, "media": 40, "final": 30}
    d = datetime.date(2026, 10, 1)
    return simular([d], [5.0], [0.0], [(0.5, 0.35, 0.2)], 0.55, periodo, {"inicial": 0.2, "media": 0.9, "final": 0.9},
                   {"inicial": True, "desenvolvimento": False, "media": True, "final": True},
                   {"inicial": 0.3, "media": 1.2, "final": 0.6},
                   {"inicial": True, "desenvolvimento": False, "media": True, "final": False}, d, umidade, irrigacoes)[0]


def test_simular_conta_na_mao():
    a = _simula(0.30)  # ADT 30 mm, AFA 16,5 mm, déficit inicial 10 mm: sem estresse, sem irrigar
    assert a["din"] == pytest.approx(10) and a["etca"] == pytest.approx(1.5)
    assert a["irrigacao"] == 0 and a["dfim"] == pytest.approx(11.5)
    b = _simula(0.25)  # déficit inicial 20 mm > AFA: Ks reduz a ET e a irrigação repõe o déficit
    assert b["ks"] == pytest.approx(10 / 13.5) and b["irrigacao"] == pytest.approx(20 + b["etca"])
    assert b["dfim"] == pytest.approx(0, abs=1e-6)
    x = _simula(0.25, {datetime.date(2026, 10, 1): 0.0})  # produtor não irrigou: vale o informado, a recomendação fica registrada
    assert x["irrigacao"] == 0 and x["lancada"] and x["irrigacao_recomendada"] == pytest.approx(b["irrigacao"])
    assert x["dfim"] == pytest.approx(20 + x["etca"])
    assert not a["lancada"] and a["irrigacao_recomendada"] == a["irrigacao"]
    with pytest.raises(ValueError, match="umidade inicial"):
        _simula(0.5)  # acima da capacidade de campo


def test_medias_na_raiz():
    from calculo.balanco import medias_na_raiz
    assert medias_na_raiz([(0.5, 0.3, 0.1)], 0.9) == (0.3, 0.1)  # uma camada só: vale ela, mesmo com raiz mais funda
    camadas = [(0.3, 0.30, 0.15), (0.5, 0.40, 0.20)]
    assert medias_na_raiz(camadas, 0.6) == pytest.approx((0.35, 0.175))  # 0,3 m de cada camada
    assert medias_na_raiz(camadas, 0.2) == pytest.approx((0.30, 0.15))  # raiz só na primeira
    assert medias_na_raiz(camadas, 1.0) == pytest.approx((0.37, 0.185))  # 0,2 m além da última camada valem a última


def _falsa_api(monkeypatch, chamadas):
    """Open-Meteo falsa: devolve ETo 4,0 mm/dia nos dias passados e 5,0 mm hoje."""
    import app.manejo as manejo
    hoje = datetime.date.today()

    def buscar(lat, lon, alt, passados=0):
        chamadas.append(passados)
        return [{"data": hoje - datetime.timedelta(days=k), "eto": 5.0 if k == 0 else 4.0, "precipitacao": float("nan")}
                for k in range(passados, -1, -1)]
    monkeypatch.setattr(manejo, "buscar_periodo", buscar)


def test_rodar_manejo(c, monkeypatch):
    chamadas = []
    _falsa_api(monkeypatch, chamadas)
    hoje = datetime.date.today()
    prepara_parcela(c)

    def parcela(nome, inicio):
        d = inicio.isoformat()
        return {**PARC, "nome": nome, "data_plantio": d, "data_inicio_fase": d, "manejo_inicio": d,
                "manejo_fim": (hoje + datetime.timedelta(days=30)).isoformat()}

    c.post("/parcelas", data=parcela("P1", hoje))
    c.post("/parcelas", data=parcela("P2", hoje - datetime.timedelta(days=5)))
    c.post("/parcelas", data=parcela("P3", hoje + datetime.timedelta(days=3)))
    assert "1 dia(s)" in c.post("/manejo/1").text
    # dias que ninguém registrou (o caso de rodar de novo dias depois) são recuperados na mesma consulta
    r = c.post("/manejo/2")
    assert "6 dia(s)" in r.text and "Atenção" not in r.text
    assert chamadas[-1] == 6  # os 5 dias do início do manejo, hoje e 1 de folga
    assert "Ainda não há dados" in c.post("/manejo/3").text  # o manejo ainda não começou
    g = c.get("/manejo/1")
    assert g.status_code == 200 and "Umidade do solo" in g.text and '"ua"' in g.text
    assert "ainda não tem resultados" in c.get("/manejo/3").text
    c.post("/logout")
    cadastra(c, "b@x.com")
    assert c.post("/manejo/1").status_code == 404
    assert c.get("/manejo/1").status_code == 404  # gráfico de parcela de outro usuário


def test_lancamentos(c, monkeypatch):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import ResultadoDia
    _falsa_api(monkeypatch, [])
    hoje = datetime.date.today()

    def dia(k):
        return (hoje - datetime.timedelta(days=k)).isoformat()

    prepara_parcela(c)
    c.post("/parcelas", data={**PARC, "data_plantio": dia(5), "data_inicio_fase": dia(5), "manejo_inicio": dia(5),
                              "manejo_fim": (hoje + datetime.timedelta(days=30)).isoformat()})
    lanc = {"parcela_id": "1", "data": dia(2), "tipo": "tempo", "valor": "30"}
    r = c.post("/lancamentos", data=lanc)
    assert "Lançamento salvo" in r.text and "35.42" in r.text  # 12 m³/h x 85% sobre 12x12 m = 70,8 mm/h; 30 min = 35,4 mm
    r = c.post("/lancamentos", data={**lanc, "tipo": "lamina", "valor": "7"})  # mesma data: substitui
    assert r.text.count('action="/lancamentos/') == 1 and "7.00" in r.text
    assert "dentro do período" in c.post("/lancamentos", data={**lanc, "data": dia(9)}).text
    assert "dentro do período" in c.post("/lancamentos", data={**lanc, "data": (hoje + datetime.timedelta(days=1)).isoformat()}).text
    assert "entre 0 e 300" in c.post("/lancamentos", data={**lanc, "data": dia(1), "tipo": "lamina", "valor": "999"}).text
    assert "tempo ou por lâmina" in c.post("/lancamentos", data={**lanc, "tipo": "x"}).text

    assert "dia(s)" in c.post("/manejo/1").text  # o balanço usa o lançado nos dias lançados e o recomendado nos demais
    with SessionLocal() as db:
        v = {x.data.isoformat(): x.valores for x in db.scalars(select(ResultadoDia))}
    assert v[dia(2)]["lancada"] and v[dia(2)]["irrigacao"] == pytest.approx(7)
    assert not v[dia(3)]["lancada"] and v[dia(3)]["irrigacao"] == v[dia(3)]["irrigacao_recomendada"]
    assert "ITN" in c.get("/manejo/1").text

    c.post("/logout")
    cadastra(c, "b@x.com")
    assert "inválida" in c.post("/lancamentos", data=lanc).text
    assert c.post("/lancamentos/1/excluir").status_code == 404
    c.post("/logout")
    c.post("/login", data={"email": "a@x.com", "senha": "senha1234"})
    assert "Lançamento excluído" in c.post("/lancamentos/1/excluir").text


def test_seed_demo(c, monkeypatch):
    import seed_demo
    from app.db import SessionLocal
    with SessionLocal() as db:
        assert seed_demo.semear(db) is True
        assert seed_demo.semear(db) is False  # não duplica
    _falsa_api(monkeypatch, [])
    assert c.post("/login", data={"email": seed_demo.EMAIL, "senha": seed_demo.SENHA}).status_code == 303
    assert "Talhão A" in c.get("/parcelas").text
    assert "1 dia(s)" in c.post("/manejo/1").text
    assert "1 dia(s)" in c.post("/manejo/2").text
