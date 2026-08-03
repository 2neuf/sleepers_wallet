import requests
import pandas as pd
import streamlit as st
from io import BytesIO

USER_ID = "742374956750540800"
SEASON = 2026
BASE_URL = "https://api.sleeper.app/v1"

st.set_page_config(page_title="Sleepers Wallet V3", page_icon="🏈", layout="wide")

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
def load_users(league_id):
    return get_json(f"{BASE_URL}/league/{league_id}/users")

@st.cache_data(ttl=3600)
def load_rosters(league_id):
    return get_json(f"{BASE_URL}/league/{league_id}/rosters")

players = load_player_map()
leagues = load_leagues()

portfolio_rows = []
league_meta = {}
my_rosters = {}

for league in leagues:
    league_id = league["league_id"]
    league_name = league.get("name", league_id)

    users = load_users(league_id)
    user_map = {u["user_id"]: u.get("display_name", u.get("username", "Unknown")) for u in users}

    rosters = load_rosters(league_id)

    my_roster = next((r for r in rosters if str(r.get("owner_id")) == USER_ID), None)
    if not my_roster:
        continue

    all_players = my_roster.get("players") or []
    taxi = my_roster.get("taxi") or []
    reserve = my_roster.get("reserve") or []
    starters = my_roster.get("starters") or []

    roster_players = list(dict.fromkeys(all_players + taxi + reserve))

    if not roster_players:
        continue

    my_rosters[league_name] = {
        "league_id": league_id,
        "players": roster_players,
        "starters": starters,
        "taxi": taxi,
        "reserve": reserve,
    }

    league_meta[league_name] = {
        "league_id": league_id,
        "users": user_map,
        "rosters": rosters,
    }

    for pid in roster_players:
        p = players.get(pid, {})
        portfolio_rows.append({
            "league_name": league_name,
            "player_id": pid,
            "player_name": p.get("full_name", pid),
            "position": p.get("position", ""),
            "team": p.get("team", ""),
        })

portfolio_df = pd.DataFrame(portfolio_rows)

exposure = (
    portfolio_df.groupby(["player_name", "position"], as_index=False)
    .agg(ligues=("league_name", "nunique"))
)

num_leagues = portfolio_df["league_name"].nunique()

exposure["exposition_pct"] = (
    exposure["ligues"] / num_leagues * 100
).round(1)

CORE_THRESHOLD = st.sidebar.slider(
    "Seuil du core (%)", 5, 60, 20, 5
)

core = exposure[exposure["exposition_pct"] >= CORE_THRESHOLD].copy()
core_players = set(core["player_name"])

page = st.sidebar.radio(
    "Navigation",
    ["📊 Portfolio", "📋 Rosters", "🤝 Trader"]
)

st.sidebar.metric("Ligues analysées", num_leagues)
st.sidebar.metric("Joueurs core", len(core))

if page == "📊 Portfolio":
    st.title("🏈 Sleepers Wallet V3")
    st.metric("Ligues analysées", num_leagues)
    st.metric("Joueurs core", len(core))
    st.dataframe(
        exposure.sort_values("exposition_pct", ascending=False),
        use_container_width=True
    )

elif page == "📋 Rosters":
    st.title("📋 Rosters")

    league_choice = st.selectbox(
        "Choisir une ligue",
        list(my_rosters.keys())
    )

    roster = my_rosters[league_choice]

    rows = []

    for pid in roster["players"]:
        p = players.get(pid, {})
        name = p.get("full_name", pid)

        section = "Bench"

        if pid in roster["starters"]:
            section = "Starter"
        elif pid in roster["taxi"]:
            section = "Taxi"
        elif pid in roster["reserve"]:
            section = "Reserve"

        rows.append({
            "Section": section,
            "Poste": p.get("position", ""),
            "Joueur": name,
            "Équipe": p.get("team", ""),
            "Core": "🟢" if name in core_players else "⚪",
        })

    roster_df = pd.DataFrame(rows)

    st.dataframe(
        roster_df.sort_values(["Section", "Poste"]),
        use_container_width=True,
        hide_index=True
    )

