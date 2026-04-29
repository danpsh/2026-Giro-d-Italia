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

        for s in all_stages:
            stage_data = res[res['Stage'] == s]
            
            # A. Stage Results (Banked)
            stage_cols = ['1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th', '10th']
            for i, col in enumerate(stage_cols, 1):
                if col in stage_data.columns:
                    temp = stage_data[['Stage', col]].copy().rename(columns={col: 'res_rider'})
                    temp['rank'], temp['Category'] = i, 'Stage Result'
                    all_results.append(temp)

            # B. GC & Jerseys (Snapshot/Floating)
            for i in range(1, 11):
                col = f'GC #{i}'
                if col in stage_data.columns:
                    temp = stage_data[['Stage', col]].copy().rename(columns={col: 'res_rider'})
                    temp['rank'], temp['Category'] = i, 'GC Standing'
                    all_results.append(temp)

            jersey_types = [('Points #', 'Points Jersey'), ('Mountain #', 'Mountain Jersey'), ('Youth #', 'Youth Jersey')]
            for prefix, cat_name in jersey_types:
                for i in range(1, 4):
                    col = f'{prefix}{i}'
                    if col in stage_data.columns:
                        temp = stage_data[['Stage', col]].copy().rename(columns={col: 'res_rider'})
                        temp['rank'], temp['Category'] = i, cat_name
                        all_results.append(temp)

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
        return proc, r_df, latest_stage

    except Exception as e:
        st.error(f"Data Error: {e}")
        return pd.DataFrame(), pd.DataFrame(), 0

proc_data, riders, current_stage = load_data()

def get_timeline_data():
    history = []
    stages = sorted(proc_data['Stage'].unique())
    for s in stages:
        banked_pts = proc_data[(proc_data['Stage'] <= s) & (proc_data['Category'] == 'Stage Result')]
        banked_total = banked_pts.groupby('owner')['pts'].sum()
        floating_pts = proc_data[(proc_data['Stage'] == s) & (proc_data['Category'] != 'Stage Result')]
        floating_total = floating_pts.groupby('owner')['pts'].sum()
        for owner in ["Daniel", "Tanner"]:
            t = banked_total.get(owner, 0) + floating_total.get(owner, 0)
            history.append({"Stage": s, "owner": owner, "Total Points": t})
    return pd.DataFrame(history)

# --- 4. VIEWS ---

def show_dashboard():
    st.title(f"📊 2026 Giro Standings (Stage {current_stage})")
    if proc_data.empty: return

    timeline_df = get_timeline_data()
    latest_scores = timeline_df[timeline_df['Stage'] == current_stage]

    # Metrics
    c1, c2, c3 = st.columns(3)
    d_pts = latest_scores[latest_scores['owner'] == "Daniel"]['Total Points'].sum()
    t_pts = latest_scores[latest_scores['owner'] == "Tanner"]['Total Points'].sum()
    c1.metric("Daniel", f"{d_pts:,.1f}")
    c2.metric("Tanner", f"{t_pts:,.1f}")
    c3.metric("Gap", f"{abs(d_pts - t_pts):,.1f}")

    st.divider()
    
    # Timeline Chart
    fig = px.line(timeline_df, x="Stage", y="Total Points", color="owner", markers=True,
                  color_discrete_map={"Daniel": "red", "Tanner": "blue"})
    fig.update_layout(xaxis=dict(tickmode='linear', tick0=1, dtick=1))
    st.plotly_chart(fig, use_container_width=True)

    # Dashboard Breakdown Tables (Split)
    st.subheader("Point Source Breakdown")
    current_snap = proc_data[
        ((proc_data['Category'] == 'Stage Result') & (proc_data['Stage'] <= current_stage)) |
        ((proc_data['Category'] != 'Stage Result') & (proc_data['Stage'] == current_stage))
    ].copy()
    current_snap['Source'] = current_snap['Category'].apply(lambda x: "Jerseys" if "Jersey" in x else x)
    
    col1, col2 = st.columns(2)
    for i, owner in enumerate(["Daniel", "Tanner"]):
        with (col1 if i==0 else col2):
            st.markdown(f"#### {owner}")
            owner_df = current_snap[current_snap['owner'] == owner]
            summary = owner_df.groupby('Source')['pts'].sum().reset_index()
            summary.loc[len(summary)] = ['Total', summary['pts'].sum()]
            st.dataframe(summary, use_container_width=True, hide_index=True)

def show_history():
    st.title("📜 Stage Standings Snapshot")
    selected_stage = st.selectbox("Select Stage:", sorted(proc_data['Stage'].unique(), reverse=True))
    
    snap = proc_data[
        ((proc_data['Category'] == 'Stage Result') & (proc_data['Stage'] <= selected_stage)) |
        ((proc_data['Category'] != 'Stage Result') & (proc_data['Stage'] == selected_stage))
    ]

    col1, col2 = st.columns(2)
    for i, owner in enumerate(["Daniel", "Tanner"]):
        with (col1 if i==0 else col2):
            st.subheader(f"{owner} - Stage {selected_stage}")
            owner_snap = snap[snap['owner'] == owner].sort_values('pts', ascending=False)
            st.dataframe(owner_snap[['Category', 'rider_name', 'pts']], use_container_width=True, hide_index=True)

def show_rosters():
    st.title("👥 Team Rosters")
    # Total points per rider in current context (Banked + CURRENT Floating)
    current_snap = proc_data[
        ((proc_data['Category'] == 'Stage Result') & (proc_data['Stage'] <= current_stage)) |
        ((proc_data['Category'] != 'Stage Result') & (proc_data['Stage'] == current_stage))
    ]
    rider_pts = current_snap.groupby(['owner', 'rider_name'])['pts'].sum().reset_index()
    
    col1, col2 = st.columns(2)
    for i, owner in enumerate(["Daniel", "Tanner"]):
        with (col1 if i==0 else col2):
            st.subheader(owner)
            df = rider_pts[rider_pts['owner'] == owner].sort_values('pts', ascending=False)
            st.dataframe(df[['rider_name', 'pts']].rename(columns={'rider_name':'Rider','pts':'Points'}), use_container_width=True, hide_index=True)

# --- NAVIGATION ---
pg = st.navigation([
    st.Page(show_dashboard, title="Standings", icon="📊"),
    st.Page(show_history, title="Stage Snapshots", icon="📜"),
    st.Page(show_rosters, title="Teams", icon="👥")
])
pg.run()
