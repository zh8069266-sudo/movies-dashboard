from pathlib import Path
import io
import sqlite3
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Movies Analytics Dashboard", page_icon="🎬", layout="wide")
COLORS = ["#7C6CF2", "#16C7A3", "#FFB74D", "#FF6B6B", "#4EA5FF", "#A78BFA"]

st.markdown("""
<style>
.stApp {background:linear-gradient(135deg,#0b1020,#111831 55%,#0b1020); color:#eef2ff;}
[data-testid="stSidebar"] {background:#0d1428; border-right:1px solid #27304f;}
.block-container {padding-top:1.3rem; padding-bottom:2rem;}
.hero {padding:23px 26px;border:1px solid #2b365c;border-radius:20px;
background:linear-gradient(120deg,rgba(124,108,242,.27),rgba(22,199,163,.12));margin-bottom:18px;}
.hero h1 {margin:0;color:white;font-size:2rem}.hero p{color:#b8c1dc;margin:8px 0 0}
.kpi {background:rgba(18,27,52,.94);border:1px solid #2b365c;border-radius:17px;padding:17px;min-height:120px;box-shadow:0 10px 30px rgba(0,0,0,.18)}
.kpi-label{color:#9ba7c8;font-size:.88rem}.kpi-value{color:#fff;font-size:1.5rem;font-weight:700;margin-top:9px}.kpi-note{color:#6f7b9d;font-size:.75rem;margin-top:5px}
</style>
""", unsafe_allow_html=True)

@st.cache_data(show_spinner=False)
def load_data(raw: bytes, filename: str):
    if filename.lower().endswith(".csv"):
        df = pd.read_csv(io.BytesIO(raw), low_memory=False)
    elif filename.lower().endswith((".db", ".sqlite", ".sqlite3")):
        temp = Path("temp_movies.db")
        temp.write_bytes(raw)
        with sqlite3.connect(temp) as con:
            tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name", con)["name"].tolist()
            if not tables:
                raise ValueError("The SQLite database contains no tables.")
            table = next((x for x in tables if x.lower() in {"movies", "movie", "films"}), tables[0])
            df = pd.read_sql_query(f'SELECT * FROM "{table}"', con)
    else:
        raise ValueError("Only CSV and SQLite files are supported.")

    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    defaults = {"title":"", "release_date":pd.NaT, "revenue":0, "budget":0,
                "vote_average":np.nan, "vote_count":0, "runtime":np.nan,
                "popularity":np.nan, "genres":"", "directors":"",
                "original_languag":"Unknown"}
    for col, value in defaults.items():
        if col not in df.columns:
            df[col] = value
    for col in ["revenue","budget","vote_average","vote_count","runtime","popularity"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["release_date"] = pd.to_datetime(df["release_date"], errors="coerce")
    df["year"] = df["release_date"].dt.year.astype("Int64")
    df["profit"] = df["revenue"].fillna(0) - df["budget"].fillna(0)
    df["primary_genre"] = df["genres"].fillna("").astype(str).str.split(",").str[0].str.strip().replace("", "Unknown")
    df["primary_director"] = df["directors"].fillna("").astype(str).str.split(",").str[0].str.strip().replace("", "Unknown")
    df["language"] = df["original_languag"].fillna("Unknown").replace("", "Unknown")
    keys = ["id"] if "id" in df.columns else ["title", "release_date"]
    return df.drop_duplicates(subset=keys, keep="first")

def compact_money(value):
    value = float(value or 0)
    if abs(value) >= 1e9: return f"${value/1e9:,.2f}B"
    if abs(value) >= 1e6: return f"${value/1e6:,.1f}M"
    if abs(value) >= 1e3: return f"${value/1e3:,.1f}K"
    return f"${value:,.0f}"

def metric_card(label, value, note):
    st.markdown(f'<div class="kpi"><div class="kpi-label">{label}</div><div class="kpi-value">{value}</div><div class="kpi-note">{note}</div></div>', unsafe_allow_html=True)

def chart_style(fig, title, height=420):
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      title=title, height=height, margin=dict(l=20,r=20,t=60,b=30), colorway=COLORS, legend_title_text="")
    return fig

