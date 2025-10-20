import streamlit as st
import FinanceDataReader as fdr
import datetime
import pandas as pd
import plotly.graph_objects as go # Plotly graph_objects 사용
import time 

# ==============================================================================
# 0. Session State 및 UI Helper Functions
# (생략: 변경 없음)
# ==============================================================================

# 차트 표시 모드 초기화 ('animation' 또는 'static')
if 'display_mode' not in st.session_state:
    st.session_state.display_mode = 'animation'

# 한국 주식 코드 판별 헬퍼 (6자리 숫자로 판단)
def is_korean_stock(code):
    return code.isdigit() and len(code) == 6

# 환율 데이터 (USD/KRW)를 가져오는 헬퍼 함수
@st.cache_data
def get_usd_krw_rate(start_date, end_date):
    """원/달러 환율(USD/KRW) 종가를 가져옵니다."""
    try:
        # FDR에서 'USD/KRW' 코드를 사용하여 환율을 가져옴 (1 USD당 KRW)
        rate_df = fdr.DataReader('USD/KRW', start_date, end_date)
        return rate_df['Close'].rename('USD/KRW')
    except Exception:
        st.warning("⚠️ 원/달러 환율 데이터를 불러오는데 실패했습니다. 미국 주식 계산에 환율이 적용되지 않습니다. (1 USD = 1,300 KRW 가정)")
        return pd.Series(1300.0, index=pd.to_datetime([])) # 기본값 1,300 KRW/USD 가정

# 시뮬레이션 요약 테이블을 계산하고 표시하는 헬퍼 함수
def display_final_summary_table(data, principal_series):
    """최종 시점의 데이터를 바탕으로 투자 요약 테이블을 계산하고 표시합니다."""
    
    valid_data_length = len(principal_series.dropna())
    if valid_data_length == 0:
        return
        
    max_index = valid_data_length - 1
    total_invested_principal = principal_series.iloc[max_index]

    investment_summary = []

    # 1. 총 적립 원금 행을 첫 번째로 추가
    principal_value = total_invested_principal
    if principal_value > 0:
        investment_summary.append({
            '종목': '총 적립 원금',
            '총 투자 원금 (원)': f"{principal_value:,.0f}",
            '현재 자산 가치 (원)': f"{principal_value:,.0f}",
            '수익 / 손실 (원)': f"{0:,.0f}", 
            '수익률 (%)': f"{0.00:,.2f}%"
        })

    # 2. 각 종목별 최종 결과 추가
    for code in data.columns:
        if code == '총 적립 원금':
            continue

        # 마지막 유효 값 (최종 자산 가치)
        final_value = data[code].dropna().iloc[-1]
        
        profit_loss = final_value - total_invested_principal
        return_rate = (profit_loss / total_invested_principal) * 100 if total_invested_principal > 0 else 0

        investment_summary.append({
            '종목': code,
            '총 투자 원금 (원)': f"{total_invested_principal:,.0f}",
            '현재 자산 가치 (원)': f"{final_value:,.0f}",
            '수익 / 손실 (원)': f"{profit_loss:,.0f}", 
            '수익률 (%)': f"{return_rate:,.2f}%"
        })

    if investment_summary:
        st.markdown("---") 
        summary_df = pd.DataFrame(investment_summary)
        st.markdown("#### 최종 시뮬레이션 요약")
        st.dataframe(
            summary_df, 
            hide_index=True,
            use_container_width=True,
        )

# ==============================================================================
# 2. 적립식 시뮬레이션 로직 (변경 없음)
# ==============================================================================
@st.cache_data(show_spinner="⏳ 데이터 로딩 및 시뮬레이션 계산 중...")
def simulate_monthly_investment(code, start_date, end_date, monthly_amount, rate_series):
    """
    월별 정액 적립식 투자의 누적 가치를 시뮬레이션합니다.
    rate_series (USD/KRW)를 사용하여 미국 주식의 환율 변동을 반영합니다.
    """
    try:
        df = fdr.DataReader(code, start_date, end_date)
        close = df['Close']
        cumulative = pd.Series(0.0, index=close.index)
        shares = 0
        last_month = -1
        is_kr_stock = is_korean_stock(code)
        
        # 환율 데이터가 없는 경우를 대비해 1300원으로 채워넣음 (최종 fallback)
        default_rate = 1300.0
        
        # 주식 데이터 인덱스에 맞춰 환율 데이터를 정렬 및 결측치 채우기
        if rate_series is not None and not rate_series.empty:
            aligned_rate = rate_series.reindex(close.index, method='ffill').fillna(default_rate)
        else:
            aligned_rate = pd.Series(default_rate, index=close.index)


        for date, price in close.items():
            current_month = date.month
            
            # 1. 투자 금액 (현지 통화) 결정
            if is_kr_stock:
                # 한국 주식: KRW 투자 / KRW 가격
                investment_amount_local = monthly_amount
                exchange_rate = 1.0 # 환율 무시
            else:
                # 미국 주식: KRW 투자 -> USD로 환전
                exchange_rate = aligned_rate.loc[date]
                investment_amount_local = monthly_amount / exchange_rate # USD 금액

            # 2. 주식 매수 (월별 첫 거래일)
            if current_month != last_month:
                shares += investment_amount_local / price
                last_month = date.month
            
            # 3. 누적 자산 가치 (KRW 기준) 계산
            if is_kr_stock:
                # 한국 주식: 주식 수 * KRW 가격
                cumulative[date] = shares * price 
            else:
                # 미국 주식: 주식 수 * USD 가격 * 최종 평가일 KRW/USD 환율
                final_rate = aligned_rate.loc[date]
                cumulative[date] = shares * price * final_rate
                
        # --- CRITICAL FIX: Series 이름을 종목 코드로 명시적으로 설정 ---
        cumulative.name = code
        # -------------------------------------------------------------
        
        # 첫 투자 시점 이후 데이터만 반환
        return cumulative[cumulative.cumsum() != 0] 
        
    except Exception as e:
        # st.error(f"디버깅용 - simulate_monthly_investment 에러 for {code}: {e}")
        st.warning(f"⚠️ 종목 코드 **{code}**의 데이터를 불러오는 데 문제가 발생했습니다.")
        return None

