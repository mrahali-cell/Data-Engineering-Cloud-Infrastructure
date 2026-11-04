"""MédiRelais · hospital dashboard: one hospital, no purchase prices.

The same code is deployed once per hospital, each app owned by that hospital's pharmacist role
(snowflake/06_hospital_apps.sql). A Streamlit app runs with its owner's rights, so Snowflake's
row access policy shows only that hospital's rows and the masking policy hides purchase prices
(terraform/governance.tf). The code never filters by hospital itself.
"""
import altair as alt
import pandas as pd
import streamlit as st
from snowflake.snowpark.context import get_active_session

session = get_active_session()
GOLD = "MEDIRELAIS.GOLD"
TARGET = 0.40            # README: share of the value at risk MédiRelais aims to save


# Gold changes once a day (06:00), so each query result is reused for an hour instead of
# waking the warehouse at every page view. Each hospital is its own app, so nothing is shared.
@st.cache_data(ttl=3600)
def q(sql):
    return session.sql(sql).to_pandas()


st.set_page_config(page_title="MédiRelais · Hospital", layout="wide")

# --- Which hospital: the only one the row access policy lets this app see ---
hospitals = q(f"""
    SELECT DISTINCT hospital_id AS ID, hospital_name AS NAME FROM {GOLD}.GOLD_DAYS_OF_COVER
    UNION
    SELECT DISTINCT hospital_id, hospital_name FROM {GOLD}.GOLD_VALUE_AT_RISK
    ORDER BY ID
""")
if hospitals.empty:
    st.warning("No data visible for this role yet.")
    st.stop()
if len(hospitals) > 1:
    # Only an admin or the network role sees several hospitals: test mode
    st.info("Test mode: this role sees every hospital. A pharmacist's app shows one only.")
    hid = st.selectbox("Hospital", hospitals.ID, format_func=lambda h: f"{h} · "
                       + hospitals.set_index("ID").NAME[h])
else:
    hid = hospitals.ID[0]
hname = hospitals.set_index("ID").NAME[hid]

latest = q(f"SELECT MAX(snapshot_date) AS D FROM {GOLD}.GOLD_VALUE_AT_RISK").D[0]
LATEST = f"snapshot_date = '{latest}'"
H = f"hospital_id = '{hid}'"

# --- Header: name, date, data quality of the night ---
dq = q(f"SELECT * FROM {GOLD}.GOLD_DATA_QUALITY")
left, right = st.columns([3, 2])
left.title(f"💊 {hname}")
left.caption(f"MédiRelais · data as of {latest}")
if not dq.empty and dq.GOLD_BLOCKED[0]:
    right.error(f"Last night's data was rejected ({float(dq.REJECT_RATE[0]):.0%}): figures are from {latest}.")
else:
    right.success("Data quality OK: figures are from last night.")

# --- Key numbers ---
risk = q(f"""
    SELECT batch_id, product_name, qty_on_hand, value_at_risk_eur::FLOAT AS value_eur,
           days_to_expiry, transfer_block_reason, is_national_shortage
    FROM {GOLD}.GOLD_VALUE_AT_RISK WHERE {LATEST} AND {H}
""")
risk.columns = [c.upper() for c in risk.columns]
transfers = q(f"""
    SELECT priority_rank, product_name, from_hospital_id, from_hospital, to_hospital_id, to_hospital,
           qty_on_hand, usable_qty_before_expiry, saveable_value_eur::FLOAT AS saveable_eur,
           days_to_expiry, is_national_shortage
    FROM {GOLD}.GOLD_TRANSFER_SUGGESTIONS
    WHERE {LATEST} AND (from_hospital_id = '{hid}' OR to_hospital_id = '{hid}')
    ORDER BY priority_rank
""")
transfers.columns = [c.upper() for c in transfers.columns]
out_ = transfers[transfers.FROM_HOSPITAL_ID == hid]
in_ = transfers[transfers.TO_HOSPITAL_ID == hid]

at_risk = risk.VALUE_EUR.sum()
saveable = out_.SAVEABLE_EUR.sum()
rate = saveable / at_risk if at_risk else 0.0
shortage = int(risk.IS_NATIONAL_SHORTAGE.sum())

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Expiring within 90 days", f"€{at_risk:,.0f}")
k2.metric("Saveable by transfers", f"€{saveable:,.0f}")
k3.metric("Recovery rate", f"{rate:.0%}", help="Saveable ÷ at risk. Network target: 40 %")
k3.progress(min(rate / TARGET, 1.0))
k3.caption(f"{min(rate / TARGET, 1.0):.0%} of the 40 % target")
k4.metric("Transfers to send", len(out_))
k5.metric("Transfers to receive", len(in_))
if shortage:
    st.error(f"⚠ {shortage} batch(es) at risk are medicines in national shortage: handle them first.")

