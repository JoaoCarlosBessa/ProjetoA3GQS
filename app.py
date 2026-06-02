from __future__ import annotations

import hashlib
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st


APP_TITLE = "Mobilidade Inteligente"
DB_PATH = Path(__file__).with_name("requests.db")
ROLE_LABELS = {"passenger": "Passageiro", "company": "Empresa"}


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


def ensure_session_state() -> None:
    if "user" not in st.session_state:
        st.session_state.user = None


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


def authenticate_user(email: str, password: str, role: str) -> tuple[bool, str | dict[str, str]]:
    with connect_db() as connection:
        row = connection.execute(
            """
            SELECT name, email, role, password_hash
            FROM users
            WHERE email = ?
            """,
            (email.strip().lower(),),
        ).fetchone()

    if row is None:
        return False, "Usuário não encontrado."

    if row["role"] != role:
        return False, "Este e-mail está cadastrado com outro tipo de acesso."

    if row["password_hash"] != hash_password(password):
        return False, "Senha incorreta."

    return True, {"name": row["name"], "email": row["email"], "role": row["role"]}


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


def load_user_count() -> int:
    with connect_db() as connection:
        row = connection.execute("SELECT COUNT(*) AS total FROM users").fetchone()
    return int(row["total"] if row else 0)


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


def count_series(values: pd.Series) -> pd.DataFrame:
    counter = Counter(
        value.strip().title()
        for value in values.fillna("")
        if str(value).strip()
    )
    data = [{"Local": local, "Pedidos": quantidade} for local, quantidade in counter.most_common()]
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


def passenger_view() -> None:
    st.subheader("Cadastro de viagem")
    st.write("Informe de onde você quer sair e para onde quer ir. Esses dados ajudam as empresas a identificar rotas mais requisitadas.")

    with st.form("trip_request_form"):
        passenger_name = st.text_input(
            "Nome do passageiro",
            value=st.session_state.user["name"] if st.session_state.user else "",
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


def company_view(df: pd.DataFrame) -> None:
    st.subheader("Painel da empresa")

    total_requests = len(df)
    unique_origins = df["origin"].nunique() if not df.empty else 0
    unique_destinations = df["destination"].nunique() if not df.empty else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Solicitações", total_requests)
    col2.metric("Origens diferentes", unique_origins)
    col3.metric("Destinos diferentes", unique_destinations)

    st.markdown("### Locais mais requisitados")
    if df.empty:
        st.info("Ainda não há solicitações registradas.")
        return

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

    st.markdown("### Rotas sugeridas")
    if route_stats.empty:
        st.info("Nenhuma rota sugerida ainda.")
    else:
        st.dataframe(route_stats, use_container_width=True, hide_index=True)

    st.markdown("### Solicitações recentes")
    recent = df.head(10).copy()
    recent["created_at"] = recent["created_at"].str.replace("T", " ", regex=False)
    st.dataframe(recent, use_container_width=True, hide_index=True)


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