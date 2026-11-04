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


# Five colours, one meaning each (the same as the hospital dashboard):
#   green = OK / can be saved, amber = warning, red = problem, blue = cold chain, grey = neutral
GREEN, AMBER, RED, BLUE, GREY = "#2e7d32", "#f9a825", "#c62828", "#1565c0", "#9e9e9e"
TEXT = "#8a8f98"           # value labels: readable on light and dark themes
REASON_COLOURS = {"Transferable": GREEN, "Under 30 days": RED, "Under €200": AMBER, "Cold chain": BLUE}
REASONS = {"transferable": "Transferable", "under_30_days": "Under 30 days",
           "under_200_eur": "Under €200", "no_cold_chain_proof": "Cold chain"}
SOURCES = {"s1_stock_postgres": "S1 · Stock", "s2_consumption_files": "S2 · Consumption",
           "s3_bdpm_reference": "S3 · Drug database", "s4_shortages": "S4 · Shortages"}
ALL = "All hospitals"


def short(hid, name):
    """'H07', 'Centre Hospitalier de l'Est' -> 'H07 · CH Est' (full names do not fit on a chart axis)."""
    n = str(name)
    if n == hid:
        return hid
    for long_, abbr in (("Centre Hospitalier ", "CH "), ("Hôpital ", "")):
        if n.startswith(long_):
            n = abbr + n[len(long_):]
    n = re.sub(r"^(CH )?(de l'|de la |des |du |de )", r"\1", n)
    return f"{hid} · {n[:1].upper() + n[1:]}"


def eur(v):
    return f"€{v:,.0f}"


def urgency(days):
    """Table cell colour by days left. Fixed light fill + black text, so it stays readable in dark mode."""
    if days < 30:
        return "background-color: #f6d5d5; color: black; font-weight: 600"
    if days < 60:
        return "background-color: #fbe9c4; color: black"
    return ""


def chip(label, value, colour):
    """Small status pill for the header strip."""
    return (f"<span style='display:inline-block;margin:0 8px 6px 0;padding:4px 12px;border-radius:999px;"
            f"border:1px solid {colour};font-size:0.85rem'>"
            f"<span style='opacity:0.7'>{label}</span> <b style='color:{colour}'>{value}</b></span>")


def card(title, status, detail, bg, fg):
    return (f"<div style='background:{bg};border-radius:10px;padding:12px 14px;color:#1f2933'>"
            f"<div style='font-size:0.85rem;opacity:0.8'>{title}</div>"
            f"<div style='font-size:1.25rem;font-weight:700;color:{fg}'>{status}</div>"
            f"<div style='font-size:0.85rem'>{detail}</div></div>")


def action_row(rank, product, frm, to, value, shortage):
    """One suggested transfer, written as an action: what to send, from where, to where, what it saves."""
    badge = (f"<span style='background:{RED};color:white;border-radius:6px;padding:1px 8px;"
             f"font-size:0.72rem;margin-left:8px;vertical-align:middle'>Shortage in France</span>") if shortage else ""
    return (f"<div style='display:flex;align-items:center;gap:16px;padding:10px 16px;margin-bottom:8px;"
            f"border:1px solid rgba(128,128,128,0.35);border-left:5px solid {RED if shortage else GREEN};"
            f"border-radius:8px'>"
            f"<div style='font-size:1.2rem;font-weight:700;opacity:0.55;width:22px'>{rank}</div>"
            f"<div style='flex:1'><div style='font-weight:600'>{product}{badge}</div>"
            f"<div style='font-size:0.85rem;opacity:0.75'>Send from <b>{frm}</b> &nbsp;→&nbsp; to <b>{to}</b></div></div>"
            f"<div style='text-align:right'><div style='font-size:1.15rem;font-weight:700'>{eur(value)}</div>"
            f"<div style='font-size:0.75rem;opacity:0.65'>saveable</div></div></div>")


