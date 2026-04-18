import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

st.set_page_config(page_title="Retirement Audit App", layout="wide")

# --------------------------------------------------
# Styling
# --------------------------------------------------
st.markdown("""
    <style>
    .stApp {
        background-color: #0e1117;
        color: white;
        font-size: 17px;
    }

    .stMarkdown, .stText, label, p, div, span {
        color: white !important;
        font-size: 17px !important;
    }

    h1 {
        font-size: 2.3rem !important;
    }

    h2 {
        font-size: 1.8rem !important;
    }

    h3 {
        font-size: 1.4rem !important;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 12px;
        margin-bottom: 12px;
    }

    .stTabs [data-baseweb="tab"] {
        background-color: transparent;
        border: 1px solid #6c757d;
        border-radius: 10px;
        padding: 10px 18px;
        color: white;
        font-size: 16px;
    }

    .stTabs [aria-selected="true"] {
        background-color: #1f2a36 !important;
        border: 1px solid #9fb3c8 !important;
    }

    .stCheckbox label {
        font-size: 16px !important;
        font-weight: 600;
    }

    .stCaption {
        font-size: 14px !important;
        color: #c9d1d9 !important;
    }

    hr {
        border-color: #3a3f4b;
    }
    </style>
    """, unsafe_allow_html=True)

# --------------------------------------------------
# Helper functions
# --------------------------------------------------
def get_ira_limits(age: int):
    base_limit = 7500
    catch_up = 1100 if age >= 50 else 0
    total_limit = base_limit + catch_up
    return base_limit, catch_up, total_limit

def get_401k_limits(age: int):
    base_limit = 24500
    if 60 <= age <= 63:
        catch_up = 11250
    elif age >= 50:
        catch_up = 8000
    else:
        catch_up = 0
    total_limit = base_limit + catch_up
    return base_limit, catch_up, total_limit

def get_hsa_limit(age: int, coverage_type: str):
    base_limit = 4400 if coverage_type == "Self-only" else 8750
    catch_up = 1000 if age >= 55 else 0
    total_limit = base_limit + catch_up
    return base_limit, catch_up, total_limit

def estimate_ss_pia(avg_annual_earnings):
    """
    Simplified estimate:
    Uses avg annual earnings / 12 as a proxy for AIME.
    2026 PIA bend points:
      90% of first $1,286
      32% of next amount up to $7,749
      15% above $7,749
    Returns annual estimate at FRA.
    """
    if avg_annual_earnings <= 0:
        return 0

    aime = avg_annual_earnings / 12
    bend1 = 1286
    bend2 = 7749

    pia_monthly = (
        min(aime, bend1) * 0.90
        + max(0, min(aime - bend1, bend2 - bend1)) * 0.32
        + max(0, aime - bend2) * 0.15
    )

    pia_monthly = np.floor(pia_monthly * 10) / 10  # truncate to lower dime
    return round(pia_monthly * 12)

def future_value(balance, annual_contrib, annual_rate, years):
    if years <= 0:
        return balance
    if annual_rate == 0:
        return balance + annual_contrib * years

    return (
        balance * (1 + annual_rate) ** years
        + annual_contrib * (((1 + annual_rate) ** years - 1) / annual_rate)
    )

