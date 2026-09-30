"""
Simula o balanço hídrico
Referência: FAO 56 (2006)
"""

import numpy as np
import datetime
import sqlite3
import contextlib
import pandas as pd
import matplotlib.pyplot as plt
import main
import Calcula_ETo as gse

def interpolacao(data, tempo, etapas, forma, data_in):
  """
  Interpolação: Equação 66 (FAO 56)
  :parâmetro data: data atual.
  :parâmetro tempo: dicionário com o número de dias de cada fase (inicial, desenvolvimento, media e final).
  :parâmetro etapas: dicionário com as etapas inicial, media e final.
  :parâmetro forma: dicionário com a forma de cada etapa (inicial, desenvolvimento, media e final). Para constante, etapa recebe True.
  :parâmetro data_in: data de início do cultivo.
  :return: valor interpolado
  """
  def interpola(prox, prev, L_etapa, Sum_L_prev, i):
    i = i + 1
    a = (i - Sum_L_prev) / L_etapa
    b = prox - prev
    c = a * b + prev
    return c
  i = data - data_in
  if i.days < tempo['inicial']:
    if not forma['inicial']:
      raise ValueError(
          "A etapa 'inicial' precisa ser constante (forma['inicial'] = True); "
          "não há uma etapa anterior para interpolar a partir dela."
      )
    valor = etapas['inicial']
  elif i.days < tempo['inicial'] + tempo['desenvolvimento']:
    if forma['desenvolvimento']:
      raise ValueError(
          "A etapa 'desenvolvimento' precisa ser não-constante (forma['desenvolvimento'] = False); "
          "ela é sempre interpolada entre 'inicial' e 'media', e 'etapas' não tem um valor próprio para ela."
      )
    valor = interpola(etapas['media'], etapas['inicial'], tempo['desenvolvimento'], tempo['inicial'], i.days)
  elif i.days < tempo['inicial'] + tempo['desenvolvimento'] + tempo['media']:
    if not forma['media']:
      raise ValueError(
          "A etapa 'media' precisa ser constante (forma['media'] = True); "
          "não há um valor de 'etapas' para uma 'media' não-constante."
      )
    valor = etapas['media']
  elif i.days < tempo['inicial'] + tempo['desenvolvimento'] + tempo['media'] + tempo['final']:
    if not forma['final']:
      Sum_L_prev = tempo['inicial'] + tempo['desenvolvimento'] + tempo['media']
      valor = interpola(etapas['final'], etapas['media'], tempo['final'], Sum_L_prev, i.days)
    else:
      valor = etapas['final']
  return valor

def AFA(p, ADT):
  """
  Calculo da Agua facilmente aproveitável (AFA) da zona radicular do solo [mm]: Equação 83 (FAO 56)
  :parâmetro p: fator de disponibilidade hídrica [0 - 1].
  :parâmetro ADT: total de água disponível na zona radicular do solo [mm].
  :return: AFA
  """
  return p * ADT

def ADT(theta_fc, theta_wp, Zr):
  """
  Calculo do total de água disponível (ADT) na zona radicular do solo [mm]: Equação 83 (FAO 56)
  :parâmetro theta_fc: capacidade de campo [m^3 m^3].
  :parâmetro theta_wp: ponto de murcha [m^3 m^3].
  :parâmetro Zr: profundidade das raízes [m].
  :return: ADT
  """
  return 1000*(theta_fc - theta_wp)*Zr

def Din(P, Dfim, RO = 0):
  """
  Déficit de água do solo no inicil do dia [mm]: Equação 85 (FAO 56)
  O RO: Escoamento superficial do dia i [mm] pode ser considerado 0, uma vez que os eventos de precipitação que proporcionam escoamento 
  superficial também elevam a umidade do solo à capacidade de campo, podendo, dessa forma, ser ignorado.
  :parâmetro Dfim: Déficit de água do solo ao final do dia [mm].
  :parâmetro P: Precipitação do dia i [mm].
  :return: Déficit de água do solo no inicil do dia [mm].
  """

  if P > 0:
    return max(Dfim - P, 0)
  else:
    return Dfim

