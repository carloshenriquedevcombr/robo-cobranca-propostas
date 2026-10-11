"""Robô de cobrança de propostas "AGUARDANDO ACEITE".

Acessa o CRM via Playwright, consulta a carteira de cada consultor(a),
envia a lista de propostas pendentes no WhatsApp (Evolution API) e,
no final, dispara um resumo para a diretoria e para o grupo da equipe.
"""
import json
import os
import re
import sys
import time
from datetime import datetime

import requests

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv é opcional
    load_dotenv = None

STATUS_ALVO = "AGUARDANDO ACEITE"
FORMATO_DATA = "%d/%m/%Y"
TIMEOUT_API = 30  # segundos

# --- CONFIGURAÇÕES DO SISTEMA (via variáveis de ambiente) ---
VARIAVEIS_OBRIGATORIAS = [
    "CRM_URL",
    "CRM_PEDIDOS_URL",
    "CRM_EMAIL",
    "CRM_SENHA",
    "EVOLUTION_API_URL",
    "EVOLUTION_INSTANCE",
    "EVOLUTION_API_KEY",
    "WHATSAPP_DIRETORIA",
]
# Opcionais: se vazias, o envio correspondente é apenas pulado
VARIAVEIS_OPCIONAIS = ["WHATSAPP_GRUPO", "WHATSAPP_SUPERVISOR"]


class ConfigError(Exception):
    """Configuração ausente ou inválida."""


def carregar_config(env=None):
    """Lê as configurações do ambiente e falha com mensagem clara se faltar algo."""
    env = os.environ if env is None else env
    faltando = [v for v in VARIAVEIS_OBRIGATORIAS if not env.get(v, "").strip()]
    if faltando:
        raise ConfigError(
            "Variáveis de ambiente obrigatórias ausentes: "
            + ", ".join(faltando)
            + ". Copie o .env.example para .env e preencha os valores."
        )
    config = {v: env[v].strip() for v in VARIAVEIS_OBRIGATORIAS}
    for v in VARIAVEIS_OPCIONAIS:
        config[v] = env.get(v, "").strip()
    config["EVOLUTION_API_URL"] = config["EVOLUTION_API_URL"].rstrip("/")
    config["EQUIPE_ARQUIVO"] = env.get("EQUIPE_ARQUIVO", "").strip() or "equipe.json"
    return config


def carregar_equipe(caminho):
    """Carrega o mapa {NOME DO CONSULTOR: número do WhatsApp} de um arquivo JSON."""
    try:
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
    except FileNotFoundError:
        raise ConfigError(
            f"Arquivo da equipe não encontrado: {caminho}. "
            "Copie o equipe.example.json para equipe.json e preencha."
        )
    except json.JSONDecodeError as e:
        raise ConfigError(f"Arquivo da equipe inválido ({caminho}): {e}")
    if not isinstance(dados, dict):
        raise ConfigError(f"O arquivo {caminho} deve conter um objeto JSON {{nome: numero}}.")
    return {str(nome).strip(): str(numero).strip() for nome, numero in dados.items()}


# --- LÓGICA PURA (testável sem navegador) ---

def extrair_quantidade(texto):
    """Extrai o número do contador 'QTD - N' exibido pelo CRM (0 se não achar)."""
    m = re.search(r"\d+", texto or "")
    return int(m.group()) if m else 0


def extrair_pedido(txt, nome):
    """Valida o texto de um card e devolve {id, empresa, data} ou None."""
    # Trava 1: Status exato
    if f"STATUS: {STATUS_ALVO}" not in txt or "NUM. PEDIDO:" not in txt:
        return None

    # Trava 2: Dono do pedido exato
    if nome.upper() not in txt.upper():
        return None

    id_m = re.search(r"ID:\s*(\d+)", txt)
    emp_m = re.search(r"EMPRESA:\s*(.+)", txt)
    dt_m = re.search(r"Criado em:\s*([\d/]{10})", txt)

    if not id_m:
        return None

    return {
        "id": id_m.group(1),
        "empresa": emp_m.group(1).strip() if emp_m else "N/A",
        "data": dt_m.group(1) if dt_m else "N/A",
    }


def filtrar_pedidos(textos_cards, nome, qtd_esperada):
    """Aplica as travas em cada card e para quando atingir a quantidade do sistema."""
    pedidos = []
    for txt in textos_cards:
        pedido = extrair_pedido(txt, nome)
        if pedido:
            pedidos.append(pedido)
        # Trava 3: Para de ler se já bateu a quantidade do sistema (Evita clones)
        if len(pedidos) == qtd_esperada:
            break
    return pedidos


