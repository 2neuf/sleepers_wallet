app.py - Sleepers Wallet V4

import requests
import pandas as pd
import streamlit as st
from itertools import combinations

USER_ID = "742374956750540800"
SEASON = 2026
BASE_URL = "https://api.sleeper.app/v1"

st.set_page_config(
page_title="Sleepers Wallet V4",
page_icon="🏈",
layout="wide"
)

---------------------------------------------------

Sleeper API

---------------------------------------------------

@st.cache_data(ttl=3600)
def get_json(url):
r = requests.get(url, timeout=30)
r.raise_for_status()
return r.json()

@st.cache_data(ttl=3600)
def load_players():
return get_json(f"{BASE_URL}/players/nfl")

@st.cache_data(ttl=3600)
def load_leagues():
return get_json(f"{BASE_URL}/user/{USER_ID}/leagues/nfl/{SEASON}")

@st.cache_data(ttl=3600)
def load_users(league_id):
return get_json(f"{BASE_URL}/league/{league_id}/users")

@st.cache_data(ttl=3600)
def load_rosters(league_id):
return get_json(f"{BASE_URL}/league/{league_id}/rosters")

players = load_players()
leagues = load_leagues()

---------------------------------------------------

FantasyCalc values

---------------------------------------------------

@st.cache_data(ttl=86400)
def load_fantasycalc_values():
try:
url = "https://api.fantasycalc.com/values/current?isDynasty=true"
data = requests.get(url, timeout=30).json()

    values = {}
    for p in data.get("players", []):
        name = p.get("name")
        value = p.get("value", 0)
        if name:
            values[name] = value

    return values

except Exception:
    return {}

fc_values = load_fantasycalc_values()

---------------------------------------------------

Pick values

---------------------------------------------------

PICK_VALUES = {
"2027 early 1st": 1400,
"2027 mid 1st": 1200,
"2027 late 1st": 1000,
"2027 early 2nd": 500,
"2027 mid 2nd": 400,
"2027 late 2nd": 300,
"2027 early 3rd": 180,
"2027 late 3rd": 100,
}

---------------------------------------------------

Build portfolio

---------------------------------------------------

portfolio_rows = []
league_data = {}

for league in leagues:

league_id = league["league_id"]
league_name = league.get("name", league_id)

users = load_users(league_id)
user_map = {
    u["user_id"]: u.get("display_name", u.get("username", "Unknown"))
    for u in users
}

rosters = load_rosters(league_id)

my_roster = next(
    (r for r in rosters if str(r.get("owner_id")) == USER_ID),
    None
)

if not my_roster:
    continue

roster_players = my_roster.get("players") or []

league_data[league_name] = {
    "league_id": league_id,
    "rosters": rosters,
    "users": user_map,
    "my_roster": my_roster,
}

for pid in roster_players:
    p = players.get(pid, {})
    name = p.get("full_name", pid)

    portfolio_rows.append({
        "league_name": league_name,
        "player_id": pid,
        "player_name": name,
        "position": p.get("position", ""),
        "team": p.get("team", ""),
        "value": fc_values.get(name, 0),
    })

portfolio_df = pd.DataFrame(portfolio_rows)

if portfolio_df.empty:
st.error("Aucun roster trouvé.")
st.stop()

---------------------------------------------------

Exposure / Core

---------------------------------------------------

exposure = (
portfolio_df.groupby(
["player_name", "position", "value"],
as_index=False
)
.agg(ligues=("league_name", "nunique"))
)

num_leagues = portfolio_df["league_name"].nunique()

exposure["exposition_pct"] = (
exposure["ligues"] / num_leagues * 100
).round(1)

CORE_THRESHOLD = st.sidebar.slider(
"Seuil du core (%)",
5,
60,
20,
5
)

core = exposure[exposure["exposition_pct"] >= CORE_THRESHOLD].copy()
core_players = set(core["player_name"])

premium_threshold = exposure["value"].quantile(0.90)

---------------------------------------------------

Sidebar

---------------------------------------------------

page = st.sidebar.radio(
"Navigation",
["📊 Portfolio", "📋 Rosters", "🤝 Trader"]
)

st.sidebar.metric("Ligues analysées", num_leagues)
st.sidebar.metric("Joueurs core", len(core))

===================================================

PORTFOLIO

===================================================

if page == "📊 Portfolio":

st.title("🏈 Sleepers Wallet V4")

st.subheader("📈 Exposition")

st.dataframe(
    exposure.sort_values(
        ["exposition_pct", "value"],
        ascending=[False, False]
    ),
    use_container_width=True
)

===================================================

ROSTERS

===================================================

elif page == "📋 Rosters":

st.title("📋 Rosters")

league_choice = st.selectbox(
    "Choisir une ligue",
    list(league_data.keys())
)

roster = league_data[league_choice]["my_roster"]

rows = []

for pid in roster.get("players", []):

    p = players.get(pid, {})
    name = p.get("full_name", pid)

    rows.append({
        "Poste": p.get("position", ""),
        "Joueur": name,
        "Équipe": p.get("team", ""),
        "Valeur": fc_values.get(name, 0),
        "Core": "🟢" if name in core_players else "⚪",
    })

roster_df = pd.DataFrame(rows)

st.dataframe(
    roster_df.sort_values(["Poste", "Valeur"], ascending=[True, False]),
    use_container_width=True,
    hide_index=True
)

===================================================

TRADER V4

===================================================

elif page == "🤝 Trader":

st.title("🤝 Trader – Trade Engine V4")

league_choice = st.selectbox(
    "Choisir une ligue",
    list(league_data.keys())
)

data = league_data[league_choice]

rosters = data["rosters"]
user_map = data["users"]
my_roster = data["my_roster"]

my_players = my_roster.get("players", [])

