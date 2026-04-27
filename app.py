import streamlit as st
import pandas as pd
import unicodedata
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go

# --- 1. SETTINGS ---
st.set_page_config(
    page_title="2026 Fantasy Cycling", 
    layout="wide", 
    initial_sidebar_state="auto"
)

COLOR_MAP = {"Tanner": "#1f77b4", "Daniel": "#d62728"}

SCORING = {
    "Tier 1": {1: 30, 2: 27, 3: 24, 4: 21, 5: 18, 6: 15, 7: 12, 8: 9, 9: 6, 10: 3},
    "Tier 2": {1: 20, 2: 18, 3: 16, 4: 14, 5: 12, 6: 10, 7: 8, 8: 6, 9: 4, 10: 2},
    "Tier 3": {1: 10, 2: 9, 3: 8, 4: 7, 5: 6, 6: 5, 7: 4, 8: 3, 9: 2, 10: 1}
}

# --- 2. HELPERS ---
def normalize_name(name):
    if not isinstance(name, str): return ""
    name = "".join(c for c in unicodedata.normalize('NFD', name) if unicodedata.category(c) != 'Mn')
    return name.lower().replace('-', ' ').strip()

def get_ordinal(n):
    if 11 <= (n % 100) <= 13:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return str(n) + suffix

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if st.session_state["password_correct"]:
        return True
    with st.sidebar.expander("🔐 Developer Access"):
        password = st.text_input("Enter Passcode", type="password")
        if st.button("Unlock"):
            if password == "1375":
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("Incorrect passcode")
    return False

def format_stage_safe(val):
    if pd.isna(val) or str(val).strip() == "" or str(val).lower() == "one day race":
        return "—"
    try:
        return f"S{int(float(val))}"
    except (ValueError, TypeError):
        return str(val)

def parse_cycling_date(date_str):
    if not isinstance(date_str, str): return pd.NaT
    start_part = date_str.split('–')[0].split('-')[0].strip()
    try:
        dt = pd.to_datetime(f"{start_part} 2026", errors='coerce')
        return dt
    except:
        return pd.NaT

@st.cache_data(ttl=300)
def load_all_data():
    try:
        y2026_r = pd.read_csv('riders.csv')
        dynasty_r = pd.read_csv('dynastyriders.csv')
        schedule = pd.read_csv('schedule.csv')
        
        schedule['original_date'] = schedule['date']
        schedule['date'] = schedule['date'].apply(parse_cycling_date)
        
        results = pd.read_excel('results.xlsx', engine='openpyxl')
        results['Date'] = pd.to_datetime(results['Date'], errors='coerce')
        
        for df in [y2026_r, dynasty_r]:
            df['team_pick'] = df.groupby('owner').cumcount() + 1
            df['add_date'] = pd.to_datetime(df['add_date'], errors='coerce')
            df['drop_date'] = pd.to_datetime(df['drop_date'], errors='coerce').fillna(pd.Timestamp('2026-12-31'))
            df['match_name'] = df['rider_name'].apply(normalize_name)
            
        return y2026_r, dynasty_r, schedule, results
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return None, None, None, None

# --- 3. DATA PROCESSING ---
r2026, d_riders, schedule_df, results_raw = load_all_data()

def process_league_data(riders_df, schedule, results):
    if riders_df is None or results is None:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    
    rank_cols = ['1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th', '10th']
    id_cols = ['Date', 'Race Name']
    if 'Stage' in results.columns: id_cols.append('Stage')
    
    df_l = results.melt(id_vars=id_cols, value_vars=rank_cols, var_name='Pos_Label', value_name='result_rider_name')
    df_l['rank'] = df_l['Pos_Label'].str.extract(r'(\d+)').astype(int)
    df_l['match_name'] = df_l['result_rider_name'].apply(normalize_name)
    df_l = df_l.merge(schedule[['race_name', 'tier']], left_on='Race Name', right_on='race_name', how='left')
    
    proc = df_l.merge(riders_df[['match_name', 'owner', 'rider_name', 'team_pick', 'add_date', 'drop_date']], on='match_name', how='inner')
    proc = proc[(proc['Date'] >= proc['add_date']) & (proc['Date'] <= proc['drop_date'])].copy()
    proc['pts'] = proc.apply(lambda r: SCORING.get(r['tier'], {}).get(r['rank'], 0), axis=1)
    
    leaderb = proc.groupby('owner')['pts'].sum().reset_index()
    scored = proc.groupby(['owner', 'rider_name', 'team_pick'])['pts'].sum().reset_index()
    pts_total = riders_df[['owner', 'rider_name', 'team_pick']].merge(scored, on=['owner', 'rider_name', 'team_pick'], how='left').fillna(0)
    
    return proc, leaderb, pts_total

