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
    "GC": {1: 50, 2: 40, 3: 30, 4: 25, 5: 20, 6: 18, 7: 16, 8: 14, 9: 12, 10: 10},
    "Stage": {1: 10, 2: 9, 3: 8, 4: 7, 5: 6, 6: 5, 7: 4, 8: 3, 9: 2, 10: 1},
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
        # Riders - requires rider_name, owner, is_replacement
        r_df = pd.read_csv('riders.csv')
        r_df['team_pick'] = r_df.groupby('owner').cumcount() + 1
        r_df['match_name'] = r_df['rider_name'].apply(normalize_name)
        if 'is_replacement' not in r_df.columns: r_df['is_replacement'] = False

        # Results - Matches your wide screenshot
        res = pd.read_excel('results.xlsx', engine='openpyxl')
        
        all_results = []

        # 1. Stage Results (Columns 1st - 10th)
        stage_cols = ['1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th', '10th']
        for i, col in enumerate(stage_cols, 1):
            temp = res[['Stage', col]].copy().rename(columns={col: 'res_rider'})
            temp['rank'] = i
            temp['Category'] = 'Stage Result'
            all_results.append(temp)

        # 2. GC Standings (Columns GC #1 - GC #10)
        gc_cols = [f'GC #{i}' for i in range(1, 11)]
        for i, col in enumerate(gc_cols, 1):
            if col in res.columns:
                temp = res[['Stage', col]].copy().rename(columns={col: 'res_rider'})
                temp['rank'] = i
                temp['Category'] = 'GC Standing'
                all_results.append(temp)

        # 3. Jersey Leaders
        jersey_cols = {'Points': 'Points Jersey', 'Mountains': 'Mountain Jersey', 'Young Rider': 'Young Rider Jersey'}
        for col, cat_name in jersey_cols.items():
            if col in res.columns:
                temp = res[['Stage', col]].copy().rename(columns={col: 'res_rider'})
                temp['rank'] = 1 
                temp['Category'] = cat_name
                all_results.append(temp)

        df_l = pd.concat(all_results, ignore_index=True)
        df_l['match_name'] = df_l['res_rider'].apply(normalize_name)

        # Merge with owners
        proc = df_l.merge(r_df[['match_name', 'owner', 'rider_name', 'team_pick', 'is_replacement']], on='match_name', how='inner')

        def calc_pts(row):
            cat, rank = row['Category'], row['rank']
            if cat == "GC Standing": base = SCORING["GC"].get(rank, 0)
            elif cat == "Stage Result": base = SCORING["Stage"].get(rank, 0)
            else: base = SCORING["Jersey"].get(1, 15) # Leaders get 15 pts
            
            if row['is_replacement']: 
                return base * REPLACEMENT_MAP.get(row['team_pick'], 0.5)
            return base

        proc['pts'] = proc.apply(calc_pts, axis=1)
        
        lb = proc.groupby('owner')['pts'].sum().reset_index()
        scored = proc.groupby(['owner', 'rider_name', 'team_pick'])['pts'].sum().reset_index()
        roster_summary = r_df[['owner', 'rider_name', 'team_pick']].merge(scored, on=['owner', 'rider_name', 'team_pick'], how='left').fillna(0)
        
        return proc, lb, roster_summary

    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

# --- 3. EXECUTION ---
proc_data, leaderboard, roster_pts = load_data()

# --- 4. NAVIGATION PAGES ---
def show_dashboard():
    st.title("📊 2026 Giro Fantasy Standings")
    if proc_data.empty:
        st.warning("Awaiting race data...")
        return

    d_pts = round(float(leaderboard[leaderboard['owner'] == "Daniel"]['pts'].sum()), 1) if not leaderboard[leaderboard['owner'] == "Daniel"].empty else 0
    t_pts = round(float(leaderboard[leaderboard['owner'] == "Tanner"]['pts'].sum()), 1) if not leaderboard[leaderboard['owner'] == "Tanner"].empty else 0
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Daniel", f"{d_pts} Pts")
    c2.metric("Tanner", f"{t_pts} Pts")
    c3.metric("Gap", f"{round(abs(d_pts - t_pts), 1)} Pts")

    st.divider()
    timeline = proc_data.groupby(['Stage', 'owner'])['pts'].sum().unstack(fill_value=0).cumsum()
    fig = px.line(timeline, title="Cumulative Points progression", markers=True, color_discrete_map={"Daniel": "red", "Tanner": "blue"})
    st.plotly_chart(fig, use_container_width=True)

def show_history():
    st.title("📜 Full Point History")
    if not proc_data.empty:
        st.dataframe(proc_data[['Stage', 'Category', 'rider_name', 'owner', 'pts']].sort_values(['Stage', 'Category'], ascending=[False, True]), use_container_width=True, hide_index=True)

def show_rosters():
    st.title("👥 Team Rosters")
    col1, col2 = st.columns(2)
    for i, owner in enumerate(["Daniel", "Tanner"]):
        with (col1 if i==0 else col2):
            st.subheader(owner)
            df = roster_pts[roster_pts['owner'] == owner].sort_values('team_pick')
            st.dataframe(df[['team_pick', 'rider_name', 'pts']].rename(columns={'team_pick':'Pick','rider_name':'Rider','pts':'Total'}), use_container_width=True, hide_index=True)

pg = st.navigation([
    st.Page(show_dashboard, title="Standings", icon="📊"),
    st.Page(show_history, title="History", icon="📜"),
    st.Page(show_rosters, title="Teams", icon="👥")
])
pg.run()
