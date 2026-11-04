import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import traceback

# --- Page Config ---
st.set_page_config(page_title="FPライフプランシミュレータ", layout="wide")

# --- CSS Styling ---
st.markdown("""
<style>
    /* 既存のカードデザイン設定 */
    .metric-card { background-color: #f8f9fa; border-radius: 10px; padding: 15px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); text-align: center; }
    .metric-title { font-size: 1.1rem; font-weight: 600; color: #495057; margin-bottom: 5px; }
    .metric-value { font-size: 2rem; font-weight: 700; color: #007bff; }
    .metric-value.red { color: #dc3545; }

    /* 追加：右上のメニュー（GitHub情報など）とフッターを非表示にする */
    [data-testid="stHeader"] { visibility: hidden; }
    [data-testid="stToolbar"] { visibility: hidden; }
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# --- Data & Constants ---
EDU_COST = {
    "幼稚園(公立)": 23, "幼稚園(私立)": 53,
    "小学校(公立)": 35, "小学校(私立)": 166,
    "中学校(公立)": 50, "中学校(私立)": 143,
    "高校(公立)": 46,   "高校(私立)": 103,
    "大学(国公立)": 125, "大学(私立文系)": 175, "大学(私立理系)": 212
}

INCOME_TAX_BRACKETS = [
    (1950000, 0.05, 0),
    (3300000, 0.10, 97500),
    (6950000, 0.20, 427500),
    (9000000, 0.23, 636000),
    (17999000, 0.33, 1536000),
    (39999000, 0.40, 2796000),
    (float('inf'), 0.45, 4796000)
]

# --- Helper Functions ---
def calc_income_tax(taxable_income):
    if taxable_income <= 0: return 0
    for limit, rate, deduction in INCOME_TAX_BRACKETS:
        if taxable_income <= limit:
            return (taxable_income * rate - deduction) * 1.021 
    return 0

def calc_salary_deduction(salary):
    if salary <= 0: return 0
    if salary <= 1625000: return 550000
    elif salary <= 1800000: return salary * 0.4 - 100000
    elif salary <= 3600000: return salary * 0.3 + 80000
    elif salary <= 6600000: return salary * 0.2 + 440000
    elif salary <= 8500000: return salary * 0.1 + 1100000
    else: return 1950000

def calc_tax_and_soc(salary, pension, other_misc_income=0, prev_salary=0, prev_pension=0, prev_other_misc_income=0, ideco_deduction=0, fam_deduction=0, age=40, pp_ded_inc=0, pp_ded_res=0, life_ded_inc=0, life_ded_res=0, is_working=True):
    if is_working and salary > 0:
        pension_ins = min(salary, 7800000) * 0.0915
        health_rate = 0.0581 if 40 <= age < 65 else 0.0500
        health_ins = min(salary, 16680000) * health_rate
        emp_ins = salary * 0.006
        soc_ins_salary = pension_ins + health_ins + emp_ins
    else:
        if pension > 0:
            soc_ins_salary = 0 
        else:
            if 20 <= age < 60:
                nh_ins = min(prev_salary * 0.05, 800000) if prev_salary > 0 else 50000
                soc_ins_salary = 200000 + nh_ins
            elif 60 <= age < 75:
                nh_ins = min(prev_salary * 0.05, 800000) if prev_salary > 0 else 50000
                soc_ins_salary = nh_ins
            else:
                soc_ins_salary = 0
                
    soc_ins_pension = pension * 0.10 if pension > 0 else 0 
    soc_ins = soc_ins_salary + soc_ins_pension
    
    employment_income_current = max(0, salary - calc_salary_deduction(salary))
    pension_deduction_current = (1100000 if age >= 65 else 600000) if pension > 0 else 0
    public_pension_income_current = max(0, pension - pension_deduction_current)
    
    total_income_current = employment_income_current + public_pension_income_current + other_misc_income
    
    taxable_income_inc = max(0, total_income_current - soc_ins - 480000 - ideco_deduction - pp_ded_inc - life_ded_inc - fam_deduction)
    income_tax = calc_income_tax(taxable_income_inc)
    
    employment_income_prev = max(0, prev_salary - calc_salary_deduction(prev_salary))
    pension_deduction_prev = (1100000 if (age - 1) >= 65 else 600000) if prev_pension > 0 else 0
    public_pension_income_prev = max(0, prev_pension - pension_deduction_prev)
    
    total_income_prev = employment_income_prev + public_pension_income_prev + prev_other_misc_income
    
    fam_deduction_res = fam_deduction * (330000 / 380000) if fam_deduction > 0 else 0
    
    taxable_income_res = max(0, total_income_prev - soc_ins - 430000 - ideco_deduction - pp_ded_res - life_ded_res - fam_deduction_res)
    resident_tax = taxable_income_res * 0.10
    
    return soc_ins, income_tax, resident_tax

def calc_mortgage_pmt(principal, rate, years):
    if years == 0 or rate == 0: return 0
    r = rate / 12
    n = years * 12
    return (principal * r * ((1+r)**n) / (((1+r)**n) - 1)) * 12
    
def calc_loan_balance(principal, rate, years, current_year):
    if current_year >= years: return 0
    if rate == 0: return principal * (1 - current_year/years)
    r = rate / 12
    n = years * 12
    current_month = current_year * 12
    balance = principal * (((1+r)**n - (1+r)**current_month) / ((1+r)**n - 1))
    return max(0, balance)

def generate_mortgage_schedule(principal, initial_rate, total_years, rate_up_year=1000, rate_up_rate=0.0):
    """金利変更シナリオに対応した住宅ローンの各年の返済額と残高を計算して配列で返す"""
    schedule_pmt = np.zeros(total_years)
    schedule_balance = np.zeros(total_years)
    balance = principal
    current_rate = initial_rate
    
    for y in range(total_years):
        if y == rate_up_year:
            current_rate = rate_up_rate
            
        if balance <= 0:
            schedule_pmt[y] = 0
            schedule_balance[y] = 0
            continue
            
        if current_rate == 0:
            pmt = balance / (total_years - y)
            schedule_pmt[y] = pmt
            balance -= pmt
            schedule_balance[y] = max(0, balance)
        else:
            r = current_rate / 12
            n = (total_years - y) * 12
            pmt_monthly = (balance * r * ((1+r)**n) / (((1+r)**n) - 1)) if n > 0 else balance
            pmt_annual = pmt_monthly * 12
            schedule_pmt[y] = pmt_annual
            
            # 月ごとの元本減少を1年分進める
            for _ in range(12):
                interest = balance * r
                principal_payment = pmt_monthly - interest
                balance -= principal_payment
            schedule_balance[y] = max(0, balance)
            
    return schedule_pmt, schedule_balance

def get_ret_deduction(years):
    if years <= 20: return max(800000, 400000 * max(1, years))
    else: return 8000000 + 700000 * (years - 20)

def calc_ret_tax(gross_amount, years, prior_deduction=0):
    deduction = get_ret_deduction(years)
    net_deduction = max(0, deduction - prior_deduction) 
    taxable = max(0, (gross_amount - net_deduction) / 2)
    inc_tax = calc_income_tax(taxable)
    res_tax = taxable * 0.10
    return inc_tax, res_tax, net_deduction

def calc_pension_amount(base_amount, start_age):
    if start_age == 65: return base_amount
    elif start_age > 65: return base_amount * (1 + 0.007 * ((start_age - 65) * 12))
    else: return base_amount * (1 - 0.004 * ((65 - start_age) * 12))

def calc_fv(monthly_pmt, annual_rate, years):
    if annual_rate == 0: return monthly_pmt * 12 * years
    r_month = annual_rate / 12
    months = years * 12
    return monthly_pmt * (((1 + r_month)**months - 1) / r_month)

def calc_fv_lump(lump_sum, annual_rate, years):
    return lump_sum * ((1 + annual_rate)**years)

def calc_payout_annual(principal, annual_rate, years):
    if annual_rate == 0 or years <= 0: return principal / years if years > 0 else 0
    return principal * (annual_rate / (1 - (1 + annual_rate)**-years))

# --- Plotting Functions ---
def plot_asset_transition(ages, balances_savings, balances_nisa, balances_taxable, balances_ideco_dc, arr_debt_housing, arr_debt_car, arr_debt_reform, arr_debt_edu, arr_annual_balance):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=ages, y=balances_savings/10000, name="世帯 預貯金", marker_color='#2ca02c', hovertemplate='%{y:.1f}万円'), secondary_y=False)
    fig.add_trace(go.Bar(x=ages, y=balances_nisa/10000, name="世帯 NISA", marker_color='#ff7f0e', hovertemplate='%{y:.1f}万円'), secondary_y=False)
    fig.add_trace(go.Bar(x=ages, y=balances_taxable/10000, name="世帯 特定口座", marker_color='#1f77b4', hovertemplate='%{y:.1f}万円'), secondary_y=False)
    fig.add_trace(go.Bar(x=ages, y=balances_ideco_dc/10000, name="世帯 iDeCo/DC", marker_color='#9467bd', hovertemplate='%{y:.1f}万円'), secondary_y=False)

    if arr_debt_housing.sum() > 0:
        fig.add_trace(go.Bar(x=ages, y=-arr_debt_housing/10000, name="住宅ローン残高", marker_color='#7f7f7f', base=0, hovertemplate='住宅ローン: %{y:.1f}万円'), secondary_y=False)
    if arr_debt_car.sum() > 0:
        fig.add_trace(go.Bar(x=ages, y=-arr_debt_car/10000, name="自動車ローン残高(世帯)", marker_color='#bcbd22', base=0, hovertemplate='自動車ローン: %{y:.1f}万円'), secondary_y=False)
    if arr_debt_reform.sum() > 0:
        fig.add_trace(go.Bar(x=ages, y=-arr_debt_reform/10000, name="リフォームローン残高", marker_color='#e377c2', base=0, hovertemplate='リフォームローン: %{y:.1f}万円'), secondary_y=False)
    if arr_debt_edu.sum() > 0:
        fig.add_trace(go.Bar(x=ages, y=-arr_debt_edu/10000, name="教育ローン残高", marker_color='#17becf', base=0, hovertemplate='教育ローン: %{y:.1f}万円'), secondary_y=False)

    fig.add_trace(go.Scatter(x=ages, y=arr_annual_balance/10000, name="世帯単年収支(右軸)", mode='lines', line=dict(color='#d62728', width=3, dash='dot'), hovertemplate='%{y:.1f}万円'), secondary_y=True)

    fig.update_layout(barmode='relative', hovermode="x unified", height=500, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    return fig

def plot_cashflow_breakdown(ages, years_count, arr_salary, arr_sp_salary, arr_pension, arr_child_allowance, arr_leave_benefit, arr_ret_income, arr_sp_pension, arr_withdrawal_amount, arr_exp_base, arr_exp_event, arr_exp_house, arr_exp_edu, arr_exp_car, arr_exp_nursing, arr_soc_ins, arr_sp_soc_ins, arr_inc_tax, arr_sp_inc_tax, arr_res_tax, arr_sp_res_tax, arr_ret_inc_tax, arr_ret_res_tax, arr_lump_sum_income):
    fig = go.Figure()

    base_inc = np.zeros(years_count)
    y_sal = arr_salary/10000
    fig.add_trace(go.Bar(x=ages, y=y_sal, name="本人 給与収入", offsetgroup=1, base=base_inc, customdata=y_sal, marker_color='#1f77b4', hovertemplate='%{customdata:.1f}万円'))
    base_inc += y_sal

    y_sp_sal = arr_sp_salary/10000
    fig.add_trace(go.Bar(x=ages, y=y_sp_sal, name="配偶者 給与収入", offsetgroup=1, base=base_inc, customdata=y_sp_sal, marker_color='#76b7b2', hovertemplate='%{customdata:.1f}万円'))
    base_inc += y_sp_sal

    y_pen = arr_pension/10000
    fig.add_trace(go.Bar(x=ages, y=y_pen, name="本人 年金・保険等(加給含)", offsetgroup=1, base=base_inc, customdata=y_pen, marker_color='#2ca02c', hovertemplate='%{customdata:.1f}万円'))
    base_inc += y_pen
    
    y_ret = arr_ret_income/10000
    fig.add_trace(go.Bar(x=ages, y=y_ret, name="退職金(手取り)", offsetgroup=1, base=base_inc, customdata=y_ret, marker_color='#17becf', hovertemplate='%{customdata:.1f}万円'))
    base_inc += y_ret

    y_leave = arr_leave_benefit/10000
    fig.add_trace(go.Bar(x=ages, y=y_leave, name="育休等の給付金(非課税)", offsetgroup=1, base=base_inc, customdata=y_leave, marker_color='#9edae5', hovertemplate='%{customdata:.1f}万円'))
    base_inc += y_leave

    y_child_allowance = arr_child_allowance/10000
    fig.add_trace(go.Bar(x=ages, y=y_child_allowance, name="児童手当", offsetgroup=1, base=base_inc, customdata=y_child_allowance, marker_color='#ff9896', hovertemplate='%{customdata:.1f}万円'))
    base_inc += y_child_allowance
    
    y_lump = arr_lump_sum_income/10000
    fig.add_trace(go.Bar(x=ages, y=y_lump, name="一時収入(iDeCo・車売却等)", offsetgroup=1, base=base_inc, customdata=y_lump, marker_color='#ff7f0e', hovertemplate='%{customdata:.1f}万円'))
    base_inc += y_lump

    y_sp_pen = arr_sp_pension/10000
    fig.add_trace(go.Bar(x=ages, y=y_sp_pen, name="配偶者 年金・iDeCo等", offsetgroup=1, base=base_inc, customdata=y_sp_pen, marker_color='#98df8a', hovertemplate='%{customdata:.1f}万円'))
    base_inc += y_sp_pen

    y_with = arr_withdrawal_amount/10000
    fig.add_trace(go.Bar(x=ages, y=y_with, name="資産取り崩し(世帯)", offsetgroup=1, base=base_inc, customdata=y_with, marker_color='#e377c2', hovertemplate='%{customdata:.1f}万円'))

    base_exp = np.zeros(years_count)
    y_base = arr_exp_base/10000
    fig.add_trace(go.Bar(x=ages, y=y_base, name="基本生活費・保険料", offsetgroup=2, base=base_exp, customdata=y_base, marker_color='#d62728', hovertemplate='%{customdata:.1f}万円'))
    base_exp += y_base

    y_event = arr_exp_event/10000
    fig.add_trace(go.Bar(x=ages, y=y_event, name="特別支出(イベント)", offsetgroup=2, base=base_exp, customdata=y_event, marker_color='#ffbb78', hovertemplate='%{customdata:.1f}万円'))
    base_exp += y_event

    y_house = arr_exp_house/10000
    fig.add_trace(go.Bar(x=ages, y=y_house, name="住宅費", offsetgroup=2, base=base_exp, customdata=y_house, marker_color='#8c564b', hovertemplate='%{customdata:.1f}万円'))
    base_exp += y_house

    y_edu = arr_exp_edu/10000
    fig.add_trace(go.Bar(x=ages, y=y_edu, name="教育費", offsetgroup=2, base=base_exp, customdata=y_edu, marker_color='#bcbd22', hovertemplate='%{customdata:.1f}万円'))
    base_exp += y_edu

    y_car = arr_exp_car/10000
    fig.add_trace(go.Bar(x=ages, y=y_car, name="自動車費(世帯)", offsetgroup=2, base=base_exp, customdata=y_car, marker_color='#7f7f7f', hovertemplate='%{customdata:.1f}万円'))
    base_exp += y_car

    y_nursing = arr_exp_nursing/10000
    fig.add_trace(go.Bar(x=ages, y=y_nursing, name="老人ホーム費用(世帯)", offsetgroup=2, base=base_exp, customdata=y_nursing, marker_color='#c49c94', hovertemplate='%{customdata:.1f}万円'))
    base_exp += y_nursing

    y_soc = arr_soc_ins/10000
    fig.add_trace(go.Bar(x=ages, y=y_soc, name="本人 社会保険料", offsetgroup=2, base=base_exp, customdata=y_soc, marker_color='#ff7f0e', hovertemplate='%{customdata:.1f}万円'))
    base_exp += y_soc

    y_sp_soc = arr_sp_soc_ins/10000
    fig.add_trace(go.Bar(x=ages, y=y_sp_soc, name="配偶者 社会保険料", offsetgroup=2, base=base_exp, customdata=y_sp_soc, marker_color='#ffbb78', hovertemplate='%{customdata:.1f}万円'))
    base_exp += y_sp_soc

    y_inc_tax = arr_inc_tax/10000
    fig.add_trace(go.Bar(x=ages, y=y_inc_tax, name="本人 所得税", offsetgroup=2, base=base_exp, customdata=y_inc_tax, marker_color='#9467bd', hovertemplate='%{customdata:.1f}万円'))
    base_exp += y_inc_tax

    y_sp_inc_tax = arr_sp_inc_tax/10000
    fig.add_trace(go.Bar(x=ages, y=y_sp_inc_tax, name="配偶者 所得税", offsetgroup=2, base=base_exp, customdata=y_sp_inc_tax, marker_color='#c5b0d5', hovertemplate='%{customdata:.1f}万円'))
    base_exp += y_sp_inc_tax

    y_res_tax = arr_res_tax/10000
    fig.add_trace(go.Bar(x=ages, y=y_res_tax, name="本人 住民税", offsetgroup=2, base=base_exp, customdata=y_res_tax, marker_color='#17becf', hovertemplate='%{customdata:.1f}万円'))
    base_exp += y_res_tax

    y_sp_res_tax = arr_sp_res_tax/10000
    fig.add_trace(go.Bar(x=ages, y=y_sp_res_tax, name="配偶者 住民税", offsetgroup=2, base=base_exp, customdata=y_sp_res_tax, marker_color='#9edae5', hovertemplate='%{customdata:.1f}万円'))
    base_exp += y_sp_res_tax

    y_ret_tax = (arr_ret_inc_tax + arr_ret_res_tax) / 10000
    fig.add_trace(go.Bar(x=ages, y=y_ret_tax, name="退職関連税(世帯)", offsetgroup=2, base=base_exp, customdata=y_ret_tax, marker_color='#000000', hovertemplate='%{customdata:.1f}万円'))

    fig.update_layout(barmode='group', hovermode="x unified", height=650, legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5))
    return fig

# --- UI Inputs ---
st.title("📊 FPライフプランシミュレータ")

tabs = st.tabs(["1. 本人", "2. 配偶者", "3. 家族・教育", "4. 住宅・車", "5. 資産・運用", "6. 年金・保険", "7. その他", "8. 老人ホーム"])

with tabs[0]:
    st.header("本人の基本・収入・退職")
    col1, col2 = st.columns(2)
    with col1:
        current_age = st.slider("現在の年齢", 20, 80, 40)
        life_expectancy = st.slider("シミュレーション終了年齢", 80, 110, 95)
        employment_start_age = st.slider("入社(就業開始)年齢", 15, 65, 22)
        is_working = st.radio("現在の就業状況(本人)", ["就業中（給与収入あり）", "既に退職済み（早期リタイア等）"])
    
    with col2:
        if is_working == "就業中（給与収入あり）":
            gross_income = st.number_input("現在の額面年収（万円）", value=600, step=1) * 10000
            salary_growth = st.slider("毎年の昇給率 (%)", 0.0, 5.0, 1.0) / 100
            has_salary_decrease = st.checkbox("役職定年等による給与減額あり(本人)")
            if has_salary_decrease:
                salary_decrease_age = st.slider("減額される年齢", current_age, 85, 55)
                salary_decrease_rate = st.slider("減額率 (%)", 10, 80, 30) / 100
            else:
                salary_decrease_age = 1000
                salary_decrease_rate = 0.0
                
            retirement_age = st.slider("退職予定年齢(会社の退職金)", current_age, 100, 60)
            retirement_allowance = st.number_input("会社の退職金見込額（万円）", value=1500, step=1) * 10000
            actual_is_working = True
        else:
            gross_income = 0
            salary_growth = 0
            salary_decrease_age = 1000
            salary_decrease_rate = 0.0
            retirement_age = st.slider("退職した年齢(退職金受給済の場合は現在の年齢)", 20, current_age, current_age)
            retirement_allowance = st.number_input("これから受け取る予定の退職金（既に受取済・なしの場合は0）", value=0, step=1) * 10000
            actual_is_working = False
            
    st.divider()
    has_post_retirement_job = st.checkbox("退職後のアルバイト・副業収入あり(本人)")
    if has_post_retirement_job:
        post_retirement_income = st.number_input("退職後の収入(万円/月)", value=10, step=1) * 10000
        post_retirement_end_age = st.slider("退職後の収入が続く年齢(本人)", retirement_age, 100, max(retirement_age, 65))
    else:
        post_retirement_income = 0
        post_retirement_end_age = 0

with tabs[1]:
    st.header("配偶者の基本・収入・退職")
    has_marriage = st.checkbox("配偶者あり")
    if has_marriage:
        col1, col2 = st.columns(2)
        with col1:
            sp_age_diff = st.slider("配偶者との年齢差(年下ならマイナス)", -20, 20, 0)
            marriage_age = st.slider("結婚する本人の年齢(結婚済みなら現在年齢以下)", 20, 80, current_age)
            wedding_cost = st.number_input("結婚式等費用（万円）", value=300, step=1) * 10000
            sp_employment_start_age = st.slider("配偶者の入社(就業開始)年齢", 15, 65, 22)
            sp_working_status = st.radio("現在の就業状況(配偶者)", ["就業中（給与収入あり）", "非就業・退職済み（専業主婦/夫等）"])
            
        with col2:
            if sp_working_status == "就業中（給与収入あり）":
                sp_gross_income = st.number_input("配偶者の現在の額面年収（万円）", value=300, step=1) * 10000
                sp_salary_growth = st.slider("配偶者の毎年の昇給率 (%)", 0.0, 5.0, 1.0) / 100
                has_sp_salary_decrease = st.checkbox("役職定年等による給与減額あり(配偶者)")
                if has_sp_salary_decrease:
                    sp_salary_decrease_age = st.slider("配偶者が減額される年齢", current_age + sp_age_diff, 85, 55)
                    sp_salary_decrease_rate = st.slider("配偶者の減額率 (%)", 10, 80, 30) / 100
                else:
                    sp_salary_decrease_age = 1000
                    sp_salary_decrease_rate = 0.0
                    
                sp_retirement_age = st.slider("配偶者の退職予定年齢", current_age + sp_age_diff, 100, 60)
                sp_retirement_allowance = st.number_input("配偶者の会社退職金見込額（万円）", value=500, step=1) * 10000
                actual_sp_working = True
            else:
                sp_gross_income = 0
                sp_salary_growth = 0
                sp_salary_decrease_age = 1000
                sp_salary_decrease_rate = 0.0
                sp_retirement_age = st.slider("配偶者の退職した年齢(受取済の場合は現在の年齢)", 20, current_age + sp_age_diff, current_age + sp_age_diff)
                sp_retirement_allowance = st.number_input("配偶者のこれから受け取る予定の退職金（受取済・なしは0）", value=0, step=1) * 10000
                actual_sp_working = False
        
        st.divider()
        has_sp_post_retirement_job = st.checkbox("退職後のアルバイト・副業収入あり(配偶者)")
        if has_sp_post_retirement_job:
            sp_post_retirement_income = st.number_input("配偶者の退職後収入(万円/月)", value=8, step=1) * 10000
            sp_post_retirement_end_age = st.slider("配偶者の退職後収入が続く年齢", sp_retirement_age, 100, max(sp_retirement_age, 65))
        else:
            sp_post_retirement_income = 0
            sp_post_retirement_end_age = 0
    else:
        sp_age_diff = marriage_age = wedding_cost = sp_gross_income = sp_salary_growth = 0
        sp_employment_start_age = 22
        sp_salary_decrease_age = 1000
        sp_salary_decrease_rate = 0.0
        sp_retirement_age = sp_retirement_allowance = 0
        has_sp_post_retirement_job = False
        sp_post_retirement_income = 0
        sp_post_retirement_end_age = 0
        actual_sp_working = False

with tabs[2]:
    st.header("家族・教育費")
    receive_child_allowance = st.checkbox("児童手当（こども手当）を受給する", value=True)
    num_children = st.slider("子どもの人数", 0, 4, 0)
    child_settings = []
    
    if num_children > 0:
        child_cols = st.columns(num_children)
        for i in range(num_children):
            with child_cols[i]:
                st.markdown(f"**第{i+1}子**")
                child_status = st.radio(f"第{i+1}子の状況", ["これから生まれる", "既に生まれている"], key=f"status_{i}")
                
                if child_status == "これから生まれる":
                    c_birth_age = st.slider(f"誕生時の本人の年齢", current_age, 80, current_age + 2 + (i*2), key=f"future_age_{i}")
                    
                    st.markdown("**産休・育休の取得予定**")
                    take_leave_main = st.checkbox("本人が取得する", key=f"leave_main_ck_{i}")
                    leave_months_main = st.slider("本人の取得期間(ヶ月)", 1, 24, 12, key=f"leave_mon_main_{i}") if take_leave_main else 0
                        
                    take_leave_sp = st.checkbox("配偶者が取得する", key=f"leave_sp_ck_{i}") if has_marriage else False
                    leave_months_sp = st.slider("配偶者の取得期間(ヶ月)", 1, 24, 12, key=f"leave_mon_sp_{i}") if take_leave_sp else 0
                else:
                    c_current_age = st.slider(f"第{i+1}子の現在の年齢", 0, 30, 5, key=f"current_c_age_{i}")
                    c_birth_age = current_age - c_current_age
                    st.caption(f"（逆算：本人が{c_birth_age}歳の時の子ども）")
                    leave_months_main = 0
                    leave_months_sp = 0
                    
                c_kind = st.selectbox(f"幼稚園", ["公立", "私立"], key=f"k_{i}")
                c_elem = st.selectbox(f"小学校", ["公立", "私立"], key=f"e_{i}")
                c_mid = st.selectbox(f"中学校", ["公立", "私立"], key=f"m_{i}")
                c_high = st.selectbox(f"高校", ["公立", "私立"], key=f"h_{i}")
                c_uni = st.selectbox(f"大学", ["国公立", "私立文系", "私立理系", "なし"], key=f"u_{i}")
                
                if c_uni != "なし":
                    st.markdown(f"**大学時代の仕送り支援**")
                    has_uni_support = st.checkbox("仕送りを行う", key=f"usup_{i}")
                    if has_uni_support:
                        uni_rent_support = st.number_input(f"家賃仕送り(万円/月)", value=5, step=1, key=f"urent_{i}") * 10000
                        uni_living_support = st.number_input(f"生活費仕送り(万円/月)", value=5, step=1, key=f"uliv_{i}") * 10000
                    else:
                        uni_rent_support = 0
                        uni_living_support = 0
                else:
                    has_uni_support = False
                    uni_rent_support = 0
                    uni_living_support = 0
                
                child_settings.append({
                    "birth_age": c_birth_age,
                    "leave_main": leave_months_main,
                    "leave_sp": leave_months_sp,
                    "course": [(4,6,f"幼稚園({c_kind})"), (7,12,f"小学校({c_elem})"), 
                               (13,15,f"中学校({c_mid})"), (16,18,f"高校({c_high})"),
                               (19,22,f"大学({c_uni})" if c_uni != "なし" else None)],
                    "uni_support": {"active": has_uni_support, "rent": uni_rent_support, "living": uni_living_support}
                })
        
    st.divider()
    use_edu_loan = st.checkbox("教育費にローン(奨学金等)を利用する")
    if use_edu_loan:
        edu_loan_rate = st.slider("教育ローン・奨学金 金利(%)", 0.0, 5.0, 2.0) / 100
        edu_loan_years = st.slider("教育ローン 返済期間(年)", 1, 20, 10)
    else:
        edu_loan_rate = edu_loan_years = 0

with tabs[3]:
    st.header("住宅・車")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("住居設定")
        housing_type = st.radio("現在の住居形態", ["賃貸", "持ち家"])
        if housing_type == "賃貸":
            rent_annual = st.number_input("現在の家賃・管理費等(万円/年)", value=120, step=1) * 10000
            rent_renewal_years = st.slider("家賃の更新周期 (年)", 1, 10, 2)
            rent_renewal_fee_months = st.slider("更新料 (新家賃の何ヶ月分)", 0.0, 3.0, 1.0, 0.5)
            
            use_rent_inflation = st.checkbox("更新時の家賃インフレ(値上げ)を考慮する")
            if use_rent_inflation:
                rent_inflation_rate = st.slider("家賃のインフレ率 (年換算 %)", 0.0, 5.0, 1.0) / 100
            else:
                rent_inflation_rate = 0.0
                
            has_existing_mortgage = False
            ex_housing_loan_balance = ex_housing_loan_years_remaining = ex_housing_loan_rate = 0
            ex_housing_rate_up_years = 1000
            ex_housing_rate_up_rate = 0.0
            has_ex_mortgage_deduction = False
            ex_mortgage_deduction_rate = ex_mortgage_deduction_years_remaining = ex_mortgage_deduction_max = 0
        else:
            has_existing_mortgage = st.checkbox("現在返済中の住宅ローンあり", value=False)
            if has_existing_mortgage:
                ex_housing_loan_balance = st.number_input("現在の住宅ローン残高（万円）", value=2000, step=10) * 10000
                ex_housing_loan_years_remaining = st.slider("残りの返済期間（年）", 1, 50, 20)
                ex_housing_loan_type = st.radio("現在の金利タイプ", ["固定金利", "変動金利"], key="ex_loan_type")
                ex_housing_loan_rate = st.slider("現在の適用金利 (%)", 0.1, 5.0, 0.5, key="ex_loan_rate") / 100
                if ex_housing_loan_type == "変動金利":
                    st.markdown("**将来の金利上昇シナリオ**")
                    ex_housing_rate_up_years = st.slider("何年後に金利が上昇するか", 1, ex_housing_loan_years_remaining, 5, key="ex_rate_up_y")
                    ex_housing_rate_up_rate = st.slider("上昇後の金利 (%)", 0.1, 5.0, 1.5, key="ex_rate_up_r") / 100
                else:
                    ex_housing_rate_up_years = 1000
                    ex_housing_rate_up_rate = 0.0
                
                has_ex_mortgage_deduction = st.checkbox("住宅ローン控除を現在利用している", value=True)
                if has_ex_mortgage_deduction:
                    ex_mortgage_deduction_rate = st.slider("既存ローンの控除率 (%)", 0.1, 1.0, 0.7, key="ex_ded_rate") / 100
                    ex_mortgage_deduction_years_remaining = st.slider("既存ローンの残り控除期間 (年)", 1, 13, 10)
                    ex_mortgage_deduction_max = st.number_input("既存ローンの借入限度額（万円）", value=3000, step=100, key="ex_ded_max") * 10000
                else:
                    ex_mortgage_deduction_rate = ex_mortgage_deduction_years_remaining = ex_mortgage_deduction_max = 0
            else:
                ex_housing_loan_balance = ex_housing_loan_years_remaining = ex_housing_loan_rate = 0
                ex_housing_rate_up_years = 1000
                ex_housing_rate_up_rate = 0.0
                has_ex_mortgage_deduction = False
                ex_mortgage_deduction_rate = ex_mortgage_deduction_years_remaining = ex_mortgage_deduction_max = 0

            rent_annual = rent_inflation_rate = 0
            rent_renewal_years = 1
            rent_renewal_fee_months = 0

        has_housing = st.checkbox("将来の住宅購入予定あり", value=False)
        if has_housing:
            housing_purchase_age = st.slider("住宅購入する本人の年齢", current_age, 90, current_age + 3)
            housing_loan_amount = st.number_input("住宅借入額（万円）", value=3000, step=10) * 10000
            housing_loan_type = st.radio("新規ローンの金利タイプ", ["固定金利", "変動金利"], key="new_loan_type")
            housing_loan_rate = st.slider("新規ローン金利 (%)", 0.1, 5.0, 1.0, key="new_loan_rate") / 100
            housing_loan_years = st.slider("新規ローン返済期間（年）", 10, 50, 35)
            
            if housing_loan_type == "変動金利":
                st.markdown("**将来の金利上昇シナリオ**")
                housing_rate_up_years = st.slider("借入から何年後に金利が上昇するか", 1, housing_loan_years, 5, key="new_rate_up_y")
                housing_rate_up_rate = st.slider("上昇後の新規ローン金利 (%)", 0.1, 5.0, 2.0, key="new_rate_up_r") / 100
            else:
                housing_rate_up_years = 1000
                housing_rate_up_rate = 0.0

            housing_down_payment = st.number_input("頭金・諸費用（万円）", value=500, step=10) * 10000
            housing_maint = st.number_input("固定資産税・火災保険等(万円/年)", value=20, step=1) * 10000
            has_mortgage_deduction = st.checkbox("住宅ローン控除を利用する", value=True, key="new_ded_chk")
            if has_mortgage_deduction:
                mortgage_deduction_rate = st.slider("新規控除率 (%)", 0.1, 1.0, 0.7, key="new_ded_rate") / 100
                mortgage_deduction_years = st.slider("新規控除期間 (年)", 10, 13, 13, key="new_ded_years")
                mortgage_deduction_max = st.number_input("新規借入限度額（万円）", value=3000, step=100, key="new_ded_max") * 10000
            else:
                mortgage_deduction_rate = mortgage_deduction_years = mortgage_deduction_max = 0
        else:
            housing_purchase_age = housing_loan_amount = housing_loan_rate = housing_loan_years = housing_down_payment = housing_maint = 0
            housing_rate_up_years = 1000
            housing_rate_up_rate = 0.0
            has_mortgage_deduction = False
            mortgage_deduction_rate = mortgage_deduction_years = mortgage_deduction_max = 0

        has_reform = st.checkbox("住宅のリフォーム予定あり")
        if has_reform:
            reform_age = st.slider("リフォームする本人の年齢", current_age, 100, current_age + 15)
            reform_cost = st.number_input("リフォーム費用(万円)", value=300, step=1) * 10000
            use_reform_loan = st.checkbox("リフォームにローンを利用する")
            if use_reform_loan:
                reform_loan_rate = st.slider("リフォームローン金利(%)", 0.1, 5.0, 2.0) / 100
                reform_loan_years = st.slider("リフォームローン返済期間(年)", 1, 20, 10)
            else:
                reform_loan_rate = reform_loan_years = 0
        else:
            reform_age = reform_cost = 0
            use_reform_loan = False
            reform_loan_rate = reform_loan_years = 0

    with col2:
        st.subheader("自動車設定（本人）")
        has_car = st.checkbox("本人用の車の所有・購入あり", value=False)
        if has_car:
            car_first_purchase_age = st.slider("次回購入する本人の年齢", current_age, 90, current_age)
            car_first_purchase_cost = st.number_input("次回の購入費用（万円）", value=300, step=1) * 10000
            car_replace_cycle = st.slider("買い替え周期（年）", 3, 20, 7)
            car_replace_cost = st.number_input("それ以降の買い替え費用（万円）", value=200, step=1) * 10000
            car_loan_use = st.checkbox("自動車購入時にローンを利用する", key="car_loan_main")
            if car_loan_use:
                car_loan_rate = st.slider("自動車ローン金利(%)", 0.1, 10.0, 2.0) / 100
                car_loan_years = st.slider("自動車ローン返済期間(年)", 1, 10, 5)
            else:
                car_loan_rate = car_loan_years = 0
            car_last_purchase_age = st.slider("最後に車を買い替える年齢(本人)", 60, 100, 75)
            car_dispose_age = st.slider("車を手放す(免返等)年齢(本人)", car_last_purchase_age, 100, min(100, car_last_purchase_age + 10))
            car_sale_price = st.number_input("最後に手放す際の売却見込額(万円)", value=50, step=1) * 10000
            car_maint_annual = st.number_input("年間維持費(駐車場等含)（万円/年）", value=30, step=1) * 10000
        else:
            car_first_purchase_age = car_first_purchase_cost = car_replace_cycle = car_replace_cost = car_last_purchase_age = car_dispose_age = car_maint_annual = 0
            car_loan_use = False
            car_loan_rate = car_loan_years = car_sale_price = 0
            
        st.markdown("---")
        st.subheader("自動車設定（配偶者）")
        if has_marriage:
            sp_has_car = st.checkbox("配偶者用の車の所有・購入あり", value=False)
            if sp_has_car:
                sp_car_first_purchase_age = st.slider("次回購入する配偶者の年齢", current_age + sp_age_diff, 90, current_age + sp_age_diff)
                sp_car_first_purchase_cost = st.number_input("次回の配偶者の購入費用（万円）", value=200, step=1) * 10000
                sp_car_replace_cycle = st.slider("配偶者の買い替え周期（年）", 3, 20, 7)
                sp_car_replace_cost = st.number_input("それ以降の配偶者の買い替え費用（万円）", value=150, step=1) * 10000
                sp_car_loan_use = st.checkbox("配偶者の自動車購入時にローンを利用する", key="car_loan_sp")
                if sp_car_loan_use:
                    sp_car_loan_rate = st.slider("配偶者の自動車ローン金利(%)", 0.1, 10.0, 2.0) / 100
                    sp_car_loan_years = st.slider("配偶者の自動車ローン返済期間(年)", 1, 10, 5)
                else:
                    sp_car_loan_rate = sp_car_loan_years = 0
                sp_car_last_purchase_age = st.slider("最後に車を買い替える年齢(配偶者)", 60, 100, 75)
                sp_car_dispose_age = st.slider("車を手放す年齢(配偶者)", sp_car_last_purchase_age, 100, min(100, sp_car_last_purchase_age + 10))
                sp_car_sale_price = st.number_input("配偶者の最後に手放す際の売却見込額(万円)", value=30, step=1) * 10000
                sp_car_maint_annual = st.number_input("配偶者の年間維持費（万円/年）", value=20, step=1) * 10000
            else:
                sp_car_first_purchase_age = sp_car_first_purchase_cost = sp_car_replace_cycle = sp_car_replace_cost = sp_car_last_purchase_age = sp_car_dispose_age = sp_car_maint_annual = 0
                sp_car_loan_use = False
                sp_car_loan_rate = sp_car_loan_years = sp_car_sale_price = 0
        else:
            sp_has_car = False
            sp_car_first_purchase_age = sp_car_first_purchase_cost = sp_car_replace_cycle = sp_car_replace_cost = sp_car_last_purchase_age = sp_car_dispose_age = sp_car_maint_annual = 0
            sp_car_loan_use = False
            sp_car_loan_rate = sp_car_loan_years = sp_car_sale_price = 0

with tabs[4]:
    st.header("資産・運用・取り崩し")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("本人")
        initial_savings = st.number_input("現在の預貯金(本人・万円)", value=100, step=1) * 10000
        initial_nisa = st.number_input("現在のNISA残高(本人・万円)", value=0, step=1) * 10000
        initial_taxable = st.number_input("現在の特定口座残高(本人・万円)", value=0, step=1) * 10000
        nisa_used_tsumitate = st.number_input("NISA つみたて投資枠利用済額(本人・万円)", value=0, step=1) * 10000
        nisa_used_growth = st.number_input("NISA 成長投資枠利用済額(本人・万円)", value=0, step=1) * 10000
        
        has_investment = st.checkbox("新規の積立投資を行う(本人)", value=True)
        if has_investment:
            invest_monthly = st.number_input("毎月の積立額(本人・万円)", value=5, step=1) * 10000
            invest_end_age = st.slider("積立を終了する本人の年齢", current_age, 100, 60)
            invest_strategy = st.radio("積立の優先順位(本人)", ["NISA優先 (年間360万/生涯1800万上限、超過分は特定口座)", "すべて特定口座へ"])
        else:
            invest_monthly = invest_end_age = 0
            invest_strategy = "すべて特定口座へ"
            
        withdrawal_start_age = st.slider("定率取り崩し開始年齢(本人)", current_age, 100, retirement_age)
        withdrawal_rate_nisa = st.slider("NISA 定率取り崩し率(本人) (%)", 0.0, 10.0, 4.0, 0.5) / 100
        withdrawal_rate_taxable = st.slider("特定口座 定率取り崩し率(本人) (%)", 0.0, 10.0, 4.0, 0.5) / 100

    with col2:
        st.subheader("配偶者")
        if has_marriage:
            sp_initial_savings = st.number_input("現在の預貯金(配偶者・万円)", value=50, step=1) * 10000
            sp_initial_nisa = st.number_input("現在のNISA残高(配偶者・万円)", value=0, step=1) * 10000
            sp_initial_taxable = st.number_input("現在の特定口座残高(配偶者・万円)", value=0, step=1) * 10000
            sp_nisa_used_tsumitate = st.number_input("NISA つみたて利用済額(配偶者・万円)", value=0, step=1) * 10000
            sp_nisa_used_growth = st.number_input("NISA 成長投資枠利用済額(配偶者・万円)", value=0, step=1) * 10000
            
            sp_has_investment = st.checkbox("新規の積立投資を行う(配偶者)", value=False)
            if sp_has_investment:
                sp_invest_monthly = st.number_input("毎月の積立額(配偶者・万円)", value=3, step=1) * 10000
                sp_invest_end_age = st.slider("積立を終了する配偶者の年齢", current_age + sp_age_diff, 100, 60)
                sp_invest_strategy = st.radio("積立の優先順位(配偶者)", ["NISA優先", "すべて特定口座へ"])
            else:
                sp_invest_monthly = sp_invest_end_age = 0
                sp_invest_strategy = "すべて特定口座へ"
                
            sp_withdrawal_start_age = st.slider("定率取り崩し開始年齢(配偶者)", current_age + sp_age_diff, 100, sp_retirement_age)
            sp_withdrawal_rate_nisa = st.slider("NISA 定率取り崩し率(配偶者) (%)", 0.0, 10.0, 4.0, 0.5) / 100
            sp_withdrawal_rate_taxable = st.slider("特定口座 定率取り崩し率(配偶者) (%)", 0.0, 10.0, 4.0, 0.5) / 100
        else:
            sp_initial_savings = sp_initial_nisa = sp_initial_taxable = sp_nisa_used_tsumitate = sp_nisa_used_growth = 0
            sp_has_investment = False
            sp_invest_monthly = sp_invest_end_age = 0
            sp_invest_strategy = "すべて特定口座へ"
            sp_withdrawal_start_age = sp_withdrawal_rate_nisa = sp_withdrawal_rate_taxable = 0

    st.divider()
    nisa_return = st.slider("NISA期待リターン (%)", 0.0, 10.0, 6.0) / 100
    taxable_return_base = st.slider("特定口座ベースリターン (%)", 0.0, 10.0, 6.0) / 100
    st.caption("※簡易計算のため、特定口座の複利運用は毎年課税（税引後リターン適用）されている前提で算出します。")
    min_savings_amount = st.number_input("預貯金の最低維持額(世帯合計・万円)", value=150, step=1) * 10000
    deficit_order = st.selectbox("赤字補填の優先順位", [
        "預貯金を先に限界まで → 特定口座(世帯) → NISA(世帯)",
        "特定口座(世帯) → NISA(世帯) → 預貯金(最低維持額割れ)",
        "NISA(世帯) → 特定口座(世帯) → 預貯金(最低維持額割れ)"
    ], index=0)

with tabs[5]:
    st.header("公的年金・個人年金・保険・iDeCo")
    
    st.subheader("■ 公的年金")
    col_pen1, col_pen2 = st.columns(2)
    with col_pen1:
        st.markdown("**本人の公的年金**")
        pension_base = st.number_input("65歳時の年金見込額(額面・万円)(本人)", value=240, step=1) * 10000
        pension_start_age = st.slider("年金受給開始年齢(本人)", 60, 75, 65)
        
    with col_pen2:
        if has_marriage:
            st.markdown("**配偶者の公的年金**")
            sp_pension_base = st.number_input("65歳時の年金見込額(額面・万円)(配偶者)", value=120, step=1) * 10000
            sp_pension_start_age = st.slider("年金受給開始年齢(配偶者)", 60, 75, 65)
            
            has_kakyu_nenkin = st.checkbox("加給年金の受給あり")
            if has_kakyu_nenkin:
                kakyu_nenkin_amount = st.number_input("加給年金額(万円/年)", value=40, step=1) * 10000
                st.caption("※加給年金とは、厚生年金に20年以上加入している方が65歳に到達した時点において、生計を維持している65歳未満の配偶者がいる場合に加算される手当です。（当シミュレータでは、配偶者が年上の場合は、配偶者が65歳になった時点で本人が65歳未満であれば、配偶者の年金へ加算する仕様としています）")
            else:
                kakyu_nenkin_amount = 0
        else:
            sp_pension_base = sp_pension_start_age = 0
            has_kakyu_nenkin = False
            kakyu_nenkin_amount = 0
            
    st.divider()
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**■ 学資保険**")
        has_edu_ins = st.checkbox("学資保険あり(世帯)")
        if has_edu_ins:
            edu_pay_type = st.radio("払込状況(学資)", ["積立中（分割払い）", "一時払い（これから支払う）"])
            if edu_pay_type == "積立中（分割払い）":
                edu_monthly = st.number_input("毎月の積立額(学資・万円)", value=1.5, step=0.1) * 10000
                edu_pay_start_age = st.slider("支払いを開始した年齢(学資)", 20, current_age, 35)
                edu_pay_end_age = st.slider("払込終了年齢(学資)", current_age, 80, 55)
                edu_pay_age = edu_lump_pay = 0
            else:
                edu_pay_age = st.slider("支払う年齢(学資)", current_age, 80, current_age)
                edu_lump_pay = st.number_input("支払金額(一時払・学資・万円)", value=200, step=10) * 10000
                edu_monthly = edu_pay_end_age = edu_pay_start_age = 0

            edu_return_rate = st.slider("見込利率(学資・年利%)", 0.0, 10.0, 1.0, 0.1) / 100
            edu_receive_type = st.radio("受取方法(学資)", ["一時金（一括）", "年金（分割）"])
            edu_receive_age = st.slider("受取開始年齢(学資)", current_age, 80, 55)
            if edu_receive_type == "年金（分割）":
                edu_receive_years = st.slider("受取期間(学資・年)", 1, 20, 4)
            else:
                edu_receive_years = 0
                
            if edu_pay_type == "積立中（分割払い）":
                invest_years = max(0, edu_pay_end_age - edu_pay_start_age)
                edu_total_paid = (edu_monthly * 12) * invest_years
                fv1 = calc_fv(edu_monthly, edu_return_rate, invest_years)
                defer_years = max(0, edu_receive_age - edu_pay_end_age)
                edu_principal = calc_fv_lump(fv1, edu_return_rate, defer_years)
            else:
                edu_total_paid = edu_lump_pay
                invest_years = max(0, edu_receive_age - edu_pay_age)
                edu_principal = calc_fv_lump(edu_lump_pay, edu_return_rate, invest_years)
                
            if edu_receive_type == "年金（分割）":
                edu_annual_amount = calc_payout_annual(edu_principal, edu_return_rate, edu_receive_years)
                edu_receive_amount = 0
                st.info(f"総払込見込: {edu_total_paid/10000:,.1f}万円 → 受取年額見込: {edu_annual_amount/10000:,.1f}万円/年")
            else:
                edu_receive_amount = edu_principal
                edu_annual_amount = 0
                st.info(f"総払込見込: {edu_total_paid/10000:,.1f}万円 → 一括受取見込: {edu_receive_amount/10000:,.1f}万円")
        else:
            edu_pay_type = edu_receive_type = ""
            edu_monthly = edu_pay_end_age = edu_pay_start_age = edu_pay_age = edu_lump_pay = 0
            edu_receive_age = edu_receive_years = edu_annual_amount = edu_receive_amount = edu_total_paid = 0

        st.markdown("---")
        st.markdown("**■ 生命保険（貯蓄型）**")
        has_life_ins = st.checkbox("生命保険あり(世帯)")
        if has_life_ins:
            life_pay_type = st.radio("払込状況(生命)", ["積立中（分割払い）", "一時払い（これから支払う）"])
            if life_pay_type == "積立中（分割払い）":
                life_monthly = st.number_input("毎月の積立額(生命・万円)", value=2.0, step=0.1) * 10000
                life_pay_start_age = st.slider("支払いを開始した年齢(生命)", 20, current_age, 35)
                life_pay_end_age = st.slider("払込終了年齢(生命)", current_age, 80, 60)
                life_pay_age = life_lump_pay = 0
            else:
                life_pay_age = st.slider("支払う年齢(生命)", current_age, 80, current_age)
                life_lump_pay = st.number_input("支払金額(一時払・生命・万円)", value=300, step=10) * 10000
                life_monthly = life_pay_end_age = life_pay_start_age = 0

            life_return_rate = st.slider("見込利率(生命・年利%)", 0.0, 10.0, 1.0, 0.1) / 100
            life_receive_type = st.radio("受取方法(生命)", ["一時金（一括）", "年金（分割）"])
            life_receive_age = st.slider("受取開始/満期年齢(生命)", current_age, 80, 60)
            if life_receive_type == "年金（分割）":
                life_receive_years = st.slider("受取期間(生命・年)", 1, 20, 10)
            else:
                life_receive_years = 0
                
            if life_pay_type == "積立中（分割払い）":
                invest_years = max(0, life_pay_end_age - life_pay_start_age)
                life_total_paid = (life_monthly * 12) * invest_years
                fv1 = calc_fv(life_monthly, life_return_rate, invest_years)
                defer_years = max(0, life_receive_age - life_pay_end_age)
                life_principal = calc_fv_lump(fv1, life_return_rate, defer_years)
            else:
                life_total_paid = life_lump_pay
                invest_years = max(0, life_receive_age - life_pay_age)
                life_principal = calc_fv_lump(life_lump_pay, life_return_rate, invest_years)
                
            if life_receive_type == "年金（分割）":
                life_annual_amount = calc_payout_annual(life_principal, life_return_rate, life_receive_years)
                life_receive_amount = 0
                st.info(f"総払込見込: {life_total_paid/10000:,.1f}万円 → 受取年額見込: {life_annual_amount/10000:,.1f}万円/年")
            else:
                life_receive_amount = life_principal
                life_annual_amount = 0
                st.info(f"総払込見込: {life_total_paid/10000:,.1f}万円 → 一括受取見込: {life_receive_amount/10000:,.1f}万円")
        else:
            life_pay_type = life_receive_type = ""
            life_monthly = life_pay_end_age = life_pay_start_age = life_pay_age = life_lump_pay = 0
            life_receive_age = life_receive_years = life_annual_amount = life_receive_amount = life_total_paid = 0

        st.markdown("---")
        st.markdown("**■ 本人の個人年金**")
        has_personal_pension = st.checkbox("個人年金保険あり(本人)")
        if has_personal_pension:
            pp_monthly = st.number_input("個人年金の毎月の積立額(万円)", value=1.0, step=0.1) * 10000
            pp_pay_start_age = st.slider("支払いを開始した年齢(個人年金)", 20, current_age, 30)
            pp_pay_end_age = st.slider("個人年金の払込終了年齢(本人)", current_age, 80, 60)
            pp_return_rate = st.slider("見込利率(個人年金・年利%)", 0.0, 10.0, 1.0, 0.1) / 100
            
            pp_receive_start_age = st.slider("個人年金の受取開始年齢(本人)", 60, 80, 60)
            pp_receive_years = st.slider("個人年金の受取期間(年)", 5, 20, 10)
            
            pp_invest_years = max(0, pp_pay_end_age - pp_pay_start_age)
            pp_total_paid = (pp_monthly * 12) * pp_invest_years
            
            fv1 = calc_fv(pp_monthly, pp_return_rate, pp_invest_years)
            defer_years = max(0, pp_receive_start_age - pp_pay_end_age)
            pp_principal = calc_fv_lump(fv1, pp_return_rate, defer_years)
            
            pp_annual_amount = calc_payout_annual(pp_principal, pp_return_rate, pp_receive_years)
            
            st.info(f"総払込見込: {pp_total_paid/10000:,.1f}万円 → 受取年額見込: {pp_annual_amount/10000:,.1f}万円/年")
        else:
            pp_monthly = pp_pay_end_age = pp_pay_start_age = pp_receive_start_age = pp_receive_years = pp_annual_amount = pp_total_paid = 0
            pp_return_rate = 0

    with col2:
        st.markdown("**■ 本人分 iDeCo/DC**")
        has_ideco = st.checkbox("個人型iDeCoあり(本人)")
        if has_ideco:
            ideco_balance_init = st.number_input("iDeCo現在の残高(本人・万円)", value=100, step=1) * 10000
            ideco_monthly = st.number_input("iDeCo毎月の積立額(本人・万円)", value=2.3, step=0.1) * 10000
            ideco_start_age = st.slider("iDeCo加入年齢（本人）", 20, current_age, 30)
            ideco_receipt_age = st.slider("iDeCo受取開始年齢(本人)", 60, 75, 60)
            if ideco_receipt_age > retirement_age:
                ideco_post_retirement_monthly = st.number_input("退職後のiDeCo積立額(本人・万円/月)", value=0.0, step=0.1, help="退職〜受取開始までの掛金") * 10000
            else:
                ideco_post_retirement_monthly = ideco_monthly
            ideco_return = st.slider("iDeCo期待リターン(本人・%)", 0.0, 10.0, 3.0) / 100
            ideco_receipt_type = st.radio("iDeCo受取方法(本人)", ["一時金", "年金(10年分割)"])
            if ideco_receipt_type == "一時金":
                ideco_lump_dest = st.radio("iDeCo一時金の入金先(本人)", ["預貯金へ", "NISA枠優先 (あふれた分は特定口座へ)", "特定口座へ(運用継続)"], index=1)
            else:
                ideco_lump_dest = "預貯金へ"
        else:
            ideco_balance_init = ideco_monthly = ideco_return = ideco_receipt_age = ideco_start_age = 0
            ideco_receipt_type = "一時金"
            ideco_lump_dest = "NISA枠優先 (あふれた分は特定口座へ)"
            ideco_post_retirement_monthly = 0
            
        has_dc = st.checkbox("企業型DCあり(本人)")
        if has_dc:
            dc_balance_init = st.number_input("DC現在の残高(本人・万円)", value=200, step=1) * 10000
            dc_monthly = st.number_input("DC毎月の会社拠出等(本人・万円)", value=1.0, step=0.1) * 10000
            dc_return = st.slider("DC期待リターン(本人・%)", 0.0, 10.0, 3.0) / 100
        else:
            dc_balance_init = dc_monthly = dc_return = 0

        st.markdown("**■ 配偶者分**")
        if has_marriage:
            has_sp_ideco = st.checkbox("個人型iDeCoあり(配偶者)")
            if has_sp_ideco:
                sp_ideco_balance_init = st.number_input("iDeCo現在の残高(配偶者・万円)", value=50, step=1) * 10000
                sp_ideco_monthly = st.number_input("iDeCo毎月の積立額(配偶者・万円)", value=2.3, step=0.1) * 10000
                sp_ideco_start_age = st.slider("iDeCo加入年齢（配偶者）", 20, current_age, 30)
                sp_ideco_receipt_age = st.slider("iDeCo受取開始年齢(配偶者)", 60, 75, 60)
                if sp_ideco_receipt_age > sp_retirement_age:
                    sp_ideco_post_retirement_monthly = st.number_input("退職後のiDeCo積立額(配偶者・万円/月)", value=0.0, step=0.1, help="退職〜受取開始までの掛金") * 10000
                else:
                    sp_ideco_post_retirement_monthly = sp_ideco_monthly
                sp_ideco_return = st.slider("iDeCo期待リターン(配偶者・%)", 0.0, 10.0, 3.0) / 100
                sp_ideco_receipt_type = st.radio("iDeCo受取方法(配偶者)", ["一時金", "年金(10年分割)"])
                if sp_ideco_receipt_type == "一時金":
                    sp_ideco_lump_dest = st.radio("iDeCo一時金の入金先(配偶者)", ["預貯金へ", "NISA枠優先 (あふれた分は特定口座へ)", "特定口座へ(運用継続)"], index=1)
                else:
                    sp_ideco_lump_dest = "預貯金へ"
            else:
                sp_ideco_balance_init = sp_ideco_monthly = sp_ideco_return = sp_ideco_receipt_age = sp_ideco_start_age = 0
                sp_ideco_receipt_type = "一時金"
                sp_ideco_lump_dest = "NISA枠優先 (あふれた分は特定口座へ)"
                sp_ideco_post_retirement_monthly = 0
                
            has_sp_dc = st.checkbox("企業型DCあり(配偶者)")
            if has_sp_dc:
                sp_dc_balance_init = st.number_input("DC現在の残高(配偶者・万円)", value=100, step=1) * 10000
                sp_dc_monthly = st.number_input("DC毎月の会社拠出等(配偶者・万円)", value=1.0, step=0.1) * 10000
                sp_dc_return = st.slider("DC期待リターン(配偶者・%)", 0.0, 10.0, 3.0) / 100
            else:
                sp_dc_balance_init = sp_dc_monthly = sp_dc_return = 0
        else:
            has_sp_ideco = has_sp_dc = False
            sp_ideco_balance_init = sp_ideco_monthly = sp_ideco_return = sp_ideco_receipt_age = sp_ideco_start_age = 0
            sp_dc_balance_init = sp_dc_monthly = sp_dc_return = 0
            sp_ideco_receipt_type = "一時金"
            sp_ideco_lump_dest = "NISA枠優先 (あふれた分は特定口座へ)"
            sp_ideco_post_retirement_monthly = 0

with tabs[6]:
    st.header("その他 (生活費・イベント・税率)")
    use_lifestage_expense = st.checkbox("生活費をライフステージ（年齢）と家族構成で自動変動させる", value=False)
    if use_lifestage_expense:
        st.markdown("現在の**「住居費を除いた」**基本生活費を入力し、必要に応じて年代ごとのベース金額を調整してください。")
        st.info("※年代ごとのベース金額に対し、将来の配偶者や子どもの増減（独立など）による係数を乗算して最終的な生活費を算出します。")
        
        col_base1, col_base2 = st.columns(2)
        with col_base1:
            base_exp_20s = st.number_input("20代の基本生活費(住居費除く・万円/年)", value=200, step=1) * 10000
            base_exp_30s = st.number_input("30代の基本生活費(住居費除く・万円/年)", value=250, step=1) * 10000
            base_exp_40s = st.number_input("40代の基本生活費(住居費除く・万円/年)", value=300, step=1) * 10000
        with col_base2:
            base_exp_50s = st.number_input("50代の基本生活費(住居費除く・万円/年)", value=300, step=1) * 10000
            base_exp_60s = st.number_input("60代の基本生活費(住居費除く・万円/年)", value=250, step=1) * 10000
            base_exp_70s_plus = st.number_input("70代以降の基本生活費(住居費除く・万円/年)", value=200, step=1) * 10000
        
        base_expense = 0
    else:
        base_expense = st.number_input("現在の基本生活費(全年代一律・万円/年)", value=250, step=1) * 10000
        base_exp_20s = base_exp_30s = base_exp_40s = base_exp_50s = base_exp_60s = base_exp_70s_plus = 0
        
    inflation_rate = st.slider("インフレ率 (%)", 0.0, 5.0, 1.5, 0.1) / 100
    future_tax_rate = st.slider("将来の金融課税率 (%)", 20.0, 50.0, 20.0) / 100
    tax_change_age = st.slider("増税される本人の年齢", current_age, 80, current_age + 10)

    st.markdown("---")
    st.subheader("不定期なライフイベント（特別支出）")
    st.write("旅行、冠婚葬祭、車検、医療費などを設定できます。周期を「1」にすると毎年、「2」にすると2年ごとに発生します。「単発」の場合は周期を空欄(または0)にしてください。")
    default_events = pd.DataFrame({
        "イベント名": ["海外旅行", "住宅修繕", "車検", "冠婚葬祭", ""],
        "開始年齢(本人)": [45, 55, current_age + 1, 60, None],
        "終了年齢(本人)": [65, 55, 75, 60, None],
        "周期(年ごと)": [5, 0, 2, 0, None],
        "費用(万円)": [100, 200, 15, 50, None]
    })
    events_df = st.data_editor(default_events, num_rows="dynamic", key="events_editor")

with tabs[7]:
    st.header("老人ホーム入居・自宅売却")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("本人")
        has_nursing_home = st.checkbox("本人の入居予定あり")
        if has_nursing_home:
            nh_entry_age = st.slider("入居する年齢(本人)", 60, 100, 80)
            nh_lump_sum = st.number_input("入居時費用（一時金・万円）(本人)", value=500, step=1) * 10000
            nh_monthly = st.number_input("月額費用（万円/月）(本人)", value=15, step=1) * 10000
            nh_base_expense_adjustment = st.number_input("入居後の基本生活費(万円/年)(本人)", value=120, step=1) * 10000
        else:
            nh_entry_age = 1000
            nh_lump_sum = nh_monthly = nh_base_expense_adjustment = 0
            
    with col2:
        st.subheader("配偶者")
        if has_marriage:
            sp_has_nursing_home = st.checkbox("配偶者の入居予定あり")
            if sp_has_nursing_home:
                sp_nh_entry_age = st.slider("入居する年齢(配偶者)", 60, 100, 80)
                sp_nh_lump_sum = st.number_input("入居時費用（一時金・万円）(配偶者)", value=500, step=1) * 10000
                sp_nh_monthly = st.number_input("月額費用（万円/月）(配偶者)", value=15, step=1) * 10000
                sp_nh_base_expense_adjustment = st.number_input("入居後の基本生活費(万円/年)(配偶者)", value=120, step=1) * 10000
            else:
                sp_nh_entry_age = 1000
                sp_nh_lump_sum = sp_nh_monthly = sp_nh_base_expense_adjustment = 0
        else:
            sp_has_nursing_home = False
            sp_nh_entry_age = 1000
            sp_nh_lump_sum = sp_nh_monthly = sp_nh_base_expense_adjustment = 0

    st.divider()
    if (housing_type == "持ち家" or has_housing) and (has_nursing_home or sp_has_nursing_home):
        has_home_sale = st.checkbox("老人ホーム入居時に持ち家を売却する", value=True)
        if has_home_sale:
            home_sale_price = st.number_input("自宅売却価格（万円）", value=2000, step=1) * 10000
            if has_nursing_home and sp_has_nursing_home:
                home_sale_trigger = st.radio("売却のタイミング", ["本人が入居した年", "配偶者が入居した年", "遅い方（二人とも入居した時点）"], index=2)
            elif has_nursing_home:
                home_sale_trigger = "本人が入居した年"
            else:
                home_sale_trigger = "配偶者が入居した年"
        else:
            home_sale_price = 0
            home_sale_trigger = None
    else:
        has_home_sale = False
        home_sale_price = 0
        home_sale_trigger = None

# --- Simulation Logic ---
try:
    ages = list(range(current_age, life_expectancy + 1))
    years_count = len(ages)

    arr_salary, arr_sp_salary = np.zeros(years_count), np.zeros(years_count)
    arr_pension, arr_sp_pension = np.zeros(years_count), np.zeros(years_count)
    arr_other_misc_income = np.zeros(years_count)
    arr_child_allowance = np.zeros(years_count)
    arr_leave_benefit = np.zeros(years_count)
    arr_ret_income = np.zeros(years_count)
    arr_lump_sum_income = np.zeros(years_count)
    arr_net_income = np.zeros(years_count)
    arr_soc_ins, arr_sp_soc_ins = np.zeros(years_count), np.zeros(years_count)
    arr_inc_tax, arr_sp_inc_tax = np.zeros(years_count), np.zeros(years_count)
    arr_res_tax, arr_sp_res_tax = np.zeros(years_count), np.zeros(years_count)
    arr_ret_inc_tax, arr_ret_res_tax = np.zeros(years_count), np.zeros(years_count) 

    arr_exp_base = np.zeros(years_count)
    arr_exp_event = np.zeros(years_count)
    arr_exp_house = np.zeros(years_count)
    arr_exp_edu = np.zeros(years_count)
    arr_exp_car = np.zeros(years_count) 
    arr_exp_nursing = np.zeros(years_count) 
    arr_total_exp = np.zeros(years_count)

    arr_withdrawal_amount = np.zeros(years_count)
    arr_annual_balance = np.zeros(years_count)
    arr_car_loan_pmts = np.zeros(years_count)
    arr_edu_loan_pmts = np.zeros(years_count)
    arr_reform_loan_pmts = np.zeros(years_count)
    arr_invest_amount = np.zeros(years_count) 

    arr_debt_housing = np.zeros(years_count)
    arr_debt_car = np.zeros(years_count)
    arr_debt_reform = np.zeros(years_count)
    arr_debt_edu = np.zeros(years_count)
    arr_debt_balance = np.zeros(years_count) 

    arr_mortgage_deduction = np.zeros(years_count)

    balances_savings = np.zeros(years_count)
    balances_nisa = np.zeros(years_count)
    balances_taxable = np.zeros(years_count)
    balances_ideco_dc = np.zeros(years_count)
    total_assets = np.zeros(years_count)

    is_depleted = False
    
    current_rent_annual = rent_annual
    last_rent_update_year = 0

    pension_actual = calc_pension_amount(pension_base, pension_start_age)
    
    # 住宅ローン スケジュール事前計算
    if housing_type == "持ち家" and has_existing_mortgage:
        ex_m_pmt, ex_m_bal = generate_mortgage_schedule(
            ex_housing_loan_balance, ex_housing_loan_rate, ex_housing_loan_years_remaining,
            ex_housing_rate_up_years if ex_housing_loan_type == "変動金利" else 1000,
            ex_housing_rate_up_rate
        )
    
    if has_housing:
        new_m_pmt, new_m_bal = generate_mortgage_schedule(
            housing_loan_amount, housing_loan_rate, housing_loan_years,
            housing_rate_up_years if housing_loan_type == "変動金利" else 1000,
            housing_rate_up_rate
        )

    curr_main_nisa = initial_nisa
    curr_main_taxable = initial_taxable
    curr_main_savings = initial_savings
    
    curr_sp_nisa = sp_initial_nisa if has_marriage else 0
    curr_sp_taxable = sp_initial_taxable if has_marriage else 0
    curr_sp_savings = sp_initial_savings if has_marriage else 0

    curr_ideco_balance = ideco_balance_init
    curr_dc_balance = dc_balance_init
    ideco_pension_annual = 0
    main_ret_deduction_used = 0 
    
    main_nisa_lifetime_invested = nisa_used_tsumitate + nisa_used_growth
    sp_nisa_lifetime_invested = sp_nisa_used_tsumitate + sp_nisa_used_growth if has_marriage else 0

    curr_sp_ideco_balance = sp_ideco_balance_init if has_marriage else 0
    curr_sp_dc_balance = sp_dc_balance_init if has_marriage else 0
    sp_ideco_pension_annual = 0
    sp_ret_deduction_used = 0 

    if has_marriage: sp_pension_actual = calc_pension_amount(sp_pension_base, sp_pension_start_age)
    else: sp_pension_actual = 0
    
    edu_total_paid = 0
    if has_edu_ins:
        if edu_pay_type == "積立中（分割払い）":
            edu_paid_so_far = (current_age - edu_pay_start_age) * edu_monthly * 12
            edu_total_paid = edu_paid_so_far + (edu_monthly * 12) * max(0, edu_pay_end_age - current_age)
        elif edu_pay_type == "一時払い（これから支払う）":
            edu_total_paid = edu_lump_pay

    life_total_paid = 0
    if has_life_ins:
        if life_pay_type == "積立中（分割払い）":
            life_paid_so_far = (current_age - life_pay_start_age) * life_monthly * 12
            life_total_paid = life_paid_so_far + (life_monthly * 12) * max(0, life_pay_end_age - current_age)
        elif life_pay_type == "一時払い（これから支払う）":
            life_total_paid = life_lump_pay
    
    def get_family_scale(main_alive, spouse_alive, children_ages):
        scale = 0.0
        if main_alive: scale += 1.0
        if spouse_alive: scale += 0.5
        for c_age in children_ages:
            if c_age < 0: pass 
            elif c_age <= 12: scale += 0.2
            elif c_age <= 18: scale += 0.3
            elif c_age <= 22: scale += 0.4
        return scale
        
    initial_spouse_alive = has_marriage and (current_age >= marriage_age)
    initial_children_ages = [current_age - child["birth_age"] for child in child_settings]
    
    initial_scale = get_family_scale(True, initial_spouse_alive, initial_children_ages)
    if initial_scale == 0: initial_scale = 1.0 

    for i, age in enumerate(ages):
        h_debt, c_debt, r_debt, e_debt = 0, 0, 0, 0
        sp_age = age + sp_age_diff if has_marriage else 0
        h_pmt_this_year = 0
        
        if housing_type == "持ち家" and has_existing_mortgage:
            if i < ex_housing_loan_years_remaining:
                h_debt += ex_m_bal[i]
                h_pmt_this_year += ex_m_pmt[i]
            if has_ex_mortgage_deduction and i < ex_mortgage_deduction_years_remaining:
                applicable_balance = min(ex_m_bal[i] if i < ex_housing_loan_years_remaining else 0, ex_mortgage_deduction_max)
                arr_mortgage_deduction[i] += applicable_balance * ex_mortgage_deduction_rate

        if has_housing and age >= housing_purchase_age:
            years_passed = age - housing_purchase_age
            if years_passed < housing_loan_years:
                h_debt += new_m_bal[years_passed]
                h_pmt_this_year += new_m_pmt[years_passed]
            if has_mortgage_deduction and 0 <= years_passed < mortgage_deduction_years:
                applicable_balance = min(new_m_bal[years_passed] if years_passed < housing_loan_years else 0, mortgage_deduction_max)
                arr_mortgage_deduction[i] += applicable_balance * mortgage_deduction_rate
                
        if has_car and car_loan_use:
            c_age = car_first_purchase_age
            while c_age <= age and c_age <= car_last_purchase_age:
                cost = car_first_purchase_cost if c_age == car_first_purchase_age else car_replace_cost
                years_passed = age - c_age
                c_debt += calc_loan_balance(cost, car_loan_rate, car_loan_years, years_passed)
                c_age += car_replace_cycle
                
        if has_marriage and sp_has_car and sp_car_loan_use:
            sp_c_age = sp_car_first_purchase_age
            while sp_c_age <= sp_age and sp_c_age <= sp_car_last_purchase_age:
                cost = sp_car_first_purchase_cost if sp_c_age == sp_car_first_purchase_age else sp_car_replace_cost
                years_passed = sp_age - sp_c_age
                c_debt += calc_loan_balance(cost, sp_car_loan_rate, sp_car_loan_years, years_passed)
                sp_c_age += sp_car_replace_cycle
                
        if has_reform and age >= reform_age and use_reform_loan:
            years_passed = age - reform_age
            r_debt = calc_loan_balance(reform_cost, reform_loan_rate, reform_loan_years, years_passed)
            if age == reform_age:
                pmt = calc_mortgage_pmt(reform_cost, reform_loan_rate, reform_loan_years)
                for j in range(i, min(years_count, i + reform_loan_years)):
                    arr_reform_loan_pmts[j] += pmt
                    
        if use_edu_loan:
            edu_cost_this_year = 0
            for child in child_settings:
                c_age = age - child["birth_age"]
                if c_age >= 4:
                    for start, end, course in child["course"]:
                        if course and start <= c_age <= end:
                            edu_cost_this_year += EDU_COST.get(course, 0) * 10000
            
            if edu_cost_this_year > 0:
                pmt = calc_mortgage_pmt(edu_cost_this_year, edu_loan_rate, edu_loan_years)
                for j in range(i, min(years_count, i + edu_loan_years)):
                    arr_edu_loan_pmts[j] += pmt
                    
            for past_i in range(0, i + 1):
                past_age = ages[past_i]
                past_edu_cost = 0
                for child in child_settings:
                    c_age = past_age - child["birth_age"]
                    if c_age >= 4:
                        for start, end, course in child["course"]:
                            if course and start <= c_age <= end:
                                past_edu_cost += EDU_COST.get(course, 0) * 10000
                if past_edu_cost > 0:
                    years_passed = age - past_age
                    e_debt += calc_loan_balance(past_edu_cost, edu_loan_rate, edu_loan_years, years_passed)
                
        arr_debt_housing[i] = h_debt
        arr_debt_car[i] = c_debt
        arr_debt_reform[i] = r_debt
        arr_debt_edu[i] = e_debt
        arr_debt_balance[i] = h_debt + c_debt + r_debt + e_debt

        curr_main_is_working = actual_is_working and (age < retirement_age)
        curr_sp_is_working = actual_sp_working and (sp_age < sp_retirement_age) if has_marriage else False
        
        current_ideco_monthly = ideco_monthly if age < retirement_age else ideco_post_retirement_monthly
        current_sp_ideco_monthly = sp_ideco_monthly if sp_age < sp_retirement_age else sp_ideco_post_retirement_monthly
        
        ideco_income_this_year = 0
        ideco_lump_sum = 0
        
        if has_dc:
            if age < retirement_age:
                curr_dc_balance = curr_dc_balance * (1 + dc_return) + (dc_monthly * 12)
            elif age == retirement_age:
                curr_ideco_balance += curr_dc_balance
                curr_dc_balance = 0
                
        if has_ideco or has_dc:
            if age < ideco_receipt_age:
                curr_ideco_balance = curr_ideco_balance * (1 + ideco_return) + (current_ideco_monthly * 12 if has_ideco else 0)
            elif age == ideco_receipt_age:
                if ideco_receipt_type == "一時金":
                    ideco_lump_sum = curr_ideco_balance
                    curr_ideco_balance = 0
                else:
                    ideco_pension_annual = curr_ideco_balance / 10
                    ideco_income_this_year = ideco_pension_annual
                    curr_ideco_balance -= ideco_pension_annual
            elif ideco_receipt_age < age < ideco_receipt_age + 10 and ideco_receipt_type == "年金(10年分割)":
                ideco_income_this_year = ideco_pension_annual
                curr_ideco_balance = max(0, curr_ideco_balance - ideco_pension_annual)

        sp_ideco_income_this_year = 0
        sp_ideco_lump_sum = 0
        
        if has_marriage:
            if has_sp_dc:
                if sp_age < sp_retirement_age:
                    curr_sp_dc_balance = curr_sp_dc_balance * (1 + sp_dc_return) + (sp_dc_monthly * 12)
                elif sp_age == sp_retirement_age:
                    curr_sp_ideco_balance += curr_sp_dc_balance
                    curr_sp_dc_balance = 0
            if has_sp_ideco or has_sp_dc:
                if sp_age < sp_ideco_receipt_age:
                    curr_sp_ideco_balance = curr_sp_ideco_balance * (1 + sp_ideco_return) + (current_sp_ideco_monthly * 12 if has_sp_ideco else 0)
                elif sp_age == sp_ideco_receipt_age:
                    if sp_ideco_receipt_type == "一時金":
                        sp_ideco_lump_sum = curr_sp_ideco_balance
                        curr_sp_ideco_balance = 0
                    else:
                        sp_ideco_pension_annual = curr_sp_ideco_balance / 10
                        sp_ideco_income_this_year = sp_ideco_pension_annual
                        curr_sp_ideco_balance -= sp_ideco_pension_annual
                elif sp_ideco_receipt_age < sp_age < sp_ideco_receipt_age + 10 and sp_ideco_receipt_type == "年金(10年分割)":
                    sp_ideco_income_this_year = sp_ideco_pension_annual
                    curr_sp_ideco_balance = max(0, curr_sp_ideco_balance - sp_ideco_pension_annual)

        if age < retirement_age:
            if actual_is_working:
                normal_salary_main = gross_income
                for a in range(current_age, age + 1):
                    if a == salary_decrease_age: normal_salary_main *= (1 - salary_decrease_rate)
                    elif a > current_age: normal_salary_main *= (1 + salary_growth)
            else:
                normal_salary_main = 0
        else:
            if has_post_retirement_job and age <= post_retirement_end_age:
                normal_salary_main = post_retirement_income * 12
            else:
                normal_salary_main = 0
                
        if has_marriage:
            if sp_age < sp_retirement_age:
                if actual_sp_working:
                    normal_salary_sp = sp_gross_income
                    for a in range(current_age + sp_age_diff, sp_age + 1):
                        if a == sp_salary_decrease_age: normal_salary_sp *= (1 - sp_salary_decrease_rate)
                        elif a > current_age + sp_age_diff: normal_salary_sp *= (1 + sp_salary_growth)
                else:
                    normal_salary_sp = 0
            else:
                if has_sp_post_retirement_job and sp_age <= sp_post_retirement_end_age:
                    normal_salary_sp = sp_post_retirement_income * 12
                else:
                    normal_salary_sp = 0
        else:
            normal_salary_sp = 0
            
        leave_ratio_main = 0
        leave_ratio_sp = 0
        
        for child in child_settings:
            if child["birth_age"] <= age <= child["birth_age"] + 2:
                years_since_birth = age - child["birth_age"]
                
                m_main = child["leave_main"]
                if m_main > 0:
                    if years_since_birth == 0: leave_this_year = min(12, m_main)
                    elif years_since_birth == 1: leave_this_year = min(12, max(0, m_main - 12))
                    elif years_since_birth == 2: leave_this_year = min(12, max(0, m_main - 24))
                    else: leave_this_year = 0
                    leave_ratio_main += leave_this_year / 12
                    
                m_sp = child["leave_sp"]
                if m_sp > 0:
                    if years_since_birth == 0: leave_this_year = min(12, m_sp)
                    elif years_since_birth == 1: leave_this_year = min(12, max(0, m_sp - 12))
                    elif years_since_birth == 2: leave_this_year = min(12, max(0, m_sp - 24))
                    else: leave_this_year = 0
                    leave_ratio_sp += leave_this_year / 12
                    
        leave_ratio_main = min(1.0, leave_ratio_main)
        leave_ratio_sp = min(1.0, leave_ratio_sp)
        
        leave_benefit_main = normal_salary_main * leave_ratio_main * 0.67
        leave_benefit_sp = normal_salary_sp * leave_ratio_sp * 0.67
        total_leave_benefit = leave_benefit_main + leave_benefit_sp
        
        salary = normal_salary_main * (1 - leave_ratio_main)
        sp_salary = normal_salary_sp * (1 - leave_ratio_sp)

        pension = pension_actual if age >= pension_start_age else 0
        pension += ideco_income_this_year
        
        sp_pension = sp_pension_actual if sp_age >= sp_pension_start_age else 0
        sp_pension += sp_ideco_income_this_year
        
        if has_marriage and has_kakyu_nenkin:
            if sp_age_diff <= 0:  
                if age >= 65 and sp_age < 65:
                    pension += kakyu_nenkin_amount
            else:  
                if sp_age >= 65 and age < 65:
                    sp_pension += kakyu_nenkin_amount
            
        temp_income_total = 0
        actual_insurance_income = 0
        
        if has_edu_ins and edu_receive_type == "一時金（一括）" and age == edu_receive_age:
            actual_insurance_income += edu_receive_amount
            temp_income_total += max(0, edu_receive_amount - edu_total_paid)
            
        if has_life_ins and life_receive_type == "一時金（一括）" and age == life_receive_age:
            actual_insurance_income += life_receive_amount
            temp_income_total += max(0, life_receive_amount - life_total_paid)

        taxable_temp_income = max(0, temp_income_total - 500000) / 2

        misc_income_total = 0
        if has_edu_ins and edu_receive_type == "年金（分割）" and edu_receive_age <= age < edu_receive_age + edu_receive_years:
            actual_insurance_income += edu_annual_amount
            misc_income_total += max(0, edu_annual_amount - (edu_total_paid / edu_receive_years))

        if has_life_ins and life_receive_type == "年金（分割）" and life_receive_age <= age < life_receive_age + life_receive_years:
            actual_insurance_income += life_annual_amount
            misc_income_total += max(0, life_annual_amount - (life_total_paid / life_receive_years))

        if has_personal_pension and pp_receive_start_age <= age < (pp_receive_start_age + pp_receive_years):
            actual_insurance_income += pp_annual_amount
            pp_annual_expense_portion = pp_total_paid / pp_receive_years if pp_receive_years > 0 else 0
            misc_income_total += max(0, pp_annual_amount - pp_annual_expense_portion)
            
        other_misc_income_this_year = taxable_temp_income + misc_income_total
        arr_other_misc_income[i] = other_misc_income_this_year
                
        child_allowance_this_year = 0
        if receive_child_allowance:
            for idx, child in enumerate(child_settings):
                c_age = age - child["birth_age"]
                if 0 <= c_age <= 2:
                    child_allowance_this_year += 15000 * 12
                elif 3 <= c_age <= 18:
                    if idx >= 2: child_allowance_this_year += 30000 * 12
                    else: child_allowance_this_year += 10000 * 12
        
        arr_child_allowance[i] = child_allowance_this_year
        arr_leave_benefit[i] = total_leave_benefit

        arr_salary[i] = salary
        arr_pension[i] = pension + actual_insurance_income
        arr_sp_salary[i] = sp_salary
        arr_sp_pension[i] = sp_pension

        ideco_ded = (current_ideco_monthly * 12) if (has_ideco and age < ideco_receipt_age) else 0
        
        current_life_ins_prem = 0
        if has_edu_ins:
            if edu_pay_type == "積立中（分割払い）" and age <= edu_pay_end_age:
                current_life_ins_prem += edu_monthly * 12
            elif edu_pay_type == "一時払い（これから支払う）" and age == edu_pay_age:
                current_life_ins_prem += edu_lump_pay
                
        if has_life_ins:
            if life_pay_type == "積立中（分割払い）" and age <= life_pay_end_age:
                current_life_ins_prem += life_monthly * 12
            elif life_pay_type == "一時払い（これから支払う）" and age == life_pay_age:
                current_life_ins_prem += life_lump_pay

        life_ins_ded_inc = 0
        if current_life_ins_prem > 80000: life_ins_ded_inc = 40000
        elif current_life_ins_prem > 40000: life_ins_ded_inc = current_life_ins_prem * 0.25 + 20000
        elif current_life_ins_prem > 20000: life_ins_ded_inc = current_life_ins_prem * 0.5 + 10000
        else: life_ins_ded_inc = current_life_ins_prem

        life_ins_ded_res = 0
        if current_life_ins_prem > 56000: life_ins_ded_res = 28000
        elif current_life_ins_prem > 32000: life_ins_ded_res = current_life_ins_prem * 0.25 + 14000
        elif current_life_ins_prem > 12000: life_ins_ded_res = current_life_ins_prem * 0.5 + 6000
        else: life_ins_ded_res = current_life_ins_prem

        current_pp_prem = pp_monthly * 12 if (has_personal_pension and age <= pp_pay_end_age) else 0
        pp_ded_inc = 0
        if current_pp_prem > 80000: pp_ded_inc = 40000
        elif current_pp_prem > 40000: pp_ded_inc = current_pp_prem * 0.25 + 20000
        elif current_pp_prem > 20000: pp_ded_inc = current_pp_prem * 0.5 + 10000
        else: pp_ded_inc = current_pp_prem

        pp_ded_res = 0
        if current_pp_prem > 56000: pp_ded_res = 28000
        elif current_pp_prem > 32000: pp_ded_res = current_pp_prem * 0.25 + 14000
        elif current_pp_prem > 12000: pp_ded_res = current_pp_prem * 0.5 + 6000
        else: pp_ded_res = current_pp_prem
        
        fam_ded = 380000 if (has_marriage and age >= marriage_age and sp_salary <= 1500000) else 0
        for child in child_settings:
            c_age = age - child["birth_age"]
            if 16 <= c_age <= 18: fam_ded += 380000
            elif 19 <= c_age <= 22: fam_ded += 630000

        prev_sal = arr_salary[i-1] if i > 0 else (gross_income if actual_is_working else 0)
        prev_pen = (pension_actual if age - 1 >= pension_start_age else 0) + (ideco_income_this_year if i > 0 else 0)
        prev_other_misc = arr_other_misc_income[i-1] if i > 0 else 0
        
        soc_ins, income_tax, res_tax = calc_tax_and_soc(salary, pension, other_misc_income=other_misc_income_this_year, prev_salary=prev_sal, prev_pension=prev_pen, prev_other_misc_income=prev_other_misc, ideco_deduction=ideco_ded, fam_deduction=fam_ded, age=age, pp_ded_inc=pp_ded_inc, pp_ded_res=pp_ded_res, life_ded_inc=life_ins_ded_inc, life_ded_res=life_ins_ded_res, is_working=curr_main_is_working)
        
        sp_soc_ins, sp_income_tax, sp_res_tax = 0, 0, 0
        if has_marriage:
            sp_ideco_ded = (current_sp_ideco_monthly * 12) if (has_sp_ideco and sp_age < sp_ideco_receipt_age) else 0
            prev_sp_sal = arr_sp_salary[i-1] if i > 0 else (sp_gross_income if actual_sp_working else 0)
            prev_sp_pen = arr_sp_pension[i-1] if i > 0 else (sp_pension_actual if sp_age >= sp_pension_start_age else 0)
            sp_soc_ins, sp_income_tax, sp_res_tax = calc_tax_and_soc(sp_salary, sp_pension, prev_salary=prev_sp_sal, prev_pension=prev_sp_pen, ideco_deduction=sp_ideco_ded, fam_deduction=0, age=sp_age, is_working=curr_sp_is_working)
            
        total_inc_tax = income_tax + sp_income_tax
        deduction_amount = arr_mortgage_deduction[i]
        if deduction_amount > 0:
            if deduction_amount <= total_inc_tax:
                income_tax = max(0, income_tax - deduction_amount)
            else:
                income_tax = 0
                sp_income_tax = 0
                
        arr_inc_tax[i] = income_tax
        arr_sp_inc_tax[i] = sp_income_tax
        arr_soc_ins[i] = soc_ins
        arr_res_tax[i] = res_tax
        arr_sp_soc_ins[i] = sp_soc_ins
        arr_sp_res_tax[i] = sp_res_tax
        
        ret_net_main, ret_inc_tax_main, ret_res_tax_main = 0, 0, 0
        ideco_lump_net_main = 0
        
        if age == retirement_age and retirement_allowance > 0:
            years = max(1, retirement_age - employment_start_age)
            it, rt, used_ded = calc_ret_tax(retirement_allowance, years, prior_deduction=main_ret_deduction_used)
            main_ret_deduction_used += used_ded
            ret_inc_tax_main += it; ret_res_tax_main += rt
            ret_net_main += (retirement_allowance - it - rt)
            
        if ideco_lump_sum > 0:
            years = max(1, age - ideco_start_age) 
            it, rt, used_ded = calc_ret_tax(ideco_lump_sum, years, prior_deduction=main_ret_deduction_used)
            if abs(age - retirement_age) <= 19:
                main_ret_deduction_used += used_ded 
            ret_inc_tax_main += it; ret_res_tax_main += rt
            ideco_lump_net_main = (ideco_lump_sum - it - rt)
            
        ret_net_sp, ret_inc_tax_sp, ret_res_tax_sp = 0, 0, 0
        ideco_lump_net_sp = 0
        
        if has_marriage:
            if sp_age == sp_retirement_age and sp_retirement_allowance > 0:
                years = max(1, sp_retirement_age - sp_employment_start_age)
                it, rt, used_ded = calc_ret_tax(sp_retirement_allowance, years, prior_deduction=sp_ret_deduction_used)
                sp_ret_deduction_used += used_ded
                ret_inc_tax_sp += it; ret_res_tax_sp += rt
                ret_net_sp += (sp_retirement_allowance - it - rt)
                
            if sp_ideco_lump_sum > 0:
                years = max(1, sp_age - sp_ideco_start_age)
                it, rt, used_ded = calc_ret_tax(sp_ideco_lump_sum, years, prior_deduction=sp_ret_deduction_used)
                if abs(sp_age - sp_retirement_age) <= 19:
                    sp_ret_deduction_used += used_ded
                ret_inc_tax_sp += it; ret_res_tax_sp += rt
                ideco_lump_net_sp = (sp_ideco_lump_sum - it - rt)

        arr_ret_inc_tax[i] = ret_inc_tax_main + ret_inc_tax_sp
        arr_ret_res_tax[i] = ret_res_tax_main + ret_res_tax_sp
        arr_ret_income[i] = ret_net_main + ret_net_sp
        
        net_income_main = salary + pension + actual_insurance_income + child_allowance_this_year + leave_benefit_main - soc_ins - income_tax - res_tax
        net_income_sp = sp_salary + sp_pension + leave_benefit_sp - sp_soc_ins - sp_income_tax - sp_res_tax
        arr_net_income[i] = net_income_main + net_income_sp

        if use_lifestage_expense:
            current_spouse_alive = has_marriage and (age >= marriage_age)
            current_children_ages = []
            for child in child_settings:
                c_age = age - child["birth_age"]
                if 0 <= c_age <= 22:
                    current_children_ages.append(c_age)
                    
            current_scale = get_family_scale(True, current_spouse_alive, current_children_ages)
            
            if age < 30: current_age_base = base_exp_20s
            elif age < 40: current_age_base = base_exp_30s
            elif age < 50: current_age_base = base_exp_40s
            elif age < 60: current_age_base = base_exp_50s
            elif age < 70: current_age_base = base_exp_60s
            else: current_age_base = base_exp_70s_plus
            
            adjusted_base_expense = current_age_base * (current_scale / initial_scale)
            
            if has_nursing_home and age >= nh_entry_age:
                exp_base = nh_base_expense_adjustment * ((1 + inflation_rate) ** i)
            else:
                exp_base = adjusted_base_expense * ((1 + inflation_rate) ** i)
        else:
            if has_nursing_home and age >= nh_entry_age:
                exp_base = nh_base_expense_adjustment * ((1 + inflation_rate) ** i)
            else:
                exp_base = base_expense * ((1 + inflation_rate) ** i)

        if has_marriage and sp_has_nursing_home and sp_age >= sp_nh_entry_age:
            exp_base += sp_nh_base_expense_adjustment * ((1 + inflation_rate) ** i)

        exp_house = 0
        exp_edu = 0
        exp_car = 0
        exp_nursing = 0
        
        if age == marriage_age: exp_base += wedding_cost
        
        events_exp_this_year = 0
        for idx, row in events_df.iterrows():
            if pd.notna(row["開始年齢(本人)"]) and pd.notna(row["費用(万円)"]):
                start_age_ev = row["開始年齢(本人)"]
                end_age_ev = row["終了年齢(本人)"] if pd.notna(row["終了年齢(本人)"]) else start_age_ev
                cycle = row["周期(年ごと)"] if pd.notna(row["周期(年ごと)"]) and row["周期(年ごと)"] > 0 else 0
                
                if cycle == 0:
                    if age == start_age_ev:
                        events_exp_this_year += row["費用(万円)"] * 10000
                else:
                    if start_age_ev <= age <= end_age_ev:
                        if (age - start_age_ev) % cycle == 0:
                            events_exp_this_year += row["費用(万円)"] * 10000
                            
        arr_exp_event[i] = events_exp_this_year
        
        if has_nursing_home and age >= nh_entry_age:
            if age == nh_entry_age:
                exp_nursing += nh_lump_sum
            exp_nursing += nh_monthly * 12
            
        if has_marriage and sp_has_nursing_home and sp_age >= sp_nh_entry_age:
            if sp_age == sp_nh_entry_age:
                exp_nursing += sp_nh_lump_sum
            exp_nursing += sp_nh_monthly * 12
        
        if has_car:
            if age <= car_dispose_age:
                exp_car += car_maint_annual
                car_purchase_cost_this_year = 0
                if age <= car_last_purchase_age:
                    if age == car_first_purchase_age: car_purchase_cost_this_year = car_first_purchase_cost
                    elif age > car_first_purchase_age and (age - car_first_purchase_age) % car_replace_cycle == 0: car_purchase_cost_this_year = car_replace_cost
                    
                if car_purchase_cost_this_year > 0:
                    if car_loan_use:
                        pass 
                    else:
                        exp_car += car_purchase_cost_this_year
                        
        if has_marriage and sp_has_car:
            if sp_age <= sp_car_dispose_age:
                exp_car += sp_car_maint_annual
                sp_car_purchase_cost_this_year = 0
                if sp_age <= sp_car_last_purchase_age:
                    if sp_age == sp_car_first_purchase_age: sp_car_purchase_cost_this_year = sp_car_first_purchase_cost
                    elif sp_age > sp_car_first_purchase_age and (sp_age - sp_car_first_purchase_age) % sp_car_replace_cycle == 0: sp_car_purchase_cost_this_year = sp_car_replace_cost
                    
                if sp_car_purchase_cost_this_year > 0:
                    if sp_car_loan_use:
                        pass
                    else:
                        exp_car += sp_car_purchase_cost_this_year
                        
        exp_car += arr_car_loan_pmts[i]
                    
        if has_ideco and age < ideco_receipt_age: exp_base += (current_ideco_monthly * 12)
        if has_marriage and has_sp_ideco and sp_age < sp_ideco_receipt_age: exp_base += (current_sp_ideco_monthly * 12)
        
        exp_base += current_life_ins_prem + current_pp_prem
            
        if housing_type == "賃貸":
            if not has_housing or age < housing_purchase_age: 
                is_renewal_year = (age - current_age) > 0 and (age - current_age) % rent_renewal_years == 0
                
                if is_renewal_year:
                    if use_rent_inflation:
                        current_rent_annual = current_rent_annual * ((1 + rent_inflation_rate) ** rent_renewal_years)
                    renewal_fee = (current_rent_annual / 12) * rent_renewal_fee_months
                    exp_house += current_rent_annual + renewal_fee
                    last_rent_update_year = age
                else:
                    exp_house += current_rent_annual
                
        if has_housing:
            if age == housing_purchase_age: exp_house += housing_down_payment
            if age >= housing_purchase_age: exp_house += housing_maint
            
        if has_reform and age == reform_age:
            if use_reform_loan:
                pass
            else:
                exp_house += reform_cost
                
        normal_exp_house = exp_house + arr_reform_loan_pmts[i] + h_pmt_this_year
                
        for child in child_settings:
            c_age = age - child["birth_age"]
            if c_age >= 4:
                for start, end, course in child["course"]:
                    if course and start <= c_age <= end:
                        edu_cost = EDU_COST.get(course, 0) * 10000
                        if not use_edu_loan:
                            exp_edu += edu_cost
                            
            if child["uni_support"]["active"] and 19 <= c_age <= 22:
                normal_exp_house += (child["uni_support"]["rent"] * 12)
                exp_base += (child["uni_support"]["living"] * 12)
                            
        normal_exp_edu = exp_edu + arr_edu_loan_pmts[i]
        normal_exp_car = exp_car
        
        exp_house = normal_exp_house
        exp_edu = normal_exp_edu
        exp_car = normal_exp_car

        arr_exp_base[i] = exp_base
        arr_exp_house[i] = exp_house
        arr_exp_edu[i] = exp_edu
        arr_exp_car[i] = exp_car
        arr_exp_nursing[i] = exp_nursing
        arr_total_exp[i] = exp_base + events_exp_this_year + exp_house + exp_edu + exp_car + exp_nursing
        
        applicable_tax_rate = future_tax_rate if age >= tax_change_age else 0.20
        taxable_real_return = taxable_return_base * (1 - applicable_tax_rate)
        
        calc_nisa = curr_main_nisa * (1 + nisa_return) + curr_sp_nisa * (1 + nisa_return)
        calc_taxable = curr_main_taxable * (1 + taxable_real_return) + curr_sp_taxable * (1 + taxable_real_return)
        calc_savings = curr_main_savings + curr_sp_savings
        
        w_taxable = (curr_main_taxable * withdrawal_rate_taxable if age >= withdrawal_start_age else 0) + (curr_sp_taxable * sp_withdrawal_rate_taxable if sp_age >= sp_withdrawal_start_age else 0)
        w_nisa = (curr_main_nisa * withdrawal_rate_nisa if age >= withdrawal_start_age else 0) + (curr_sp_nisa * sp_withdrawal_rate_nisa if sp_age >= sp_withdrawal_start_age else 0)
        
        calc_taxable -= w_taxable
        calc_nisa -= w_nisa
        arr_withdrawal_amount[i] = w_taxable + w_nisa
        
        annual_balance = arr_net_income[i] - arr_total_exp[i]
        arr_annual_balance[i] = annual_balance 
        
        lump_sum_income_this_year = 0
        
        if has_home_sale:
            if home_sale_trigger == "本人が入居した年" and age == nh_entry_age:
                calc_savings += home_sale_price
            elif home_sale_trigger == "配偶者が入居した年" and sp_age == sp_nh_entry_age:
                calc_savings += home_sale_price
            elif home_sale_trigger == "遅い方（二人とも入居した時点）":
                target_year = max(nh_entry_age if has_nursing_home else 0, sp_nh_entry_age if sp_has_nursing_home else 0)
                if age == target_year or (sp_age == target_year and not has_nursing_home):
                    calc_savings += home_sale_price
            
        if has_car and age == car_dispose_age and car_sale_price > 0:
            calc_savings += car_sale_price
            lump_sum_income_this_year += car_sale_price
            
        if has_marriage and sp_has_car and sp_age == sp_car_dispose_age and sp_car_sale_price > 0:
            calc_savings += sp_car_sale_price
            lump_sum_income_this_year += sp_car_sale_price
        
        if ideco_lump_net_main > 0:
            lump_sum_income_this_year += ideco_lump_net_main
            if ideco_lump_dest == "特定口座へ(運用継続)":
                calc_taxable += ideco_lump_net_main
            elif ideco_lump_dest == "NISA枠優先 (あふれた分は特定口座へ)":
                nisa_room_annual = 3600000
                nisa_room_lifetime = max(0, 18000000 - main_nisa_lifetime_invested)
                nisa_add = min(ideco_lump_net_main, nisa_room_annual, nisa_room_lifetime)
                taxable_add = ideco_lump_net_main - nisa_add
                calc_nisa += nisa_add
                calc_taxable += taxable_add
                main_nisa_lifetime_invested += nisa_add
            else:
                calc_savings += ideco_lump_net_main
        
        if ideco_lump_net_sp > 0:
            lump_sum_income_this_year += ideco_lump_net_sp
            if sp_ideco_lump_dest == "特定口座へ(運用継続)":
                calc_taxable += ideco_lump_net_sp
            elif sp_ideco_lump_dest == "NISA枠優先 (あふれた分は特定口座へ)":
                nisa_room_annual = 3600000
                nisa_room_lifetime = max(0, 18000000 - sp_nisa_lifetime_invested)
                nisa_add = min(ideco_lump_net_sp, nisa_room_annual, nisa_room_lifetime)
                taxable_add = ideco_lump_net_sp - nisa_add
                calc_nisa += nisa_add
                calc_taxable += taxable_add
                sp_nisa_lifetime_invested += nisa_add
            else:
                calc_savings += ideco_lump_net_sp
                
        arr_lump_sum_income[i] = lump_sum_income_this_year
        calc_savings += annual_balance + w_taxable + w_nisa
            
        invested_this_year = 0
        if has_investment and age <= invest_end_age:
            invest_available_main = invest_monthly * 12
        else:
            invest_available_main = 0
            
        if sp_has_investment and sp_age <= sp_invest_end_age:
            invest_available_sp = sp_invest_monthly * 12
        else:
            invest_available_sp = 0
            
        total_invest_target = invest_available_main + invest_available_sp
        invest_available_from_savings = max(0, calc_savings - min_savings_amount)
        actual_invest = min(total_invest_target, invest_available_from_savings)
        
        if actual_invest > 0:
            ratio_main = invest_available_main / total_invest_target if total_invest_target > 0 else 0
            actual_main_invest = actual_invest * ratio_main
            actual_sp_invest = actual_invest - actual_main_invest
            
            if actual_main_invest > 0:
                if invest_strategy == "NISA優先 (年間360万/生涯1800万上限、超過分は特定口座)":
                    nisa_room_annual = 3600000
                    nisa_room_lifetime = max(0, 18000000 - main_nisa_lifetime_invested)
                    nisa_add = min(actual_main_invest, nisa_room_annual, nisa_room_lifetime)
                    taxable_add = actual_main_invest - nisa_add
                    calc_nisa += nisa_add
                    calc_taxable += taxable_add
                    main_nisa_lifetime_invested += nisa_add
                else:
                    calc_taxable += actual_main_invest
                    
            if actual_sp_invest > 0:
                if sp_invest_strategy == "NISA優先":
                    nisa_room_annual = 3600000
                    nisa_room_lifetime = max(0, 18000000 - sp_nisa_lifetime_invested)
                    nisa_add = min(actual_sp_invest, nisa_room_annual, nisa_room_lifetime)
                    taxable_add = actual_sp_invest - nisa_add
                    calc_nisa += nisa_add
                    calc_taxable += taxable_add
                    sp_nisa_lifetime_invested += nisa_add
                else:
                    calc_taxable += actual_sp_invest

            calc_savings -= actual_invest
        arr_invest_amount[i] = actual_invest

        shortfall = min_savings_amount - calc_savings
        
        if shortfall > 0:
            if deficit_order == "特定口座(世帯) → NISA(世帯) → 預貯金(最低維持額割れ)":
                order = [(calc_taxable, 'taxable'), (calc_nisa, 'nisa')]
            elif deficit_order == "NISA(世帯) → 特定口座(世帯) → 預貯金(最低維持額割れ)":
                order = [(calc_nisa, 'nisa'), (calc_taxable, 'taxable')]
            elif deficit_order == "預貯金を先に限界まで → 特定口座(世帯) → NISA(世帯)":
                available_savings = max(0, calc_savings)
                take_from_savings = min(available_savings, shortfall)
                calc_savings -= take_from_savings
                shortfall -= take_from_savings
                order = [(calc_taxable, 'taxable'), (calc_nisa, 'nisa')]
            else:
                order = []
                
            for val, name in order:
                if shortfall <= 0: break
                take = min(val, shortfall)
                if name == 'taxable': calc_taxable -= take
                elif name == 'nisa': calc_nisa -= take
                calc_savings += take
                shortfall -= take

        current_total_assets = calc_nisa + calc_taxable + calc_savings + curr_ideco_balance + curr_dc_balance + curr_sp_ideco_balance + curr_sp_dc_balance
        if current_total_assets <= 0 or (shortfall > 0 and (calc_nisa + calc_taxable + calc_savings) <= 0):
            is_depleted = True
        
        if is_depleted:
            arr_debt_housing[i] = arr_debt_housing[i-1] * (1 + housing_loan_rate) if i > 0 else arr_debt_housing[i]
            arr_debt_car[i] = arr_debt_car[i-1] * (1 + car_loan_rate) if i > 0 else arr_debt_car[i]
            arr_debt_reform[i] = arr_debt_reform[i-1] * (1 + reform_loan_rate) if i > 0 else arr_debt_reform[i]
            arr_debt_edu[i] = arr_debt_edu[i-1] * (1 + edu_loan_rate) if i > 0 else arr_debt_edu[i]
            arr_debt_balance[i] = arr_debt_housing[i] + arr_debt_car[i] + arr_debt_reform[i] + arr_debt_edu[i]
            
            arr_exp_house[i] -= (arr_reform_loan_pmts[i] + h_pmt_this_year)
            arr_exp_car[i] -= arr_car_loan_pmts[i]
            arr_exp_edu[i] -= arr_edu_loan_pmts[i]
            
            arr_annual_balance[i] = 0
            arr_net_income[i] = 0
            arr_total_exp[i] = 0
            arr_car_loan_pmts[i] = 0
            arr_edu_loan_pmts[i] = 0
            arr_reform_loan_pmts[i] = 0
            
            calc_nisa = 0
            calc_taxable = 0
            calc_savings = 0
            curr_ideco_balance = 0
            curr_dc_balance = 0
            curr_sp_ideco_balance = 0
            curr_sp_dc_balance = 0

        balances_nisa[i] = max(0, calc_nisa)
        balances_taxable[i] = max(0, calc_taxable)
        balances_savings[i] = max(0, calc_savings) 
        balances_ideco_dc[i] = max(0, curr_ideco_balance + curr_dc_balance + curr_sp_ideco_balance + curr_sp_dc_balance)
        total_assets[i] = balances_savings[i] + balances_nisa[i] + balances_taxable[i] + balances_ideco_dc[i]
        
        curr_main_nisa = balances_nisa[i]
        curr_main_taxable = balances_taxable[i]
        curr_main_savings = balances_savings[i]
        curr_sp_nisa = 0
        curr_sp_taxable = 0
        curr_sp_savings = 0

    depletion_age = next((ages[i] for i, total in enumerate(total_assets - balances_ideco_dc) if total <= 0), None)

    # --- UI Outputs ---
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        color_class = "red" if depletion_age else ""
        st.markdown(f'<div class="metric-card"><div class="metric-title">流動資産の枯渇年齢</div><div class="metric-value {color_class}">{depletion_age if depletion_age else "枯渇なし"}歳</div></div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="metric-card"><div class="metric-title">85歳時点の純資産(ローン控除後)</div><div class="metric-value">{(total_assets[ages.index(85) if 85 in ages else -1] - arr_debt_balance[ages.index(85) if 85 in ages else -1])/10000:,.1f}万円</div></div>', unsafe_allow_html=True)
    with col3:
        total_ret = sum([arr_net_income[i] for i, a in enumerate(ages) if a >= retirement_age])
        st.markdown(f'<div class="metric-card"><div class="metric-title">退職後の世帯累計手取り</div><div class="metric-value">{total_ret/10000:,.1f}万円</div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    with st.expander("📝 教育費の平均コスト目安表 (年額/万円) を見る"):
        st.table(pd.DataFrame([
            {"段階": "幼稚園", "公立": EDU_COST["幼稚園(公立)"], "私立": EDU_COST["幼稚園(私立)"]},
            {"段階": "小学校", "公立": EDU_COST["小学校(公立)"], "私立": EDU_COST["小学校(私立)"]},
            {"段階": "中学校", "公立": EDU_COST["中学校(公立)"], "私立": EDU_COST["中学校(私立)"]},
            {"段階": "高校", "公立": EDU_COST["高校(公立)"], "私立": EDU_COST["高校(私立)"]},
            {"段階": "大学", "公立": EDU_COST["大学(国公立)"], "私立": f'文系:{EDU_COST["大学(私立文系)"]} / 理系:{EDU_COST["大学(私立理系)"]}'}
        ]).set_index("段階"))

    st.markdown("### 📈 資産推移と年間収支 (単位：万円)")
    fig1 = plot_asset_transition(ages, balances_savings, balances_nisa, balances_taxable, balances_ideco_dc, arr_debt_housing, arr_debt_car, arr_debt_reform, arr_debt_edu, arr_annual_balance)
    st.plotly_chart(fig1, use_container_width=True, config={'displayModeBar': False})
    st.caption("※特定口座の資産残高は、簡易計算のため毎年課税（税引後リターン適用）されているものとして算出しています。")

    st.markdown("### 💰 年間収支の内訳比較（額面ベース / 単位：万円）")
    fig2 = plot_cashflow_breakdown(ages, years_count, arr_salary, arr_sp_salary, arr_pension, arr_child_allowance, arr_leave_benefit, arr_ret_income, arr_sp_pension, arr_withdrawal_amount, arr_exp_base, arr_exp_event, arr_exp_house, arr_exp_edu, arr_exp_car, arr_exp_nursing, arr_soc_ins, arr_sp_soc_ins, arr_inc_tax, arr_sp_inc_tax, arr_res_tax, arr_sp_res_tax, arr_ret_inc_tax, arr_ret_res_tax, arr_lump_sum_income)
    st.plotly_chart(fig2, use_container_width=True, config={'displayModeBar': False})

    st.markdown("### 📋 世帯キャッシュフロー表 (単位: 万円)")
    df = pd.DataFrame({
        '本人年齢': ages,
        '世帯手取り収入': arr_net_income / 10000,
        '退職金(手取り)': arr_ret_income / 10000,
        '一時収入(iDeCo等)': arr_lump_sum_income / 10000,
        '育休給付金': arr_leave_benefit / 10000,
        '児童手当': arr_child_allowance / 10000,
        '資産取崩': arr_withdrawal_amount / 10000,
        '積立投資額': arr_invest_amount / 10000,
        '基本生活費': arr_exp_base / 10000,
        '特別支出(イベント)': arr_exp_event / 10000,
        '住宅費': arr_exp_house / 10000,
        '教育費': arr_exp_edu / 10000,
        '自動車費': arr_exp_car / 10000,
        '老人ホーム費用': arr_exp_nursing / 10000,
        '住宅ローン控除': arr_mortgage_deduction / 10000,
        '社会保険料(世帯)': (arr_soc_ins + arr_sp_soc_ins) / 10000,
        '所得税(世帯)': (arr_inc_tax + arr_sp_inc_tax) / 10000,
        '住民税(世帯)': (arr_res_tax + arr_sp_res_tax) / 10000,
        '退職関連税(世帯)': (arr_ret_inc_tax + arr_ret_res_tax) / 10000,
        '世帯年間収支': arr_annual_balance / 10000,
        '住宅ローン残高': arr_debt_housing / 10000,
        '自動車ローン残高': arr_debt_car / 10000,
        'リフォームローン残高': arr_debt_reform / 10000,
        '教育ローン残高': arr_debt_edu / 10000,
        '負債合計': arr_debt_balance / 10000,
        '預貯金': balances_savings / 10000,
        '特定口座': balances_taxable / 10000,
        'NISA': balances_nisa / 10000,
        '世帯iDeCo/DC': balances_ideco_dc / 10000,
        '世帯総資産': total_assets / 10000,
        '純資産額': (total_assets - arr_debt_balance) / 10000
    }).set_index('本人年齢')

    style_func = lambda x: 'color: red' if isinstance(x, (int, float)) and x < 0 else ''
    try:
        st.dataframe(df.style.format("{:.1f}").map(style_func, subset=['世帯年間収支', '預貯金', '特定口座', 'NISA', '世帯総資産', '純資産額']), height=400, use_container_width=True)
    except AttributeError:
        st.dataframe(df.style.format("{:.1f}").applymap(style_func, subset=['世帯年間収支', '預貯金', '特定口座', 'NISA', '世帯総資産', '純資産額']), height=400, use_container_width=True)

    # --- アフィリエイト・ネクストアクション エリア ---
    st.markdown("---")
    st.markdown("### 💡 シミュレーション結果からのネクストアクション")
    st.write("あなたのシミュレーション結果に基づいた、おすすめのアクションです。")

    st.subheader("📱 まずは日々の家計を可視化しよう")
    st.write("精度の高いシミュレーションを行うには、現在の支出を正確に把握することが重要です。銀行やクレカと自動連携できる家計簿アプリがおすすめです。")
    st.link_button("人気の無料家計簿アプリをインストールする (PR)", "https://example.com/?a=kakeibo")

    col_btn1, col_btn2 = st.columns(2)
    
    with col_btn1:
        if depletion_age is not None:
            st.error("📉 **将来の資金不足が予測されます**")
            st.write("支出の見直しや、収入アップの検討が必要です。プロに相談するか、まずは固定費の削減から始めましょう。")
            st.link_button("👨‍💼 【無料】プロにライフプラン・家計を相談する (PR)", "https://example.com/?a=fp")
            st.link_button("📱 スマホ代を見直して固定費を下げる (PR)", "https://example.com/?a=sim")
            st.link_button("💼 転職エージェントに登録して収入アップを目指す (PR)", "https://example.com/?a=tenshoku")
        else:
            st.success("📈 **将来の資金計画は順調です！**")
            st.write("この調子で資産形成を進めましょう。NISAなどの非課税制度や、お得なポイント還元をフル活用するのがおすすめです。")
            st.link_button("🚀 ネット証券（NISA口座）を比較・開設する (PR)", "https://example.com/?a=sec")
            st.link_button("💳 積立投資でお得にポイントが貯まるクレカを作る (PR)", "https://example.com/?a=card")

    with col_btn2:
        has_mortgage_balance = arr_debt_housing.sum() > 0
        if has_mortgage_balance:
            st.info("🏠 **住宅ローンの見直しで数百万円浮くかも？**")
            st.write("住宅ローン残高があります。金利の低いネット銀行などに借り換えることで、毎月の返済額や総支払額を大きく減らせる可能性があります。")
            st.link_button("👉 モゲチェックで最適な借り換え金利を比較する (PR)", "https://example.com/?a=mogecheck")
            
        if (housing_type == "持ち家" or has_housing) and (depletion_age is not None or has_home_sale):
            st.warning("🏢 **ご自宅の価値を確認してみませんか？**")
            st.write("将来の資金不足や老人ホーム入居に向けて、現在の自宅の売却相場を知っておくことは資産形成において非常に重要です。")
            st.link_button("🏠 無料で不動産の一括査定を申し込む (PR)", "https://example.com/?a=fudosan")

except Exception as e:
    st.error(f"シミュレーション中にエラーが発生しました: {e}")
    st.code(traceback.format_exc())