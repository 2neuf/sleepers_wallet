
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
    r = requests.get(url, timeout=20)
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

rows = []
league_summary = []

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
    if my_roster:
        roster_players.extend(my_roster.get("players") or [])
        roster_players.extend(my_roster.get("reserve") or [])
        roster_players.extend(my_roster.get("taxi") or [])

    roster_players = list(dict.fromkeys(roster_players))
    has_roster = len(roster_players) > 0

    include = has_roster

    league_summary.append({
        "Ligue": league_name,
        "Draft": draft_status,
        "Roster existant": "Oui" if has_roster else "Non",
        "Incluse": "Oui" if include else "Non",
        "League ID": league_id,
    })

    if include:
        for pid in roster_players:
            p = players.get(pid, {})
            rows.append({
                "league_id": league_id,
                "league_name": league_name,
                "player_id": pid,
                "player_name": p.get("full_name", pid),
                "position": p.get("position", ""),
                "team": p.get("team", ""),
            })

league_df = pd.DataFrame(league_summary)
portfolio_df = pd.DataFrame(rows)

active_leagues = league_df[league_df["Incluse"] == "Oui"]
num_active = len(active_leagues)

st.title("🏈 Sleepers Wallet")
st.caption("Portefeuille dynasty personnel – Saison 2026")

col1, col2, col3 = st.columns(3)
col1.metric("Ligues totales", len(leagues))
col2.metric("Ligues analysées", num_active)
col3.metric("Joueurs uniques", portfolio_df["player_name"].nunique() if not portfolio_df.empty else 0)

st.subheader("📋 Statut des ligues")
st.dataframe(league_df, use_container_width=True)

if portfolio_df.empty:
    st.warning("Aucun roster analysable trouvé.")
    st.stop()

exposure = (
    portfolio_df.groupby(["player_name", "position"], as_index=False)
    .agg(ligues=("league_id", "nunique"))
)
exposure["exposition_pct"] = (exposure["ligues"] / num_active * 100).round(1)
exposure = exposure.sort_values(["ligues", "player_name"], ascending=[False, True])

st.subheader("📈 Exposition par joueur")
position_filter = st.selectbox(
    "Filtrer par poste",
    ["Tous"] + sorted([p for p in exposure["position"].dropna().unique() if p]),
)

filtered = exposure if position_filter == "Tous" else exposure[exposure["position"] == position_filter]
st.dataframe(filtered, use_container_width=True)

core = exposure[exposure["exposition_pct"] >= 50]
st.metric("Joueurs core (≥50%)", len(core))

st.subheader("🔥 Top exposition")
top10 = exposure.head(10)
fig = px.bar(top10, x="player_name", y="exposition_pct", text="exposition_pct")
fig.update_layout(xaxis_title="", yaxis_title="% de ligues")
st.plotly_chart(fig, use_container_width=True)

st.subheader("🧊 Heatmap ligues × joueurs")
top_heat = exposure.head(20)["player_name"].tolist()
heat = portfolio_df[portfolio_df["player_name"].isin(top_heat)].copy()
heat["owned"] = 1
pivot = heat.pivot_table(index="player_name", columns="league_name", values="owned", fill_value=0)

fig2 = px.imshow(pivot, aspect="auto", text_auto=True)
st.plotly_chart(fig2, use_container_width=True)

st.subheader("🎯 Ligues à homogénéiser")
core_players = set(core["player_name"])
missing_rows = []

for league_name in active_leagues["Ligue"]:
    owned = set(portfolio_df.loc[portfolio_df["league_name"] == league_name, "player_name"])
    missing = sorted(core_players - owned)
    if missing:
        missing_rows.append({
            "Ligue": league_name,
            "Core manquant": ", ".join(missing[:8]) + ("…" if len(missing) > 8 else ""),
            "Nb manquants": len(missing),
        })

if missing_rows:
    st.dataframe(pd.DataFrame(missing_rows).sort_values("Nb manquants"), use_container_width=True)
else:
    st.success("Toutes les ligues possèdent déjà l’ensemble du core.")

st.subheader("🧪 Joueurs présents dans une seule ligue")
singletons = exposure[exposure["ligues"] == 1]
st.dataframe(singletons, use_container_width=True)

st.subheader("⬇️ Export Excel")

def build_excel():
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        league_df.to_excel(writer, sheet_name="Ligues", index=False)
        exposure.to_excel(writer, sheet_name="Exposition", index=False)
        portfolio_df.to_excel(writer, sheet_name="Portefeuille", index=False)
    output.seek(0)
    return output

st.download_button(
    label="Télécharger le portefeuille (.xlsx)",
    data=build_excel(),
    file_name="sleepers_wallet_2026.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
