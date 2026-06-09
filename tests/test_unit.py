"""
Testes Unitários — Mobilidade Inteligente
==========================================
Testam funções isoladas, sem dependência de banco de dados ou interface.
"""

import hashlib
import sqlite3
import pytest
from collections import Counter
from unittest.mock import patch
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import (
    hash_password,
    count_series,
    route_candidates,
    connect_db,
    init_db,
    search_routes_by_stop,
    load_routes,
)


# ─────────────────────────────────────────────
# hash_password
# ─────────────────────────────────────────────

class TestHashPassword:
    def test_retorna_string(self):
        """hash_password deve retornar uma string."""
        assert isinstance(hash_password("minhasenha"), str)

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
        """Senha vazia deve gerar hash SHA-256 válido (64 caracteres hex)."""
        assert len(hash_password("")) == 64

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
        resultado = count_series(pd.Series(["Centro", "Bairro A", "Centro"]))
        assert isinstance(resultado, pd.DataFrame)

    def test_colunas_corretas(self):
        resultado = count_series(pd.Series(["Centro", "Centro", "Bairro A"]))
        assert list(resultado.columns) == ["Local", "Pedidos"]

    def test_contagem_correta(self):
        resultado = count_series(pd.Series(["centro", "centro", "bairro a"]))
        assert resultado[resultado["Local"] == "Centro"]["Pedidos"].values[0] == 2

    def test_normaliza_capitalizacao(self):
        resultado = count_series(pd.Series(["centro", "CENTRO", "Centro"]))
        assert len(resultado) == 1
        assert resultado["Pedidos"].values[0] == 3

    def test_ignora_valores_vazios(self):
        resultado = count_series(pd.Series(["Centro", "", None, "Centro"]))
        assert len(resultado) == 1
        assert resultado["Pedidos"].values[0] == 2

    def test_serie_vazia(self):
        assert count_series(pd.Series([], dtype=str)).empty

    def test_ordenado_por_mais_pedidos(self):
        resultado = count_series(pd.Series(["A", "B", "B", "B", "A", "C"]))
        pedidos = resultado["Pedidos"].tolist()
        assert pedidos == sorted(pedidos, reverse=True)


# ─────────────────────────────────────────────
# route_candidates
# ─────────────────────────────────────────────

class TestRouteCandidates:
    def _df(self, pairs):
        return pd.DataFrame(pairs, columns=["origin", "destination"])

    def test_retorna_dataframe(self):
        assert isinstance(route_candidates(self._df([("Centro", "Bairro A")])), pd.DataFrame)

    def test_colunas_corretas(self):
        resultado = route_candidates(self._df([("Centro", "Bairro A")]))
        assert list(resultado.columns) == ["Origem", "Destino", "Pedidos"]

    def test_df_vazio_retorna_vazio(self):
        resultado = route_candidates(pd.DataFrame())
        assert resultado.empty
        assert list(resultado.columns) == ["Origem", "Destino", "Pedidos"]

    def test_conta_rotas_corretamente(self):
        df = self._df([("Centro", "Bairro A"), ("Centro", "Bairro A"), ("Bairro A", "Centro")])
        resultado = route_candidates(df)
        rota = resultado[(resultado["Origem"] == "Centro") & (resultado["Destino"] == "Bairro A")]
        assert rota["Pedidos"].values[0] == 2

    def test_rotas_distintas_nao_agrupadas(self):
        df = self._df([("Centro", "Bairro A"), ("Bairro A", "Centro")])
        assert len(route_candidates(df)) == 2

    def test_ordenado_por_mais_pedidos(self):
        df = self._df([("X","Y"),("X","Y"),("X","Y"),("A","B"),("A","B"),("C","D")])
        resultado = route_candidates(df)
        pedidos = resultado["Pedidos"].tolist()
        assert pedidos == sorted(pedidos, reverse=True)


# ─────────────────────────────────────────────
# connect_db
# ─────────────────────────────────────────────

class TestConnectDb:
    def test_retorna_conexao_valida(self, tmp_path):
        with patch("app.DB_PATH", tmp_path / "test.db"):
            conn = connect_db()
            assert conn is not None
            conn.close()

    def test_row_factory_configurada(self, tmp_path):
        with patch("app.DB_PATH", tmp_path / "test.db"):
            conn = connect_db()
            assert conn.row_factory == sqlite3.Row
            conn.close()

    def test_cria_arquivo_de_banco(self, tmp_path):
        db_path = tmp_path / "test.db"
        with patch("app.DB_PATH", db_path):
            connect_db().close()
        assert db_path.exists()


# ─────────────────────────────────────────────
# init_db
# ─────────────────────────────────────────────

