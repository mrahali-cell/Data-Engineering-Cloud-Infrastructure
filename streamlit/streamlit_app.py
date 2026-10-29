import streamlit as st
from snowflake.snowpark.context import get_active_session

session = get_active_session()

def q(sql):
    return session.sql(sql).to_pandas()

st.title("💊 MédiRelais")
st.caption("Medication about to expire in our 12 hospitals, and where to send it")

# --- Key numbers ---
kpi = q("""
    SELECT SUM(value_at_risk_eur)::FLOAT AS AT_RISK, COUNT(*) AS BATCHES
    FROM MEDIRELAIS.GOLD.GOLD_VALUE_AT_RISK
""")
saved = q("""
    SELECT COALESCE(SUM(value_at_risk_eur), 0)::FLOAT AS SAVED
    FROM MEDIRELAIS.GOLD.GOLD_TRANSFER_SUGGESTIONS
    WHERE can_use_before_expiry
""")
c1, c2, c3 = st.columns(3)
c1.metric("Value expiring in 90 days", f"€{kpi.AT_RISK[0]:,.0f}")
c2.metric("Batches at risk", int(kpi.BATCHES[0]))
c3.metric("Value we can save by transfer", f"€{saved.SAVED[0]:,.0f}")

# --- Use case 1: value at risk by hospital ---
st.subheader("Value at risk by hospital")
risk = q("""
    SELECT hospital_name AS HOSPITAL, SUM(value_at_risk_eur)::FLOAT AS VALUE_AT_RISK_EUR
    FROM MEDIRELAIS.GOLD.GOLD_VALUE_AT_RISK
    GROUP BY hospital_name
    ORDER BY VALUE_AT_RISK_EUR DESC
""")
st.bar_chart(risk, x="HOSPITAL", y="VALUE_AT_RISK_EUR")

# --- Use case 1: what to send where ---
st.subheader("Suggested transfers (for the pharmacist)")
st.dataframe(q("""
    SELECT product_name AS PRODUCT, from_hospital AS FROM_HOSPITAL, to_hospital AS TO_HOSPITAL,
           qty_on_hand AS QTY, value_at_risk_eur::FLOAT AS VALUE_EUR,
           days_to_expiry AS DAYS_LEFT, can_use_before_expiry AS CAN_USE_IN_TIME
    FROM MEDIRELAIS.GOLD.GOLD_TRANSFER_SUGGESTIONS
    ORDER BY VALUE_EUR DESC
"""), use_container_width=True)

# --- Use case 2: over-stock alerts ---
st.subheader("Over-stock alerts (for the buyer)")
st.caption("Stock lasts longer than its shelf life: stop ordering these")
st.dataframe(q("""
    SELECT hospital_name AS HOSPITAL, product_name AS PRODUCT,
           days_of_cover::FLOAT AS DAYS_OF_STOCK, min_days_to_expiry AS DAYS_BEFORE_EXPIRY
    FROM MEDIRELAIS.GOLD.GOLD_DAYS_OF_COVER
    WHERE is_overstock_alert
    ORDER BY DAYS_OF_STOCK DESC
"""), use_container_width=True)