def DP(P, I, ET, Dfim):
  """
  Percolação profunda do dia i [mm]: Equação 88 (FAO 56)
  O CR: Ascensão capilar do dia i [mm] é considerado 0, uma vez que o nível do lençol freático se encontra 1m abaixo da zona radicular.
  O RO: Escoamento superficial do dia i [mm] é considerado 0, uma vez que os eventos de precipitação que proporcionam escoamento 
  superficial também elevam a umidade do solo à capacidade de campo, podendo, dessa forma, ser ignorado.
  :parâmetro P: Precipitação do dia [mm].
  :parâmetro I: Lâmina de irrigação do dia [mm].
  :parâmetro ET: Evapotranspiração do cultivo do dia anterior [mm].
  :parâmetro Dfim: Déficit de água do solo ao final do dia anterior [mm].
  return: Percolação profunda do dia i [mm]
  """
  CR = 0
  RO = 0
  if (P - RO) + I - ET - Dfim > 0:
    return (P - RO) + I - ET - Dfim
  else:
    return 0

def Ks(Din, ADT, AFA):
  """
  Coeficiente de redução de evapotranspiração em função da umidade do solo [0 - 1]: Equação 84 (FAO 56)
  :parâmetro Din: Déficit inicial de água do solo do dia [mm].
  :parâmetro ADT: Total de água disponível na zona radicular do solo [mm].
  :parâmetro AFA: Agua facilmente aproveitável (AFA) da zona radicular do solo [mm].
  return: Coeficiente de redução de evapotranspiração em função da umidade do solo [0 - 1]
  """
  if Din < AFA:
    return 1
  else:
    return (ADT - Din) / (ADT - AFA)

def Etca(Eto, Kc, Ks):
  """
  Evapotranspiração da cultura ajustada [mm/d]: Equação 81 (FAO 56)
  :parâmetro Eto: Evapotranspiração de referencia [mm].
  :parâmetro Kc: coeficiente da cultura.
  :parâmetro Ks: coeficiente de redução de evapotranspiração em função da umidade do solo [0 - 1].
  return: Evapotranspiração da cultura ajustada [mm/d].
  """
  return Eto * Kc * Ks

def Dfim(Dfim, P, I, ET, DP):
  """
  Déficit de água do solo ao final do dia [mm]: Equação 85 (FAO 56)
  O CR: Ascensão capilar do dia i [mm] é considerado 0, uma vez que o nível do lençol freático se encontra 1m abaixo da zona radicular.
  O RO: Escoamento superficial do dia i [mm] é considerado 0, uma vez que os eventos de precipitação que proporcionam escoamento 
  superficial também elevam a umidade do solo à capacidade de campo, podendo, dessa forma, ser ignorado.
  :parâmetro P: Precipitação do dia [mm].
  :parâmetro I: Lâmina de irrigação do dia [mm].
  :parâmetro ET: Evapotranspiração do cultivo do dia [mm].
  :parâmetro Dfim: Déficit de água do solo ao final do dia anterior [mm].
  :parâmetro DP: Percolação profunda do dia [mm].
  return: Déficit de água do solo ao final do dia  [mm]
  """
  CR = 0
  RO = 0
  if Dfim - (P - RO) - I - CR + ET + DP < 0:
    return 0
  else:
    return Dfim - (P - RO) - I - CR + ET + DP

def Irrigacao(Din, AFA, ET):
  """
  Lâmina de irrigação [mm]
  :parâmetro Din: Déficit de água do solo no inicil do dia [mm].
  :parâmetro AFA: Agua facilmente aproveitável (AFA) da zona radicular do solo [mm].
  :parâmetro ET: Evapotranspiração do cultivo do dia [mm].
  return: Lâmina de irrigação [mm]
  """
  if Din >= AFA:
    return Din + ET
  else:
    return 0

