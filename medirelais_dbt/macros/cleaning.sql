-- Cleaning helpers for the all-text bronze tables.
-- The hospital systems write the same value in several ways (see ingestion/generate_sources.py):
-- these macros turn every known spelling into one clean value, or NULL when it cannot be read.
-- A NULL is never dropped silently: the *_checked models send the row to quarantine with a reason.

-- " h03 " -> "H03"
{% macro clean_code(column) -%}
    UPPER(TRIM({{ column }}))
{%- endmacro %}

-- "  120 ", "120 units" -> 120 ; "N/A", "null", "-", "" -> NULL
{% macro clean_quantity(column) -%}
    TRY_TO_NUMBER(REGEXP_REPLACE(TRIM({{ column }}), '[ ]*units?$', ''))
{%- endmacro %}

-- "2026-10-28", "28/10/2026", "20261028", "28 Oct 2026" -> 2026-10-28 ; "31/31/2026", "soon" -> NULL
{% macro clean_date(column) -%}
    COALESCE(
        TRY_TO_DATE(TRIM({{ column }}), 'YYYY-MM-DD'),
        TRY_TO_DATE(TRIM({{ column }}), 'DD/MM/YYYY'),
        TRY_TO_DATE(TRIM({{ column }}), 'YYYYMMDD'),
        TRY_TO_DATE(TRIM({{ column }}), 'DD MON YYYY'))
{%- endmacro %}

-- A legacy "default" date such as 2099-01-01 parses fine but means "unknown"
{% macro is_placeholder_date(column) -%}
    (YEAR({{ column }}) >= 2099)
{%- endmacro %}

-- "Paracétamol", "HÉPARINE sodique" -> "PARACETAMOL", "HEPARINE SODIQUE"
-- (upper case without accents, so a substance is compared the same way in every file)
{% macro normalize_text(column) -%}
    TRANSLATE(UPPER(TRIM({{ column }})), 'ÀÂÄÁÃÉÈÊËÍÌÎÏÓÒÔÖÕÚÙÛÜÇÑ', 'AAAAAEEEEIIIIOOOOOUUUUCN')
{%- endmacro %}

-- TRUE when the keyword appears as a whole word (or words) in the text: "HEPARINE" matches
-- "HEPARINE SODIQUE" but not "ENOXAPARINE" - both sides are normalized first
{% macro contains_word(text, keyword) -%}
    REGEXP_LIKE({{ normalize_text(text) }}, '(.*[^A-Z])?' || {{ keyword }} || '([^A-Z].*)?')
{%- endmacro %}