st.markdown('<div class="hero"><h1>🎬 Movies Analytics Dashboard</h1><p>Interactive analysis of revenue, budgets, ratings, genres, and directors</p></div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ Data Source")
    uploaded = st.file_uploader("Upload your data file", type=["csv","db","sqlite","sqlite3"])
    local_file = Path("movies_sample.csv")
    if uploaded:
        raw, filename = uploaded.getvalue(), uploaded.name
    elif local_file.exists():
        raw, filename = local_file.read_bytes(), local_file.name
    else:
        raw, filename = None, None

if raw is None:
    st.info("Upload SQLite11.csv from the sidebar, or place it in the same folder as app.py.")
    st.stop()

try:
    df = load_data(raw, filename)
except Exception as exc:
    st.error(f"Could not read the file: {exc}")
    st.stop()

with st.sidebar:
    st.success(f"Loaded {len(df):,} rows")
    st.header("🔎 Filters")
    years = df["year"].dropna().astype(int)
    year_range = st.slider("Release Year", int(years.min()), int(years.max()), (int(years.min()), int(years.max()))) if len(years) else None
    genres = sorted(df["primary_genre"].dropna().unique().tolist())
    selected_genres = st.multiselect("Genre", genres)
    languages = sorted(df["language"].dropna().astype(str).unique().tolist())
    selected_languages = st.multiselect("Original Language", languages)
    min_rating = st.slider("Minimum Rating", 0.0, 10.0, 0.0, 0.1)
    min_votes = st.number_input("Minimum Vote Count", min_value=0, value=0, step=1000)
    search = st.text_input("Search by Movie Title")

filtered = df.copy()
if year_range: filtered = filtered[filtered["year"].between(*year_range)]
if selected_genres: filtered = filtered[filtered["primary_genre"].isin(selected_genres)]
if selected_languages: filtered = filtered[filtered["language"].isin(selected_languages)]
filtered = filtered[filtered["vote_average"].fillna(0) >= min_rating]
filtered = filtered[filtered["vote_count"].fillna(0) >= min_votes]
if search: filtered = filtered[filtered["title"].fillna("").str.contains(search, case=False, na=False)]

if filtered.empty:
    st.warning("No results match the current filters. Try relaxing the filters.")
    st.stop()

cols = st.columns(5)
with cols[0]: metric_card("Total Movies", f"{len(filtered):,}", f"out of {len(df):,}")
with cols[1]: metric_card("Total Revenue", compact_money(filtered["revenue"].sum()), "filtered movies")
with cols[2]: metric_card("Average Rating", f'{filtered["vote_average"].mean():.2f} / 10', "vote average")
with cols[3]: metric_card("Total Profit", compact_money(filtered["profit"].sum()), "revenue minus budget")
with cols[4]: metric_card("Average Runtime", f'{filtered["runtime"].mean():.0f} min', "excluding missing values")

st.write("")
tab1, tab2, tab3, tab4 = st.tabs(["📊 Overview", "💰 Financial Performance", "⭐ Quality & Audience", "🎭 Genres & Directors"])

with tab1:
    left, right = st.columns([1.4,1])
    yearly = filtered.dropna(subset=["year"]).groupby("year", as_index=False).agg(movies=("title","count"))
    with left:
        fig = px.area(yearly, x="year", y="movies", markers=True, color_discrete_sequence=[COLORS[0]])
        st.plotly_chart(chart_style(fig, "Movies by Release Year"), use_container_width=True)
    with right:
        top = filtered.nlargest(10,"revenue").sort_values("revenue")
        fig = px.bar(top, x="revenue", y="title", orientation="h", color="revenue", color_continuous_scale=["#2A2F55","#7C6CF2","#16C7A3"])
        fig.update_coloraxes(showscale=False); fig.update_xaxes(tickformat="$,.2s")
        st.plotly_chart(chart_style(fig, "Top 10 Movies by Revenue"), use_container_width=True)
    left, right = st.columns(2)
    with left:
        fig = px.histogram(filtered, x="vote_average", nbins=25, color_discrete_sequence=[COLORS[1]])
        st.plotly_chart(chart_style(fig, "Rating Distribution"), use_container_width=True)
    with right:
        genre_counts = filtered["primary_genre"].value_counts().head(10).reset_index()
        genre_counts.columns = ["genre","movies"]
        fig = px.treemap(genre_counts, path=["genre"], values="movies", color="movies", color_continuous_scale=["#171F3D","#7C6CF2","#16C7A3"])
        st.plotly_chart(chart_style(fig, "Most Common Genres"), use_container_width=True)

with tab2:
    valid = filtered[(filtered["budget"]>0) & (filtered["revenue"]>0)].copy()
    left, right = st.columns([1.35,1])
    with left:
        fig = px.scatter(valid, x="budget", y="revenue", size="vote_count", color="vote_average", hover_name="title",
                         color_continuous_scale=["#FF6B6B","#FFB74D","#16C7A3"], size_max=38, log_x=True, log_y=True)
        fig.update_xaxes(tickformat="$,.2s"); fig.update_yaxes(tickformat="$,.2s")
        st.plotly_chart(chart_style(fig, "Budget vs Revenue (Log Scale)"), use_container_width=True)
    with right:
        top_profit = valid.nlargest(10,"profit").sort_values("profit")
        fig = px.bar(top_profit, x="profit", y="title", orientation="h", color="profit", color_continuous_scale=["#2A2F55","#16C7A3"])
        fig.update_coloraxes(showscale=False); fig.update_xaxes(tickformat="$,.2s")
        st.plotly_chart(chart_style(fig, "Top 10 Movies by Profit"), use_container_width=True)

with tab3:
    left, right = st.columns(2)
    with left:
        best = filtered[filtered["vote_count"] >= max(1000,min_votes)].nlargest(15,"vote_average").sort_values("vote_average")
        fig = px.bar(best, x="vote_average", y="title", orientation="h", color="vote_count", color_continuous_scale=["#343B65","#A78BFA","#16C7A3"])
        st.plotly_chart(chart_style(fig, "Top-Rated Movies with at Least 1,000 Votes"), use_container_width=True)
    with right:
        fig = px.scatter(filtered, x="popularity", y="vote_average", size="vote_count", color="primary_genre", hover_name="title", size_max=30)
        st.plotly_chart(chart_style(fig, "Popularity vs Rating"), use_container_width=True)

with tab4:
    left, right = st.columns(2)
    genres_summary = filtered.groupby("primary_genre",as_index=False).agg(movies=("title","count"),average_rating=("vote_average","mean")).query("movies >= 3").nlargest(15,"movies")
    with left:
        fig = px.bar(genres_summary.sort_values("movies"), x="movies", y="primary_genre", orientation="h", color="average_rating", color_continuous_scale=["#FF6B6B","#FFB74D","#16C7A3"])
        st.plotly_chart(chart_style(fig, "Genre Volume and Average Rating"), use_container_width=True)
    with right:
        directors = filtered.groupby("primary_director",as_index=False).agg(movies=("title","count"),average_rating=("vote_average","mean"),revenue=("revenue","sum")).query("primary_director != 'Unknown' and movies >= 2").nlargest(12,"revenue").sort_values("revenue")
        fig = px.bar(directors, x="revenue", y="primary_director", orientation="h", color="average_rating", color_continuous_scale=["#343B65","#A78BFA","#16C7A3"])
        fig.update_xaxes(tickformat="$,.2s")
        st.plotly_chart(chart_style(fig, "Top Directors by Revenue"), use_container_width=True)

st.subheader("🏆 Movies Table")
columns = [c for c in ["title","year","primary_genre","directors","vote_average","vote_count","budget","revenue","profit","runtime"] if c in filtered.columns]
st.dataframe(filtered.sort_values(["vote_average","vote_count"],ascending=False)[columns].head(250), use_container_width=True, hide_index=True)
st.download_button("⬇️ Download Filtered Results as CSV", filtered.to_csv(index=False).encode("utf-8-sig"), "filtered_movies.csv", "text/csv", use_container_width=True)
st.caption("Built with Streamlit and Plotly. All metrics update automatically with the filters.")
