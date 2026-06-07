"""
Testes Unitários — Mobilidade Inteligente
==========================================
Testam funções isoladas, sem dependência de banco de dados ou interface.
"""

import hashlib
import pytest
from collections import Counter
from unittest.mock import patch, MagicMock
import pandas as pd
import sys
import os

# Adiciona o diretório raiz ao path para importar o app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import hash_password, count_series, route_candidates


# ─────────────────────────────────────────────
# hash_password
# ─────────────────────────────────────────────

class TestHashPassword:
    def test_retorna_string(self):
        """hash_password deve retornar uma string."""
        resultado = hash_password("minhasenha")
        assert isinstance(resultado, str)

    def test_hash_consistente(self):
        """A mesma senha deve sempre gerar o mesmo hash."""
        assert hash_password("abc123") == hash_password("abc123")

    def test_senhas_diferentes_geram_hashes_diferentes(self):
        """Senhas distintas não devem produzir o mesmo hash."""
        assert hash_password("senha1") != hash_password("senha2")

    def test_hash_e_sha256(self):
        """O hash gerado deve corresponder ao SHA-256 da senha."""
        senha = "teste_unitario"
        esperado = hashlib.sha256(senha.encode("utf-8")).hexdigest()
        assert hash_password(senha) == esperado

    def test_senha_vazia(self):
        """Senha vazia deve gerar hash válido (SHA-256 de string vazia)."""
        resultado = hash_password("")
        assert len(resultado) == 64  # SHA-256 sempre tem 64 caracteres hex

    def test_senha_com_caracteres_especiais(self):
        """Senha com caracteres especiais deve ser processada corretamente."""
        resultado = hash_password("s3nh@#!çã")
        assert isinstance(resultado, str)
        assert len(resultado) == 64


# ─────────────────────────────────────────────
# count_series
# ─────────────────────────────────────────────

class TestCountSeries:
    def test_retorna_dataframe(self):
        """Deve retornar um DataFrame."""
        serie = pd.Series(["Centro", "Bairro A", "Centro"])
        resultado = count_series(serie)
        assert isinstance(resultado, pd.DataFrame)

    def test_colunas_corretas(self):
        """DataFrame deve ter colunas 'Local' e 'Pedidos'."""
        serie = pd.Series(["Centro", "Centro", "Bairro A"])
        resultado = count_series(serie)
        assert list(resultado.columns) == ["Local", "Pedidos"]

    def test_contagem_correta(self):
        """Deve contar corretamente as ocorrências."""
        serie = pd.Series(["centro", "centro", "bairro a"])
        resultado = count_series(serie)
        assert resultado[resultado["Local"] == "Centro"]["Pedidos"].values[0] == 2

    def test_normaliza_capitalização(self):
        """Entradas com capitalização diferente devem ser agrupadas."""
        serie = pd.Series(["centro", "CENTRO", "Centro"])
        resultado = count_series(serie)
        assert len(resultado) == 1
        assert resultado["Pedidos"].values[0] == 3

    def test_ignora_valores_vazios(self):
        """Strings vazias e NaN devem ser ignorados."""
        serie = pd.Series(["Centro", "", None, "Centro"])
        resultado = count_series(serie)
        assert len(resultado) == 1
        assert resultado["Pedidos"].values[0] == 2

    def test_serie_vazia(self):
        """Série vazia deve retornar DataFrame vazio."""
        serie = pd.Series([], dtype=str)
        resultado = count_series(serie)
        assert resultado.empty

    def test_ordenado_por_mais_pedidos(self):
        """Resultado deve estar ordenado do mais para o menos pedido."""
        serie = pd.Series(["A", "B", "B", "B", "A", "C"])
        resultado = count_series(serie)
        assert resultado["Pedidos"].tolist() == sorted(resultado["Pedidos"].tolist(), reverse=True)


# ─────────────────────────────────────────────
# route_candidates
# ─────────────────────────────────────────────

class TestRouteCandidates:
    def _make_df(self, pairs):
        """Cria um DataFrame de solicitações a partir de pares (origem, destino)."""
        return pd.DataFrame(pairs, columns=["origin", "destination"])

    def test_retorna_dataframe(self):
        """Deve retornar um DataFrame."""
        df = self._make_df([("Centro", "Bairro A")])
        resultado = route_candidates(df)
        assert isinstance(resultado, pd.DataFrame)

    def test_colunas_corretas(self):
        """DataFrame deve ter colunas 'Origem', 'Destino' e 'Pedidos'."""
        df = self._make_df([("Centro", "Bairro A")])
        resultado = route_candidates(df)
        assert list(resultado.columns) == ["Origem", "Destino", "Pedidos"]

    def test_df_vazio_retorna_vazio(self):
        """DataFrame vazio deve retornar DataFrame vazio com as colunas corretas."""
        resultado = route_candidates(pd.DataFrame())
        assert resultado.empty
        assert list(resultado.columns) == ["Origem", "Destino", "Pedidos"]

    def test_conta_rotas_corretamente(self):
        """Deve contar pares origem-destino corretamente."""
        df = self._make_df([
            ("Centro", "Bairro A"),
            ("Centro", "Bairro A"),
            ("Bairro A", "Centro"),
        ])
        resultado = route_candidates(df)
        rota = resultado[(resultado["Origem"] == "Centro") & (resultado["Destino"] == "Bairro A")]
        assert rota["Pedidos"].values[0] == 2

    def test_rotas_distintas_nao_agrupadas(self):
        """Centro→A e A→Centro devem ser rotas separadas."""
        df = self._make_df([
            ("Centro", "Bairro A"),
            ("Bairro A", "Centro"),
        ])
        resultado = route_candidates(df)
        assert len(resultado) == 2

    def test_ordenado_por_mais_pedidos(self):
        """Rotas devem aparecer ordenadas da mais pedida para a menos pedida."""
        df = self._make_df([
            ("X", "Y"), ("X", "Y"), ("X", "Y"),
            ("A", "B"), ("A", "B"),
            ("C", "D"),
        ])
        resultado = route_candidates(df)
        assert resultado["Pedidos"].tolist() == sorted(resultado["Pedidos"].tolist(), reverse=True)
