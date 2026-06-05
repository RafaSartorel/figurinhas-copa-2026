# Figurinhas Copa 2026 - Base oficial

Repositório para manter a base oficial das figurinhas do álbum da Copa 2026.

## Arquivo principal

- `data/inventory.json`: base oficial para o GPT consultar.
- `data/inventory.csv`: versão em tabela, útil para conferência manual.

## Padrão de identificação

Cada figurinha usa o padrão:

```text
<SIGLA><NÚMERO COM 2 DÍGITOS>
```

Exemplos:

```text
BEL12
SCO10
BRA02
ARG15
```

## Como usar com GPT

1. O GPT analisa a foto.
2. Extrai as figurinhas identificadas.
3. Normaliza para o padrão `TEAM_CODE + 2_DIGIT_NUMBER`.
4. Compara com `data/inventory.json`.
5. Retorna novas, repetidas e dúvidas.

## URL raw

Depois de subir o arquivo no GitHub, a URL raw terá este formato:

```text
https://raw.githubusercontent.com/SEU_USUARIO/figurinhas-copa-2026/main/data/inventory.json
```

Substitua `SEU_USUARIO` pelo seu usuário do GitHub.
