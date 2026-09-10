"""
Utilizando Open-Meteo para dados:
- Radiação solar (soma diária, em MJ/m²)
- Umidade relativa do ar (máxima, mínima e média)
- Temperatura (máxima, mínima e média)
- Direção do vento dominante e velocidade máxima do vento
- Evapotranspiração de referência (ET0 - FAO Penman-Monteith)
"""

import requests
import pandas as pd

"""
Busca da cidade para encontrar Latitude e Longitude
"""

def buscar_coordenadas(nome_cidade: str, idioma: str = "pt"):
    
    url = "https://geocoding-api.open-meteo.com/v1/search"
    parametros = {"name": nome_cidade, "count": 1, "language": idioma, "format": "json"}

    resposta = requests.get(url, params=parametros, timeout=30)
    resposta.raise_for_status()
    resultados = resposta.json().get("results")

    if not resultados:
        raise ValueError(f"Nenhuma cidade encontrada para '{nome_cidade}'.")

    melhor = resultados[0]
    return {
        "nome": melhor["name"],
        "estado": melhor.get("admin1", ""),
        "pais": melhor["country"],
        "latitude": melhor["latitude"],
        "longitude": melhor["longitude"],
        "timezone": melhor.get("timezone", "auto"),
    }


    """
    Consulta a API Open-Meteo e retorna um DataFrame com os dados diários.

    Parâmetros:
        latitude, longitude: coordenadas do local
        timezone: fuso horário (padrão 'auto', detectado pela lat/lon)
    """
def buscar_dados_diarios(
    latitude: float,
    longitude: float,
    timezone: str = "auto",
) -> pd.DataFrame:


    url = "https://api.open-meteo.com/v1/forecast"

    variaveis_diarias = [
        "temperature_2m_max",
        "temperature_2m_min",
        "temperature_2m_mean",
        "relative_humidity_2m_max",
        "relative_humidity_2m_min",
        "relative_humidity_2m_mean",
        "wind_speed_10m_max",
        "wind_direction_10m_dominant",
        "shortwave_radiation_sum",
        "et0_fao_evapotranspiration",
    ]

    parametros = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": ",".join(variaveis_diarias),
        "timezone": timezone,
    }

    resposta = requests.get(url, params=parametros, timeout=30)
    resposta.raise_for_status()
    dados = resposta.json()

    df_diario = pd.DataFrame(dados["daily"])
    df_diario.rename(
        columns={
            "time": "data",
            "temperature_2m_max": "temp_maxima_c",
            "temperature_2m_min": "temp_minima_c",
            "temperature_2m_mean": "temp_media_c",
            "relative_humidity_2m_max": "umidade_maxima_pct",
            "relative_humidity_2m_min": "umidade_minima_pct",
            "relative_humidity_2m_mean": "umidade_media_pct",
            "wind_speed_10m_max": "velocidade_vento_max_kmh",
            "wind_direction_10m_dominant": "direcao_vento_dominante_graus",
            "shortwave_radiation_sum": "radiacao_solar_total_mjm2",
            "et0_fao_evapotranspiration": "evapotranspiracao_referencia_et0_mm",
        },
        inplace=True,
    )

    return df_diario


if __name__ == "__main__":
    # Nome da cidade desejada (pode incluir estado/país para maior precisão,
    # ex: "Belo Horizonte, Brasil")
    NOME_CIDADE = input("Digite o nome da cidade: ").strip() or "São Paulo"

    local = buscar_coordenadas(NOME_CIDADE)
    print(
        f"Local encontrado: {local['nome']}, {local['estado']}, {local['pais']} "
        f"(lat={local['latitude']}, lon={local['longitude']})\n"
    )

    df_diario = buscar_dados_diarios(
        latitude=local["latitude"],
        longitude=local["longitude"],
        timezone=local.get("timezone", "auto"),
    )

    print("=== Dados diários ===")
    print(df_diario)

    # Salva em CSV com o nome da cidade no arquivo
    nome_arquivo = local["nome"].lower().replace(" ", "_")
    df_diario.to_csv(f"dados_diarios_{nome_arquivo}.csv", index=False)
    print("\nArquivo CSV salvo com sucesso.")