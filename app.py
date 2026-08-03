
import requests
import pandas as pd
import streamlit as st
import plotly.express as px
from io import BytesIO

USER_ID = "742374956750540800"
SEASON = 2026
BASE_URL = "https://api.sleeper.app/v1"

st.set_page_config(page_title="Sleepers Wallet", page_icon="🏈", layout="wide")

@st.cache_data(ttl=3600)
def get_json(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=3600)
def load_player_map():
    return get_json(f"{BASE_URL}/players/nfl")

@st.cache_data(ttl=3600)
def load_leagues():
    return get_json(f"{BASE_URL}/user/{USER_ID}/leagues/nfl/{SEASON}")

@st.cache_data(ttl=3600)
def load_draft(draft_id):
    return get_json(f"{BASE_URL}/draft/{draft_id}")

@st.cache_data(ttl=3600)
def load_rosters(league_id):
    return get_json(f"{BASE_URL}/league/{league_id}/rosters")

players = load_player_map()
leagues = load_leagues()

portfolio_rows = []
league_summary = []
league_rosters = {}

for league in leagues:
    league_id = league["league_id"]
    league_name = league.get("name", league_id)
    draft_id = league.get("draft_id")

    draft_status = "unknown"
    if draft_id:
        try:
            draft = load_draft(draft_id)
            draft_status = draft.get("status", "unknown")
        except Exception:
            draft_status = "unknown"

    rosters = load_rosters(league_id)
    my_roster = next((r for r in rosters if str(r.get("owner_id")) == USER_ID), None)

    roster_players = []
    starters = []
    bench = []
    taxi = []
    reserve = []

    if my_roster:
        starters = my_roster.get("starters") or []
        all_players = my_roster.get("players") or []
        taxi = my_roster.get("taxi") or []
        reserve = my_roster.get("reserve") or []

        starter_set = set(starters)
        taxi_set = set(taxi)
        reserve_set = set(reserve)

        bench = [p for p in all_players if p not in starter_set and p not in taxi_set and p not in reserve_set]
        roster_players = list(dict.fromkeys(all_players + taxi + reserve))

    has_roster = len(roster_players) > 0
    include = has_roster

    league_summary.append({
        "Ligue": league_name,
        "Draft": draft_status,
        "Roster existant": "Oui" if has_roster else "Non",
        "Incluse": "Oui" if include else "Non",
        "League ID": league_id,
    })

    def enrich(player_ids, section):
        rows = []
        for pid in player_ids:
            p = players.get(pid, {})
            rows.append({
                "player_id": pid,
                "player_name": p.get("full_name", pid),
                "position": p.get("position", ""),
                "team": p.get("team", ""),
                "section": section,
            })
        return rows

    league_rosters[league_name] = pd.DataFrame(
        enrich(starters, "Starters")
        + enrich(bench, "Bench")
        + enrich(taxi, "Taxi")
        + enrich(reserve, "Reserve")
    )

    if include:
        for pid in roster_players:
            p = players.get(pid, {})
            portfolio_rows.append({
                "league_id": league_id,
                "league_name": league_name,
                "player_id": pid,
                "player_name": p.get("full_name", pid),
                "position": p.get("position", ""),
                "team": p.get("team", ""),
            })

league_df = pd.DataFrame(league_summary)
portfolio_df = pd.DataFrame(portfolio_rows)

active_leagues = league_df[league_df["Incluse"] == "Oui"]
num_active = len(active_leagues)

if portfolio_df.empty:
    st.error("Aucun roster analysable trouvé.")
    st.stop()

exposure = (
    portfolio_df.groupby(["player_name", "position"], as_index=False)
    .agg(ligues=("league_id", "nunique"))
)
exposure["exposition_pct"] = (exposure["ligues"] / num_active * 100).round(1)
exposure = exposure.sort_values(["ligues", "player_name"], ascending=[False, True])

CORE_THRESHOLD = st.sidebar.slider(
    "Seuil du core (%)",
    min_value=5,
    max_value=60,
    value=20,
    step=5
)

core = exposure[exposure["exposition_pct"] >= CORE_THRESHOLD].copy()
core_players = set(core["player_name"])

page = st.sidebar.radio("Navigation", ["📊 Portfolio", "📋 Rosters", "🤝 Trader"])

st.sidebar.metric("Ligues analysées", num_active)
st.sidebar.metric("Joueurs uniques", portfolio_df["player_name"].nunique())
st.sidebar.metric(f"Core ≥{CORE_THRESHOLD}%", len(core))

if page == "📊 Portfolio":
    st.title("🏈 Sleepers Wallet")
    st.dataframe(league_df, use_container_width=True)
    st.subheader("📈 Exposition")
    st.dataframe(exposure, use_container_width=True)

elif page == "📋 Rosters":
    st.title("📋 Rosters")
    league_choice = st.selectbox("Choisir une ligue", list(league_rosters.keys()))
    roster_df = league_rosters[league_choice]
    roster_df["Core"] = roster_df["player_name"].apply(lambda x: "🟢 Core" if x in core_players else "⚪ Hors core")
    for section in ["Starters", "Bench", "Taxi", "Reserve"]:
        sub = roster_df[roster_df["section"] == section]
        if not sub.empty:
            st.subheader(section)
            st.dataframe(sub[["position", "player_name", "team", "Core"]], use_container_width=True, hide_index=True)

elif page == "🤝 Trader":
    st.title("🤝 Trader")
    league_choice = st.selectbox("Choisir une ligue", list(league_rosters.keys()))
    roster_df = league_rosters[league_choice]
    owned = set(roster_df["player_name"])

    missing_core = core[~core["player_name"].isin(owned)].copy()
    st.subheader("🎯 Cibles à acquérir")
    if missing_core.empty:
        st.success("Cette ligue possède déjà tout le core.")
    else:
        st.dataframe(
            missing_core[["position", "player_name", "exposition_pct"]]
            .rename(columns={"position": "Poste", "player_name": "Cible", "exposition_pct": "Exposition (%)"}),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("📤 Joueurs à proposer")
    send_df = roster_df[~roster_df["player_name"].isin(core_players)].copy()
    if send_df.empty:
        st.info("Aucun joueur hors core.")
    else:
        exposure_map = exposure.set_index("player_name")["ligues"].to_dict()
        send_df["Présence portefeuille"] = send_df["player_name"].map(exposure_map).fillna(1)
        send_df["Priorité échange"] = send_df["Présence portefeuille"].apply(
            lambda x: "🔴 Haute" if x == 1 else ("🟠 Moyenne" if x <= 2 else "🟢 Faible")
        )
        st.dataframe(
            send_df[["position", "player_name", "team", "Priorité échange"]],
            use_container_width=True,
            hide_index=True,
        )

st.sidebar.subheader("⬇️ Export")

def build_excel():
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        league_df.to_excel(writer, sheet_name="Ligues", index=False)
        exposure.to_excel(writer, sheet_name="Exposition", index=False)
        portfolio_df.to_excel(writer, sheet_name="Portefeuille", index=False)
    output.seek(0)
    return output

st.sidebar.download_button(
    label="Télécharger Excel",
    data=build_excel(),
    file_name="sleepers_wallet_v2_2026.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
