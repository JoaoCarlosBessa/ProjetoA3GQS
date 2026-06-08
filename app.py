from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st


APP_TITLE = "Mobilidade Inteligente"
DB_PATH = Path(__file__).with_name("requests.db")
ROLE_LABELS = {"passenger": "Passageiro", "company": "Empresa"}


# ─────────────────────────────────────────────
# Utilitários
# ─────────────────────────────────────────────

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def connect_db() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with connect_db() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS trip_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                passenger_name TEXT,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                travel_date TEXT,
                notes TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        # Tabela de rotas cadastradas pela empresa
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS routes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_email TEXT NOT NULL,
                name TEXT NOT NULL,
                origin TEXT NOT NULL,
                departure_time TEXT NOT NULL,
                stops TEXT NOT NULL,
                capacity INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """
        )
        # Tabela de inscrições de passageiros nas rotas
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS enrollments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                route_id INTEGER NOT NULL,
                passenger_email TEXT NOT NULL,
                passenger_name TEXT NOT NULL,
                enrolled_at TEXT NOT NULL,
                UNIQUE(route_id, passenger_email),
                FOREIGN KEY (route_id) REFERENCES routes(id)
            )
            """
        )


def ensure_session_state() -> None:
    if "user" not in st.session_state:
        st.session_state.user = None


# ─────────────────────────────────────────────
# Usuários
# ─────────────────────────────────────────────

