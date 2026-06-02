# Mobilidade Inteligente

Sistema em Python para dois tipos de usuários:

- Passageiros informam origem, destino e data desejada.
- Empresas visualizam os locais e rotas mais requisitados para planejar linhas de ônibus.

## Como executar

1. Instale as dependências:

```bash
pip install -r requirements.txt
```

2. Inicie o app:

```bash
streamlit run app.py
```

## Como funciona

- Os pedidos são salvos localmente em um banco SQLite.
- O painel da empresa mostra métricas, locais mais pedidos e combinações origem/destino mais frequentes.