import streamlit as st
import FinanceDataReader as fdr
import datetime
import pandas as pd
import plotly.express as px # Plotly 라이브러리 추가

# ==============================================================================
# 1. UI 및 입력 설정
# ==============================================================================

st.markdown("<h2 style='font-size: 24px; text-align: center; margin-bottom: 20px;'>💰 적립식 투자 시뮬레이션 (Plotly 차트) 📈</h2>", unsafe_allow_html=True)

# 1.1. 날짜 입력 (조회 시작일과 종료일을 같은 행에 배치)
col_start_date, col_end_date = st.columns(2)

with col_start_date:
    start_date = st.date_input(
        "📅 조회 시작일",
        datetime.datetime(2022, 1, 1),
        max_value=datetime.datetime.now()
    )

with col_end_date:
    end_date = st.date_input(
        "📅 조회 종료일",
        datetime.datetime.now(),
        max_value=datetime.datetime.now()
    )

# 시작 날짜와 종료 날짜 비교 및 조정
if start_date > end_date:
    st.warning("시작일이 종료일보다 늦습니다. 날짜를 자동으로 맞바꿔 반영합니다.")
    start_date, end_date = end_date, start_date

st.markdown("---")

# 1.2. 종목 코드 및 적립 금액 입력
col_code1, col_code2, col_code3, col_amount = st.columns([1, 1, 1, 1.5])

with col_code1:
    code1 = st.text_input('종목코드 1', value='QQQ', placeholder='(예시) QQQ')

with col_code2:
    code2 = st.text_input('종목코드 2', value='005930', placeholder='(예시) 005930')

with col_code3:
    code3 = st.text_input('종목코드 3', value='AAPL', placeholder='(예시) AAPL')

with col_amount:
    # 월별 투자 금액 입력
    monthly_amount_krw = st.number_input(
        '💵 매월 적립 금액 (원)',
        min_value=1000,
        value=500000, # 50만원 기본값
        step=10000
    )

st.markdown("---")

# 입력된 종목 코드를 리스트로 생성
codes = [code1.strip(), code2.strip(), code3.strip()]
codes = [code for code in codes if code] # 빈 코드 제거

# 이전 버전에서 사용되던 애니메이션 상태 변수는 제거합니다.
# if 'current_index' not in st.session_state:
#     st.session_state.current_index = 0

# ==============================================================================
# 2. 적립식 시뮬레이션 로직 (Full Range 데이터 계산)
# ==============================================================================

# @st.cache_data를 사용하여 입력값(날짜, 코드, 금액)이 바뀌지 않으면 재계산하지 않도록 함
@st.cache_data(show_spinner="⏳ 주식 데이터를 불러오고 시뮬레이션을 계산 중...")
def run_monthly_installment_simulation(code, start_date, end_date, monthly_amount):
    """
    주어진 종목에 대해 월별 정액 적립식 투자의 누적 가치를 시뮬레이션합니다.
    """
    if not code:
        return None

    try:
        # 데이터 로딩
        df = fdr.DataReader(code, start_date, end_date)
        
        # 'Close' 가격만 사용
        close_prices = df['Close']
        if close_prices.empty:
            return None

        cumulative_value = pd.Series(0.0, index=close_prices.index)
        total_shares = 0.0
        last_invested_month = -1

        for date, price in close_prices.items():
            current_month = date.month
            
            # 매월 첫 거래일에 투자 (월이 바뀌었는지 확인)
            if current_month != last_invested_month:
                if price > 0:
                    shares_bought = monthly_amount / price
                    total_shares += shares_bought
                    last_invested_month = current_month
                
            current_value = total_shares * price
            cumulative_value[date] = current_value
            
        cumulative_value = cumulative_value[cumulative_value.cumsum() != 0]
        cumulative_value.name = code
        return cumulative_value

    except Exception:
        # 오류 메시지를 표시하되, 전체 앱은 멈추지 않도록 처리
        st.warning(f"⚠️ 종목 코드 **{code}**의 데이터를 불러오는 데 문제가 발생했습니다. (시작일: {start_date}, 종료일: {end_date})")
        return None

# ==============================================================================
# 3. Plotly 차트 생성 함수
# ==============================================================================