def amortization_schedule(principal, annual_rate, monthly_payment, extra_monthly=0.0, max_months=1200):
    """
    Returns a dictionary with balances over time and payoff stats.
    Handles final partial payment correctly.
    """
    principal = float(principal)
    annual_rate = float(annual_rate)
    monthly_payment = float(monthly_payment)
    extra_monthly = float(extra_monthly)

    if principal <= 0:
        return {
            "amortizes": True,
            "months": 0,
            "interest": 0.0,
            "balances": [0.0]
        }

    monthly_rate = annual_rate / 12
    balance = principal
    total_interest = 0.0
    month = 0
    balances = [balance]

    while balance > 0.005 and month < max_months:
        interest = balance * monthly_rate
        scheduled_payment = monthly_payment + extra_monthly
        actual_payment = min(scheduled_payment, balance + interest)
        principal_payment = actual_payment - interest

        if principal_payment <= 0:
            return {
                "amortizes": False,
                "months": None,
                "interest": total_interest,
                "balances": balances
            }

        balance = max(balance - principal_payment, 0.0)
        total_interest += interest
        month += 1
        balances.append(balance)

    if month >= max_months and balance > 0.005:
        return {
            "amortizes": False,
            "months": None,
            "interest": total_interest,
            "balances": balances
        }

    return {
        "amortizes": True,
        "months": month,
        "interest": total_interest,
        "balances": balances
    }

def projected_mortgage_balance(schedule_balances, years_from_now):
    month_index = int(years_from_now * 12)
    if not schedule_balances:
        return 0.0
    if month_index >= len(schedule_balances):
        return 0.0
    return schedule_balances[month_index]

# --------------------------------------------------
# Header
# --------------------------------------------------
st.title("Retirement Audit App 🚀")
st.subheader("Retirement Audit - Accounts, Home Equity & Retirement Income")

retirement_age = st.slider("Preferred Retirement Age", 50, 80, 65, 1)

tab1, tab2, tab3 = st.tabs(["Spouse 1 / Primary", "Spouse 2 / Partner", "Retirement Income"])

accounts = {"spouse1": {}, "spouse2": {}}