#Função para executar INSERT INTO
def execute_insert(sql,data,database_path):
    """
    Função para executar INSERT INTO
    :parametro sql: string com código sql
    :parametro data: dados que serão inseridos no banco de dados
    :parametro database_path: caminho para o banco de dados
    """
    with contextlib.closing(sqlite3.connect(database_path)) as conn: # auto-closes
        with conn: # auto-commits
            with contextlib.closing(conn.cursor()) as cursor: # auto-closes
                cursor.execute(sql,data)
                return cursor.fetchall()


def execute(sql,database_path):
    """
    Função para executar INSERT INTO
    :parametro sql: string com código sql
    :parametro database_path: caminho para o banco de dados
    :return: dataframe com os valores retornados pela consulta sql
    """
    with contextlib.closing(sqlite3.connect(database_path)) as conn: # auto-closes
        with conn: # auto-commits
            with contextlib.closing(conn.cursor()) as cursor: # auto-closes
                cursor.execute(sql)
                return cursor.fetchall()


def criar_tabela_serie_diaria(database_path):
    """
    Garante que a tabela 'serie_diaria' exista — é nela que cada dia registrado
    por registrar_dia() é acumulado, um de cada vez.
    :parametro database_path: caminho para o banco de dados.
    """
    execute(
        """CREATE TABLE IF NOT EXISTS serie_diaria(
               LOCAL TEXT, DATA TEXT, ETO REAL, PRECIPITACAO REAL,
               UNIQUE(LOCAL, DATA)
           )""",
        database_path,
    )


def registrar_dia(local, latitude, longitude, altitude, database_path, timezone="auto"):
    """
    Busca o dia de hoje na Open-Meteo, calcula o ETo (Calcula_ETo.calcular_eto_hoje)
    e grava a linha do dia na tabela 'serie_diaria'. Rodar isso uma vez por dia (ex:
    numa tarefa agendada) é o que faz a série temporal crescer com o tempo, um dia de
    cada vez, em vez de buscar o ciclo inteiro de uma só vez.
    Se já existir um registro para esse LOCAL+DATA, ele é atualizado (não duplicado).
    :parâmetro local: nome/identificador do local (separa séries de locais diferentes).
    :parâmetro latitude, longitude, altitude: coordenadas do local.
    :parâmetro database_path: caminho para o banco de dados.
    :parâmetro timezone: fuso horário (padrão 'auto').
    :return: dicionário com os dados do dia (mesmo formato de calcular_eto_hoje()).
    """
    criar_tabela_serie_diaria(database_path)

    df_diario = main.buscar_dados_diarios(latitude, longitude, timezone)
    resultado = gse.calcular_eto_hoje(df_diario, latitude, altitude)

    execute_insert(
        """INSERT INTO serie_diaria (LOCAL, DATA, ETO, PRECIPITACAO)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(LOCAL, DATA) DO UPDATE SET
               ETO = excluded.ETO,
               PRECIPITACAO = excluded.PRECIPITACAO""",
        (local, resultado["data"], resultado["eto_calculado_mm"], resultado.get("precipitacao_total_mm")),
        database_path,
    )
    return resultado


def carregar_serie_diaria(local, database_path):
    """
    Carrega toda a série diária já acumulada (via registrar_dia) para um local.
    :parâmetro local: nome/identificador do local usado em registrar_dia().
    :parâmetro database_path: caminho para o banco de dados.
    :return: DataFrame com colunas DATA (datetime), ETO, PRECIPITACAO, ordenado por
             data — pronto para fatiar em (DATA, ETO) e (DATA, PRECIPITACAO) e passar
             para balanco() como os parâmetros 'eto' e 'P'.
    """
    linhas = execute_insert(
        "SELECT DATA, ETO, PRECIPITACAO FROM serie_diaria WHERE LOCAL = ? ORDER BY DATA",
        (local,),
        database_path,
    )
    df = pd.DataFrame(linhas, columns=["DATA", "ETO", "PRECIPITACAO"])
    df["DATA"] = pd.to_datetime(df["DATA"])
    return df

