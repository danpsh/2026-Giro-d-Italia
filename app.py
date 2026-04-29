import streamlit as st
import pandas as pd
import unicodedata
import plotly.express as px

# --- 1. SETTINGS ---
st.set_page_config(
    page_title="2026 Giro Fantasy", 
    layout="wide", 
    initial_sidebar_state="collapsed"
)

SCORING = {
    "GC Standing": {1: 50, 2: 40, 3: 30, 4: 25, 5: 20, 6: 18, 7: 16, 8: 14, 9: 12, 10: 10},
    "Stage Result": {1: 10, 2: 9, 3: 8, 4: 7, 5: 6, 6: 5, 7: 4, 8: 3, 9: 2, 10: 1},
    "Jersey": {1: 15, 2: 10, 3: 5} 
}

REPLACEMENT_MAP = {
    1: 1.0, 2: 1.0, 3: 0.9, 4: 0.9, 5: 0.8, 6: 0.8,
    7: 0.7, 8: 0.7, 9: 0.6, 10: 0.6, 11: 0.5, 12: 0.5,
    13: 0.5, 14: 0.5, 15: 0.5
}

# --- 2. HELPERS ---
def normalize_name(name):
    if not isinstance(name, str): return ""
    name = "".join(c for c in unicodedata.normalize('NFD', name) if unicodedata.category(c) != 'Mn')
    return name.lower().replace('-', ' ').strip()

