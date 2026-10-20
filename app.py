"""Front end em terminal para o projeto de leitura de extratos OFX."""

import getpass
import os
from pathlib import Path

import psycopg2
from ofxparse import OfxParser

# Dados de conexão com o PostgreSQL (a senha é pedida ao usar o banco)
CONEXAO = {
    "host": "localhost",
    "port": 5432,
    "dbname": "postgres",
    "user": "postgres",
}

ARQUIVO_PADRAO = Path(__file__).parent / "extrato.ofx"

LARGURA = 70
VERDE = "\033[32m"
VERMELHO = "\033[31m"
NORMAL = "\033[0m"


# ---------------------------------------------------------------------------
# Funções de apoio para a tela
# ---------------------------------------------------------------------------

def limpar_tela():
    """Limpa o terminal (no Windows também ativa as cores ANSI)."""
    os.system("cls" if os.name == "nt" else "clear")


def titulo(texto):
    """Exibe um título centralizado entre linhas."""
    print("=" * LARGURA)
    print(texto.center(LARGURA))
    print("=" * LARGURA)


def formatar_moeda(valor):
    """Formata um valor no padrão brasileiro, por exemplo: R$ -1.234,56."""
    numero = f"{abs(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    sinal = "-" if valor < 0 else ""
    return f"{sinal}R$ {numero}"


def colorir(valor, texto):
    """Pinta o texto de verde para valores positivos e de vermelho para negativos."""
    cor = VERDE if valor >= 0 else VERMELHO
    return f"{cor}{texto}{NORMAL}"


def mostrar_tabela(movimentacoes):
    """Exibe uma lista de (data, valor, descricao) em formato de tabela."""
    print(f"{'DATA':<12}{'VALOR':>16}   DESCRIÇÃO")
    print("-" * LARGURA)

    for data, valor, descricao in movimentacoes:
        valor_formatado = colorir(valor, f"{formatar_moeda(valor):>16}")
        print(f"{data.strftime('%d/%m/%Y'):<12}{valor_formatado}   {descricao}")

    print("-" * LARGURA)
    print(f"Quantidade de movimentações: {len(movimentacoes)}")


def mostrar_resumo(valores):
    """Exibe a quantidade, o total de entradas, o total de saídas e o saldo."""
    entradas = sum(v for v in valores if v > 0)
    saidas = sum(v for v in valores if v < 0)
    saldo = entradas + saidas

    print(f"Quantidade de movimentações : {len(valores)}")
    print(f"Total de entradas           : {colorir(entradas, formatar_moeda(entradas))}")
    print(f"Total de saídas             : {colorir(saidas, formatar_moeda(saidas))}")
    print(f"Saldo calculado             : {colorir(saldo, formatar_moeda(saldo))}")


# ---------------------------------------------------------------------------
# Arquivo OFX
# ---------------------------------------------------------------------------

def carregar_arquivo(estado, caminho):
    """Lê o arquivo OFX e guarda as transações no estado. Retorna True se deu certo."""
    try:
        with open(caminho, "rb") as arquivo:
            ofx = OfxParser.parse(arquivo)
        transacoes = ofx.account.statement.transactions
    except FileNotFoundError:
        print(f"Arquivo não encontrado: {caminho}")
        return False
    except Exception as erro:  # pylint: disable=broad-exception-caught
        # O ofxparse lança tipos de erro diferentes para cada problema no arquivo
        print(f"Não foi possível ler o arquivo OFX: {erro}")
        return False

    estado["caminho"] = Path(caminho)
    estado["transacoes"] = transacoes
    return True


def arquivo_carregado(estado):
    """Avisa o usuário e retorna False quando nenhum extrato foi carregado."""
    if not estado["transacoes"]:
        print("Nenhum extrato carregado. Use a opção 3 para carregar um arquivo OFX.")
        return False
    return True


def ver_extrato(estado):
    """Opção 1: lista as movimentações do arquivo OFX."""
    titulo(f"EXTRATO - {estado['caminho'].name}" if estado["caminho"] else "EXTRATO")
    if not arquivo_carregado(estado):
        return

    mostrar_tabela([(t.date, t.amount, t.memo) for t in estado["transacoes"]])


def ver_resumo(estado):
    """Opção 2: mostra os totais do arquivo OFX."""
    titulo("RESUMO DO EXTRATO")
    if not arquivo_carregado(estado):
        return

    mostrar_resumo([t.amount for t in estado["transacoes"]])


def carregar_outro_arquivo(estado):
    """Opção 3: pede o caminho de um novo arquivo OFX."""
    titulo("CARREGAR ARQUIVO OFX")
    print("Digite o caminho do arquivo (ou deixe em branco para cancelar).")
    caminho = input("> ").strip().strip('"')

    if not caminho:
        print("Operação cancelada.")
        return

    if carregar_arquivo(estado, caminho):
        print(f"Arquivo carregado: {len(estado['transacoes'])} movimentações encontradas.")


# ---------------------------------------------------------------------------
# Banco de dados PostgreSQL
# ---------------------------------------------------------------------------

