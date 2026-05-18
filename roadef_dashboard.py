import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
from roadef_tools.xml_io import load_instance, load_solution
from roadef_tools.inventory import tank_events
from roadef_tools.model import Solution, Instance

st.set_page_config(
    page_title="Antigravity Dispatcher Dashboard",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for Premium Look
st.markdown("""
    <style>
    .main {
        background-color: #f0f2f6;
    }
    .stMetric {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #d1d5db;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    h1, h2, h3, .stSubheader, .stText, p, span, label {
        color: #1f2937 !important;
    }
    [data-testid="stMetricLabel"] {
        color: #4b5563 !important;
        font-weight: 600 !important;
    }
    [data-testid="stMetricValue"] {
        color: #0f766e !important; /* Deep teal for values */
    }
    .stDataFrame, .stTable {
        background-color: #ffffff !important;
    }
    </style>
""", unsafe_allow_html=True)


# Sidebar - Instance & Solution Selection
with st.sidebar:
    st.header("Plan Configuration")
    instance_path = st.text_input(
        "Instance XML", 
        "roadef_2016_data/set_B/Instances_B_V25-11042016/V2.18.xml"
    )
    solution_path = st.text_input(
        "Robust Solution XML", 
        "roadef_2016_data/hust_smart_results/2.18_robust_rolling_35d_v2.xml"
    )
    
    st.divider()
    st.info("Locked Window: Next 7 Days")
    include_call_ins = st.checkbox("Include Call-in Customers", value=True)
    st.markdown("""
        **Reliability Settings**
        - Confidence Interval: 90%
        - Buffer Ratio: 8.0%
        - Min Quantity Clip: Active
    """)

import polars as pl

@st.cache_data
def load_data(inst_path, sol_path):
    instance = load_instance(inst_path)
    solution = load_solution(sol_path)
    return instance, solution

@st.cache_data
def build_inventory_dataframe(_instance, _solution):
    # Use polars for high-speed dataframe construction from simulation events
    events = tank_events(_instance, _solution)
    
    # Efficiently extract point-to-index mapping
    point_to_idx = {c.index: c.index for c in _instance.customers}
    point_to_safety = {c.index: c.safety_level for c in _instance.customers}
    point_to_capacity = {c.index: c.capacity for c in _instance.customers}
    
    df = pl.DataFrame([
        {
            "Point": e.point,
            "Day": e.step * _instance.unit / 1440,
            "Inventory": max(0.0, e.ending_inventory),
            "Delivery": e.delivered if e.delivered > 0 else 0
        }
        for e in events if e.point in point_to_idx
    ])
    
    # Join with metadata (lazy-ish approach)
    df = df.with_columns([
        pl.col("Point").replace(point_to_safety).alias("Safety"),
        pl.col("Point").replace(point_to_capacity).alias("Capacity")
    ])
    
    return df

try:
    instance, solution = load_data(instance_path, solution_path)
    df_events = build_inventory_dataframe(instance, solution)
except Exception as e:
    st.error(f"Error loading data: {e}")
    st.stop()

# --- Locked Window Filter ---
LOCK_HORIZON_MINUTES = 7 * 1440
locked_shifts = [s for s in solution.shifts if s.start < LOCK_HORIZON_MINUTES]

# --- Dashboard Header ---
st.title("🚛 Dispatcher Command Center")
st.subheader("7-Day Operational Game Plan")

# --- KPI Section ---
col1, col2, col3, col4 = st.columns(4)

total_deliveries = sum(
    1 for s in locked_shifts for op in s.operations if op.quantity > 0
)
total_volume = sum(
    op.quantity for s in locked_shifts for op in s.operations if op.quantity > 0
)
unique_drivers = len(set(s.driver for s in locked_shifts))
unique_trailers = len(set(s.trailer for s in locked_shifts))

with col1:
    st.metric("Locked Shifts", len(locked_shifts))
with col2:
    st.metric("Total Deliveries", total_deliveries)
with col3:
    st.metric("Total Volume (kg)", f"{total_volume:,.0f}")
with col4:
    st.metric("Active Fleet", f"{unique_drivers}D / {unique_trailers}T")

# --- Main Dashboard Sections ---
tab1, tab2, tab3 = st.tabs(["📋 Shift Schedule", "📈 Inventory Forecast", "🚛 Fleet Utilization"])

with tab1:
    st.header("Next 7 Days - Driver Briefing")
    
    shift_data = []
    for s in locked_shifts:
        day = s.start // 1440
        start_str = f"Day {day} { (s.start % 1440)//60 :02d}:{(s.start % 60):02d}"
        
        # Calculate end time from last operation
        last_op = s.operations[-1]
        
        # Get setup time from customer or source
        p_idx = last_op.point
        setup = 0
        if p_idx in [c.index for c in instance.customers]:
            setup = next(c.setup_time for c in instance.customers if c.index == p_idx)
        elif p_idx in [src.index for src in instance.sources]:
            setup = next(src.setup_time for src in instance.sources if src.index == p_idx)
        
        end_time = last_op.arrival + setup
        duration_hrs = (end_time - s.start) / 60
        end_str = f"Day {end_time // 1440} { (end_time % 1440)//60 :02d}:{(end_time % 60):02d}"
        
        # Intelligent Route String: Group reloads and format customers
        route_parts = ["Depart Base" if instance.base_index == 0 else f"Start@{instance.base_index}"]
        last_p = instance.base_index
        for op in s.operations:
            p_idx = op.point
            is_source = p_idx in [src.index for src in instance.sources] or p_idx == instance.base_index
            
            if p_idx == last_p:
                continue # Skip consecutive repeats in display
            
            label = str(p_idx)
            if is_source:
                label = f"Refill@{p_idx}" if p_idx != instance.base_index else "Return Base"
            
            route_parts.append(label)
            last_p = p_idx
        
        # Explicitly show Return Base if not the last action
        if last_p != instance.base_index:
            route_parts.append("Return Base")
            
        shift_data.append({
            "Shift ID": s.index,
            "Start": start_str,
            "End": end_str,
            "Duration": f"{duration_hrs:.1f}h",
            "Driver": instance.drivers[s.driver].index,
            "Trailer": instance.trailers[s.trailer].index,
            "Intelligent Route": " ➔ ".join(route_parts),
            "Total Vol": f"{sum(op.quantity for op in s.operations if op.quantity > 0):,.0f}"
        })
    
    df_shifts = pd.DataFrame(shift_data)
    st.dataframe(df_shifts, use_container_width=True, hide_index=True)
    
    st.divider()
    with st.expander("🔍 Trailer Compatibility Reference"):
        compat_data = []
        for t in instance.trailers:
            allowed_custs = [
                c.index for c in instance.customers 
                if t.index in c.allowed_trailers
            ]
            cust_list = "ALL CUSTOMERS" if len(allowed_custs) == len(instance.customers) else ", ".join(map(str, allowed_custs))
            compat_data.append({
                "Trailer ID": t.index,
                "Capacity": f"{t.capacity:,.0f} kg",
                "Allowed Customers Count": len(allowed_custs),
                "Compatible Customer List": cust_list
            })
        st.dataframe(
            pd.DataFrame(compat_data),
            column_config={
                "Capacity": st.column_config.TextColumn("Capacity", width="large"),
                "Compatible Customer List": st.column_config.TextColumn("Compatible Customer List", width="max")
            },
            use_container_width=True,
            hide_index=True
        )

with tab2:
    st.header("Inventory Visibility")
    
    selected_customer = st.selectbox(
        "Select Customer to Inspect", 
        sorted(df_events["Point"].unique())
    )
    
    # Filter using Polars (very fast)
    cust_df_pl = df_events.filter(pl.col("Point") == selected_customer)
    cust_df = cust_df_pl.to_pandas() # Plotly needs pandas
    
    fig = go.Figure()
    
    # Inventory Line
    fig.add_trace(go.Scatter(
        x=cust_df["Day"], y=cust_df["Inventory"],
        mode='lines', name='Projected Inventory',
        line=dict(color='#00ffcc', width=3)
    ))
    
    # Safety Level
    fig.add_trace(go.Scatter(
        x=cust_df["Day"], y=cust_df["Safety"],
        mode='lines', name='Safety Level',
        line=dict(color='#ff4b4b', dash='dash')
    ))
    
    # Tank Capacity
    fig.add_trace(go.Scatter(
        x=cust_df["Day"], y=cust_df["Capacity"],
        mode='lines', name='Tank Capacity',
        line=dict(color='#ffffff', dash='dot', width=1),
        opacity=0.3
    ))
    
    # Deliveries (Bars)
    deliveries = cust_df[cust_df["Delivery"] > 0]
    if not deliveries.empty:
        fig.add_trace(go.Bar(
            x=deliveries["Day"], y=deliveries["Delivery"],
            name='Deliveries', marker_color='#ffd700',
            opacity=0.5, yaxis='y2'
        ))

    fig.update_layout(
        title=f"Customer {selected_customer} - 35 Day Robust Forecast",
        xaxis_title="Days",
        yaxis_title="Inventory (kg)",
        yaxis2=dict(
            title="Delivery Quantity",
            overlaying='y',
            side='right',
            showgrid=False
        ),
        template="plotly_white",
        shapes=[
            # Highlight the locked window
            dict(
                type="rect",
                xref="x", yref="paper",
                x0=0, x1=7, y0=0, y1=1,
                fillcolor="rgba(0, 255, 204, 0.1)",
                layer="below", line_width=0,
            )
        ]
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Show status alerts
    min_inv = cust_df[cust_df["Day"] <= 7]["Inventory"].min()
    safety = cust_df["Safety"].iloc[0]
    
    if min_inv <= 1e-6:
        st.error(f"🚨 STOCK-OUT IMMINENT: Customer {selected_customer} will run completely dry in the next 7 days!")
    elif min_inv < safety:
        st.warning(f"⚠️ Safety Breach: Customer {selected_customer} is projected to drop below safety levels in the next 7 days.")
    else:
        st.success(f"✅ Secure: Customer {selected_customer} remains above safety levels throughout the locked window.")

with tab3:
    st.header("Fleet Availability & Coverage")
    
    # Heatmap of shifts per day per driver
    driver_days = []
    for s in locked_shifts:
        driver_days.append({
            "Driver": f"D{instance.drivers[s.driver].index}",
            "Day": int(s.start // 1440),
            "Shifts": 1
        })
    
    if driver_days:
        df_fleet = pd.DataFrame(driver_days).groupby(["Driver", "Day"]).sum().reset_index()
        
        # Calculate Hours per day per driver
        driver_hours = []
        for s in locked_shifts:
            last_op = s.operations[-1]
            p_idx = last_op.point
            setup = 0
            if p_idx in [c.index for c in instance.customers]:
                setup = next(c.setup_time for c in instance.customers if c.index == p_idx)
            elif p_idx in [src.index for src in instance.sources]:
                setup = next(src.setup_time for src in instance.sources if src.index == p_idx)
            
            duration_hrs = (last_op.arrival + setup - s.start) / 60
            driver_hours.append({
                "Driver": f"D{instance.drivers[s.driver].index}",
                "Day": int(s.start // 1440),
                "Hours": duration_hrs
            })
        df_hours = pd.DataFrame(driver_hours).groupby(["Driver", "Day"]).sum().reset_index()

        col_a, col_b = st.columns(2)
        with col_a:
            fig_fleet = px.density_heatmap(
                df_fleet, x="Day", y="Driver", z="Shifts",
                color_continuous_scale="RdYlGn_r",
                title="Shift Count Heatmap"
            )
            fig_fleet.update_layout(template="plotly_white")
            st.plotly_chart(fig_fleet, use_container_width=True)
            
        with col_b:
            fig_hours = px.density_heatmap(
                df_hours, x="Day", y="Driver", z="Hours",
                color_continuous_scale="Viridis",
                title="Workload Heatmap (Hours per Day)"
            )
            fig_hours.update_layout(template="plotly_white")
            st.plotly_chart(fig_hours, use_container_width=True)
        
        # --- Driver Activity Pulse (0/1 Time Series) ---
        st.divider()
        st.subheader("Driver Activity Pulse (Next 7 Days)")
        
        # Create a minute-by-minute occupancy grid for the first 4 drivers
        horizon_mins = 7 * 1440
        drivers_to_plot = sorted(list(set(s.driver for s in locked_shifts)))[:4]
        
        pulse_data = []
        for d_idx in drivers_to_plot:
            occupancy = [0] * (horizon_mins + 1)
            for s in locked_shifts:
                if s.driver != d_idx:
                    continue
                
                last_op = s.operations[-1]
                p_idx = last_op.point
                setup = 0
                if p_idx in [c.index for c in instance.customers]:
                    setup = next(c.setup_time for c in instance.customers if c.index == p_idx)
                elif p_idx in [src.index for src in instance.sources]:
                    setup = next(src.setup_time for src in instance.sources if src.index == p_idx)
                
                end_time = last_op.arrival + setup
                for t in range(int(s.start), min(int(end_time), horizon_mins)):
                    occupancy[t] = 1
            
            for t in range(0, horizon_mins, 30): # Downsample to 30min for performance
                pulse_data.append({
                    "Driver": f"D{instance.drivers[d_idx].index}",
                    "Day": t / 1440,
                    "Active": occupancy[t]
                })
        
        if pulse_data:
            df_pulse = pd.DataFrame(pulse_data)
            fig_pulse = px.line(
                df_pulse, x="Day", y="Active", facet_row="Driver",
                line_shape="hv", # Stepped line
                color="Driver",
                height=600,
                title="Driver Duty Cycle (1=Active, 0=Resting)"
            )
            fig_pulse.update_layout(template="plotly_white", showlegend=False)
            fig_pulse.update_yaxes(tickvals=[0, 1], title="")
            st.plotly_chart(fig_pulse, use_container_width=True)
            
        # --- Daily Throughput & Consumption Chart ---
        st.divider()
        st.subheader("Daily Throughput vs. Demand")
        
        # Calculate Deliveries
        daily_volume = []
        for s in solution.shifts:
            day = s.start // 1440
            vol = 0
            for op in s.operations:
                if op.quantity <= 0:
                    continue
                cust = instance.customer_by_point.get(op.point)
                if not include_call_ins and cust and cust.call_in:
                    continue
                vol += op.quantity
            daily_volume.append({"Day": day, "Volume": vol})
        
        df_vol = pd.DataFrame(daily_volume).groupby("Day").sum().reset_index()
        
        # Calculate Consumption
        daily_cons = []
        steps_per_day = 1440 // instance.unit
        for day in range(35):
            total_c = 0
            for customer in instance.customers:
                if not include_call_ins and customer.call_in:
                    continue
                start = day * steps_per_day
                end = min(start + steps_per_day, len(customer.forecast))
                total_c += sum(customer.forecast[start:end])
            daily_cons.append({"Day": day, "Consumption": total_c})
        
        df_cons = pd.DataFrame(daily_cons)
        
        # Merge and Plot
        df_merged = pd.merge(df_vol, df_cons, on="Day", how="outer").fillna(0)
        
        fig_vol = go.Figure()
        
        # Deliveries Bar
        fig_vol.add_trace(go.Bar(
            x=df_merged["Day"], y=df_merged["Volume"],
            name='Total Delivered', marker_color='#ffd700'
        ))
        
        # Consumption Line
        fig_vol.add_trace(go.Scatter(
            x=df_merged["Day"], y=df_merged["Consumption"],
            name='Total Consumption', line=dict(color='#00ffcc', width=3),
            mode='lines+markers'
        ))
        
        fig_vol.update_layout(
            title="Fleet Throughput vs. Aggregate Demand",
            xaxis_title="Operational Day",
            yaxis_title="Quantity (kg)",
            template="plotly_white",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_vol, use_container_width=True)
        
    else:
        st.write("No shifts scheduled in the locked window.")

st.divider()
st.caption("Generated by Antigravity Robust Rolling Optimizer. Sunday Night Planning Session.")
