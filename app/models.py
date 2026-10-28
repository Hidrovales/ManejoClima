import datetime

from sqlalchemy import JSON, Boolean, Date, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    fazendas: Mapped[list["Fazenda"]] = relationship(back_populates="dono", cascade="all, delete-orphan")


class Fazenda(Base):
    __tablename__ = "fazendas"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    nome: Mapped[str] = mapped_column(String(120))
    proprietario: Mapped[str | None] = mapped_column(String(120))
    estado: Mapped[str | None] = mapped_column(String(60))
    cidade: Mapped[str | None] = mapped_column(String(120))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    altitude: Mapped[float | None] = mapped_column(Float)
    dono: Mapped[User] = relationship(back_populates="fazendas")
    solos: Mapped[list["Solo"]] = relationship(back_populates="fazenda", cascade="all, delete-orphan")
    culturas: Mapped[list["Cultura"]] = relationship(back_populates="fazenda", cascade="all, delete-orphan")
    equipamentos: Mapped[list["Equipamento"]] = relationship(back_populates="fazenda", cascade="all, delete-orphan")
    parcelas: Mapped[list["Parcela"]] = relationship(back_populates="fazenda", cascade="all, delete-orphan")


class Solo(Base):
    __tablename__ = "solos"
    id: Mapped[int] = mapped_column(primary_key=True)
    fazenda_id: Mapped[int] = mapped_column(ForeignKey("fazendas.id"), index=True)
    nome: Mapped[str] = mapped_column(String(120))
    fazenda: Mapped[Fazenda] = relationship(back_populates="solos")
    camadas: Mapped[list["Camada"]] = relationship(back_populates="solo", cascade="all, delete-orphan", order_by="Camada.id")


class Camada(Base):
    __tablename__ = "camadas"
    id: Mapped[int] = mapped_column(primary_key=True)
    solo_id: Mapped[int] = mapped_column(ForeignKey("solos.id"), index=True)
    espessura: Mapped[float] = mapped_column(Float)  # m
    theta_fc: Mapped[float] = mapped_column(Float)  # capacidade de campo, m³/m³
    theta_wp: Mapped[float] = mapped_column(Float)  # ponto de murcha, m³/m³
    solo: Mapped[Solo] = relationship(back_populates="camadas")


class Cultura(Base):
    __tablename__ = "culturas"
    id: Mapped[int] = mapped_column(primary_key=True)
    fazenda_id: Mapped[int] = mapped_column(ForeignKey("fazendas.id"), index=True)
    nome: Mapped[str] = mapped_column(String(120))
    p: Mapped[float] = mapped_column(Float)  # fator de disponibilidade hídrica
    fazenda: Mapped[Fazenda] = relationship(back_populates="culturas")
    fases: Mapped[list["FaseCultura"]] = relationship(cascade="all, delete-orphan", order_by="FaseCultura.id")


class FaseCultura(Base):
    """Uma linha da tabela de fases: inicial, desenvolvimento, media ou final (nessa ordem)."""
    __tablename__ = "fases_cultura"
    id: Mapped[int] = mapped_column(primary_key=True)
    cultura_id: Mapped[int] = mapped_column(ForeignKey("culturas.id"), index=True)
    fase: Mapped[str] = mapped_column(String(20))
    duracao: Mapped[int] = mapped_column(Integer)  # dias (periodo)
    kc: Mapped[float | None] = mapped_column(Float)  # vazio no desenvolvimento: é interpolado
    z: Mapped[float | None] = mapped_column(Float)  # profundidade das raízes, m (z_etapas)
    area_sombreada: Mapped[float | None] = mapped_column(Float)  # %, guardada mas ainda não usada no cálculo
    constante: Mapped[bool] = mapped_column(Boolean, default=False)  # forma_kc (vale também para as raízes)


