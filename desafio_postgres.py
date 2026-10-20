"""Desafio extra: grava as movimentações do extrato OFX no PostgreSQL."""

from pathlib import Path

import psycopg2
from ofxparse import OfxParser

CONEXAO = {
    "host": "localhost",
    "port": 5432,
    "dbname": "postgres",
    "user": "postgres",
    "password": "123456",
}

caminho_extrato = Path(__file__).parent / "extrato.ofx"

with open(caminho_extrato, "rb") as arquivo:
    ofx = OfxParser.parse(arquivo)

transacoes = ofx.account.statement.transactions

try:
    conexao = psycopg2.connect(**CONEXAO)
except UnicodeDecodeError:

    raise SystemExit(
        "Não foi possível conectar: verifique o usuário e a senha em CONEXAO."
    ) from None

cursor = conexao.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS movimentacoes (
        id SERIAL PRIMARY KEY,
        data_movimentacao DATE,
        valor NUMERIC(15,2),
        descricao VARCHAR(255)
    )
""")

cursor.execute("""
    ALTER TABLE movimentacoes
    ADD COLUMN IF NOT EXISTS fitid VARCHAR(255) UNIQUE
""")

inseridas = 0
duplicadas = 0

for t in transacoes:

    cursor.execute(
        """
        INSERT INTO movimentacoes (data_movimentacao, valor, descricao, fitid)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (fitid) DO NOTHING
        """,
        (t.date.date(), t.amount, t.memo, t.id),
    )

    if cursor.rowcount == 1:
        inseridas += 1
    else:
        duplicadas += 1

conexao.commit()
cursor.close()
conexao.close()

print(f"Movimentações lidas do arquivo : {len(transacoes)}")
print(f"Inseridas no banco             : {inseridas}")
print(f"Ignoradas (já existiam)        : {duplicadas}")
