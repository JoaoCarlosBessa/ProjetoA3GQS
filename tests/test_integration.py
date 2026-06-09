"""
Testes de Integração — Mobilidade Inteligente
===============================================
Testam a interação entre as funções e o banco de dados SQLite (em banco temporário).
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
    save_route,
    load_routes,
    load_company_routes,
    toggle_route_active,
    delete_route,
    enroll_passenger,
    unenroll_passenger,
    load_passenger_enrollments,
    load_route_enrollments,
)


# ─────────────────────────────────────────────
# Fixture: banco isolado com todas as tabelas
# ─────────────────────────────────────────────

@pytest.fixture(autouse=True)
def banco_temporario(tmp_path):
    db_temp = tmp_path / "test.db"

    def connect_temp():
        conn = sqlite3.connect(str(db_temp), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    with connect_temp() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL, role TEXT NOT NULL, created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trip_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                passenger_name TEXT, origin TEXT NOT NULL, destination TEXT NOT NULL,
                travel_date TEXT, notes TEXT, created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS routes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_email TEXT NOT NULL, name TEXT NOT NULL, origin TEXT NOT NULL,
                departure_time TEXT NOT NULL, stops TEXT NOT NULL,
                capacity INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS enrollments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                route_id INTEGER NOT NULL, passenger_email TEXT NOT NULL,
                passenger_name TEXT NOT NULL, enrolled_at TEXT NOT NULL,
                UNIQUE(route_id, passenger_email),
                FOREIGN KEY (route_id) REFERENCES routes(id)
            )
        """)

    with patch("app.connect_db", side_effect=connect_temp):
        yield


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

STOPS_PADRAO = [{"local": "Bairro Jardim", "horario": "07:15"}]

def _criar_rota(email="empresa@test.com", nome="Linha A", origem="Terminal",
                horario="07:00", stops=None, capacidade=40):
    return save_route(email, nome, origem, horario, stops or STOPS_PADRAO, capacidade)


# ─────────────────────────────────────────────
# Usuários
# ─────────────────────────────────────────────

class TestCreateUser:
    def test_cria_usuario_com_sucesso(self):
        ok, msg = create_user("João", "joao@email.com", "123", "passenger")
        assert ok is True
        assert "sucesso" in msg.lower()

    def test_email_duplicado_retorna_erro(self):
        create_user("João", "joao@email.com", "123", "passenger")
        ok, msg = create_user("Clone", "joao@email.com", "456", "passenger")
        assert ok is False
        assert "e-mail" in msg.lower()

    def test_email_case_insensitive(self):
        create_user("Maria", "maria@email.com", "abc", "passenger")
        ok, _ = create_user("Maria2", "MARIA@EMAIL.COM", "abc", "passenger")
        assert ok is False

    def test_roles_diferentes_aceitos(self):
        ok1, _ = create_user("P", "p@email.com", "123", "passenger")
        ok2, _ = create_user("E", "e@email.com", "123", "company")
        assert ok1 is True and ok2 is True


class TestAuthenticateUser:
    @pytest.fixture(autouse=True)
    def usuario_base(self):
        create_user("Carlos", "carlos@email.com", "senha_certa", "passenger")

    def test_login_valido(self):
        ok, dados = authenticate_user("carlos@email.com", "senha_certa", "passenger")
        assert ok is True
        assert dados["name"] == "Carlos"

    def test_senha_errada(self):
        ok, msg = authenticate_user("carlos@email.com", "errada", "passenger")
        assert ok is False
        assert "senha" in msg.lower()

    def test_email_inexistente(self):
        ok, msg = authenticate_user("x@email.com", "123", "passenger")
        assert ok is False
        assert "não encontrado" in msg.lower()

    def test_role_incorreta(self):
        ok, msg = authenticate_user("carlos@email.com", "senha_certa", "company")
        assert ok is False
        assert "acesso" in msg.lower()

    def test_nao_expoe_hash(self):
        _, dados = authenticate_user("carlos@email.com", "senha_certa", "passenger")
        assert "password_hash" not in dados