# --------------------------------------------------
# Spouse tabs - investment accounts
# --------------------------------------------------
for spouse, tab in [("spouse1", tab1), ("spouse2", tab2)]:
    with tab:
        display_name = "Spouse 1 / Primary" if spouse == "spouse1" else "Spouse 2 / Partner"
        st.markdown(f"### {display_name}")

        spouse_age = st.number_input(
            "Current Age",
            min_value=18,
            max_value=retirement_age,
            value=30,
            key=f"{spouse}_age"
        )

        ira_base, ira_catch, ira_total_limit = get_ira_limits(spouse_age)
        k401_base, k401_catch, k401_total_limit = get_401k_limits(spouse_age)

        st.caption(
            f"2026 IRA limit: ${ira_base:,}"
            + (f" + ${ira_catch:,} catch-up" if ira_catch > 0 else "")
            + f" = ${ira_total_limit:,} total"
        )
        st.caption(
            f"2026 401(k) employee deferral limit: ${k401_base:,}"
            + (f" + ${k401_catch:,} catch-up" if k401_catch > 0 else "")
            + f" = ${k401_total_limit:,} total"
        )

        col_l, col_r = st.columns(2)

        selected_any = False

        with col_l:
            use_traditional_ira = st.checkbox(
                "Include Traditional IRA",
                value=False,
                key=f"{spouse}_use_traditional_ira"
            )
            if use_traditional_ira:
                selected_any = True
                st.markdown("**Traditional IRA**")
                accounts[spouse]["traditional_ira"] = {
                    "balance": st.number_input(
                        "Current Balance ($)",
                        min_value=0.0,
                        value=0.0,
                        format="%.0f",
                        key=f"{spouse}_trad_ira_bal"
                    ),
                    "contrib": st.number_input(
                        "Annual Contribution ($)",
                        min_value=0.0,
                        value=0.0,
                        format="%.0f",
                        key=f"{spouse}_trad_ira_cont"
                    ),
                    "rate": st.slider(
                        "Expected Growth Rate (%)",
                        min_value=0.0,
                        max_value=20.0,
                        value=7.0,
                        step=0.1,
                        key=f"{spouse}_trad_ira_rate"
                    )
                }

            use_roth_ira = st.checkbox(
                "Include Roth IRA",
                value=False,
                key=f"{spouse}_use_roth_ira"
            )
            if use_roth_ira:
                selected_any = True
                st.markdown("**Roth IRA**")
                accounts[spouse]["roth_ira"] = {
                    "balance": st.number_input(
                        "Current Roth Balance ($)",
                        min_value=0.0,
                        value=0.0,
                        format="%.0f",
                        key=f"{spouse}_roth_bal"
                    ),
                    "contrib": st.number_input(
                        "Annual Roth Contribution ($)",
                        min_value=0.0,
                        value=0.0,
                        format="%.0f",
                        key=f"{spouse}_roth_cont"
                    ),
                    "rate": st.slider(
                        "Expected Growth Rate (%)",
                        min_value=0.0,
                        max_value=20.0,
                        value=7.0,
                        step=0.1,
                        key=f"{spouse}_roth_rate"
                    )
                }

            use_hsa = st.checkbox(
                "Include HSA",
                value=False,
                key=f"{spouse}_use_hsa"
            )
            if use_hsa:
                selected_any = True
                st.markdown("**HSA**")
                hsa_coverage = st.selectbox(
                    "HSA Coverage Type",
                    options=["Self-only", "Family"],
                    key=f"{spouse}_hsa_coverage"
                )
                hsa_base, hsa_catch, hsa_total_limit = get_hsa_limit(spouse_age, hsa_coverage)
                st.caption(
                    f"2026 HSA limit: ${hsa_base:,}"
                    + (f" + ${hsa_catch:,} catch-up" if hsa_catch > 0 else "")
                    + f" = ${hsa_total_limit:,} total"
                )
                accounts[spouse]["hsa"] = {
                    "balance": st.number_input(
                        "Current HSA Balance ($)",
                        min_value=0.0,
                        value=0.0,
                        format="%.0f",
                        key=f"{spouse}_hsa_bal"
                    ),
                    "contrib": st.number_input(
                        "Annual HSA Contribution ($)",
                        min_value=0.0,
                        value=0.0,
                        format="%.0f",
                        key=f"{spouse}_hsa_cont"
                    ),
                    "rate": st.slider(
                        "Expected Growth Rate (%)",
                        min_value=0.0,
                        max_value=20.0,
                        value=6.5,
                        step=0.1,
                        key=f"{spouse}_hsa_rate"
                    ),
                    "coverage": hsa_coverage,
                    "limit": hsa_total_limit
                }

        with col_r:
            use_traditional_401k = st.checkbox(
                "Include Traditional 401(k)",
                value=False,
                key=f"{spouse}_use_traditional_401k"
            )
            if use_traditional_401k:
                selected_any = True
                st.markdown("**Traditional 401(k)**")
                st.caption("Employer match is always Traditional and does not count toward your elective deferral limit.")
                accounts[spouse]["traditional_401k"] = {
                    "balance": st.number_input(
                        "Current Balance ($)",
                        min_value=0.0,
                        value=0.0,
                        format="%.0f",
                        key=f"{spouse}_trad_401k_bal"
                    ),
                    "contrib": st.number_input(
                        "Your Annual Contribution ($)",
                        min_value=0.0,
                        value=0.0,
                        format="%.0f",
                        key=f"{spouse}_trad_401k_cont"
                    ),
                    "employer_match": st.number_input(
                        "Employer Match ($)",
                        min_value=0.0,
                        value=0.0,
                        format="%.0f",
                        key=f"{spouse}_trad_401k_match"
                    ),
                    "rate": st.slider(
                        "Expected Growth Rate (%)",
                        min_value=0.0,
                        max_value=20.0,
                        value=7.0,
                        step=0.1,
                        key=f"{spouse}_trad_401k_rate"
                    )
                }

            use_roth_401k = st.checkbox(
                "Include Roth 401(k)",
                value=False,
                key=f"{spouse}_use_roth_401k"
            )
            if use_roth_401k:
                selected_any = True
                st.markdown("**Roth 401(k)**")
                accounts[spouse]["roth_401k"] = {
                    "balance": st.number_input(
                        "Current Balance ($)",
                        min_value=0.0,
                        value=0.0,
                        format="%.0f",
                        key=f"{spouse}_roth_401k_bal"
                    ),
                    "contrib": st.number_input(
                        "Your Annual Contribution ($)",
                        min_value=0.0,
                        value=0.0,
                        format="%.0f",
                        key=f"{spouse}_roth_401k_cont"
                    ),
                    "rate": st.slider(
                        "Expected Growth Rate (%)",
                        min_value=0.0,
                        max_value=20.0,
                        value=7.0,
                        step=0.1,
                        key=f"{spouse}_roth_401k_rate"
                    )
                }

            use_brokerage = st.checkbox(
                "Include Brokerage / Taxable",
                value=False,
                key=f"{spouse}_use_brokerage"
            )
            if use_brokerage:
                selected_any = True
                st.markdown("**Brokerage / Taxable**")
                accounts[spouse]["brokerage"] = {
                    "balance": st.number_input(
                        "Current Balance ($)",
                        min_value=0.0,
                        value=0.0,
                        format="%.0f",
                        key=f"{spouse}_brok_bal"
                    ),
                    "contrib": st.number_input(
                        "Annual Contribution ($)",
                        min_value=0.0,
                        value=0.0,
                        format="%.0f",
                        key=f"{spouse}_brok_cont"
                    ),
                    "rate": st.slider(
                        "Expected Growth Rate (%)",
                        min_value=0.0,
                        max_value=20.0,
                        value=6.5,
                        step=0.1,
                        key=f"{spouse}_brok_rate"
                    )
                }

        if not selected_any:
            st.info("Select the accounts you want to use to begin.")

        ira_total_entered = (
            accounts[spouse].get("traditional_ira", {}).get("contrib", 0.0)
            + accounts[spouse].get("roth_ira", {}).get("contrib", 0.0)
        )
        if ira_total_entered > ira_total_limit:
            st.warning(
                f"Combined Traditional IRA + Roth IRA contributions are ${ira_total_entered:,.0f}, "
                f"which is above the 2026 combined IRA limit of ${ira_total_limit:,.0f} for this age."
            )

        k401_total_entered = (
            accounts[spouse].get("traditional_401k", {}).get("contrib", 0.0)
            + accounts[spouse].get("roth_401k", {}).get("contrib", 0.0)
        )
        if k401_total_entered > k401_total_limit:
            st.warning(
                f"Combined Traditional 401(k) + Roth 401(k) employee contributions are ${k401_total_entered:,.0f}, "
                f"which is above the 2026 elective deferral limit of ${k401_total_limit:,.0f} for this age."
            )

        if "hsa" in accounts[spouse]:
            hsa_limit = accounts[spouse]["hsa"].get("limit", 0.0)
            hsa_entered = accounts[spouse]["hsa"].get("contrib", 0.0)
            if hsa_entered > hsa_limit:
                st.warning(
                    f"HSA contribution is ${hsa_entered:,.0f}, which is above the 2026 HSA limit of "
                    f"${hsa_limit:,.0f} for that age and coverage type."
                )

