import streamlit as st
import FinanceDataReader as fdr
import datetime
import pandas as pd
import plotly.graph_objects as go

st.markdown("<h2 style='font-size: 24px; text-align: center; margin-bottom: 20px;'>💰 적립식 투자 시뮬레이션 (부드러운 Plotly 애니메이션) 📈</h2>", unsafe_allow_html=True)

# =============================
# 1. 입력 설정
# =============================
col_start_date, col_end_date = st.columns(2)
with col_start_date:
    start_date = st.date_input("조회 시작일", datetime.datetime(2022, 1, 1), max_value=datetime.datetime.now())
with col_end_date:
    end_date = st.date_input("조회 종료일", datetime.datetime.now(), max_value=datetime.datetime.now())

if start_date > end_date:
    start_date, end_date = end_date, start_date

col_code1, col_code2, col_code3, col_amount = st.columns([1, 1, 1, 1.5])
with col_code1: code1 = st.text_input('종목코드 1', value='QQQ')
with col_code2: code2 = st.text_input('종목코드 2', value='005930')
with col_code3: code3 = st.text_input('종목코드 3', value='AAPL')
with col_amount:
    monthly_amount_krw = st.number_input('매월 적립 금액 (원)', min_value=1000, value=500000, step=10000)

codes = [c.strip() for c in [code1, code2, code3] if c.strip()]

# =============================
# 2. 시뮬레이션 함수
# =============================
@st.cache_data
def simulate_monthly_investment(code, start_date, end_date, monthly_amount):
    df = fdr.DataReader(code, start_date, end_date)
    close = df['Close']
    cumulative = pd.Series(0.0, index=close.index)
    shares = 0
    last_month = -1
    for date, price in close.items():
        if date.month != last_month:
            shares += monthly_amount / price
            last_month = date.month
        cumulative[date] = shares * price
    cumulative.name = code
    return cumulative

if codes:
    dfs = []
    for c in codes:
        series = simulate_monthly_investment(c, start_date, end_date, monthly_amount_krw)
        if series is not None and not series.empty:
            dfs.append(series)
    if not dfs:
        st.warning("유효한 데이터가 없습니다.")
        st.stop()
    data = pd.concat(dfs, axis=1)

    # =============================
    # 3. 총 적립 원금 계산
    # =============================
    cumulative_principal = pd.Series(0.0, index=data.index)
    total = 0
    last_month = -1
    for date in data.index:
        if date.month != last_month:
            total += monthly_amount_krw
            last_month = date.month
        cumulative_principal[date] = total
    data['총 적립 원금'] = cumulative_principal

    # =============================
    # 4. Plotly frames 기반 애니메이션
    # =============================
    fig = go.Figure(
        data=[go.Scatter(x=[data.index[0]], y=[data[c].iloc[0]], mode='lines', name=c) for c in data.columns],
        layout=go.Layout(
            title="누적 자산 가치 변화",
            xaxis=dict(title="날짜"),
            yaxis=dict(title="가치 (원)", range=[0, data.max().max()*1.1]),
            updatemenus=[dict(type="buttons",
                              buttons=[dict(label="재생", method="animate", args=[None, {"frame": {"duration": 50, "redraw": True}, "fromcurrent": True}]),
                                       dict(label="정지", method="animate", args=[[None], {"frame": {"duration": 0, "redraw": False}, "mode": "immediate"}])])]
        ),
        frames=[go.Frame(
            data=[go.Scatter(x=data.index[:k+1], y=data[col][:k+1], mode='lines', name=col) for col in data.columns],
            name=str(k)
        ) for k in range(len(data))]
    )
    st.plotly_chart(fig, use_container_width=True)
