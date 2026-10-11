import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

CARD_OK = """NUM. PEDIDO: 1001
ID: 98765
EMPRESA: Padaria Exemplo LTDA
CONSULTOR: ANA EXEMPLO
STATUS: AGUARDANDO ACEITE
Criado em: 05/03/2026"""


def card(id_="98765", empresa="Padaria Exemplo LTDA", consultor="ANA EXEMPLO",
         status="AGUARDANDO ACEITE", data="05/03/2026"):
    return (f"NUM. PEDIDO: 1\nID: {id_}\nEMPRESA: {empresa}\n"
            f"CONSULTOR: {consultor}\nSTATUS: {status}\nCriado em: {data}")


# --- extrair_quantidade ---

@pytest.mark.parametrize("texto,esperado", [
    ("QTD - 7", 7),
    ("QTD - 120", 120),
    ("QTD - ", 0),
    ("", 0),
    (None, 0),
])
def test_extrair_quantidade(texto, esperado):
    assert main.extrair_quantidade(texto) == esperado


# --- extrair_pedido ---

def test_extrair_pedido_card_valido():
    assert main.extrair_pedido(CARD_OK, "ANA EXEMPLO") == {
        "id": "98765", "empresa": "Padaria Exemplo LTDA", "data": "05/03/2026",
    }


def test_extrair_pedido_nome_case_insensitive():
    assert main.extrair_pedido(CARD_OK, "Ana Exemplo") is not None


def test_extrair_pedido_status_diferente():
    assert main.extrair_pedido(card(status="APROVADO"), "ANA EXEMPLO") is None


def test_extrair_pedido_sem_num_pedido():
    txt = CARD_OK.replace("NUM. PEDIDO: 1001\n", "")
    assert main.extrair_pedido(txt, "ANA EXEMPLO") is None


def test_extrair_pedido_outro_consultor():
    assert main.extrair_pedido(card(consultor="BRUNO FICTICIO"), "ANA EXEMPLO") is None


def test_extrair_pedido_sem_id():
    txt = CARD_OK.replace("ID: 98765\n", "")
    assert main.extrair_pedido(txt, "ANA EXEMPLO") is None


def test_extrair_pedido_campos_ausentes_viram_na():
    txt = "NUM. PEDIDO: 1\nID: 5\nCONSULTOR: ANA EXEMPLO\nSTATUS: AGUARDANDO ACEITE"
    assert main.extrair_pedido(txt, "ANA EXEMPLO") == {"id": "5", "empresa": "N/A", "data": "N/A"}


# --- filtrar_pedidos ---

def test_filtrar_pedidos_ignora_invalidos_e_para_na_quantidade():
    cards = [
        card(id_="1"),
        card(id_="2", status="CANCELADO"),
        card(id_="3", consultor="CLARA TESTE"),
        card(id_="4"),
        card(id_="5"),  # clone/cache: não deve entrar, já bateu a quantidade
    ]
    pedidos = main.filtrar_pedidos(cards, "ANA EXEMPLO", 2)
    assert [p["id"] for p in pedidos] == ["1", "4"]


def test_filtrar_pedidos_nenhum_valido():
    assert main.filtrar_pedidos([card(status="APROVADO")], "ANA EXEMPLO", 1) == []


# --- calcular_periodo ---

def test_calcular_periodo():
    datas = ["10/02/2026", "01/03/2026", "N/A", "15/01/2026", "data-ruim"]
    assert main.calcular_periodo(datas) == ("15/01/2026", "01/03/2026")


def test_calcular_periodo_vazio():
    assert main.calcular_periodo([]) == ("N/A", "N/A")
    assert main.calcular_periodo(["N/A"]) == ("N/A", "N/A")


# --- mensagens ---

PEDIDOS = [
    {"id": "1", "empresa": "Padaria Exemplo LTDA", "data": "05/03/2026"},
    {"id": "2", "empresa": "Mercado Fictício", "data": "N/A"},
]


def test_montar_lista_clientes():
    assert main.montar_lista_clientes(PEDIDOS) == (
        "🔸 *Padaria Exemplo LTDA* (ID: 1) - 05/03/2026\n"
        "🔸 *Mercado Fictício* (ID: 2) - N/A\n"
    )


def test_montar_mensagem_individual():
    msg = main.montar_mensagem_individual("ANA EXEMPLO", PEDIDOS)
    assert msg.startswith("Fala *ANA EXEMPLO*!")
    assert "*2* proposta(s)" in msg
    assert "AGUARDANDO ACEITE" in msg
    assert main.montar_lista_clientes(PEDIDOS) in msg


def test_montar_alerta_supervisor():
    msg = main.montar_alerta_supervisor("CLARA TESTE", PEDIDOS)
    assert "*CLARA TESTE*" in msg
    assert msg.endswith(main.montar_lista_clientes(PEDIDOS))


def test_montar_resumo():
    msg = main.montar_resumo(5, "15/01/2026", "01/03/2026")
    assert msg.startswith("📊 *RELATÓRIO DE PROPOSTAS*")
    assert "*AGUARDANDO ACEITE*: *5*" in msg
    assert "Período acumulado: 15/01/2026 a 01/03/2026" in msg


# --- configuração ---

ENV_OK = {
    "CRM_URL": "https://crm.exemplo.com.br/",
    "CRM_PEDIDOS_URL": "https://crm.exemplo.com.br/pedidos",
    "CRM_EMAIL": "usuario@exemplo.com.br",
    "CRM_SENHA": "x",
    "EVOLUTION_API_URL": "http://localhost:8080/",
    "EVOLUTION_INSTANCE": "teste",
    "EVOLUTION_API_KEY": "chave",
    "WHATSAPP_DIRETORIA": "5511900000000",
}


def test_carregar_config_ok():
    cfg = main.carregar_config(ENV_OK)
    assert cfg["EVOLUTION_API_URL"] == "http://localhost:8080"
    assert cfg["EQUIPE_ARQUIVO"] == "equipe.json"
    assert cfg["WHATSAPP_GRUPO"] == ""


def test_carregar_config_faltando():
    env = dict(ENV_OK, CRM_SENHA="")
    del env["EVOLUTION_API_KEY"]
    with pytest.raises(main.ConfigError) as e:
        main.carregar_config(env)
    assert "CRM_SENHA" in str(e.value) and "EVOLUTION_API_KEY" in str(e.value)


def test_carregar_equipe(tmp_path):
    arq = tmp_path / "equipe.json"
    arq.write_text(json.dumps({"ANA EXEMPLO": 5511900000001}), encoding="utf-8")
    assert main.carregar_equipe(str(arq)) == {"ANA EXEMPLO": "5511900000001"}


def test_carregar_equipe_inexistente(tmp_path):
    with pytest.raises(main.ConfigError):
        main.carregar_equipe(str(tmp_path / "nao-existe.json"))


def test_equipe_example_valido():
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    equipe = main.carregar_equipe(os.path.join(raiz, "equipe.example.json"))
    assert len(equipe) == 3