# --------------------------------------------------
# Retirement income tab
# --------------------------------------------------
with tab3:
    st.markdown("### Income Sources in Retirement")

    st.subheader("Social Security Estimator")
    st.markdown(
        "Enter average annual earnings for a rough estimate of annual Social Security at Full Retirement Age (typically 67)."
    )

    col_est1, col_est2 = st.columns(2)
    with col_est1:
        avg_annual_earnings_sp1 = st.number_input(
            "Spouse 1 Average Annual Earnings ($)",
            min_value=0,
            max_value=300000,
            value=60000,
            step=1000,
            key="avg_earn_sp1"
        )
    with col_est2:
        avg_annual_earnings_sp2 = st.number_input(
            "Spouse 2 Average Annual Earnings ($)",
            min_value=0,
            max_value=300000,
            value=0,
            step=1000,
            key="avg_earn_sp2"
        )

    est_ss_sp1 = estimate_ss_pia(avg_annual_earnings_sp1)
    est_ss_sp2 = estimate_ss_pia(avg_annual_earnings_sp2)

    col_ss_metric1, col_ss_metric2 = st.columns(2)
    with col_ss_metric1:
        st.metric("Estimated Annual SS at FRA - Spouse 1", f"${est_ss_sp1:,.0f}")
    with col_ss_metric2:
        st.metric("Estimated Annual SS at FRA - Spouse 2", f"${est_ss_sp2:,.0f}")

    st.info(
        "This is a simplified estimate using the 2026 PIA formula. Actual benefits depend on your 35 highest indexed earnings years, "
        "inflation adjustments, and your claiming age. For your exact estimate, use ssa.gov/myaccount."
    )

    use_manual_ss = st.checkbox(
        "Use Social Security manual inputs / override",
        value=False,
        key="use_manual_ss"
    )

    if use_manual_ss:
        st.subheader("Social Security - Manual Inputs / Override")
        col_ss1, col_ss2 = st.columns(2)
        with col_ss1:
            ss_start_sp1 = st.slider("Claim Age - Spouse 1", 62, 70, 67, key="ss_start_sp1")
            ss_annual_sp1 = st.number_input(
                "Annual SS at Claim Age - Spouse 1 ($)",
                min_value=0,
                max_value=100000,
                value=int(est_ss_sp1),
                step=1000,
                key="ss_ann_sp1"
            )
        with col_ss2:
            ss_start_sp2 = st.slider("Claim Age - Spouse 2", 62, 70, 67, key="ss_start_sp2")
            ss_annual_sp2 = st.number_input(
                "Annual SS at Claim Age - Spouse 2 ($)",
                min_value=0,
                max_value=100000,
                value=int(est_ss_sp2),
                step=1000,
                key="ss_ann_sp2"
            )
    else:
        ss_start_sp1 = 67
        ss_start_sp2 = 67
        ss_annual_sp1 = est_ss_sp1
        ss_annual_sp2 = est_ss_sp2

    use_pension = st.checkbox(
        "Include Pension / Defined Benefit",
        value=False,
        key="use_pension"
    )

    if use_pension:
        st.markdown("### Pension / Defined Benefit")
        col_pen1, col_pen2 = st.columns(2)
        with col_pen1:
            pension_annual_sp1 = st.number_input(
                "Annual Pension - Spouse 1 ($)",
                min_value=0,
                value=0,
                step=1000,
                key="pen_sp1"
            )
            pension_cola_sp1 = st.slider(
                "Pension COLA % - Spouse 1",
                min_value=0.0,
                max_value=5.0,
                value=2.0,
                step=0.1,
                key="pen_cola_sp1"
            ) / 100
        with col_pen2:
            pension_annual_sp2 = st.number_input(
                "Annual Pension - Spouse 2 ($)",
                min_value=0,
                value=0,
                step=1000,
                key="pen_sp2"
            )
            pension_cola_sp2 = st.slider(
                "Pension COLA % - Spouse 2",
                min_value=0.0,
                max_value=5.0,
                value=2.0,
                step=0.1,
                key="pen_cola_sp2"
            ) / 100
    else:
        pension_annual_sp1 = 0
        pension_cola_sp1 = 0.0
        pension_annual_sp2 = 0
        pension_cola_sp2 = 0.0