@st.cache_data(ttl=300)
def load_data():
    try:
        # 1. Load Riders
        r_df = pd.read_csv('riders.csv')
        r_df['team_pick'] = r_df.groupby('owner').cumcount() + 1
        r_df['match_name'] = r_df['rider_name'].apply(normalize_name)
        if 'is_replacement' not in r_df.columns: r_df['is_replacement'] = False

        # 2. Load Results
        res = pd.read_excel('results.xlsx', engine='openpyxl')
        all_results = []

        # Stage Results
        stage_cols = ['1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th', '10th']
        for i, col in enumerate(stage_cols, 1):
            if col in res.columns:
                temp = res[['Stage', col]].copy().rename(columns={col: 'res_rider'})
                temp['rank'], temp['Category'] = i, 'Stage Result'
                all_results.append(temp)

        # GC Standings
        for i in range(1, 11):
            col = f'GC #{i}'
            if col in res.columns:
                temp = res[['Stage', col]].copy().rename(columns={col: 'res_rider'})
                temp['rank'], temp['Category'] = i, 'GC Standing'
                all_results.append(temp)

        # Jerseys
        jersey_types = [('Points #', 'Points Jersey'), ('Mountain #', 'Mountain Jersey'), ('Youth #', 'Youth Jersey')]
        for prefix, cat_name in jersey_types:
            for i in range(1, 4):
                col = f'{prefix}{i}'
                if col in res.columns:
                    temp = res[['Stage', col]].copy().rename(columns={col: 'res_rider'})
                    temp['rank'], temp['Category'] = i, cat_name
                    all_results.append(temp)

        # 3. Merge and Score
        df_l = pd.concat(all_results, ignore_index=True)
        df_l['match_name'] = df_l['res_rider'].apply(normalize_name)
        
        proc = df_l.merge(r_df[['match_name', 'owner', 'rider_name', 'team_pick', 'is_replacement']], on='match_name', how='inner')

        def calc_pts(row):
            cat, rank = row['Category'], row['rank']
            if cat == "GC Standing": base = SCORING["GC Standing"].get(rank, 0)
            elif cat == "Stage Result": base = SCORING["Stage Result"].get(rank, 0)
            else: base = SCORING["Jersey"].get(rank, 0) 
            
            if row['is_replacement']: 
                return base * REPLACEMENT_MAP.get(row['team_pick'], 0.5)
            return base

        proc['pts'] = proc.apply(calc_pts, axis=1)
        
        lb = proc.groupby('owner')['pts'].sum().reset_index()
        scored = proc.groupby(['owner', 'rider_name', 'team_pick'])['pts'].sum().reset_index()
        roster_summary = r_df[['owner', 'rider_name', 'team_pick']].merge(scored, on=['owner', 'rider_name', 'team_pick'], how='left').fillna(0)
        
        return proc, lb, roster_summary

    except Exception as e:
        st.error(f"Data Error: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

# Load Data Once
proc_data, leaderboard, roster_pts = load_data()

# --- 3. VIEWS ---

def show_dashboard():
    st.title("📊 2026 Giro Standings")
    if proc_data.empty:
        st.info("Ensure riders.csv and results.xlsx are present to see standings.")
        return

    # Dynamic Metrics
    owners = leaderboard['owner'].unique()
    cols = st.columns(len(owners) + 1)
    
    owner_totals = {}
    for i, owner in enumerate(owners):
        pts = leaderboard.loc[leaderboard['owner'] == owner, 'pts'].sum()
        owner_totals[owner] = pts
        cols[i].metric(owner, f"{pts:,.1f} Pts")

    if len(owners) == 2:
        gap = abs(list(owner_totals.values())[0] - list(owner_totals.values())[1])
        cols[-1].metric("Gap", f"{gap:,.1f} Pts")

    st.divider()

    # Timeline Chart
    timeline = proc_data.groupby(['Stage', 'owner'])['pts'].sum().unstack(fill_value=0).cumsum()
    if not timeline.empty:
        fig = px.line(timeline, title="Cumulative Points Progression", markers=True, 
                      color_discrete_map={"Daniel": "#EF553B", "Tanner": "#636EFA"})
        st.plotly_chart(fig, use_container_width=True)

def show_breakdown():
    st.title("🏆 Points Breakdown")
    if proc_data.empty:
        st.info("No data available.")
        return

    tab1, tab2, tab3 = st.tabs(["Stage Results", "GC Standings", "Jerseys"])

    with tab1:
        st.subheader("🏁 Stage Placement Points")
        df = proc_data[proc_data['Category'] == 'Stage Result']
        res = df.groupby(['owner', 'rider_name'])['pts'].sum().reset_index().sort_values('pts', ascending=False)
        st.dataframe(res, use_container_width=True, hide_index=True)

    with tab2:
        st.subheader("💗 GC Standing Points")
        df = proc_data[proc_data['Category'] == 'GC Standing']
        res = df.groupby(['owner', 'rider_name'])['pts'].sum().reset_index().sort_values('pts', ascending=False)
        st.dataframe(res, use_container_width=True, hide_index=True)

    with tab3:
        st.subheader("👕 Jersey Points (Points, KOM, Youth)")
        df = proc_data[proc_data['Category'].str.contains('Jersey')]
        res = df.groupby(['owner', 'rider_name', 'Category'])['pts'].sum().reset_index().sort_values('pts', ascending=False)
        st.dataframe(res, use_container_width=True, hide_index=True)

def show_history():
    st.title("📜 Full Point History")
    if not proc_data.empty:
        st.dataframe(proc_data[['Stage', 'Category', 'rider_name', 'owner', 'pts']].sort_values(['Stage', 'pts'], ascending=[False, False]), 
                     use_container_width=True, hide_index=True)

def show_rosters():
    st.title("👥 Team Rosters")
    col1, col2 = st.columns(2)
    owners = ["Daniel", "Tanner"]
    for i, owner in enumerate(owners):
        with (col1 if i==0 else col2):
            st.subheader(owner)
            df = roster_pts[roster_pts['owner'] == owner].sort_values('team_pick')
            st.dataframe(df[['team_pick', 'rider_name', 'pts']].rename(columns={'team_pick':'Pick','rider_name':'Rider','pts':'Total'}), 
                         use_container_width=True, hide_index=True)

# --- 4. NAVIGATION ---
pg = st.navigation([
    st.Page(show_dashboard, title="Standings", icon="📊"),
    st.Page(show_breakdown, title="Breakdown", icon="🏆"),
    st.Page(show_history, title="History", icon="📜"),
    st.Page(show_rosters, title="Teams", icon="👥")
])
pg.run()