def calcular_periodo(datas):
    """Devolve (data mais antiga, data mais nova) em DD/MM/AAAA, ignorando inválidas."""
    validas = []
    for d in datas:
        try:
            validas.append(datetime.strptime(d, FORMATO_DATA))
        except (TypeError, ValueError):
            pass
    if not validas:
        return "N/A", "N/A"
    return min(validas).strftime(FORMATO_DATA), max(validas).strftime(FORMATO_DATA)


def montar_lista_clientes(pedidos):
    """Monta a listinha de clientes usada nas mensagens do WhatsApp."""
    return "".join(
        f"🔸 *{p['empresa']}* (ID: {p['id']}) - {p['data']}\n" for p in pedidos
    )


def montar_mensagem_individual(nome, pedidos):
    """Mensagem de cobrança enviada no privado do(a) consultor(a)."""
    return (
        f"Fala *{nome}*! Tudo bem?\n\n"
        f"Seus clientes já deram o 'sim' mais difícil, mas vi aqui que você tem *{len(pedidos)}* "
        f"proposta(s) travada(s) como {STATUS_ALVO}.\n\n"
        f"{montar_lista_clientes(pedidos)}\n"
        "A concorrência é rápida. Não deixa esse cliente esfriar! Chama eles agora no WhatsApp "
        "para o clique final e garante a sua comissão. 🚀"
    )


def montar_alerta_supervisor(nome, pedidos):
    """Alerta enviado ao supervisor quando o consultor não tem número cadastrado."""
    return (
        f"🚨 *Aviso Sistema:* A consultora *{nome}* tem pendências, mas o número não está "
        "cadastrado no robô.\n\n" + montar_lista_clientes(pedidos)
    )


def montar_resumo(total, data_inicio, data_fim):
    """Resumo final enviado para a diretoria e para o grupo."""
    return (
        "📊 *RELATÓRIO DE PROPOSTAS*\n\n"
        f"Pendências em *{STATUS_ALVO}*: *{total}*\n"
        f"Período acumulado: {data_inicio} a {data_fim}\n\n"
        "⚠️ As listas individuais já foram enviadas no privado de cada consultor(a) "
        "cobrando a finalização."
    )


# --- INTEGRAÇÕES ---

def enviar_whatsapp(config, numero, mensagem):
    """Envia mensagem via Evolution API (Suporta contatos e grupos)"""
    url = f"{config['EVOLUTION_API_URL']}/message/sendText/{config['EVOLUTION_INSTANCE']}"

    # IDs de grupo (JID com "@") vão exatamente como estão; números normais também
    destino = str(numero)

    payload = {
        "number": destino,
        "text": mensagem,  # Algumas versões do Evolution preferem 'text' solto
        "textMessage": {"text": mensagem},  # Mantemos por compatibilidade
        "options": {
            "delay": 1500,
            "presence": "composing",
        },
    }

    headers = {"apikey": config["EVOLUTION_API_KEY"], "Content-Type": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT_API)
        if response.status_code in [200, 201]:
            tipo_envio = "Grupo" if "@" in destino else "Contato"
            print(f"  ✅ Mensagem enviada para {tipo_envio}: {destino}")
        else:
            print(f"  ⚠️ Falha ao enviar para {numero}: {response.text}")
    except Exception as e:
        print(f"  ❌ Erro de rede na API: {e}")


