import streamlit as st
from snowflake.snowpark.context import get_active_session

session = get_active_session()

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
    SELECT COALESCE(SUM(value_at_risk_eur), 0)::FLOAT AS SAVED
    FROM MEDIRELAIS.GOLD.GOLD_TRANSFER_SUGGESTIONS
    WHERE can_use_before_expiry AND {LATEST}
""")
c1, c2, c3 = st.columns(3)
c1.metric("Value expiring in 90 days", f"€{kpi.AT_RISK[0]:,.0f}")
c2.metric("Batches at risk", int(kpi.BATCHES[0]))
c3.metric("Saveable value (transfers usable in time)", f"€{saved.SAVED[0]:,.0f}")

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
    SELECT product_name AS PRODUCT, from_hospital AS FROM_HOSPITAL, to_hospital AS TO_HOSPITAL,
           qty_on_hand AS QTY, value_at_risk_eur::FLOAT AS VALUE_EUR,
           days_to_expiry AS DAYS_LEFT, can_use_before_expiry AS CAN_USE_IN_TIME
    FROM MEDIRELAIS.GOLD.GOLD_TRANSFER_SUGGESTIONS
    WHERE {LATEST}
    ORDER BY VALUE_EUR DESC
"""), use_container_width=True)

# --- Use case 1: cold-chain batches waiting for temperature proof ---
st.subheader("Blocked: cold-chain batches without temperature proof")
st.caption("Cold-chain products can only move with proof they stayed between 2 and 8 °C")
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
           days_of_cover::FLOAT AS DAYS_OF_STOCK, min_days_to_expiry AS DAYS_BEFORE_EXPIRY
    FROM MEDIRELAIS.GOLD.GOLD_DAYS_OF_COVER
    WHERE is_overstock_alert AND {LATEST}
    ORDER BY DAYS_OF_STOCK DESC
"""), use_container_width=True)