def hbar(df, y, x, colour, x_title, height_per_row=34):
    """Sorted horizontal bars with the value printed at the end of each bar."""
    df = df.sort_values(x, ascending=False).copy()
    df["LABEL"] = df[x].map(lambda v: f" {eur(v)}")
    order = list(df[y])
    bars = alt.Chart(df).mark_bar(color=colour).encode(
        x=alt.X(f"{x}:Q", title=x_title, axis=alt.Axis(format=",.0f"),
                scale=alt.Scale(domain=[0, float(df[x].max()) * 1.2])),
        y=alt.Y(f"{y}:N", sort=order, title=None, axis=alt.Axis(labelLimit=260)),
        tooltip=[y, alt.Tooltip(f"{x}:Q", format=",.0f", title="€")])
    labels = alt.Chart(df).mark_text(align="left", dx=3, color=TEXT).encode(
        x=f"{x}:Q", y=alt.Y(f"{y}:N", sort=order), text="LABEL:N")
    return (bars + labels).properties(height=height_per_row * len(order) + 50)


st.set_page_config(page_title="MédiRelais · Team", layout="wide")
latest = q(f"SELECT MAX(snapshot_date) AS D FROM {GOLD}.GOLD_VALUE_AT_RISK").D[0]
LATEST = f"snapshot_date = '{latest}'"

# Pipeline tables are read once here: the header strip and the Pipeline tab share them (cached)
loads = q(f"SELECT * FROM {GOLD}.GOLD_PIPELINE_LOADS")
hist = q(f"SELECT * FROM {GOLD}.GOLD_QUALITY_HISTORY")
dq = q(f"SELECT * FROM {GOLD}.GOLD_DATA_QUALITY")
last = loads.sort_values("RUN_AT").groupby("JOB").tail(1) if not loads.empty else loads

# =============================== HEADER STRIP ===============================
st.title("💊 MédiRelais · network")
chips = [chip("Data as of", str(latest), GREY), chip("Hospitals", "12", GREY)]
if loads.empty:
    chips.append(chip("Pipeline", "no run logged", RED))
else:
    ok_all = (last.STATUS == "SUCCESS").all()
    chips.append(chip("Pipeline", "last loads OK" if ok_all else "a load failed", GREEN if ok_all else RED))
if not dq.empty:
    blocked = bool(dq.GOLD_BLOCKED[0])
    chips.append(chip("Quality, last night", f"{float(dq.REJECT_RATE[0]):.1%} rejected · "
                      + ("gold blocked" if blocked else "gate passed"), RED if blocked else GREEN))
st.markdown("".join(chips), unsafe_allow_html=True)
if not dq.empty and dq.GOLD_BLOCKED[0]:
    st.error(f"Last night's data was rejected by the quality gate: every figure below is from {latest}.")

business, pipeline = st.tabs(["Business", "Pipeline"])

