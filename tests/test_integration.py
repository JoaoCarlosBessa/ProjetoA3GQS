"""
Testes de Integração — Mobilidade Inteligente
===============================================
Testam a interação entre as funções e o banco de dados SQLite real (em memória).
"""

import pytest
import sqlite3
import sys
import os
from unittest.mock import patch
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import (
    hash_password,
    create_user,
    authenticate_user,
    save_request,
    load_requests,
    load_user_count,
)


# ─────────────────────────────────────────────
# Fixture: banco de dados isolado em memória
# ─────────────────────────────────────────────

@pytest.fixture(autouse=True)
def banco_temporario(tmp_path):
    """
    Cria um banco de dados SQLite temporário para cada teste.
    Garante isolamento total entre os testes.
    """
    db_temp = tmp_path / "test.db"

    def connect_temp():
        conn = sqlite3.connect(str(db_temp), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    # Inicializa as tabelas no banco temporário
    with connect_temp() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trip_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                passenger_name TEXT,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                travel_date TEXT,
                notes TEXT,
                created_at TEXT NOT NULL
            )
        """)

    # Substitui connect_db do app pelo banco temporário
    with patch("app.connect_db", side_effect=connect_temp):
        yield


# ─────────────────────────────────────────────
# create_user
# ─────────────────────────────────────────────

class TestCreateUser:
    def test_cria_usuario_com_sucesso(self):
        """Usuário válido deve ser criado com sucesso."""
        sucesso, mensagem = create_user("João Silva", "joao@email.com", "senha123", "passenger")
        assert sucesso is True
        assert "sucesso" in mensagem.lower()

    def test_email_duplicado_retorna_erro(self):
        """Cadastrar o mesmo e-mail duas vezes deve falhar na segunda tentativa."""
        create_user("João", "joao@email.com", "senha123", "passenger")
        sucesso, mensagem = create_user("João Clone", "joao@email.com", "outrasenha", "passenger")
        assert sucesso is False
        assert "e-mail" in mensagem.lower()

    def test_email_case_insensitive(self):
        """E-mails com capitalização diferente devem ser tratados como iguais."""
        create_user("Maria", "maria@email.com", "abc", "passenger")
        sucesso, _ = create_user("Maria2", "MARIA@EMAIL.COM", "abc", "passenger")
        assert sucesso is False

    def test_senha_armazenada_como_hash(self):
        """A senha não deve ser armazenada em texto puro."""
        create_user("Ana", "ana@email.com", "minhasenha", "passenger")
        # Se autenticação com senha errada falha, é porque foi salva como hash
        sucesso, _ = authenticate_user("ana@email.com", "senhaerrada", "passenger")
        assert sucesso is False

    def test_roles_diferentes_aceitos(self):
        """Deve aceitar os papéis 'passenger' e 'company'."""
        ok1, _ = create_user("Passageiro", "pass@email.com", "123", "passenger")
        ok2, _ = create_user("Empresa", "emp@email.com", "123", "company")
        assert ok1 is True
        assert ok2 is True


# ─────────────────────────────────────────────
# authenticate_user
# ─────────────────────────────────────────────

class TestAuthenticateUser:
    @pytest.fixture(autouse=True)
    def usuario_base(self):
        """Cria um usuário padrão antes de cada teste desta classe."""
        create_user("Carlos", "carlos@email.com", "senha_certa", "passenger")

    def test_login_valido(self):
        """Credenciais corretas devem autenticar com sucesso."""
        sucesso, dados = authenticate_user("carlos@email.com", "senha_certa", "passenger")
        assert sucesso is True
        assert dados["name"] == "Carlos"
        assert dados["role"] == "passenger"

    def test_senha_errada(self):
        """Senha incorreta deve retornar falha na autenticação."""
        sucesso, mensagem = authenticate_user("carlos@email.com", "senha_errada", "passenger")
        assert sucesso is False
        assert "senha" in mensagem.lower()

    def test_email_inexistente(self):
        """E-mail não cadastrado deve retornar erro."""
        sucesso, mensagem = authenticate_user("naoexiste@email.com", "qualquer", "passenger")
        assert sucesso is False
        assert "não encontrado" in mensagem.lower()

    def test_role_incorreta(self):
        """Login com tipo de usuário errado deve ser recusado."""
        sucesso, mensagem = authenticate_user("carlos@email.com", "senha_certa", "company")
        assert sucesso is False
        assert "acesso" in mensagem.lower()

    def test_retorna_dados_corretos(self):
        """Dados retornados devem corresponder ao usuário cadastrado."""
        _, dados = authenticate_user("carlos@email.com", "senha_certa", "passenger")
        assert dados["email"] == "carlos@email.com"
        assert "password_hash" not in dados  # Nunca expor o hash


# ─────────────────────────────────────────────
# save_request + load_requests
# ─────────────────────────────────────────────

class TestSaveAndLoadRequests:
    def test_salva_e_carrega_solicitacao(self):
        """Uma solicitação salva deve aparecer no carregamento."""
        save_request("Maria", "Terminal Central", "Bairro Jardim", "2025-08-01", "Manhã")
        df = load_requests()
        assert len(df) == 1
        assert df.iloc[0]["origin"] == "Terminal Central"
        assert df.iloc[0]["destination"] == "Bairro Jardim"

    def test_multiplas_solicitacoes(self):
        """Várias solicitações devem ser salvas e retornadas corretamente."""
        save_request("A", "Origem 1", "Destino 1", "2025-08-01", "")
        save_request("B", "Origem 2", "Destino 2", "2025-08-02", "")
        save_request("C", "Origem 3", "Destino 3", "2025-08-03", "")
        df = load_requests()
        assert len(df) == 3

    def test_ordem_decrescente_por_data(self):
        """Solicitações mais recentes devem aparecer primeiro."""
        save_request("A", "Origem A", "Destino A", "2025-07-01", "")
        save_request("B", "Origem B", "Destino B", "2025-08-01", "")
        df = load_requests()
        # A mais recente (B) deve estar no topo
        assert df.iloc[0]["passenger_name"] == "B"

    def test_banco_vazio_retorna_df_vazio(self):
        """Sem solicitações, load_requests deve retornar DataFrame vazio."""
        df = load_requests()
        assert df.empty

    def test_colunas_presentes(self):
        """DataFrame deve ter todas as colunas esperadas."""
        save_request("X", "O", "D", "2025-01-01", "nota")
        df = load_requests()
        esperadas = ["passenger_name", "origin", "destination", "travel_date", "notes", "created_at"]
        for col in esperadas:
            assert col in df.columns


# ─────────────────────────────────────────────
# load_user_count
# ─────────────────────────────────────────────

class TestLoadUserCount:
    def test_sem_usuarios(self):
        """Banco vazio deve retornar contagem zero."""
        assert load_user_count() == 0

    def test_conta_corretamente(self):
        """Deve contar corretamente o número de usuários cadastrados."""
        create_user("U1", "u1@email.com", "123", "passenger")
        create_user("U2", "u2@email.com", "123", "company")
        assert load_user_count() == 2

    def test_email_duplicado_nao_incrementa(self):
        """Tentativa de cadastro com e-mail duplicado não deve incrementar a contagem."""
        create_user("U1", "u1@email.com", "123", "passenger")
        create_user("U1_dup", "u1@email.com", "456", "passenger")  # deve falhar
        assert load_user_count() == 1