# ─────────────────────────────────────────────
# Solicitações de viagem
# ─────────────────────────────────────────────

class TestSaveAndLoadRequests:
    def test_salva_e_carrega(self):
        save_request("Maria", "Terminal", "Jardim", "2025-08-01", "Manhã")
        df = load_requests()
        assert len(df) == 1
        assert df.iloc[0]["origin"] == "Terminal"

    def test_banco_vazio(self):
        assert load_requests().empty

    def test_ordem_decrescente(self):
        save_request("A", "O1", "D1", "2025-07-01", "")
        save_request("B", "O2", "D2", "2025-08-01", "")
        assert load_requests().iloc[0]["passenger_name"] == "B"

    def test_colunas_presentes(self):
        save_request("X", "O", "D", "2025-01-01", "n")
        df = load_requests()
        for col in ["passenger_name", "origin", "destination", "travel_date", "notes", "created_at"]:
            assert col in df.columns


# ─────────────────────────────────────────────
# Rotas
# ─────────────────────────────────────────────

class TestSaveRoute:
    def test_salva_rota_com_sucesso(self):
        ok, msg = _criar_rota()
        assert ok is True
        assert "sucesso" in msg.lower()

    def test_rota_aparece_em_load_routes(self):
        _criar_rota(nome="Linha Teste")
        rotas = load_routes()
        assert any(r["name"] == "Linha Teste" for r in rotas)

    def test_stops_serializados_corretamente(self):
        stops = [{"local": "Ponto A", "horario": "07:10"}, {"local": "Ponto B", "horario": "07:25"}]
        _criar_rota(stops=stops)
        rota = load_routes()[0]
        assert len(rota["stops"]) == 2
        assert rota["stops"][0]["local"] == "Ponto A"

    def test_rota_ativa_por_padrao(self):
        _criar_rota()
        assert load_routes()[0]["active"] == 1

    def test_banco_vazio_retorna_lista_vazia(self):
        assert load_routes() == []


class TestLoadRoutes:
    def test_only_active_filtra_inativas(self):
        _criar_rota(nome="Ativa")
        _criar_rota(nome="Inativa")
        rotas = load_routes()
        # Desativa a segunda
        toggle_route_active(rotas[1]["id"], False)
        ativas = load_routes(only_active=True)
        assert all(r["active"] == 1 for r in ativas)
        assert len(ativas) == 1

    def test_conta_inscritos_corretamente(self):
        _criar_rota()
        rota = load_routes()[0]
        # sem inscritos ainda
        assert rota["enrolled"] == 0


class TestLoadCompanyRoutes:
    def test_filtra_por_empresa(self):
        _criar_rota(email="empresa1@test.com", nome="Linha 1")
        _criar_rota(email="empresa2@test.com", nome="Linha 2")
        rotas = load_company_routes("empresa1@test.com")
        assert len(rotas) == 1
        assert rotas[0]["name"] == "Linha 1"

    def test_empresa_sem_rotas(self):
        assert load_company_routes("nenhuma@test.com") == []


class TestToggleRouteActive:
    def test_desativa_rota(self):
        _criar_rota()
        rota_id = load_routes()[0]["id"]
        toggle_route_active(rota_id, False)
        assert load_routes()[0]["active"] == 0

    def test_reativa_rota(self):
        _criar_rota()
        rota_id = load_routes()[0]["id"]
        toggle_route_active(rota_id, False)
        toggle_route_active(rota_id, True)
        assert load_routes()[0]["active"] == 1


class TestDeleteRoute:
    def test_remove_rota(self):
        _criar_rota()
        rota_id = load_routes()[0]["id"]
        delete_route(rota_id)
        assert load_routes() == []

    def test_remove_inscricoes_junto(self):
        _criar_rota()
        rota_id = load_routes()[0]["id"]
        enroll_passenger(rota_id, "p@email.com", "Passageiro")
        delete_route(rota_id)
        # Confirma que inscrição sumiu junto
        assert load_routes() == []


# ─────────────────────────────────────────────
# Inscrições
# ─────────────────────────────────────────────