# =============================== BUSINESS ===============================
with business:
    # Data for the charts (queries unchanged), read before the filter so it can list the hospitals
    h = q(f"""SELECT hospital_id AS ID, hospital_name AS NAME,
                     COALESCE(transfer_block_reason, 'transferable') AS REASON,
                     SUM(value_at_risk_eur)::FLOAT AS EUR
              FROM {GOLD}.GOLD_VALUE_AT_RISK WHERE {LATEST} GROUP BY 1, 2, 3""")
    f = q(f"""SELECT priority_rank AS RANK, product_name AS PRODUCT, from_hospital_id AS FROM_H,
                     to_hospital_id AS TO_H, saveable_value_eur::FLOAT AS EUR, is_national_shortage AS SHORTAGE
              FROM {GOLD}.GOLD_TRANSFER_SUGGESTIONS WHERE {LATEST} ORDER BY priority_rank""")
    o = q(f"""SELECT hospital_id AS ID, hospital_name AS NAME, SUM(overstock_value_eur)::FLOAT AS EUR
              FROM {GOLD}.GOLD_DAYS_OF_COVER WHERE {LATEST} GROUP BY 1, 2 HAVING SUM(overstock_value_eur) > 0""")
    s = q(f"""
        SELECT product_name AS MEDICINE, hospital_id AS ID, hospital_name AS NAME, qty_on_hand AS QTY,
               days_to_expiry AS DAYS_LEFT, value_at_risk_eur::FLOAT AS EUR
        FROM {GOLD}.GOLD_VALUE_AT_RISK WHERE is_national_shortage AND {LATEST}
        ORDER BY DAYS_LEFT""")

    names = {}
    for d in (h, o, s):
        if not d.empty:
            names.update(dict(zip(d.ID, d.NAME)))
    label = {i: short(i, names.get(i, i)) for i in set(names) | set(f.FROM_H) | set(f.TO_H)}

    # ---- Hospital filter: applies to the charts below, never to the KPI row ----
    pick = st.selectbox("Hospital", [ALL] + sorted(label), format_func=lambda i: i if i == ALL else label[i])
    one = pick != ALL
    if one:
        h, o, s = h[h.ID == pick], o[o.ID == pick], s[s.ID == pick]
        f = f[(f.FROM_H == pick) | (f.TO_H == pick)]

    # ---- KPI row (network, unchanged) ----
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
    if one:
        st.caption(f"These three numbers are for the whole network. Everything below is filtered on {label[pick]}.")
    st.markdown("---")

    # ---- Today's actions ----
    st.subheader("Today's actions: which transfers should we make?")
    if f.empty:
        st.info("No transfer suggested today" + (f" for {label[pick]}." if one else "."))
    else:
        st.caption(f"{len(f)} transfer{'s' if len(f) > 1 else ''} · {eur(f.EUR.sum())} saveable · "
                   "in priority order, medicines in shortage in France first")
        st.markdown("".join(action_row(int(r.RANK), r.PRODUCT, label[r.FROM_H], label[r.TO_H], r.EUR,
                                       bool(r.SHORTAGE)) for r in f.itertuples()),
                    unsafe_allow_html=True)
    st.markdown("---")

    # ---- 1. Where the € at risk goes: one bar, three parts ----
    st.subheader("Of the € at risk, how much can transfers save?")
    at_risk = float(h.EUR.sum()) if one else k.AT_RISK_EUR
    saveable = float(f[f.FROM_H == pick].EUR.sum()) if one else k.SAVE_EUR
    target_eur = TARGET * at_risk
    saved = min(saveable, at_risk)
    gap = max(target_eur - saved, 0.0)
    parts = pd.DataFrame({
        "PART": ["Saveable by transfers", "Gap to the 40 % target", "Rest at risk"],
        "EUR": [saved, gap, max(at_risk - saved - gap, 0.0)]})
    parts["END"] = parts.EUR.cumsum()
    parts["START"] = parts.END - parts.EUR
    parts["MID"] = (parts.START + parts.END) / 2
    parts["LABEL"] = parts.EUR.map(eur)
    parts["ROW"] = "€ at risk"
    seg = alt.Chart(parts).mark_bar(size=46).encode(
        x=alt.X("START:Q", title=None, axis=None, scale=alt.Scale(domain=[0, max(at_risk, 1.0)])),
        x2="END:Q", y=alt.Y("ROW:N", title=None, axis=None),
        color=alt.Color("PART:N", title=None, sort=list(parts.PART),
                        scale=alt.Scale(domain=list(parts.PART), range=[GREEN, AMBER, GREY]),
                        legend=alt.Legend(orient="bottom")),
        tooltip=["PART", alt.Tooltip("EUR:Q", format=",.0f", title="€")])
    seg_txt = alt.Chart(parts[parts.EUR > 0.08 * max(at_risk, 1.0)]).mark_text(fontWeight="bold").encode(
        x="MID:Q", y="ROW:N", text="LABEL:N",
        color=alt.condition(alt.datum.PART == "Gap to the 40 % target", alt.value("black"), alt.value("white")))
    st.altair_chart((seg + seg_txt).properties(height=110), use_container_width=True)
    st.caption(f"{label[pick] + ': ' if one else ''}At risk {eur(at_risk)} · "
               f"target = 40 % of it ({eur(target_eur)}). Saveable = what the receiving hospital can use "
               "before expiry. Actually saved needs a register of real transfers (out of scope, README).")

    st.markdown("---")
    left, right = st.columns(2)

    # ---- 2. Hospitals (or, for one hospital, reasons): € at risk and whether it can move ----
    with left:
        h = h.copy()
        h["STATUS"] = h.REASON.map(REASONS).fillna("Other")
        if one:
            st.subheader("Why can't this stock move?")
            st.caption(f"€ at risk at {label[pick]}, by what blocks a transfer")
        else:
            st.subheader("Which hospitals hold the € at risk?")
            st.caption("Coloured by what blocks a transfer · green = can move")
        if h.empty:
            st.info("Nothing at risk today.")
        elif one:
            r = h.groupby("STATUS", as_index=False).EUR.sum().sort_values("EUR", ascending=False)
            r["LABEL"] = r.EUR.map(lambda v: f" {eur(v)}")
            order = list(r.STATUS)
            bars = alt.Chart(r).mark_bar().encode(
                x=alt.X("EUR:Q", title="€ at risk", axis=alt.Axis(format=",.0f"),
                        scale=alt.Scale(domain=[0, float(r.EUR.max()) * 1.2])),
                y=alt.Y("STATUS:N", sort=order, title=None),
                color=alt.Color("STATUS:N", legend=None,
                                scale=alt.Scale(domain=list(REASON_COLOURS), range=list(REASON_COLOURS.values()))),
                tooltip=["STATUS", alt.Tooltip("EUR:Q", format=",.0f", title="€")])
            labels = alt.Chart(r).mark_text(align="left", dx=3, color=TEXT).encode(
                x="EUR:Q", y=alt.Y("STATUS:N", sort=order), text="LABEL:N")
            st.altair_chart((bars + labels).properties(height=40 * len(order) + 50), use_container_width=True)
        else:
            h["HOSPITAL"] = h.ID.map(label)
            tot = h.groupby("HOSPITAL", as_index=False).EUR.sum().sort_values("EUR", ascending=False)
            tot["LABEL"] = tot.EUR.map(lambda v: f" {eur(v)}")
            order = list(tot.HOSPITAL)
            bars = alt.Chart(h).mark_bar().encode(
                x=alt.X("sum(EUR):Q", title="€ at risk", axis=alt.Axis(format=",.0f"),
                        scale=alt.Scale(domain=[0, float(tot.EUR.max()) * 1.2])),
                y=alt.Y("HOSPITAL:N", sort=order, title=None),
                color=alt.Color("STATUS:N", title=None, sort=list(REASON_COLOURS),
                                scale=alt.Scale(domain=list(REASON_COLOURS), range=list(REASON_COLOURS.values())),
                                legend=alt.Legend(orient="bottom", columns=4)),
                order=alt.Order("STATUS:N"),
                tooltip=["HOSPITAL", "STATUS", alt.Tooltip("sum(EUR):Q", format=",.0f", title="€")])
            labels = alt.Chart(tot).mark_text(align="left", dx=3, color=TEXT).encode(
                x="EUR:Q", y=alt.Y("HOSPITAL:N", sort=order), text="LABEL:N")
            st.altair_chart((bars + labels).properties(height=30 * len(order) + 60), use_container_width=True)

    # ---- 3. Over-stock ----
    with right:
        st.subheader("Where are we ordering too much?")
        st.caption("Over-stock: € of stock that will expire before it is used at the current pace")
        if o.empty:
            st.info("No over-stock today" + (f" at {label[pick]}." if one else "."))
        else:
            o = o.copy()
            o["HOSPITAL"] = o.ID.map(label)
            st.altair_chart(hbar(o, "HOSPITAL", "EUR", AMBER, "€ that will expire unused", 34),
                            use_container_width=True)

    # ---- 4. Shortage medicines at risk ----
    st.markdown("---")
    st.subheader("Which shortage medicines expire soonest?")
    st.caption("Medicines in national shortage that expire within 90 days · most urgent first "
               "(red: under 30 days, amber: under 60 days)")
    if s.empty:
        st.info("No shortage medicine at risk today" + (f" at {label[pick]}." if one else "."))
    else:
        s = s.copy()
        # Row label = medicine + hospital code (unique, so the table needs no 0, 1, 2... column)
        s.index = [f"{m} · {i}" for m, i in zip(s.MEDICINE, s.ID)]
        s["HOSPITAL"] = s.ID.map(label)
        s = s[["HOSPITAL", "QTY", "DAYS_LEFT", "EUR"]]
        s.columns = ["Hospital", "Quantity", "Days left", "€ at risk"]
        st.dataframe(s.style
                     .format({"€ at risk": "€{:,.0f}", "Quantity": "{:,.0f}", "Days left": "{:.0f}"})
                     .applymap(urgency, subset=["Days left"]),
                     use_container_width=True)

    # ---- 5. Trend (only once there are two snapshot days) ----
    t = q(f"""
        SELECT v.snapshot_date AS DAY, SUM(v.value_at_risk_eur)::FLOAT AS AT_RISK,
               COALESCE(MAX(s.saveable), 0)::FLOAT AS SAVEABLE
        FROM {GOLD}.GOLD_VALUE_AT_RISK v
        LEFT JOIN (SELECT snapshot_date, SUM(saveable_value_eur) AS saveable
                   FROM {GOLD}.GOLD_TRANSFER_SUGGESTIONS GROUP BY 1) s USING (snapshot_date)
        GROUP BY 1 ORDER BY 1""")
    st.markdown("---")
    st.subheader("Are we getting closer to the 40 % target?")
    if len(t) < 2:
        st.caption(f"The trend appears from the second snapshot day (today: one day, {latest}).")
    else:
        st.caption("Whole network, per snapshot day · dashed line = 40 % target")
        t["Target (40 %)"] = TARGET * t.AT_RISK
        t = t.rename(columns={"AT_RISK": "At risk", "SAVEABLE": "Saveable"})
        long = t.melt(["DAY"], ["At risk", "Saveable", "Target (40 %)"], var_name="WHAT", value_name="EUR")
        st.altair_chart(alt.Chart(long).mark_line(point=True, strokeWidth=3).encode(
            x=alt.X("DAY:T", title=None, axis=alt.Axis(format="%d %b")),
            y=alt.Y("EUR:Q", title="€", axis=alt.Axis(format=",.0f")),
            color=alt.Color("WHAT:N", title=None,
                            scale=alt.Scale(domain=["At risk", "Saveable", "Target (40 %)"],
                                            range=[GREY, GREEN, AMBER]),
                            legend=alt.Legend(orient="bottom")),
            strokeDash=alt.condition(alt.datum.WHAT == "Target (40 %)", alt.value([6, 4]), alt.value([1, 0])),
            tooltip=[alt.Tooltip("DAY:T", format="%d %b"), "WHAT", alt.Tooltip("EUR:Q", format=",.0f")]
        ).properties(height=260), use_container_width=True)

