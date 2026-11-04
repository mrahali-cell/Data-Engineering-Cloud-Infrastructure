"""MédiRelais · team dashboard: all hospitals. Tab Business + tab Pipeline.

Owned by MEDIRELAIS_READER (03_schedule.sql): every hospital, no purchase prices, GOLD only.
The pipeline tab reads GOLD tables built for it (gold_pipeline_loads, gold_quality_history,
gold_data_quality), so the dashboard never needs BRONZE or SILVER rights.
"""
import altair as alt
import pandas as pd
import streamlit as st
from snowflake.snowpark.context import get_active_session

session = get_active_session()
GOLD = "MEDIRELAIS.GOLD"
TARGET = 0.40          # README: share of the value at risk MédiRelais aims to save
MAX_REJECT = 0.15      # quality gate threshold (airflow/tasks/quality_gate.py)


# Gold changes once a day (06:00), so each query result is reused for an hour instead of
# waking the warehouse at every page view
@st.cache_data(ttl=3600)
def q(sql):
    df = session.sql(sql).to_pandas()
    df.columns = [c.upper() for c in df.columns]
    return df


def bullet(value, target, title, fmt):
    """Bar = value, orange tick = target (orange reads on light and dark backgrounds)."""
    df = pd.DataFrame({"what": [title], "value": [value], "target": [target]})
    bar = alt.Chart(df).mark_bar(size=22, color="#2e7d32").encode(
        x=alt.X("value:Q", title=None, axis=alt.Axis(format=fmt),
                scale=alt.Scale(domain=[0, max(value, target) * 1.15 or 1])),
        y=alt.Y("what:N", title=None))
    tick = alt.Chart(df).mark_tick(color="#e65100", thickness=3, size=34).encode(x="target:Q", y="what:N")
    return (bar + tick).properties(height=70)


st.set_page_config(page_title="MédiRelais · Team", layout="wide")
latest = q(f"SELECT MAX(snapshot_date) AS D FROM {GOLD}.GOLD_VALUE_AT_RISK").D[0]
LATEST = f"snapshot_date = '{latest}'"

st.title("💊 MédiRelais · network")
st.caption(f"12 hospitals · data as of {latest}")
business, pipeline = st.tabs(["Business", "Pipeline"])