# ==============================================================================
# 3. 메인 실행 블록
# ==============================================================================
st.markdown("<h2 style='font-size: 24px; text-align: center; margin-bottom: 20px;'>💰 적립식 투자 시뮬레이션 (부드러운 Plotly 애니메이션) 📈</h2>", unsafe_allow_html=True)

# 1.1. 날짜 입력
col_start_date, col_end_date = st.columns(2)
with col_start_date:
    start_date = st.date_input("📅 조회 시작일", datetime.datetime(2022, 1, 1), max_value=datetime.datetime.now())
with col_end_date:
    end_date = st.date_input("📅 조회 종료일", datetime.datetime.now(), max_value=datetime.datetime.now())

if start_date > end_date:
    st.warning("시작일이 종료일보다 늦습니다. 날짜를 자동으로 맞바꿔 반영합니다.")
    start_date, end_date = end_date, start_date

st.markdown("---")

# 1.2. 적립 금액 입력
monthly_amount_krw = st.number_input(
    '💵 매월 적립 금액 (원)',
    min_value=1000,
    value=500000, # 50만원 기본값
    step=10000
)

# 1.3. 종목 코드 입력
col_code1, col_code2, col_code3 = st.columns(3)
with col_code1: code1 = st.text_input('종목코드 1', value='QQQ', placeholder='(예시) QQQ')
with col_code2: code2 = st.text_input('종목코드 2', value='005930', placeholder='(예시) 005930')
with col_code3: code3 = st.text_input('종목코드 3', value='AAPL', placeholder='(예시) AAPL')

st.markdown("---")

codes = [c.strip() for c in [code1, code2, code3] if c.strip()]

