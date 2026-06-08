"""
Testes Unitários — Mobilidade Inteligente
==========================================
Testam funções isoladas, sem dependência de banco de dados ou interface.
"""

import hashlib
import sqlite3
import pytest
from collections import Counter
from unittest.mock import patch, MagicMock
import pandas as pd
import sys
import os

# Adiciona o diretório raiz ao path para importar o app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import hash_password, count_series, route_candidates, connect_db, init_db


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


# ─────────────────────────────────────────────
# connect_db
# ─────────────────────────────────────────────

class TestConnectDb:
    def test_retorna_conexao_valida(self, tmp_path):
        """connect_db deve retornar uma conexão SQLite funcional."""
        with patch("app.DB_PATH", tmp_path / "test.db"):
            conn = connect_db()
            assert conn is not None
            conn.close()

    def test_row_factory_configurada(self, tmp_path):
        """A conexão deve usar row_factory para acesso por nome de coluna."""
        with patch("app.DB_PATH", tmp_path / "test.db"):
            conn = connect_db()
            assert conn.row_factory == sqlite3.Row
            conn.close()

    def test_cria_arquivo_de_banco(self, tmp_path):
        """O arquivo do banco deve ser criado no caminho configurado."""
        db_path = tmp_path / "test.db"
        with patch("app.DB_PATH", db_path):
            conn = connect_db()
            conn.close()
        assert db_path.exists()


# ─────────────────────────────────────────────
# init_db
# ─────────────────────────────────────────────

class TestInitDb:
    def test_cria_tabela_users(self, tmp_path):
        """init_db deve criar a tabela 'users'."""
        with patch("app.DB_PATH", tmp_path / "test.db"):
            init_db()
            conn = connect_db()
            tabelas = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            nomes = [t["name"] for t in tabelas]
            assert "users" in nomes
            conn.close()

    def test_cria_tabela_trip_requests(self, tmp_path):
        """init_db deve criar a tabela 'trip_requests'."""
        with patch("app.DB_PATH", tmp_path / "test.db"):
            init_db()
            conn = connect_db()
            tabelas = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            nomes = [t["name"] for t in tabelas]
            assert "trip_requests" in nomes
            conn.close()

    def test_idempotente(self, tmp_path):
        """Chamar init_db duas vezes não deve gerar erro (IF NOT EXISTS)."""
        with patch("app.DB_PATH", tmp_path / "test.db"):
            init_db()
            init_db()  # segunda chamada não deve lançar exceção

    def test_tabela_users_tem_colunas_corretas(self, tmp_path):
        """A tabela users deve ter todas as colunas esperadas."""
        with patch("app.DB_PATH", tmp_path / "test.db"):
            init_db()
            conn = connect_db()
            colunas = conn.execute("PRAGMA table_info(users)").fetchall()
            nomes = [col["name"] for col in colunas]
            for esperada in ["id", "name", "email", "password_hash", "role", "created_at"]:
                assert esperada in nomes
            conn.close()

    def test_tabela_trip_requests_tem_colunas_corretas(self, tmp_path):
        """A tabela trip_requests deve ter todas as colunas esperadas."""
        with patch("app.DB_PATH", tmp_path / "test.db"):
            init_db()
            conn = connect_db()
            colunas = conn.execute("PRAGMA table_info(trip_requests)").fetchall()
            nomes = [col["name"] for col in colunas]
            for esperada in ["id", "passenger_name", "origin", "destination", "travel_date", "notes", "created_at"]:
                assert esperada in nomes
            conn.close()
