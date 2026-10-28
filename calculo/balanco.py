"""Fórmulas do balanço hídrico (FAO 56) e simulação pura, sem banco nem gráficos.
As fórmulas são cópia de Balanco_Hidrico.py; simular() é o laço de balanco() sem a parte do sqlite.
"""

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


def medias_na_raiz(camadas, Zr):
  """
  θ_fc e θ_wp médios na zona radicular, ponderados pela espessura de cada camada (de cima para baixo).
  :parâmetro camadas: lista de (espessura [m], theta_fc, theta_wp), da superfície para baixo.
  :parâmetro Zr: profundidade das raízes [m]. Se passar da última camada, vale a última.
  """
  if len(camadas) == 1:
    return camadas[0][1], camadas[0][2]
  fc = wp = prof = 0.0
  for esp, f, w in camadas:
    t = min(esp, Zr - prof)
    if t <= 0:
      break
    fc, wp, prof = fc + f * t, wp + w * t, prof + t
  if prof < Zr:
    fc, wp, prof = fc + camadas[-1][1] * (Zr - prof), wp + camadas[-1][2] * (Zr - prof), Zr
  return fc / prof, wp / prof


def simular(datas, eto, P, camadas, p, periodo, z_etapas, forma_z, kc_etapas, forma_kc, data_in, umidade_inicial,
            irrigacoes=None):
  """
  Balanço dia a dia (mesmo laço de balanco()), devolvendo uma lista de dicionários, um por dia.
  :parâmetro datas: datas consecutivas (datetime.date) a calcular.
  :parâmetro eto, P: listas com ETo e precipitação [mm] de cada data.
  :parâmetro camadas: lista de (espessura [m], theta_fc, theta_wp) do solo; ver medias_na_raiz().
  :parâmetro data_in: início do ciclo da cultura (referência da interpolação de Kc e Zr).
  :parâmetro umidade_inicial: umidade do solo no primeiro dia [m^3 m^-3]; define o déficit inicial.
  :parâmetro irrigacoes: dicionário {data: lâmina aplicada [mm]}. Nos dias que estão nele vale o valor informado;
                         nos demais vale a irrigação recomendada pelo balanço.
  """
  if p >= 1:
    raise ValueError("O fator p deve ser menor que 1.")
  zr0 = interpolacao(datas[0], periodo, z_etapas, forma_z, data_in)
  fc0, wp0 = medias_na_raiz(camadas, zr0)
  if not wp0 - 1e-9 <= umidade_inicial <= fc0 + 1e-9:
    raise ValueError(f"A umidade inicial ({umidade_inicial}) está fora dos limites do solo na profundidade das raízes "
                     f"(ponto de murcha {wp0:.3f}, capacidade de campo {fc0:.3f}). Ajuste a parcela.")
  dfim = din = 1000 * (fc0 - umidade_inicial) * zr0
  linhas = []
  for j, d in enumerate(datas):
    kc = interpolacao(d, periodo, kc_etapas, forma_kc, data_in)
    Zr = interpolacao(d, periodo, z_etapas, forma_z, data_in)
    theta_fc, theta_wp = medias_na_raiz(camadas, Zr)
    adt = ADT(theta_fc, theta_wp, Zr)
    afa = AFA(p, ADT=adt)
    if j != 0:
      din = Din(P[j], dfim)
    ks = Ks(din, adt, afa)
    etca = Etca(eto[j], kc, ks)
    recomendada = Irrigacao(din, afa, etca)
    lancada = bool(irrigacoes) and d in irrigacoes
    I = irrigacoes[d] if lancada else recomendada
    dp = DP(P[j], I, etca, dfim)
    dfim = Dfim(dfim, P[j], I, etca, dp)
    FC = Zr * theta_fc * 1000
    PMP = Zr * theta_wp * 1000
    linhas.append({"eto": eto[j], "precipitacao": P[j], "kc": kc, "zr": Zr, "adt": adt, "afa": afa, "din": din,
                   "dfim": dfim, "ks": ks, "irrigacao": I, "irrigacao_recomendada": recomendada, "lancada": lancada, "dp": dp, "etca": etca, "fc": FC, "pmp": PMP,
                   "f": FC - (FC - PMP) * p, "ua": FC - din})
  return linhas
