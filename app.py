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
        r_df = pd.read_csv('riders.csv')
        r_df['team_pick'] = r_df.groupby('owner').cumcount() + 1
        r_df['match_name'] = r_df['rider_name'].apply(normalize_name)
        if 'is_replacement' not in r_df.columns: r_df['is_replacement'] = False

        res = pd.read_excel('results.xlsx', engine='openpyxl')
        all_stages = sorted(res['Stage'].unique())
        latest_stage = max(all_stages)
        all_results = []

        raw_results_list = []
        for s in all_stages:
            stage_data = res[res['Stage'] == s]
            
            # A. Daily Stage Results
            stage_cols = ['1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th', '10th']
            for i, col in enumerate(stage_cols, 1):
                if col in stage_data.columns:
                    raw_results_list.append({'Stage': s, 'res_rider': stage_data[col].iloc[0], 'rank': i, 'Category': 'Stage Result'})

            # B. GC & Jerseys (ONLY on Stage 21)
            if s == 21:
                for i in range(1, 11):
                    col = f'GC #{i}'
                    if col in stage_data.columns:
                        raw_results_list.append({'Stage': s, 'res_rider': stage_data[col].iloc[0], 'rank': i, 'Category': 'GC Standing'})
                
                jersey_types = [('Points #', 'Points Jersey'), ('Mountain #', 'Mountain Jersey'), ('Youth #', 'Youth Jersey')]
                for prefix, cat_name in jersey_types:
                    for i in range(1, 4):
                        col = f'{prefix}{i}'
                        if col in stage_data.columns:
                            raw_results_list.append({'Stage': s, 'res_rider': stage_data[col].iloc[0], 'rank': i, 'Category': cat_name})

        df_all_raw = pd.DataFrame(raw_results_list)
        df_all_raw['match_name'] = df_all_raw['res_rider'].apply(normalize_name)

        proc = df_all_raw.merge(r_df[['match_name', 'owner', 'rider_name', 'team_pick', 'is_replacement']], on='match_name', how='inner')

        def calc_pts(row, apply_replacement=True):
            cat, rank = row['Category'], row['rank']
            if cat == "GC Standing": base = SCORING["GC Standing"].get(rank, 0)
            elif cat == "Stage Result": base = SCORING["Stage Result"].get(rank, 0)
            else: base = SCORING["Jersey"].get(rank, 0) 
            if apply_replacement and row.get('is_replacement', False): 
                return base * REPLACEMENT_MAP.get(row['team_pick'], 0.5)
            return base

        proc['pts'] = proc.apply(calc_pts, axis=1)

        # Unpicked Logic
        unpicked = df_all_raw[~df_all_raw['match_name'].isin(r_df['match_name'].tolist())].copy()
        unpicked['pts'] = unpicked.apply(lambda x: calc_pts(x, False), axis=1)
        best_unpicked = unpicked.groupby('res_rider')['pts'].sum().reset_index().sort_values('pts', ascending=False)

        return proc, r_df, latest_stage, best_unpicked

    except Exception as e:
        st.error(f"Data Error: {e}")
        return pd.DataFrame(), pd.DataFrame(), 0, pd.DataFrame()

proc_data, riders, current_stage, best_unpicked = load_data()

# --- 3. VIEWS ---

def show_dashboard():
    st.title(f"🏆 2026 Giro Standings (Stage {current_stage})")
    if proc_data.empty: 
        st.info("No data available.")
        return

    # Final Standings Calculation
    standings = proc_data.groupby('owner')['pts'].sum().reset_index().sort_values('pts', ascending=False)
    
    # 1. STANDINGS TABLE
    st.subheader("Current Leaderboard")
    cols = st.columns(len(standings))
    for idx, row in standings.iterrows():
        cols[idx].metric(row['owner'], f"{row['pts']:,.1f}")

    st.divider()

    # 2. TOP 10 SCORERS PER TEAM
    st.subheader("Top 10 Scorers per Team")
    col_left, col_right = st.columns(2)
    
    owners = ["Daniel", "Tanner"]
    for i, owner in enumerate(owners):
        with (col_left if i == 0 else col_right):
            st.markdown(f"**{owner}'s Top Scorers**")
            top_10 = (proc_data[proc_data['owner'] == owner]
                      .groupby('rider_name')['pts'].sum()
                      .reset_index()
                      .sort_values('pts', ascending=False)
                      .head(10))
            st.table(top_10.rename(columns={'rider_name': 'Rider', 'pts': 'Total Points'}))

    st.divider()

    # 3. SCORING BREAKDOWN
    st.subheader("Point Source Analysis")
    st.markdown("Breakdown of points earned across different categories.")
    
    # Group categories for cleaner look
    def group_cat(cat):
        if "Jersey" in cat: return "Jerseys"
        return cat

    proc_data['Display Category'] = proc_data['Category'].apply(group_cat)
    source_breakdown = (proc_data.groupby(['owner', 'Display Category'])['pts']
                        .sum().unstack(fill_value=0).reset_index())
    
    st.dataframe(source_breakdown, use_container_width=True, hide_index=True)

def show_analytics():
    st.title("📈 Draft & Market Analytics")
    tab1, tab2 = st.tabs(["Draft Pick Efficiency", "Best Unpicked Riders"])
    
    with tab1:
        st.subheader("Points Earned by Draft Slot")
        pick_eff = proc_data.groupby(['owner', 'team_pick'])['pts'].sum().reset_index()
        fig = px.bar(pick_eff, x="team_pick", y="pts", color="owner", barmode="group",
                     color_discrete_map={"Daniel": "red", "Tanner": "blue"})
        fig.update_layout(xaxis=dict(tickmode='linear', dtick=1))
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.subheader("The 'Hindsight' List")
        if not best_unpicked.empty:
            top_fa = best_unpicked[best_unpicked['pts'] > 0].head(10)
            st.table(top_fa.rename(columns={'res_rider': 'Rider', 'pts': 'Potential Points'}))

def show_rosters():
    st.title("👥 Detailed Rider Breakdowns")
    col1, col2 = st.columns(2)
    for i, owner in enumerate(["Daniel", "Tanner"]):
        with (col1 if i==0 else col2):
            st.header(f"Team {owner}")
            r_totals = proc_data[proc_data['owner'] == owner].groupby('rider_name')['pts'].sum().reset_index()
            owner_riders = riders[riders['owner'] == owner].merge(r_totals, on='rider_name', how='left').fillna(0).sort_values('pts', ascending=False)
            for _, r_row in owner_riders.iterrows():
                with st.expander(f"**{r_row['rider_name']}** — {r_row['pts']:,.1f} pts"):
                    details = proc_data[proc_data['rider_name'] == r_row['rider_name']][['Stage', 'Category', 'rank', 'pts']]
                    st.dataframe(details, use_container_width=True, hide_index=True)

# --- NAVIGATION ---
pg = st.navigation([
    st.Page(show_dashboard, title="Standings", icon="🏆"),
    st.Page(show_analytics, title="Draft Analytics", icon="📈"),
    st.Page(show_rosters, title="Rider Breakdowns", icon="👥")
])
pg.run()