class TestInitDb:
    def _tabelas(self, tmp_path):
        with patch("app.DB_PATH", tmp_path / "test.db"):
            init_db()
            conn = connect_db()
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            conn.close()
            return [r["name"] for r in rows]

    def test_cria_tabela_users(self, tmp_path):
        assert "users" in self._tabelas(tmp_path)

    def test_cria_tabela_trip_requests(self, tmp_path):
        assert "trip_requests" in self._tabelas(tmp_path)

    def test_cria_tabela_routes(self, tmp_path):
        assert "routes" in self._tabelas(tmp_path)

    def test_cria_tabela_enrollments(self, tmp_path):
        assert "enrollments" in self._tabelas(tmp_path)

    def test_idempotente(self, tmp_path):
        with patch("app.DB_PATH", tmp_path / "test.db"):
            init_db()
            init_db()  # não deve lançar exceção

    def test_colunas_users(self, tmp_path):
        with patch("app.DB_PATH", tmp_path / "test.db"):
            init_db()
            conn = connect_db()
            nomes = [c["name"] for c in conn.execute("PRAGMA table_info(users)").fetchall()]
            conn.close()
        for col in ["id", "name", "email", "password_hash", "role", "created_at"]:
            assert col in nomes

    def test_colunas_routes(self, tmp_path):
        with patch("app.DB_PATH", tmp_path / "test.db"):
            init_db()
            conn = connect_db()
            nomes = [c["name"] for c in conn.execute("PRAGMA table_info(routes)").fetchall()]
            conn.close()
        for col in ["id", "company_email", "name", "origin", "departure_time", "stops", "capacity", "active"]:
            assert col in nomes

    def test_colunas_enrollments(self, tmp_path):
        with patch("app.DB_PATH", tmp_path / "test.db"):
            init_db()
            conn = connect_db()
            nomes = [c["name"] for c in conn.execute("PRAGMA table_info(enrollments)").fetchall()]
            conn.close()
        for col in ["id", "route_id", "passenger_email", "passenger_name", "enrolled_at"]:
            assert col in nomes


# ─────────────────────────────────────────────
# search_routes_by_stop
# ─────────────────────────────────────────────

class TestSearchRoutesByStop:
    def test_query_vazia_retorna_lista_vazia(self):
        """String vazia não deve disparar nenhuma busca."""
        resultado = search_routes_by_stop("")
        assert resultado == []

    def test_query_so_espacos_retorna_vazia(self):
        resultado = search_routes_by_stop("   ")
        assert resultado == []

    def test_encontra_por_origem(self):
        """Deve encontrar rota cujo ponto de partida contém o termo."""
        rota_mock = {
            "id": 1, "name": "Linha A", "origin": "Terminal Central",
            "departure_time": "07:00", "stops": [{"local": "Bairro X", "horario": "07:15"}],
            "capacity": 40, "enrolled": 5, "active": 1,
        }
        with patch("app.load_routes", return_value=[rota_mock]):
            resultado = search_routes_by_stop("terminal")
        assert len(resultado) == 1
        assert resultado[0]["name"] == "Linha A"

    def test_encontra_por_parada(self):
        """Deve encontrar rota cujo ponto de parada contém o termo."""
        rota_mock = {
            "id": 2, "name": "Linha B", "origin": "Garagem",
            "departure_time": "08:00", "stops": [{"local": "Universidade Federal", "horario": "08:30"}],
            "capacity": 30, "enrolled": 0, "active": 1,
        }
        with patch("app.load_routes", return_value=[rota_mock]):
            resultado = search_routes_by_stop("universidade")
        assert len(resultado) == 1

    def test_busca_case_insensitive(self):
        """Busca deve ignorar maiúsculas e minúsculas."""
        rota_mock = {
            "id": 3, "name": "Linha C", "origin": "Praça da Sé",
            "departure_time": "09:00", "stops": [],
            "capacity": 20, "enrolled": 0, "active": 1,
        }
        with patch("app.load_routes", return_value=[rota_mock]):
            assert len(search_routes_by_stop("PRAÇA")) == 1
            assert len(search_routes_by_stop("praça")) == 1

    def test_nao_encontra_termo_inexistente(self):
        """Termo que não aparece em nenhuma rota deve retornar lista vazia."""
        rota_mock = {
            "id": 4, "name": "Linha D", "origin": "Norte",
            "departure_time": "06:00", "stops": [{"local": "Sul", "horario": "06:30"}],
            "capacity": 50, "enrolled": 0, "active": 1,
        }
        with patch("app.load_routes", return_value=[rota_mock]):
            resultado = search_routes_by_stop("leste")
        assert resultado == []

    def test_sem_rotas_cadastradas(self):
        """Se não há rotas, deve retornar lista vazia."""
        with patch("app.load_routes", return_value=[]):
            assert search_routes_by_stop("qualquer") == []

    def test_nao_duplica_rota_com_multiplas_paradas(self):
        """Rota com múltiplas paradas coincidentes deve aparecer apenas uma vez."""
        rota_mock = {
            "id": 5, "name": "Linha E", "origin": "Centro",
            "departure_time": "07:00",
            "stops": [
                {"local": "Centro Comercial", "horario": "07:10"},
                {"local": "Centro Cívico", "horario": "07:20"},
            ],
            "capacity": 40, "enrolled": 0, "active": 1,
        }
        with patch("app.load_routes", return_value=[rota_mock]):
            resultado = search_routes_by_stop("centro")
        assert len(resultado) == 1
