import streamlit as st
import pandas as pd
import unicodedata
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go

# --- 1. SETTINGS ---
st.set_page_config(
    page_title="2026 Giro d'Italia Fantasy", 
    layout="wide", 
    initial_sidebar_state="collapsed"
)

# Giro Specific Scoring
SCORING = {
    "GC": {1: 50, 2: 40, 3: 30, 4: 25, 5: 20, 6: 18, 7: 16, 8: 14, 9: 12, 10: 10},
    "Stage": {1: 10, 2: 9, 3: 8, 4: 7, 5: 6, 6: 5, 7: 4, 8: 3, 9: 2, 10: 1},
    "Jersey": {1: 15, 2: 10, 3: 5} 
}

# Penalty multiplier based on draft slot (team_pick)
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

def get_ordinal(n):
    if 11 <= (n % 100) <= 13: return str(n) + 'th'
    suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return str(n) + suffix

@st.cache_data(ttl=300)
def load_data():
    try:
        # Riders
        r_df = pd.read_csv('riders.csv')
        r_df['team_pick'] = r_df.groupby('owner').cumcount() + 1
        r_df['add_date'] = pd.to_datetime(r_df['add_date'], errors='coerce').fillna(pd.Timestamp('2026-01-01'))
        r_df['drop_date'] = pd.to_datetime(r_df['drop_date'], errors='coerce').fillna(pd.Timestamp('2026-12-31'))
        r_df['match_name'] = r_df['rider_name'].apply(normalize_name)
        if 'is_replacement' not in r_df.columns: r_df['is_replacement'] = False

        # Schedule
        sched = pd.read_csv('schedule.csv')
        sched['date'] = pd.to_datetime(sched['date'], errors='coerce')

        # Results
        res = pd.read_excel('results.xlsx', engine='openpyxl')
        res['Date'] = pd.to_datetime(res['Date'], errors='coerce')
        
        # Melt results to long format
        rank_cols = ['1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th', '10th']
        df_l = res.melt(id_vars=['Date', 'Race Name', 'Stage', 'Category'], 
                        value_vars=rank_cols, var_name='Pos_Label', value_name='res_rider')
        df_l['rank'] = df_l['Pos_Label'].str.extract(r'(\d+)').astype(int)
        df_l['match_name'] = df_l['res_rider'].apply(normalize_name)

        # Merge results with owners
        proc = df_l.merge(r_df[['match_name', 'owner', 'rider_name', 'team_pick', 'add_date', 'drop_date', 'is_replacement']], on='match_name', how='inner')
        proc = proc[(proc['Date'] >= proc['add_date']) & (proc['Date'] <= proc['drop_date'])].copy()

        # Point calculation
        def calc_pts(row):
            cat, rank = row['Category'], row['rank']
            if cat == "GC": base = SCORING["GC"].get(rank, 0)
            elif cat == "Stage": base = SCORING["Stage"].get(rank, 0)
            else: base = SCORING["Jersey"].get(rank, 0)
            
            if row['is_replacement']: return base * REPLACEMENT_MAP.get(row['team_pick'], 0.5)
            return base

        proc['pts'] = proc.apply(calc_pts, axis=1)
        
        lb = proc.groupby('owner')['pts'].sum().reset_index()
        scored = proc.groupby(['owner', 'rider_name', 'team_pick'])['pts'].sum().reset_index()
        pts_summary = r_df[['owner', 'rider_name', 'team_pick']].merge(scored, on=['owner', 'rider_name', 'team_pick'], how='left').fillna(0)
        
        return proc, lb, pts_summary, sched

    except Exception as e:
        st.error(f"Data loading error: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

# --- 3. RUN PROCESSING ---
proc_data, leaderboard, roster_pts, schedule_df = load_data()

# --- 4. PAGE FUNCTIONS ---
def show_dashboard():
    st.title("🇮🇹 2026 Giro d'Italia Fantasy")
    
    if proc_data.empty:
        st.info("No race results recorded yet.")
        return

    # Metrics
    d_total = round(float(leaderboard[leaderboard['owner'] == "Daniel"]['pts'].sum()), 1) if not leaderboard[leaderboard['owner'] == "Daniel"].empty else 0
    t_total = round(float(leaderboard[leaderboard['owner'] == "Tanner"]['pts'].sum()), 1) if not leaderboard[leaderboard['owner'] == "Tanner"].empty else 0
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Daniel", f"{d_total} Pts")
    m2.metric("Tanner", f"{t_total} Pts")
    m3.metric("Lead", f"{round(abs(d_total - t_total), 1)} Pts")

    # Chart
    st.subheader("Race Progression")
    timeline = proc_data.groupby(['Date', 'owner'])['pts'].sum().unstack(fill_value=0).cumsum()
    fig = px.line(timeline, labels={"value": "Total Points", "Date": ""}, color_discrete_map={"Daniel": "#d62728", "Tanner": "#1f77b4"})
    st.plotly_chart(fig, use_container_width=True)

def show_history():
    st.title("📜 Detailed Point History")
    if not proc_data.empty:
        display_df = proc_data[['Date', 'Race Name', 'Category', 'rider_name', 'owner', 'rank', 'pts']].copy()
        display_df = display_df.sort_values('Date', ascending=False)
        st.dataframe(display_df, use_container_width=True, hide_index=True)

def show_rosters():
    st.title("👥 Team Rosters")
    col1, col2 = st.columns(2)
    for i, owner in enumerate(["Daniel", "Tanner"]):
        with (col1 if i==0 else col2):
            st.subheader(f"Team {owner}")
            team_df = roster_pts[roster_pts['owner'] == owner].sort_values('team_pick')
            st.dataframe(team_df[['team_pick', 'rider_name', 'pts']].rename(columns={'team_pick': 'Slot', 'rider_name': 'Rider', 'pts': 'Total'}), 
                         hide_index=True, use_container_width=True)

# --- 5. NAVIGATION ---
pg = st.navigation([
    st.Page(show_dashboard, title="Dashboard", icon="📊"),
    st.Page(show_history, title="Point History", icon="📜"),
    st.Page(show_rosters, title="Rosters", icon="👥")
])
pg.run()
