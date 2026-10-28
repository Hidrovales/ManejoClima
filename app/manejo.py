import datetime
import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from calculo import balanco, calcula_eto, open_meteo

from .models import Parcela, ResultadoDia, SerieDiaria

FASES_ORDEM = ["inicial", "desenvolvimento", "media", "final"]


def taxa_aplicacao(parcela: Parcela) -> float:
    """mm/h que o equipamento aplica ao solo: vazão (m³/h) sobre a área do espaçamento, vezes a eficiência."""
    e = parcela.equipamento
    return e.vazao * 1000 / (parcela.espacamento_x * parcela.espacamento_y) * e.eficiencia / 100


def buscar_periodo(latitude: float, longitude: float, altitude: float, dias_passados: int = 0) -> list[dict]:
    """ETo e chuva de hoje e dos `dias_passados` dias anteriores (Open-Meteo + FAO-56), do mais antigo ao de hoje.
    Isolada para os testes não dependerem da rede."""
    df = open_meteo.buscar_dados_diarios(latitude, longitude, dias_passados=dias_passados)
    dias = []
    for i in range(len(df)):
        r = calcula_eto.calcular_eto_hoje(df.iloc[[i]], latitude, altitude)
        dias.append({"data": datetime.date.fromisoformat(str(r["data"])[:10]), "eto": float(r["eto_calculado_mm"]),
                     "precipitacao": r.get("precipitacao_total_mm")})
    return dias


def rodar_manejo(db: Session, parcela: Parcela) -> str:
    """Atualiza a série da fazenda (do início do manejo até hoje), recalcula o balanço da parcela e grava o resultado."""
    f, cult = parcela.fazenda, parcela.cultura
    if None in (f.latitude, f.longitude, f.altitude):
        raise ValueError("A fazenda precisa ter latitude, longitude e altitude cadastradas.")

    # uma única consulta traz hoje e os dias desde o início do manejo, então dias perdidos se recuperam sozinhos
    # (a Open-Meteo devolve no máximo 92 dias passados; a data do servidor pode diferir 1 dia da da fazenda, por isso o +1)
    passados = max(0, min(92, (datetime.date.today() - parcela.manejo_inicio).days + 1))
    dias = buscar_periodo(f.latitude, f.longitude, f.altitude, passados)
    hoje = dias[-1]["data"]
    for d in dias:
        if math.isnan(d["eto"]):  # dia com dados incompletos na API: fica de fora (o aviso no fim informa)
            continue
        chuva = d["precipitacao"]
        # shortcut: chuva ausente na API vira 0 mm, trocar por aviso se isso começar a acontecer
        chuva = 0.0 if chuva is None or math.isnan(chuva) else float(chuva)
        linha = db.scalar(select(SerieDiaria).where(SerieDiaria.fazenda_id == f.id, SerieDiaria.data == d["data"]))
        if linha:
            linha.eto, linha.precipitacao = d["eto"], chuva
        else:
            db.add(SerieDiaria(fazenda_id=f.id, data=d["data"], eto=d["eto"], precipitacao=chuva))
    db.flush()
    serie = {s.data: s for s in db.scalars(select(SerieDiaria).where(SerieDiaria.fazenda_id == f.id))}

    fs = {x.fase: x for x in cult.fases}
    periodo = {k: fs[k].duracao for k in FASES_ORDEM}
    constantes = {k: fs[k].constante for k in FASES_ORDEM}  # a mesma coluna "constante" vale para Kc e raízes
    # início do ciclo = início da fase informada menos as fases que vêm antes dela
    data_in = parcela.data_inicio_fase - datetime.timedelta(
        days=sum(periodo[k] for k in FASES_ORDEM[:FASES_ORDEM.index(parcela.fase)]))
    ultimo = min(parcela.manejo_fim, data_in + datetime.timedelta(days=sum(periodo.values()) - 1))

    # só dias consecutivos a partir do início do manejo: a série não pode ter buracos
    datas, d = [], parcela.manejo_inicio
    while d <= ultimo and d in serie:
        datas.append(d)
        d += datetime.timedelta(days=1)
    if not datas:
        raise ValueError(f"Ainda não há dados diários para {parcela.manejo_inicio:%d/%m/%Y}. "
                         f"A série desta fazenda começa em {min(serie):%d/%m/%Y} "
                         f"(a Open-Meteo só devolve até 92 dias passados).")

    camadas = [(c.espessura, c.theta_fc, c.theta_wp) for c in parcela.solo.camadas]
    linhas = balanco.simular(
        datas, [serie[d].eto for d in datas], [serie[d].precipitacao for d in datas],
        camadas, cult.p, periodo,
        {k: fs[k].z for k in ("inicial", "media", "final")}, constantes,
        {k: fs[k].kc for k in ("inicial", "media", "final")}, constantes,
        data_in, parcela.umidade_inicial, {x.data: x.lamina_mm for x in parcela.lancamentos})
    parcela.resultados = [ResultadoDia(data=d, valores=v) for d, v in zip(datas, linhas)]
    db.commit()
    msg = f"Manejo calculado: {len(datas)} dia(s), de {datas[0]:%d/%m/%Y} a {datas[-1]:%d/%m/%Y}."
    if datas[-1] < min(ultimo, hoje):
        msg += f" Atenção: faltam dados diários a partir de {datas[-1] + datetime.timedelta(days=1):%d/%m/%Y}."
    return msg