def buscar_e_notificar(config, equipe):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        # headless=True para rodar na VPS invisível
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(viewport={"width": 1366, "height": 768})
        page = context.new_page()

        print("🚀 [1/4] Realizando Login no CRM...")
        page.goto(config["CRM_URL"])
        page.fill('input[type="email"]', config["CRM_EMAIL"])
        page.fill('input[type="password"]', config["CRM_SENHA"])
        page.keyboard.press("Enter")

        time.sleep(5)
        print("📂 [2/4] Acessando aba de Pedidos...")
        page.goto(config["CRM_PEDIDOS_URL"])
        page.wait_for_selector(".fa-list-alt", timeout=15000)
        page.evaluate("document.querySelector('.fa-list-alt').closest('.bubble-element').click()")
        time.sleep(5)

        # Localiza os dropdowns
        select_consultor = page.locator("select:has(option:has-text('Selecione um Consultor'))").first
        select_status = page.locator("select:has(option:has-text('Selecione um STATUS'))").first

        print("👥 [3/4] Mapeando os consultores do sistema...")
        opcoes_brutas = select_consultor.locator("option").all_inner_texts()
        lista_consultores = [n.strip() for n in opcoes_brutas if n.strip() and "Selecione" not in n]

        total_geral_pedidos = 0
        datas_pedidos = []  # Para descobrir o período exato dos pedidos travados

        print(f"🔎 Iniciando pesquisa individual para {len(lista_consultores)} consultores...")

        for nome in lista_consultores:
            print(f"\n👉 Consultando carteira de: {nome}")

            # Limpa o filtro anterior para não bugar o cache do Bubble
            try:
                page.locator('text="Limpar Filtros"').click(timeout=2000)
            except Exception:
                pass

            # Seleciona o Consultor da vez
            try:
                select_consultor.select_option(label=nome)
                time.sleep(1)
            except Exception:
                print(f"  ❌ Falha ao clicar no consultor {nome}.")
                continue

            # Seleciona o Status Aguardando Aceite
            try:
                select_status.select_option(label=STATUS_ALVO)
                time.sleep(5)  # Delay vital para o Bubble carregar os dados
            except Exception:
                print("  ❌ Falha ao selecionar status.")
                continue

            # Lê a quantidade que o sistema diz ter
            try:
                qtd_txt = page.locator(r"text=/QTD - \d+/").first.inner_text(timeout=3000)
                qtd_esperada = extrair_quantidade(qtd_txt)
            except Exception:
                qtd_esperada = 0

            if qtd_esperada <= 0:
                print("  ✅ Tudo limpo.")
                continue

            print(f"  👀 Sistema informa {qtd_esperada} pedidos. Processando...")

            # Rola a tela para carregar todos os cards
            cards_locator = page.locator(".bubble-element.GroupItem")
            itens_atuais = 0
            tentativas_vazias = 0

            while itens_atuais < qtd_esperada and tentativas_vazias < 4:
                page.mouse.wheel(0, 3000)
                time.sleep(2)

                novos_itens = cards_locator.count()
                if novos_itens == itens_atuais:
                    tentativas_vazias += 1
                else:
                    itens_atuais = novos_itens
                    tentativas_vazias = 0

            # Validação blindada dos cards na tela (lê sob demanda até bater a quantidade)
            textos_cards = (cards_locator.nth(i).inner_text() for i in range(cards_locator.count()))
            pedidos_pessoa = filtrar_pedidos(textos_cards, nome, qtd_esperada)
            qtd_real = len(pedidos_pessoa)

            if qtd_real == 0:
                print("  -> Alarme Falso do sistema. Eram apenas cards antigos em cache.")
                continue

            total_geral_pedidos += qtd_real
            datas_pedidos.extend(p["data"] for p in pedidos_pessoa)
            print(f"  ✅ Confirmado: {qtd_real} pedidos legítimos.")

            numero_destino = equipe.get(nome)
            if numero_destino:
                enviar_whatsapp(config, numero_destino, montar_mensagem_individual(nome, pedidos_pessoa))
            elif config["WHATSAPP_SUPERVISOR"]:
                # Falha de segurança: Número não existe na lista. Envia para o supervisor resolver.
                print("  ⚠️ Telefone ausente. Enviando alerta pro Supervisor.")
                enviar_whatsapp(config, config["WHATSAPP_SUPERVISOR"], montar_alerta_supervisor(nome, pedidos_pessoa))
            else:
                print("  ⚠️ Telefone ausente e WHATSAPP_SUPERVISOR não configurado. Alerta não enviado.")

        # 4. DISPARO FINAL (Relatório Diretoria e Grupo)
        if total_geral_pedidos > 0:
            print("\n📢 [4/4] Disparando resumo final para Diretoria e Grupo...")

            data_inicio, data_fim = calcular_periodo(datas_pedidos)
            resumo = montar_resumo(total_geral_pedidos, data_inicio, data_fim)

            # Dispara para a Diretoria
            enviar_whatsapp(config, config["WHATSAPP_DIRETORIA"], resumo)

            # Dispara para o Grupo da equipe
            if config["WHATSAPP_GRUPO"]:
                print("  Enviando para o Grupo...")
                enviar_whatsapp(config, config["WHATSAPP_GRUPO"], resumo)
        else:
            print("\n✅ Zero pendências hoje na equipe inteira. Meta em dia!")

        browser.close()


def main():
    if load_dotenv:
        load_dotenv()
    try:
        config = carregar_config()
        equipe = carregar_equipe(config["EQUIPE_ARQUIVO"])
    except ConfigError as e:
        print(f"❌ Erro de configuração: {e}", file=sys.stderr)
        sys.exit(1)
    buscar_e_notificar(config, equipe)


if __name__ == "__main__":
    main()