def plot_balanco(df, figsize):
  """
  Plotar gráfico do balanço hídrico.
  :parametro df: dataframe com todas as variáveis geradas pela função balanco.
  :parametro figsize: tamanho da figura (x,y).
  """
  import seaborn as sns
  precipitacao, irrigacao, dp = np.frombuffer(df['PRECIPITACAO']), np.frombuffer(df['I']), np.frombuffer(df['DP'])
  # Usa o tamanho real dos dados calculados (pode ser menor que o ciclo teórico
  # completo, já que a série pode ainda estar sendo alimentada dia a dia).
  dias = precipitacao.shape[0]
  data_list = [datetime.datetime.strptime(df['DATA_PLANTIO'], '%Y-%m-%d %H:%M:%S') + datetime.timedelta(days=idx) for idx in range(dias)]
  datas = []
  for i in range(len(data_list)):
    datas.append(str(data_list[i].day) + '/' + str(data_list[i].month) + '/' + str(data_list[i].year))
  #-------------------------------------------------------------------------------------
  classe_precipitacao, classe_irrigacao, classe_dp = [], [], []
  for i in range(precipitacao.shape[0]):
    classe_precipitacao.append('PRECIPITAÇÃO')
    classe_irrigacao.append('I')
    classe_dp.append('DP')
  column_names = ["DATA", "VALOR", "CLASSE"]
  df_p = pd.DataFrame(columns = column_names)
  df_i = pd.DataFrame(columns = column_names)
  df_dp = pd.DataFrame(columns = column_names)
  df_p['DATA'], df_p['VALOR'], df_p['CLASSE'] = datas, precipitacao.tolist(), classe_precipitacao
  df_i['DATA'], df_i['VALOR'], df_i['CLASSE'] = datas, irrigacao.tolist(), classe_irrigacao
  df_dp['DATA'], df_dp['VALOR'], df_dp['CLASSE'] = datas, dp.tolist(), classe_dp
  df_p = pd.concat([df_p, df_i, df_dp], ignore_index=True)
  #-------------------------------------------------------------------------------------
  sns.set_style("whitegrid")
  fig, ax = plt.subplots(nrows=1, ncols=1, figsize=figsize, dpi=100)
  colors = ["gold", "dodgerblue", "crimson"]
  # Set your custom color palette
  sns.set_palette(sns.color_palette(colors))
  sns.barplot(x="DATA", y="VALOR", hue="CLASSE", data=df_p, linewidth=0.7, saturation=1)
  ax2, = ax.plot(np.frombuffer(df['FC']), '-', color = 'blue', ms=5, lw=2, alpha=1, mfc='blue', label= "CAPACIDADE DE CAMPO")
  ax5, = ax.plot(np.frombuffer(df['UA']), '--o', color = 'green', ms=5, lw=2, alpha=1, mfc='green', label = 'UMIDADE DO SOLO')
  ax3, = ax.plot(np.frombuffer(df['F']), '-', color = 'red', ms=5, lw=2, alpha=1, mfc='red', label = 'UMIDADE CRÍTICA')
  ax4, = ax.plot(np.frombuffer(df['PMP']), '-', color = 'black', ms=5, lw=2, alpha=1, mfc='black', label = 'PONTO DE MURCHA PERMANENTE')
  plt.tick_params(labelsize=7)
  ax.set_xticklabels(ax.get_xticklabels(), rotation=45)
  plt.ylabel("mm", fontsize=10)
  plt.legend(bbox_to_anchor=(1.01, 1), borderaxespad=0)
  ax.set(xlabel=None) 
  ax.legend()
  pass
  return

