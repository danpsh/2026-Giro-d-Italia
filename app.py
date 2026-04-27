import streamlit as st
import pandas as pd
import unicodedata
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go

# --- 1. SETTINGS ---
st.set_page_config(
    page_title="2026 Giro League", 
    layout="wide", 
    initial_sidebar_state="auto"
)

COLOR_MAP = {"Tanner": "#1f77b4", "Daniel": "#d62728"}

# Updated Scoring based on Giro Image
# Note: GC and Stages use the same 1-10 scale. Jerseys use 1-3.
SCORING = {
    "GC": {1: 50, 2: 40, 3: 30, 4: 25, 5: 20, 6: 18, 7: 16, 8: 14, 9: 12, 10: 10},
    "Stage": {1: 10, 2: 9, 3: 8, 4: 7, 5: 6, 6: 5, 7: 4, 8: 3, 9: 2, 10: 1},
    "Jersey": {1: 15, 2: 10, 3: 5} # Applied to Points, Mountain, and Young Rider
}

# Replacement Multipliers based on Draft Round
REPLACEMENT_MAP = {
    1: 1.0, 2: 1.0,
    3: 0.9, 4: 0.9,
    5: 0.8, 6: 0.8,
    7: 0.7, 8: 0.7,
    9: 0.6, 10: 0.6,
    11: 0.5, 12: 0.5, 13: 0.5, 14: 0.5, 15: 0.5
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
        
        # Expecting columns: Date, Race Name, Stage, Category (GC, Stage, Points, Mountain, Young), and 1st-10th
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
    id_cols = ['Date', 'Race Name', 'Stage', 'Category']
    
    df_l = results.melt(id_vars=id_cols, value_vars=rank_cols, var_name='Pos_Label', value_name='result_rider_name')
    df_l['rank'] = df_l['Pos_Label'].str.extract(r'(\d+)').astype(int)
    df_l['match_name'] = df_l['result_rider_name'].apply(normalize_name)
    
    proc = df_l.merge(riders_df[['match_name', 'owner', 'rider_name', 'team_pick', 'add_date', 'drop_date', 'is_replacement']], on='match_name', how='inner')
    
    # Filter for active dates
    proc = proc[(proc['Date'] >= proc['add_date']) & (proc['Date'] <= proc['drop_date'])].copy()
    
    def calculate_points(row):
        cat = row['Category']
        rank = row['rank']
        
        # Base Points
        if cat == "GC":
            base = SCORING["GC"].get(rank, 0)
        elif cat == "Stage":
            base = SCORING["Stage"].get(rank, 0)
        else: # Points, Mountain, or Young Rider Jerseys
            base = SCORING["Jersey"].get(rank, 0)
            
        # Apply Replacement Penalty if applicable
        if row.get('is_replacement', False):
            multiplier = REPLACEMENT_MAP.get(row['team_pick'], 0.5)
            return base * multiplier
        return base

    proc['pts'] = proc.apply(calculate_points, axis=1)
    
    leaderb = proc.groupby('owner')['pts'].sum().reset_index()
    scored = proc.groupby(['owner', 'rider_name', 'team_pick'])['pts'].sum().reset_index()
    pts_total = riders_df[['owner', 'rider_name', 'team_pick']].merge(scored, on=['owner', 'rider_name', 'team_pick'], how='left').fillna(0)
    
    return proc, leaderb, pts_total

# Assuming your riders.csv has an 'is_replacement' column (True/False)
if r2026 is not None and 'is_replacement' not in r2026.columns:
    r2026['is_replacement'] = False
if d_riders is not None and 'is_replacement' not in d_riders.columns:
    d_riders['is_replacement'] = False

proc2026, lb2026, pts2026 = process_league_data(r2026, schedule_df, results_raw)
dynasty_proc, dynasty_lb, dynasty_pts = process_league_data(d_riders, schedule_df, results_raw)

leagues = {
    "Giro 2026": {"proc": proc2026, "lb": lb2026, "pts": pts2026},
    "Dynasty": {"proc": dynasty_proc, "lb": dynasty_lb, "pts": dynasty_pts}
}

# --- 4. PAGE DEFINITIONS --- (Same dashboard logic as before)
def render_dashboard(league_key, title):
    st.title(title)
    data = leagues[league_key]
    
    if data["proc"].empty:
        st.info("No points recorded yet for this league.")
        return

    d_total = round(float(data["lb"][data["lb"]['owner'] == "Daniel"]['pts'].sum()), 1)
    t_total = round(float(data["lb"][data["lb"]['owner'] == "Tanner"]['pts'].sum()), 1)
    current_leader = "Daniel" if d_total >= t_total else "Tanner"
    opponent = "Tanner" if current_leader == "Daniel" else "Daniel"
    
    m1, m2, m3 = st.columns(3)
    with m1: st.metric(current_leader, f"{d_total if current_leader == 'Daniel' else t_total} Pts")
    with m2: st.metric(opponent, f"{t_total if current_leader == 'Daniel' else d_total} Pts")
    with m3: st.metric("Overall Lead", f"{round(abs(d_total - t_total), 1)} Pts")

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
            recent = data["proc"][data["proc"]['Date'].isin(recent_dates)].sort_values(by=['Date', 'Race Name', 'rank'], ascending=[False, True, True])
            recent_disp = recent[['Date', 'Race Name', 'Category', 'Stage', 'rider_name', 'owner', 'rank', 'pts']].copy()
            recent_disp['Date'] = recent_disp['Date'].dt.strftime('%b %d')
            recent_disp['Stage'] = recent_disp['Stage'].apply(format_stage_safe)
            recent_disp['Place'] = recent_disp['rank'].apply(get_ordinal)
            st.dataframe(recent_disp[['Date', 'Race Name', 'Category', 'rider_name', 'owner', 'Place', 'pts']].rename(columns={'rider_name':'Rider','owner':'Owner','pts':'Pts'}), hide_index=True, use_container_width=True)

    with c_up:
        st.subheader("📅 Upcoming 5 Races")
        today = pd.Timestamp(datetime.now().date())
        upcoming = schedule_df[schedule_df['date'] >= today].nsmallest(5, 'date')
        if not upcoming.empty:
            upcoming_disp = upcoming[['original_date', 'race_name', 'race_type']].copy()
            st.dataframe(upcoming_disp.rename(columns={'original_date':'Date','race_name':'Race','race_type':'Type'}), hide_index=True, use_container_width=True)

def show_giro(): render_dashboard("Giro 2026", "2026 Giro d'Italia Dashboard")
def show_dynasty(): render_dashboard("Dynasty", "Dynasty Fantasy Cycling Dashboard")

# (Point History, Roster, Analysis, etc remain largely the same, just utilizing the new SCORING)
def show_point_history():
    st.title("Point History")
    choice = st.radio("Select League", ["Giro 2026", "Dynasty"], horizontal=True) if st.session_state.get("password_correct") else "Giro 2026"
    proc = leagues[choice]["proc"]
    if proc.empty: return
    ytd = proc.sort_values(by=['Date', 'Race Name', 'rank'], ascending=[False, True, True]).copy()
    ytd['Date_Str'] = ytd['Date'].dt.strftime('%b %d')
    ytd['Full_Stage'] = ytd['Stage'].apply(format_stage_safe)
    ytd['Place_Label'] = ytd['rank'].apply(get_ordinal)
    st.dataframe(ytd[['Date_Str', 'Race Name', 'Category', 'Full_Stage', 'rider_name', 'owner', 'Place_Label', 'pts']].rename(
        columns={'Date_Str':'Date', 'rider_name':'Rider', 'Full_Stage':'Stage', 'owner':'Team', 'Place_Label':'Place', 'pts':'Points'}
    ), hide_index=True, use_container_width=True)

# ... (rest of the functions: show_roster, show_analysis, show_schedule, show_free_agents) ...

# --- 5. NAVIGATION ---
pages = [
    st.Page(show_giro, title="Giro Dashboard", icon="🚴"), 
    st.Page(show_point_history, title="Point History", icon="📜"),
    st.Page(show_roster, title="Master Roster", icon="👥"), 
    st.Page(show_analysis, title="Analysis", icon="📈")
]

if check_password():
    pages.append(st.Page(show_dynasty, title="Dynasty Dashboard", icon="🏆"))

pg = st.navigation(pages)
pg.run()