elif page == "🤝 Trader":
    st.title("🤝 Trader – Assistant de trade")

    league_choice = st.selectbox(
        "Choisir une ligue",
        list(my_rosters.keys())
    )

    rosters = league_meta[league_choice]["rosters"]
    user_map = league_meta[league_choice]["users"]

    my_roster = my_rosters[league_choice]

    my_player_ids = set(my_roster["players"])

    my_player_names = set(
        players.get(pid, {}).get("full_name", pid)
        for pid in my_player_ids
    )

    target_df = core[
        ~core["player_name"].isin(my_player_names)
    ].sort_values("exposition_pct", ascending=False)

    if target_df.empty:
        st.success("Cette ligue possède déjà tout le core.")
        st.stop()

    target_name = st.selectbox(
        "🎯 Sélectionner une cible",
        target_df["player_name"].tolist()
    )

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
                owner_name = user_map.get(
                    r.get("owner_id"),
                    "Inconnu"
                )
                break

        if owner_roster is None:
            st.error("Impossible de trouver le propriétaire.")
            st.stop()

        owner_players = owner_roster.get("players") or []

        positions = ["QB", "RB", "WR", "TE"]

        league_counts = {p: [] for p in positions}

        for r in rosters:
            pids = r.get("players") or []
            pos_list = [
                players.get(pid, {}).get("position", "")
                for pid in pids
            ]

            for pos in positions:
                league_counts[pos].append(pos_list.count(pos))

        league_avg = {
            pos: sum(vals) / len(vals)
            for pos, vals in league_counts.items()
        }

        owner_positions = [
            players.get(pid, {}).get("position", "")
            for pid in owner_players
        ]

        owner_count = {
            pos: owner_positions.count(pos)
            for pos in positions
        }

        weakness_scores = {
            pos: league_avg[pos] - owner_count[pos]
            for pos in positions
        }

        weakness_sorted = sorted(
            weakness_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )

        st.subheader(f"🎯 {target_name}")
        st.markdown(f"**Propriétaire :** {owner_name}")

        weak_df = pd.DataFrame([
            {
                "Poste": pos,
                "Besoin": round(score, 2)
            }
            for pos, score in weakness_sorted
        ])

        st.subheader("📉 Faiblesses du roster adverse")
        st.dataframe(weak_df, use_container_width=True, hide_index=True)

        tradable = []

        exposure_map = exposure.set_index(
            "player_name"
        )["ligues"].to_dict()

        for pid in my_player_ids:
            p = players.get(pid, {})
            name = p.get("full_name", pid)

            if name in core_players:
                continue

            tradable.append({
                "Poste": p.get("position", ""),
                "Joueur": name,
                "Équipe": p.get("team", ""),
                "Exposition": exposure_map.get(name, 1),
            })

        tradable_df = pd.DataFrame(tradable)

        best_need = weakness_sorted[0][0]

        if not tradable_df.empty:

            tradable_df["Fit"] = tradable_df["Poste"].apply(
                lambda x: "🟢 Très bon fit"
                if x == best_need else "⚪"
            )

            tradable_df = tradable_df.sort_values(
                ["Fit", "Exposition"],
                ascending=[False, True]
            )

            st.subheader("📤 Joueurs que tu peux offrir")
            st.dataframe(
                tradable_df,
                use_container_width=True,
                hide_index=True
            )

            best_offer = tradable_df.iloc[0]["Joueur"]

        else:
            st.info("Aucun joueur hors core disponible.")
            best_offer = "un pick futur"

        st.subheader("💡 Package conseillé")

        if len(tradable_df) >= 2:
            package = (
                f"{tradable_df.iloc[0]['Joueur']} + "
                f"{tradable_df.iloc[1]['Joueur']} + 2027 2nd"
            )
        else:
            package = f"{best_offer} + 2027 2nd"

        st.success(
            f"**Tu envoies :** {package}\n\n"
            f"**Tu reçois :** {target_name}"
        )

        current_owned = len(my_player_names & core_players)
        future_owned = current_owned + 1

        current_score = round(
            current_owned / max(len(core_players), 1) * 100,
            1
        )

        future_score = round(
            future_owned / max(len(core_players), 1) * 100,
            1
        )

        impact_pct = round(100 / max(num_leagues, 1), 1)

        impact_df = pd.DataFrame([
            {
                "Métrique": f"Exposition {target_name}",
                "Valeur": f"+{impact_pct}%"
            },
            {
                "Métrique": "Score homogénéisation",
                "Valeur": f"{current_score}% → {future_score}%"
            },
            {
                "Métrique": "Perte de joueur core",
                "Valeur": "Aucune"
            },
        ])

        st.subheader("📊 Impact portefeuille")
        st.dataframe(impact_df, use_container_width=True, hide_index=True)

st.sidebar.markdown("---")
st.sidebar.subheader("⬇️ Export")

def build_excel():
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        exposure.to_excel(writer, sheet_name="Exposition", index=False)
        portfolio_df.to_excel(writer, sheet_name="Portefeuille", index=False)
        core.to_excel(writer, sheet_name="Core", index=False)

    output.seek(0)
    return output

st.sidebar.download_button(
    "Télécharger Excel",
    data=build_excel(),
    file_name="sleepers_wallet_v3.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