# --------------------------------------------------
# Home equity section
# --------------------------------------------------
st.markdown("---")
st.subheader("Home Equity")

use_home_equity = st.checkbox(
    "Include Home Equity section",
    value=False,
    key="use_home_equity"
)

if use_home_equity:
    home_value = st.number_input(
        "Current Home Value ($)",
        min_value=0.0,
        value=0.0,
        format="%.0f"
    )
    mortgage_balance = st.number_input(
        "Remaining Mortgage ($)",
        min_value=0.0,
        value=0.0,
        format="%.0f"
    )
    home_appreciation = st.slider(
        "Annual Home Appreciation (%)",
        min_value=0.0,
        max_value=10.0,
        value=3.0,
        step=0.1
    ) / 100
    include_home = st.checkbox(
        "Include Home Equity in Graph & Net Worth",
        value=True
    )
else:
    home_value = 0.0
    mortgage_balance = 0.0
    home_appreciation = 0.0
    include_home = False

# --------------------------------------------------
# Mortgage payoff section
# --------------------------------------------------
st.markdown("---")
st.subheader("Mortgage Payoff Calculator")

use_mortgage_calc = st.checkbox(
    "Include Mortgage Payoff Calculator",
    value=False,
    key="use_mortgage_calc"
)

mort_principal = float(mortgage_balance)
mort_rate_pct = 6.5
mort_rate_annual = mort_rate_pct / 100
mort_years = 30
monthly_payment = 1500.0
extra_monthly = 0.0