# =============================== PIPELINE ===============================
with pipeline:
    if loads.empty:
        st.warning("No ingestion run logged yet.")
        st.stop()

    kpi_box = st.container()      # KPI row drawn first on screen, filled once the date range is known

    # ---- 1. Status per source, now ----
    st.markdown("---")
    st.subheader("Is each source up to date?")
    cards = st.columns(len(SOURCES))
    for col, (job, name) in zip(cards, SOURCES.items()):
        row = last[last.JOB == job]
        if row.empty:
            col.markdown(card(name, "No run logged", "", "#f6d5d5", RED), unsafe_allow_html=True)
            continue
        hrs = float((pd.Timestamp.now(tz="UTC") - pd.to_datetime(row.RUN_AT.iloc[0], utc=True)).total_seconds() / 3600)
        ok = row.STATUS.iloc[0] == "SUCCESS"
        bg, fg = (("#e3f1e3", GREEN) if hrs < 26 else ("#fbe9c4", "#7a5200")) if ok else ("#f6d5d5", RED)
        col.markdown(card(name, row.STATUS.iloc[0].capitalize(),
                          f"{hrs:,.1f} h ago · {int(row.ROWS_LOADED.iloc[0]):,} rows", bg, fg),
                     unsafe_allow_html=True)

    # ---- 2. History ----
    st.markdown("---")
    st.subheader("History")
    days = sorted(loads.RUN_DATE.unique())
    start, end = st.select_slider("Run dates", options=days, value=(days[0], days[-1]))
    sel = loads[(loads.RUN_DATE >= start) & (loads.RUN_DATE <= end)]

    # KPI row (unchanged)
    with kpi_box:
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

    # ---- Grid: one cell per source and day ----
    with left:
        st.markdown("**Did every source load, every day?**")
        st.caption("Green: all runs OK · amber: a run failed, then a retry worked · red: failed · "
                   "number = rows loaded")
        daily = sel[sel.JOB.isin(list(SOURCES))].groupby(["RUN_DATE", "JOB"]).agg(
            RUNS=("STATUS", "size"), FAILED=("STATUS", lambda x: int((x != "SUCCESS").sum())),
            OK=("STATUS", lambda x: int((x == "SUCCESS").sum())),
            ROWS_LOADED=("ROWS_LOADED", "sum")).reset_index()
        if daily.empty:
            st.info("No load in this date range.")
        else:
            daily["SOURCE"] = daily.JOB.map(SOURCES)
            daily["RESULT"] = [("All runs OK" if fl == 0 else "Retried after a failure") if ok else "Failed"
                               for fl, ok in zip(daily.FAILED, daily.OK)]
            daily["LABEL"] = daily.ROWS_LOADED.map(lambda v: f"{v:,.0f}")
            daily["DAY"] = pd.to_datetime(daily.RUN_DATE).dt.strftime("%d %b")
            day_order = sorted(daily.DAY.unique(), key=lambda d: pd.to_datetime(d + " 2026"))
            base = alt.Chart(daily).encode(
                x=alt.X("DAY:O", title=None, sort=day_order, axis=alt.Axis(labelAngle=0, orient="top")),
                y=alt.Y("SOURCE:N", title=None, sort=list(SOURCES.values())))
            grid = base.mark_rect(stroke="white", strokeWidth=3, cornerRadius=4).encode(
                color=alt.Color("RESULT:N", title=None,
                                scale=alt.Scale(domain=["All runs OK", "Retried after a failure", "Failed"],
                                                range=[GREEN, AMBER, RED]),
                                legend=alt.Legend(orient="bottom")),
                tooltip=["DAY", "SOURCE", "RUNS", "FAILED", alt.Tooltip("ROWS_LOADED:Q", format=",.0f")])
            txt = base.mark_text(fontWeight="bold").encode(
                text="LABEL:N",
                color=alt.condition(alt.datum.RESULT == "Retried after a failure", alt.value("black"),
                                    alt.value("white")))
            st.altair_chart((grid + txt).properties(height=230), use_container_width=True)

    # ---- Quality gate: reject rate per night against the 15 % line ----
    with right:
        st.markdown("**Did the quality gate let each night through?**")
        st.caption("Share of the night's consumption rows rejected · dashed line = 15 % gate "
                   "(above it, gold is not refreshed)")
        night = hist.groupby("DELIVERY_DATE").apply(
            lambda g: pd.Series({"RATE": g.loc[g.IS_REJECTED, "ROWS_RECEIVED"].sum() / g.ROWS_RECEIVED.sum()})
        ).reset_index() if not hist.empty else pd.DataFrame()
        if night.empty:
            st.info("No delivery yet.")
        else:
            night["GATE"] = (night.RATE > MAX_REJECT).map({True: "Blocked", False: "Passed"})
            night["NIGHT"] = pd.to_datetime(night.DELIVERY_DATE).dt.strftime("%d %b")
            night["LABEL"] = night.RATE.map(lambda v: f"{v:.1%}")
            order = list(night.sort_values("DELIVERY_DATE").NIGHT)
            ymax = max(float(night.RATE.max()), MAX_REJECT) * 1.25
            bars = alt.Chart(night).mark_bar(size=34, cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
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

    # ---- Why rows were rejected, one night at a time ----
    st.markdown("**Why were rows rejected?**")
    rej = hist[hist.ROW_STATUS != "clean"].copy() if not hist.empty else pd.DataFrame()
    if rej.empty:
        st.info("No rejected row.")
    else:
        nights = sorted(rej.DELIVERY_DATE.unique())
        nsel = st.selectbox("Night", nights[::-1], format_func=lambda d: pd.to_datetime(d).strftime("%d %b %Y"))
        r = rej[rej.DELIVERY_DATE == nsel].groupby(["ROW_STATUS", "IS_REJECTED"], as_index=False).ROWS_RECEIVED.sum()
        r["REASON"] = r.ROW_STATUS.str.replace("_", " ").str.capitalize()
        r["KIND"] = r.IS_REJECTED.map({True: "Rejected", False: "Kept once (not an error)"})
        r["LABEL"] = r.ROWS_RECEIVED.map(lambda v: f" {v:,.0f} rows")
        r = r.sort_values("ROWS_RECEIVED", ascending=False)
        order = list(r.REASON)
        st.caption("Red = rows held in quarantine · grey = duplicates, kept once so they are not errors")
        bars = alt.Chart(r).mark_bar().encode(
            x=alt.X("ROWS_RECEIVED:Q", title="Rows", scale=alt.Scale(domain=[0, float(r.ROWS_RECEIVED.max()) * 1.25])),
            y=alt.Y("REASON:N", sort=order, title=None),
            color=alt.Color("KIND:N", title=None,
                            scale=alt.Scale(domain=["Rejected", "Kept once (not an error)"], range=[RED, GREY]),
                            legend=None),
            tooltip=["REASON", "KIND", alt.Tooltip("ROWS_RECEIVED:Q", title="Rows")])
        labels = alt.Chart(r).mark_text(align="left", dx=3, color=TEXT).encode(
            x="ROWS_RECEIVED:Q", y=alt.Y("REASON:N", sort=order), text="LABEL:N")
        st.altair_chart((bars + labels).properties(height=36 * len(order) + 50), use_container_width=True)