def create_plotly_chart(data, title="적립식 투자 시뮬레이션 결과"):
    """
    Plotly Express를 사용하여 누적 자산 가치 차트를 생성하고 애니메이션 프레임을 설정합니다.
    """
    # 1. 누적 데이터프레임 (Wide format) 준비
    data_wide = data.copy()
    data_wide.index.name = '날짜'
    
    # 2. Plotly animation_frame을 위한 누적 데이터 구조 재가공 (트릭)
    # Plotly는 각 프레임에 대해 전체 데이터를 표시하므로, 
    # 차트가 시간에 따라 그려지도록 누적된 데이터를 담는 새로운 구조가 필요합니다.
    frames_data = []
    
    for i in range(len(data_wide)):
        # 현재 프레임의 데이터 (i번째 날까지)
        frame_df = data_wide.iloc[:i + 1].copy()
        
        # Long Format으로 변환
        frame_df_long = frame_df.reset_index().melt(
            id_vars='날짜', 
            var_name='종목코드', 
            value_name='누적 자산 가치 (원)'
        )
        
        # 이 프레임이 나타내는 '날짜'를 애니메이션 프레임 키로 사용
        frame_df_long['Animation Date'] = data_wide.index[i].strftime('%Y-%m-%d')
        frames_data.append(frame_df_long)

    # 모든 프레임 데이터를 합칩니다.
    df_anim = pd.concat(frames_data)
    
    # --- Plotly Chart Creation ---
    
    fig = px.line(
        df_anim.dropna(subset=['누적 자산 가치 (원)']), 
        x='날짜',
        y='누적 자산 가치 (원)',
        color='종목코드',
        animation_frame='Animation Date', # 네이티브 애니메이션 적용
        title=title,
    )
    
    # Y축 범위 고정 (애니메이션 중 차트가 출렁이는 현상 방지)
    y_max = df_anim['누적 자산 가치 (원)'].max() * 1.05 if not df_anim.empty else 1000000 
    fig.update_yaxes(range=[0, y_max])
    
    # 레이아웃 개선
    fig.update_layout(
        xaxis_title="날짜",
        yaxis_title="누적 자산 가치 (원)",
        hovermode="x unified",
        legend_title_text='종목',
        margin=dict(l=20, r=20, t=40, b=20),
        height=500,
        # 애니메이션 속도 및 부드러운 전환 설정
        updatemenus=[
            dict(
                type='buttons',
                showactive=False,
                y=0,
                x=0.01,
                xanchor='left',
                yanchor='bottom',
                pad=dict(t=10, r=10),
                buttons=[
                    dict(
                        label='▶️ 재생 시작',
                        method='animate',
                        args=[None, {
                            'frame': {'duration': 10, 'redraw': True}, # 프레임당 10ms (속도)
                            'fromcurrent': True,
                            'transition': {'duration': 1, 'easing': 'linear'} # 부드러운 전환
                        }]
                    )
                ]
            )
        ]
        # Plotly의 기본 슬라이더는 자동으로 표시되므로 별도로 설정하지 않습니다.
    )
    
    # Y축에 통화 형식 포맷 적용
    fig.update_yaxes(tickformat=',.0f')

    # '총 적립 원금' 라인 스타일을 모든 프레임에 적용 (Plotly 애니메이션 필요)
    for frame in fig.frames:
        for trace in frame.data:
            if trace.name == '총 적립 원금':
                trace.update(
                    line=dict(color='lightgray', width=2, dash='dash'),
                    opacity=0.8,
                    hovertemplate="날짜: %{x}<br>원금: %{y:,.0f} 원<extra></extra>"
                )
    
    # 초기 데이터에도 스타일 적용
    for trace in fig.data:
        if trace.name == '총 적립 원금':
            trace.update(
                line=dict(color='lightgray', width=2, dash='dash'),
                opacity=0.8,
                hovertemplate="날짜: %{x}<br>원금: %{y:,.0f} 원<extra></extra>"
            )

    return fig

# ==============================================================================
# 4. 시뮬레이션 실행 및 결과 표시
# ==============================================================================

