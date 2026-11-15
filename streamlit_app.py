import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import traceback
import json
import base64
import zlib

# --- Page Config ---
st.set_page_config(page_title="最強ライフプランシミュレータ",page_icon="📊", layout="wide")

# --- CSS Styling ---
st.markdown("""
<style>
    /* カードデザイン設定 */
    .metric-card { background-color: #f8f9fa; border-radius: 10px; padding: 15px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); text-align: center; }
    .metric-title { font-weight: 600; color: #495057; margin-bottom: 5px; }
    .metric-value { font-size: 1.8rem; font-weight: 700; color: #007bff; }
    .metric-value.red { color: #dc3545; }

    /* 右上のメニュー（GitHub情報など）とフッターを非表示にする */
    [data-testid="stHeader"] { visibility: hidden; }
    [data-testid="stToolbar"] { visibility: hidden; }
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }

    /* スマホ向け（画面幅768px以下）のレイアウト調整 */
    @media (max-width: 768px) {
        /* スライダー誤操作防止用のスクロール安全地帯（右側の余白）を作成 */
        div[data-testid="stSlider"] {
            padding-right: 50px !important;
        }
        /* タイトルが不自然に改行されないようフォントサイズを最適化 */
        h1 {
            font-size: 1.5rem !important;
            line-height: 1.3 !important;
        }
    }
</style>
""", unsafe_allow_html=True)
# --- Data & Constants ---
EDU_COST = {
    "幼稚園(公立)": 23, "幼稚園(私立)": 53,
    "小学校(公立)": 35, "小学校(私立)": 166,
    "中学校(公立)": 50, "中学校(私立)": 143,
    "高校(公立)": 46,   "高校(私立)": 103,
    "国公立大学(4年)": 125, "私立大学文系(4年)": 175, "私立大学理系(4年)": 212,
    "短大(2年)": 100, "専門学校(2年)": 100
}