class TestEnrollPassenger:
    @pytest.fixture(autouse=True)
    def rota_base(self):
        _criar_rota(capacidade=2)
        self.rota_id = load_routes()[0]["id"]

    def test_inscricao_com_sucesso(self):
        ok, msg = enroll_passenger(self.rota_id, "p@email.com", "Passageiro")
        assert ok is True
        assert "sucesso" in msg.lower()

    def test_inscricao_duplicada_retorna_erro(self):
        enroll_passenger(self.rota_id, "p@email.com", "Passageiro")
        ok, msg = enroll_passenger(self.rota_id, "p@email.com", "Passageiro")
        assert ok is False
        assert "inscrito" in msg.lower()

    def test_rota_lotada_retorna_erro(self):
        enroll_passenger(self.rota_id, "p1@email.com", "P1")
        enroll_passenger(self.rota_id, "p2@email.com", "P2")
        ok, msg = enroll_passenger(self.rota_id, "p3@email.com", "P3")
        assert ok is False
        assert "vagas" in msg.lower()

    def test_rota_inexistente(self):
        ok, msg = enroll_passenger(9999, "p@email.com", "Passageiro")
        assert ok is False

    def test_contagem_enrolled_atualiza(self):
        enroll_passenger(self.rota_id, "p@email.com", "Passageiro")
        rota = load_routes()[0]
        assert rota["enrolled"] == 1


class TestUnenrollPassenger:
    @pytest.fixture(autouse=True)
    def inscricao_base(self):
        _criar_rota()
        self.rota_id = load_routes()[0]["id"]
        enroll_passenger(self.rota_id, "p@email.com", "Passageiro")

    def test_cancela_inscricao(self):
        unenroll_passenger(self.rota_id, "p@email.com")
        ids = load_passenger_enrollments("p@email.com")
        assert self.rota_id not in ids

    def test_enrolled_diminui_apos_cancelamento(self):
        unenroll_passenger(self.rota_id, "p@email.com")
        assert load_routes()[0]["enrolled"] == 0


class TestLoadPassengerEnrollments:
    def test_retorna_ids_corretos(self):
        _criar_rota(nome="R1")
        _criar_rota(nome="R2")
        rotas = load_routes()
        enroll_passenger(rotas[0]["id"], "p@email.com", "P")
        enroll_passenger(rotas[1]["id"], "p@email.com", "P")
        ids = load_passenger_enrollments("p@email.com")
        assert rotas[0]["id"] in ids
        assert rotas[1]["id"] in ids

    def test_passageiro_sem_inscricoes(self):
        assert load_passenger_enrollments("ninguem@email.com") == []


class TestLoadRouteEnrollments:
    def test_retorna_passageiros_inscritos(self):
        _criar_rota()
        rota_id = load_routes()[0]["id"]
        enroll_passenger(rota_id, "p@email.com", "Passageiro")
        df = load_route_enrollments(rota_id)
        assert len(df) == 1
        assert df.iloc[0]["passenger_email"] == "p@email.com"

    def test_sem_inscritos_retorna_df_vazio(self):
        _criar_rota()
        rota_id = load_routes()[0]["id"]
        assert load_route_enrollments(rota_id).empty

    def test_colunas_corretas(self):
        _criar_rota()
        rota_id = load_routes()[0]["id"]
        enroll_passenger(rota_id, "p@email.com", "P")
        df = load_route_enrollments(rota_id)
        for col in ["passenger_name", "passenger_email", "enrolled_at"]:
            assert col in df.columns


class TestLoadUserCount:
    def test_sem_usuarios(self):
        assert load_user_count() == 0

    def test_conta_corretamente(self):
        create_user("U1", "u1@email.com", "123", "passenger")
        create_user("U2", "u2@email.com", "123", "company")
        assert load_user_count() == 2

    def test_email_duplicado_nao_incrementa(self):
        create_user("U1", "u1@email.com", "123", "passenger")
        create_user("Dup", "u1@email.com", "456", "passenger")
        assert load_user_count() == 1
