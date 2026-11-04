"""MédiRelais · team dashboard: all hospitals. Tab Business + tab Pipeline.

Owned by MEDIRELAIS_READER (03_schedule.sql): every hospital, no purchase prices, GOLD only.
The pipeline tab reads GOLD tables built for it (gold_pipeline_loads, gold_quality_history,
gold_data_quality), so the dashboard never needs BRONZE or SILVER rights.
"""
import re

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


# One colour per meaning, the same on every chart (and the same as the hospital dashboard)
GREEN, LIGHT_GREEN, GREY = "#2e7d32", "#a5d6a7", "#9e9e9e"
RED, AMBER, ORANGE, BLUE = "#c62828", "#f9a825", "#e65100", "#1565c0"
TEXT = "#8a8f98"           # value labels: readable on light and dark themes
REASON_COLOURS = {"Transferable": GREEN, "Under 30 days": RED, "Under €200": AMBER, "Cold chain": BLUE}
REASONS = {"transferable": "Transferable", "under_30_days": "Under 30 days",
           "under_200_eur": "Under €200", "no_cold_chain_proof": "Cold chain"}
SOURCES = {"s1_stock_postgres": "S1 · Stock", "s2_consumption_files": "S2 · Consumption",
           "s3_bdpm_reference": "S3 · Drug database", "s4_shortages": "S4 · Shortages"}


def short(hid, name):
    """'H07', 'Centre Hospitalier de l'Est' -> 'H07 · CH Est' (full names do not fit on a chart axis)."""
    n = str(name)
    for long_, abbr in (("Centre Hospitalier ", "CH "), ("Hôpital ", "")):
        if n.startswith(long_):
            n = abbr + n[len(long_):]
    n = re.sub(r"^(CH )?(de l'|de la |des |du |de )", r"\1", n)
    return f"{hid} · {n[:1].upper() + n[1:]}"


def urgency(days):
    """Table cell colour by days left (black text: the light fills are unreadable with white text)."""
    if days < 30:
        return "background-color: #fbebeb; color: black"
    if days < 60:
        return "background-color: #f9eeda; color: black"
    return ""