my_names = set(
    players.get(pid, {}).get("full_name", pid)
    for pid in my_players
)

target_df = core[
    ~core["player_name"].isin(my_names)
].sort_values(["value", "exposition_pct"], ascending=[False, False])

if target_df.empty:
    st.success("Cette ligue possède déjà tout le core.")
    st.stop()

target_name = st.selectbox(
    "🎯 Cible à acquérir",
    target_df["player_name"].tolist()
)

target_value = int(fc_values.get(target_name, 0))

target_pid = None

for pid, pdata in players.items():
    if pdata.get("full_name") == target_name:
        target_pid = pid
        break

if st.button("Analyser le trade", use_container_width=True):

    owner_roster = None
    owner_name = "Inconnu"

    for r in rosters:
        if target_pid in (r.get("players") or []):
            owner_roster = r
            owner_name = user_map.get(r.get("owner_id"), "Inconnu")
            break

    if owner_roster is None:
        st.error("Propriétaire introuvable.")
        st.stop()

    st.subheader(f"🎯 {target_name}")
    st.markdown(f"**Valeur cible :** {target_value}")
    st.markdown(f"**Propriétaire :** {owner_name}")

    # ---------------------------------------------------
    # Best base piece
    # ---------------------------------------------------

    tradable = []

    for pid in my_players:

        p = players.get(pid, {})
        name = p.get("full_name", pid)
        value = int(fc_values.get(name, 0))

        if name in core_players:
            continue

        if value >= premium_threshold:
            continue

        tradable.append({
            "name": name,
            "position": p.get("position", ""),
            "value": value,
        })

    tradable_df = pd.DataFrame(tradable)

    if tradable_df.empty:
        st.warning("Aucun joueur échangeable détecté.")
        st.stop()

    tradable_df = tradable_df.sort_values("value", ascending=False)

    base_piece = tradable_df.iloc[0]

    base_value = int(base_piece["value"])

    gap = target_value - base_value

    st.subheader("⚖️ Trade de base")

    base_trade = pd.DataFrame([
        {"Actif": target_name, "Valeur": target_value},
        {"Actif": base_piece["name"], "Valeur": base_value},
    ])

    st.dataframe(base_trade, use_container_width=True, hide_index=True)

    st.metric("Écart de valeur", gap)

    # ---------------------------------------------------
    # Compensation pool
    # ---------------------------------------------------

    compensation_pool = []

    for _, row in tradable_df.iloc[1:].iterrows():
        compensation_pool.append((row["name"], int(row["value"])))

    for pick_name, pick_value in PICK_VALUES.items():
        compensation_pool.append((pick_name, pick_value))

    # ---------------------------------------------------
    # Generate options
    # ---------------------------------------------------

    options = []

    for r in [1, 2]:

        for combo in combinations(compensation_pool, r):

            total = sum(v for _, v in combo)

            diff = total - gap

            score = abs(diff)

            options.append({
                "combo": combo,
                "total": total,
                "diff": diff,
                "score": score,
            })

    options = sorted(options, key=lambda x: x["score"])[:8]

    st.subheader("➕ Compensations proposées (tu ajoutes)")

    for i, opt in enumerate(options[:5], start=1):

        with st.expander(f"Proposition {i}"):

            rows = []

            for name, value in opt["combo"]:
                rows.append({"Actif": name, "Valeur": value})

            st.dataframe(pd.DataFrame(rows), hide_index=True)

            final_diff = opt["diff"]

            st.write(f"**Valeur ajoutée :** {opt['total']}")
            st.write(f"**Écart final :** {final_diff}")

            if abs(final_diff) <= 100:
                st.success("🟢 Équilibré")
            elif abs(final_diff) <= 300:
                st.warning("🟡 Agressif")
            else:
                st.error("🔴 Surpayé")

    # ---------------------------------------------------
    # If you overpay
    # ---------------------------------------------------

    overpay_gap = base_value - target_value

    if overpay_gap > 0:

        st.subheader("🔄 Compensations à demander")

        owner_pool = []

        for pid in owner_roster.get("players", []):

            p = players.get(pid, {})
            name = p.get("full_name", pid)
            value = int(fc_values.get(name, 0))

            if value >= premium_threshold:
                continue

            owner_pool.append((name, value))

        owner_options = []

        for r in [1, 2]:

            for combo in combinations(owner_pool, r):

                total = sum(v for _, v in combo)

                diff = total - overpay_gap

                owner_options.append({
                    "combo": combo,
                    "total": total,
                    "diff": diff,
                    "score": abs(diff),
                })

        owner_options = sorted(owner_options, key=lambda x: x["score"])[:5]

        for i, opt in enumerate(owner_options, start=1):

            with st.expander(f"Compensation demandée {i}"):

                rows = []

                for name, value in opt["combo"]:
                    rows.append({"Actif": name, "Valeur": value})

                st.dataframe(pd.DataFrame(rows), hide_index=True)

                st.write(f"**Écart final :** {opt['diff']}")

    # ---------------------------------------------------
    # Impact portfolio
    # ---------------------------------------------------

    st.subheader("📊 Impact portefeuille")

    current_core = len(my_names & core_players)

    future_core = current_core + (0 if target_name in my_names else 1)

    impact_df = pd.DataFrame([
        {
            "Métrique": "Exposition cible",
            "Valeur": f"+{round(100/num_leagues,1)}%"
        },
        {
            "Métrique": "Core avant",
            "Valeur": current_core
        },
        {
            "Métrique": "Core après",
            "Valeur": future_core
        },
    ])

    st.dataframe(impact_df, use_container_width=True, hide_index=True)

st.sidebar.markdown("---")
st.sidebar.caption("Sleepers Wallet V4 – FantasyCalc Trade Engine")