schedule_no_extra = {"amortizes": False, "months": None, "interest": 0.0, "balances": [mort_principal]}
schedule_with_extra = {"amortizes": False, "months": None, "interest": 0.0, "balances": [mort_principal]}

if use_mortgage_calc:
    mort_principal = st.number_input(
        "Current Mortgage Balance ($)",
        min_value=0.0,
        value=float(mortgage_balance),
        format="%.2f"
    )
    mort_rate_pct = st.number_input(
        "Annual Interest Rate (%)",
        min_value=0.0,
        max_value=20.0,
        value=6.5,
        step=0.125
    )
    mort_rate_annual = mort_rate_pct / 100
    mort_years = st.number_input(
        "Remaining Term (Years)",
        min_value=1,
        max_value=40,
        value=30,
        step=1
    )
    monthly_payment = st.number_input(
        "Standard Monthly Payment ($)",
        min_value=0.0,
        value=1500.0,
        format="%.2f"
    )
    extra_monthly = st.number_input(
        "Extra Monthly Payment ($)",
        min_value=0.0,
        value=0.0,
        format="%.2f"
    )

    schedule_no_extra = amortization_schedule(
        principal=mort_principal,
        annual_rate=mort_rate_annual,
        monthly_payment=monthly_payment,
        extra_monthly=0.0
    )
    schedule_with_extra = amortization_schedule(
        principal=mort_principal,
        annual_rate=mort_rate_annual,
        monthly_payment=monthly_payment,
        extra_monthly=extra_monthly
    )

    if not schedule_no_extra["amortizes"]:
        st.error("The standard monthly payment is too low to amortize this mortgage.")
    else:
        date_no = datetime.now() + timedelta(days=schedule_no_extra["months"] * 30)

        if schedule_with_extra["amortizes"]:
            date_yes = datetime.now() + timedelta(days=schedule_with_extra["months"] * 30)
            savings = schedule_no_extra["interest"] - schedule_with_extra["interest"]

            col1, col2, col3 = st.columns(3)
            col1.metric("Payoff Date (no extra)", date_no.strftime("%b %Y"))
            col2.metric("Payoff Date (with extra)", date_yes.strftime("%b %Y"))
            col3.metric("Interest Savings", f"${savings:,.2f}")
        else:
            col1, col2 = st.columns(2)
            col1.metric("Payoff Date (no extra)", date_no.strftime("%b %Y"))
            col2.warning("Extra-payment scenario does not amortize with the values entered.")

# --------------------------------------------------
# Retirement projections
# --------------------------------------------------
total_invest = 0.0
max_years = 0