# --- Historical Market Return Data (1988 - 2025, Total Return) ---
HIST_YEARS = list(range(1988, 2026))
HIST_RETURNS = {
    "S&P500 (米国株式)": [
        0.166, 0.317, -0.031, 0.305, 0.076, 0.101, 0.013, 0.376, 0.230, 0.334, # 1988-1997
        0.286, 0.210, -0.091, -0.119, -0.221, 0.287, 0.109, 0.049, 0.158, 0.055, # 1998-2007 (2000-2002 ITバブル崩壊)
        -0.370, 0.265, 0.151, 0.021, 0.160, 0.324, 0.137, 0.014, 0.120, 0.218, # 2008-2017 (2008 リーマンショック -37%)
        -0.044, 0.315, 0.184, 0.287, -0.181, 0.263, 0.250, 0.120               # 2018-2025 (2022 インフレ株安 -18.1%)
    ],
    "オールカントリー (全世界株式 / MSCI ACWI)": [
        0.233, 0.176, -0.165, 0.199, -0.042, 0.249, 0.056, 0.195, 0.132, 0.150, # 1988-1997
        0.220, 0.268, -0.139, -0.162, -0.193, 0.340, 0.152, 0.108, 0.210, 0.117, # 1998-2007
        -0.422, 0.346, 0.127, -0.073, 0.161, 0.228, 0.042, -0.024, 0.079, 0.240, # 2008-2017 (2008 リーマンショック -42.2%)
        -0.094, 0.266, 0.163, 0.185, -0.184, 0.222, 0.175, 0.105               # 2018-2025
    ]
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

# --- Affiliate Links Master Config (ASP取得後にここを書き換えるだけで全箇所に反映) ---
AFFILIATE_LINKS = {
    "fp_consult": "https://example.com/?a=fp_consult",       # 🥇 1位: FP無料相談・保険見直し (マネーキャリア等)
    "mortgage": "https://example.com/?a=mogecheck",          # 🥈 2位: 住宅ローン比較・借換診断 (モゲチェック等)
    "securities": "https://example.com/?a=securities",       # 🥉 3位: ネット証券・NISA・待機資金運用 (SBI/楽天等)
    "credit_card": "https://example.com/?a=credit_card",     # 🥉 3位: クレカ積立用カード (三井住友カード等)
    "real_estate": "https://example.com/?a=real_estate",     # 4位: 不動産一括査定 (イエウール/すまいステップ等)
    "kakeibo_app": "https://example.com/?a=kakeibo_app",     # 5位: 無料家計簿アプリ (マネーフォワードME等)
    "career_up": "https://example.com/?a=career_up",         # 番外: 年収アップ・転職エージェント
    "furusato": "https://example.com/?a=furusato"            # 🎁 特枠: ふるさと納税 (ふるなび/さとふる等の定率案件)
}

# --- Helper Functions ---
def safe_number_input(label, min_value, max_value, default_value, step=1, **kwargs):
    """value（初期値）がmin_value〜max_valueの範囲外になってエラーで落ちるのを防ぐ安全な入力ウィジェット"""
    safe_val = max(min_value, min(max_value, default_value))
    return st.number_input(label, min_value=min_value, max_value=max_value, value=safe_val, step=step, **kwargs)

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

def calc_furusato_limit(salary, pension=0, ideco_yearly=0, fam_deduction=0, age=40, is_working=True):
    """現在の年収・家族構成・iDeCo掛金から、ふるさと納税の年間控除上限額（目安・円）を算出する"""
    if salary <= 0 and pension <= 0:
        return 0
    soc_ins, _, _ = calc_tax_and_soc(
        salary, pension, prev_salary=salary, prev_pension=pension,
        ideco_deduction=ideco_yearly, fam_deduction=fam_deduction, age=age, is_working=is_working
    )
    emp_inc = max(0, salary - calc_salary_deduction(salary))
    pen_ded = (1100000 if age >= 65 else 600000) if pension > 0 else 0
    pub_pen_inc = max(0, pension - pen_ded)
    total_inc = emp_inc + pub_pen_inc

    # 所得税の課税所得と適用税率の特定
    taxable_inc = max(0, total_inc - soc_ins - 480000 - ideco_yearly - fam_deduction)
    inc_rate = 0.05
    for limit, rate, _ in INCOME_TAX_BRACKETS:
        if taxable_inc <= limit:
            inc_rate = rate
            break

    # 住民税所得割額の算出
    fam_ded_res = fam_deduction * (330000 / 380000) if fam_deduction > 0 else 0
    taxable_res = max(0, total_inc - soc_ins - 430000 - ideco_yearly - fam_ded_res)
    res_tax_shotokuwari = taxable_res * 0.10
    if res_tax_shotokuwari <= 0:
        return 0

    # 特例控除上限(住民税所得割の20%)から逆算した寄付上限額
    denom = 0.90 - (inc_rate * 1.021)
    if denom <= 0:
        return 0
    limit_yen = (res_tax_shotokuwari * 0.20) / denom + 2000
    return int(limit_yen // 1000) * 1000


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
            for _ in range(12):
                interest = balance * r
                principal_payment = pmt_monthly - interest
                balance -= principal_payment
            schedule_balance[y] = max(0, balance)
            
    return schedule_pmt, schedule_balance

def get_ret_deduction(years):
    if years <= 20: return max(800000.0, 400000.0 * max(1, years))
    else: return 8000000.0 + 700000.0 * (years - 20)

def calc_retirement_tax_with_rules(current_event, past_events, person_name="本人"):
    """ 19年ルール・5年ルールの重複期間の調整（減額）を厳密に行った退職所得控除計算 """
    amount = current_event["amount"]
    years_current = max(1, current_event["end"] - current_event["start"])
    base_deduction = get_ret_deduction(years_current)
    
    overlap_deduction_total = 0.0
    apply_adjustment = False
    overlap_years_total = 0
    
    for past in past_events:
        years_diff = current_event["age"] - past["age"]
        if years_diff <= 0: continue
            
        is_19_year = (past["type"] == "company" and current_event["type"] == "ideco" and years_diff <= 19)
        is_5_year_1 = (past["type"] == "ideco" and current_event["type"] == "company" and years_diff <= 4)
        is_5_year_2 = (past["type"] == "company" and current_event["type"] == "company" and years_diff <= 4)
        
        if is_19_year or is_5_year_1 or is_5_year_2:
            overlap_start = max(current_event["start"], past["start"])
            overlap_end = min(current_event["end"], past["end"])
            overlap_years = max(0, overlap_end - overlap_start)
            
            if overlap_years > 0:
                apply_adjustment = True
                overlap_years_total += overlap_years
                overlap_deduction_total += get_ret_deduction(overlap_years)
                
    net_deduction = max(0.0, base_deduction - overlap_deduction_total)
    taxable = max(0.0, (amount - net_deduction) / 2)
    inc_tax = calc_income_tax(taxable)
    res_tax = taxable * 0.10
    
    calc_formula = f"基本枠:{base_deduction/10000:,.1f}万"
    if apply_adjustment and overlap_years_total > 0:
        rule_name = "重複調整"
        if current_event["type"] == "ideco": rule_name = "19年ルール"
        elif current_event["type"] == "company": rule_name = "5年ルール"
        calc_formula += f" ({rule_name}適用: 重複{overlap_years_total}年分 -{overlap_deduction_total/10000:,.1f}万減額)"

    detail = {
        "受取人": person_name,
        "年齢": current_event["age"],
        "種類": current_event.get("label", "iDeCo" if current_event["type"] == "ideco" else "会社退職金"),
        "額面金額": f"{amount/10000:,.1f}万円",
        "対象年数": f"{years_current}年",
        "控除計算式・重複調整": calc_formula,
        "適用控除額": f"{net_deduction/10000:,.1f}万円",
        "課税対象": f"{taxable/10000:,.1f}万円",
        "税額(所得+住民)": f"{(inc_tax + res_tax)/10000:,.1f}万円",
        "手取り額": f"{(amount - inc_tax - res_tax)/10000:,.1f}万円"
    }
    return inc_tax, res_tax, detail

def calc_same_year_retirement_tax(events, person_name="本人"):
    total_amount = sum(e["amount"] for e in events)
    min_start = min(e["start"] for e in events)
    max_end = max(e["end"] for e in events)
    years = max(1, max_end - min_start)
    
    deduction = get_ret_deduction(years)
    taxable = max(0, (total_amount - deduction) / 2)
    inc_tax = calc_income_tax(taxable)
    res_tax = taxable * 0.10
    
    types = " + ".join([e.get("label", "iDeCo" if e["type"]=="ideco" else "会社退職金") for e in events])
    
    detail = {
        "受取人": person_name,
        "年齢": events[0]["age"],
        "種類": f"同年合算 ({types})",
        "額面金額": f"{total_amount/10000:,.1f}万円",
        "対象年数": f"{years}年 (合算)",
        "控除計算式・重複調整": f"合算期間で算出 (基本枠:{deduction/10000:,.1f}万)",
        "適用控除額": f"{deduction/10000:,.1f}万円",
        "課税対象": f"{taxable/10000:,.1f}万円",
        "税額(所得+住民)": f"{(inc_tax + res_tax)/10000:,.1f}万円",
        "手取り額": f"{(total_amount - inc_tax - res_tax)/10000:,.1f}万円"
    }
    return inc_tax, res_tax, detail
    
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

# --- URL State Management (保存と読み込み) ---
def encode_state(state_dict):
    try:
        json_str = json.dumps(state_dict)
        compressed = zlib.compress(json_str.encode('utf-8'))
        return base64.urlsafe_b64encode(compressed).decode('utf-8')
    except Exception:
        return ""

def decode_state(encoded_str):
    try:
        compressed = base64.urlsafe_b64decode(encoded_str.encode('utf-8'))
        json_str = zlib.decompress(compressed).decode('utf-8')
        return json.loads(json_str)
    except Exception:
        return {}

if 'loaded_state' not in st.session_state:
    query_params = st.query_params
    if 'd' in query_params:
        st.session_state['loaded_state'] = decode_state(query_params['d'])
    else:
        st.session_state['loaded_state'] = {}

def get_val(key, default):
    # 過去のURLに無い新しい項目は、自動的にdefault値を使ってエラーを防ぐ（後方互換性）
    return st.session_state['loaded_state'].get(key, default)

def get_pct_val(key, default_pct):
    """URL保存時に /100 された小数(0.10等)で保存されていても、画面表示用の%(10.0等)に自動復元する関数"""
    v = float(get_val(key, default_pct))
    # もし保存されていた値が 1.0 以下（例: 0.05 や 0.10）で、本来の初期値が 1.0 より大きい（例: 5.0 や 10.0）なら100倍して戻す
    if 0 < abs(v) <= 1.0 and abs(default_pct) > 1.0:
        return round(v * 100.0, 4)
    return v

# --- Plotting Functions ---
def format_man_oku_val(val_man, show_decimal=False):
    """万円単位の数値を『〇億〇,〇〇〇万円』（小数点なし）の文字列に変換する補助関数"""
    if pd.isna(val_man):
        return "0万円"
    sign = "-" if val_man < 0 else ""
    abs_val = abs(float(val_man))
    
    if not show_decimal:
        abs_int = int(round(abs_val))
        if abs_int == 0:
            return "0万円"
        oku = abs_int // 10000
        man = abs_int % 10000
        if oku > 0:
            return f"{sign}{oku}億{man:,}万円" if man > 0 else f"{sign}{oku}億円"
        else:
            return f"{sign}{man:,}万円"
    else:
        oku = int(abs_val // 10000)
        man = abs_val % 10000
        if oku > 0:
            return f"{sign}{oku}億{man:,.1f}万円" if man >= 0.05 else f"{sign}{oku}億円"
        else:
            return f"{sign}{man:,.1f}万円"

def format_man_oku_array(arr_yen, show_decimal=False):
    """円単位の配列を受け取り、ホバー表示用の『〇億〇,〇〇〇万円』文字列リストを返す"""
    arr_man = np.asarray(arr_yen) / 10000.0
    return [format_man_oku_val(v, show_decimal) for v in arr_man]

def get_jp_axis_ticks(min_man, max_man):
    """Y軸の最小・最大値(万円)から、『k』を使わない自然な日本語目盛り(億・万円)を生成する"""
    span = max_man - min_man
    if span <= 0:
        return None, None
    raw_step = span / 6.0
    nice_steps = [50, 100, 200, 250, 500, 1000, 2000, 2500, 5000, 10000, 20000, 25000, 50000, 100000]
    step = next((s for s in nice_steps if s >= raw_step), 100000)
    
    start_tick = int(np.floor(min_man / step)) * step
    end_tick = int(np.ceil(max_man / step)) * step
    
    tickvals = list(range(start_tick, end_tick + step, step))
    ticktext = []
    for v in tickvals:
        if v == 0:
            ticktext.append("0万円")
        else:
            sign = "-" if v < 0 else ""
            av = abs(v)
            oku = av // 10000
            man = av % 10000
            if oku > 0:
                ticktext.append(f"{sign}{oku}億{man:,}万円" if man > 0 else f"{sign}{oku}億円")
            else:
                ticktext.append(f"{sign}{man:,}万円")
    return tickvals, ticktext


def plot_monte_carlo(ages, p90, p50, p10, p10_no_defense=None, view_mode="all"):
    fig = go.Figure()
    
    # ★③「暴落対策のプラス効果（差額）をクローズアップ」モード
    if view_mode == "diff" and p10_no_defense is not None:
        diff_yen = p10 - p10_no_defense
        diff_man = diff_yen / 10000.0
        fig.add_trace(go.Scatter(
            x=ages, y=diff_man, mode='lines', name='暴落対策による純資産プラス効果 (対策あり − 対策なし)',
            line=dict(color='#2ca02c', width=3),
            fill='tozeroy',
            fillcolor='rgba(44, 160, 44, 0.2)',
            customdata=[("+" if v > 0 else "") + format_man_oku_val(v) for v in diff_man],
            hovertemplate='対策効果: %{customdata}<extra></extra>'
        ))
        fig.add_hline(y=0, line_dash="solid", line_color="black", line_width=1)
        
        min_y = min(0, float(np.min(diff_man)))
        max_y = max(100, float(np.max(diff_man)) * 1.1)
        t_vals, t_text = get_jp_axis_ticks(min_y, max_y)
        
        fig.update_xaxes(fixedrange=True, ticksuffix="歳")
        if t_vals:
            fig.update_yaxes(fixedrange=True, tickvals=t_vals, ticktext=t_text, range=[min(t_vals), max(t_vals)])
        else:
            fig.update_yaxes(fixedrange=True, tickformat=",d", ticksuffix="万円")
            
        fig.update_layout(title="🛡️ 暴落対策による純資産の改善額推移（悲観シナリオ：対策あり − 対策なし）", hovermode="x unified", height=420, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        return fig

    # ★①通常全体表示("all") ＆ ②対数風圧縮スケール("symlog")
    scale_base = 1000.0 # 1,000万円を基準に対数圧縮
    def trans_y(arr_yen):
        y_man = np.asarray(arr_yen) / 10000.0
        if view_mode == "symlog":
            return np.sign(y_man) * np.log10(1.0 + np.abs(y_man) / scale_base)
        return y_man

    # 帯の描画 (p10 to p90)
    fig.add_trace(go.Scatter(
        x=ages + ages[::-1],
        y=np.concatenate([trans_y(p90), trans_y(p10[::-1])]),
        fill='toself',
        fillcolor='rgba(0,176,246,0.15)',
        line=dict(color='rgba(255,255,255,0)'),
        name='上位10%〜下位10%のブレ幅',
        hoverinfo='skip',
        showlegend=True
    ))
    
    # p90 (楽観)
    fig.add_trace(go.Scatter(
        x=ages, y=trans_y(p90), mode='lines', name='楽観シナリオ (上位10%)',
        line=dict(color='#2ca02c', width=2, dash='dot'),
        customdata=format_man_oku_array(p90),
        hovertemplate='%{customdata}'
    ))

    # p50 (中央値)
    fig.add_trace(go.Scatter(
        x=ages, y=trans_y(p50), mode='lines', name='標準シナリオ (中央値)',
        line=dict(color='#1f77b4', width=3),
        customdata=format_man_oku_array(p50),
        hovertemplate='%{customdata}'
    ))
    
    # 暴落対策がOFFだった場合の悲観シナリオ比較ライン
    if p10_no_defense is not None:
        fig.add_trace(go.Scatter(
            x=ages, y=trans_y(p10_no_defense), mode='lines', name='悲観シナリオ (もし暴落対策がなかった場合)',
            line=dict(color='#7f7f7f', width=2.5, dash='dot'),
            customdata=format_man_oku_array(p10_no_defense),
            hovertemplate='%{customdata}'
        ))

    # p10 (悲観・暴落想定)
    fill_mode = 'tonexty' if (p10_no_defense is not None and view_mode == "symlog") else None
    fig.add_trace(go.Scatter(
        x=ages, y=trans_y(p10), mode='lines', name='悲観シナリオ (下位10% / 暴落対策あり)',
        line=dict(color='#d62728', width=3, dash='dash'),
        fill=fill_mode,
        fillcolor='rgba(44, 160, 44, 0.15)' if fill_mode else None,
        customdata=format_man_oku_array(p10),
        hovertemplate='%{customdata}'
    ))
    
    # ゼロライン
    fig.add_hline(y=0, line_dash="solid", line_color="black", line_width=1)
    
    fig.update_xaxes(fixedrange=True, ticksuffix="歳")

    if view_mode == "symlog":
        # 対数圧縮スケール用の目盛り生成
        raw_ticks = [-5000, -2000, -1000, -500, 0, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000, 500000]
        all_man = np.concatenate([p90/10000, p10/10000] + ([p10_no_defense/10000] if p10_no_defense is not None else []))
        min_m, max_m = min(0, float(np.min(all_man))), max(1000, float(np.max(all_man)))
        valid_ticks = [v for v in raw_ticks if min_m * 1.2 <= v <= max_m * 1.5]
        if 0 not in valid_ticks: valid_ticks.append(0)
        valid_ticks = sorted(list(set(valid_ticks)))
        t_vals = [float(np.sign(v) * np.log10(1.0 + abs(v) / scale_base)) for v in valid_ticks]
        t_text = [format_man_oku_val(v) if v != 0 else "0万円" for v in valid_ticks]
        fig.update_yaxes(fixedrange=True, tickvals=t_vals, ticktext=t_text)
    else:
        all_vals = [p90/10000, p50/10000, p10/10000]
        if p10_no_defense is not None:
            all_vals.append(p10_no_defense/10000)
            
        min_y = min(0, float(np.min(all_vals)))
        max_y = max(500, float(np.max(all_vals)) * 1.05)
        t_vals, t_text = get_jp_axis_ticks(min_y, max_y)
        
        if t_vals:
            fig.update_yaxes(fixedrange=True, tickvals=t_vals, ticktext=t_text, range=[min(t_vals), max(t_vals)])
        else:
            fig.update_yaxes(fixedrange=True, tickformat=",d", ticksuffix="万円")
        
    fig.update_layout(title="モンテカルロ・シミュレーション (300回試行) による純資産推移", hovermode="x unified", height=420, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    return fig


def plot_asset_transition(ages, balances_savings, balances_dry_powder, balances_nisa, balances_taxable, balances_ideco_dc, arr_debt_housing, arr_debt_car, arr_debt_reform, arr_debt_edu, arr_annual_balance, arr_spot_invest=None):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    def add_asset_bar(y_yen, name, color, prefix=""):
        # 全期間で0円の項目は追加しない
        if np.all(np.abs(y_yen) < 1):
            return
        y_man = y_yen / 10000.0
        # 0円の年はNaNにしてホバー表示から隠す
        y_plot = np.where(np.abs(y_man) >= 0.5, y_man, np.nan)
        hover_str = f"{prefix}%{{customdata}}" if prefix else "%{customdata}"
        fig.add_trace(go.Bar(
            x=ages, y=y_plot, name=name, marker_color=color,
            customdata=format_man_oku_array(y_yen),
            hovertemplate=hover_str
        ), secondary_y=False)

    add_asset_bar(balances_savings, "世帯 預貯金(生活防衛)", '#2ca02c')
    add_asset_bar(balances_dry_powder, "暴落待機資金", '#00b4d8')
    add_asset_bar(balances_nisa, "世帯 NISA", '#ff7f0e')
    add_asset_bar(balances_taxable, "世帯 特定口座", '#1f77b4')
    add_asset_bar(balances_ideco_dc, "世帯 iDeCo/DC", '#9467bd')

    add_asset_bar(-arr_debt_housing, "住宅ローン残高", '#7f7f7f', "住宅ローン: ")
    add_asset_bar(-arr_debt_car, "自動車ローン残高(世帯)", '#bcbd22', "自動車ローン: ")
    add_asset_bar(-arr_debt_reform, "リフォームローン残高", '#e377c2', "リフォームローン: ")
    add_asset_bar(-arr_debt_edu, "教育ローン残高", '#17becf', "教育ローン: ")

    # 暴落時スポット投資が発動した年に金色の星マーカーを表示
    total_pos_bars = (np.maximum(0, balances_savings) + balances_dry_powder + balances_nisa + balances_taxable + balances_ideco_dc) / 10000
    if arr_spot_invest is not None and arr_spot_invest.sum() > 0:
        spot_indices = [idx for idx, val in enumerate(arr_spot_invest) if val > 0]
        spot_ages = [ages[idx] for idx in spot_indices]
        spot_y = [total_pos_bars[idx] * 1.04 + 100 for idx in spot_indices]
        spot_vals = [format_man_oku_val(arr_spot_invest[idx] / 10000) for idx in spot_indices]
        fig.add_trace(go.Scatter(
            x=spot_ages,
            y=spot_y,
            mode='markers',
            name='🎯 暴落スポット投資発動',
            marker=dict(symbol='star', size=14, color='#ffd700', line=dict(color='#d62728', width=1.5)),
            customdata=spot_vals,
            hovertemplate='🎯 スポット投資発動: %{customdata}投入<extra></extra>'
        ), secondary_y=False)

    fig.add_trace(go.Scatter(x=ages, y=arr_annual_balance/10000, name="世帯単年収支(取崩前)", mode='lines', line=dict(color='#d62728', width=3, dash='dot'), customdata=format_man_oku_array(arr_annual_balance), hovertemplate='%{customdata}'), secondary_y=True)

    total_neg_bars = -(arr_debt_housing + arr_debt_car + arr_debt_reform + arr_debt_edu) / 10000
    min_y1 = min(0, float(np.min(total_neg_bars)), float(np.min(balances_savings / 10000)))
    max_y1 = max(1000, float(np.max(total_pos_bars)) * 1.08)
    t_vals1, t_text1 = get_jp_axis_ticks(min_y1, max_y1)

    fig.update_xaxes(fixedrange=True, ticksuffix="歳")
    if t_vals1:
        fig.update_yaxes(fixedrange=True, tickvals=t_vals1, ticktext=t_text1, secondary_y=False)
    else:
        fig.update_yaxes(fixedrange=True, tickformat=",d", ticksuffix="万円", secondary_y=False)
    fig.update_yaxes(fixedrange=True, tickformat=",d", ticksuffix="万円", secondary_y=True)
    
    fig.update_layout(dragmode=False, barmode='relative', hovermode="x unified", height=500, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    return fig

def plot_historical_backtest(ages, net_main, net_no_def, net_sub, main_name, sub_name, start_year, view_mode="all"):
    fig = go.Figure()
    
    # 歴史上の年号ラベルを作成（例: "45歳 (2008年相場)"）
    hist_len = len(HIST_YEARS)
    start_idx = HIST_YEARS.index(start_year) if start_year in HIST_YEARS else 0
    mapped_years = [HIST_YEARS[(start_idx + i) % hist_len] for i in range(len(ages))]
    
    if view_mode == "diff" and net_no_def is not None:
        diff_man = (net_main - net_no_def) / 10000.0
        fig.add_trace(go.Scatter(
            x=ages, y=diff_man, mode='lines', name='暴落対策による純資産プラス効果 (対策あり − 対策なし)',
            line=dict(color='#2ca02c', width=3),
            fill='tozeroy',
            fillcolor='rgba(44, 160, 44, 0.2)',
            customdata=[f"{ ('+' if v > 0 else '') + format_man_oku_val(v) } （{yr}年相場）" for v, yr in zip(diff_man, mapped_years)],
            hovertemplate='対策効果: %{customdata}<extra></extra>'
        ))
        fig.add_hline(y=0, line_dash="solid", line_color="black", line_width=1)
        min_y, max_y = min(0, float(np.min(diff_man))), max(100, float(np.max(diff_man)) * 1.1)
        t_vals, t_text = get_jp_axis_ticks(min_y, max_y)
        fig.update_xaxes(fixedrange=True, ticksuffix="歳")
        if t_vals:
            fig.update_yaxes(fixedrange=True, tickvals=t_vals, ticktext=t_text, range=[min(t_vals), max(t_vals)])
        else:
            fig.update_yaxes(fixedrange=True, tickformat=",d", ticksuffix="万円")
        fig.update_layout(title=f"🛡️ 暴落対策による純資産の改善額推移（{main_name} / {start_year}年相場スタート）", hovermode="x unified", height=420, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        return fig

    scale_base = 1000.0
    def trans_y(arr_yen):
        y_man = np.asarray(arr_yen) / 10000.0
        if view_mode == "symlog":
            return np.sign(y_man) * np.log10(1.0 + np.abs(y_man) / scale_base)
        return y_man

    # 比較用のもう一方のインデックス（S&P500選択時はオルカン、オルカン選択時はS&P500）
    fig.add_trace(go.Scatter(
        x=ages, y=trans_y(net_sub), mode='lines', name=f'比較: {sub_name} (暴落対策あり)',
        line=dict(color='#ff7f0e', width=2, dash='dash'),
        customdata=format_man_oku_array(net_sub),
        hovertemplate='%{customdata}'
    ))

    # 暴落対策がなかった場合の比較ライン
    if net_no_def is not None:
        fig.add_trace(go.Scatter(
            x=ages, y=trans_y(net_no_def), mode='lines', name=f'{main_name} (もし暴落対策がなかった場合)',
            line=dict(color='#7f7f7f', width=2.5, dash='dot'),
            customdata=format_man_oku_array(net_no_def),
            hovertemplate='%{customdata}'
        ))

    # メインのインデックス推移
    fill_mode = 'tonexty' if net_no_def is not None else None
    fig.add_trace(go.Scatter(
        x=ages, y=trans_y(net_main), mode='lines', name=f'{main_name} (暴落対策あり)',
        line=dict(color='#1f77b4', width=3.5),
        fill=fill_mode,
        fillcolor='rgba(44, 160, 44, 0.15)' if fill_mode else None,
        customdata=[f"{val_str} （{yr}年相場）" for val_str, yr in zip(format_man_oku_array(net_main), mapped_years)],
        hovertemplate='%{customdata}'
    ))

    fig.add_hline(y=0, line_dash="solid", line_color="black", line_width=1)
    fig.update_xaxes(fixedrange=True, ticksuffix="歳")

    all_man = np.concatenate([net_main/10000, net_sub/10000] + ([net_no_def/10000] if net_no_def is not None else []))
    if view_mode == "symlog":
        raw_ticks = [-5000, -2000, -1000, -500, 0, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000, 500000]
        min_m, max_m = min(0, float(np.min(all_man))), max(1000, float(np.max(all_man)))
        valid_ticks = [v for v in raw_ticks if min_m * 1.2 <= v <= max_m * 1.5]
        if 0 not in valid_ticks: valid_ticks.append(0)
        valid_ticks = sorted(list(set(valid_ticks)))
        t_vals = [float(np.sign(v) * np.log10(1.0 + abs(v) / scale_base)) for v in valid_ticks]
        t_text = [format_man_oku_val(v) if v != 0 else "0万円" for v in valid_ticks]
        fig.update_yaxes(fixedrange=True, tickvals=t_vals, ticktext=t_text)
    else:
        min_y = min(0, float(np.min(all_man)))
        max_y = max(500, float(np.max(all_man)) * 1.05)
        t_vals, t_text = get_jp_axis_ticks(min_y, max_y)
        if t_vals:
            fig.update_yaxes(fixedrange=True, tickvals=t_vals, ticktext=t_text, range=[min(t_vals), max(t_vals)])
        else:
            fig.update_yaxes(fixedrange=True, tickformat=",d", ticksuffix="万円")

    fig.update_layout(title=f"📜 過去実績バックテスト推移（{start_year}年相場スタート：S&P500 vs オールカントリー）", hovermode="x unified", height=420, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    return fig


def plot_cashflow_breakdown(ages, years_count, arr_salary, arr_sp_salary, arr_pension, arr_child_allowance, arr_leave_benefit, arr_ret_income, arr_sp_pension, arr_withdrawal_amount, arr_exp_base, arr_exp_support, arr_exp_ideco_savings_ins, arr_exp_insurance, arr_exp_event, arr_exp_house, arr_exp_edu, arr_exp_car, arr_exp_nursing, arr_soc_ins, arr_sp_soc_ins, arr_inc_tax, arr_sp_inc_tax, arr_res_tax, arr_sp_res_tax, arr_ret_inc_tax, arr_ret_res_tax, arr_lump_sum_income):
    fig = go.Figure()

    base_inc = np.zeros(years_count)
    base_exp = np.zeros(years_count)

    def add_cf_bar(arr_yen, name, group, base_arr, color):
        # 全期間を通して0円の項目は凡例・グラフ自体に追加しない
        if np.all(arr_yen < 5000):
            return
        y_man = arr_yen / 10000.0
        active_mask = y_man >= 0.5
        # その年の金額が0円（0.5万円未満）の箇所は y も base も NaN にしてポップアップから完全に消す
        y_plot = np.where(active_mask, y_man, np.nan)
        base_plot = np.where(active_mask, base_arr, np.nan)
        fig.add_trace(go.Bar(
            x=ages,
            y=y_plot,
            name=name,
            offsetgroup=group,
            base=base_plot,
            customdata=format_man_oku_array(arr_yen),
            marker_color=color,
            hovertemplate='%{customdata}'
        ))
        base_arr += np.where(active_mask, y_man, 0.0)

    # 収入グループ (offsetgroup=1)
    add_cf_bar(arr_salary, "本人 給与収入", 1, base_inc, '#1f77b4')
    add_cf_bar(arr_sp_salary, "配偶者 給与収入", 1, base_inc, '#76b7b2')
    add_cf_bar(arr_pension, "本人 年金・保険等", 1, base_inc, '#2ca02c')
    add_cf_bar(arr_ret_income, "退職金(手取り)", 1, base_inc, '#17becf')
    add_cf_bar(arr_leave_benefit, "育休給付金(非課税)", 1, base_inc, '#9edae5')
    add_cf_bar(arr_child_allowance, "児童手当", 1, base_inc, '#ff9896')
    add_cf_bar(arr_lump_sum_income, "一時収入(iDeCo等)", 1, base_inc, '#ff7f0e')
    add_cf_bar(arr_sp_pension, "配偶者 年金・iDeCo等", 1, base_inc, '#98df8a')
    add_cf_bar(arr_withdrawal_amount, "資産取崩・赤字補填", 1, base_inc, '#e377c2')

    # 支出グループ (offsetgroup=2)
    add_cf_bar(arr_exp_base, "基本生活費", 2, base_exp, '#d62728')
    add_cf_bar(arr_exp_support, "子どもへの仕送り", 2, base_exp, '#ff9896')
    add_cf_bar(arr_exp_ideco_savings_ins, "iDeCo・貯蓄型保険掛金", 2, base_exp, '#aec7e8')
    add_cf_bar(arr_exp_insurance, "民間保険料(固定費)", 2, base_exp, '#e377c2')
    add_cf_bar(arr_exp_event, "特別支出(イベント)", 2, base_exp, '#ffbb78')
    add_cf_bar(arr_exp_house, "住宅費", 2, base_exp, '#8c564b')
    add_cf_bar(arr_exp_edu, "教育費", 2, base_exp, '#bcbd22')
    add_cf_bar(arr_exp_car, "自動車費(世帯)", 2, base_exp, '#7f7f7f')
    add_cf_bar(arr_exp_nursing, "老人ホーム費用(世帯)", 2, base_exp, '#c49c94')
    add_cf_bar(arr_soc_ins, "本人 社会保険料", 2, base_exp, '#ff7f0e')
    add_cf_bar(arr_sp_soc_ins, "配偶者 社会保険料", 2, base_exp, '#ffbb78')
    add_cf_bar(arr_inc_tax, "本人 所得税", 2, base_exp, '#9467bd')
    add_cf_bar(arr_sp_inc_tax, "配偶者 所得税", 2, base_exp, '#c5b0d5')
    add_cf_bar(arr_res_tax, "本人 住民税", 2, base_exp, '#17becf')
    add_cf_bar(arr_sp_res_tax, "配偶者 住民税", 2, base_exp, '#9edae5')
    add_cf_bar(arr_ret_inc_tax + arr_ret_res_tax, "退職関連税(世帯)", 2, base_exp, '#000000')

    max_cf = max(500, float(np.max(base_inc)), float(np.max(base_exp)))
    t_vals_cf, t_text_cf = get_jp_axis_ticks(0, max_cf)

    fig.update_xaxes(fixedrange=True, ticksuffix="歳")
    if t_vals_cf:
        fig.update_yaxes(fixedrange=True, tickvals=t_vals_cf, ticktext=t_text_cf)
    else:
        fig.update_yaxes(fixedrange=True, tickformat=",d", ticksuffix="万円")
    fig.update_layout(dragmode=False, barmode='group', hovermode="x unified", height=650, legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5))
    return fig

# --- UI Inputs ---
col_title, col_save = st.columns([7, 3])
with col_title:
    st.title("📊 最強ライフプランシミュレータ")
with col_save:
    st.write("") # ボタンの縦位置合わせ用の余白
    st.write("")
    if st.button("💾 設定をURLに保存", type="primary", use_container_width=True, help="現在の入力状態をURLとして保存します"):
        st.session_state['save_requested'] = True

tabs = st.tabs(["1. 本人", "2. 配偶者", "3. 家族・教育", "4. 住宅・車", "5. 資産・運用", "6. 年金・保険", "7. その他", "8. 老人ホーム"])

with tabs[0]:
    st.header("本人の基本・収入・退職")
    col1, col2 = st.columns(2)
    with col1:
        current_age = st.number_input("現在の年齢", min_value=20, max_value=80, value=get_val("current_age", 40), step=1)
        life_expectancy = st.number_input("シミュレーション終了年齢", min_value=50, max_value=110, value=get_val("life_expectancy", 90), step=1)
        employment_start_age = st.number_input("入社(就業開始)年齢", min_value=15, max_value=65, value=get_val("employment_start_age", 22), step=1)
        is_working = st.radio("現在の就業状況(本人)", ["就業中（給与収入あり）", "既に退職済み（早期リタイア等）"], index=0 if get_val("is_working", "就業中（給与収入あり）") == "就業中（給与収入あり）" else 1)
    
    with col2:
        if is_working == "就業中（給与収入あり）":
            gross_income = st.number_input("現在の額面年収（万円）", value=int(get_val("gross_income", 6000000)/10000), step=10) * 10000
            salary_growth = st.number_input("毎年の昇給率 (%)", min_value=0.0, max_value=30.0, value=get_val("salary_growth", 0.03)*100, step=0.1) / 100

            has_salary_cap = st.checkbox("昇給の頭打ち（上限額・停止年齢）を設定する(本人)", value=get_val("has_salary_cap", False))
            if has_salary_cap:
                saved_cap = get_val("salary_cap_amount", 8000000)
                default_cap = 8000000 if saved_cap >= 1000000000 else saved_cap
                salary_cap_amount = st.number_input("昇給上限キャップ（額面・万円）(本人)", min_value=100, max_value=10000, value=int(default_cap/10000), step=10) * 10000
                
                saved_plateau = get_val("salary_plateau_age", 50)
                default_plateau = 50 if saved_plateau >= 1000 else saved_plateau
                salary_plateau_age = safe_number_input("昇給がストップする年齢(本人)", min_value=current_age, max_value=100, default_value=default_plateau, step=1)
            else:
                salary_cap_amount = 1000000000
                salary_plateau_age = 1000

            has_salary_decrease = st.checkbox("役職定年等による給与減額あり(本人)", value=get_val("has_salary_decrease", False))
            if has_salary_decrease:
                salary_decrease_age = st.number_input("減額される年齢", min_value=current_age, max_value=85, value=get_val("salary_decrease_age", 55), step=1)
                salary_decrease_rate = st.number_input("減額率 (%)", min_value=10, max_value=80, value=int(get_val("salary_decrease_rate", 0.3)*100), step=1) / 100
            else:
                salary_decrease_age = 1000
                salary_decrease_rate = 0.0
                
            retirement_age = safe_number_input("退職予定年齢(会社の退職金)", min_value=20, max_value=100, default_value=get_val("retirement_age", 60), step=1)
            retirement_allowance = st.number_input("会社の退職金見込額（万円）", value=int(get_val("retirement_allowance", 5000000)/10000), step=10) * 10000
            actual_is_working = True
        else:
            gross_income = 0
            salary_growth = 0
            has_salary_cap = False
            salary_cap_amount = 1000000000
            salary_plateau_age = 1000
            salary_decrease_age = 1000
            salary_decrease_rate = 0.0
            retirement_age = safe_number_input("退職した年齢(退職金受給済の場合は現在の年齢)", min_value=20, max_value=100, default_value=get_val("retirement_age", current_age), step=1)
            retirement_allowance = st.number_input("これから受け取る予定の退職金（既に受取済・なしの場合は0）", value=int(get_val("retirement_allowance", 0)/10000), step=10) * 10000
            actual_is_working = False
            
        ret_lump_dest_opts = ["預貯金へ", "NISA枠優先 (あふれた分は特定口座へ)", "特定口座へ(運用継続)"]
        saved_ret_dest = get_val("ret_lump_dest", "預貯金へ")
        ret_lump_dest = st.radio("退職金の入金先(本人)", ret_lump_dest_opts, index=ret_lump_dest_opts.index(saved_ret_dest) if saved_ret_dest in ret_lump_dest_opts else 0)
            
    st.divider()
    has_post_retirement_job = st.checkbox("退職後のアルバイト・副業収入あり(本人)", value=get_val("has_post_retirement_job", False))
    if has_post_retirement_job:
        post_retirement_income = st.number_input("退職後の収入(万円/月)", value=int(get_val("post_retirement_income", 100000)/10000), step=1) * 10000
        post_retirement_end_age = st.number_input("退職後の収入が続く年齢(本人)", min_value=retirement_age, max_value=100, value=get_val("post_retirement_end_age", max(retirement_age, 65)), step=1)
    else:
        post_retirement_income = 0
        post_retirement_end_age = 0

    if actual_is_working and gross_income > 0:
        est_furusato_main = calc_furusato_limit(gross_income, age=current_age, is_working=True)
        if est_furusato_main >= 10000:
            st.caption(f"🎁 **ふるさと納税の上限目安：** 現在の年収（{int(gross_income/10000)}万円）での年間寄付上限は **約 {est_furusato_main/10000:,.1f} 万円**（{est_furusato_main:,}円）です（iDeCoや扶養控除は下部サマリーで自動反映）。[👉 人気のふるさと納税サイトで返礼品を見る (PR)]({AFFILIATE_LINKS['furusato']})")

with tabs[1]:
    st.header("配偶者の基本・収入・退職")
    has_marriage = st.checkbox("配偶者あり", value=get_val("has_marriage", False))
    if has_marriage:
        col1, col2 = st.columns(2)
        with col1:
            sp_age_diff = st.number_input("配偶者との年齢差(年下ならマイナス)", min_value=-20, max_value=20, value=get_val("sp_age_diff", 0), step=1)
            marriage_age = st.number_input("結婚する本人の年齢(結婚済みなら現在年齢以下)", min_value=20, max_value=80, value=get_val("marriage_age", current_age), step=1)
            wedding_cost = st.number_input("結婚式等費用（万円）", value=int(get_val("wedding_cost", 3000000)/10000), step=10) * 10000
            sp_employment_start_age = st.number_input("配偶者の入社(就業開始)年齢", min_value=15, max_value=65, value=get_val("sp_employment_start_age", 22), step=1)
            sp_working_status = st.radio("現在の就業状況(配偶者)", ["就業中（給与収入あり）", "非就業・退職済み（専業主婦/夫等）"], index=0 if get_val("sp_working_status", "就業中（給与収入あり）") == "就業中（給与収入あり）" else 1)
            
        with col2:
            if sp_working_status == "就業中（給与収入あり）":
                sp_gross_income = st.number_input("配偶者の現在の額面年収（万円）", value=int(get_val("sp_gross_income", 3000000)/10000), step=10) * 10000
                sp_salary_growth = st.number_input("配偶者の毎年の昇給率 (%)", min_value=0.0, max_value=5.0, value=get_val("sp_salary_growth", 0.01)*100, step=0.1) / 100

                has_sp_salary_cap = st.checkbox("昇給の頭打ち（上限額・停止年齢）を設定する(配偶者)", value=get_val("has_sp_salary_cap", False))
                if has_sp_salary_cap:
                    saved_sp_cap = get_val("sp_salary_cap_amount", 5000000)
                    default_sp_cap = 5000000 if saved_sp_cap >= 1000000000 else saved_sp_cap
                    sp_salary_cap_amount = st.number_input("配偶者の昇給上限キャップ（額面・万円）", min_value=100, max_value=10000, value=int(default_sp_cap/10000), step=10) * 10000
                    
                    saved_sp_plateau = get_val("sp_salary_plateau_age", 50)
                    default_sp_plateau = 50 if saved_sp_plateau >= 1000 else saved_sp_plateau
                    sp_salary_plateau_age = safe_number_input("配偶者の昇給がストップする年齢", min_value=current_age + sp_age_diff, max_value=100, default_value=default_sp_plateau, step=1)
                else:
                    sp_salary_cap_amount = 1000000000
                    sp_salary_plateau_age = 1000

                has_sp_salary_decrease = st.checkbox("役職定年等による給与減額あり(配偶者)", value=get_val("has_sp_salary_decrease", False))
                if has_sp_salary_decrease:
                    sp_salary_decrease_age = st.number_input("配偶者が減額される年齢", min_value=current_age + sp_age_diff, max_value=85, value=get_val("sp_salary_decrease_age", 55), step=1)
                    sp_salary_decrease_rate = st.number_input("配偶者の減額率 (%)", min_value=10, max_value=80, value=int(get_val("sp_salary_decrease_rate", 0.3)*100), step=1) / 100
                else:
                    sp_salary_decrease_age = 1000
                    sp_salary_decrease_rate = 0.0
                    
                sp_retirement_age = safe_number_input("配偶者の退職予定年齢", min_value=20, max_value=100, default_value=get_val("sp_retirement_age", 60), step=1)
                sp_retirement_allowance = st.number_input("配偶者の会社退職金見込額（万円）", value=int(get_val("sp_retirement_allowance", 5000000)/10000), step=10) * 10000
                actual_sp_working = True
            else:
                sp_gross_income = 0
                sp_salary_growth = 0
                has_sp_salary_cap = False
                sp_salary_cap_amount = 1000000000
                sp_salary_plateau_age = 1000
                sp_salary_decrease_age = 1000
                sp_salary_decrease_rate = 0.0
                sp_retirement_age = safe_number_input("配偶者の退職した年齢(受取済の場合は現在の年齢)", min_value=20, max_value=100, default_value=get_val("sp_retirement_age", current_age + sp_age_diff), step=1)
                sp_retirement_allowance = st.number_input("配偶者のこれから受け取る予定の退職金（受取済・なしは0）", value=int(get_val("sp_retirement_allowance", 0)/10000), step=10) * 10000
                actual_sp_working = False
                
            saved_sp_ret_dest = get_val("sp_ret_lump_dest", "預貯金へ")
            sp_ret_lump_dest = st.radio("退職金の入金先(配偶者)", ret_lump_dest_opts, index=ret_lump_dest_opts.index(saved_sp_ret_dest) if saved_sp_ret_dest in ret_lump_dest_opts else 0)
        
        st.divider()
        has_sp_post_retirement_job = st.checkbox("退職後のアルバイト・副業収入あり(配偶者)", value=get_val("has_sp_post_retirement_job", False))
        if has_sp_post_retirement_job:
            sp_post_retirement_income = st.number_input("配偶者の退職後収入(万円/月)", value=int(get_val("sp_post_retirement_income", 80000)/10000), step=1) * 10000
            sp_post_retirement_end_age = st.number_input("配偶者の退職後収入が続く年齢", min_value=sp_retirement_age, max_value=100, value=get_val("sp_post_retirement_end_age", max(sp_retirement_age, 65)), step=1)
        else:
            sp_post_retirement_income = 0
            sp_post_retirement_end_age = 0
    else:
        sp_age_diff = marriage_age = wedding_cost = sp_gross_income = sp_salary_growth = 0
        sp_employment_start_age = 22
        has_sp_salary_cap = False
        sp_salary_cap_amount = 1000000000
        sp_salary_plateau_age = 1000
        sp_salary_decrease_age = 1000
        sp_salary_decrease_rate = 0.0
        sp_retirement_age = sp_retirement_allowance = 0
        has_sp_post_retirement_job = False
        sp_post_retirement_income = 0
        sp_post_retirement_end_age = 0
        actual_sp_working = False
        sp_ret_lump_dest = "預貯金へ"

with tabs[2]:
    st.header("家族・教育費")
    receive_child_allowance = st.checkbox("児童手当（こども手当）を受給する", value=get_val("receive_child_allowance", True))
    
    with st.expander("📝 教育費の平均コスト目安表 (年額・万円) を見る"):
        st.markdown(f"""
        | 教育段階 | 公立・国公立 (年額) | 私立・その他 (年額) |
        | :--- | :--- | :--- |
        | **幼稚園** (3年間) | **{EDU_COST["幼稚園(公立)"]} 万円** | **{EDU_COST["幼稚園(私立)"]} 万円** |
        | **小学校** (6年間) | **{EDU_COST["小学校(公立)"]} 万円** | **{EDU_COST["小学校(私立)"]} 万円** |
        | **中学校** (3年間) | **{EDU_COST["中学校(公立)"]} 万円** | **{EDU_COST["中学校(私立)"]} 万円** |
        | **高校** (3年間) | **{EDU_COST["高校(公立)"]} 万円** | **{EDU_COST["高校(私立)"]} 万円** |
        | **大学・短大・専門** | **国公立大: {EDU_COST["国公立大学(4年)"]} 万円** | **私立文系: {EDU_COST["私立大学文系(4年)"]} 万円** ／ **私立理系: {EDU_COST["私立大学理系(4年)"]} 万円** ／ **短大・専門: {EDU_COST["短大(2年)"]} 万円** |
        """)

    num_children = st.number_input("子どもの人数", min_value=0, max_value=6, value=get_val("num_children", 0), step=1)    

    child_settings = []

    if num_children > 0:
        for i in range(num_children):
            if i % 3 == 0:
                child_cols = st.columns(3)
            
            with child_cols[i % 3]:
                st.markdown(f"**第{i+1}子**")
                saved_status = get_val(f"status_{i}", "これから生まれる")
                child_status = st.radio(f"第{i+1}子の状況", ["これから生まれる", "既に生まれている"], index=0 if saved_status == "これから生まれる" else 1, key=f"status_{i}")
                
                if child_status == "これから生まれる":
                    c_birth_age = st.number_input(f"誕生時の本人の年齢", min_value=current_age, max_value=80, value=get_val(f"future_age_{i}", current_age + 2 + (i*2)), step=1, key=f"future_age_{i}")
                    
                    st.markdown("**産休・育休の取得予定**")
                    take_leave_main = st.checkbox("本人が取得する", value=get_val(f"leave_main_ck_{i}", False), key=f"leave_main_ck_{i}")
                    leave_months_main = st.number_input("本人の取得期間(ヶ月)", min_value=1, max_value=24, value=get_val(f"leave_mon_main_{i}", 12), step=1, key=f"leave_mon_main_{i}") if take_leave_main else 0
                        
                    take_leave_sp = st.checkbox("配偶者が取得する", value=get_val(f"leave_sp_ck_{i}", False), key=f"leave_sp_ck_{i}") if has_marriage else False
                    leave_months_sp = st.number_input("配偶者の取得期間(ヶ月)", min_value=1, max_value=24, value=get_val(f"leave_mon_sp_{i}", 12), step=1, key=f"leave_mon_sp_{i}") if take_leave_sp else 0
                else:
                    c_current_age = st.number_input(f"第{i+1}子の現在の年齢", min_value=0, max_value=30, value=get_val(f"current_c_age_{i}", 5), step=1, key=f"current_c_age_{i}")
                    c_birth_age = current_age - c_current_age
                    st.caption(f"（逆算：本人が{c_birth_age}歳の時の子ども）")
                    leave_months_main = 0
                    leave_months_sp = 0
                    
                def select_index(opts, saved_val):
                    return opts.index(saved_val) if saved_val in opts else 0
                
                opts_k = ["公立", "私立"]
                c_kind = st.selectbox(f"幼稚園", opts_k, index=select_index(opts_k, get_val(f"k_{i}", "公立")), key=f"k_{i}")
                c_elem = st.selectbox(f"小学校", opts_k, index=select_index(opts_k, get_val(f"e_{i}", "公立")), key=f"e_{i}")
                c_mid = st.selectbox(f"中学校", opts_k, index=select_index(opts_k, get_val(f"m_{i}", "公立")), key=f"m_{i}")
                c_high = st.selectbox(f"高校", opts_k, index=select_index(opts_k, get_val(f"h_{i}", "公立")), key=f"h_{i}")
                
                opts_u = ["国公立大学(4年)", "私立大学文系(4年)", "私立大学理系(4年)", "短大(2年)", "専門学校(2年)", "なし"]
                c_uni = st.selectbox(f"進学先", opts_u, index=select_index(opts_u, get_val(f"u_{i}", "国公立大学(4年)")), key=f"u_{i}")
                
                if c_uni != "なし":
                    uni_end_age = 20 if "2年" in c_uni else 22
                    st.markdown(f"**進学期間中の仕送り支援**")
                    has_uni_support = st.checkbox("仕送りを行う", value=get_val(f"usup_{i}", False), key=f"usup_{i}")
                    if has_uni_support:
                        uni_rent_support = st.number_input(f"家賃仕送り(万円/月)", value=int(get_val(f"urent_{i}", 50000)/10000), step=1, key=f"urent_{i}") * 10000
                        uni_living_support = st.number_input(f"生活費仕送り(万円/月)", value=int(get_val(f"uliv_{i}", 50000)/10000), step=1, key=f"uliv_{i}") * 10000
                    else:
                        uni_rent_support = 0
                        uni_living_support = 0
                else:
                    uni_end_age = 18
                    has_uni_support = False
                    uni_rent_support = 0
                    uni_living_support = 0
                
                child_settings.append({
                    "birth_age": c_birth_age, "leave_main": leave_months_main, "leave_sp": leave_months_sp,
                    "course": [(4,6,f"幼稚園({c_kind})"), (7,12,f"小学校({c_elem})"), (13,15,f"中学校({c_mid})"), (16,18,f"高校({c_high})"), (19,uni_end_age, c_uni if c_uni != "なし" else None)],
                    "uni_support": {"active": has_uni_support, "rent": uni_rent_support, "living": uni_living_support, "start": 19, "end": uni_end_age}
                })
        
    st.divider()
    use_edu_loan = st.checkbox("教育費にローン(奨学金等)を利用する", value=get_val("use_edu_loan", False))
    if use_edu_loan:
        edu_loan_rate = st.number_input("教育ローン・奨学金 金利(%)", min_value=0.0, max_value=5.0, value=get_val("edu_loan_rate", 0.02)*100, step=0.1) / 100
        edu_loan_years = st.number_input("教育ローン 返済期間(年)", min_value=1, max_value=20, value=get_val("edu_loan_years", 10), step=1)
    else:
        edu_loan_rate = edu_loan_years = 0
with tabs[3]:
    st.header("住宅・車")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("住居設定")
        housing_type = st.radio("現在の住居形態", ["賃貸", "持ち家"], index=0 if get_val("housing_type", "賃貸") == "賃貸" else 1)
        if housing_type == "賃貸":
            rent_annual = st.number_input("現在の家賃・管理費等(万円/年)", value=int(get_val("rent_annual", 1200000)/10000), step=10) * 10000
            rent_renewal_years = st.number_input("家賃の更新周期 (年)", min_value=1, max_value=10, value=get_val("rent_renewal_years", 2), step=1)
            rent_renewal_fee_months = st.number_input("更新料 (新家賃の何ヶ月分)", min_value=0.0, max_value=3.0, value=get_val("rent_renewal_fee_months", 1.0), step=0.5)
            
            use_rent_inflation = st.checkbox("更新時の家賃インフレ(値上げ)を考慮する", value=get_val("use_rent_inflation", False))
            if use_rent_inflation:
                rent_inflation_rate = st.number_input("家賃のインフレ率 (年換算 %)", min_value=0.0, max_value=5.0, value=get_val("rent_inflation_rate", 0.01)*100, step=0.1) / 100
            else:
                rent_inflation_rate = 0.0
                
            has_existing_mortgage = False
            ex_housing_loan_balance = ex_housing_loan_years_remaining = ex_housing_loan_rate = 0
            ex_housing_rate_up_years = 1000
            ex_housing_rate_up_rate = 0.0
            has_ex_mortgage_deduction = False
            ex_mortgage_deduction_rate = ex_mortgage_deduction_years_remaining = ex_mortgage_deduction_max = 0
        else:
            has_existing_mortgage = st.checkbox("現在返済中の住宅ローンあり", value=get_val("has_existing_mortgage", False))
            if has_existing_mortgage:
                ex_housing_loan_balance = st.number_input("現在の住宅ローン残高（万円）", value=int(get_val("ex_housing_loan_balance", 20000000)/10000), step=100) * 10000
                ex_housing_loan_years_remaining = st.number_input("残りの返済期間（年）", min_value=1, max_value=50, value=get_val("ex_housing_loan_years_remaining", 20), step=1)
                ex_housing_loan_type = st.radio("現在の金利タイプ", ["固定金利", "変動金利"], index=0 if get_val("ex_housing_loan_type", "固定金利") == "固定金利" else 1, key="ex_loan_type")
                ex_housing_loan_rate = st.number_input("現在の適用金利 (%)", min_value=0.1, max_value=5.0, value=get_val("ex_housing_loan_rate", 0.005)*100, step=0.1, key="ex_loan_rate") / 100
                if ex_housing_loan_type == "変動金利":
                    st.markdown("**将来の金利上昇シナリオ**")
                    ex_housing_rate_up_years = st.number_input("何年後に金利が上昇するか", min_value=1, max_value=ex_housing_loan_years_remaining, value=get_val("ex_housing_rate_up_years", 5), step=1, key="ex_rate_up_y")
                    ex_housing_rate_up_rate = st.number_input("上昇後の金利 (%)", min_value=0.1, max_value=5.0, value=get_val("ex_housing_rate_up_rate", 0.015)*100, step=0.1, key="ex_rate_up_r") / 100
                else:
                    ex_housing_rate_up_years = 1000
                    ex_housing_rate_up_rate = 0.0
                
                has_ex_mortgage_deduction = st.checkbox("住宅ローン控除を現在利用している", value=get_val("has_ex_mortgage_deduction", True))
                if has_ex_mortgage_deduction:
                    ex_mortgage_deduction_rate = st.number_input("既存ローンの控除率 (%)", min_value=0.1, max_value=1.0, value=get_val("ex_mortgage_deduction_rate", 0.007)*100, step=0.1, key="ex_ded_rate") / 100
                    ex_mortgage_deduction_years_remaining = st.number_input("既存ローンの残り控除期間 (年)", min_value=1, max_value=13, value=get_val("ex_mortgage_deduction_years_remaining", 10), step=1)
                    ex_mortgage_deduction_max = st.number_input("既存ローンの借入限度額（万円）", value=int(get_val("ex_mortgage_deduction_max", 30000000)/10000), step=100, key="ex_ded_max") * 10000
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

        has_housing = st.checkbox("将来の住宅購入予定あり", value=get_val("has_housing", False))
        if has_housing:
            housing_purchase_age = st.number_input("住宅購入する本人の年齢", min_value=current_age, max_value=90, value=get_val("housing_purchase_age", current_age + 3), step=1)
            housing_loan_amount = st.number_input("住宅借入額（万円）", value=int(get_val("housing_loan_amount", 30000000)/10000), step=100) * 10000
            housing_loan_type = st.radio("新規ローンの金利タイプ", ["固定金利", "変動金利"], index=0 if get_val("housing_loan_type", "固定金利") == "固定金利" else 1, key="new_loan_type")
            housing_loan_rate = st.number_input("新規ローン金利 (%)", min_value=0.1, max_value=5.0, value=get_val("housing_loan_rate", 0.01)*100, step=0.1, key="new_loan_rate") / 100
            housing_loan_years = st.number_input("新規ローン返済期間（年）", min_value=10, max_value=50, value=get_val("housing_loan_years", 35), step=1)
            
            if housing_loan_type == "変動金利":
                st.markdown("**将来の金利上昇シナリオ**")
                housing_rate_up_years = st.number_input("借入から何年後に金利が上昇するか", min_value=1, max_value=housing_loan_years, value=get_val("housing_rate_up_years", 5), step=1, key="new_rate_up_y")
                housing_rate_up_rate = st.number_input("上昇後の新規ローン金利 (%)", min_value=0.1, max_value=5.0, value=get_val("housing_rate_up_rate", 0.02)*100, step=0.1, key="new_rate_up_r") / 100
            else:
                housing_rate_up_years = 1000
                housing_rate_up_rate = 0.0

            housing_down_payment = st.number_input("頭金・諸費用（万円）", value=int(get_val("housing_down_payment", 5000000)/10000), step=10) * 10000
            housing_maint = st.number_input("固定資産税・火災保険等(万円/年)", value=int(get_val("housing_maint", 200000)/10000), step=1) * 10000
            has_mortgage_deduction = st.checkbox("住宅ローン控除を利用する", value=get_val("has_mortgage_deduction", True), key="new_ded_chk")
            if has_mortgage_deduction:
                mortgage_deduction_rate = st.number_input("新規控除率 (%)", min_value=0.1, max_value=1.0, value=get_val("mortgage_deduction_rate", 0.007)*100, step=0.1, key="new_ded_rate") / 100
                mortgage_deduction_years = st.number_input("新規控除期間 (年)", min_value=10, max_value=13, value=get_val("mortgage_deduction_years", 13), step=1, key="new_ded_years")
                mortgage_deduction_max = st.number_input("新規借入限度額（万円）", value=int(get_val("mortgage_deduction_max", 30000000)/10000), step=100, key="new_ded_max") * 10000
            else:
                mortgage_deduction_rate = mortgage_deduction_years = mortgage_deduction_max = 0
        else:
            housing_purchase_age = housing_loan_amount = housing_loan_rate = housing_loan_years = housing_down_payment = housing_maint = 0
            housing_rate_up_years = 1000
            housing_rate_up_rate = 0.0
            has_mortgage_deduction = False
            mortgage_deduction_rate = mortgage_deduction_years = mortgage_deduction_max = 0

        has_reform = st.checkbox("住宅のリフォーム予定あり", value=get_val("has_reform", False))
        if has_reform:
            reform_age = st.number_input("リフォームする本人の年齢", min_value=current_age, max_value=100, value=get_val("reform_age", current_age + 15), step=1)
            reform_cost = st.number_input("リフォーム費用(万円)", value=int(get_val("reform_cost", 3000000)/10000), step=10) * 10000
            use_reform_loan = st.checkbox("リフォームにローンを利用する", value=get_val("use_reform_loan", False))
            if use_reform_loan:
                reform_loan_rate = st.number_input("リフォームローン金利(%)", min_value=0.1, max_value=5.0, value=get_val("reform_loan_rate", 0.02)*100, step=0.1) / 100
                reform_loan_years = st.number_input("リフォームローン返済期間(年)", min_value=1, max_value=20, value=get_val("reform_loan_years", 10), step=1)
            else:
                reform_loan_rate = reform_loan_years = 0
        else:
            reform_age = reform_cost = 0
            use_reform_loan = False
            reform_loan_rate = reform_loan_years = 0

        if has_existing_mortgage or has_housing:
            st.caption(f"💡 **住宅ローン最適化のヒント：** 金利がわずか0.2〜0.3%違うだけで総支払額は数百万円変わります。現在の最安金利や借換メリットは [👉 住宅ローン無料診断（モゲチェック等 / PR）]({AFFILIATE_LINKS['mortgage']}) で1分で確認できます。")
        if housing_type == "持ち家":
            st.caption(f"🏠 **資産把握のヒント：** 持ち家の現在の売却相場を知っておくと老後計画の精度が上がります。[👉 机上でわかる無料不動産査定 (PR)]({AFFILIATE_LINKS['real_estate']})")

    with col2:
        st.subheader("自動車設定（本人）")
        has_car = st.checkbox("本人用の車の所有・購入あり", value=get_val("has_car", False))
        if has_car:
            car_first_purchase_age = st.number_input("次回購入する本人の年齢", min_value=current_age, max_value=90, value=get_val("car_first_purchase_age", current_age), step=1)
            car_first_purchase_cost = st.number_input("次回の購入費用（万円）", value=int(get_val("car_first_purchase_cost", 3000000)/10000), step=10) * 10000
            car_replace_cycle = st.number_input("買い替え周期（年）", min_value=3, max_value=20, value=get_val("car_replace_cycle", 7), step=1)
            car_replace_cost = st.number_input("それ以降の買い替え費用（万円）", value=int(get_val("car_replace_cost", 2000000)/10000), step=10) * 10000
            car_loan_use = st.checkbox("自動車購入時にローンを利用する", value=get_val("car_loan_use", False), key="car_loan_main")
            if car_loan_use:
                car_loan_rate = st.number_input("自動車ローン金利(%)", min_value=0.1, max_value=10.0, value=get_val("car_loan_rate", 0.02)*100, step=0.1) / 100
                car_loan_years = st.number_input("自動車ローン返済期間(年)", min_value=1, max_value=10, value=get_val("car_loan_years", 5), step=1)
            else:
                car_loan_rate = car_loan_years = 0
            car_last_purchase_age = st.number_input("最後に車を買い替える年齢(本人)", min_value=60, max_value=100, value=get_val("car_last_purchase_age", 75), step=1)
            car_dispose_age = st.number_input("車を手放す(免返等)年齢(本人)", min_value=car_last_purchase_age, max_value=100, value=get_val("car_dispose_age", min(100, car_last_purchase_age + 10)), step=1)
            car_sale_price = st.number_input("最後に手放す際の売却見込額(万円)", value=int(get_val("car_sale_price", 500000)/10000), step=10) * 10000
            car_maint_annual = st.number_input("年間維持費(駐車場等含)（万円/年）", value=int(get_val("car_maint_annual", 300000)/10000), step=1) * 10000
        else:
            car_first_purchase_age = car_first_purchase_cost = car_replace_cycle = car_replace_cost = car_last_purchase_age = car_dispose_age = car_maint_annual = 0
            car_loan_use = False
            car_loan_rate = car_loan_years = car_sale_price = 0
            
        st.markdown("---")
        st.subheader("自動車設定（配偶者）")
        if has_marriage:
            sp_has_car = st.checkbox("配偶者用の車の所有・購入あり", value=get_val("sp_has_car", False))
            if sp_has_car:
                sp_car_first_purchase_age = st.number_input("次回購入する配偶者の年齢", min_value=current_age + sp_age_diff, max_value=90, value=get_val("sp_car_first_purchase_age", current_age + sp_age_diff), step=1)
                sp_car_first_purchase_cost = st.number_input("次回の配偶者の購入費用（万円）", value=int(get_val("sp_car_first_purchase_cost", 2000000)/10000), step=10) * 10000
                sp_car_replace_cycle = st.number_input("配偶者の買い替え周期（年）", min_value=3, max_value=20, value=get_val("sp_car_replace_cycle", 7), step=1)
                sp_car_replace_cost = st.number_input("それ以降の配偶者の買い替え費用（万円）", value=int(get_val("sp_car_replace_cost", 1500000)/10000), step=10) * 10000
                sp_car_loan_use = st.checkbox("配偶者の自動車購入時にローンを利用する", value=get_val("sp_car_loan_use", False), key="car_loan_sp")
                if sp_car_loan_use:
                    sp_car_loan_rate = st.number_input("配偶者の自動車ローン金利(%)", min_value=0.1, max_value=10.0, value=get_val("sp_car_loan_rate", 0.02)*100, step=0.1) / 100
                    sp_car_loan_years = st.number_input("配偶者の自動車ローン返済期間(年)", min_value=1, max_value=10, value=get_val("sp_car_loan_years", 5), step=1)
                else:
                    sp_car_loan_rate = sp_car_loan_years = 0
                sp_car_last_purchase_age = st.number_input("最後に車を買い替える年齢(配偶者)", min_value=60, max_value=100, value=get_val("sp_car_last_purchase_age", 75), step=1)
                sp_car_dispose_age = st.number_input("車を手放す年齢(配偶者)", min_value=sp_car_last_purchase_age, max_value=100, value=get_val("sp_car_dispose_age", min(100, sp_car_last_purchase_age + 10)), step=1)
                sp_car_sale_price = st.number_input("配偶者の最後に手放す際の売却見込額(万円)", value=int(get_val("sp_car_sale_price", 300000)/10000), step=10) * 10000
                sp_car_maint_annual = st.number_input("配偶者の年間維持費（万円/年）", value=int(get_val("sp_car_maint_annual", 200000)/10000), step=1) * 10000
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
        initial_savings = st.number_input("現在の預貯金(本人・万円)", min_value=0, value=int(get_val("initial_savings", 3000000)/10000), step=10) * 10000
        initial_nisa = st.number_input("現在のNISA残高(本人・万円)", min_value=0, value=int(get_val("initial_nisa", 10000000)/10000), step=10) * 10000
        initial_taxable = st.number_input("現在の特定口座残高(本人・万円)", min_value=0, value=int(get_val("initial_taxable", 10000000)/10000), step=10) * 10000
        
        default_nisa_used = get_val("nisa_used_total", get_val("nisa_used_tsumitate", 0) + get_val("nisa_used_growth", 0))
        nisa_used_total = safe_number_input("NISA 生涯投資枠の利用済額(本人・万円 / 上限1800万)", min_value=0, max_value=1800, default_value=int(default_nisa_used/10000), step=10, help="つみたて投資枠と成長投資枠を合わせた、これまでの元本利用済額を入力してください。") * 10000
        nisa_used_tsumitate = nisa_used_total
        nisa_used_growth = 0
        
        has_investment = st.checkbox("新規の積立投資を行う(本人)", value=get_val("has_investment", True))
        if has_investment:
            invest_monthly = st.number_input("毎月の積立額(本人・万円)", min_value=0.0, value=float(get_val("invest_monthly", 150000)/10000), step=1.0) * 10000
            invest_end_age = safe_number_input("積立を終了する本人の年齢", min_value=current_age, max_value=110, default_value=get_val("invest_end_age", 60), step=1)
            invest_strategy = "NISA優先 (年間360万/生涯1800万上限、超過分は特定口座)"
            st.caption("💡 積立は自動的に「NISA枠（年間360万・生涯1,800万の残り枠）を最優先」で埋め、枠を超えた分は「特定口座」へ投資されます。")
        else:
            invest_monthly = invest_end_age = 0
            invest_strategy = "すべて特定口座へ"
            
        withdrawal_start_age = safe_number_input("定率取り崩し開始年齢(本人)", min_value=current_age, max_value=110, default_value=get_val("withdrawal_start_age", retirement_age), step=1)
        withdrawal_rate_nisa = safe_number_input("NISA 定率取り崩し率(本人) (%)", min_value=0.0, max_value=100.0, default_value=float(get_val("withdrawal_rate_nisa", 0.04)*100), step=0.1) / 100
        withdrawal_rate_taxable = safe_number_input("特定口座 定率取り崩し率(本人) (%)", min_value=0.0, max_value=100.0, default_value=float(get_val("withdrawal_rate_taxable", 0.04)*100), step=0.1) / 100

    with col2:
        st.subheader("配偶者")
        if has_marriage:
            sp_initial_savings = st.number_input("現在の預貯金(配偶者・万円)", min_value=0, value=int(get_val("sp_initial_savings", 500000)/10000), step=10) * 10000
            sp_initial_nisa = st.number_input("現在のNISA残高(配偶者・万円)", min_value=0, value=int(get_val("sp_initial_nisa", 0)/10000), step=10) * 10000
            sp_initial_taxable = st.number_input("現在の特定口座残高(配偶者・万円)", min_value=0, value=int(get_val("sp_initial_taxable", 0)/10000), step=10) * 10000
            
            default_sp_nisa_used = get_val("sp_nisa_used_total", get_val("sp_nisa_used_tsumitate", 0) + get_val("sp_nisa_used_growth", 0))
            sp_nisa_used_total = safe_number_input("NISA 生涯投資枠の利用済額(配偶者・万円 / 上限1800万)", min_value=0, max_value=1800, default_value=int(default_sp_nisa_used/10000), step=10) * 10000
            sp_nisa_used_tsumitate = sp_nisa_used_total
            sp_nisa_used_growth = 0
            
            sp_has_investment = st.checkbox("新規の積立投資を行う(配偶者)", value=get_val("sp_has_investment", False))
            if sp_has_investment:
                sp_invest_monthly = st.number_input("毎月の積立額(配偶者・万円)", min_value=0.0, value=float(get_val("sp_invest_monthly", 30000)/10000), step=1.0) * 10000
                sp_invest_end_age = safe_number_input("積立を終了する配偶者の年齢", min_value=current_age + sp_age_diff, max_value=110, default_value=get_val("sp_invest_end_age", 60), step=1)
                sp_invest_strategy = "NISA優先"
                st.caption("💡 配偶者の積立も「NISA枠（年間360万・生涯1,800万上限）優先 → 超過分は特定口座」へ自動投資されます。")
            else:
                sp_invest_monthly = sp_invest_end_age = 0
                sp_invest_strategy = "すべて特定口座へ"
                
            sp_withdrawal_start_age = safe_number_input("定率取り崩し開始年齢(配偶者)", min_value=current_age + sp_age_diff, max_value=110, default_value=get_val("sp_withdrawal_start_age", sp_retirement_age), step=1)
            sp_withdrawal_rate_nisa = safe_number_input("NISA 定率取り崩し率(配偶者) (%)", min_value=0.0, max_value=100.0, default_value=float(get_val("sp_withdrawal_rate_nisa", 0.04)*100), step=0.1) / 100
            sp_withdrawal_rate_taxable = safe_number_input("特定口座 定率取り崩し率(配偶者) (%)", min_value=0.0, max_value=100.0, default_value=float(get_val("sp_withdrawal_rate_taxable", 0.04)*100), step=0.1) / 100
        else:
            sp_initial_savings = sp_initial_nisa = sp_initial_taxable = sp_nisa_used_total = sp_nisa_used_tsumitate = sp_nisa_used_growth = 0
            sp_has_investment = False
            sp_invest_monthly = sp_invest_end_age = 0
            sp_invest_strategy = "すべて特定口座へ"
            sp_withdrawal_start_age = sp_withdrawal_rate_nisa = sp_withdrawal_rate_taxable = 0

    # ▼▼▼ 1. 預貯金の最低維持（温存）ライン設定 ▼▼▼
    st.divider()
    st.subheader("預貯金の維持ライン・暴落待機資金ルール")
    st.markdown("**■ 預貯金の最低維持（温存）ライン設定**")
    st.write("※生活防衛資金やポートフォリオの現金比率など、取り崩さずに確保しておきたい現金の目標水準を設定します。")
    
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        min_savings_amount = st.number_input("最低維持額（定額・万円）", min_value=0, value=int(get_val("min_savings_amount", 2400000)/10000), step=10) * 10000
    with col_m2:
        min_savings_rate = safe_number_input("最低維持率（総資産の %）", min_value=0.0, max_value=100.0, default_value=get_pct_val("min_savings_rate", 5.0), step=0.5) / 100
        
    min_save_opts = ["金額が高い方を採用", "金額が低い方を採用", "定額のみを採用", "定率のみを採用"]
    saved_min_rule = get_val("min_savings_rule", "金額が高い方を採用")
    min_savings_rule = st.radio("維持基準の適用方法", min_save_opts, index=min_save_opts.index(saved_min_rule) if saved_min_rule in min_save_opts else 0)

    st.markdown("<br>", unsafe_allow_html=True)
    def_opts = [
        "預貯金を最低維持ラインまで使う → 特定口座(世帯) → NISA(世帯)",
        "特定口座(世帯) → NISA(世帯) → 預貯金を最低維持ラインまで使う",
        "NISA(世帯) → 特定口座(世帯) → 預貯金を最低維持ラインまで使う"
    ]
    saved_def = get_val("deficit_order", "預貯金を最低維持ラインまで使う → 特定口座(世帯) → NISA(世帯)")
    if "限界まで" in saved_def or "最低維持額割れ" in saved_def:
        if "特定口座(世帯) → NISA" in saved_def: saved_def = def_opts[1]
        elif "NISA(世帯) → 特定口座" in saved_def: saved_def = def_opts[2]
        else: saved_def = def_opts[0]
        
    deficit_order = st.selectbox("赤字補填の優先順位", def_opts, index=def_opts.index(saved_def) if saved_def in def_opts else 0)

    # ▼▼▼ 2. 預貯金の最高維持ライン（上限キャップ）設定 ▼▼▼
    st.divider()
    st.markdown("**■ 預貯金の最高維持（上限）ライン ＆ 余剰キャッシュ自動投資設定**")
    st.write("※預貯金が増えすぎて現金が遊んでしまうのを防ぐため、保有する預貯金の最高維持ラインを設定し、それを超えた分を自動的に投資へ回します。")
    has_max_savings_cap = st.checkbox("預貯金の最高維持ラインを設定し、超過分を自動で投資へ回す", value=get_val("has_max_savings_cap", False))
    if has_max_savings_cap:
        col_mx1, col_mx2 = st.columns(2)
        with col_mx1:
            max_savings_amount = st.number_input("最高維持額（定額・万円）", min_value=0, value=int(get_val("max_savings_amount", 5000000)/10000), step=10) * 10000
        with col_mx2:
            max_savings_rate = safe_number_input("最高維持率（総資産の %）", min_value=0.0, max_value=100.0, default_value=get_pct_val("max_savings_rate", 20.0), step=0.5) / 100
            
        max_save_opts = ["金額が高い方を採用", "金額が低い方を採用", "定額のみを採用", "定率のみを採用"]
        saved_max_rule = get_val("max_savings_rule", "金額が高い方を採用")
        max_savings_rule = st.radio("最高維持基準の適用方法（最低維持基準とは別に設定可能）", max_save_opts, index=max_save_opts.index(saved_max_rule) if saved_max_rule in max_save_opts else 0, key="max_sav_rule_radio")
        
        st.caption("💡 **超過分の投資ルール（NISA優先）：** 預貯金の最低維持ラインおよび暴落待機資金（上限枠）を確保した上で、この最高維持ラインを超えた余剰預貯金は、**自動的に「NISA枠（年間投資枠360万円・生涯非課税限度額1,800万円の残り枠）を最優先」で埋め、あふれた分を「特定口座」へ積立投資**します。（※計算上、最低維持ラインの方が高くなった場合は最低維持ラインの確保が優先されます）")
    else:
        max_savings_amount = 1000000000
        max_savings_rate = 1.0
        max_savings_rule = "金額が高い方を採用"

    # ▼▼▼ 3. 暴落時の追加投資用待機資金（ドライパウダー）設定 ▼▼▼
    st.divider()
    st.markdown("**■ 暴落時の追加投資用待機資金（ドライパウダー）設定**")
    st.write("※生活防衛資金（預貯金の最低維持ライン）とは別枠で、暴落時に安く買い向かうための待機資金プールと段階的投入ルールを設定します。")
    has_dry_powder = st.checkbox("暴落時の追加投資用待機資金（ドライパウダー）を運用する", value=get_val("has_dry_powder", False))
    if has_dry_powder:
        col_dp1, col_dp2 = st.columns(2)
        with col_dp1:
            initial_dry_powder = st.number_input("現在の待機資金残高（万円）", min_value=0, value=int(get_val("initial_dry_powder", 2000000)/10000), step=10) * 10000
        with col_dp2:
            dp_yield = safe_number_input("待機資金の平時運用利回り (年率 %)", min_value=-10.0, max_value=100.0, default_value=float(get_val("dp_yield", 0.01)*100), step=0.1, help="個人向け国債・MMF・高金利預金など、待機中の利回り（税引前）") / 100

        st.markdown("**💧 待機資金の目標上限（プール枠）設定**")
        col_dpm1, col_dpm2 = st.columns(2)
        with col_dpm1:
            dp_max_cap = st.number_input("待機資金の目標上限額（定額・万円）", min_value=0, value=int(get_val("dp_max_cap", 3000000)/10000), step=10, help="定額での待機資金プール目標上限です。") * 10000
        with col_dpm2:
            dp_max_rate = safe_number_input("待機資金の目標上限率（総資産の %）", min_value=0.0, max_value=100.0, default_value=get_pct_val("dp_max_rate", 10.0), step=0.5, help="総資産に対する比率での待機資金プール目標上限です。") / 100

        dp_rule_opts = ["金額が高い方を採用", "金額が低い方を採用", "定額のみを採用", "定率のみを採用"]
        saved_dp_rule = get_val("dp_max_rule", "定額のみを採用")
        dp_max_rule = st.radio("待機資金の上限基準の適用方法", dp_rule_opts, index=dp_rule_opts.index(saved_dp_rule) if saved_dp_rule in dp_rule_opts else 2, key="dp_max_rule_radio")

        dp_refill_opts = [
            "待機資金のプールを最優先（最低維持ラインを超えた余剰分は、まず待機資金の上限枠まで優先補充し、残りで通常積立を行う）",
            "通常の毎月積立を優先（毎月の積立投資を行った後、まだ最低維持ラインを超える余剰預貯金があれば待機資金へ補充する）"
        ]
        saved_dp_refill = get_val("dp_refill_priority", dp_refill_opts[0])
        dp_refill_priority = st.radio("平時の待機資金プール（補充）の優先順位", dp_refill_opts, index=dp_refill_opts.index(saved_dp_refill) if saved_dp_refill in dp_refill_opts else 0)
        st.caption("※家計収支が赤字等で預貯金が最低維持ライン以下の年や、暴落が発生した年は、待機資金への補充は自動的に停止します。また、利回りや資産変動により待機資金が上限枠を超えた超過分は、自動的に投資（NISA優先→特定口座）へ回されます。")

        st.markdown("**🎯 暴落時の段階的買い向かい（ピラミッディング）ルール**")
        col_dpr1, col_dpr2, col_dpr3 = st.columns(3)
        with col_dpr1:
            dp_step_drop = safe_number_input("発動の下落刻み幅 (%)", min_value=0.1, max_value=100.0, default_value=get_pct_val("dp_step_drop", 10.0), step=0.5, help="例: 10%に設定すると、-10%, -20%, -30%...と段階的に発動します。") / 100
        with col_dpr2:
            dp_step_rate = safe_number_input("1段階あたりの投入率係数 (%)", min_value=0.1, max_value=100.0, default_value=get_pct_val("dp_step_rate", 10.0), step=0.5, help="例: 10%に設定すると、1段目で10%、2段目で20%、3段目で30%を投入します。") / 100
        with col_dpr3:
            dp_full_drop = safe_number_input("全額(100%)投入する下落幅 (%)", min_value=0.1, max_value=100.0, default_value=get_pct_val("dp_full_drop", 50.0), step=1.0, help="年間リターンがこの下落幅に達した年は、残りの待機資金を100%全力投入します。") / 100

        
        dp_calc_opts = [
            "累積・残高基準（通過ステップごとにその時の残高の〇%を順次投入）",
            "累積・当初枠基準（通過ステップの投入率を単純合算して投入）",
            "単発判定（到達した最大ステップの〇%のみを投入）"
        ]
        saved_dp_calc = get_val("dp_calc_mode", dp_calc_opts[0])
        dp_calc_mode = st.radio("年次シミュレーション上の段階投入の計算方式", dp_calc_opts, index=dp_calc_opts.index(saved_dp_calc) if saved_dp_calc in dp_calc_opts else 0)
        
        preview_texts = []
        rem = 1.0
        cum_sum = 0.0
        step_idx = 1
        while step_idx * dp_step_drop < dp_full_drop and step_idx <= 10:
            drop_pct = step_idx * dp_step_drop * 100
            stage_r = min(1.0, step_idx * dp_step_rate)
            if dp_calc_mode == dp_calc_opts[0]:
                rem *= (1.0 - stage_r)
                total_r = (1.0 - rem) * 100
            elif dp_calc_mode == dp_calc_opts[1]:
                cum_sum = min(1.0, cum_sum + stage_r)
                total_r = cum_sum * 100
            else:
                total_r = stage_r * 100
            preview_texts.append(f"**-{drop_pct:g}%**時: 累計**{total_r:.1f}%**投入")
            step_idx += 1
        preview_texts.append(f"**-{dp_full_drop*100:g}%**以上: **100%（全額）**投入")
        st.caption("💡 現在の設定による年間投入率の目安： " + " ／ ".join(preview_texts))
        
        # ▼▼▼ ここに追加（上の st.caption とまったく同じインデント幅・半角スペース8個） ▼▼▼
        st.caption(f"💧 **待機資金の置き場について：** 暴落待機資金を普通預金に眠らせず、個人向け国債（変動10年）や証券連携の高金利口座（年利1.0%前後）に置くには [👉 NISA・待機資金運用に強いネット証券比較 (PR)]({AFFILIATE_LINKS['securities']}) を活用するのが定番です。")

    else:
        initial_dry_powder = dp_max_cap = 0
        dp_max_rate = 0.0
        dp_max_rule = "定額のみを採用"
        dp_yield = 0.0
        dp_refill_priority = "待機資金のプールを最優先（最低維持ラインを超えた余剰分は、まず待機資金の上限枠まで優先補充し、残りで通常積立を行う）"
        dp_step_drop = 0.10
        dp_step_rate = 0.10
        dp_full_drop = 0.50
        dp_calc_mode = "累積・残高基準（通過ステップごとにその時の残高の〇%を順次投入）"



   # ▼▼▼ 4. シミュレーション・リターン設定（タブ5の最後に配置） ▼▼▼
    st.divider()
    st.subheader("シミュレーション・リターン設定")
    sim_opts = [
        "定率シミュレーション（基本）",
        "モンテカルロシミュレーション（リスク・暴落を考慮）",
        "ヒストリカル・バックテスト（S&P500 / オルカンの過去実績を適用）"
    ]
    saved_sim = get_val("sim_mode", "定率シミュレーション（基本）")
    sim_mode = st.radio("シミュレーション方式を選択", sim_opts, index=sim_opts.index(saved_sim) if saved_sim in sim_opts else 0)
    
    if sim_mode == "モンテカルロシミュレーション（リスク・暴落を考慮）":
        st.caption("※設定したリスク（標準偏差）とランダム暴落確率に基づく300通りの相場推移をシミュレーションします。")
        mc_pause_auto = st.checkbox(
            "⚡ 数字の連続入力モード（入力中の自動再計算を一時停止し、ボタン押下で一括計算する）",
            value=get_val("mc_pause_auto", False),
            help="ONにすると、各タブで数字を変更しても勝手にはモンテカルロ計算が走らなくなり、サクサク入力できます。"
        )
    else:
        mc_pause_auto = False

    if sim_mode == "ヒストリカル・バックテスト（S&P500 / オルカンの過去実績を適用）":
        st.info("📜 **1988年〜2025年（38年間）の実際の市場リターン（ITバブル崩壊・リーマンショック・コロナショック等を含む）**を現在の年齢から順番に当てはめて検証します。（38年経過後は1988年へループします）")
        col_hb1, col_hb2 = st.columns(2)
        with col_hb1:
            hist_index_opts = ["S&P500 (米国株式)", "オールカントリー (全世界株式 / MSCI ACWI)"]
            saved_h_idx = get_val("hist_index_choice", hist_index_opts[0])
            hist_index_choice = st.radio("メインで検証するインデックス", hist_index_opts, index=hist_index_opts.index(saved_h_idx) if saved_h_idx in hist_index_opts else 0)
        with col_hb2:
            hist_era_opts = [
                "2000年スタート（最悪期：ITバブル崩壊〜リーマンショックの『失われた10年』から開始）",
                "2007年スタート（金融危機直撃：開始2年目にリーマンショックの大暴落に直面）",
                "1988年スタート（長期標準：1988年からITバブル・リーマン・近年まで順に経験）",
                "2010年スタート（近年好調期：リーマン後の回復期・コロナショック・近年相場）"
            ]
            saved_h_era = get_val("hist_era_choice", hist_era_opts[0])
            hist_era_choice = st.selectbox("相場サイクルの開始年代（スタート地点）", hist_era_opts, index=hist_era_opts.index(saved_h_era) if saved_h_era in hist_era_opts else 0)
            hist_start_year = int(hist_era_choice[:4])
            
        expected_return = safe_number_input("参考：退職時必要額の逆算用 基準リターン (%)", min_value=-50.0, max_value=100.0, default_value=float(get_val("expected_return", 0.08)*100), step=0.1, help="バックテスト時の『退職時の必要額(運用取崩)』カードの逆算計算にのみ使用します。") / 100
        risk_std = mc_crash_prob = mc_crash_min = mc_crash_max = 0.0
    else:
        hist_index_choice = "S&P500 (米国株式)"
        hist_era_choice = "2000年スタート（最悪期：ITバブル崩壊〜リーマンショックの『失われた10年』から開始）"
        hist_start_year = 2000
        
        st.markdown("**■ 基本リターン設定（NISA・特定口座 共通）**")
        col_ret1, col_ret2 = st.columns(2)
        with col_ret1:
            expected_return = safe_number_input("期待リターン (%)", min_value=-50.0, max_value=100.0, default_value=float(get_val("expected_return", 0.08)*100), step=0.1) / 100
        with col_ret2:
            if sim_mode == "モンテカルロシミュレーション（リスク・暴落を考慮）":
                risk_std = safe_number_input("標準偏差/基本リスク (%)", min_value=0.0, max_value=200.0, default_value=float(get_val("risk_std", 0.18)*100), step=0.1) / 100
            else:
                risk_std = 0.0

        with st.expander("📊 ポートフォリオ別のリターン・リスク入力目安表を開く"):
            st.markdown("""
            | 運用スタイル (資産配分) | 期待リターン (名目) | リスク (標準偏差) | 特徴 |
            | :--- | :--- | :--- | :--- |
            | **超積極型** (株式 100%) | **8.0 %** | **18.0 %** | 上振れも凄いが、暴落のダメージも直撃する。（★現在の初期値） |
            | **積極型** (株式 70% / 債券等 30%) | **6.5 %** | **13.0 %** | リターンを狙いつつ、暴落時のショックをある程度和らげる王道スタイル。 |
            | **バランス型** (株式 50% / 債券等 50%) | **5.0 %** | **10.0 %** | リスクが大きく下がるため、悲観シナリオでも資産が安定して長持ちしやすい。 |
            | **保守型** (株式 30% / 債券等 70%) | **3.5 %** | **6.5 %** | インフレ負けを防ぐ最低限の運用。取り崩し期（老後）に入ってからの基本戦略。 |
            """)
                
        if sim_mode == "モンテカルロシミュレーション（リスク・暴落を考慮）":
            st.markdown("**■ ランダム暴落（ファットテール）設定**", help="通常の相場変動に加えて、突発的な大暴落が起こる確率と規模を設定します。0%にすると純粋な正規分布になります。")
            col_mc1, col_mc2, col_mc3 = st.columns(3)
            with col_mc1:
                mc_crash_prob = safe_number_input("発生確率(年率 %)", min_value=0.0, max_value=100.0, default_value=get_pct_val("mc_crash_prob", 5.0), step=0.5) / 100
            with col_mc2:
                mc_crash_min = safe_number_input("下落幅の下限(%)", min_value=0.0, max_value=100.0, default_value=get_pct_val("mc_crash_min", 15.0), step=1.0) / 100
            with col_mc3:
                mc_crash_max = safe_number_input("下落幅の上限(%)", min_value=0.0, max_value=100.0, default_value=get_pct_val("mc_crash_max", 30.0), step=1.0) / 100
        else:
            mc_crash_prob = mc_crash_min = mc_crash_max = 0.0
            
        st.caption("※簡易計算のため、特定口座の複利運用は毎年課税（税引後リターン適用）されている前提で算出します。")
    
    st.markdown("---")
    st.markdown("**■ 暴落（ショック）イベント設定**")
    has_market_shock = st.checkbox("特定の年齢で相場の大暴落を発生させる（ストレステスト）", value=get_val("has_market_shock", False))
    if has_market_shock:
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            shock_age = safe_number_input("暴落が発生する本人の年齢", min_value=current_age, max_value=110, default_value=get_val("shock_age", retirement_age), step=1)
        with col_s2:
            shock_drop_rate = safe_number_input("下落率 (%)", min_value=0.0, max_value=100.0, default_value=float(get_val("shock_drop_rate", 0.30)*100), step=1.0) / 100
    else:
        shock_age = 1000
        shock_drop_rate = 0.0

with tabs[5]:
    st.header("公的年金・個人年金・保険・iDeCo")
    
    st.subheader("■ 民間保険料（掛け捨て等の固定費）")
    insurance_premium_monthly = safe_number_input("毎月の民間保険料合計(万円/月)", min_value=0, max_value=100, default_value=int(get_val("insurance_premium_monthly", 0)/10000), step=1) * 10000
    insurance_premium_yearly = insurance_premium_monthly * 12
    st.caption("※医療保険、掛け捨て生命保険、がん保険などの毎月の固定費を入力してください。シミュレーション上の「基本生活費」とは完全に別枠で集計されます。")

    if insurance_premium_monthly >= 10000:
        st.caption(f"💡 **固定費削減のヒント：** 日本は高額療養費制度などの公的保険が手厚いため、民間保険を見直すだけで月1〜2万円浮くケースが多々あります。[👉 無料でFPに保険の重複チェックを相談する (PR)]({AFFILIATE_LINKS['fp_consult']})")

    st.divider()

    st.subheader("■ 公的年金")
    col_pen1, col_pen2 = st.columns(2)
    with col_pen1:
        st.markdown("**本人の公的年金**")
        pension_base = st.number_input("65歳時の年金見込額(額面・万円)(本人)", value=int(get_val("pension_base", 1200000)/10000), step=10) * 10000
        pension_start_age = st.number_input("年金受給開始年齢(本人)", min_value=60, max_value=75, value=get_val("pension_start_age", 65), step=1)
        
    with col_pen2:
        if has_marriage:
            st.markdown("**配偶者の公的年金**")
            sp_pension_base = st.number_input("65歳時の年金見込額(額面・万円)(配偶者)", value=int(get_val("sp_pension_base", 1200000)/10000), step=10) * 10000
            sp_pension_start_age = st.number_input("年金受給開始年齢(配偶者)", min_value=60, max_value=75, value=get_val("sp_pension_start_age", 65), step=1)
            
            has_kakyu_nenkin = st.checkbox("加給年金の受給あり", value=get_val("has_kakyu_nenkin", False))
            if has_kakyu_nenkin:
                kakyu_nenkin_amount = st.number_input("加給年金額(万円/年)", value=int(get_val("kakyu_nenkin_amount", 400000)/10000), step=1) * 10000
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
        has_edu_ins = st.checkbox("学資保険あり(世帯)", value=get_val("has_edu_ins", False))
        if has_edu_ins:
            edu_pay_opts = ["積立中（分割払い）", "一時払い（これから支払う）"]
            saved_edu_pay = get_val("edu_pay_type", "積立中（分割払い）")
            edu_pay_type = st.radio("払込状況(学資)", edu_pay_opts, index=edu_pay_opts.index(saved_edu_pay) if saved_edu_pay in edu_pay_opts else 0)
            if edu_pay_type == "積立中（分割払い）":
                edu_monthly = st.number_input("毎月の積立額(学資・万円)", value=get_val("edu_monthly", 15000)/10000, step=0.1) * 10000
                edu_pay_start_age = safe_number_input("支払いを開始した年齢(学資)", min_value=20, max_value=100, default_value=get_val("edu_pay_start_age", 35), step=1)
                edu_pay_end_age = st.number_input("払込終了年齢(学資)", min_value=current_age, max_value=80, value=get_val("edu_pay_end_age", 55), step=1)
                edu_pay_age = edu_lump_pay = 0
            else:
                edu_pay_age = st.number_input("支払う年齢(学資)", min_value=current_age, max_value=80, value=get_val("edu_pay_age", current_age), step=1)
                edu_lump_pay = st.number_input("支払金額(一時払・学資・万円)", value=int(get_val("edu_lump_pay", 2000000)/10000), step=10) * 10000
                edu_monthly = edu_pay_end_age = edu_pay_start_age = 0

            edu_return_rate = st.number_input("見込利率(学資・年利%)", min_value=0.0, max_value=10.0, value=get_val("edu_return_rate", 0.01)*100, step=0.1) / 100
            edu_rec_opts = ["一時金（一括）", "年金（分割）"]
            saved_edu_rec = get_val("edu_receive_type", "一時金（一括）")
            edu_receive_type = st.radio("受取方法(学資)", edu_rec_opts, index=edu_rec_opts.index(saved_edu_rec) if saved_edu_rec in edu_rec_opts else 0)
            edu_receive_age = st.number_input("受取開始年齢(学資)", min_value=current_age, max_value=80, value=get_val("edu_receive_age", 55), step=1)
            if edu_receive_type == "年金（分割）":
                edu_receive_years = st.number_input("受取期間(学資・年)", min_value=1, max_value=20, value=get_val("edu_receive_years", 4), step=1)
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
        has_life_ins = st.checkbox("生命保険あり(世帯)", value=get_val("has_life_ins", False))
        if has_life_ins:
            life_pay_opts = ["積立中（分割払い）", "一時払い（これから支払う）"]
            saved_life_pay = get_val("life_pay_type", "積立中（分割払い）")
            life_pay_type = st.radio("払込状況(生命)", life_pay_opts, index=life_pay_opts.index(saved_life_pay) if saved_life_pay in life_pay_opts else 0)
            if life_pay_type == "積立中（分割払い）":
                life_monthly = st.number_input("毎月の積立額(生命・万円)", value=get_val("life_monthly", 20000)/10000, step=0.1) * 10000
                life_pay_start_age = safe_number_input("支払いを開始した年齢(生命)", min_value=20, max_value=100, default_value=get_val("life_pay_start_age", 35), step=1)
                life_pay_end_age = st.number_input("払込終了年齢(生命)", min_value=current_age, max_value=80, value=get_val("life_pay_end_age", 60), step=1)
                life_pay_age = life_lump_pay = 0
            else:
                life_pay_age = st.number_input("支払う年齢(生命)", min_value=current_age, max_value=80, value=get_val("life_pay_age", current_age), step=1)
                life_lump_pay = st.number_input("支払金額(一時払・生命・万円)", value=int(get_val("life_lump_pay", 3000000)/10000), step=10) * 10000
                life_monthly = life_pay_end_age = life_pay_start_age = 0

            life_return_rate = st.number_input("見込利率(生命・年利%)", min_value=0.0, max_value=10.0, value=get_val("life_return_rate", 0.01)*100, step=0.1) / 100
            life_rec_opts = ["一時金（一括）", "年金（分割）"]
            saved_life_rec = get_val("life_receive_type", "一時金（一括）")
            life_receive_type = st.radio("受取方法(生命)", life_rec_opts, index=life_rec_opts.index(saved_life_rec) if saved_life_rec in life_rec_opts else 0)
            life_receive_age = st.number_input("受取開始/満期年齢(生命)", min_value=current_age, max_value=80, value=get_val("life_receive_age", 60), step=1)
            if life_receive_type == "年金（分割）":
                life_receive_years = st.number_input("受取期間(生命・年)", min_value=1, max_value=20, value=get_val("life_receive_years", 10), step=1)
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
        has_personal_pension = st.checkbox("個人年金保険あり(本人)", value=get_val("has_personal_pension", False))
        if has_personal_pension:
            pp_monthly = st.number_input("個人年金の毎月の積立額(万円)", value=get_val("pp_monthly", 10000)/10000, step=0.1) * 10000
            pp_pay_start_age = safe_number_input("支払いを開始した年齢(個人年金)", min_value=20, max_value=100, default_value=get_val("pp_pay_start_age", 30), step=1)
            pp_pay_end_age = st.number_input("個人年金の払込終了年齢(本人)", min_value=current_age, max_value=80, value=get_val("pp_pay_end_age", 60), step=1)
            pp_return_rate = st.number_input("見込利率(個人年金・年利%)", min_value=0.0, max_value=10.0, value=get_val("pp_return_rate", 0.01)*100, step=0.1) / 100
            
            pp_receive_start_age = st.number_input("個人年金の受取開始年齢(本人)", min_value=60, max_value=80, value=get_val("pp_receive_start_age", 60), step=1)
            pp_receive_years = st.number_input("個人年金の受取期間(年)", min_value=5, max_value=20, value=get_val("pp_receive_years", 10), step=1)
            
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
        has_ideco = st.checkbox("個人型iDeCoあり(本人)", value=get_val("has_ideco", False))
        if has_ideco:
            ideco_balance_init = st.number_input("iDeCo現在の残高(本人・万円)", value=int(get_val("ideco_balance_init", 1000000)/10000), step=10) * 10000
            ideco_monthly = st.number_input("iDeCo毎月の積立額(本人・万円)", value=get_val("ideco_monthly", 23000)/10000, step=0.1) * 10000
            ideco_start_age = st.number_input("iDeCo加入年齢（本人）", min_value=20, max_value=current_age, value=get_val("ideco_start_age", 30), step=1)
            ideco_receipt_age = st.number_input("iDeCo受取開始年齢(本人)", min_value=60, max_value=75, value=get_val("ideco_receipt_age", 60), step=1)
            if ideco_receipt_age > retirement_age:
                ideco_post_retirement_monthly = st.number_input("退職後のiDeCo積立額(本人・万円/月)", value=get_val("ideco_post_retirement_monthly", 0.0)/10000, step=0.1, help="退職〜受取開始までの掛金") * 10000
            else:
                ideco_post_retirement_monthly = ideco_monthly
            ideco_return = st.number_input("iDeCo期待リターン(本人・%)", min_value=0.0, max_value=10.0, value=get_val("ideco_return", 0.03)*100, step=0.1) / 100
            ideco_rec_opts = ["一時金", "年金(10年分割)"]
            saved_ideco_rec = get_val("ideco_receipt_type", "一時金")
            ideco_receipt_type = st.radio("iDeCo受取方法(本人)", ideco_rec_opts, index=ideco_rec_opts.index(saved_ideco_rec) if saved_ideco_rec in ideco_rec_opts else 0)
            if ideco_receipt_type == "一時金":
                ideco_dest_opts = ["預貯金へ", "NISA枠優先 (あふれた分は特定口座へ)", "特定口座へ(運用継続)"]
                saved_ideco_dest = get_val("ideco_lump_dest", "NISA枠優先 (あふれた分は特定口座へ)")
                ideco_lump_dest = st.radio("iDeCo一時金の入金先(本人)", ideco_dest_opts, index=ideco_dest_opts.index(saved_ideco_dest) if saved_ideco_dest in ideco_dest_opts else 1)
            else:
                ideco_lump_dest = "預貯金へ"
        else:
            ideco_balance_init = ideco_monthly = ideco_return = ideco_receipt_age = ideco_start_age = 0
            ideco_receipt_type = "一時金"
            ideco_lump_dest = "NISA枠優先 (あふれた分は特定口座へ)"
            ideco_post_retirement_monthly = 0
            
        has_dc = st.checkbox("企業型DCあり(本人)", value=get_val("has_dc", False))
        if has_dc:
            dc_balance_init = st.number_input("DC現在の残高(本人・万円)", value=int(get_val("dc_balance_init", 2000000)/10000), step=10) * 10000
            dc_monthly = st.number_input("DC毎月の会社拠出等(本人・万円)", value=get_val("dc_monthly", 10000)/10000, step=0.1) * 10000
            dc_return = st.number_input("DC期待リターン(本人・%)", min_value=0.0, max_value=10.0, value=get_val("dc_return", 0.03)*100, step=0.1) / 100
            
            dc_rec_opts = ["退職時にiDeCoへ移管し運用継続", "退職時に一時金として一括受取"]
            saved_dc_rec = get_val("dc_receipt_type", "退職時にiDeCoへ移管し運用継続")
            dc_receipt_type = st.radio("企業型DCの受取方針(本人)", dc_rec_opts, index=dc_rec_opts.index(saved_dc_rec) if saved_dc_rec in dc_rec_opts else 0)
        else:
            dc_balance_init = dc_monthly = dc_return = 0
            dc_receipt_type = "退職時にiDeCoへ移管し運用継続"

        st.markdown("**■ 配偶者分**")
        if has_marriage:
            has_sp_ideco = st.checkbox("個人型iDeCoあり(配偶者)", value=get_val("has_sp_ideco", False))
            if has_sp_ideco:
                sp_ideco_balance_init = st.number_input("iDeCo現在の残高(配偶者・万円)", value=int(get_val("sp_ideco_balance_init", 500000)/10000), step=10) * 10000
                sp_ideco_monthly = st.number_input("iDeCo毎月の積立額(配偶者・万円)", value=get_val("sp_ideco_monthly", 23000)/10000, step=0.1) * 10000
                sp_ideco_start_age = st.number_input("iDeCo加入年齢（配偶者）", min_value=20, max_value=current_age, value=get_val("sp_ideco_start_age", 30), step=1)
                sp_ideco_receipt_age = st.number_input("iDeCo受取開始年齢(配偶者)", min_value=60, max_value=75, value=get_val("sp_ideco_receipt_age", 60), step=1)
                if sp_ideco_receipt_age > sp_retirement_age:
                    sp_ideco_post_retirement_monthly = st.number_input("退職後のiDeCo積立額(配偶者・万円/月)", value=get_val("sp_ideco_post_retirement_monthly", 0.0)/10000, step=0.1, help="退職〜受取開始までの掛金") * 10000
                else:
                    sp_ideco_post_retirement_monthly = sp_ideco_monthly
                sp_ideco_return = st.number_input("iDeCo期待リターン(配偶者・%)", min_value=0.0, max_value=10.0, value=get_val("sp_ideco_return", 0.03)*100, step=0.1) / 100
                sp_ideco_rec_opts = ["一時金", "年金(10年分割)"]
                saved_sp_ideco_rec = get_val("sp_ideco_receipt_type", "一時金")
                sp_ideco_receipt_type = st.radio("iDeCo受取方法(配偶者)", sp_ideco_rec_opts, index=sp_ideco_rec_opts.index(saved_sp_ideco_rec) if saved_sp_ideco_rec in sp_ideco_rec_opts else 0)
                if sp_ideco_receipt_type == "一時金":
                    sp_ideco_dest_opts = ["預貯金へ", "NISA枠優先 (あふれた分は特定口座へ)", "特定口座へ(運用継続)"]
                    saved_sp_ideco_dest = get_val("sp_ideco_lump_dest", "NISA枠優先 (あふれた分は特定口座へ)")
                    sp_ideco_lump_dest = st.radio("iDeCo一時金の入金先(配偶者)", sp_ideco_dest_opts, index=sp_ideco_dest_opts.index(saved_sp_ideco_dest) if saved_sp_ideco_dest in sp_ideco_dest_opts else 1)
                else:
                    sp_ideco_lump_dest = "預貯金へ"
            else:
                sp_ideco_balance_init = sp_ideco_monthly = sp_ideco_return = sp_ideco_receipt_age = sp_ideco_start_age = 0
                sp_ideco_receipt_type = "一時金"
                sp_ideco_lump_dest = "NISA枠優先 (あふれた分は特定口座へ)"
                sp_ideco_post_retirement_monthly = 0
                
            has_sp_dc = st.checkbox("企業型DCあり(配偶者)", value=get_val("has_sp_dc", False))
            if has_sp_dc:
                sp_dc_balance_init = st.number_input("DC現在の残高(配偶者・万円)", value=int(get_val("sp_dc_balance_init", 1000000)/10000), step=10) * 10000
                sp_dc_monthly = st.number_input("DC毎月の会社拠出等(配偶者・万円)", value=get_val("sp_dc_monthly", 10000)/10000, step=0.1) * 10000
                sp_dc_return = st.number_input("DC期待リターン(配偶者・%)", min_value=0.0, max_value=10.0, value=get_val("sp_dc_return", 0.03)*100, step=0.1) / 100
                
                sp_dc_rec_opts = ["退職時にiDeCoへ移管し運用継続", "退職時に一時金として一括受取"]
                saved_sp_dc_rec = get_val("sp_dc_receipt_type", "退職時にiDeCoへ移管し運用継続")
                sp_dc_receipt_type = st.radio("企業型DCの受取方針(配偶者)", sp_dc_rec_opts, index=sp_dc_rec_opts.index(saved_sp_dc_rec) if saved_sp_dc_rec in sp_dc_rec_opts else 0)
            else:
                sp_dc_balance_init = sp_dc_monthly = sp_dc_return = 0
                sp_dc_receipt_type = "退職時にiDeCoへ移管し運用継続"
        else:
            has_sp_ideco = has_sp_dc = False
            sp_ideco_balance_init = sp_ideco_monthly = sp_ideco_return = sp_ideco_receipt_age = sp_ideco_start_age = 0
            sp_dc_balance_init = sp_dc_monthly = sp_dc_return = 0
            sp_ideco_receipt_type = "一時金"
            sp_ideco_lump_dest = "NISA枠優先 (あふれた分は特定口座へ)"
            sp_ideco_post_retirement_monthly = 0

with tabs[6]:
    st.header("その他 (生活費・イベント・税率)")
    use_lifestage_expense = st.checkbox("生活費をライフステージ（年齢）と家族構成で自動変動させる", value=get_val("use_lifestage_expense", False))
    if use_lifestage_expense:
        st.markdown("現在の**「住居費や保険料を除いた」**基本生活費を入力し、必要に応じて年代ごとのベース金額を調整してください。")
        st.info("※年代ごとのベース金額に対し、将来の配偶者や子どもの増減（独立など）による係数を乗算して最終的な生活費を算出します。")
        
        col_base1, col_base2 = st.columns(2)
        with col_base1:
            base_exp_20s = st.number_input("20代の基本生活費(住居等除く・万円/年)", value=int(get_val("base_exp_20s", 2000000) / 10000 if get_val("base_exp_20s", 2000000) > 10000 else get_val("base_exp_20s", 200)), step=10) * 10000
            base_exp_30s = st.number_input("30代の基本生活費(住居等除く・万円/年)", value=int(get_val("base_exp_30s", 2500000) / 10000 if get_val("base_exp_30s", 2500000) > 10000 else get_val("base_exp_30s", 250)), step=10) * 10000
            base_exp_40s = st.number_input("40代の基本生活費(住居等除く・万円/年)", value=int(get_val("base_exp_40s", 3000000) / 10000 if get_val("base_exp_40s", 3000000) > 10000 else get_val("base_exp_40s", 300)), step=10) * 10000
        with col_base2:
            base_exp_50s = st.number_input("50代の基本生活費(住居等除く・万円/年)", value=int(get_val("base_exp_50s", 3000000) / 10000 if get_val("base_exp_50s", 3000000) > 10000 else get_val("base_exp_50s", 300)), step=10) * 10000
            base_exp_60s = st.number_input("60代の基本生活費(住居等除く・万円/年)", value=int(get_val("base_exp_60s", 2500000) / 10000 if get_val("base_exp_60s", 2500000) > 10000 else get_val("base_exp_60s", 250)), step=10) * 10000
            base_exp_70s_plus = st.number_input("70代以降の基本生活費(住居等除く・万円/年)", value=int(get_val("base_exp_70s_plus", 2000000) / 10000 if get_val("base_exp_70s_plus", 2000000) > 10000 else get_val("base_exp_70s_plus", 200)), step=10) * 10000
        
        base_expense = 0
    else:
        base_expense = st.number_input("現在の基本生活費(全年代一律・保険住居除く・万円/年)", value=int(get_val("base_expense", 2500000) / 10000 if get_val("base_expense", 2500000) > 10000 else get_val("base_expense", 250)), step=10) * 10000
        base_exp_20s = base_exp_30s = base_exp_40s = base_exp_50s = base_exp_60s = base_exp_70s_plus = 0

    st.caption(f"📱 **正確な生活費がわからない方へ：** 銀行やクレカを自動連携できる [👉 人気の無料家計簿アプリ (PR)]({AFFILIATE_LINKS['kakeibo_app']}) を使うと、住居費や保険料を除いた正確な基本生活費が一目で把握できます。")
        
    inflation_rate = st.number_input("インフレ率 (%)", min_value=0.0, max_value=5.0, value=get_val("inflation_rate", 0.015)*100, step=0.1) / 100
    
    has_tax_increase = st.checkbox("将来の金融所得課税の引き上げ（増税）を想定する", value=get_val("has_tax_increase", float(get_val("future_tax_rate", 0.20)) > 0.20))
    if has_tax_increase:
        col_tx1, col_tx2 = st.columns(2)
        with col_tx1:
            future_tax_rate = st.number_input("引き上げ後の金融課税率 (%)", min_value=20.0, max_value=50.0, value=max(25.0, float(get_val("future_tax_rate", 0.25))*100), step=1.0) / 100
        with col_tx2:
            tax_change_age = st.number_input("増税される本人の年齢", min_value=current_age, max_value=100, value=get_val("tax_change_age", current_age + 10), step=1)
    else:
        future_tax_rate = 0.20
        tax_change_age = 1000

    st.markdown("---")
    st.subheader("不定期なライフイベント（特別支出）")
    st.write("旅行、冠婚葬祭、車検、医療費などを設定できます。周期を「1」にすると毎年、「2」にすると2年ごとに発生します。「単発」の場合は周期を空欄(または0)にしてください。")
    
    saved_events_data = get_val("events_df_data", None)
    if saved_events_data:
        default_events = pd.DataFrame(saved_events_data)
    else:
        default_events = pd.DataFrame({
            "イベント名": ["家電の買い替え", "スマホ・PC更新", "国内旅行・遠征等", "車検", "冠婚葬祭", "住宅修繕", "医療・入院予備費"],
            "開始年齢(本人)": [current_age + 5, current_age + 2, current_age + 1, current_age + 1, current_age + 2, 55, 65],
            "終了年齢(本人)": [85, 75, 70, 75, 60, 75, 85],
            "周期(年ごと)": [10, 4, 1, 2, 5, 10, 10],
            "費用(万円)": [40, 15, 10, 15, 30, 150, 50]
        })
    
    default_events = pd.concat([default_events, pd.DataFrame([{"イベント名": "", "開始年齢(本人)": None, "終了年齢(本人)": None, "周期(年ごと)": None, "費用(万円)": None}])], ignore_index=True)

    events_df = st.data_editor(default_events, num_rows="dynamic", key="events_editor")

    st.markdown("---")
    st.subheader("🛡️ 暴落時のガードレール（自動支出カット）設定")
    st.write("相場が大きく下落した年に、自動的に生活費や特別支出を切り詰めて資産の枯渇を防ぎます。（※削れる変動費として「基本生活費」と「イベント費」にのみ適用されます）")
    has_guardrail = st.checkbox("ガードレール機能を有効にする", value=get_val("has_guardrail", False))
    if has_guardrail:
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            guardrail_trigger = safe_number_input("発動条件: 年間リターンが何%下落(マイナス)したら", min_value=0.1, max_value=100.0, default_value=get_pct_val("guardrail_trigger", 15.0), step=1.0) / 100
        with col_g2:
            guardrail_cut = safe_number_input("カット率: その年の生活費・イベント費を何%削減するか", min_value=0.1, max_value=100.0, default_value=get_pct_val("guardrail_cut", 15.0), step=1.0) / 100
    else:
        guardrail_trigger = 0.0
        guardrail_cut = 0.0

with tabs[7]:
    st.header("老人ホーム入居・自宅売却")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("本人")
        has_nursing_home = st.checkbox("本人の入居予定あり", value=get_val("has_nursing_home", False))
        if has_nursing_home:
            nh_entry_age = st.number_input("入居する年齢(本人)", min_value=60, max_value=100, value=get_val("nh_entry_age", 80), step=1)
            nh_lump_sum = st.number_input("入居時費用（一時金・万円）(本人)", value=int(get_val("nh_lump_sum", 5000000)/10000), step=10) * 10000
            nh_monthly = st.number_input("月額費用（万円/月）(本人)", value=int(get_val("nh_monthly", 150000)/10000), step=1) * 10000
            nh_base_expense_adjustment = st.number_input("入居後の基本生活費(万円/年)(本人)", value=int(get_val("nh_base_expense_adjustment", 1200000)/10000), step=10) * 10000
        else:
            nh_entry_age = 1000
            nh_lump_sum = nh_monthly = nh_base_expense_adjustment = 0
            
    with col2:
        st.subheader("配偶者")
        if has_marriage:
            sp_has_nursing_home = st.checkbox("配偶者の入居予定あり", value=get_val("sp_has_nursing_home", False))
            if sp_has_nursing_home:
                sp_nh_entry_age = st.number_input("入居する年齢(配偶者)", min_value=60, max_value=100, value=get_val("sp_nh_entry_age", 80), step=1)
                sp_nh_lump_sum = st.number_input("入居時費用（一時金・万円）(配偶者)", value=int(get_val("sp_nh_lump_sum", 5000000)/10000), step=10) * 10000
                sp_nh_monthly = st.number_input("月額費用（万円/月）(配偶者)", value=int(get_val("sp_nh_monthly", 150000)/10000), step=1) * 10000
                sp_nh_base_expense_adjustment = st.number_input("入居後の基本生活費(万円/年)(配偶者)", value=int(get_val("sp_nh_base_expense_adjustment", 1200000)/10000), step=10) * 10000
            else:
                sp_nh_entry_age = 1000
                sp_nh_lump_sum = sp_nh_monthly = sp_nh_base_expense_adjustment = 0
        else:
            sp_has_nursing_home = False
            sp_nh_entry_age = 1000
            sp_nh_lump_sum = sp_nh_monthly = sp_nh_base_expense_adjustment = 0

    st.divider()
    if (housing_type == "持ち家" or has_housing) and (has_nursing_home or sp_has_nursing_home):
        has_home_sale = st.checkbox("老人ホーム入居時に持ち家を売却する", value=get_val("has_home_sale", True))
        if has_home_sale:
            home_sale_price = st.number_input("自宅売却価格（万円）", value=int(get_val("home_sale_price", 20000000)/10000), step=100) * 10000
            sale_opts = ["本人が入居した年", "配偶者が入居した年", "遅い方（二人とも入居した時点）"]
            if has_nursing_home and sp_has_nursing_home:
                saved_trig = get_val("home_sale_trigger", "遅い方（二人とも入居した時点）")
                home_sale_trigger = st.radio("売却のタイミング", sale_opts, index=sale_opts.index(saved_trig) if saved_trig in sale_opts else 2)
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

# --- 保存用の変数をまとめる処理 ---
_current_vars = dict(locals())
current_state = {}
for k, v in _current_vars.items():
    if not k.startswith('_') and type(v) in [int, float, str, bool]:
        current_state[k] = v

current_state["events_df_data"] = events_df.to_dict('records')

if st.session_state.get('save_requested'):
    encoded_str = encode_state(current_state)
    try:
        st.query_params["d"] = encoded_str
        st.toast("✅ URLを更新しました！ブラウザのURLをブックマークやお気に入りに保存してください。", icon="💾")
    except Exception as e:
        st.warning(f"URL保存時にエラーが発生しました（データが長すぎる可能性があります）: {e}")
    st.session_state['save_requested'] = False

# --- Simulation Logic ---
try:
    ages = list(range(current_age, life_expectancy + 1))
    years_count = len(ages)

    def run_simulation(return_arr, enable_defense=True):
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
        arr_exp_support = np.zeros(years_count) # ★追加：子どもへの仕送り
        arr_exp_ideco_savings_ins = np.zeros(years_count) # ★追加：iDeCo・貯蓄型保険等の掛金
        arr_exp_insurance = np.zeros(years_count)
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
        arr_spot_invest = np.zeros(years_count)

        arr_debt_housing = np.zeros(years_count)
        arr_debt_car = np.zeros(years_count)
        arr_debt_reform = np.zeros(years_count)
        arr_debt_edu = np.zeros(years_count)
        arr_debt_balance = np.zeros(years_count) 

        arr_mortgage_deduction = np.zeros(years_count)

        balances_savings = np.zeros(years_count)
        balances_dry_powder = np.zeros(years_count)
        balances_nisa = np.zeros(years_count)
        balances_taxable = np.zeros(years_count)
        balances_ideco_dc = np.zeros(years_count)
        total_assets = np.zeros(years_count)


        
        current_rent_annual = rent_annual
        last_rent_update_year = 0

        pension_actual = calc_pension_amount(pension_base, pension_start_age)
        
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
        use_dp = has_dry_powder and enable_defense
        use_gr = has_guardrail and enable_defense
        curr_main_savings = initial_savings + (initial_dry_powder if (has_dry_powder and not enable_defense) else 0)
        curr_dry_powder = initial_dry_powder if use_dp else 0
        
        curr_sp_nisa = sp_initial_nisa if has_marriage else 0
        curr_sp_taxable = sp_initial_taxable if has_marriage else 0
        curr_sp_savings = sp_initial_savings if has_marriage else 0

        curr_ideco_balance = ideco_balance_init
        curr_dc_balance = dc_balance_init
        ideco_pension_annual = 0
        main_past_ret_events = [] 
        ret_tax_details = [] 
        
        main_nisa_lifetime_invested = nisa_used_tsumitate + nisa_used_growth
        sp_nisa_lifetime_invested = sp_nisa_used_tsumitate + sp_nisa_used_growth if has_marriage else 0

        curr_sp_ideco_balance = sp_ideco_balance_init if has_marriage else 0
        curr_sp_dc_balance = sp_dc_balance_init if has_marriage else 0
        sp_ideco_pension_annual = 0
        sp_past_ret_events = [] 

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
                    if age == c_age:
                        pmt = calc_mortgage_pmt(cost, car_loan_rate, car_loan_years)
                        for j in range(i, min(years_count, i + car_loan_years)):
                            arr_car_loan_pmts[j] += pmt
                    c_age += car_replace_cycle
                    
            if has_marriage and sp_has_car and sp_car_loan_use:
                sp_c_age = sp_car_first_purchase_age
                while sp_c_age <= sp_age and sp_c_age <= sp_car_last_purchase_age:
                    cost = sp_car_first_purchase_cost if sp_c_age == sp_car_first_purchase_age else sp_car_replace_cost
                    years_passed = sp_age - sp_c_age
                    c_debt += calc_loan_balance(cost, sp_car_loan_rate, sp_car_loan_years, years_passed)
                    if sp_age == sp_c_age:
                        pmt = calc_mortgage_pmt(cost, sp_car_loan_rate, sp_car_loan_years)
                        for j in range(i, min(years_count, i + sp_car_loan_years)):
                            arr_car_loan_pmts[j] += pmt
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
            dc_lump_sum = 0
            
            if has_dc:
                if age < retirement_age:
                    curr_dc_balance = curr_dc_balance * (1 + dc_return) + (dc_monthly * 12)
                elif age == retirement_age:
                    if dc_receipt_type == "退職時にiDeCoへ移管し運用継続":
                        curr_ideco_balance += curr_dc_balance
                    else:
                        dc_lump_sum = curr_dc_balance
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
            sp_dc_lump_sum = 0
            
            if has_marriage:
                if has_sp_dc:
                    if sp_age < sp_retirement_age:
                        curr_sp_dc_balance = curr_sp_dc_balance * (1 + sp_dc_return) + (sp_dc_monthly * 12)
                    elif sp_age == sp_retirement_age:
                        if sp_dc_receipt_type == "退職時にiDeCoへ移管し運用継続":
                            curr_sp_ideco_balance += curr_sp_dc_balance
                        else:
                            sp_dc_lump_sum = curr_sp_dc_balance
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
                        if a == salary_decrease_age:
                            normal_salary_main *= (1 - salary_decrease_rate)
                        elif a > current_age:
                            if a <= salary_plateau_age:
                                normal_salary_main = min(normal_salary_main * (1 + salary_growth), salary_cap_amount)
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
                            if a == sp_salary_decrease_age:
                                normal_salary_sp *= (1 - sp_salary_decrease_rate)
                            elif a > current_age + sp_age_diff:
                                if a <= sp_salary_plateau_age:
                                    normal_salary_sp = min(normal_salary_sp * (1 + sp_salary_growth), sp_salary_cap_amount)
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
            
            
            main_ret_events_this_year = []
            if age == retirement_age and retirement_allowance > 0:
                main_ret_events_this_year.append({"type": "company", "label": "会社退職金", "start": employment_start_age, "end": retirement_age, "amount": retirement_allowance, "age": age})
            if dc_lump_sum > 0:
                # DC一時金は会社の退職金と同年合算されるため type:"company" として処理
                main_ret_events_this_year.append({"type": "company", "label": "企業型DC(一時金)", "start": employment_start_age, "end": retirement_age, "amount": dc_lump_sum, "age": age})
            
            if ideco_lump_sum > 0:
                ideco_label = "iDeCo (企業型DC移管分含む)" if (has_dc and dc_receipt_type == "退職時にiDeCoへ移管し運用継続") else "iDeCo"
                main_ret_events_this_year.append({"type": "ideco", "label": ideco_label, "start": ideco_start_age, "end": age, "amount": ideco_lump_sum, "age": age})
                
            if len(main_ret_events_this_year) == 1:
                ev = main_ret_events_this_year[0]
                it, rt, detail = calc_retirement_tax_with_rules(ev, main_past_ret_events, "本人")
                ret_inc_tax_main += it; ret_res_tax_main += rt
                if ev["type"] == "company": ret_net_main += (ev["amount"] - it - rt)
                else: ideco_lump_net_main = (ev["amount"] - it - rt)
                main_past_ret_events.append(ev)
                ret_tax_details.append(detail)
            elif len(main_ret_events_this_year) > 1:
                it, rt, detail = calc_same_year_retirement_tax(main_ret_events_this_year, "本人")
                ret_inc_tax_main += it; ret_res_tax_main += rt
                total_gross = sum(e["amount"] for e in main_ret_events_this_year)
                for ev in main_ret_events_this_year:
                    ratio = ev["amount"] / total_gross if total_gross > 0 else 0
                    if ev["type"] == "company": ret_net_main += (ev["amount"] - it * ratio - rt * ratio)
                    else: ideco_lump_net_main = (ev["amount"] - it * ratio - rt * ratio)
                    main_past_ret_events.append(ev)
                ret_tax_details.append(detail)
            
            ret_net_sp, ret_inc_tax_sp, ret_res_tax_sp = 0, 0, 0
            ideco_lump_net_sp = 0
            
            if has_marriage:
                sp_ret_events_this_year = []
                if sp_age == sp_retirement_age and sp_retirement_allowance > 0:
                    sp_ret_events_this_year.append({"type": "company", "label": "会社退職金", "start": sp_employment_start_age, "end": sp_retirement_age, "amount": sp_retirement_allowance, "age": sp_age})
                if sp_dc_lump_sum > 0:
                    sp_ret_events_this_year.append({"type": "company", "label": "企業型DC(一時金)", "start": sp_employment_start_age, "end": sp_retirement_age, "amount": sp_dc_lump_sum, "age": sp_age})
                    
                if sp_ideco_lump_sum > 0:
                    sp_ideco_label = "iDeCo (企業型DC移管分含む)" if (has_sp_dc and sp_dc_receipt_type == "退職時にiDeCoへ移管し運用継続") else "iDeCo"
                    sp_ret_events_this_year.append({"type": "ideco", "label": sp_ideco_label, "start": sp_ideco_start_age, "end": sp_age, "amount": sp_ideco_lump_sum, "age": sp_age})


                    
                if len(sp_ret_events_this_year) == 1:
                    ev = sp_ret_events_this_year[0]
                    it, rt, detail = calc_retirement_tax_with_rules(ev, sp_past_ret_events, "配偶者")
                    ret_inc_tax_sp += it; ret_res_tax_sp += rt
                    if ev["type"] == "company": ret_net_sp += (ev["amount"] - it - rt)
                    else: ideco_lump_net_sp = (ev["amount"] - it - rt)
                    sp_past_ret_events.append(ev)
                    ret_tax_details.append(detail)
                elif len(sp_ret_events_this_year) > 1:
                    it, rt, detail = calc_same_year_retirement_tax(sp_ret_events_this_year, "配偶者")
                    ret_inc_tax_sp += it; ret_res_tax_sp += rt
                    total_gross = sum(e["amount"] for e in sp_ret_events_this_year)
                    for ev in sp_ret_events_this_year:
                        ratio = ev["amount"] / total_gross if total_gross > 0 else 0
                        if ev["type"] == "company": ret_net_sp += (ev["amount"] - it * ratio - rt * ratio)
                        else: ideco_lump_net_sp = (ev["amount"] - it * ratio - rt * ratio)
                        sp_past_ret_events.append(ev)
                    ret_tax_details.append(detail)

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
                        
            # ★iDeCo・個人年金・貯蓄型保険の掛金を「基本生活費」から独立させて集計
            exp_ideco_savings_ins = 0
            if has_ideco and age < ideco_receipt_age: exp_ideco_savings_ins += (current_ideco_monthly * 12)
            if has_marriage and has_sp_ideco and sp_age < sp_ideco_receipt_age: exp_ideco_savings_ins += (current_sp_ideco_monthly * 12)
            exp_ideco_savings_ins += current_life_ins_prem + current_pp_prem
                
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
            
            # ★子どもへの仕送り（家賃＋生活費）も「基本生活費・住宅費」から独立させて集計
            exp_support = 0
            for child in child_settings:
                c_age = age - child["birth_age"]
                if c_age >= 4:
                    for start, end, course in child["course"]:
                        if course and start <= c_age <= end:
                            edu_cost = EDU_COST.get(course, 0) * 10000
                            if not use_edu_loan:
                                exp_edu += edu_cost
                                
                if child["uni_support"]["active"] and child["uni_support"]["start"] <= c_age <= child["uni_support"]["end"]:
                    exp_support += (child["uni_support"]["rent"] + child["uni_support"]["living"]) * 12
                                
            normal_exp_edu = exp_edu + arr_edu_loan_pmts[i]
            normal_exp_car = exp_car
            
            exp_house = normal_exp_house
            exp_edu = normal_exp_edu
            exp_car = normal_exp_car

            arr_exp_base[i] = exp_base
            arr_exp_support[i] = exp_support
            arr_exp_ideco_savings_ins[i] = exp_ideco_savings_ins
            arr_exp_insurance[i] = insurance_premium_yearly
            arr_exp_house[i] = exp_house
            arr_exp_edu[i] = exp_edu
            arr_exp_car[i] = exp_car
            arr_exp_nursing[i] = exp_nursing
            
            # --- 🛡️ ガードレール機能（相場暴落時の支出カット） ---
            if use_gr and return_arr[i] <= -guardrail_trigger:
                arr_exp_base[i] = arr_exp_base[i] * (1.0 - guardrail_cut)
                arr_exp_event[i] = arr_exp_event[i] * (1.0 - guardrail_cut)

            # 総支出の合算
            arr_total_exp[i] = arr_exp_base[i] + arr_exp_support[i] + arr_exp_ideco_savings_ins[i] + arr_exp_insurance[i] + arr_exp_event[i] + arr_exp_house[i] + arr_exp_edu[i] + arr_exp_car[i] + arr_exp_nursing[i]
            
            applicable_tax_rate = future_tax_rate if age >= tax_change_age else 0.20
            
            current_return = return_arr[i]
            current_taxable_real_return = current_return * (1 - applicable_tax_rate)
            
            calc_nisa = curr_main_nisa * (1 + current_return) + curr_sp_nisa * (1 + current_return)
            calc_taxable = curr_main_taxable * (1 + current_taxable_real_return) + curr_sp_taxable * (1 + current_taxable_real_return)
            calc_savings = curr_main_savings + curr_sp_savings
            
            # ★待機資金の平時運用（税引後利回り）
            dp_real_yield = dp_yield * (1 - applicable_tax_rate)
            calc_dry_powder = curr_dry_powder * (1 + dp_real_yield) if use_dp else 0
            
            w_taxable = (curr_main_taxable * withdrawal_rate_taxable if age >= withdrawal_start_age else 0) + (curr_sp_taxable * sp_withdrawal_rate_taxable if sp_age >= sp_withdrawal_start_age else 0)
            w_nisa = (curr_main_nisa * withdrawal_rate_nisa if age >= withdrawal_start_age else 0) + (curr_sp_nisa * sp_withdrawal_rate_nisa if sp_age >= sp_withdrawal_start_age else 0)
            
            calc_taxable -= w_taxable
            calc_nisa -= w_nisa
            
            annual_balance = arr_net_income[i] - arr_total_exp[i]
            arr_annual_balance[i] = annual_balance 
            
            lump_sum_income_this_year = 0
            main_nisa_annual_rem = 3600000
            sp_nisa_annual_rem = 3600000
            
            if has_home_sale:
                if home_sale_trigger == "本人が入居した年" and age == nh_entry_age:
                    calc_savings += home_sale_price
                    lump_sum_income_this_year += home_sale_price
                elif home_sale_trigger == "配偶者が入居した年" and sp_age == sp_nh_entry_age:
                    calc_savings += home_sale_price
                    lump_sum_income_this_year += home_sale_price
                elif home_sale_trigger == "遅い方（二人とも入居した時点）":
                    target_year = max(nh_entry_age if has_nursing_home else 0, sp_nh_entry_age if sp_has_nursing_home else 0)
                    if age == target_year or (sp_age == target_year and not has_nursing_home):
                        calc_savings += home_sale_price
                        lump_sum_income_this_year += home_sale_price
                
            if has_car and age == car_dispose_age and car_sale_price > 0:
                calc_savings += car_sale_price
                lump_sum_income_this_year += car_sale_price
                
            if has_marriage and sp_has_car and sp_age == sp_car_dispose_age and sp_car_sale_price > 0:
                calc_savings += sp_car_sale_price
                lump_sum_income_this_year += sp_car_sale_price
                
            if ret_net_main > 0:
                if ret_lump_dest == "特定口座へ(運用継続)":
                    calc_taxable += ret_net_main
                elif ret_lump_dest == "NISA枠優先 (あふれた分は特定口座へ)":
                    nisa_room_lifetime = max(0, 18000000 - main_nisa_lifetime_invested)
                    nisa_add = min(ret_net_main, main_nisa_annual_rem, nisa_room_lifetime)
                    taxable_add = ret_net_main - nisa_add
                    calc_nisa += nisa_add
                    calc_taxable += taxable_add
                    main_nisa_lifetime_invested += nisa_add
                    main_nisa_annual_rem -= nisa_add
                else:
                    calc_savings += ret_net_main
                    
            if ret_net_sp > 0:
                if sp_ret_lump_dest == "特定口座へ(運用継続)":
                    calc_taxable += ret_net_sp
                elif sp_ret_lump_dest == "NISA枠優先 (あふれた分は特定口座へ)":
                    nisa_room_lifetime = max(0, 18000000 - sp_nisa_lifetime_invested)
                    nisa_add = min(ret_net_sp, sp_nisa_annual_rem, nisa_room_lifetime)
                    taxable_add = ret_net_sp - nisa_add
                    calc_nisa += nisa_add
                    calc_taxable += taxable_add
                    sp_nisa_lifetime_invested += nisa_add
                    sp_nisa_annual_rem -= nisa_add
                else:
                    calc_savings += ret_net_sp
            
            if ideco_lump_net_main > 0:
                if ideco_lump_dest == "特定口座へ(運用継続)":
                    calc_taxable += ideco_lump_net_main
                elif ideco_lump_dest == "NISA枠優先 (あふれた分は特定口座へ)":
                    nisa_room_lifetime = max(0, 18000000 - main_nisa_lifetime_invested)
                    nisa_add = min(ideco_lump_net_main, main_nisa_annual_rem, nisa_room_lifetime)
                    taxable_add = ideco_lump_net_main - nisa_add
                    calc_nisa += nisa_add
                    calc_taxable += taxable_add
                    main_nisa_lifetime_invested += nisa_add
                    main_nisa_annual_rem -= nisa_add
                else:
                    calc_savings += ideco_lump_net_main
            
            if ideco_lump_net_sp > 0:
                if sp_ideco_lump_dest == "特定口座へ(運用継続)":
                    calc_taxable += ideco_lump_net_sp
                elif sp_ideco_lump_dest == "NISA枠優先 (あふれた分は特定口座へ)":
                    nisa_room_lifetime = max(0, 18000000 - sp_nisa_lifetime_invested)
                    nisa_add = min(ideco_lump_net_sp, sp_nisa_annual_rem, nisa_room_lifetime)
                    taxable_add = ideco_lump_net_sp - nisa_add
                    calc_nisa += nisa_add
                    calc_taxable += taxable_add
                    sp_nisa_lifetime_invested += nisa_add
                    sp_nisa_annual_rem -= nisa_add
                else:
                    calc_savings += ideco_lump_net_sp
                    
            prev_savings_balance = calc_savings
            
            arr_lump_sum_income[i] = lump_sum_income_this_year
            calc_savings += annual_balance + w_taxable + w_nisa
            actual_withdrawal_this_year = w_taxable + w_nisa
            
            # ★総資産と各維持ライン（預貯金最低・預貯金最高・待機資金上限）の算出
            current_total_assets = max(0, calc_savings + calc_dry_powder + calc_taxable + calc_nisa + curr_ideco_balance + curr_dc_balance + curr_sp_ideco_balance + curr_sp_dc_balance)
            
            # 1) 預貯金の最低維持ライン (target_savings)
            rate_amount = current_total_assets * min_savings_rate
            if min_savings_rule == "金額が高い方を採用": target_savings = max(min_savings_amount, rate_amount)
            elif min_savings_rule == "金額が低い方を採用": target_savings = min(min_savings_amount, rate_amount)
            elif min_savings_rule == "定率のみを採用": target_savings = rate_amount
            else: target_savings = min_savings_amount

            # 2) 暴落待機資金の目標上限枠 (target_dp_cap)
            if use_dp:
                dp_rate_amount = current_total_assets * dp_max_rate
                if dp_max_rule == "金額が高い方を採用": target_dp_cap = max(dp_max_cap, dp_rate_amount)
                elif dp_max_rule == "金額が低い方を採用": target_dp_cap = min(dp_max_cap, dp_rate_amount)
                elif dp_max_rule == "定率のみを採用": target_dp_cap = dp_rate_amount
                else: target_dp_cap = dp_max_cap
            else:
                target_dp_cap = 0

            # ★【バグ修正】まず「純粋な収支赤字による預貯金の最低ライン割れ」を補填する（積立や超過投資で減った分を赤字と誤認させないため先に処理）
            shortfall_to_fill = max(0, target_savings - calc_savings)
            max_allowed_withdrawal = max(0, prev_savings_balance - calc_savings)
            shortfall = min(shortfall_to_fill, max_allowed_withdrawal)
            
            if shortfall > 0:
                if deficit_order == "特定口座(世帯) → NISA(世帯) → 預貯金を最低維持ラインまで使う":
                    order = [(calc_taxable, 'taxable'), (calc_nisa, 'nisa')]
                elif deficit_order == "NISA(世帯) → 特定口座(世帯) → 預貯金を最低維持ラインまで使う":
                    order = [(calc_nisa, 'nisa'), (calc_taxable, 'taxable')]
                else:
                    order = [(calc_taxable, 'taxable'), (calc_nisa, 'nisa')]
                    
                for val, name in order:
                    if shortfall <= 0: break
                    take = min(val, shortfall)
                    if name == 'taxable': calc_taxable -= take
                    elif name == 'nisa': calc_nisa -= take
                    calc_savings += take
                    shortfall -= take
                    actual_withdrawal_this_year += take

            arr_withdrawal_amount[i] = actual_withdrawal_this_year

            # --- 積立・暴落待機資金・最高維持ライン超過スイープ処理 ---
            if has_investment and age <= invest_end_age:
                invest_available_main = invest_monthly * 12
            else:
                invest_available_main = 0
                
            if sp_has_investment and sp_age <= sp_invest_end_age:
                invest_available_sp = sp_invest_monthly * 12
            else:
                invest_available_sp = 0
                
            total_invest_target = invest_available_main + invest_available_sp
            is_crash_year = use_dp and (current_return <= -dp_step_drop)

            # ★平時かつ「待機資金のプールを最優先」の場合、通常積立の前に最低維持ライン超えの余剰分から待機資金を上限枠(target_dp_cap)まで満たす
            if use_dp and not is_crash_year and "待機資金のプールを最優先" in dp_refill_priority:
                if calc_dry_powder < target_dp_cap:
                    surplus_for_dp = max(0, calc_savings - target_savings)
                    needed_dp = target_dp_cap - calc_dry_powder
                    refill_amount = min(surplus_for_dp, needed_dp)
                    calc_savings -= refill_amount
                    calc_dry_powder += refill_amount

            # 通常の毎月積立投資（最低維持ライン target_savings を割らない範囲で実行）
            invest_available_from_savings = max(0, calc_savings - target_savings)
            actual_invest = min(total_invest_target, invest_available_from_savings)
            
            if actual_invest > 0:
                ratio_main = invest_available_main / total_invest_target if total_invest_target > 0 else 0
                actual_main_invest = actual_invest * ratio_main
                actual_sp_invest = actual_invest - actual_main_invest
                
                if actual_main_invest > 0:
                    if invest_strategy == "NISA優先 (年間360万/生涯1800万上限、超過分は特定口座)":
                        nisa_room_lifetime = max(0, 18000000 - main_nisa_lifetime_invested)
                        nisa_add = min(actual_main_invest, main_nisa_annual_rem, nisa_room_lifetime)
                        taxable_add = actual_main_invest - nisa_add
                        calc_nisa += nisa_add
                        calc_taxable += taxable_add
                        main_nisa_lifetime_invested += nisa_add
                        main_nisa_annual_rem -= nisa_add
                    else:
                        calc_taxable += actual_main_invest
                        
                if actual_sp_invest > 0:
                    if sp_invest_strategy == "NISA優先":
                        nisa_room_lifetime = max(0, 18000000 - sp_nisa_lifetime_invested)
                        nisa_add = min(actual_sp_invest, sp_nisa_annual_rem, nisa_room_lifetime)
                        taxable_add = actual_sp_invest - nisa_add
                        calc_nisa += nisa_add
                        calc_taxable += taxable_add
                        sp_nisa_lifetime_invested += nisa_add
                        sp_nisa_annual_rem -= nisa_add
                    else:
                        calc_taxable += actual_sp_invest

                calc_savings -= actual_invest
            arr_invest_amount[i] = actual_invest

            # --- ★暴落時スポット投資 ＆ 平時の待機資金調整（補充・上限超過スイープ） ---
            spot_invest_this_year = 0
            if use_dp:
                if is_crash_year and calc_dry_powder > 0:
                    drop_abs = abs(current_return)
                    if drop_abs >= dp_full_drop:
                        deploy_ratio = 1.0
                    else:
                        steps_reached = int(drop_abs // dp_step_drop)
                        if dp_calc_mode == "累積・残高基準（通過ステップごとにその時の残高の〇%を順次投入）":
                            rem_ratio = 1.0
                            for s in range(1, steps_reached + 1):
                                stage_r = min(1.0, s * dp_step_rate)
                                rem_ratio *= (1.0 - stage_r)
                            deploy_ratio = 1.0 - rem_ratio
                        elif dp_calc_mode == "累積・当初枠基準（通過ステップの投入率を単純合算して投入）":
                            deploy_ratio = min(1.0, sum(s * dp_step_rate for s in range(1, steps_reached + 1)))
                        else:
                            deploy_ratio = min(1.0, steps_reached * dp_step_rate)
                            
                    spot_invest_this_year = calc_dry_powder * deploy_ratio
                    calc_dry_powder -= spot_invest_this_year
                    
                    nisa_room_lifetime = max(0, 18000000 - main_nisa_lifetime_invested)
                    nisa_add = min(spot_invest_this_year, main_nisa_annual_rem, nisa_room_lifetime)
                    taxable_add = spot_invest_this_year - nisa_add
                    calc_nisa += nisa_add
                    calc_taxable += taxable_add
                    main_nisa_lifetime_invested += nisa_add
                    main_nisa_annual_rem -= nisa_add
                elif not is_crash_year:
                    if calc_dry_powder < target_dp_cap:
                        # 上限枠に空きがある場合、最低維持ラインを超える余剰預貯金があれば補充
                        surplus_savings = max(0, calc_savings - target_savings)
                        needed_dp = target_dp_cap - calc_dry_powder
                        refill_amount = min(surplus_savings, needed_dp)
                        calc_savings -= refill_amount
                        calc_dry_powder += refill_amount
                    elif calc_dry_powder > target_dp_cap:
                        # ★【バグ修正】利回りや総資産変動で待機資金が上限枠(target_dp_cap)を超えている場合、超過分を投資(NISA優先→特定口座)へスイープして上限以下に揃える
                        excess_dp = calc_dry_powder - target_dp_cap
                        calc_dry_powder -= excess_dp
                        nisa_room_lifetime = max(0, 18000000 - main_nisa_lifetime_invested)
                        nisa_add = min(excess_dp, main_nisa_annual_rem, nisa_room_lifetime)
                        taxable_add = excess_dp - nisa_add
                        calc_nisa += nisa_add
                        calc_taxable += taxable_add
                        main_nisa_lifetime_invested += nisa_add
                        main_nisa_annual_rem -= nisa_add
                        arr_invest_amount[i] += excess_dp
                        
            arr_spot_invest[i] = spot_invest_this_year

            # --- ★預貯金の最高維持ライン超過分の自動投資（NISA優先→特定口座スイープ）ロジック ---
            if has_max_savings_cap:
                max_rate_amount = current_total_assets * max_savings_rate
                if max_savings_rule == "金額が高い方を採用":
                    raw_max_target = max(max_savings_amount, max_rate_amount)
                elif max_savings_rule == "金額が低い方を採用":
                    raw_max_target = min(max_savings_amount, max_rate_amount)
                elif max_savings_rule == "定率のみを採用":
                    raw_max_target = max_rate_amount
                else:
                    raw_max_target = max_savings_amount
                
                # 最低維持ライン(target_savings)を下回らないよう安全補正
                effective_max_savings = max(target_savings, raw_max_target)
                
                if calc_savings > effective_max_savings:
                    excess_savings = calc_savings - effective_max_savings
                    calc_savings -= excess_savings
                    
                    # NISA枠優先（年間360万/生涯1800万の残り枠）→ 超過分は特定口座へ自動積立
                    nisa_room_lifetime = max(0, 18000000 - main_nisa_lifetime_invested)
                    nisa_add = min(excess_savings, main_nisa_annual_rem, nisa_room_lifetime)
                    taxable_add = excess_savings - nisa_add
                    calc_nisa += nisa_add
                    calc_taxable += taxable_add
                    main_nisa_lifetime_invested += nisa_add
                    main_nisa_annual_rem -= nisa_add
                        
                    arr_invest_amount[i] += excess_savings

            balances_nisa[i] = max(0, calc_nisa)
            balances_taxable[i] = max(0, calc_taxable)
            balances_savings[i] = calc_savings
            balances_dry_powder[i] = max(0, calc_dry_powder)
            balances_ideco_dc[i] = max(0, curr_ideco_balance + curr_dc_balance + curr_sp_ideco_balance + curr_sp_dc_balance)
            total_assets[i] = balances_savings[i] + balances_dry_powder[i] + balances_nisa[i] + balances_taxable[i] + balances_ideco_dc[i]
            
            curr_main_nisa = balances_nisa[i]
            curr_main_taxable = balances_taxable[i]
            curr_main_savings = balances_savings[i]
            curr_dry_powder = balances_dry_powder[i]
            curr_sp_nisa = 0
            curr_sp_taxable = 0
            curr_sp_savings = 0

        depletion_age = next((ages[i] for i, total in enumerate(total_assets - balances_ideco_dc) if total <= 0), None)
        
        return {
            "ages": ages,
            "years_count": years_count,
            "arr_salary": arr_salary,
            "arr_sp_salary": arr_sp_salary,
            "arr_pension": arr_pension,
            "arr_sp_pension": arr_sp_pension,
            "arr_other_misc_income": arr_other_misc_income,
            "arr_child_allowance": arr_child_allowance,
            "arr_leave_benefit": arr_leave_benefit,
            "arr_ret_income": arr_ret_income,
            "arr_lump_sum_income": arr_lump_sum_income,
            "arr_net_income": arr_net_income,
            "arr_soc_ins": arr_soc_ins,
            "arr_sp_soc_ins": arr_sp_soc_ins,
            "arr_inc_tax": arr_inc_tax,
            "arr_sp_inc_tax": arr_sp_inc_tax,
            "arr_res_tax": arr_res_tax,
            "arr_sp_res_tax": arr_sp_res_tax,
            "arr_ret_inc_tax": arr_ret_inc_tax,
            "arr_ret_res_tax": arr_ret_res_tax,
            "arr_exp_base": arr_exp_base,
            "arr_exp_support": arr_exp_support,
            "arr_exp_ideco_savings_ins": arr_exp_ideco_savings_ins,
            "arr_exp_insurance": arr_exp_insurance,
            "arr_exp_event": arr_exp_event,
            "arr_exp_house": arr_exp_house,
            "arr_exp_edu": arr_exp_edu,
            "arr_exp_car": arr_exp_car,
            "arr_exp_nursing": arr_exp_nursing,
            "arr_total_exp": arr_total_exp,
            "arr_withdrawal_amount": arr_withdrawal_amount,
            "arr_annual_balance": arr_annual_balance,
            "arr_car_loan_pmts": arr_car_loan_pmts,
            "arr_edu_loan_pmts": arr_edu_loan_pmts,
            "arr_reform_loan_pmts": arr_reform_loan_pmts,
            "arr_invest_amount": arr_invest_amount,
            "arr_spot_invest": arr_spot_invest,
            "arr_debt_housing": arr_debt_housing,
            "arr_debt_car": arr_debt_car,
            "arr_debt_reform": arr_debt_reform,
            "arr_debt_edu": arr_debt_edu,
            "arr_debt_balance": arr_debt_balance,
            "arr_mortgage_deduction": arr_mortgage_deduction,
            "balances_savings": balances_savings,
            "balances_dry_powder": balances_dry_powder,
            "balances_nisa": balances_nisa,
            "balances_taxable": balances_taxable,
            "balances_ideco_dc": balances_ideco_dc,
            "total_assets": total_assets,
            "depletion_age": depletion_age,
            "arr_ret_tax_details": ret_tax_details,
            "arr_return_rate": return_arr
        }

    def generate_return_array(expected_ret, risk, mode="fixed", hist_key="S&P500 (米国株式)", start_yr=2000):
        if mode == "fixed":
            arr = np.full(years_count, expected_ret)
        elif mode == "historical":
            base_seq = HIST_RETURNS.get(hist_key, HIST_RETURNS["S&P500 (米国株式)"])
            s_idx = HIST_YEARS.index(start_yr) if start_yr in HIST_YEARS else 0
            arr = np.array([base_seq[(s_idx + y) % len(base_seq)] for y in range(years_count)], dtype=float)
        else:
            arr = np.random.normal(expected_ret, risk, years_count)
            if mc_crash_prob > 0:
                low_bound = min(mc_crash_min, mc_crash_max)
                high_bound = max(mc_crash_min, mc_crash_max)
                for y in range(years_count):
                    if np.random.rand() < mc_crash_prob:
                        arr[y] -= np.random.uniform(low_bound, high_bound)
            
        if has_market_shock and shock_age in ages:
            idx = ages.index(shock_age)
            arr[idx] = -shock_drop_rate 
        return arr

    if sim_mode == "定率シミュレーション（基本）":
        ret_arr = generate_return_array(expected_return, 0.0, "fixed")
        res_base = run_simulation(ret_arr, enable_defense=True)
        res = res_base
        
        depletion_age = res_base["depletion_age"]
        depletion_age_p10 = None
        percentile_10_no_def = None
        mc_avg_spot_count = 0.0
        mc_avg_spot_total = 0.0

    elif sim_mode == "ヒストリカル・バックテスト（S&P500 / オルカンの過去実績を適用）":
        sub_index_choice = "オールカントリー (全世界株式 / MSCI ACWI)" if "S&P500" in hist_index_choice else "S&P500 (米国株式)"
        ret_arr_main = generate_return_array(0.0, 0.0, "historical", hist_index_choice, hist_start_year)
        ret_arr_sub = generate_return_array(0.0, 0.0, "historical", sub_index_choice, hist_start_year)
        
        res_base = run_simulation(ret_arr_main, enable_defense=True)
        res_sub = run_simulation(ret_arr_sub, enable_defense=True)
        res = res_base
        
        depletion_age = res_base["depletion_age"]
        depletion_age_p10 = res_sub["depletion_age"]
        
        hist_net_main = res_base["total_assets"] - res_base["arr_debt_balance"]
        hist_net_sub = res_sub["total_assets"] - res_sub["arr_debt_balance"]
        
        if has_dry_powder or has_guardrail:
            res_no_def = run_simulation(ret_arr_main, enable_defense=False)
            hist_net_no_def = res_no_def["total_assets"] - res_no_def["arr_debt_balance"]
            depletion_age_hist_no_def = res_no_def["depletion_age"]
        else:
            res_no_def = None
            hist_net_no_def = None
            depletion_age_hist_no_def = None
            
        percentile_10_no_def = None
        mc_avg_spot_count = float(np.sum(res_base["arr_spot_invest"] > 0))
        mc_avg_spot_total = float(np.sum(res_base["arr_spot_invest"]))
        
    else:
        ret_arr_base = generate_return_array(expected_return, risk_std, "fixed")
        res_base = run_simulation(ret_arr_base, enable_defense=True)
        depletion_age = res_base["depletion_age"]
        
        state_hash = json.dumps(current_state, sort_keys=True, default=str)
        need_recalc = True
        
        if mc_pause_auto and 'mc_cached_data' in st.session_state:
            st.info("⚡ **連続入力モード中：** 入力変更による自動モンテカルロ計算を一時停止しています。すべての数値の入力が終わったら下のボタンを押してください。")
            if st.button("🔄 最新の入力内容でモンテカルロ・シミュレーションを実行する", type="primary", use_container_width=True):
                need_recalc = True
            else:
                need_recalc = False
        elif 'mc_cached_data' in st.session_state and st.session_state.get('mc_cached_hash') == state_hash:
            need_recalc = False

        if need_recalc:
            NUM_SIMULATIONS = 300
            mc_net_assets = []
            mc_sim_results = []
            mc_net_assets_no_def = []
            mc_spot_counts = []
            mc_spot_totals = []
            
            defense_active = has_dry_powder or has_guardrail
            np.random.seed(42)
            
            with st.spinner("モンテカルロ・シミュレーションを計算中..."):
                for _ in range(NUM_SIMULATIONS):
                    ret_arr = generate_return_array(expected_return, risk_std, "montecarlo")
                    sim_res = run_simulation(ret_arr, enable_defense=True)
                    net_assets = sim_res["total_assets"] - sim_res["arr_debt_balance"]
                    mc_net_assets.append(net_assets)
                    mc_sim_results.append(sim_res)
                    
                    mc_spot_counts.append(int(np.sum(sim_res["arr_spot_invest"] > 0)))
                    mc_spot_totals.append(float(np.sum(sim_res["arr_spot_invest"])))
                    
                    if defense_active:
                        sim_res_no_def = run_simulation(ret_arr, enable_defense=False)
                        net_assets_no_def = sim_res_no_def["total_assets"] - sim_res_no_def["arr_debt_balance"]
                        mc_net_assets_no_def.append(net_assets_no_def)
                    
            mc_net_assets = np.array(mc_net_assets)
            percentile_90 = np.percentile(mc_net_assets, 90, axis=0)
            percentile_50 = np.percentile(mc_net_assets, 50, axis=0)
            percentile_10 = np.percentile(mc_net_assets, 10, axis=0)
            
            depletion_age_p10 = next((ages[i] for i, total in enumerate(percentile_10) if total <= 0), None)
            
            if defense_active and len(mc_net_assets_no_def) > 0:
                mc_net_assets_no_def = np.array(mc_net_assets_no_def)
                percentile_10_no_def = np.percentile(mc_net_assets_no_def, 10, axis=0)
                depletion_age_p10_no_def = next((ages[i] for i, total in enumerate(percentile_10_no_def) if total <= 0), None)
            else:
                percentile_10_no_def = None
                depletion_age_p10_no_def = None
                
            mc_avg_spot_count = float(np.mean(mc_spot_counts))
            mc_avg_spot_total = float(np.mean(mc_spot_totals))
            
            check_idx = ages.index(85) if 85 in ages else -1
            idx_p10 = int(np.argmin(np.abs(mc_net_assets[:, check_idx] - percentile_10[check_idx])))
            idx_p50 = int(np.argmin(np.abs(mc_net_assets[:, check_idx] - percentile_50[check_idx])))
            idx_p90 = int(np.argmin(np.abs(mc_net_assets[:, check_idx] - percentile_90[check_idx])))
            
            res_p10_rep = mc_sim_results[idx_p10]
            res_p50_rep = mc_sim_results[idx_p50]
            res_p90_rep = mc_sim_results[idx_p90]
            
            st.session_state['mc_cached_hash'] = state_hash
            st.session_state['mc_cached_data'] = {
                "percentile_90": percentile_90, "percentile_50": percentile_50, "percentile_10": percentile_10,
                "depletion_age_p10": depletion_age_p10, "percentile_10_no_def": percentile_10_no_def,
                "depletion_age_p10_no_def": depletion_age_p10_no_def, "mc_avg_spot_count": mc_avg_spot_count,
                "mc_avg_spot_total": mc_avg_spot_total, "res_p10_rep": res_p10_rep, "res_p50_rep": res_p50_rep, "res_p90_rep": res_p90_rep
            }
        else:
            cached = st.session_state['mc_cached_data']
            percentile_90 = cached["percentile_90"]
            percentile_50 = cached["percentile_50"]
            percentile_10 = cached["percentile_10"]
            depletion_age_p10 = cached["depletion_age_p10"]
            percentile_10_no_def = cached["percentile_10_no_def"]
            depletion_age_p10_no_def = cached["depletion_age_p10_no_def"]
            mc_avg_spot_count = cached["mc_avg_spot_count"]
            mc_avg_spot_total = cached["mc_avg_spot_total"]
            res_p10_rep = cached["res_p10_rep"]
            res_p50_rep = cached["res_p50_rep"]
            res_p90_rep = cached["res_p90_rep"]
            
        res = res_base

    ret_idx = ages.index(retirement_age) if retirement_age in ages else 0
    req_cash = 0
    req_invested = 0
    
    for age in reversed(ages[ret_idx:]):
        i = ages.index(age)
        sp_age = age + sp_age_diff if has_marriage else 0
        
        sale_income = 0
        if has_home_sale:
            if home_sale_trigger == "本人が入居した年" and age == nh_entry_age: sale_income += home_sale_price
            elif home_sale_trigger == "配偶者が入居した年" and sp_age == sp_nh_entry_age: sale_income += home_sale_price
            elif home_sale_trigger == "遅い方（二人とも入居した時点）":
                target_year = max(nh_entry_age if has_nursing_home else 0, sp_nh_entry_age if sp_has_nursing_home else 0)
                if age == target_year or (sp_age == target_year and not has_nursing_home): sale_income += home_sale_price
                
        if has_car and age == car_dispose_age: sale_income += car_sale_price
        if has_marriage and sp_has_car and sp_age == sp_car_dispose_age: sale_income += sp_car_sale_price
        
        shortfall = res_base["arr_total_exp"][i] - res_base["arr_net_income"][i] - sale_income
        req_cash += shortfall
        
        applicable_tax_rate = future_tax_rate if age >= tax_change_age else 0.20
        taxable_real_return = expected_return * (1 - applicable_tax_rate)
        req_invested = (req_invested / (1 + taxable_real_return)) + shortfall

    req_cash = max(0, req_cash)
    req_invested = max(0, req_invested)


    # --- UI Outputs ---
    st.markdown("---")
    st.markdown("### 📊 シミュレーション結果サマリー")
    
    col1, col2, col3, col4 = st.columns(4)
    if sim_mode == "モンテカルロシミュレーション（リスク・暴落を考慮）":
        with col1:
            color_class = "red" if depletion_age else ""
            st.markdown(f'<div class="metric-card"><div class="metric-title" style="font-size:0.9rem;">資産の枯渇年齢 (標準/中央値)</div><div class="metric-value {color_class}">{depletion_age if depletion_age else "枯渇なし"}歳</div></div>', unsafe_allow_html=True)
        with col2:
            color_class_p10 = "red" if depletion_age_p10 else ""
            st.markdown(f'<div class="metric-card"><div class="metric-title" style="font-size:0.9rem;">資産の枯渇年齢 (悲観/下位10%)</div><div class="metric-value {color_class_p10}">{depletion_age_p10 if depletion_age_p10 else "枯渇なし"}歳</div></div>', unsafe_allow_html=True)
        with col3:
            check_idx = ages.index(85) if 85 in ages else -1
            val_85_p50 = percentile_50[check_idx]
            val_85_p10 = percentile_10[check_idx]
            st.markdown(f'<div class="metric-card"><div class="metric-title" style="font-size:0.9rem;">85歳純資産 (中央値 / 悲観)</div><div class="metric-value" style="font-size:1.35rem;">{format_man_oku_val(val_85_p50/10000)}<br><span style="font-size:0.95rem;color:#dc3545;">(悲観: {format_man_oku_val(val_85_p10/10000)})</span></div></div>', unsafe_allow_html=True)
        with col4:
            color_class_req2 = "red" if req_invested > 0 else ""
            st.markdown(f'<div class="metric-card"><div class="metric-title" style="font-size:0.9rem;">退職時の必要額 (運用 / 貯金のみ)</div><div class="metric-value {color_class_req2}" style="font-size:1.35rem;">{format_man_oku_val(req_invested/10000)}<br><span style="font-size:0.95rem;color:#495057;">(貯金: {format_man_oku_val(req_cash/10000)})</span></div></div>', unsafe_allow_html=True)
    elif sim_mode == "ヒストリカル・バックテスト（S&P500 / オルカンの過去実績を適用）":
        short_main = "S&P500" if "S&P500" in hist_index_choice else "オルカン"
        short_sub = "オルカン" if "S&P500" in hist_index_choice else "S&P500"
        check_idx = ages.index(85) if 85 in ages else -1
        with col1:
            color_class = "red" if depletion_age else ""
            st.markdown(f'<div class="metric-card"><div class="metric-title" style="font-size:0.9rem;">枯渇年齢 ({short_main} / {hist_start_year}年〜)</div><div class="metric-value {color_class}">{depletion_age if depletion_age else "枯渇なし"}歳</div></div>', unsafe_allow_html=True)
        with col2:
            color_class_sub = "red" if depletion_age_p10 else ""
            st.markdown(f'<div class="metric-card"><div class="metric-title" style="font-size:0.9rem;">枯渇年齢 (比較: {short_sub})</div><div class="metric-value {color_class_sub}">{depletion_age_p10 if depletion_age_p10 else "枯渇なし"}歳</div></div>', unsafe_allow_html=True)
        with col3:
            val_85_m = hist_net_main[check_idx]
            val_85_s = hist_net_sub[check_idx]
            st.markdown(f'<div class="metric-card"><div class="metric-title" style="font-size:0.9rem;">85歳純資産 ({short_main} / {short_sub})</div><div class="metric-value" style="font-size:1.35rem;">{format_man_oku_val(val_85_m/10000)}<br><span style="font-size:0.95rem;color:#ff7f0e;">({short_sub}: {format_man_oku_val(val_85_s/10000)})</span></div></div>', unsafe_allow_html=True)
        with col4:
            color_class_req2 = "red" if req_invested > 0 else ""
            st.markdown(f'<div class="metric-card"><div class="metric-title" style="font-size:0.9rem;">退職時の必要額 (運用 / 貯金のみ)</div><div class="metric-value {color_class_req2}" style="font-size:1.35rem;">{format_man_oku_val(req_invested/10000)}<br><span style="font-size:0.95rem;color:#495057;">(貯金: {format_man_oku_val(req_cash/10000)})</span></div></div>', unsafe_allow_html=True)
    else:
        with col1:
            color_class = "red" if depletion_age else ""
            st.markdown(f'<div class="metric-card"><div class="metric-title" style="font-size:0.95rem;">資産の枯渇年齢</div><div class="metric-value {color_class}">{depletion_age if depletion_age else "枯渇なし"}歳</div></div>', unsafe_allow_html=True)
        with col2:
            val_85 = res_base["total_assets"][ages.index(85) if 85 in ages else -1] - res_base["arr_debt_balance"][ages.index(85) if 85 in ages else -1]
            st.markdown(f'<div class="metric-card"><div class="metric-title" style="font-size:0.95rem;">85歳時点の純資産</div><div class="metric-value">{format_man_oku_val(val_85/10000)}</div></div>', unsafe_allow_html=True)
        with col3:
            color_class_req1 = "red" if req_cash > 0 else ""
            st.markdown(f'<div class="metric-card"><div class="metric-title" style="font-size:0.95rem;">退職時の必要額(貯金のみ)</div><div class="metric-value {color_class_req1}">{format_man_oku_val(req_cash/10000)}</div></div>', unsafe_allow_html=True)
        with col4:
            color_class_req2 = "red" if req_invested > 0 else ""
            st.markdown(f'<div class="metric-card"><div class="metric-title" style="font-size:0.95rem;">退職時の必要額(運用取崩)</div><div class="metric-value {color_class_req2}">{format_man_oku_val(req_invested/10000)}</div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

# --- ★新設：シミュレーション数値連動型「AI家計・資産改善ポテンシャル診断」 ---
    init_fam_ded = 380000 if (has_marriage and current_age >= marriage_age and (not actual_sp_working or sp_gross_income <= 1500000)) else 0
    for ch in child_settings:
        c_a = current_age - ch["birth_age"]
        if 16 <= c_a <= 18: init_fam_ded += 380000
        elif 19 <= c_a <= 22: init_fam_ded += 630000
    init_ideco_m = (ideco_monthly * 12) if (has_ideco and current_age < ideco_receipt_age) else 0
    init_ideco_s = (sp_ideco_monthly * 12) if (has_marriage and has_sp_ideco and (current_age + sp_age_diff) < sp_ideco_receipt_age) else 0

    furusato_limit_main = calc_furusato_limit(res_base["arr_salary"][0], res_base["arr_pension"][0], init_ideco_m, init_fam_ded, current_age, actual_is_working)
    furusato_limit_sp = calc_furusato_limit(res_base["arr_sp_salary"][0], res_base["arr_sp_pension"][0], init_ideco_s, 0, current_age + sp_age_diff, actual_sp_working) if has_marriage else 0
    furusato_limit_total = furusato_limit_main + furusato_limit_sp

    with st.container(border=True):
        st.markdown("##### 💡 シミュレーション数値に基づく「家計・資産の改善ポテンシャル診断」")
        if furusato_limit_total >= 10000:
            sp_fur_text = f"（本人: 約{furusato_limit_main/10000:,.1f}万円 ／ 配偶者: 約{furusato_limit_sp/10000:,.1f}万円）" if furusato_limit_sp > 0 else ""
            col_fur_txt, col_fur_btn = st.columns([7, 3])
            with col_fur_txt:
                st.markdown(f"🎁 **今年のふるさと納税 控除上限目安：世帯合計 約 {furusato_limit_total/10000:,.1f} 万円** {sp_fur_text}\n\n<span style='font-size:0.88rem;color:#495057;'>※年収・社会保険料・iDeCo掛金・扶養家族をすべて反映した目安です。実質2,000円の負担でお米や食材・日用品を受け取ることで、毎年の基本生活費（食費等）を確実に圧縮できます。</span>", unsafe_allow_html=True)
            with col_fur_btn:
                st.link_button(f"🎁 上限{furusato_limit_total/10000:,.1f}万円以内で返礼品を探す (PR)", AFFILIATE_LINKS["furusato"], use_container_width=True)
            st.divider()

        diag_cols = st.columns(3)
        
        # 診断1：住宅ローンの金利引き下げポテンシャル（設定中のローンがある場合、金利-0.3%での削減額を実計算）
        with diag_cols[0]:
            if housing_type == "持ち家" and has_existing_mortgage and ex_housing_loan_balance > 0 and ex_housing_loan_rate > 0.004:
                reduced_rate = max(0.003, ex_housing_loan_rate - 0.003)
                pmt_curr, _ = generate_mortgage_schedule(ex_housing_loan_balance, ex_housing_loan_rate, ex_housing_loan_years_remaining)
                pmt_low, _ = generate_mortgage_schedule(ex_housing_loan_balance, reduced_rate, ex_housing_loan_years_remaining)
                save_loan_man = max(10, int((np.sum(pmt_curr) - np.sum(pmt_low)) / 10000))
                st.markdown(f"🏠 **住宅ローン見直し効果**\n\n現在の残高（{format_man_oku_val(ex_housing_loan_balance/10000)}）の金利がもし **0.3%下がれば**、完済までの総支払額が **約{format_man_oku_val(save_loan_man)} 削減**できます。")
                st.link_button("👉 モゲチェックで借換メリットを無料診断 (PR)", AFFILIATE_LINKS["mortgage"], use_container_width=True)
            elif has_housing and housing_loan_amount > 0:
                reduced_rate = max(0.003, housing_loan_rate - 0.003)
                pmt_curr, _ = generate_mortgage_schedule(housing_loan_amount, housing_loan_rate, housing_loan_years)
                pmt_low, _ = generate_mortgage_schedule(housing_loan_amount, reduced_rate, housing_loan_years)
                save_loan_man = max(10, int((np.sum(pmt_curr) - np.sum(pmt_low)) / 10000))
                st.markdown(f"🏠 **新規住宅ローンの金利比較効果**\n\n借入予定（{format_man_oku_val(housing_loan_amount/10000)}）の金利を **0.3%低く** 選ぶだけで、総返済額が **約{format_man_oku_val(save_loan_man)} お得**になります。")
                st.link_button("👉 住宅ローンの最安金利を比較・診断する (PR)", AFFILIATE_LINKS["mortgage"], use_container_width=True)
            else:
                # ローンがない場合はクレカ積立＋証券口座のポテンシャルを表示
                annual_inv_man = (invest_monthly + (sp_invest_monthly if has_marriage else 0)) * 12 / 10000
                invest_yrs = max(5, invest_end_age - current_age) if has_investment else 20
                pt_gain_man = max(5, int(min(120, max(36, annual_inv_man)) * 0.01 * invest_yrs))
                st.markdown(f"💳 **クレカ積立＆非課税枠の活用**\n\n毎月の積立をネット証券×高還元クレカで行うだけで、運用益とは別に **累計 約{pt_gain_man}万円相当のポイント** が自動で貯まります。")
                st.link_button("👉 NISA・クレカ積立に強いネット証券を見る (PR)", AFFILIATE_LINKS["securities"], use_container_width=True)

        # 診断2：保険料・固定費の見直し→投資スイープ効果（85歳時点の複利効果を実計算）
        with diag_cols[1]:
            yrs_to_85 = max(10, 85 - current_age)
            monthly_cut_target = 1.0 if insurance_premium_monthly >= 10000 else 1.5
            r_net = max(0.03, expected_return * 0.8)
            fv_cut_man = int((monthly_cut_target * 12) * (((1 + r_net)**yrs_to_85 - 1) / r_net))
            if insurance_premium_monthly >= 10000:
                st.markdown(f"🛡️ **民間保険の見直し＋運用効果**\n\n毎月の保険料（{int(insurance_premium_monthly/10000)}万円）を見直して **月1万円削減** しNISAで運用すると、85歳時点の純資産が **＋{format_man_oku_val(fv_cut_man)} 増加**します。")
            else:
                st.markdown(f"🔍 **ライフプランの『答え合わせ』**\n\n固定費や保険・税制の最適化で **月1.5万円** の余剰を作り運用に回せれば、85歳時点の純資産は **＋{format_man_oku_val(fv_cut_man)} 上乗せ**されます。")
            st.link_button("👨‍💼 【無料】FPに家計とプランの最適化を相談 (PR)", AFFILIATE_LINKS["fp_consult"], use_container_width=True)

        # 診断3：待機資金（ドライパウダー）の金利差 or 自宅査定ポテンシャル
        with diag_cols[2]:
            if has_dry_powder and (initial_dry_powder > 0 or dp_max_cap > 0):
                base_dp_man = max(initial_dry_powder, dp_max_cap) / 10000
                dp_gain_man = max(10, int(base_dp_man * ((1.01 ** min(30, yrs_to_85)) - 1)))
                st.markdown(f"💧 **待機資金（{format_man_oku_val(base_dp_man)}）の平時利回り効果**\n\n待機資金を普通預金ではなく個人向け国債や高金利口座（年1%想定）に置くだけで、平時でも **約＋{format_man_oku_val(dp_gain_man)}** の収益差が生まれます。")
                st.link_button("🚀 待機資金の運用に最適な証券・銀行口座 (PR)", AFFILIATE_LINKS["securities"], use_container_width=True)
            elif housing_type == "持ち家" or has_housing:
                st.markdown("🏢 **自宅の資産価値（純資産）の可視化**\n\n持ち家は最大の資産です。現在の正確な売却相場を把握しておくことで、老後の住み替えや老人ホーム入居資金の計画が盤石になります。")
                st.link_button("🏠 無料で自宅の現在の査定額を調べてみる (PR)", AFFILIATE_LINKS["real_estate"], use_container_width=True)
            else:
                st.markdown("📱 **生活費の精緻化でシミュレーション精度UP**\n\n家計簿アプリで現在の正確な支出を把握し、月5,000円のムダを削るだけで生涯の資産寿命は大きく伸びます。")
                st.link_button("📱 人気の無料家計簿アプリを試してみる (PR)", AFFILIATE_LINKS["kakeibo_app"], use_container_width=True)

    if sim_mode == "モンテカルロシミュレーション（リスク・暴落を考慮）":
        st.markdown("### 🎲 モンテカルロ・シミュレーション推移（300回試行・ストレステスト）")
        st.caption("※下位10%の悲観シナリオは、暴落相場や長期低迷に直面した場合のストレステストとして機能します。")
        
        if has_dry_powder or has_guardrail:
            check_idx = ages.index(85) if 85 in ages else -1
            diff_85_p10 = (percentile_10[check_idx] - percentile_10_no_def[check_idx]) / 10000 if percentile_10_no_def is not None else 0.0
            sign_str = "+" if diff_85_p10 > 0 else ""
            
            if depletion_age_p10_no_def is not None and depletion_age_p10 is None:
                ext_text = f"枯渇回避！（対策なし: {depletion_age_p10_no_def}歳枯渇 → 枯渇なし）"
            elif depletion_age_p10_no_def is not None and depletion_age_p10 is not None:
                diff_age = depletion_age_p10 - depletion_age_p10_no_def
                ext_text = f"資産寿命 {'+' if diff_age >= 0 else ''}{diff_age}年延命！（{depletion_age_p10_no_def}歳 → {depletion_age_p10}歳）"
            else:
                ext_text = "悲観シナリオでも枯渇なしを維持"
                
            col_def1, col_def2, col_def3 = st.columns(3)
            with col_def1:
                st.info(f"🛡️ **暴落対策による純資産改善効果 (悲観・85歳時点)**\n\n### **{sign_str}{format_man_oku_val(diff_85_p10)}**")
            with col_def2:
                st.success(f"⏳ **暴落対策による資産寿命の延命効果 (悲観シナリオ)**\n\n**{ext_text}**")
            with col_def3:
                if has_dry_powder:
                    st.warning(f"🎯 **待機資金スポット投資の発動実績 (300回平均)**\n\n生涯平均 **{mc_avg_spot_count:.1f} 回** 発動（累計投入: **{format_man_oku_val(mc_avg_spot_total/10000)}**）")
                else:
                    st.warning("🛡️ **ガードレール（自動支出カット）稼働中**\n\n暴落年に生活費とイベント費を自動削減しています。")

        if has_dry_powder or has_guardrail:
            mc_view_opts = [
                "🌐 通常全体表示（楽観〜悲観）",
                "📐 対数圧縮スケール（下位の線も広げて見やすくする）",
                "📊 暴落対策効果（対策あり − 対策なしの差額クローズアップ）"
            ]
            mc_view_map = {mc_view_opts[0]: "all", mc_view_opts[1]: "symlog", mc_view_opts[2]: "diff"}
        else:
            mc_view_opts = [
                "🌐 通常全体表示（楽観〜悲観）",
                "📐 対数圧縮スケール（下位の線も広げて見やすくする）"
            ]
            mc_view_map = {mc_view_opts[0]: "all", mc_view_opts[1]: "symlog"}
            
        mc_view_sel = st.radio("グラフの表示スケール切り替え：", mc_view_opts, index=0, horizontal=True)
        mc_view_key = mc_view_map.get(mc_view_sel, "all")

        fig_mc = plot_monte_carlo(ages, percentile_90, percentile_50, percentile_10, percentile_10_no_def, view_mode=mc_view_key)
        st.plotly_chart(fig_mc, use_container_width=True, config={'displayModeBar': False})
        st.markdown("---")

    elif sim_mode == "ヒストリカル・バックテスト（S&P500 / オルカンの過去実績を適用）":
        st.markdown(f"### 📜 過去実績バックテスト推移（{hist_start_year}年相場サイクル開始）")
        st.caption("※カーソルを合わせると、その年齢に適用された実際の歴史上の年号（例：2008年リーマンショック等）と純資産額が確認できます。")
        
        if has_dry_powder or has_guardrail:
            check_idx = ages.index(85) if 85 in ages else -1
            diff_85_hist = (hist_net_main[check_idx] - hist_net_no_def[check_idx]) / 10000 if hist_net_no_def is not None else 0.0
            sign_str = "+" if diff_85_hist > 0 else ""
            
            if depletion_age_hist_no_def is not None and depletion_age is None:
                ext_text = f"枯渇回避！（対策なし: {depletion_age_hist_no_def}歳枯渇 → 枯渇なし）"
            elif depletion_age_hist_no_def is not None and depletion_age is not None:
                diff_age = depletion_age - depletion_age_hist_no_def
                ext_text = f"資産寿命 {'+' if diff_age >= 0 else ''}{diff_age}年延命！（{depletion_age_hist_no_def}歳 → {depletion_age}歳）"
            else:
                ext_text = "この歴史的相場でも枯渇なしを維持"
                
            col_def1, col_def2, col_def3 = st.columns(3)
            with col_def1:
                st.info(f"🛡️ **暴落対策による純資産改善効果 (85歳時点)**\n\n### **{sign_str}{format_man_oku_val(diff_85_hist)}**")
            with col_def2:
                st.success(f"⏳ **暴落対策による資産寿命の延命効果**\n\n**{ext_text}**")
            with col_def3:
                if has_dry_powder:
                    st.warning(f"🎯 **待機資金スポット投資の発動実績**\n\n計 **{int(mc_avg_spot_count)} 回** 発動（累計投入: **{format_man_oku_val(mc_avg_spot_total/10000)}**）")
                else:
                    st.warning("🛡️ **ガードレール（自動支出カット）稼働中**\n\n歴史的暴落年に生活費とイベント費を自動削減しています。")

        if has_dry_powder or has_guardrail:
            hb_view_opts = [
                "🌐 通常全体表示（S&P500 vs オルカン ＆ 対策有無）",
                "📐 対数圧縮スケール（下位の線も広げて見やすくする）",
                "📊 暴落対策効果（対策あり − 対策なしの差額クローズアップ）"
            ]
            hb_view_map = {hb_view_opts[0]: "all", hb_view_opts[1]: "symlog", hb_view_opts[2]: "diff"}
        else:
            hb_view_opts = [
                "🌐 通常全体表示（S&P500 vs オルカン）",
                "📐 対数圧縮スケール（下位の線も広げて見やすくする）"
            ]
            hb_view_map = {hb_view_opts[0]: "all", hb_view_opts[1]: "symlog"}

        hb_view_sel = st.radio("バックテストグラフの表示スケール切り替え：", hb_view_opts, index=0, horizontal=True)
        hb_view_key = hb_view_map.get(hb_view_sel, "all")

        fig_hb = plot_historical_backtest(ages, hist_net_main, hist_net_no_def, hist_net_sub, short_main, short_sub, hist_start_year, view_mode=hb_view_key)
        st.plotly_chart(fig_hb, use_container_width=True, config={'displayModeBar': False})
        st.markdown("---")

    # ★下の棒グラフとキャッシュフロー表で表示するシナリオの切り替えUI
    if sim_mode == "モンテカルロシミュレーション（リスク・暴落を考慮）":
        st.markdown("### 📊 詳細キャッシュフロー分析（シナリオ別・内訳検証）")
        detail_scenario_opts = [
            "📉 悲観シナリオ（下位10%代表 / 暴落・低迷時のリアルな内訳と待機資金の動きを確認）",
            "🎲 モンテカルロ中央値シナリオ（50%代表 / 相場の波がある標準的な内訳）",
            "📈 楽観シナリオ（上位10%代表 / 好調相場の内訳）",
            "📏 定率（無風）シナリオ（毎年固定リターンで推移した場合の内訳）"
        ]
        selected_detail_scenario = st.radio(
            "下の棒グラフ・キャッシュフロー表に表示するシナリオを選択してください：",
            detail_scenario_opts,
            index=0,
            help="「悲観シナリオ」を選ぶと、実際に暴落が起きた年に待機資金（水色のバー）からスポット投資（★マーク）が発動し、その後の相場回復で資産がどう推移したかを棒グラフと表で詳しく確認できます。"
        )
        if selected_detail_scenario == detail_scenario_opts[0]:
            res = res_p10_rep
        elif selected_detail_scenario == detail_scenario_opts[1]:
            res = res_p50_rep
        elif selected_detail_scenario == detail_scenario_opts[2]:
            res = res_p90_rep
        else:
            res = res_base
            
        spot_count_this = int(np.sum(res["arr_spot_invest"] > 0))
        spot_total_this = float(np.sum(res["arr_spot_invest"])) / 10000
        if has_dry_powder and spot_count_this > 0:
            spot_ages_list = [f"{ages[idx]}歳({format_man_oku_val(res['arr_spot_invest'][idx]/10000)})" for idx in range(years_count) if res["arr_spot_invest"][idx] > 0]
            st.caption(f"🎯 **選択中のシナリオでのスポット投資発動履歴（計{spot_count_this}回 / 合計{format_man_oku_val(spot_total_this)}投入）：** " + "、 ".join(spot_ages_list))
    elif sim_mode == "ヒストリカル・バックテスト（S&P500 / オルカンの過去実績を適用）":
        st.markdown("### 📊 詳細キャッシュフロー分析（過去実績バックテスト内訳）")
        hb_detail_opts = [
            f"📌 メイン検証：{hist_index_choice}（暴落対策あり）",
            f"🔄 比較対象：{sub_index_choice}（暴落対策あり）"
        ] + ([f"🛡️ 比較対象：{hist_index_choice}（もし暴落対策がなかった場合）"] if res_no_def is not None else [])
        selected_hb_detail = st.radio("下の棒グラフ・キャッシュフロー表に表示するデータを選択してください：", hb_detail_opts, index=0, horizontal=True)
        if selected_hb_detail == hb_detail_opts[0]:
            res = res_base
        elif selected_hb_detail == hb_detail_opts[1]:
            res = res_sub
        else:
            res = res_no_def

        spot_count_this = int(np.sum(res["arr_spot_invest"] > 0))
        spot_total_this = float(np.sum(res["arr_spot_invest"])) / 10000
        if has_dry_powder and spot_count_this > 0:
            s_idx = HIST_YEARS.index(hist_start_year) if hist_start_year in HIST_YEARS else 0
            spot_ages_list = [f"{ages[idx]}歳[{HIST_YEARS[(s_idx+idx)%len(HIST_YEARS)]}年相場]({format_man_oku_val(res['arr_spot_invest'][idx]/10000)})" for idx in range(years_count) if res["arr_spot_invest"][idx] > 0]
            st.caption(f"🎯 **バックテストでのスポット投資発動履歴（計{spot_count_this}回 / 合計{format_man_oku_val(spot_total_this)}投入）：** " + "、 ".join(spot_ages_list))
    else:
        st.markdown("### 📈 資産推移と年間収支 (単位：万円)")
        res = res_base
        
    fig1 = plot_asset_transition(ages, res["balances_savings"], res["balances_dry_powder"], res["balances_nisa"], res["balances_taxable"], res["balances_ideco_dc"], res["arr_debt_housing"], res["arr_debt_car"], res["arr_debt_reform"], res["arr_debt_edu"], res["arr_annual_balance"], res["arr_spot_invest"])
    st.plotly_chart(fig1, use_container_width=True, config={'displayModeBar': False})
    st.caption("※折れ線グラフ（経常収支）は、あえて「取り崩し分を含まない純粋な生活費の赤字」を表示しています。これを取り崩し込みにしてしまうと、資産が枯渇するまでグラフが「0（トントン）」に張り付いてしまい、本当の家計の赤字幅が見えなくなってしまうためです。")

    st.markdown("### 💰 年間収支の内訳比較（額面ベース / 単位：万円）")
    st.caption("※赤字になった年は「資産取崩・赤字補填」のピンクの棒グラフで生活費が補填されている様子が確認できます。")
    fig2 = plot_cashflow_breakdown(ages, years_count, res["arr_salary"], res["arr_sp_salary"], res["arr_pension"], res["arr_child_allowance"], res["arr_leave_benefit"], res["arr_ret_income"], res["arr_sp_pension"], res["arr_withdrawal_amount"], res["arr_exp_base"], res["arr_exp_support"], res["arr_exp_ideco_savings_ins"], res["arr_exp_insurance"], res["arr_exp_event"], res["arr_exp_house"], res["arr_exp_edu"], res["arr_exp_car"], res["arr_exp_nursing"], res["arr_soc_ins"], res["arr_sp_soc_ins"], res["arr_inc_tax"], res["arr_sp_inc_tax"], res["arr_res_tax"], res["arr_sp_res_tax"], res["arr_ret_inc_tax"], res["arr_ret_res_tax"], res["arr_lump_sum_income"])
    st.plotly_chart(fig2, use_container_width=True, config={'displayModeBar': False})

    st.markdown("### 📋 世帯キャッシュフロー表 (単位: 万円)")
    show_all_cf_cols = st.checkbox("0円の項目（未設定のローンや手当など）もすべて表に表示する", value=False)

    df = pd.DataFrame({
        '本人年齢': ages,
        '相場リターン(%)': res["arr_return_rate"] * 100,
        '世帯手取り収入(経常)': res["arr_net_income"] / 10000,
        '一時収入(退職金・家等)': res["arr_lump_sum_income"] / 10000,
        '育休給付金': res["arr_leave_benefit"] / 10000,
        '児童手当': res["arr_child_allowance"] / 10000,
        '資産取崩(補填含む)': res["arr_withdrawal_amount"] / 10000,
        '積立投資額': res["arr_invest_amount"] / 10000,
        '暴落スポット投資': res["arr_spot_invest"] / 10000,
        '基本生活費': res["arr_exp_base"] / 10000,
        '子ども仕送り': res["arr_exp_support"] / 10000,
        'iDeCo・貯蓄保険掛金': res["arr_exp_ideco_savings_ins"] / 10000,
        '民間保険料': res["arr_exp_insurance"] / 10000,
        '特別支出(イベント)': res["arr_exp_event"] / 10000,
        '住宅費': res["arr_exp_house"] / 10000,
        '教育費': res["arr_exp_edu"] / 10000,
        '自動車費': res["arr_exp_car"] / 10000,
        '老人ホーム費用': res["arr_exp_nursing"] / 10000,
        '住宅ローン控除': res["arr_mortgage_deduction"] / 10000,
        '社会保険料(世帯)': (res["arr_soc_ins"] + res["arr_sp_soc_ins"]) / 10000,
        '所得税(世帯)': (res["arr_inc_tax"] + res["arr_sp_inc_tax"]) / 10000,
        '住民税(世帯)': (res["arr_res_tax"] + res["arr_sp_res_tax"]) / 10000,
        '退職関連税(世帯)': (res["arr_ret_inc_tax"] + res["arr_ret_res_tax"]) / 10000,
        '世帯年間収支(取崩前)': res["arr_annual_balance"] / 10000,
        '住宅ローン残高': res["arr_debt_housing"] / 10000,
        '自動車ローン残高': res["arr_debt_car"] / 10000,
        'リフォームローン残高': res["arr_debt_reform"] / 10000,
        '教育ローン残高': res["arr_debt_edu"] / 10000,
        '負債合計': res["arr_debt_balance"] / 10000,
        '預貯金': res["balances_savings"] / 10000,
        '暴落待機資金': res["balances_dry_powder"] / 10000,
        '特定口座': res["balances_taxable"] / 10000,
        'NISA': res["balances_nisa"] / 10000,
        '世帯iDeCo/DC': res["balances_ideco_dc"] / 10000,
        '世帯総資産': res["total_assets"] / 10000,
        '純資産額': (res["total_assets"] - res["arr_debt_balance"]) / 10000
    }).set_index('本人年齢')

    # 主要な基本列は常に残し、その他の列は全期間0円なら非表示にして横スクロールを減らす
    always_keep_cols = {'相場リターン(%)', '世帯手取り収入(経常)', '積立投資額', '基本生活費', '世帯年間収支(取崩前)', '預貯金', '特定口座', 'NISA', '世帯総資産', '純資産額'}
    if not show_all_cf_cols:
        cols_to_keep = [c for c in df.columns if (c in always_keep_cols) or (df[c].abs().max() >= 0.5)]
        df_display = df[cols_to_keep]
    else:
        df_display = df

    red_subset = [c for c in ['相場リターン(%)', '世帯年間収支(取崩前)', '預貯金', '特定口座', 'NISA', '世帯総資産', '純資産額'] if c in df_display.columns]
    # 相場リターン(%)だけ小数第1位、他の金額列は整数（カンマ区切り）でスッキリ表示
    fmt_dict = {c: ("{:.1f}" if c == '相場リターン(%)' else "{:,.0f}") for c in df_display.columns}
    style_func = lambda x: 'color: red' if isinstance(x, (int, float)) and x < 0 else ''
    try:
        st.dataframe(df_display.style.format(fmt_dict).map(style_func, subset=red_subset), height=400, use_container_width=True)
    except AttributeError:
        st.dataframe(df_display.style.format(fmt_dict).applymap(style_func, subset=red_subset), height=400, use_container_width=True)

    if res.get("arr_ret_tax_details"):
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("📄 退職金・iDeCo 課税計算の詳細レポートを見る", expanded=True):
            st.caption("※適用されている退職所得控除の年数ルール（19年ルール・5年ルール）や、税額の計算プロセスを確認できます。")
            df_ret_tax = pd.DataFrame(res["arr_ret_tax_details"])
            st.dataframe(df_ret_tax, use_container_width=True, hide_index=True)

    # --- アフィリエイト・ネクストアクション エリア（全ジャンル網羅・4カード構成） ---
    st.markdown("---")
    st.markdown("### 🚀 シミュレーション結果を現実にする4つのネクストアクション")
    st.caption("※設計したライフプランを実行に移すための、おすすめの無料ツール・相談窓口です。")

    col_act1, col_act2 = st.columns(2)
    with col_act1:
        with st.container(border=True):
            if depletion_age is not None or (sim_mode != "定率シミュレーション（基本）" and depletion_age_p10 is not None):
                st.error("🥇 **Step 1：プロのFPと「資金不足の解消・保険見直し」を行う**")
                st.write("悲観シナリオ等で資金不足が予測されています。自己判断で無理なリスクを取る前に、まずはプロと一緒に「保険料などの固定費削減」や「無理のない収支改善」を行うのが最も確実です。")
            else:
                st.success("🥇 **Step 1：作ったプランに死角がないかプロのFPと「答え合わせ」する**")
                st.write("シミュレーション上は非常に優秀な結果です！このプラン（URL）をそのままFPに見せて、相続や税制改正、教育費・住宅費の見落としがないか無料のセカンドオピニオンを受けてみましょう。")
            st.link_button("👨‍💼 【無料】プロにライフプラン・保険見直しを相談する (PR)", AFFILIATE_LINKS["fp_consult"], use_container_width=True)

        with st.container(border=True):
            st.info("🥉 **Step 3：NISA枠の最大化 ＆ 暴落待機資金の専用口座を準備する**")
            st.write("新NISAでの自動積立や、暴落時に機動的に買い向かうための待機資金（MMF・個人向け国債・高金利連携預金）は、手数料が安くポイント還元率の高いネット証券＋クレカの組み合わせが必須です。")
            c_sec1, c_sec2 = st.columns(2)
            with c_sec1:
                st.link_button("🚀 ネット証券を比較・開設 (PR)", AFFILIATE_LINKS["securities"], use_container_width=True)
            with c_sec2:
                st.link_button("💳 積立でお得なクレカ (PR)", AFFILIATE_LINKS["credit_card"], use_container_width=True)

    with col_act2:
        with st.container(border=True):
            st.warning("🥈 **Step 2：人生最大の固定費「住居費・住宅ローン」を最適化する**")
            st.write("住宅ローンの金利引き下げ（借り換え・新規比較）や、持ち家の現在の売却相場を把握することは、一度の手続きで数百万円単位の純資産改善につながる最もコスパの高いアクションです。")
            c_est1, c_est2 = st.columns(2)
            with c_est1:
                st.link_button("🏠 モゲチェックで金利診断 (PR)", AFFILIATE_LINKS["mortgage"], use_container_width=True)
            with c_est2:
                st.link_button("🏢 自宅の無料一括査定 (PR)", AFFILIATE_LINKS["real_estate"], use_container_width=True)

        with st.container(border=True):
            st.markdown("📱 **Step 4：ふるさと納税・家計自動化・収入アップで入金力を高める**")
            st.write("ふるさと納税による食費・日用品費の削減、家計簿アプリでの支出の自動可視化、そして本業・副業での入金力アップ（昇給・転職）が資産形成を加速させます。")
            c_sub1, c_sub2, c_sub3 = st.columns(3)
            with c_sub1:
                st.link_button("🎁 ふるさと納税 (PR)", AFFILIATE_LINKS["furusato"], use_container_width=True)
            with c_sub2:
                st.link_button("📱 無料家計簿アプリ (PR)", AFFILIATE_LINKS["kakeibo_app"], use_container_width=True)
            with c_sub3:
                st.link_button("💼 年収アップ診断 (PR)", AFFILIATE_LINKS["career_up"], use_container_width=True)

    # --- ★ASP審査通過・コンプライアンス遵守のための免責事項・PR表記 ---
    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("⚖️ 免責事項・広告掲載（PR）およびプライバシーポリシーについて"):
        st.markdown("""
        * **免責事項（シミュレーション結果について）：**  
          当シミュレータ（最強ライフプランシミュレータ）は、利用者ご自身が入力された条件および一定の統計的・税制的仮定に基づく概算試算ツールであり、将来の運用成果や資産額、税額等を保証するものではありません。また、特定の金融商品の勧誘や投資助言を行うものではありません。最終的な投資判断や住宅購入・保険契約等の決定は、ご自身の判断と責任において行われますようお願いいたします。
        * **広告掲載（アフィリエイトプログラム）について：**  
          当ツール内のリンクの一部には、アフィリエイトプログラム（PR・広告）が含まれています。リンク先のサービス・商品に関するお問い合わせは、各提供元企業様へ直接お願いいたします。
        * **データの取り扱いとプライバシーについて：**  
          当ツールに入力された年収・資産等の個人データは、ブラウザ上の計算および「設定をURLに保存」機能（URL文字列への圧縮変換）にのみ使用され、当サイトのサーバーや外部データベースへ勝手に送信・保存されることはありませんので安心してご利用ください。
        """)

except Exception as e:
    st.error(f"シミュレーション中にエラーが発生しました: {e}")
    st.code(traceback.format_exc())