import streamlit as st
from snowflake.snowpark.context import get_active_session

session = get_active_session()

# Gold changes once a day (06:00), so each query result is reused for an hour instead of
# waking the warehouse at every page view
@st.cache_data(ttl=3600)
def q(sql):
    return session.sql(sql).to_pandas()

# Gold keeps one row per snapshot day: always show the latest day only,
# otherwise the totals add up every day loaded so far.
LATEST = "snapshot_date = (SELECT MAX(snapshot_date) FROM MEDIRELAIS.GOLD.GOLD_VALUE_AT_RISK)"

st.title("💊 MédiRelais")
st.caption("Medication about to expire in our 12 hospitals, and where to send it")
st.caption(f"Data as of {q('SELECT MAX(snapshot_date) AS D FROM MEDIRELAIS.GOLD.GOLD_VALUE_AT_RISK').D[0]}")

# --- Key numbers ---
kpi = q(f"""
    SELECT SUM(value_at_risk_eur)::FLOAT AS AT_RISK, COUNT(*) AS BATCHES
    FROM MEDIRELAIS.GOLD.GOLD_VALUE_AT_RISK
    WHERE {LATEST}
""")
saved = q(f"""
    SELECT COALESCE(SUM(saveable_value_eur), 0)::FLOAT AS SAVED
    FROM MEDIRELAIS.GOLD.GOLD_TRANSFER_SUGGESTIONS
    WHERE {LATEST}
""")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Value expiring in 90 days", f"€{kpi.AT_RISK[0]:,.0f}")
c2.metric("Batches at risk", int(kpi.BATCHES[0]))
c3.metric("Saveable value (what receivers can use before expiry)", f"€{saved.SAVED[0]:,.0f}")
c4.metric("Recovery rate (saveable ÷ at risk)",
          f"{saved.SAVED[0] / kpi.AT_RISK[0]:.0%}" if kpi.AT_RISK[0] else "–")

# --- Data quality of the latest night ---
st.subheader("Data quality (latest night)")
dq = q("SELECT * FROM MEDIRELAIS.GOLD.GOLD_DATA_QUALITY")
q1, q2, q3 = st.columns(3)
q1.metric("Delivery", str(dq.DELIVERY_DATE[0]))
q2.metric("Rows received", int(dq.ROWS_RECEIVED[0]))
q3.metric("Rejected to quarantine", f"{float(dq.REJECT_RATE[0]):.1%}")
if dq.GOLD_BLOCKED[0]:
    st.error("Over 15 %: gold was not refreshed. The figures below are from the last good day.")
else:
    st.success("Quality OK: the figures below are from tonight.")

# --- Use case 1: value at risk by hospital ---
st.subheader("Value at risk by hospital")
risk = q(f"""
    SELECT hospital_name AS HOSPITAL, SUM(value_at_risk_eur)::FLOAT AS VALUE_AT_RISK_EUR
    FROM MEDIRELAIS.GOLD.GOLD_VALUE_AT_RISK
    WHERE {LATEST}
    GROUP BY hospital_name
    ORDER BY VALUE_AT_RISK_EUR DESC
""")
st.bar_chart(risk, x="HOSPITAL", y="VALUE_AT_RISK_EUR")

# --- Use case 1: what to send where ---
st.subheader("Suggested transfers (for the pharmacist)")
st.dataframe(q(f"""
    SELECT priority_rank AS PRIORITY, product_name AS PRODUCT, from_hospital AS FROM_HOSPITAL,
           to_hospital AS TO_HOSPITAL, qty_on_hand AS QTY, days_to_expiry AS DAYS_LEFT,
           ROUND(share_usable_before_expiry * 100) AS PCT_USABLE_IN_TIME,
           saveable_value_eur::FLOAT AS SAVEABLE_EUR, is_national_shortage AS SHORTAGE_IN_FRANCE
    FROM MEDIRELAIS.GOLD.GOLD_TRANSFER_SUGGESTIONS
    WHERE {LATEST}
    ORDER BY PRIORITY
"""), use_container_width=True)

# --- Use case 1: cold-chain batches, never transferred ---
st.subheader("Not transferable: cold-chain batches")
st.caption("Cold-chain products (insulin, vaccines...) stay at their hospital: we have no fridge data "
           "to prove they stayed between 2 and 8 °C. Use them first or warn the prescribers.")
st.dataframe(q(f"""
    SELECT hospital_name AS HOSPITAL, product_name AS PRODUCT, qty_on_hand AS QTY,
           value_at_risk_eur::FLOAT AS VALUE_EUR, days_to_expiry AS DAYS_LEFT
    FROM MEDIRELAIS.GOLD.GOLD_VALUE_AT_RISK
    WHERE transfer_block_reason = 'no_cold_chain_proof' AND {LATEST}
    ORDER BY VALUE_EUR DESC
"""), use_container_width=True)

# --- Use case 2: over-stock alerts ---
st.subheader("Over-stock alerts (for the buyer)")
st.caption("Some of this stock will expire before it is used: stop ordering these")
st.dataframe(q(f"""
    SELECT hospital_name AS HOSPITAL, product_name AS PRODUCT,
           avg_daily_use::FLOAT AS DAILY_USE,
           days_of_cover::FLOAT AS DAYS_OF_STOCK, min_days_to_expiry AS DAYS_BEFORE_EXPIRY,
           overstock_value_eur::FLOAT AS OVERSTOCK_VALUE_EUR
    FROM MEDIRELAIS.GOLD.GOLD_DAYS_OF_COVER
    WHERE is_overstock_alert AND {LATEST}
    ORDER BY OVERSTOCK_VALUE_EUR DESC
"""), use_container_width=True)