for spouse in accounts:
    current_age = st.session_state.get(f"{spouse}_age", 30)
    years_to_retirement = max(retirement_age - current_age, 0)
    max_years = max(max_years, years_to_retirement)

    for _, acc in accounts[spouse].items():
        annual_contrib = acc.get("contrib", 0.0) + acc.get("employer_match", 0.0)
        annual_rate = acc.get("rate", 7.0) / 100
        projected = future_value(
            balance=acc.get("balance", 0.0),
            annual_contrib=annual_contrib,
            annual_rate=annual_rate,
            years=years_to_retirement
        )
        total_invest += projected

# Use mortgage payoff schedule to estimate future balance if available.
if include_home:
    home_proj_value = home_value * (1 + home_appreciation) ** max_years

    if use_mortgage_calc and schedule_no_extra["amortizes"]:
        mortgage_balance_at_retirement = projected_mortgage_balance(
            schedule_no_extra["balances"],
            max_years
        )
    else:
        mortgage_balance_at_retirement = mortgage_balance

    home_proj_equity = max(home_proj_value - mortgage_balance_at_retirement, 0.0)
else:
    home_proj_value = 0.0
    mortgage_balance_at_retirement = 0.0
    home_proj_equity = 0.0

total_nw = total_invest + (home_proj_equity if include_home else 0.0)

st.markdown(f"### Projected at Age {retirement_age}")
c1, c2, c3 = st.columns(3)
c1.metric("Investments Total", f"${total_invest:,.0f}")
c2.metric("Home Equity", f"${home_proj_equity:,.0f}" if include_home else "$0")
c3.metric("Total Net Worth", f"${total_nw:,.0f}")

if include_home and use_mortgage_calc and schedule_no_extra["amortizes"]:
    st.caption(
        f"Projected home equity uses mortgage paydown over time. Estimated mortgage balance at retirement: "
        f"${mortgage_balance_at_retirement:,.0f}"
    )
elif include_home and not use_mortgage_calc and mortgage_balance > 0:
    st.caption(
        "Tip: turn on the Mortgage Payoff Calculator if you want projected home equity to reflect mortgage paydown over time."
    )

# --------------------------------------------------
# Growth graph
# --------------------------------------------------
st.subheader("Growth Over Time")
years_arr = np.arange(0, max_years + 6)

invest_growth = np.zeros(len(years_arr))
home_growth = np.zeros(len(years_arr))

for y_idx, y in enumerate(years_arr):
    for spouse in accounts:
        current_age = st.session_state.get(f"{spouse}_age", 30)
        years_to_retirement = max(retirement_age - current_age, 0)
        effective_years = min(y, years_to_retirement)

        for _, acc in accounts[spouse].items():
            annual_contrib = acc.get("contrib", 0.0) + acc.get("employer_match", 0.0)
            annual_rate = acc.get("rate", 7.0) / 100
            balance = acc.get("balance", 0.0)

            invest_growth[y_idx] += future_value(
                balance=balance,
                annual_contrib=annual_contrib,
                annual_rate=annual_rate,
                years=effective_years
            )

    if include_home:
        future_home_value = home_value * (1 + home_appreciation) ** y
        if use_mortgage_calc and schedule_no_extra["amortizes"]:
            future_mortgage_balance = projected_mortgage_balance(schedule_no_extra["balances"], y)
        else:
            future_mortgage_balance = mortgage_balance
        home_growth[y_idx] = max(future_home_value - future_mortgage_balance, 0.0)

total_growth = invest_growth + (home_growth if include_home else 0.0)

fig, ax = plt.subplots(figsize=(12, 6))
ax.plot(years_arr, invest_growth, label="Investments", linewidth=3)
if include_home:
    ax.plot(years_arr, home_growth, label="Home Equity", linewidth=3)
ax.plot(years_arr, total_growth, label="Total Net Worth", linewidth=4, linestyle="--")
ax.set_xlabel("Years from Now")
ax.set_ylabel("Value ($)")
ax.legend()
ax.grid(True, alpha=0.3)
st.pyplot(fig)