def plot_extras(df, figsize):
  """
  Plotar gráfico com a ETo, ETc e Kc usados no balanço hídrico.
  :parametro df: dataframe com todas as variáveis geradas pela função balanco.
  :parametro figsize: tamanho da figura (x,y).
  """
  import seaborn as sns
  eto = np.frombuffer(df['ETO'])
  etc = np.frombuffer(df['ETCA'])
  kc = np.frombuffer(df['KC'])
  # Usa o tamanho real dos dados calculados (pode ser menor que o ciclo teórico
  # completo, já que a série pode ainda estar sendo alimentada dia a dia).
  dias = eto.shape[0]
  data_list = [datetime.datetime.strptime(df['DATA_PLANTIO'], '%Y-%m-%d %H:%M:%S') + datetime.timedelta(days=idx) for idx in range(dias)]
  datas = []
  for i in range(len(data_list)):
    datas.append(str(data_list[i].day) + '/' + str(data_list[i].month) + '/' + str(data_list[i].year))
  #-------------------------------------------------------------------------------------
  fig, ax1 = plt.subplots(figsize=figsize, dpi=100)

  color = 'tab:red'
  ax1.set_ylabel('ETo', color=color, fontsize=10)
  ax1.plot(datas,eto, color=color)
  plt.plot(datas,etc, color="blue")
  ax1.tick_params(axis='y', labelcolor=color)
  plt.xticks(rotation=45)
  plt.tick_params(labelsize=10)
  ax2 = ax1.twinx()  # instantiate a second axes that shares the same x-axis
  #-------------------------------------------------------------------------------------
  color = 'tab:green'
  ax2.set_ylabel('KC', color=color, fontsize=10)  # we already handled the x-label with ax1
  ax2.plot(datas,kc, color=color)
  ax2.tick_params(axis='y', labelcolor=color)
  ax2.xaxis.set_major_locator(plt.MaxNLocator(15))

  fig.tight_layout()  # otherwise the right y-label is slightly clipped
  plt.show()

  pass
  return 
 