# 시뮬레이션 요약 테이블을 계산하고 표시하는 헬퍼 함수
def display_final_summary_table(combined_data_full, cumulative_principal, max_index, monthly_amount_krw):
    """최종 시점의 데이터를 바탕으로 투자 요약 테이블을 계산하고 표시합니다."""
    
    # 최종 시점의 투자 원금
    total_invested_principal_at_current_date = cumulative_principal.iloc[max_index]

    investment_summary = []
    
    # 1. 총 적립 원금 행을 첫 번째로 추가
    principal_value = total_invested_principal_at_current_date
    if principal_value > 0:
        investment_summary.append({
            '종목': '총 적립 원금',
            '총 투자 원금 (원)': f"{principal_value:,.0f}",
            '현재 자산 가치 (원)': f"{principal_value:,.0f}",
            '수익 / 손실 (원)': f"{0:,.0f}", 
            '수익률 (%)': f"{0.00:,.2f}%"
        })

    # 2. 각 종목별 최종 결과 추가
    for code in combined_data_full.columns:
        if code == '총 적립 원금':
            continue

        series = combined_data_full[code].dropna()
        if series.empty:
            continue
        
        final_value = series.iloc[-1]
        
        profit_loss = final_value - total_invested_principal_at_current_date
        return_rate = (profit_loss / total_invested_principal_at_current_date) * 100 if total_invested_principal_at_current_date > 0 else 0

        investment_summary.append({
            '종목': code,
            '총 투자 원금 (원)': f"{total_invested_principal_at_current_date:,.0f}",
            '현재 자산 가치 (원)': f"{final_value:,.0f}",
            '수익 / 손실 (원)': f"{profit_loss:,.0f}",
            '수익률 (%)': f"{return_rate:,.2f}%"
        })

    if investment_summary:
        summary_df = pd.DataFrame(investment_summary)
        st.markdown("#### 최종 시뮬레이션 요약")
        st.dataframe(
            summary_df, 
            hide_index=True,
            use_container_width=True,
        )

# --- 메인 실행 블록 ---

if codes:
    st.markdown("<h3 style='font-size: 18px; text-align: left;'>📊 적립식 투자 시뮬레이션 결과</h3>", unsafe_allow_html=True)
    
    simulation_results = []
    
    # 4.1. 모든 종목의 전체 시뮬레이션 데이터 계산
    for code in codes:
        result_series = run_monthly_installment_simulation(
            code, 
            start_date, 
            end_date, 
            monthly_amount_krw
        )
        if result_series is not None and not result_series.empty:
            simulation_results.append(result_series)

    # 4.2. 결과 데이터프레임 병합
    if simulation_results:
        combined_data_full = pd.concat(simulation_results, axis=1).dropna(how='all')
        
        max_index = len(combined_data_full) - 1
        
        if max_index < 0:
            st.info("선택된 기간 및 코드로 유효한 거래일 데이터가 없습니다.")
            st.stop()
            
        # --- 총 적립 원금 라인 계산 ---
        cumulative_principal = pd.Series(0.0, index=combined_data_full.index)
        total_invested_principal = 0.0
        last_invested_month = -1

        for date in combined_data_full.index:
            current_month = date.month
            
            if current_month != last_invested_month:
                total_invested_principal += monthly_amount_krw
                last_invested_month = current_month
            
            cumulative_principal[date] = total_invested_principal
        
        # 데이터프레임에 '총 적립 원금' 라인 추가
        combined_data_full['총 적립 원금'] = cumulative_principal
        
        # --- 컨트롤 패널 (Plotly 내장 재생 기능 사용) ---
        st.markdown("<h4 style='font-size: 16px; margin-top: 15px;'>▶️ 애니메이션 재생 컨트롤 (차트 내부의 재생 버튼 사용)</h4>", unsafe_allow_html=True)

        col_instant = st.columns(1)[0] # 버튼 하나만 남기고 구조 단순화

        # '최종 결과 바로 표시' 버튼은 Plotly의 애니메이션을 건너뛰고 최종 정적 상태를 표시합니다.
        with col_instant:
            st.button(
                '최종 결과 바로 표시 (시간 무시)', 
                use_container_width=True, 
                key='instant_result',
                help="애니메이션을 건너뛰고 최종 시점의 차트와 요약 정보를 즉시 표시합니다."
            )
        
        # --- Chart Display ---
        
        # Plotly Animation Chart (Full Data)
        fig_anim = create_plotly_chart(combined_data_full)
        st.plotly_chart(fig_anim, use_container_width=True)
        
        # --- Final Summary Table ---
        
        # Plotly 애니메이션 사용 시 실시간 업데이트는 불가능하므로, 최종 결과만 표시합니다.
        display_final_summary_table(
            combined_data_full, 
            cumulative_principal, 
            max_index, 
            monthly_amount_krw
        )
        
    else:
        st.info("선택된 기간 및 코드로 시뮬레이션할 유효한 데이터가 없습니다.")