def card(title, status, detail, bg, fg):
    return (f"<div style='background:{bg};border-radius:10px;padding:12px 14px;color:#1f2933'>"
            f"<div style='font-size:0.85rem;opacity:0.8'>{title}</div>"
            f"<div style='font-size:1.25rem;font-weight:700;color:{fg}'>{status}</div>"
            f"<div style='font-size:0.85rem'>{detail}</div></div>")


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
    st.markdown("---")

    # ---- 1. Where the € at risk goes: one bar, three parts ----
    st.subheader("Of the € at risk, how much can transfers save?")
    target_eur = TARGET * k.AT_RISK_EUR
    saved = min(k.SAVE_EUR, k.AT_RISK_EUR)
    gap = max(target_eur - saved, 0.0)
    parts = pd.DataFrame({
        "PART": ["Saveable by transfers", "Gap to the 40 % target", "Rest at risk"],
        "EUR": [saved, gap, max(k.AT_RISK_EUR - saved - gap, 0.0)]})
    parts["END"] = parts.EUR.cumsum()
    parts["START"] = parts.END - parts.EUR
    parts["MID"] = (parts.START + parts.END) / 2
    parts["LABEL"] = parts.EUR.map(lambda v: f"€{v:,.0f}")
    parts["ROW"] = "€ at risk"
    seg = alt.Chart(parts).mark_bar(size=46).encode(
        x=alt.X("START:Q", title=None, axis=None, scale=alt.Scale(domain=[0, max(k.AT_RISK_EUR, 1.0)])),
        x2="END:Q", y=alt.Y("ROW:N", title=None, axis=None),
        color=alt.Color("PART:N", title=None, sort=list(parts.PART),
                        scale=alt.Scale(domain=list(parts.PART), range=[GREEN, LIGHT_GREEN, GREY]),
                        legend=alt.Legend(orient="bottom")),
        tooltip=["PART", alt.Tooltip("EUR:Q", format=",.0f", title="€")])
    seg_txt = alt.Chart(parts[parts.EUR > 0.08 * k.AT_RISK_EUR]).mark_text(fontWeight="bold").encode(
        x="MID:Q", y="ROW:N", text="LABEL:N",
        color=alt.condition(alt.datum.PART == "Gap to the 40 % target", alt.value("#1b5e20"), alt.value("white")))
    st.altair_chart((seg + seg_txt).properties(height=110), use_container_width=True)
    st.caption(f"Total at risk €{k.AT_RISK_EUR:,.0f} · target = 40 % of it (€{target_eur:,.0f}). "
               "Saveable = what the receiving hospital can use before expiry. "
               "Actually saved needs a register of real transfers (out of scope, README).")

    st.markdown("---")
    left, right = st.columns(2)

    # ---- 2. Hospitals: € at risk, split by what can be done ----
    with left:
        st.subheader("Hospitals by € at risk")
        st.caption("Why the stock at risk can or cannot move")
        h = q(f"""SELECT hospital_id AS ID, hospital_name AS NAME,
                         COALESCE(transfer_block_reason, 'transferable') AS REASON,
                         SUM(value_at_risk_eur)::FLOAT AS EUR
                  FROM {GOLD}.GOLD_VALUE_AT_RISK WHERE {LATEST} GROUP BY 1, 2, 3""")
        if h.empty:
            st.write("Nothing at risk today.")
        else:
            h["HOSPITAL"] = [short(i, n) for i, n in zip(h.ID, h.NAME)]
            h["STATUS"] = h.REASON.map(REASONS).fillna("Other")
            tot = h.groupby("HOSPITAL", as_index=False).EUR.sum().sort_values("EUR", ascending=False)
            tot["LABEL"] = tot.EUR.map(lambda v: f" €{v:,.0f}")
            order = list(tot.HOSPITAL)
            bars = alt.Chart(h).mark_bar().encode(
                x=alt.X("sum(EUR):Q", title="€ at risk", axis=alt.Axis(format=",.0f"),
                        scale=alt.Scale(domain=[0, float(tot.EUR.max()) * 1.18])),
                y=alt.Y("HOSPITAL:N", sort=order, title=None),
                color=alt.Color("STATUS:N", title=None, sort=list(REASON_COLOURS),
                                scale=alt.Scale(domain=list(REASON_COLOURS), range=list(REASON_COLOURS.values())),
                                legend=alt.Legend(orient="bottom", columns=2)),
                order=alt.Order("STATUS:N"),
                tooltip=["HOSPITAL", "STATUS", alt.Tooltip("sum(EUR):Q", format=",.0f", title="€")])
            labels = alt.Chart(tot).mark_text(align="left", dx=3, color=TEXT).encode(
                x="EUR:Q", y=alt.Y("HOSPITAL:N", sort=order), text="LABEL:N")
            st.altair_chart((bars + labels).properties(height=34 * len(order) + 60), use_container_width=True)

    # ---- 3. Today's transfers, one bar per route ----
    with right:
        st.subheader("Today's suggested transfers")
        st.caption("One bar per transfer, in priority order · shortage medicines first")
        f = q(f"""SELECT priority_rank AS RANK, product_name AS PRODUCT, from_hospital_id AS FROM_H,
                         to_hospital_id AS TO_H, saveable_value_eur::FLOAT AS EUR, is_national_shortage AS SHORTAGE
                  FROM {GOLD}.GOLD_TRANSFER_SUGGESTIONS WHERE {LATEST} ORDER BY priority_rank""")
        if f.empty:
            st.write("No transfer suggested today.")
        else:
            f["ROUTE"] = [f"{int(r)}. {a} → {b} · {p}" for r, a, b, p in zip(f.RANK, f.FROM_H, f.TO_H, f.PRODUCT)]
            f["KIND"] = f.SHORTAGE.map({True: "Medicine in shortage in France", False: "Transfer"}).fillna("Transfer")
            f["LABEL"] = f.EUR.map(lambda v: f" €{v:,.0f}")
            order = list(f.ROUTE)
            bars = alt.Chart(f).mark_bar().encode(
                x=alt.X("EUR:Q", title="€ saveable", axis=alt.Axis(format=",.0f"),
                        scale=alt.Scale(domain=[0, float(f.EUR.max()) * 1.18])),
                y=alt.Y("ROUTE:N", sort=order, title=None, axis=alt.Axis(labelLimit=320)),
                color=alt.Color("KIND:N", title=None,
                                scale=alt.Scale(domain=["Medicine in shortage in France", "Transfer"],
                                                range=[ORANGE, GREEN]),
                                legend=alt.Legend(orient="bottom", labelLimit=300)),
                tooltip=["ROUTE", "KIND", alt.Tooltip("EUR:Q", format=",.0f", title="€")])
            labels = alt.Chart(f).mark_text(align="left", dx=3, color=TEXT).encode(
                x="EUR:Q", y=alt.Y("ROUTE:N", sort=order), text="LABEL:N")
            st.altair_chart((bars + labels).properties(height=38 * len(order) + 60), use_container_width=True)

    st.markdown("---")
    left, right = st.columns(2)

    # ---- 4. Trend: at risk, saveable and target over the snapshot days ----
    with left:
        st.subheader("Trend by snapshot day")
        t = q(f"""
            SELECT v.snapshot_date AS DAY, SUM(v.value_at_risk_eur)::FLOAT AS AT_RISK,
                   COALESCE(MAX(s.saveable), 0)::FLOAT AS SAVEABLE
            FROM {GOLD}.GOLD_VALUE_AT_RISK v
            LEFT JOIN (SELECT snapshot_date, SUM(saveable_value_eur) AS saveable
                       FROM {GOLD}.GOLD_TRANSFER_SUGGESTIONS GROUP BY 1) s USING (snapshot_date)
            GROUP BY 1 ORDER BY 1""")
        if len(t) < 2:
            st.info("The trend appears from the second snapshot day. "
                    f"Today there is one day of results ({latest}).")
        else:
            t["TARGET (40 %)"] = TARGET * t.AT_RISK
            t = t.rename(columns={"AT_RISK": "At risk", "SAVEABLE": "Saveable"})
            long = t.melt(["DAY"], ["At risk", "Saveable", "TARGET (40 %)"], var_name="WHAT", value_name="EUR")
            st.caption("€ at risk, € saveable and the 40 % target, per day")
            st.altair_chart(alt.Chart(long).mark_line(point=True, strokeWidth=3).encode(
                x=alt.X("DAY:T", title=None, axis=alt.Axis(format="%d %b")),
                y=alt.Y("EUR:Q", title="€", axis=alt.Axis(format=",.0f")),
                color=alt.Color("WHAT:N", title=None,
                                scale=alt.Scale(domain=["At risk", "Saveable", "TARGET (40 %)"],
                                                range=[RED, GREEN, ORANGE]),
                                legend=alt.Legend(orient="bottom")),
                strokeDash=alt.condition(alt.datum.WHAT == "TARGET (40 %)", alt.value([6, 4]), alt.value([1, 0])),
                tooltip=[alt.Tooltip("DAY:T", format="%d %b"), "WHAT", alt.Tooltip("EUR:Q", format=",.0f")]
            ).properties(height=280), use_container_width=True)

    # ---- 5. Over-stock ----
    with right:
        st.subheader("Over-stock € by hospital")
        st.caption("Stock that will expire before it is used at the current pace: order less")
        o = q(f"""SELECT hospital_id AS ID, hospital_name AS NAME, SUM(overstock_value_eur)::FLOAT AS EUR
                  FROM {GOLD}.GOLD_DAYS_OF_COVER WHERE {LATEST} GROUP BY 1, 2 HAVING SUM(overstock_value_eur) > 0""")
        if o.empty:
            st.write("No over-stock today.")
        else:
            o["HOSPITAL"] = [short(i, n) for i, n in zip(o.ID, o.NAME)]
            o["LABEL"] = o.EUR.map(lambda v: f" €{v:,.0f}")
            order = list(o.sort_values("EUR", ascending=False).HOSPITAL)
            bars = alt.Chart(o).mark_bar(color=AMBER).encode(
                x=alt.X("EUR:Q", title="€ that will expire unused", axis=alt.Axis(format=",.0f"),
                        scale=alt.Scale(domain=[0, float(o.EUR.max()) * 1.18])),
                y=alt.Y("HOSPITAL:N", sort=order, title=None),
                tooltip=["HOSPITAL", alt.Tooltip("EUR:Q", format=",.0f", title="€")])
            labels = alt.Chart(o).mark_text(align="left", dx=3, color=TEXT).encode(
                x="EUR:Q", y=alt.Y("HOSPITAL:N", sort=order), text="LABEL:N")
            st.altair_chart((bars + labels).properties(height=40 * len(order) + 50), use_container_width=True)

    # ---- 6. Shortage medicines at risk ----
    st.markdown("---")
    st.subheader("Shortage medicines at risk")
    st.caption("Medicines in national shortage that expire within 90 days · most urgent first "
               "(red: under 30 days, amber: under 60 days)")
    s = q(f"""
        SELECT product_name AS MEDICINE, hospital_id AS ID, hospital_name AS NAME, qty_on_hand AS QTY,
               days_to_expiry AS DAYS_LEFT, value_at_risk_eur::FLOAT AS EUR
        FROM {GOLD}.GOLD_VALUE_AT_RISK WHERE is_national_shortage AND {LATEST}
        ORDER BY DAYS_LEFT""")
    if s.empty:
        st.write("No shortage medicine at risk today.")
    else:
        s["HOSPITAL"] = [short(i, n) for i, n in zip(s.ID, s.NAME)]
        # Row label = medicine + hospital code (unique, so the table needs no 0, 1, 2... column)
        s.index = [f"{m} · {i}" for m, i in zip(s.MEDICINE, s.ID)]
        s = s[["HOSPITAL", "QTY", "DAYS_LEFT", "EUR"]]
        s.columns = ["Hospital", "Quantity", "Days left", "€ at risk"]
        st.dataframe(s.style
                     .format({"€ at risk": "€{:,.0f}", "Quantity": "{:,.0f}", "Days left": "{:.0f}"})
                     .applymap(urgency, subset=["Days left"]),
                     use_container_width=True)

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

    st.markdown("---")

    # ---- Last load of each of the 4 sources ----
    st.subheader("Last load of each source")
    cards = st.columns(len(SOURCES))
    for col, (job, label) in zip(cards, SOURCES.items()):
        row = last[last.JOB == job]
        if row.empty:
            col.markdown(card(label, "No run logged", "", "#fbebeb", RED), unsafe_allow_html=True)
            continue
        hrs = float((pd.Timestamp.now(tz="UTC") - pd.to_datetime(row.RUN_AT.iloc[0], utc=True)).total_seconds() / 3600)
        ok = row.STATUS.iloc[0] == "SUCCESS"
        bg, fg = (("#e5f4e4", GREEN) if hrs < 26 else ("#f9eeda", "#8a5a00")) if ok else ("#fbebeb", RED)
        col.markdown(card(label, row.STATUS.iloc[0].capitalize(), f"{hrs:,.1f} h ago", bg, fg), unsafe_allow_html=True)

    st.markdown("---")
    left, right = st.columns(2)

    # ---- Grid: one cell per source and day ----
    with left:
        st.subheader("Loads per source and day")
        st.caption("Green: every run of the day succeeded · amber: a run failed, then a retry worked "
                   "· number = rows loaded")
        daily = sel[sel.JOB.isin(list(SOURCES))].groupby(["RUN_DATE", "JOB"]).agg(
            RUNS=("STATUS", "size"), FAILED=("STATUS", lambda x: int((x != "SUCCESS").sum())),
            ROWS_LOADED=("ROWS_LOADED", "sum")).reset_index()
        if daily.empty:
            st.write("No load in this date range.")
        else:
            daily["SOURCE"] = daily.JOB.map(SOURCES)
            daily["RESULT"] = daily.FAILED.map(lambda n: "All runs OK" if n == 0 else "Retried after a failure")
            daily["LABEL"] = daily.ROWS_LOADED.map(lambda v: f"{v:,.0f}")
            daily["DAY"] = pd.to_datetime(daily.RUN_DATE).dt.strftime("%d %b")
            day_order = sorted(daily.DAY.unique(), key=lambda d: pd.to_datetime(d + " 2026"))
            base = alt.Chart(daily).encode(
                x=alt.X("DAY:O", title=None, sort=day_order, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("SOURCE:N", title=None, sort=list(SOURCES.values())))
            grid = base.mark_rect(stroke="white", strokeWidth=3).encode(
                color=alt.Color("RESULT:N", title=None,
                                scale=alt.Scale(domain=["All runs OK", "Retried after a failure"],
                                                range=[GREEN, AMBER]),
                                legend=alt.Legend(orient="bottom")),
                tooltip=["DAY", "SOURCE", "RUNS", "FAILED", alt.Tooltip("ROWS_LOADED:Q", format=",.0f")])
            txt = base.mark_text(color="white", fontWeight="bold").encode(text="LABEL:N")
            st.altair_chart((grid + txt).properties(height=230), use_container_width=True)

    # ---- Quality gate: reject rate per night against the 15 % line ----
    with right:
        st.subheader("Quality gate, night by night")
        st.caption("Share of the night's consumption rows rejected · dashed line = 15 % gate "
                   "(above it, gold is not refreshed)")
        night = hist.groupby("DELIVERY_DATE").apply(
            lambda g: pd.Series({"RATE": g.loc[g.IS_REJECTED, "ROWS_RECEIVED"].sum() / g.ROWS_RECEIVED.sum()})
        ).reset_index()
        if night.empty:
            st.write("No delivery yet.")
        else:
            night["GATE"] = (night.RATE > MAX_REJECT).map({True: "Blocked", False: "Passed"})
            night["NIGHT"] = pd.to_datetime(night.DELIVERY_DATE).dt.strftime("%d %b")
            night["LABEL"] = night.RATE.map(lambda v: f"{v:.1%}")
            order = list(night.sort_values("DELIVERY_DATE").NIGHT)
            ymax = max(float(night.RATE.max()), MAX_REJECT) * 1.25
            bars = alt.Chart(night).mark_bar(size=38).encode(
                x=alt.X("NIGHT:O", title=None, sort=order, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("RATE:Q", title="Rows rejected", axis=alt.Axis(format="%"),
                        scale=alt.Scale(domain=[0, ymax])),
                color=alt.Color("GATE:N", title=None, scale=alt.Scale(domain=["Passed", "Blocked"],
                                                                     range=[GREEN, RED]),
                                legend=alt.Legend(orient="bottom")),
                tooltip=["NIGHT", alt.Tooltip("RATE:Q", format=".1%"), "GATE"])
            labels = alt.Chart(night).mark_text(dy=-8, color=TEXT).encode(
                x=alt.X("NIGHT:O", sort=order), y="RATE:Q", text="LABEL:N")
            rule = alt.Chart(pd.DataFrame({"y": [MAX_REJECT]})).mark_rule(
                strokeDash=[6, 4], color=RED, size=2).encode(y="y:Q")
            st.altair_chart((bars + labels + rule).properties(height=230), use_container_width=True)

    # ---- Why rows were rejected ----
    st.subheader("Why rows were rejected")
    st.caption("Share of each reason among the night's quarantined consumption rows "
               "(duplicates are kept once, so they are not errors) · hover for the row counts")
    rej = hist[hist.ROW_STATUS != "clean"].copy()
    if rej.empty:
        st.write("No rejected row.")
    else:
        rej["NIGHT"] = pd.to_datetime(rej.DELIVERY_DATE).dt.strftime("%d %b")
        rej["REASON"] = rej.ROW_STATUS.str.replace("_", " ")
        order = sorted(rej.NIGHT.unique(), key=lambda d: pd.to_datetime(d + " 2026"))
        st.altair_chart(alt.Chart(rej).mark_bar().encode(
            y=alt.Y("NIGHT:O", title=None, sort=order),
            # share, not count: the first night holds 4 weeks of history and would hide the others
            x=alt.X("sum(ROWS_RECEIVED):Q", title=None, stack="normalize", axis=alt.Axis(format="%")),
            color=alt.Color("REASON:N", title=None, scale=alt.Scale(scheme="tableau10"),
                            legend=alt.Legend(orient="bottom", columns=3)),
            tooltip=["NIGHT", "REASON", alt.Tooltip("sum(ROWS_RECEIVED):Q", title="Rows")]
        ).properties(height=40 * len(order) + 70), use_container_width=True)