# =============================== BUSINESS ===============================
with business:
    k = q(f"""
        SELECT (SELECT SUM(value_at_risk_eur) FROM {GOLD}.GOLD_VALUE_AT_RISK WHERE {LATEST})::FLOAT AS AT_RISK_EUR,
               (SELECT SUM(qty_on_hand)       FROM {GOLD}.GOLD_VALUE_AT_RISK WHERE {LATEST})::FLOAT AS AT_RISK_UNITS,
               (SELECT COALESCE(SUM(saveable_value_eur), 0) FROM {GOLD}.GOLD_TRANSFER_SUGGESTIONS WHERE {LATEST})::FLOAT AS SAVE_EUR,
               (SELECT COALESCE(SUM(usable_qty_before_expiry), 0) FROM {GOLD}.GOLD_TRANSFER_SUGGESTIONS WHERE {LATEST})::FLOAT AS SAVE_UNITS
    """).iloc[0]
    rate = k.SAVE_EUR / k.AT_RISK_EUR if k.AT_RISK_EUR else 0.0

    c1, c2, c3 = st.columns(3)
    c1.metric("Value expiring in 90 days", f"€{k.AT_RISK_EUR:,.0f}")
    c2.metric("Saveable by transfers", f"€{k.SAVE_EUR:,.0f}")
    c3.metric("Recovery rate", f"{rate:.0%}", f"{rate - TARGET:+.0%} vs 40 % target")

    st.subheader("Target vs saveable")
    st.caption("Bar = saveable by the suggested transfers · orange tick = target (40 % of what is at risk). "
               "Actually saved needs a register of real transfers (out of scope, README).")
    b1, b2 = st.columns(2)
    b1.altair_chart(bullet(k.SAVE_EUR, TARGET * k.AT_RISK_EUR, "€", ",.0f"), use_container_width=True)
    b1.caption(f"€{k.SAVE_EUR:,.0f} saveable · target €{TARGET * k.AT_RISK_EUR:,.0f}")
    b2.altair_chart(bullet(k.SAVE_UNITS, TARGET * k.AT_RISK_UNITS, "Units", ",.0f"), use_container_width=True)
    b2.caption(f"{k.SAVE_UNITS:,.0f} units saveable · target {TARGET * k.AT_RISK_UNITS:,.0f}")

    left, right = st.columns(2)
    with left:
        st.subheader("Hospitals ranked by € at risk")
        h = q(f"""SELECT hospital_name AS HOSPITAL, SUM(value_at_risk_eur)::FLOAT AS EUR
                  FROM {GOLD}.GOLD_VALUE_AT_RISK WHERE {LATEST} GROUP BY 1""")
        st.altair_chart(alt.Chart(h).mark_bar(color="#c62828").encode(
            x=alt.X("EUR:Q", title="€ at risk"), y=alt.Y("HOSPITAL:N", sort="-x", title=None),
            tooltip=["HOSPITAL", alt.Tooltip("EUR:Q", format=",.0f")]), use_container_width=True)
    with right:
        st.subheader("Transfer flows (€ saveable)")
        f = q(f"""SELECT from_hospital_id AS FROM_H, to_hospital_id AS TO_H, SUM(saveable_value_eur)::FLOAT AS EUR
                  FROM {GOLD}.GOLD_TRANSFER_SUGGESTIONS WHERE {LATEST} GROUP BY 1, 2""")
        if f.empty:
            st.write("No transfer suggested today.")
        else:
            st.altair_chart(alt.Chart(f).mark_rect().encode(
                x=alt.X("TO_H:N", title="To"), y=alt.Y("FROM_H:N", title="From"),
                color=alt.Color("EUR:Q", title="€", scale=alt.Scale(scheme="greens")),
                tooltip=["FROM_H", "TO_H", alt.Tooltip("EUR:Q", format=",.0f")]), use_container_width=True)

    left, right = st.columns([2, 3])          # narrower charts, wider table on the right
    with left:
        st.subheader("Trend by snapshot day")
        t = q(f"""
            SELECT v.snapshot_date AS DAY, SUM(v.value_at_risk_eur)::FLOAT AS AT_RISK,
                   COALESCE(MAX(s.saveable), 0)::FLOAT AS SAVEABLE
            FROM {GOLD}.GOLD_VALUE_AT_RISK v
            LEFT JOIN (SELECT snapshot_date, SUM(saveable_value_eur) AS saveable
                       FROM {GOLD}.GOLD_TRANSFER_SUGGESTIONS GROUP BY 1) s USING (snapshot_date)
            GROUP BY 1 ORDER BY 1""")
        t["RECOVERY"] = t.SAVEABLE / t.AT_RISK
        t["DAY_LABEL"] = pd.to_datetime(t.DAY).dt.strftime("%d %b")
        # Stacked bar: the whole bar = value at risk, split into the part transfers can save and the rest
        t["NOT_SAVEABLE"] = (t.AT_RISK - t.SAVEABLE).clip(lower=0)
        long = t.melt(["DAY_LABEL"], ["SAVEABLE", "NOT_SAVEABLE"], var_name="WHAT", value_name="EUR")
        long["WHAT"] = long.WHAT.map({"SAVEABLE": "Saveable", "NOT_SAVEABLE": "Not saveable"})
        st.altair_chart(alt.Chart(long).mark_bar().encode(
            x=alt.X("DAY_LABEL:O", title=None, sort=list(t.DAY_LABEL)),
            y=alt.Y("EUR:Q", title="€ at risk", stack="zero"),
            color=alt.Color("WHAT:N", title=None, sort=["Saveable", "Not saveable"],
                            scale=alt.Scale(domain=["Saveable", "Not saveable"], range=["#2e7d32", "#9e9e9e"]),
                            legend=alt.Legend(orient="bottom")),
            order=alt.Order("WHAT:N", sort="descending"),
            tooltip=["DAY_LABEL", "WHAT", alt.Tooltip("EUR:Q", format=",.0f")]),
            use_container_width=True)
        st.caption("Recovery rate by day · dashed line = 40 % target")
        bars = alt.Chart(t).mark_bar(color="#2e7d32").encode(
            x=alt.X("DAY_LABEL:O", title=None, sort=list(t.DAY_LABEL)),
            y=alt.Y("RECOVERY:Q", title="Recovery", axis=alt.Axis(format="%")),
            tooltip=["DAY_LABEL", alt.Tooltip("RECOVERY:Q", format=".0%")])
        goal = alt.Chart(pd.DataFrame({"y": [TARGET]})).mark_rule(strokeDash=[6, 4], color="#e65100").encode(y="y:Q")
        st.altair_chart((bars + goal).properties(height=160), use_container_width=True)
    with right:
        st.subheader("Over-stock € by hospital")
        o = q(f"""SELECT hospital_name AS HOSPITAL, SUM(overstock_value_eur)::FLOAT AS EUR
                  FROM {GOLD}.GOLD_DAYS_OF_COVER WHERE {LATEST} GROUP BY 1 HAVING SUM(overstock_value_eur) > 0""")
        st.altair_chart(alt.Chart(o).mark_bar(color="#f9a825").encode(
            x=alt.X("EUR:Q", title="€ that will expire unused"), y=alt.Y("HOSPITAL:N", sort="-x", title=None),
            tooltip=["HOSPITAL", alt.Tooltip("EUR:Q", format=",.0f")]), use_container_width=True)
        st.subheader("Shortage medicines at risk")
        st.dataframe(q(f"""
            SELECT hospital_name AS HOSPITAL, product_name AS PRODUCT, qty_on_hand AS QTY,
                   days_to_expiry AS DAYS_LEFT, value_at_risk_eur::FLOAT AS EUR
            FROM {GOLD}.GOLD_VALUE_AT_RISK WHERE is_national_shortage AND {LATEST}
            ORDER BY DAYS_LEFT"""), use_container_width=True)

