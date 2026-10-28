"""Cria dados de demonstração no banco: python seed_demo.py
Login: demo@exemplo.com / demo12345. Datas relativas a hoje, para o 'Rodar manejo' funcionar na hora."""
import datetime

import bcrypt
from sqlalchemy import select

from app.db import Base, SessionLocal, engine
from app.models import Camada, Cultura, Equipamento, FaseCultura, Fazenda, Parcela, Solo, User

EMAIL, SENHA = "demo@exemplo.com", "demo12345"


def semear(db) -> bool:
    """Devolve False (sem mexer em nada) se o usuário demo já existe."""
    if db.scalar(select(User).where(User.email == EMAIL)):
        return False
    hoje = datetime.date.today()
    fim = hoje + datetime.timedelta(days=30)

    solo = Solo(nome="Franco-arenoso", camadas=[Camada(espessura=0.3, theta_fc=0.25, theta_wp=0.12),
                                                       Camada(espessura=0.5, theta_fc=0.28, theta_wp=0.14)])
    def fases(dur, kc, z):  # dur: 4 fases; kc e z: (inicial, média, final), o desenvolvimento é interpolado
        idx = {"inicial": 0, "media": 1, "final": 2}
        return [FaseCultura(fase=f, duracao=d, kc=kc[idx[f]] if f in idx else None, z=z[idx[f]] if f in idx else None,
                            constante=f in ("inicial", "media"))
                for f, d in zip(("inicial", "desenvolvimento", "media", "final"), dur)]

    milho = Cultura(nome="Milho", p=0.55, fases=fases((20, 35, 40, 30), (0.3, 1.2, 0.6), (0.2, 0.9, 0.9)))
    feijao = Cultura(nome="Feijão", p=0.45, fases=fases((20, 30, 40, 20), (0.4, 1.15, 0.35), (0.2, 0.6, 0.6)))
    aspersor = Equipamento(tipo="Aspersor", nome="Aspersor convencional", vazao=1.2, eficiencia=75)
    gotejo = Equipamento(tipo="Gotejador", nome="Gotejamento linha 1", vazao=0.004, eficiencia=90)

    def parcela(nome, area, cultura, umidade, equip, x, y):
        return Parcela(nome=nome, area_ha=area, data_plantio=hoje, cultura=cultura, fase="inicial",
                       data_inicio_fase=hoje, solo=solo, umidade_inicial=umidade, equipamento=equip,
                       espacamento_x=x, espacamento_y=y, manejo_inicio=hoje, manejo_fim=fim)

    fazenda = Fazenda(nome="Fazenda Exemplo", proprietario="João Silva", estado="Pernambuco", cidade="Petrolina",
                      latitude=-9.39, longitude=-40.50, altitude=376, solos=[solo], culturas=[milho, feijao],
                      equipamentos=[aspersor, gotejo],
                      parcelas=[parcela("Talhão A", 2.5, milho, 0.20, aspersor, 12, 12),
                                parcela("Talhão B", 1.0, feijao, 0.18, gotejo, 1.0, 0.5)])
    db.add(User(nome="Usuário Demo", email=EMAIL, fazendas=[fazenda],
                senha_hash=bcrypt.hashpw(SENHA.encode(), bcrypt.gensalt()).decode()))
    db.commit()
    return True


if __name__ == "__main__":
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        print(f"Dados criados. Login: {EMAIL} / {SENHA}" if semear(db) else "Usuário demo já existe, nada foi alterado.")