def conectar(estado):
    """Abre a conexão com o PostgreSQL, pedindo a senha na primeira vez."""
    if estado["senha"] is None:
        print("(a senha não aparece enquanto você digita)")
        estado["senha"] = getpass.getpass(f"Senha do usuário '{CONEXAO['user']}': ")

    try:
        return psycopg2.connect(**CONEXAO, password=estado["senha"], connect_timeout=5)
    except UnicodeDecodeError:
        # No Windows em português, o erro de senha inválida vem com acentos
        # que o psycopg2 não consegue ler
        print("Não foi possível conectar: verifique o usuário e a senha.")
    except psycopg2.OperationalError as erro:
        print(f"Não foi possível conectar ao PostgreSQL: {erro}")

    # Esquece a senha para que ela seja pedida de novo na próxima tentativa
    estado["senha"] = None
    return None


def criar_tabela(cursor):
    """Cria a tabela movimentacoes, caso ainda não exista."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movimentacoes (
            id SERIAL PRIMARY KEY,
            data_movimentacao DATE,
            valor NUMERIC(15,2),
            descricao VARCHAR(255)
        )
    """)

    # O FITID identifica cada transação; o UNIQUE impede gravar duplicadas
    cursor.execute("""
        ALTER TABLE movimentacoes
        ADD COLUMN IF NOT EXISTS fitid VARCHAR(255) UNIQUE
    """)


def gravar_transacoes(cursor, transacoes):
    """Insere as transações na tabela e retorna quantas foram realmente gravadas."""
    inseridas = 0

    for t in transacoes:
        cursor.execute(
            """
            INSERT INTO movimentacoes (data_movimentacao, valor, descricao, fitid)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (fitid) DO NOTHING
            """,
            (t.date.date(), t.amount, t.memo, t.id),
        )
        # rowcount = 1 quando inseriu; 0 quando o FITID já existia
        inseridas += cursor.rowcount

    return inseridas


def importar_para_banco(estado):
    """Opção 4: grava as movimentações do OFX na tabela movimentacoes."""
    titulo("IMPORTAR PARA O POSTGRESQL")
    if not arquivo_carregado(estado):
        return

    conexao = conectar(estado)
    if conexao is None:
        return

    transacoes = estado["transacoes"]

    try:
        # O "with conexao" faz o commit no final (ou desfaz tudo se der erro)
        with conexao, conexao.cursor() as cursor:
            criar_tabela(cursor)
            inseridas = gravar_transacoes(cursor, transacoes)
    except psycopg2.Error as erro:
        print(f"Erro no banco de dados, nada foi gravado: {erro}")
        return
    finally:
        conexao.close()

    print(f"Movimentações no arquivo  : {len(transacoes)}")
    print(f"Inseridas no banco        : {inseridas}")
    print(f"Ignoradas (já existiam)   : {len(transacoes) - inseridas}")


def consultar_banco(estado):
    """Opção 5: mostra o que já está gravado na tabela movimentacoes."""
    titulo("MOVIMENTAÇÕES GRAVADAS NO BANCO")

    conexao = conectar(estado)
    if conexao is None:
        return

    linhas = []
    try:
        with conexao, conexao.cursor() as cursor:
            cursor.execute("SELECT to_regclass('movimentacoes')")
            tabela_existe = cursor.fetchone()[0] is not None

            if tabela_existe:
                cursor.execute("""
                    SELECT data_movimentacao, valor, descricao
                    FROM movimentacoes
                    ORDER BY data_movimentacao, id
                """)
                linhas = cursor.fetchall()
    except psycopg2.Error as erro:
        print(f"Erro no banco de dados: {erro}")
        return
    finally:
        conexao.close()

    if not linhas:
        print("Nenhuma movimentação gravada ainda. Use a opção 4 para importar.")
        return

    mostrar_tabela(linhas)
    print()
    mostrar_resumo([valor for _, valor, _ in linhas])


# ---------------------------------------------------------------------------
# Menu principal
# ---------------------------------------------------------------------------

OPCOES = {
    "1": ("Ver extrato", ver_extrato),
    "2": ("Ver resumo (entradas, saídas e saldo)", ver_resumo),
    "3": ("Carregar outro arquivo OFX", carregar_outro_arquivo),
    "4": ("Importar movimentações para o PostgreSQL", importar_para_banco),
    "5": ("Consultar movimentações gravadas no banco", consultar_banco),
}


def mostrar_menu(estado):
    """Exibe o cabeçalho com o arquivo atual e as opções do menu."""
    titulo("LEITOR DE EXTRATOS OFX")

    if estado["transacoes"]:
        quantidade = len(estado["transacoes"])
        print(f"Arquivo: {estado['caminho'].name} ({quantidade} movimentações)")
    else:
        print("Arquivo: nenhum extrato carregado")

    print()
    for numero, (descricao, _) in OPCOES.items():
        print(f"  [{numero}] {descricao}")
    print("  [0] Sair")


def main():
    """Mantém o menu na tela até o usuário escolher sair."""
    estado = {"caminho": None, "transacoes": [], "senha": None}
    carregar_arquivo(estado, ARQUIVO_PADRAO)

    while True:
        limpar_tela()
        mostrar_menu(estado)
        escolha = input("\nEscolha uma opção: ").strip()

        if escolha == "0":
            print("Até logo!")
            break

        if escolha in OPCOES:
            limpar_tela()
            _, acao = OPCOES[escolha]
            acao(estado)
        else:
            print("Opção inválida.")

        input("\nPressione ENTER para voltar ao menu...")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nPrograma encerrado.")