# =============================== PIPELINE ===============================
with pipeline:
    loads = q(f"SELECT * FROM {GOLD}.GOLD_PIPELINE_LOADS")
    hist = q(f"SELECT * FROM {GOLD}.GOLD_QUALITY_HISTORY")
    dq = q(f"SELECT * FROM {GOLD}.GOLD_DATA_QUALITY")

    if loads.empty:
        st.warning("No ingestion run logged yet.")
        st.stop()
    days = sorted(loads.RUN_DATE.unique())
    start, end = st.select_slider("Run dates", options=days, value=(days[0], days[-1]))
    sel = loads[(loads.RUN_DATE >= start) & (loads.RUN_DATE <= end)]

    # Header cards
    last = loads.sort_values("RUN_AT").groupby("JOB").tail(1)
    hours = (pd.Timestamp.now(tz="UTC") - pd.to_datetime(last.RUN_AT, utc=True)).dt.total_seconds() / 3600
    fresh = int((hours < 26).sum())
    ok_last = (last.STATUS == "SUCCESS").all()
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Last load per source", "All OK" if ok_last else "Failure", delta=None)
    p2.metric("Sources fresh (< 26 h)", f"{fresh}/{len(last)}")
    if not dq.empty:
        p3.metric("Reject rate, latest night", f"{float(dq.REJECT_RATE[0]):.1%}",
                  "gate blocked gold" if dq.GOLD_BLOCKED[0] else "gate passed",
                  delta_color="inverse" if dq.GOLD_BLOCKED[0] else "normal")
    p4.metric("Rows lost (read ≠ loaded)", int((~sel.NOTHING_LOST.astype(bool)).sum()))

    left, right = st.columns(2)
    with left:
        st.subheader("Ingestion per source and day")
        daily = sel.groupby(["RUN_DATE", "JOB"]).agg(
            RUNS=("STATUS", "size"), FAILED=("STATUS", lambda s: int((s != "SUCCESS").sum())),
            ROWS_IN=("ROWS_IN", "sum"), ROWS_LOADED=("ROWS_LOADED", "sum")).reset_index()
        daily["NOTHING_LOST"] = daily.ROWS_IN == daily.ROWS_LOADED
        st.dataframe(daily.sort_values(["RUN_DATE", "JOB"], ascending=[False, True]),
                     use_container_width=True)
        st.subheader("Hours since last load")
        fr = last[["JOB", "STATUS"]].assign(HOURS=hours.round(1).values)
        st.dataframe(fr.style.apply(lambda r: [
            # black text: the cell colours are light, so the default text is unreadable in dark mode
            "background-color: #e5f4e4; color: black" if r.HOURS < 26 else
            "background-color: #f9eeda; color: black" if r.HOURS < 50 else
            "background-color: #fbebeb; color: black"] * len(r), axis=1),
            use_container_width=True)
    with right:
        st.subheader("Reject rate by night (consumption)")
        night = hist.groupby("DELIVERY_DATE").apply(
            lambda g: pd.Series({"RATE": g.loc[g.IS_REJECTED, "ROWS_RECEIVED"].sum() / g.ROWS_RECEIVED.sum()})
        ).reset_index()
        night["GATE"] = (night.RATE > MAX_REJECT).map({True: "Blocked", False: "Passed"})
        line = alt.Chart(night).mark_line(point=True).encode(
            x=alt.X("DELIVERY_DATE:T", title=None), y=alt.Y("RATE:Q", title="Rejected", axis=alt.Axis(format="%")),
            tooltip=["DELIVERY_DATE", alt.Tooltip("RATE:Q", format=".1%"), "GATE"])
        rule = alt.Chart(pd.DataFrame({"y": [MAX_REJECT]})).mark_rule(strokeDash=[6, 4], color="#c62828").encode(y="y:Q")
        st.altair_chart(line + rule, use_container_width=True)
        st.caption("Dashed line: the 15 % quality gate")
        st.subheader("Gate result per night")
        st.altair_chart(alt.Chart(night).mark_square(size=400).encode(
            x=alt.X("DELIVERY_DATE:T", title=None),
            color=alt.Color("GATE:N", title=None, scale=alt.Scale(domain=["Passed", "Blocked"],
                                                                  range=["#2e7d32", "#c62828"])),
            tooltip=["DELIVERY_DATE", "GATE"]).properties(height=60), use_container_width=True)
        st.subheader("Rejects by reason")
        rej = hist[hist.ROW_STATUS != "clean"]
        st.altair_chart(alt.Chart(rej).mark_bar().encode(
            x=alt.X("DELIVERY_DATE:T", title=None), y=alt.Y("sum(ROWS_RECEIVED):Q", title="Rows"),
            color=alt.Color("ROW_STATUS:N", title="Reason"),
            tooltip=["DELIVERY_DATE", "ROW_STATUS", "sum(ROWS_RECEIVED)"]), use_container_width=True)

    st.caption("Not shown yet: dbt test results per run and credits per day (need a test-results table "
               "and a role with access to SNOWFLAKE.ACCOUNT_USAGE; see snowflake/05_costs.sql).")
