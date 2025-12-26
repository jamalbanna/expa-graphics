import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import plotly.express as px

# -----------------------------------------------------------------------------
# Page config
st.set_page_config(
    page_title='AIESEC Exchange Analytics',
    page_icon='🌍',
    layout='wide'
)

st.title("🌍 AIESEC Exchange Analytics Dashboard")

# -----------------------------------------------------------------------------
# Sidebar Inputs
st.sidebar.header("API & Filter Settings")

access_token = st.sidebar.text_input(
    "Enter your AIESEC EXPA API Access Token",
    type="password"
)
if not access_token:
    st.info("""
        🔑 Please enter your AIESEC EXPA Analytics access token in the sidebar.  
        You can get your token by:
        1. Going to [EXPA Analytics](https://expa.aiesec.org/analytics/)
        2. Logging in
        3. Copying the access token from your account settings or API section
    """)
    st.stop()

# Exchange type (single select)
exchange_type_map = {
    "Outgoing": "person",
    "Incoming": "opportunity"
}
selected_exchange_type = st.sidebar.selectbox(
    "Select Exchange Type",
    options=list(exchange_type_map.keys())
)

# Programmes (multi-select)
programme_map = {
    "Global Volunteer": 6,
    "Global Talent": 7,
    "Global Teacher": 8
}
selected_programmes = st.sidebar.multiselect(
    "Select Programme(s)",
    options=list(programme_map.keys()),
    default=list(programme_map.keys())
)

# Entity filter (required)
entity_id_input = st.sidebar.text_input(
    "Enter Entity ID (required)",
    value=""
)
try:
    office_id = int(entity_id_input)
except:
    st.warning("Please enter a valid numeric Entity ID")
    st.stop()

# Date range
start_date = st.sidebar.date_input("Start Date", value=datetime(2024, 1, 1))
end_date = st.sidebar.date_input("End Date", value=datetime(2024, 12, 31))

# Chart styling options
st.sidebar.header("Chart Options")
line_shape = st.sidebar.selectbox("Line Style", ["linear", "spline"])

# -----------------------------------------------------------------------------
# Function: fetch data
@st.cache_data(ttl=3600)
def fetch_exchange_data(token, exchange_type, programmes, start_date, end_date, interval="month", office_id=None):
    API_URL = "https://analytics.api.aiesec.org/v2/applications/analyze.json"

    params = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "histogram[type]": exchange_type_map[exchange_type],  # dynamic by exchange type
        "histogram[interval]": interval,
        "exchange_type": exchange_type_map[exchange_type],
        "histogram[office_id]": office_id,
        "access_token": token
    }

    for prog in programmes:
        params.setdefault("programmes[]", []).append(programme_map[prog])

    response = requests.get(API_URL, params=params)
    if response.status_code != 200:
        st.error(f"API request failed with status code {response.status_code}")
        st.json(response.json())
        st.stop()

    json_data = response.json()
    if "analytics" not in json_data:
        st.error("API response does not contain 'analytics'. Full response:")
        st.json(json_data)
        st.stop()

    data = json_data["analytics"]

    STATUS_MAP = {
        "total_applications": "Applied",
        "total_an_accepted": "Accepted",
        "total_approvals": "Approved",
        "total_realized": "Realized",
        "total_finished": "Finished",
        "total_completed": "Completed"
    }

    rows = []
    for key, label in STATUS_MAP.items():
        if key not in data:
            continue
        parent_key = "people" if key == "total_signup" else "applications"
        if parent_key not in data[key] or "buckets" not in data[key][parent_key]:
            continue
        buckets = data[key][parent_key]["buckets"]
        for b in buckets:
            rows.append({
                "date": pd.to_datetime(b["key_as_string"]),
                "status": label,
                "count": b["doc_count"]
            })

    df = pd.DataFrame(rows)
    return df

# Fetch data
exchange_df = fetch_exchange_data(
    token=access_token,
    exchange_type=selected_exchange_type,
    programmes=selected_programmes,
    start_date=start_date,
    end_date=end_date,
    office_id=office_id
)

if exchange_df.empty:
    st.warning("No data returned from the API for the selected filters.")
    st.stop()

# -----------------------------------------------------------------------------
# Status filter
st.subheader("Filter Statuses")
statuses = exchange_df["status"].unique()
selected_statuses = st.multiselect(
    "Select statuses to display",
    options=statuses,
    default=list(statuses)
)
filtered_df = exchange_df[exchange_df["status"].isin(selected_statuses)]

# Remove Sign Up from chart
filtered_df = filtered_df[filtered_df["status"] != "Sign Up"]

# -----------------------------------------------------------------------------
# Time-series chart (Plotly)
st.header("Exchange Trends Over Time")
fig = px.line(
    filtered_df,
    x="date",
    y="count",
    color="status",
    line_shape=line_shape,
    markers=True,
    title="Exchange Progress Over Time",
    labels={"count": "Number of People/Applications", "date": "Date", "status": "Status"}
)
fig.update_traces(line=dict(width=3))  # thicker lines
fig.update_layout(template="plotly_white", legend_title_text="Status")
st.plotly_chart(fig, use_container_width=True)

# -----------------------------------------------------------------------------
# Funnel conversion with numbers + %
st.header("Funnel Conversion Rates")
pivot_df = filtered_df.pivot(index="date", columns="status", values="count").fillna(0)
funnel_steps = ["Applied", "Accepted", "Approved", "Realized", "Finished", "Completed"]

funnel_data = []
for i in range(len(funnel_steps)-1):
    step_from = funnel_steps[i]
    step_to = funnel_steps[i+1]
    from_sum = pivot_df.get(step_from, pd.Series([0])).sum()
    to_sum = pivot_df.get(step_to, pd.Series([0])).sum()
    rate = to_sum / from_sum if from_sum > 0 else 0
    funnel_data.append({
        "Step": f"{step_from} → {step_to}",
        "From Count": int(from_sum),
        "To Count": int(to_sum),
        "Conversion %": f"{rate*100:.1f}%"
    })

funnel_df = pd.DataFrame(funnel_data)
st.table(funnel_df)

# -----------------------------------------------------------------------------
# Key metrics
st.header("Key Metrics")
cols = st.columns(4)
with cols[0]:
    st.metric("Total Applied", int(pivot_df.get("Applied", pd.Series([0])).sum()))
with cols[1]:
    st.metric("Total Approved", int(pivot_df.get("Approved", pd.Series([0])).sum()))
with cols[2]:
    st.metric("Total Realized", int(pivot_df.get("Realized", pd.Series([0])).sum()))
with cols[3]:
    total_applied = pivot_df.get("Applied", pd.Series([0])).sum()
    total_realized = pivot_df.get("Realized", pd.Series([0])).sum()
    realization_rate = total_realized / total_applied if total_applied > 0 else 0
    st.metric("Realization Rate", f"{realization_rate*100:.1f}%")