def create_user(name: str, email: str, password: str, role: str) -> tuple[bool, str]:
    created_at = datetime.now().isoformat(timespec="seconds")
    try:
        with connect_db() as connection:
            connection.execute(
                """
                INSERT INTO users (name, email, password_hash, role, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name.strip(), email.strip().lower(), hash_password(password), role, created_at),
            )
    except sqlite3.IntegrityError:
        return False, "Já existe um usuário cadastrado com este e-mail."
    return True, "Usuário cadastrado com sucesso."


def authenticate_user(email: str, password: str, role: str) -> tuple[bool, str | dict]:
    with connect_db() as connection:
        row = connection.execute(
            "SELECT name, email, role, password_hash FROM users WHERE email = ?",
            (email.strip().lower(),),
        ).fetchone()

    if row is None:
        return False, "Usuário não encontrado."
    if row["role"] != role:
        return False, "Este e-mail está cadastrado com outro tipo de acesso."
    if row["password_hash"] != hash_password(password):
        return False, "Senha incorreta."

    return True, {"name": row["name"], "email": row["email"], "role": row["role"]}


def load_user_count() -> int:
    with connect_db() as connection:
        row = connection.execute("SELECT COUNT(*) AS total FROM users").fetchone()
    return int(row["total"] if row else 0)


# ─────────────────────────────────────────────
# Solicitações de viagem
# ─────────────────────────────────────────────

def save_request(passenger_name: str, origin: str, destination: str, travel_date: str, notes: str) -> None:
    created_at = datetime.now().isoformat(timespec="seconds")
    with connect_db() as connection:
        connection.execute(
            """
            INSERT INTO trip_requests (passenger_name, origin, destination, travel_date, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (passenger_name.strip(), origin.strip(), destination.strip(), travel_date.strip(), notes.strip(), created_at),
        )


def load_requests() -> pd.DataFrame:
    with connect_db() as connection:
        rows = connection.execute(
            """
            SELECT passenger_name, origin, destination, travel_date, notes, created_at
            FROM trip_requests
            ORDER BY datetime(created_at) DESC, id DESC
            """
        ).fetchall()
    return pd.DataFrame(rows, columns=["passenger_name", "origin", "destination", "travel_date", "notes", "created_at"])


# ─────────────────────────────────────────────
# Rotas da empresa
# ─────────────────────────────────────────────

def save_route(
    company_email: str,
    name: str,
    origin: str,
    departure_time: str,
    stops: list[dict],
    capacity: int,
) -> tuple[bool, str]:
    """
    Salva uma rota nova. `stops` é uma lista de dicts:
    [{"local": "Ponto A", "horario": "07:15"}, ...]
    """
    created_at = datetime.now().isoformat(timespec="seconds")
    try:
        with connect_db() as connection:
            connection.execute(
                """
                INSERT INTO routes (company_email, name, origin, departure_time, stops, capacity, active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    company_email.strip().lower(),
                    name.strip(),
                    origin.strip(),
                    departure_time,
                    json.dumps(stops, ensure_ascii=False),
                    capacity,
                    created_at,
                ),
            )
    except Exception as e:
        return False, f"Erro ao salvar rota: {e}"
    return True, "Rota cadastrada com sucesso."


def load_routes(only_active: bool = False) -> list[dict]:
    """Retorna todas as rotas (ou só as ativas) com contagem de inscritos."""
    query = """
        SELECT
            r.id, r.company_email, r.name, r.origin,
            r.departure_time, r.stops, r.capacity, r.active, r.created_at,
            COUNT(e.id) AS enrolled
        FROM routes r
        LEFT JOIN enrollments e ON e.route_id = r.id
    """
    if only_active:
        query += " WHERE r.active = 1"
    query += " GROUP BY r.id ORDER BY r.departure_time"

    with connect_db() as connection:
        rows = connection.execute(query).fetchall()

    routes = []
    for row in rows:
        r = dict(row)
        r["stops"] = json.loads(r["stops"])
        routes.append(r)
    return routes


def load_company_routes(company_email: str) -> list[dict]:
    """Retorna rotas cadastradas por uma empresa específica."""
    with connect_db() as connection:
        rows = connection.execute(
            """
            SELECT
                r.id, r.name, r.origin, r.departure_time,
                r.stops, r.capacity, r.active, r.created_at,
                COUNT(e.id) AS enrolled
            FROM routes r
            LEFT JOIN enrollments e ON e.route_id = r.id
            WHERE r.company_email = ?
            GROUP BY r.id
            ORDER BY r.departure_time
            """,
            (company_email.strip().lower(),),
        ).fetchall()

    routes = []
    for row in rows:
        r = dict(row)
        r["stops"] = json.loads(r["stops"])
        routes.append(r)
    return routes


def toggle_route_active(route_id: int, active: bool) -> None:
    """Ativa ou desativa uma rota."""
    with connect_db() as connection:
        connection.execute(
            "UPDATE routes SET active = ? WHERE id = ?",
            (1 if active else 0, route_id),
        )


def delete_route(route_id: int) -> None:
    """Remove uma rota e todas as inscrições associadas."""
    with connect_db() as connection:
        connection.execute("DELETE FROM enrollments WHERE route_id = ?", (route_id,))
        connection.execute("DELETE FROM routes WHERE id = ?", (route_id,))


# ─────────────────────────────────────────────
# Inscrições de passageiros
# ─────────────────────────────────────────────

def enroll_passenger(route_id: int, passenger_email: str, passenger_name: str) -> tuple[bool, str]:
    """Inscreve um passageiro em uma rota, respeitando o limite de vagas."""
    with connect_db() as connection:
        # Verifica vagas disponíveis
        row = connection.execute(
            """
            SELECT r.capacity, COUNT(e.id) AS enrolled
            FROM routes r
            LEFT JOIN enrollments e ON e.route_id = r.id
            WHERE r.id = ? AND r.active = 1
            GROUP BY r.id
            """,
            (route_id,),
        ).fetchone()

        if row is None:
            return False, "Rota não encontrada ou inativa."
        if row["enrolled"] >= row["capacity"]:
            return False, "Não há vagas disponíveis nesta rota."

        enrolled_at = datetime.now().isoformat(timespec="seconds")
        try:
            connection.execute(
                """
                INSERT INTO enrollments (route_id, passenger_email, passenger_name, enrolled_at)
                VALUES (?, ?, ?, ?)
                """,
                (route_id, passenger_email.strip().lower(), passenger_name.strip(), enrolled_at),
            )
        except sqlite3.IntegrityError:
            return False, "Você já está inscrito nesta rota."

    return True, "Inscrição realizada com sucesso!"


def unenroll_passenger(route_id: int, passenger_email: str) -> None:
    """Cancela a inscrição de um passageiro."""
    with connect_db() as connection:
        connection.execute(
            "DELETE FROM enrollments WHERE route_id = ? AND passenger_email = ?",
            (route_id, passenger_email.strip().lower()),
        )


def load_passenger_enrollments(passenger_email: str) -> list[int]:
    """Retorna lista de route_ids em que o passageiro está inscrito."""
    with connect_db() as connection:
        rows = connection.execute(
            "SELECT route_id FROM enrollments WHERE passenger_email = ?",
            (passenger_email.strip().lower(),),
        ).fetchall()
    return [r["route_id"] for r in rows]


def load_route_enrollments(route_id: int) -> pd.DataFrame:
    """Retorna os passageiros inscritos em uma rota."""
    with connect_db() as connection:
        rows = connection.execute(
            """
            SELECT passenger_name, passenger_email, enrolled_at
            FROM enrollments
            WHERE route_id = ?
            ORDER BY enrolled_at
            """,
            (route_id,),
        ).fetchall()
    return pd.DataFrame(rows, columns=["passenger_name", "passenger_email", "enrolled_at"])


# ─────────────────────────────────────────────
# Análise de demanda
# ─────────────────────────────────────────────

def count_series(values: pd.Series) -> pd.DataFrame:
    counter = Counter(
        value.strip().title()
        for value in values.fillna("")
        if str(value).strip()
    )
    data = [{"Local": local, "Pedidos": qtd} for local, qtd in counter.most_common()]
    return pd.DataFrame(data)


def route_candidates(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["Origem", "Destino", "Pedidos"])

    pair_counts = Counter()
    for _, row in df.iterrows():
        origin = str(row["origin"]).strip().title()
        destination = str(row["destination"]).strip().title()
        if origin and destination:
            pair_counts[(origin, destination)] += 1

    records = [
        {"Origem": origin, "Destino": destination, "Pedidos": total}
        for (origin, destination), total in pair_counts.most_common()
    ]
    return pd.DataFrame(records)


# ─────────────────────────────────────────────
# Views — Passageiro
# ─────────────────────────────────────────────

def passenger_view() -> None:
    tab_solicitar, tab_rotas = st.tabs(["📋 Solicitar viagem", "🚌 Rotas disponíveis"])

    with tab_solicitar:
        _passenger_request_form()

    with tab_rotas:
        _passenger_routes_view()


def _passenger_request_form() -> None:
    st.subheader("Cadastro de viagem")
    st.write("Informe de onde você quer sair e para onde quer ir. Esses dados ajudam as empresas a identificar rotas mais requisitadas.")

    with st.form("trip_request_form"):
        passenger_name = st.text_input(
            "Nome do passageiro",
            value=st.session_state.user["name"],
            placeholder="Opcional",
        )
        origin = st.text_input("Origem", placeholder="Ex.: Terminal Central")
        destination = st.text_input("Destino", placeholder="Ex.: Bairro Jardim")
        travel_date = st.date_input("Data desejada")
        notes = st.text_area("Observações", placeholder="Ex.: horário preferido, ponto de referência, etc.")
        submitted = st.form_submit_button("Enviar solicitação")

    if submitted:
        if not origin.strip() or not destination.strip():
            st.error("Preencha origem e destino para enviar a solicitação.")
            return
        save_request(
            passenger_name=passenger_name,
            origin=origin,
            destination=destination,
            travel_date=travel_date.isoformat(),
            notes=notes,
        )
        st.success("Solicitação registrada com sucesso.")


def _passenger_routes_view() -> None:
    st.subheader("Rotas disponíveis")
    routes = load_routes(only_active=True)

    if not routes:
        st.info("Nenhuma rota disponível no momento.")
        return

    passenger_email = st.session_state.user["email"]
    enrolled_ids = load_passenger_enrollments(passenger_email)

    for route in routes:
        vagas_restantes = route["capacity"] - route["enrolled"]
        inscrito = route["id"] in enrolled_ids

        with st.expander(f"🚌 {route['name']} — Partida: {route['departure_time']}", expanded=False):
            col1, col2 = st.columns([2, 1])

            with col1:
                st.markdown(f"**Ponto de partida:** {route['origin']}")
                st.markdown("**Paradas:**")
                for stop in route["stops"]:
                    st.markdown(f"- `{stop['horario']}` — {stop['local']}")

            with col2:
                st.metric("Vagas restantes", vagas_restantes)
                if inscrito:
                    st.success("✅ Você está inscrito")
                    if st.button("Cancelar inscrição", key=f"cancel_{route['id']}"):
                        unenroll_passenger(route["id"], passenger_email)
                        st.rerun()
                elif vagas_restantes > 0:
                    if st.button("Inscrever-se", key=f"enroll_{route['id']}", type="primary"):
                        ok, msg = enroll_passenger(
                            route["id"],
                            passenger_email,
                            st.session_state.user["name"],
                        )
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                else:
                    st.warning("Sem vagas")


# ─────────────────────────────────────────────
# Views — Empresa
# ─────────────────────────────────────────────

def company_view(df: pd.DataFrame) -> None:
    tab_painel, tab_rotas, tab_cadastrar = st.tabs([
        "📊 Painel de demanda",
        "🚌 Minhas rotas",
        "➕ Cadastrar rota",
    ])

    with tab_painel:
        _company_demand_panel(df)

    with tab_rotas:
        _company_routes_panel()

    with tab_cadastrar:
        _company_register_route_form()


def _company_demand_panel(df: pd.DataFrame) -> None:
    st.subheader("Painel de demanda")

    total_requests = len(df)
    unique_origins = df["origin"].nunique() if not df.empty else 0
    unique_destinations = df["destination"].nunique() if not df.empty else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Solicitações", total_requests)
    col2.metric("Origens diferentes", unique_origins)
    col3.metric("Destinos diferentes", unique_destinations)

    if df.empty:
        st.info("Ainda não há solicitações registradas.")
        return

    st.markdown("### Locais mais requisitados")
    origin_stats = count_series(df["origin"])
    destination_stats = count_series(df["destination"])
    route_stats = route_candidates(df)

    left, right = st.columns(2)
    with left:
        st.markdown("**Origem mais pedida**")
        st.dataframe(origin_stats, use_container_width=True, hide_index=True)
    with right:
        st.markdown("**Destino mais pedido**")
        st.dataframe(destination_stats, use_container_width=True, hide_index=True)

    st.markdown("### Rotas sugeridas pela demanda")
    if route_stats.empty:
        st.info("Nenhuma rota sugerida ainda.")
    else:
        st.dataframe(route_stats, use_container_width=True, hide_index=True)

    st.markdown("### Solicitações recentes")
    recent = df.head(10).copy()
    recent["created_at"] = recent["created_at"].str.replace("T", " ", regex=False)
    st.dataframe(recent, use_container_width=True, hide_index=True)


def _company_routes_panel() -> None:
    st.subheader("Minhas rotas")
    company_email = st.session_state.user["email"]
    routes = load_company_routes(company_email)

    if not routes:
        st.info("Você ainda não cadastrou nenhuma rota.")
        return

    for route in routes:
        vagas_restantes = route["capacity"] - route["enrolled"]
        status = "🟢 Ativa" if route["active"] else "🔴 Inativa"

        with st.expander(f"{status} — {route['name']} | Partida: {route['departure_time']}", expanded=False):
            col1, col2 = st.columns([2, 1])

            with col1:
                st.markdown(f"**Ponto de partida:** {route['origin']}")
                st.markdown("**Paradas:**")
                for stop in route["stops"]:
                    st.markdown(f"- `{stop['horario']}` — {stop['local']}")

            with col2:
                st.metric("Capacidade", route["capacity"])
                st.metric("Inscritos", route["enrolled"])
                st.metric("Vagas restantes", vagas_restantes)

            # Passageiros inscritos
            enrollments_df = load_route_enrollments(route["id"])
            if not enrollments_df.empty:
                st.markdown("**Passageiros inscritos:**")
                enrollments_df["enrolled_at"] = enrollments_df["enrolled_at"].str.replace("T", " ", regex=False)
                st.dataframe(enrollments_df, use_container_width=True, hide_index=True)
            else:
                st.caption("Nenhum passageiro inscrito ainda.")

            # Ações
            st.markdown("---")
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                label_toggle = "Desativar rota" if route["active"] else "Ativar rota"
                if st.button(label_toggle, key=f"toggle_{route['id']}"):
                    toggle_route_active(route["id"], not route["active"])
                    st.rerun()
            with btn_col2:
                if st.button("🗑️ Excluir rota", key=f"delete_{route['id']}"):
                    delete_route(route["id"])
                    st.success("Rota excluída.")
                    st.rerun()


def _company_register_route_form() -> None:
    st.subheader("Cadastrar nova rota")
    st.write("Defina o ponto de partida, horário e todas as paradas com seus horários estimados.")

    with st.form("route_form"):
        route_name = st.text_input("Nome da rota", placeholder="Ex.: Linha Centro–Universidade")
        origin = st.text_input("Local de partida", placeholder="Ex.: Terminal Rodoviário")
        departure_time = st.time_input("Horário de partida")
        capacity = st.number_input("Capacidade de passageiros", min_value=1, max_value=200, value=40, step=1)

        st.markdown("**Paradas** — adicione até 10 pontos intermediários e o destino final")

        stops = []
        for i in range(1, 11):
            c1, c2 = st.columns([3, 1])
            with c1:
                local = st.text_input(f"Parada {i}", placeholder="Ex.: Praça da Sé", key=f"stop_local_{i}")
            with c2:
                horario = st.time_input(f"Horário {i}", key=f"stop_time_{i}")
            if local.strip():
                stops.append({"local": local.strip(), "horario": horario.strftime("%H:%M")})

        submitted = st.form_submit_button("Cadastrar rota", type="primary")

    if submitted:
        if not route_name.strip():
            st.error("Informe o nome da rota.")
            return
        if not origin.strip():
            st.error("Informe o local de partida.")
            return
        if not stops:
            st.error("Adicione pelo menos uma parada.")
            return

        ok, msg = save_route(
            company_email=st.session_state.user["email"],
            name=route_name,
            origin=origin,
            departure_time=departure_time.strftime("%H:%M"),
            stops=stops,
            capacity=int(capacity),
        )
        if ok:
            st.success(msg)
        else:
            st.error(msg)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="🚌", layout="wide")
    init_db()
    ensure_session_state()

    st.title("Mobilidade Inteligente")
    st.caption("Sistema para passageiros solicitarem rotas e para empresas analisarem a demanda de transporte.")

    st.sidebar.subheader("Acesso")

    if st.session_state.user is None:
        auth_mode = st.sidebar.radio("Entrar ou cadastrar", ["Entrar", "Cadastrar"], index=0)
        auth_role_label = st.sidebar.selectbox("Tipo de usuário", ["Passageiro", "Empresa"])
        auth_role = "passenger" if auth_role_label == "Passageiro" else "company"

        if auth_mode == "Cadastrar":
            with st.sidebar.form("register_form"):
                register_name = st.text_input("Nome")
                register_email = st.text_input("E-mail")
                register_password = st.text_input("Senha", type="password")
                register_confirm = st.text_input("Confirmar senha", type="password")
                register_submitted = st.form_submit_button("Criar conta")

            if register_submitted:
                if not register_name.strip() or not register_email.strip() or not register_password.strip():
                    st.sidebar.error("Preencha nome, e-mail e senha.")
                elif register_password != register_confirm:
                    st.sidebar.error("As senhas não conferem.")
                else:
                    success, message = create_user(register_name, register_email, register_password, auth_role)
                    if success:
                        st.sidebar.success(message)
                    else:
                        st.sidebar.error(message)
        else:
            with st.sidebar.form("login_form"):
                login_email = st.text_input("E-mail")
                login_password = st.text_input("Senha", type="password")
                login_submitted = st.form_submit_button("Entrar")

            if login_submitted:
                success, result = authenticate_user(login_email, login_password, auth_role)
                if success:
                    st.session_state.user = result
                    st.rerun()
                else:
                    st.sidebar.error(result)

        st.sidebar.markdown("---")
        st.sidebar.write("Banco local SQLite")
        st.sidebar.write(f"Arquivo: {DB_PATH.name}")
        st.info("Faça login ou crie uma conta para usar o sistema.")
        return

    role_label = ROLE_LABELS.get(st.session_state.user["role"], st.session_state.user["role"].title())
    st.sidebar.success(f"Logado como {st.session_state.user['name']} ({role_label})")

    if st.sidebar.button("Sair"):
        st.session_state.user = None
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.write("Banco local SQLite")
    st.sidebar.write(f"Arquivo: {DB_PATH.name}")
    st.sidebar.write(f"Usuários cadastrados: {load_user_count()}")

    requests_df = load_requests()

    if st.session_state.user["role"] == "passenger":
        passenger_view()
    else:
        company_view(requests_df)


if __name__ == "__main__":
    main()