# --- Act today | Expiry timeline ---
a, b = st.columns(2)
with a:
    st.subheader("Act today")
    st.caption("Transfers to send (prepare the batch for the courier)")
    st.dataframe(out_[["PRIORITY_RANK", "PRODUCT_NAME", "TO_HOSPITAL", "QTY_ON_HAND",
                       "DAYS_TO_EXPIRY", "SAVEABLE_EUR", "IS_NATIONAL_SHORTAGE"]],
                 use_container_width=True)
    st.caption("Transfers to receive (check you have room and will use it)")
    st.dataframe(in_[["PRIORITY_RANK", "PRODUCT_NAME", "FROM_HOSPITAL", "USABLE_QTY_BEFORE_EXPIRY",
                      "DAYS_TO_EXPIRY", "IS_NATIONAL_SHORTAGE"]],
                 use_container_width=True)
with b:
    st.subheader("Expiry timeline")
    st.caption("€ at risk by days left, coloured by what can be done")
    if risk.empty:
        st.write("Nothing at risk.")
    else:
        t = risk.copy()
        t["WHEN"] = pd.cut(t.DAYS_TO_EXPIRY, [-1, 30, 60, 90], labels=["0–30 d", "30–60 d", "60–90 d"])
        t["STATUS"] = t.TRANSFER_BLOCK_REASON.fillna("transferable").map({
            "transferable": "Transferable", "under_30_days": "Under 30 days",
            "under_200_eur": "Under €200", "no_cold_chain_proof": "Cold chain"})
        t = t.groupby(["WHEN", "STATUS"], observed=True).VALUE_EUR.sum().reset_index()
        st.altair_chart(
            alt.Chart(t).mark_bar().encode(
                y=alt.Y("WHEN:N", title=None, sort=["0–30 d", "30–60 d", "60–90 d"]),
                x=alt.X("VALUE_EUR:Q", title="€ at risk"),
                color=alt.Color("STATUS:N", title=None,
                                scale=alt.Scale(domain=["Transferable", "Under 30 days", "Under €200", "Cold chain"],
                                                range=["#2e7d32", "#c62828", "#f9a825", "#1565c0"])),
                tooltip=["WHEN", "STATUS", alt.Tooltip("VALUE_EUR:Q", format=",.0f")]),
            use_container_width=True)

# --- Use first | Buyer ---
c, d = st.columns(2)
with c:
    st.subheader("Use first (cannot be transferred)")
    st.caption("Use these locally or warn the prescribers")
    use_first = risk[risk.TRANSFER_BLOCK_REASON.notna()].sort_values("DAYS_TO_EXPIRY")
    st.dataframe(use_first[["PRODUCT_NAME", "QTY_ON_HAND", "DAYS_TO_EXPIRY", "VALUE_EUR",
                            "TRANSFER_BLOCK_REASON"]], use_container_width=True)
with d:
    st.subheader("Buyer")
    cover = q(f"""
        SELECT product_name, avg_daily_use::FLOAT AS daily_use, days_of_cover::FLOAT AS days_of_cover,
               min_days_to_expiry, overstock_value_eur::FLOAT AS overstock_eur, is_overstock_alert
        FROM {GOLD}.GOLD_DAYS_OF_COVER WHERE {LATEST} AND {H}
    """)
    cover.columns = [c.upper() for c in cover.columns]
    over = cover[cover.IS_OVERSTOCK_ALERT].sort_values("OVERSTOCK_EUR", ascending=False)
    st.caption("Over-stock: stop ordering these")
    st.dataframe(over[["PRODUCT_NAME", "DAILY_USE", "DAYS_OF_COVER", "MIN_DAYS_TO_EXPIRY", "OVERSTOCK_EUR"]],
                 use_container_width=True)
    low = cover[cover.DAYS_OF_COVER < 7].sort_values("DAYS_OF_COVER")
    st.caption("Low cover: under 7 days left at the normal pace, order now")
    st.dataframe(low[["PRODUCT_NAME", "DAILY_USE", "DAYS_OF_COVER"]].style.apply(
                     lambda r: ["background-color: #fbebeb" if r.DAYS_OF_COVER < 3 else ""] * len(r), axis=1),
                 use_container_width=True)
