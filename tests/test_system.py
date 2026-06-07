"""
Testes de Sistema — Mobilidade Inteligente
===========================================
Testam fluxos completos do sistema de ponta a ponta, simulando
o comportamento real do usuário sem mockar a lógica de negócio.
"""

import pytest
import sqlite3
import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import (
    create_user,
    authenticate_user,
    save_request,
    load_requests,
    load_user_count,
    route_candidates,
    count_series,
)


# ─────────────────────────────────────────────
# Fixture: banco isolado para testes de sistema
# ─────────────────────────────────────────────

@pytest.fixture(autouse=True)
def banco_sistema(tmp_path):
    """
    Banco de dados temporário isolado para cada teste de sistema.
    Simula o ambiente real completo sem afetar dados de produção.
    """
    db_temp = tmp_path / "system_test.db"

    def connect_temp():
        conn = sqlite3.connect(str(db_temp), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

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

    with patch("app.connect_db", side_effect=connect_temp):
        yield


# ─────────────────────────────────────────────
# Fluxo 1: Cadastro e login de passageiro
# ─────────────────────────────────────────────

class TestFluxoCadastroELogin:
    def test_passageiro_se_cadastra_e_faz_login(self):
        """
        DADO que um passageiro se cadastra com dados válidos
        QUANDO ele tenta fazer login com as mesmas credenciais
        ENTÃO o login deve ser bem-sucedido e retornar seus dados
        """
        sucesso_cadastro, _ = create_user("Lucas Souza", "lucas@email.com", "senha123", "passenger")
        assert sucesso_cadastro is True

        sucesso_login, dados = authenticate_user("lucas@email.com", "senha123", "passenger")
        assert sucesso_login is True
        assert dados["name"] == "Lucas Souza"
        assert dados["role"] == "passenger"

    def test_empresa_se_cadastra_e_faz_login(self):
        """
        DADO que uma empresa se cadastra
        QUANDO ela faz login com as credenciais corretas
        ENTÃO deve acessar o sistema com role 'company'
        """
        create_user("Empresa XYZ", "contato@xyz.com", "empresa123", "company")
        sucesso, dados = authenticate_user("contato@xyz.com", "empresa123", "company")
        assert sucesso is True
        assert dados["role"] == "company"

    def test_passageiro_nao_acessa_como_empresa(self):
        """
        DADO que um passageiro está cadastrado
        QUANDO ele tenta logar com o tipo 'company'
        ENTÃO o sistema deve rejeitar o acesso
        """
        create_user("Maria", "maria@email.com", "abc", "passenger")
        sucesso, _ = authenticate_user("maria@email.com", "abc", "company")
        assert sucesso is False

    def test_dois_usuarios_diferentes_coexistem(self):
        """
        DADO que dois usuários distintos se cadastram
        QUANDO o sistema conta os usuários
        ENTÃO devem existir exatamente dois registros
        """
        create_user("User A", "a@email.com", "123", "passenger")
        create_user("User B", "b@email.com", "456", "company")
        assert load_user_count() == 2


# ─────────────────────────────────────────────
# Fluxo 2: Passageiro envia solicitações de viagem
# ─────────────────────────────────────────────

class TestFluxoSolicitacaoDeViagem:
    def test_passageiro_envia_solicitacao_completa(self):
        """
        DADO que um passageiro está autenticado
        QUANDO ele preenche todos os campos e envia a solicitação
        ENTÃO a solicitação deve ser salva e visível no sistema
        """
        create_user("Ana", "ana@email.com", "123", "passenger")
        authenticate_user("ana@email.com", "123", "passenger")

        save_request("Ana", "Terminal Rodoviário", "Universidade Federal", "2025-09-01", "Prefiro manhã")

        df = load_requests()
        assert len(df) == 1
        assert df.iloc[0]["origin"] == "Terminal Rodoviário"
        assert df.iloc[0]["destination"] == "Universidade Federal"
        assert df.iloc[0]["passenger_name"] == "Ana"

    def test_passageiro_envia_multiplas_solicitacoes(self):
        """
        DADO que um passageiro precisa de várias rotas
        QUANDO ele envia 3 solicitações diferentes
        ENTÃO todas devem estar registradas no sistema
        """
        save_request("Pedro", "Casa", "Trabalho", "2025-09-01", "")
        save_request("Pedro", "Trabalho", "Academia", "2025-09-01", "")
        save_request("Pedro", "Academia", "Casa", "2025-09-01", "")

        df = load_requests()
        assert len(df) == 3

    def test_solicitacao_sem_nome_e_aceita(self):
        """
        DADO que o nome do passageiro é opcional
        QUANDO uma solicitação é enviada sem nome
        ENTÃO deve ser salva normalmente
        """
        save_request("", "Centro", "Bairro Norte", "2025-09-01", "")
        df = load_requests()
        assert len(df) == 1


# ─────────────────────────────────────────────
# Fluxo 3: Empresa analisa demanda de transporte
# ─────────────────────────────────────────────

class TestFluxoEmpresaAnalisaDemanda:
    @pytest.fixture(autouse=True)
    def solicitacoes_base(self):
        """Popula o banco com um conjunto representativo de solicitações."""
        solicitacoes = [
            ("Ana",    "Centro",        "Bairro Jardim",   "2025-09-01", ""),
            ("Bruno",  "Centro",        "Bairro Jardim",   "2025-09-02", ""),
            ("Carla",  "Centro",        "Bairro Jardim",   "2025-09-03", ""),
            ("Diego",  "Terminal Sul",  "Universidade",    "2025-09-01", ""),
            ("Elisa",  "Terminal Sul",  "Universidade",    "2025-09-02", ""),
            ("Fábio",  "Bairro Norte",  "Centro",          "2025-09-01", ""),
        ]
        for nome, origem, destino, data, obs in solicitacoes:
            save_request(nome, origem, destino, data, obs)

    def test_empresa_ve_total_de_solicitacoes(self):
        """
        DADO que existem 6 solicitações registradas
        QUANDO a empresa carrega os dados
        ENTÃO deve ver todas as 6 solicitações
        """
        df = load_requests()
        assert len(df) == 6

    def test_empresa_identifica_origem_mais_pedida(self):
        """
        DADO as solicitações registradas
        QUANDO a empresa analisa as origens
        ENTÃO 'Centro' deve ser a origem mais requisitada (3 vezes)
        """
        df = load_requests()
        stats = count_series(df["origin"])
        mais_pedida = stats.iloc[0]
        assert mais_pedida["Local"] == "Centro"
        assert mais_pedida["Pedidos"] == 3

    def test_empresa_identifica_rota_mais_pedida(self):
        """
        DADO as solicitações registradas
        QUANDO a empresa analisa as rotas
        ENTÃO 'Centro → Bairro Jardim' deve ser a rota mais frequente (3 vezes)
        """
        df = load_requests()
        rotas = route_candidates(df)
        rota_top = rotas.iloc[0]
        assert rota_top["Origem"] == "Centro"
        assert rota_top["Destino"] == "Bairro Jardim"
        assert rota_top["Pedidos"] == 3

    def test_empresa_ve_rotas_distintas(self):
        """
        DADO as solicitações registradas
        QUANDO a empresa consulta as rotas sugeridas
        ENTÃO devem existir 3 rotas distintas
        """
        df = load_requests()
        rotas = route_candidates(df)
        assert len(rotas) == 3

    def test_empresa_ve_destinos_distintos(self):
        """
        DADO as solicitações com destinos variados
        QUANDO a empresa analisa os destinos
        ENTÃO o número de destinos únicos deve ser correto
        """
        df = load_requests()
        destinos_unicos = df["destination"].nunique()
        assert destinos_unicos == 3  # Bairro Jardim, Universidade, Centro


# ─────────────────────────────────────────────
# Fluxo 4: Cenários de borda e segurança
# ─────────────────────────────────────────────

class TestCenariosDeSeguranca:
    def test_sistema_com_banco_vazio(self):
        """
        DADO um banco sem nenhum dado
        QUANDO o sistema é consultado
        ENTÃO deve responder sem erros
        """
        df = load_requests()
        assert df.empty
        assert load_user_count() == 0

    def test_email_duplicado_nao_gera_segundo_usuario(self):
        """
        DADO que um e-mail já está cadastrado
        QUANDO alguém tenta criar outra conta com o mesmo e-mail
        ENTÃO o sistema deve rejeitar e manter apenas um usuário
        """
        create_user("Original", "dup@email.com", "123", "passenger")
        create_user("Cópia", "dup@email.com", "456", "company")
        assert load_user_count() == 1

    def test_login_com_senha_errada_nao_autentica(self):
        """
        DADO um usuário cadastrado
        QUANDO ele tenta logar com senha incorreta
        ENTÃO o sistema deve negar o acesso
        """
        create_user("Seguro", "seguro@email.com", "senha_real", "passenger")
        sucesso, _ = authenticate_user("seguro@email.com", "senha_falsa", "passenger")
        assert sucesso is False

    def test_multiplos_usuarios_isolados(self):
        """
        DADO dois usuários distintos no sistema
        QUANDO cada um faz login com suas credenciais
        ENTÃO cada um deve acessar apenas sua própria conta
        """
        create_user("Alice", "alice@email.com", "alice123", "passenger")
        create_user("Bob", "bob@email.com", "bob456", "company")

        _, dados_alice = authenticate_user("alice@email.com", "alice123", "passenger")
        _, dados_bob = authenticate_user("bob@email.com", "bob456", "company")

        assert dados_alice["name"] == "Alice"
        assert dados_bob["name"] == "Bob"
        assert dados_alice["email"] != dados_bob["email"]