def balanco(local, cultura, theta_fc, theta_wp, p, P, eto, periodo, z_etapas, forma_z, kc_etapas, forma_kc, data_in, database_path):
  """
  Balanço de irrigação
  :parâmetro theta_fc: capacidade de campo [m^3 m^3].
  :parâmetro theta_wp: ponto de murcha [m^3 m^3].
  :parâmetro p: fator de disponibilidade hídrica [0 - 1].
  :parâmetro P: precipitação do dia [mm].
  :parâmetro eto: dataframe com a série temporal de Evapotranspiração de referencia [mm] (Coluna 0 - Data, Coluna 1 - Eto).
  :parâmetro periodo: dicionário com o número de dias de cada fase (inicial, desenvolvimento, media e final).
  :parâmetro z_etapas: dicionário com as etapas inicial, media e final da profundidade radicular.
  :parâmetro forma_z: dicionário com a forma de cada etapa (inicial, desenvolvimento, media e final) da profundidade radicular. 
                      Para constante, etapa recebe True.
  :parâmetro kc_etapas: dicionário com as etapas inicial, media e final do coeficiente de cultura.
  :parâmetro forma_kc: dicionário com a forma de cada etapa (inicial, desenvolvimento, media e final) do coeficiente de cultura. 
                       Para constante, etapa recebe True.
  :parâmetro data_in: data de início do cultivo.
  """
  #------------------------------------
  dias = sum(periodo.values())
  data_in = datetime.datetime(data_in['ano'], data_in['mes'], data_in['dia'])
  data_list = [data_in + datetime.timedelta(days=idx) for idx in range(dias)]
  #------------------------------------
  eto = eto[eto.iloc[:,0] >= data_list[0]]
  eto = eto[eto.iloc[:,0] <= data_list[-1]]
  eto = eto.iloc[:,1].values
  #------------------------------------
  P = P[P.iloc[:,0] >= data_list[0]]
  P = P[P.iloc[:,0] <= data_list[-1]]
  P = P.iloc[:,1].values
  #------------------------------------
  # A série é alimentada dia a dia (registrar_dia()), então no início do ciclo
  # ela normalmente ainda não cobre todos os `dias` do período — calculamos só
  # até onde já há dado, em vez de estourar índice.
  dias_disponiveis = min(len(data_list), eto.shape[0], P.shape[0])
  if dias_disponiveis < dias:
    print(
        f"Aviso: há dados para {dias_disponiveis} de {dias} dias do ciclo "
        f"(a série está sendo alimentada dia a dia). Calculando só até aí."
    )
  data_list = data_list[:dias_disponiveis]
  eto = eto[:dias_disponiveis]
  P = P[:dias_disponiveis]
  #------------------------------------
  #Informações para o dia 0:
  etca = 0
  dfim = 0
  din = 0
  #------------------------------------
  result_kc, result_Zr, result_adt, result_afa = np.empty([1,eto.shape[0]]), np.empty([1,eto.shape[0]]), np.empty([1,eto.shape[0]]), np.empty([1,eto.shape[0]])
  result_din, result_dfim, result_ks = np.empty([1,eto.shape[0]]), np.empty([1,eto.shape[0]]), np.empty([1,eto.shape[0]])
  result_I, result_dp, result_etca, result_FC =  np.empty([1,eto.shape[0]]), np.empty([1,eto.shape[0]]), np.empty([1,eto.shape[0]]), np.empty([1,eto.shape[0]])
  result_PMP, result_F, result_UA = np.empty([1,eto.shape[0]]), np.empty([1,eto.shape[0]]), np.empty([1,eto.shape[0]])
  #------------------------------------
  for j, i in enumerate(data_list):
    kc = interpolacao(i, periodo, kc_etapas, forma_kc, data_in)
    Zr = interpolacao(i, periodo, z_etapas, forma_z, data_in)
    adt = ADT(theta_fc, theta_wp, Zr)
    afa = AFA(p , ADT= adt)
    if j != 0:
      din = Din(P[j], dfim)
    ks = Ks(din, adt, afa)
    etca = Etca(eto[j], kc, ks)
    I = Irrigacao(din, afa, etca)
    dp = DP(P[j], I, etca, dfim)
    dfim = Dfim(dfim, P[j], I, etca, dp)
    FC = Zr * theta_fc * 1000
    PMP = Zr * theta_wp * 1000
    F = FC - (FC - PMP) * p
    UA = FC - din 
    #------------------------------------
    result_din[0][j] = din
    result_kc[0][j] = kc
    result_Zr[0][j] = Zr
    result_adt[0][j] = adt
    result_afa[0][j] = afa
    result_dfim[0][j] = dfim
    result_ks[0][j] = ks
    result_I[0][j] = I
    result_dp[0][j] = dp
    result_etca[0][j] = etca
    result_FC[0][j] = FC
    result_PMP[0][j] = PMP
    result_F[0][j] = F
    result_UA[0][j] = UA
    #------------------------------------
  execute("""CREATE TABLE IF NOT EXISTS results(LOCAL TEXT, CULTURA TEXT, DATA_PLANTIO TEXT,
                                              KC_INICIAL INT, KC_MEDIO INT, KC_FINAL INT,
                                              ZR_INICIAL INT, ZR_MEDIO INT, ZR_FINAL INT,
                                              PERIODO_INICIAL INT, PERIODO_DESENVOLVIMENTO INT, PERIODO_MEDIO INT, PERIODO_FINAL INT,
                                              P FLOAT, THETA_FC FLOAT, THETA_WP FLOAT,
                                              ETO BLOB, PRECIPITACAO BLOB,
                                              KC BLOB, ZR BLOB, ADT BLOB, AFA BLOB, DIN BLOB, DFIM BLOB, KS BLOB,
                                              I BLOB, DP BLOB, ETCA BLOB, FC BLOB, PMP BLOB, F BLOB, UA BLOB,
                                              UNIQUE(LOCAL, CULTURA, DATA_PLANTIO)
                                              )""", database_path)

  
  execute_insert("""INSERT INTO results VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                               ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
                                               ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                     ON CONFLICT(LOCAL, CULTURA, DATA_PLANTIO) DO UPDATE SET
                       KC_INICIAL=excluded.KC_INICIAL, KC_MEDIO=excluded.KC_MEDIO, KC_FINAL=excluded.KC_FINAL,
                       ZR_INICIAL=excluded.ZR_INICIAL, ZR_MEDIO=excluded.ZR_MEDIO, ZR_FINAL=excluded.ZR_FINAL,
                       PERIODO_INICIAL=excluded.PERIODO_INICIAL, PERIODO_DESENVOLVIMENTO=excluded.PERIODO_DESENVOLVIMENTO,
                       PERIODO_MEDIO=excluded.PERIODO_MEDIO, PERIODO_FINAL=excluded.PERIODO_FINAL,
                       P=excluded.P, THETA_FC=excluded.THETA_FC, THETA_WP=excluded.THETA_WP,
                       ETO=excluded.ETO, PRECIPITACAO=excluded.PRECIPITACAO,
                       KC=excluded.KC, ZR=excluded.ZR, ADT=excluded.ADT, AFA=excluded.AFA,
                       DIN=excluded.DIN, DFIM=excluded.DFIM, KS=excluded.KS,
                       I=excluded.I, DP=excluded.DP, ETCA=excluded.ETCA, FC=excluded.FC,
                       PMP=excluded.PMP, F=excluded.F, UA=excluded.UA"""
              ,(local, cultura, data_in, 
                kc_etapas['inicial'], kc_etapas['media'], kc_etapas['final'], 
                z_etapas['inicial'], z_etapas['media'], z_etapas['final'],
                periodo['inicial'], periodo['desenvolvimento'], periodo['media'], periodo['final'], 
                p, theta_fc, theta_wp, 
                eto.tobytes(), P.tobytes(),
                result_kc.tobytes(), result_Zr.tobytes(), result_adt.tobytes(), result_afa.tobytes(),
                result_din.tobytes(), result_dfim.tobytes(), result_ks.tobytes(), 
                result_I.tobytes(), result_dp.tobytes(), result_etca.tobytes(), result_FC.tobytes(), 
                result_PMP.tobytes(), result_F.tobytes(), result_UA.tobytes()
                ), database_path)

  
  return