proc2026, lb2026, pts2026 = process_league_data(r2026, schedule_df, results_raw)
dynasty_proc, dynasty_lb, dynasty_pts = process_league_data(d_riders, schedule_df, results_raw)

leagues = {
    "2026": {"proc": proc2026, "lb": lb2026, "pts": pts2026},
    "Dynasty": {"proc": dynasty_proc, "lb": dynasty_lb, "pts": dynasty_pts}
}

# --- 4. PAGE DEFINITIONS ---

def render_dashboard(league_key, title):
    st.title(title)
    data = leagues[league_key]
    
    if data["proc"].empty:
        st.info("No points recorded yet for this league.")
        return

    d_total = int(data["lb"][data["lb"]['owner'] == "Daniel"]['pts'].sum())
    t_total = int(data["lb"][data["lb"]['owner'] == "Tanner"]['pts'].sum())
    current_leader = "Daniel" if d_total >= t_total else "Tanner"
    opponent = "Tanner" if current_leader == "Daniel" else "Daniel"
    
    m1, m2, m3 = st.columns(3)
    with m1: st.metric(current_leader, f"{d_total if current_leader == 'Daniel' else t_total} Pts")
    with m2: st.metric(opponent, f"{t_total if current_leader == 'Daniel' else d_total} Pts")
    with m3: st.metric("Overall Lead", f"{abs(d_total - t_total)} Pts")

    st.divider()

    col_left, col_right = st.columns([1, 2])
    with col_left:
        st.subheader("🏆 Top Scorers")
        for name in [current_leader, opponent]:
            st.markdown(f"**{name} Top 5**")
            top5 = data["pts"][data["pts"]['owner'] == name].nlargest(5, 'pts')[['rider_name', 'pts']]
            st.dataframe(top5.rename(columns={'rider_name':'Rider','pts':'Points'}), hide_index=True, use_container_width=True)

    with col_right:
        st.subheader("📈 Leader's Advantage")
        timeline = data["proc"].groupby(['Date', 'owner'])['pts'].sum().unstack(fill_value=0)
        full_range = pd.date_range(start=timeline.index.min(), end=timeline.index.max())
        cumulative = timeline.reindex(full_range, fill_value=0).cumsum()
        for name in ["Daniel", "Tanner"]:
            if name not in cumulative.columns: cumulative[name] = 0
        cumulative['Gap'] = cumulative[current_leader] - cumulative[opponent]
        chart_data = cumulative.reset_index().rename(columns={'index': 'Date'})
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=chart_data['Date'], y=chart_data['Gap'].clip(lower=0), fill='tozeroy', fillcolor='rgba(31, 119, 180, 0.4)', line=dict(width=0), hoverinfo='skip'))
        fig.add_trace(go.Scatter(x=chart_data['Date'], y=chart_data['Gap'].clip(upper=0), fill='tozeroy', fillcolor='rgba(214, 39, 40, 0.4)', line=dict(width=0), hoverinfo='skip'))
        fig.add_trace(go.Scatter(x=chart_data['Date'], y=chart_data['Gap'], mode='lines', line=dict(width=3, color='black'), hovertemplate=f"Date: %{{x}}<br>{current_leader} Lead: %{{y}} pts<extra></extra>"))
        fig.add_hline(y=0, line_dash="solid", line_color="#888", line_width=1)
        fig.update_layout(hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    st.divider()

    c_rec, c_up = st.columns(2)
    with c_rec:
        st.subheader("🏁 Latest Results")
        if not data["proc"].empty:
            recent_dates = data["proc"]['Date'].sort_values(ascending=False).unique()[:3]
            recent = data["proc"][data["proc"]['Date'].isin(recent_dates)].sort_values(
                by=['Date', 'Race Name', 'rank'], 
                ascending=[False, True, True]
            )
            recent_disp = recent[['Date', 'Race Name', 'Stage', 'rider_name', 'owner', 'rank', 'pts']].copy()
            recent_disp['Date'] = recent_disp['Date'].dt.strftime('%b %d')
            recent_disp['Stage'] = recent_disp['Stage'].apply(format_stage_safe)
            recent_disp['Place'] = recent_disp['rank'].apply(get_ordinal)
            st.dataframe(recent_disp[['Date', 'Race Name', 'Stage', 'rider_name', 'owner', 'Place', 'pts']].rename(columns={'rider_name':'Rider','owner':'Owner','pts':'Pts'}), hide_index=True, use_container_width=True)
        else:
            st.write("No results recorded yet.")

    with c_up:
        st.subheader("📅 Upcoming 5 Races")
        today = pd.Timestamp(datetime.now().date())
        upcoming = schedule_df[schedule_df['date'] >= today].nsmallest(5, 'date')
        if not upcoming.empty:
            upcoming_disp = upcoming[['original_date', 'race_name', 'tier']].copy()
            st.dataframe(upcoming_disp.rename(columns={'original_date':'Date','race_name':'Race','tier':'Tier'}), hide_index=True, use_container_width=True)
        else:
            st.write("No more races scheduled.")

def show_2026(): render_dashboard("2026", "2026 Fantasy Cycling Dashboard")
def show_dynasty(): render_dashboard("Dynasty", "Dynasty Fantasy Cycling Dashboard")

def show_point_history():
    st.title("Point History")
    choice = st.radio("Select League", ["2026", "Dynasty"], horizontal=True) if st.session_state.get("password_correct") else "2026"
    proc = leagues[choice]["proc"]
    if proc.empty: return
    ytd = proc.sort_values(by=['Date', 'Race Name', 'rank'], ascending=[False, True, True]).copy()
    ytd['Date_Str'] = ytd['Date'].dt.strftime('%b %d')
    ytd['Full_Stage'] = ytd['Stage'].apply(format_stage_safe)
    ytd['Place_Label'] = ytd['rank'].apply(get_ordinal)
    
    st.dataframe(ytd[['Date_Str', 'Race Name', 'Full_Stage', 'rider_name', 'owner', 'Place_Label', 'pts']].rename(
        columns={'Date_Str':'Date', 'rider_name':'Rider', 'Full_Stage':'Stage', 'owner':'Team', 'Place_Label':'Place', 'pts':'Points'}
    ), hide_index=True, use_container_width=True)

def show_roster():
    st.title("Master Roster Comparison")
    choice = st.radio("Select League", ["2026", "Dynasty"], horizontal=True) if st.session_state.get("password_correct") else "2026"
    pts = leagues[choice]["pts"]
    pick_indices = list(range(1, 31))
    def get_team(owner):
        team_data = pts[pts['owner'] == owner]
        names, vals = [], []
        for p in pick_indices:
            row = team_data[team_data['team_pick'] == p]
            names.append(row.iloc[0]['rider_name'] if not row.empty else "—")
            vals.append(int(row.iloc[0]['pts']) if not row.empty else 0)
        return names, vals
    t_n, t_p = get_team("Tanner")
    d_n, d_p = get_team("Daniel")
    
    st.dataframe(pd.DataFrame({
        "Slot": pick_indices, 
        "Tanner": t_n, 
        "Points (T)": t_p, 
        "Daniel": d_n, 
        "Points (D)": d_p
    }), hide_index=True, use_container_width=True, height=1000)

def show_analysis():
    st.title("Draft Performance Analysis")
    choice = st.radio("Select League", ["2026", "Dynasty"], horizontal=True) if st.session_state.get("password_correct") else "2026"
    pts = leagues[choice]["pts"]
    
    st.subheader("Tiered Breakdown (Groups of 10)")
    groups_10 = [(f"Picks {i}–{i+9}", i, i+9) for i in range(1, 31, 10)]
    
    for label, start, end in groups_10:
        t_pts = int(pts[(pts['owner'] == "Tanner") & (pts['team_pick'] >= start) & (pts['team_pick'] <= end)]['pts'].sum())
        d_pts = int(pts[(pts['owner'] == "Daniel") & (pts['team_pick'] >= start) & (pts['team_pick'] <= end)]['pts'].sum())
        
        with st.expander(f"{label} Summary — Tanner: {t_pts} | Daniel: {d_pts}"):
            c1, c2 = st.columns(2)
            for i, owner in enumerate(["Tanner", "Daniel"]):
                with (c1 if i==0 else c2):
                    owner_df = pts[(pts['owner'] == owner) & (pts['team_pick'] >= start) & (pts['team_pick'] <= end)]
                    st.dataframe(
                        owner_df[['team_pick', 'rider_name', 'pts']].rename(columns={'team_pick':'Slot','rider_name':'Rider','pts':'Points'}), 
                        hide_index=True, use_container_width=True
                    )

def show_schedule():
    st.title("Full 2026 Schedule")
    st.dataframe(schedule_df[['original_date', 'race_name', 'tier', 'race_type']].rename(columns={'original_date':'Date','race_name':'Race','tier':'Tier','race_type':'Type'}), hide_index=True, use_container_width=True, height=1000)

def show_free_agents():
    st.title("Free Agent Database")
    
    # Toggle logic for which league roster to exclude
    fa_league = st.radio("Show Free Agents for:", ["2026", "Dynasty"], horizontal=True)
    
    rank_cols = ['1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th', '10th']
    df_all = results_raw.melt(id_vars=['Race Name'], value_vars=rank_cols, var_name='rank_label', value_name='rider_name')
    df_all['rank'] = df_all['rank_label'].str.extract(r'(\d+)').astype(int)
    df_all = df_all.merge(schedule_df[['race_name', 'tier']], left_on='Race Name', right_on='race_name', how='left')
    df_all['pts'] = df_all.apply(lambda r: SCORING.get(r['tier'], {}).get(r['rank'], 0), axis=1)
    
    total_scores = df_all.groupby('rider_name')['pts'].sum().reset_index()
    total_scores['match_name'] = total_scores['rider_name'].apply(normalize_name)
    
    # Filter based on selected league
    if fa_league == "2026":
        drafted_names = set(r2026['match_name'].tolist())
    else:
        drafted_names = set(d_riders['match_name'].tolist())
        
    free_agents = total_scores[~total_scores['match_name'].isin(drafted_names)].sort_values(by='pts', ascending=False)
    
    st.info(f"Displaying riders not currently owned in the {fa_league} league.")
    st.dataframe(free_agents[['rider_name', 'pts']].rename(columns={'rider_name': 'Rider', 'pts': 'Total Points'}), hide_index=True, use_container_width=True)

# --- 5. NAVIGATION ---
pages = [
    st.Page(show_2026, title="2026 Dashboard", icon="📊"), 
    st.Page(show_point_history, title="Point History", icon="📜"),
    st.Page(show_roster, title="Master Roster", icon="👥"), 
    st.Page(show_analysis, title="Analysis", icon="📈"),
    st.Page(show_schedule, title="Full Schedule", icon="📅")
]

# Only appended if password is correct
if check_password():
    pages.append(st.Page(show_free_agents, title="Free Agent Database", icon="🆓"))
    pages.append(st.Page(show_dynasty, title="Dynasty Dashboard", icon="🏆"))

pg = st.navigation(pages)
pg.run()
