# Testes de qualidade do ChargeSense

Suíte complementar produzida para o trabalho de Qualidade de Software.
Os testes utilizam diretamente `../backend` e `../firmware/esp32`, sem duplicar o código de produção.

## Execução

Requisitos: Linux/WSL, Python 3.12 e GCC.
A partir da raiz do repositório:

```bash
python -m venv quality/.venv
source quality/.venv/bin/activate
python -m pip install -r quality/requirements-lock.txt
python quality/run_tests.py
python quality/load_test.py
```

O primeiro comando de testes reúne 95 casos complementares e 15 testes originais do backend,
incluindo compilação e execução dos testes nativos de medição em C.
Resultado de referência: **108 passed e 2 xfailed**.
Os dois `xfail(strict=True)` de TC14 documentam uma regra proposta de tipagem numérica estrita;
a API atualmente aceita coerção de booleanos/textos, comportamento caracterizado por TC13.
Eles não representam critérios aprovados nem testes corrigidos.

O teste de carga inicia um servidor HTTP local em porta dinâmica, com banco temporário e
chaves fictícias. São 2.000 requisições, 50% POST e 50% GET, com concorrências 1, 5, 20 e 50.
Não acessa a infraestrutura externa. Os resultados não equivalem a desempenho de produção.

Relatórios JUnit, cobertura e carga são gerados em `quality/evidence/` e não são versionados.
Uma nova execução sobrescreve os relatórios correspondentes.
`rastreabilidade.csv` relaciona TC01–TC17 aos requisitos e resultados esperados.
Não houve teste físico de sensores ou desligamento nesta suíte.
