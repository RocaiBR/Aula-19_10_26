"""Atividade prática: exibe as movimentações do extrato OFX com totais e saldo."""

from pathlib import Path

from ofxparse import OfxParser

caminho_extrato = Path(__file__).parent / "extrato.ofx"

with open(caminho_extrato, "rb") as arquivo:
    ofx = OfxParser.parse(arquivo)

transacoes = ofx.account.statement.transactions

entradas = 0
saidas = 0

print("=" * 40)
print("EXTRATO BANCÁRIO".center(40))
print("=" * 40)

for t in transacoes:

    print(f"""
Data      : {t.date.strftime('%d/%m/%Y')}
Valor     : R$ {t.amount:.2f}
Descrição : {t.memo}
----------------------------------------""")

    if t.amount > 0:
        entradas += t.amount
    else:
        saidas += t.amount

saldo = entradas + saidas

print()
print("=" * 40)
print("RESUMO".center(40))
print("=" * 40)
print(f"Quantidade de movimentações : {len(transacoes)}")
print(f"Total de entradas           : R$ {entradas:.2f}")
print(f"Total de saídas             : R$ {saidas:.2f}")
print(f"Saldo calculado             : R$ {saldo:.2f}")
