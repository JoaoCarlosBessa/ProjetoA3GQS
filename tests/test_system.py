"""
Testes de Sistema — Mobilidade Inteligente
===========================================
Testam fluxos completos de ponta a ponta no estilo DADO / QUANDO / ENTÃO.
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
    save_route,
    load_routes,
    load_company_routes,
    toggle_route_active,
    delete_route,
    enroll_passenger,
    unenroll_passenger,
    load_passenger_enrollments,
    load_route_enrollments,
    search_routes_by_stop,
)


# ─────────────────────────────────────────────
# Fixture: banco completo isolado
# ─────────────────────────────────────────────

@pytest.fixture(autouse=True)
def banco_sistema(tmp_path):
    db_temp = tmp_path / "system_test.db"

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
# Fluxo 1: Cadastro e login
# ─────────────────────────────────────────────

class TestFluxoCadastroELogin:
    def test_passageiro_se_cadastra_e_faz_login(self):
        """
        DADO que um passageiro se cadastra com dados válidos
        QUANDO ele faz login com as mesmas credenciais
        ENTÃO o acesso é concedido com os dados corretos
        """
        ok, _ = create_user("Lucas", "lucas@email.com", "senha123", "passenger")
        assert ok is True
        ok, dados = authenticate_user("lucas@email.com", "senha123", "passenger")
        assert ok is True
        assert dados["name"] == "Lucas"
        assert dados["role"] == "passenger"

    def test_empresa_se_cadastra_e_faz_login(self):
        """
        DADO que uma empresa se cadastra
        QUANDO ela faz login
        ENTÃO acessa o sistema como 'company'
        """
        create_user("Empresa XYZ", "xyz@email.com", "empresa123", "company")
        ok, dados = authenticate_user("xyz@email.com", "empresa123", "company")
        assert ok is True
        assert dados["role"] == "company"

    def test_passageiro_nao_acessa_como_empresa(self):
        """
        DADO que um passageiro está cadastrado
        QUANDO ele tenta logar com tipo 'company'
        ENTÃO o acesso é negado
        """
        create_user("Maria", "maria@email.com", "abc", "passenger")
        ok, _ = authenticate_user("maria@email.com", "abc", "company")
        assert ok is False

    def test_dois_usuarios_coexistem(self):
        create_user("A", "a@email.com", "123", "passenger")
        create_user("B", "b@email.com", "456", "company")
        assert load_user_count() == 2


# ─────────────────────────────────────────────
# Fluxo 2: Passageiro solicita viagem
# ─────────────────────────────────────────────

class TestFluxoSolicitacaoDeViagem:
    def test_passageiro_envia_solicitacao_completa(self):
        """
        DADO que um passageiro está autenticado
        QUANDO ele envia uma solicitação completa
        ENTÃO ela fica visível no sistema
        """
        save_request("Ana", "Terminal", "Universidade", "2025-09-01", "Manhã")
        df = load_requests()
        assert len(df) == 1
        assert df.iloc[0]["origin"] == "Terminal"
        assert df.iloc[0]["passenger_name"] == "Ana"

    def test_multiplas_solicitacoes(self):
        save_request("P", "A", "B", "2025-09-01", "")
        save_request("P", "B", "C", "2025-09-01", "")
        save_request("P", "C", "A", "2025-09-01", "")
        assert len(load_requests()) == 3

    def test_solicitacao_sem_nome_aceita(self):
        save_request("", "Centro", "Norte", "2025-09-01", "")
        assert len(load_requests()) == 1


# ─────────────────────────────────────────────
# Fluxo 3: Empresa cadastra e gerencia rotas
# ─────────────────────────────────────────────

class TestFluxoEmpresaGerenciaRotas:
    STOPS = [{"local": "Bairro Jardim", "horario": "07:15"},
             {"local": "Universidade", "horario": "07:40"}]

    def test_empresa_cadastra_rota_e_ela_aparece(self):
        """
        DADO que uma empresa está autenticada
        QUANDO ela cadastra uma rota com paradas
        ENTÃO a rota aparece na listagem com os dados corretos
        """
        create_user("Empresa", "emp@email.com", "123", "company")
        ok, _ = save_route("emp@email.com", "Linha Centro", "Terminal", "07:00", self.STOPS, 40)
        assert ok is True
        rotas = load_company_routes("emp@email.com")
        assert len(rotas) == 1
        assert rotas[0]["name"] == "Linha Centro"
        assert len(rotas[0]["stops"]) == 2

    def test_empresa_desativa_e_reativa_rota(self):
        """
        DADO uma rota ativa cadastrada
        QUANDO a empresa desativa e depois reativa
        ENTÃO o status reflete corretamente
        """
        save_route("emp@email.com", "Linha A", "Terminal", "07:00", self.STOPS, 30)
        rota_id = load_routes()[0]["id"]

        toggle_route_active(rota_id, False)
        assert load_routes()[0]["active"] == 0

        toggle_route_active(rota_id, True)
        assert load_routes()[0]["active"] == 1

    def test_empresa_exclui_rota_e_inscricoes(self):
        """
        DADO uma rota com passageiros inscritos
        QUANDO a empresa exclui a rota
        ENTÃO a rota e todas as inscrições são removidas
        """
        save_route("emp@email.com", "Linha B", "Terminal", "08:00", self.STOPS, 20)
        rota_id = load_routes()[0]["id"]
        enroll_passenger(rota_id, "p@email.com", "Passageiro")

        delete_route(rota_id)

        assert load_routes() == []
        assert load_passenger_enrollments("p@email.com") == []

    def test_duas_empresas_veem_apenas_suas_rotas(self):
        """
        DADO duas empresas com rotas cadastradas
        QUANDO cada uma consulta suas rotas
        ENTÃO cada uma vê apenas as próprias
        """
        save_route("emp1@email.com", "Linha Emp1", "A", "07:00", self.STOPS, 30)
        save_route("emp2@email.com", "Linha Emp2", "B", "08:00", self.STOPS, 30)

        assert len(load_company_routes("emp1@email.com")) == 1
        assert load_company_routes("emp1@email.com")[0]["name"] == "Linha Emp1"
        assert len(load_company_routes("emp2@email.com")) == 1


# ─────────────────────────────────────────────
# Fluxo 4: Passageiro se inscreve em rota
# ─────────────────────────────────────────────

class TestFluxoInscricaoDePassageiro:
    STOPS = [{"local": "Bairro X", "horario": "07:20"}]

    @pytest.fixture(autouse=True)
    def rota_disponivel(self):
        save_route("emp@email.com", "Linha Popular", "Terminal", "07:00", self.STOPS, 2)
        self.rota_id = load_routes()[0]["id"]

    def test_passageiro_se_inscreve_com_sucesso(self):
        """
        DADO uma rota com vagas
        QUANDO o passageiro se inscreve
        ENTÃO a inscrição é registrada e as vagas diminuem
        """
        ok, msg = enroll_passenger(self.rota_id, "p@email.com", "Passageiro")
        assert ok is True
        assert self.rota_id in load_passenger_enrollments("p@email.com")
        assert load_routes()[0]["enrolled"] == 1

    def test_segunda_inscricao_bloqueada(self):
        """
        DADO que um passageiro já está inscrito
        QUANDO ele tenta se inscrever novamente
        ENTÃO o sistema rejeita
        """
        enroll_passenger(self.rota_id, "p@email.com", "Passageiro")
        ok, _ = enroll_passenger(self.rota_id, "p@email.com", "Passageiro")
        assert ok is False

    def test_inscricao_bloqueada_quando_lotado(self):
        """
        DADO uma rota com capacidade 2 totalmente ocupada
        QUANDO um terceiro passageiro tenta se inscrever
        ENTÃO o sistema rejeita com mensagem de sem vagas
        """
        enroll_passenger(self.rota_id, "p1@email.com", "P1")
        enroll_passenger(self.rota_id, "p2@email.com", "P2")
        ok, msg = enroll_passenger(self.rota_id, "p3@email.com", "P3")
        assert ok is False
        assert "vagas" in msg.lower()

    def test_passageiro_cancela_inscricao_e_vaga_abre(self):
        """
        DADO um passageiro inscrito em uma rota lotada
        QUANDO ele cancela a inscrição
        ENTÃO a vaga fica disponível novamente
        """
        enroll_passenger(self.rota_id, "p1@email.com", "P1")
        enroll_passenger(self.rota_id, "p2@email.com", "P2")
        unenroll_passenger(self.rota_id, "p1@email.com")

        assert load_routes()[0]["enrolled"] == 1
        ok, _ = enroll_passenger(self.rota_id, "p3@email.com", "P3")
        assert ok is True

    def test_empresa_ve_lista_de_inscritos(self):
        """
        DADO passageiros inscritos em uma rota
        QUANDO a empresa consulta os inscritos
        ENTÃO vê todos corretamente
        """
        enroll_passenger(self.rota_id, "p1@email.com", "Alice")
        enroll_passenger(self.rota_id, "p2@email.com", "Bob")
        df = load_route_enrollments(self.rota_id)
        assert len(df) == 2
        emails = df["passenger_email"].tolist()
        assert "p1@email.com" in emails
        assert "p2@email.com" in emails


# ─────────────────────────────────────────────
# Fluxo 5: Busca de rota por ponto
# ─────────────────────────────────────────────

class TestFluxoBuscaPorPonto:
    @pytest.fixture(autouse=True)
    def rotas_disponiveis(self):
        save_route("emp@email.com", "Linha Norte", "Terminal Norte", "07:00",
                   [{"local": "Praça Central", "horario": "07:20"},
                    {"local": "Universidade", "horario": "07:45"}], 40)
        save_route("emp@email.com", "Linha Sul", "Terminal Sul", "08:00",
                   [{"local": "Shopping", "horario": "08:20"},
                    {"local": "Aeroporto", "horario": "08:50"}], 30)

    def test_busca_por_origem_encontra_rota(self):
        """
        DADO duas rotas cadastradas
        QUANDO o passageiro busca por 'terminal norte'
        ENTÃO apenas a rota com essa origem é retornada
        """
        resultado = search_routes_by_stop("terminal norte")
        assert len(resultado) == 1
        assert resultado[0]["name"] == "Linha Norte"

    def test_busca_por_parada_encontra_rota(self):
        """
        DADO rotas com paradas distintas
        QUANDO o passageiro busca por 'universidade'
        ENTÃO a rota que passa por esse ponto é encontrada
        """
        resultado = search_routes_by_stop("universidade")
        assert len(resultado) == 1
        assert resultado[0]["name"] == "Linha Norte"

    def test_busca_parcial_funciona(self):
        """
        DADO rotas com nomes longos
        QUANDO o passageiro digita apenas parte do nome
        ENTÃO a busca retorna corretamente
        """
        resultado = search_routes_by_stop("aero")
        assert len(resultado) == 1
        assert resultado[0]["name"] == "Linha Sul"

    def test_busca_sem_resultado(self):
        """
        DADO rotas cadastradas
        QUANDO o passageiro busca por um ponto inexistente
        ENTÃO a lista de resultados é vazia
        """
        resultado = search_routes_by_stop("rodoviária")
        assert resultado == []

    def test_busca_vazia_retorna_vazio(self):
        """
        DADO qualquer estado do sistema
        QUANDO o passageiro não digita nada
        ENTÃO a busca retorna lista vazia sem erros
        """
        assert search_routes_by_stop("") == []

    def test_busca_retorna_apenas_rotas_ativas(self):
        """
        DADO uma rota desativada
        QUANDO o passageiro busca por um ponto dela
        ENTÃO a rota não aparece nos resultados
        """
        rota_id = load_routes()[0]["id"]
        toggle_route_active(rota_id, False)
        resultado = search_routes_by_stop("terminal norte")
        assert all(r["active"] == 1 for r in resultado)


# ─────────────────────────────────────────────
# Fluxo 6: Empresa analisa demanda
# ─────────────────────────────────────────────

class TestFluxoEmpresaAnalisaDemanda:
    @pytest.fixture(autouse=True)
    def solicitacoes_base(self):
        dados = [
            ("Ana",   "Centro",       "Bairro Jardim", "2025-09-01", ""),
            ("Bruno", "Centro",       "Bairro Jardim", "2025-09-02", ""),
            ("Carla", "Centro",       "Bairro Jardim", "2025-09-03", ""),
            ("Diego", "Terminal Sul", "Universidade",  "2025-09-01", ""),
            ("Elisa", "Terminal Sul", "Universidade",  "2025-09-02", ""),
            ("Fábio", "Bairro Norte", "Centro",        "2025-09-01", ""),
        ]
        for nome, orig, dest, data, obs in dados:
            save_request(nome, orig, dest, data, obs)

    def test_total_de_solicitacoes(self):
        assert len(load_requests()) == 6

    def test_origem_mais_pedida(self):
        df = load_requests()
        stats = count_series(df["origin"])
        assert stats.iloc[0]["Local"] == "Centro"
        assert stats.iloc[0]["Pedidos"] == 3

    def test_rota_mais_pedida(self):
        df = load_requests()
        rotas = route_candidates(df)
        assert rotas.iloc[0]["Origem"] == "Centro"
        assert rotas.iloc[0]["Destino"] == "Bairro Jardim"
        assert rotas.iloc[0]["Pedidos"] == 3

    def test_numero_de_rotas_distintas(self):
        df = load_requests()
        assert len(route_candidates(df)) == 3


# ─────────────────────────────────────────────
# Fluxo 7: Segurança e borda
# ─────────────────────────────────────────────

class TestCenariosDeSeguranca:
    def test_sistema_com_banco_vazio(self):
        assert load_requests().empty
        assert load_user_count() == 0
        assert load_routes() == []

    def test_email_duplicado_nao_cria_segundo_usuario(self):
        create_user("Original", "dup@email.com", "123", "passenger")
        create_user("Cópia", "dup@email.com", "456", "company")
        assert load_user_count() == 1

    def test_senha_errada_bloqueia_acesso(self):
        create_user("Seguro", "seguro@email.com", "real", "passenger")
        ok, _ = authenticate_user("seguro@email.com", "falsa", "passenger")
        assert ok is False

    def test_inscricao_em_rota_inativa_bloqueada(self):
        save_route("emp@email.com", "Linha X", "A", "07:00",
                   [{"local": "B", "horario": "07:30"}], 10)
        rota_id = load_routes()[0]["id"]
        toggle_route_active(rota_id, False)
        ok, msg = enroll_passenger(rota_id, "p@email.com", "P")
        assert ok is False
        assert "inativa" in msg.lower() or "não encontrada" in msg.lower()