def carregar_resultado(local, cultura, database_path):
  """
  Carrega o resultado mais recente de balanco() para (local, cultura) e devolve
  um dicionário pronto para plot_balanco()/plot_extras() — os campos BLOB já
  vêm decodificados de volta para arrays numpy.
  :parâmetro local: mesmo 'local' passado para balanco().
  :parâmetro cultura: mesma 'cultura' passada para balanco().
  :parâmetro database_path: caminho para o banco de dados.
  :return: dicionário com as colunas da tabela 'results', ou None se não houver
           nenhum resultado salvo para esse local/cultura.
  """
  colunas = [
      "LOCAL", "CULTURA", "DATA_PLANTIO",
      "KC_INICIAL", "KC_MEDIO", "KC_FINAL",
      "ZR_INICIAL", "ZR_MEDIO", "ZR_FINAL",
      "PERIODO_INICIAL", "PERIODO_DESENVOLVIMENTO", "PERIODO_MEDIO", "PERIODO_FINAL",
      "P", "THETA_FC", "THETA_WP",
      "ETO", "PRECIPITACAO",
      "KC", "ZR", "ADT", "AFA", "DIN", "DFIM", "KS",
      "I", "DP", "ETCA", "FC", "PMP", "F", "UA",
  ]
  colunas_blob = {
      "ETO", "PRECIPITACAO", "KC", "ZR", "ADT", "AFA", "DIN", "DFIM", "KS",
      "I", "DP", "ETCA", "FC", "PMP", "F", "UA",
  }

  linhas = execute_insert(
      """SELECT * FROM results WHERE LOCAL = ? AND CULTURA = ?
         ORDER BY DATA_PLANTIO DESC LIMIT 1""",
      (local, cultura),
      database_path,
  )
  if not linhas:
      return None

  resultado = dict(zip(colunas, linhas[0]))
  for chave in colunas_blob:
      resultado[chave] = np.frombuffer(resultado[chave])
  return resultado