if codes:
    
    # 환율 데이터 선취 및 캐싱
    usd_krw_rate_series = get_usd_krw_rate(start_date, end_date)

    dfs = []
    for c in codes:
        # 환율 데이터를 시뮬레이션 함수에 전달
        series = simulate_monthly_investment(c, start_date, end_date, monthly_amount_krw, usd_krw_rate_series)
        if series is not None:
            dfs.append(series)
            
    if not dfs:
        st.warning("유효한 데이터가 없습니다. 종목 코드나 날짜를 확인해 주세요.")
        st.stop()
        
    # 데이터 병합 후, NaN 값을 직전 유효 값으로 채우고 모든 열이 NaN인 행만 제거하여 안정성 확보
    data = pd.concat(dfs, axis=1).ffill().dropna(how='all')
    
    # ==============================================================================
    # 3.1. 총 적립 원금 계산 (변경 없음)
    # ==============================================================================
    cumulative_principal = pd.Series(0.0, index=data.index)
    total = 0
    last_month = -1
    for date in data.index:
        current_month = date.month
        if current_month != last_month:
            total += monthly_amount_krw
            last_month = current_month
        cumulative_principal[date] = total
    data['총 적립 원금'] = cumulative_principal

    # ==============================================================================
    # 3.2. 제목 및 버튼 (수정됨)
    # ==============================================================================
    # 🎯 [수정] col_title만 남기고 col_button 제거
    st.markdown("<h3 style='font-size: 18px; text-align: left;'>📊 적립식 투자 시뮬레이션 결과</h3>", unsafe_allow_html=True)
    
    # ==============================================================================
    # 3.3. Plotly go.Figure 기반 애니메이션 (변경 없음)
    # ==============================================================================
    
    # 1. 월별 첫 거래일 인덱스 추출 (프레임 최적화)
    data['YearMonth'] = data.index.to_series().dt.to_period('M')
    monthly_indices = data.groupby('YearMonth').apply(lambda x: x.index[0]).tolist()
    data = data.drop(columns=['YearMonth'])
    
    # === 마지막 유효 날짜를 프레임에 강제로 추가하여 애니메이션이 끝까지 재생되도록 보장 ===
    last_available_date = data.index[-1]
    if last_available_date not in monthly_indices:
        monthly_indices.append(last_available_date)
    # =============================================================================================
    
    # 2. 프레임 생성
    frames = []
    # 애니메이션 모드일 경우에만 프레임을 생성
    if st.session_state.display_mode == 'animation':
        for date in monthly_indices:
            if date not in data.index:
                continue

            k = data.index.get_loc(date) 
            
            frame_data = []
            for col in data.columns:
                line_style = dict(color='dimgray', width=2, dash='dot') if col == '총 적립 원금' else None
                
                frame_data.append(
                    go.Scatter(
                        x=data.index[:k+1], 
                        y=data[col][:k+1], 
                        mode='lines', 
                        name=col, # 종목 코드를 name으로 직접 전달
                        line=line_style if line_style else None
                    )
                )

            # 동적 Y축 범위 계산: 현재 시점까지의 최대 자산 가치 (+10% 여유)
            max_val_up_to_k = data.iloc[:k+1].drop(columns=['총 적립 원금'], errors='ignore').max().max() * 1.1
            if max_val_up_to_k == 0:
                max_val_up_to_k = monthly_amount_krw * 2 # 최소값 보장

            frames.append(go.Frame(data=frame_data, name=date.strftime('%Y-%m-%d'), 
                                   layout=go.Layout(
                                       title=f"누적 자산 가치 변화 (시점: {date.strftime('%Y년 %m월 %d일')})",
                                       # 동적 Y축 스케일링 적용
                                       yaxis=dict(range=[0, max_val_up_to_k]) 
                                   )))
            
    # 3. 초기/정적 데이터 트레이스 생성
    initial_data = []
    
    # 🎯 [수정] 버튼이 없으므로, 무조건 최종 데이터로 정적 차트를 그리거나, 첫 행으로 애니메이션을 시작합니다.
    data_to_render = data if st.session_state.display_mode == 'static' else data.iloc[[0]] 

    for col in data.columns:
        line_style = dict(color='dimgray', width=2, dash='dot') if col == '총 적립 원금' else None
        
        initial_data.append(
            go.Scatter(
                x=data_to_render.index, 
                y=data_to_render[col], 
                mode='lines', 
                name=col, # 종목 코드를 name으로 직접 전달
                line=line_style if line_style else None
            )
        )

    # 4. Figure 생성 및 버튼 위치 조정 (변경 없음)
    initial_max_val = data.iloc[:3].drop(columns=['총 적립 원금'], errors='ignore').max().max() * 1.1 
    if initial_max_val == 0:
        initial_max_val = monthly_amount_krw * 2 # 최소값 보장

    fig = go.Figure(
        data=initial_data,
        layout=go.Layout(
            title="누적 자산 가치 변화",
            xaxis=dict(title="날짜"),
            # 초기 Y축 범위 설정 (작은 값에 맞춰 시작)
            yaxis=dict(title="가치 (원)", range=[0, initial_max_val], tickformat=',.0f'), 
            height=550,
        ),
        frames=frames
    )
    
    # 애니메이션 모드일 때만 Plotly 재생 버튼 추가 (변경 없음)
    if st.session_state.display_mode == 'animation':
        fig.update_layout(
            updatemenus=[dict(type="buttons",
                             x=1.21, 
                             y=0.7, 
                             showactive=False,
                             # ⭐⭐ 수정된 부분: xanchor와 yanchor 추가 ⭐⭐
                             xanchor='left', # x=1.21을 기준으로 버튼을 왼쪽에 고정
                             yanchor='middle', # y=0.7을 기준으로 버튼을 중앙에 고정
                             # ================================================
                             buttons=[
                                 dict(label="▶️ 재생 시작", 
                                      method="animate", 
                                      args=[None, {"frame": {"duration": 150, "redraw": True}, # 속도 150ms/월
                                                    "fromcurrent": True, 
                                                    "transition": {"duration": 20, "easing": "linear"}}]), 
                                 dict(label="⏸️ 정지", 
                                      method="animate", 
                                      args=[[None], {"frame": {"duration": 0, "redraw": False}, "mode": "immediate"}])
                             ])]
        )

    # 5. 차트 표시
    st.plotly_chart(fig, use_container_width=True)
    
    # 🎯 [수정] 안내 메시지 단순화
    if st.session_state.display_mode == 'animation':
        st.caption("차트 우측 상단의 '▶️ 재생 시작' 버튼으로 애니메이션을 시청하세요.")
    else:
        st.caption("현재는 '최종 결과 바로 표시' 모드입니다.")

    # ----------------------------------------------------------
    # 6. 최종 요약 테이블 표시
    # ----------------------------------------------------------
    # 🎯 [수정] 항상 최종 요약표를 표시
    display_final_summary_table(data, cumulative_principal)