# --------------------------------------------------
# Retirement withdrawal simulation
# --------------------------------------------------
st.markdown("---")
st.subheader("Retirement Withdrawal Simulation")

wd_rate_pct = st.slider(
    "Annual Withdrawal Rate from Investments (%)",
    min_value=3.0,
    max_value=12.0,
    value=4.5,
    step=0.1,
    help="Lower rates are generally safer for longer retirements."
)
wd_rate = wd_rate_pct / 100

post_growth_pct = st.slider(
    "Expected Annual Portfolio Growth in Retirement (%)",
    min_value=0.0,
    max_value=12.0,
    value=6.0,
    step=0.1,
    help="This replaces the old hardcoded 10% assumption."
)
post_growth = post_growth_pct / 100

wd_years_max = 60
starting_balance = invest_growth[max_years] if len(invest_growth) > max_years else invest_growth[-1]

if starting_balance <= 0:
    st.warning("No investments projected at retirement — can't simulate withdrawals.")
else:
    annual_wd = starting_balance * wd_rate
    st.write(
        f"**First-year withdrawal from investments:** ${annual_wd:,.0f} "
        f"({wd_rate_pct:.1f}% of starting balance)"
    )

    years_post = np.arange(0, wd_years_max + 1)
    balances = [starting_balance]
    depleted_year = None

    for y in range(1, len(years_post)):
        new_bal = balances[-1] * (1 + post_growth) - annual_wd
        if new_bal <= 0:
            depleted_year = y
            balances.append(0.0)
            break
        balances.append(new_bal)

    if depleted_year is None:
        depleted_year = wd_years_max + 1
        while len(balances) < len(years_post):
            balances.append(balances[-1])

    fig_wd, ax_wd = plt.subplots(figsize=(12, 6))
    ax_wd.plot(
        years_post[:len(balances)],
        balances,
        label="Portfolio Balance",
        linewidth=3
    )
    ax_wd.axhline(starting_balance, linestyle="--", label="Starting Balance")
    if depleted_year <= wd_years_max:
        ax_wd.axvline(depleted_year, linestyle="--", label="Depletion Point")
    ax_wd.set_xlabel("Years in Retirement")
    ax_wd.set_ylabel("Balance ($)")
    ax_wd.set_title(f"Withdrawal at {wd_rate_pct:.1f}% - {post_growth_pct:.1f}% Annual Growth")
    ax_wd.legend()
    ax_wd.grid(True, alpha=0.3)
    st.pyplot(fig_wd)

    if depleted_year > 40:
        st.success(
            "Your portfolio is projected to last **more than 40 years** with money still remaining at the end."
        )
    elif depleted_year > 30:
        st.success(
            f"Your portfolio is projected to last **{depleted_year} years** — enough for a standard 30-year retirement with some buffer."
        )
    elif depleted_year > 25:
        st.info(
            f"Your portfolio is projected to last **about {depleted_year} years** — covers most 30-year retirements but with limited margin for error."
        )
    elif depleted_year > 20:
        st.warning(
            f"Your portfolio is projected to last only **{depleted_year} years** — it may run out before a full 30-year retirement."
        )
    else:
        st.error(
            f"Your portfolio is projected to deplete in just **{depleted_year} years** — this is a high-risk withdrawal plan."
        )

    st.markdown(f"""
    **Important notes on withdrawal rates:**
    - This simulation now uses your chosen retirement growth assumption of **{post_growth_pct:.1f}%** instead of a fixed 10%.
    - Lower withdrawal rates are generally safer than higher ones.
    - This is still a simplified model. It does **not** include market volatility, inflation-adjusted withdrawals, taxes, or sequence-of-returns risk.
    """)

# --------------------------------------------------
# Fun section
# --------------------------------------------------
st.markdown("---")
name = st.text_input("What's your name?")
if name:
    st.write(f"Hello, {name}! Keep building — you're doing great.")
if st.button("Encouragement"):
    st.balloons()