class Equipamento(Base):
    __tablename__ = "equipamentos"
    id: Mapped[int] = mapped_column(primary_key=True)
    fazenda_id: Mapped[int] = mapped_column(ForeignKey("fazendas.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(40))
    nome: Mapped[str] = mapped_column(String(120))
    vazao: Mapped[float] = mapped_column(Float)  # m³/h
    eficiencia: Mapped[float] = mapped_column(Float)  # %
    fazenda: Mapped[Fazenda] = relationship(back_populates="equipamentos")


class Parcela(Base):
    __tablename__ = "parcelas"
    id: Mapped[int] = mapped_column(primary_key=True)
    fazenda_id: Mapped[int] = mapped_column(ForeignKey("fazendas.id"), index=True)
    nome: Mapped[str] = mapped_column(String(120))
    area_ha: Mapped[float] = mapped_column(Float)
    data_plantio: Mapped[datetime.date] = mapped_column(Date)
    cultura_id: Mapped[int] = mapped_column(ForeignKey("culturas.id"))
    fase: Mapped[str] = mapped_column(String(20))  # fase a manejar: inicial/desenvolvimento/media/final
    data_inicio_fase: Mapped[datetime.date] = mapped_column(Date)
    solo_id: Mapped[int] = mapped_column(ForeignKey("solos.id"))
    umidade_inicial: Mapped[float] = mapped_column(Float)  # θ no início do manejo, m³/m³
    equipamento_id: Mapped[int] = mapped_column(ForeignKey("equipamentos.id"))
    espacamento_x: Mapped[float] = mapped_column(Float)  # m
    espacamento_y: Mapped[float] = mapped_column(Float)  # m
    manejo_inicio: Mapped[datetime.date] = mapped_column(Date)
    manejo_fim: Mapped[datetime.date] = mapped_column(Date)
    fazenda: Mapped[Fazenda] = relationship(back_populates="parcelas")
    cultura: Mapped[Cultura] = relationship()
    solo: Mapped[Solo] = relationship()
    equipamento: Mapped[Equipamento] = relationship()
    resultados: Mapped[list["ResultadoDia"]] = relationship(cascade="all, delete-orphan", order_by="ResultadoDia.data")
    lancamentos: Mapped[list["Lancamento"]] = relationship(cascade="all, delete-orphan", order_by="Lancamento.data")


class SerieDiaria(Base):
    """ETo e chuva de cada dia já registrado para a fazenda (cresce um dia por vez, ao rodar o manejo)."""
    __tablename__ = "serie_diaria"
    __table_args__ = (UniqueConstraint("fazenda_id", "data"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    fazenda_id: Mapped[int] = mapped_column(ForeignKey("fazendas.id"), index=True)
    data: Mapped[datetime.date] = mapped_column(Date)
    eto: Mapped[float] = mapped_column(Float)  # mm
    precipitacao: Mapped[float] = mapped_column(Float)  # mm


class ResultadoDia(Base):
    """Um dia do balanço de uma parcela; 'valores' guarda kc, zr, adt, afa, din, dfim, ks, irrigacao, dp, etca, fc, pmp, f, ua."""
    __tablename__ = "resultados_dia"
    id: Mapped[int] = mapped_column(primary_key=True)
    parcela_id: Mapped[int] = mapped_column(ForeignKey("parcelas.id"), index=True)
    data: Mapped[datetime.date] = mapped_column(Date)
    valores: Mapped[dict] = mapped_column(JSON)


class Lancamento(Base):
    """Irrigação aplicada em um dia (no máximo um por parcela e dia): informada por tempo (min) ou por lâmina (mm)."""
    __tablename__ = "lancamentos"
    __table_args__ = (UniqueConstraint("parcela_id", "data"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    parcela_id: Mapped[int] = mapped_column(ForeignKey("parcelas.id"), index=True)
    data: Mapped[datetime.date] = mapped_column(Date)
    tipo: Mapped[str] = mapped_column(String(10))  # "tempo" ou "lamina"
    valor: Mapped[float] = mapped_column(Float)  # minutos ou mm, conforme o tipo
    lamina_mm: Mapped[float] = mapped_column(Float)  # lâmina que chegou ao solo; é o que o balanço usa
