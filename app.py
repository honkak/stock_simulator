import streamlit as st
import FinanceDataReader as fdr
import datetime
import pandas as pd
import time # 애니메이션 속도 조절을 위해 time 모듈 추가
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

# Session State 초기화 (애니메이션 상태 저장)
if 'current_index' not in st.session_state:
    st.session_state.current_index = 0

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
    Plotly Express를 사용하여 누적 자산 가치 차트를 생성합니다.
    """
    # Plotly Express를 위해 데이터 구조를 Long Format으로 변환
    df_long = data.reset_index().melt(
        id_vars='index', 
        var_name='종목코드', 
        value_name='누적 자산 가치 (원)'
    ).rename(columns={'index': '날짜'})
    
    # Plotly Express 차트 생성
    fig = px.line(
        df_long.dropna(),
        x='날짜',
        y='누적 자산 가치 (원)',
        color='종목코드',
        title=title
    )
    
    # 레이아웃 개선
    fig.update_layout(
        xaxis_title="날짜",
        yaxis_title="누적 자산 가치 (원)",
        hovermode="x unified",
        legend_title_text='종목',
        margin=dict(l=20, r=20, t=40, b=20),
        height=500
    )
    
    # Y축에 통화 형식 포맷 적용
    fig.update_yaxes(tickformat=',.0f')
    
    return fig

# ==============================================================================
# 4. 시뮬레이션 실행 및 결과 표시 (애니메이션 포함)
# ==============================================================================

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

    # 4.2. 결과 데이터프레임 병합 및 애니메이션 컨트롤
    if simulation_results:
        combined_data_full = pd.concat(simulation_results, axis=1).dropna(how='all')
        dates_list = combined_data_full.index.tolist()
        max_index = len(dates_list) - 1
        
        # 데이터가 없으면 진행 불가
        if max_index < 0:
            st.info("선택된 기간 및 코드로 유효한 거래일 데이터가 없습니다.")
            st.stop()
            
        # 세션 상태 초기 인덱스 보정
        if st.session_state.current_index > max_index:
            st.session_state.current_index = max_index
        
        # --- 컨트롤 패널 ---
        st.markdown("<h4 style='font-size: 16px; margin-top: 15px;'>▶️ 시뮬레이션 재생 컨트롤</h4>", unsafe_allow_html=True)

        col_play, col_instant = st.columns([1, 1])

        # 4.2.1. 최종 결과 바로 표시 버튼
        with col_instant:
            if st.button('최종 결과 바로 표시 (시간 무시)', use_container_width=True, key='instant_result'):
                st.session_state.current_index = max_index
                # st.rerun() 대신 인덱스만 업데이트하고 바로 아래에서 그 결과를 그림

        # 4.2.2. 날짜 슬라이더 (수동 재생 및 시작점 설정)
        display_index = st.slider(
            '차트 표시 날짜를 선택하세요',
            min_value=0,
            max_value=max_index,
            value=st.session_state.current_index,
            step=1,
            key='date_slider'
        )
        
        # 슬라이더 값 변경 시 세션 상태 업데이트
        st.session_state.current_index = display_index
        
        # 현재 시점을 표시
        current_date_display = dates_list[st.session_state.current_index].strftime('%Y년 %m월 %d일')
        st.caption(f"**현재 시뮬레이션 시점:** {current_date_display}")
        
        # 4.2.3. 차트 및 요약 테이블을 업데이트할 Placeholder 설정
        chart_viz_placeholder = st.empty()        # 차트 시각화
        chart_date_caption_placeholder = st.empty() # 애니메이션 날짜 캡션
        summary_placeholder = st.empty()
        
        # 4.2.4. 재생 시작 버튼 (애니메이션 루프)
        with col_play:
            if st.button('재생 시작 (애니메이션)', use_container_width=True, key='start_play'):
                # 루프가 돌아가는 동안 UI를 막고 애니메이션을 표시
                for i in range(st.session_state.current_index, max_index + 1, 10): # 10일 간격으로 빠르게 진행
                    
                    # 현재 데이터 슬라이싱
                    current_data_for_anim = combined_data_full.iloc[:i + 1]
                    
                    with chart_viz_placeholder.container():
                        # Plotly 차트 생성 및 업데이트
                        fig = create_plotly_chart(current_data_for_anim)
                        st.plotly_chart(fig, use_container_width=True)
                        
                    with chart_date_caption_placeholder:
                        # 현재 시점을 표시
                        current_date_in_anim = dates_list[i].strftime('%Y년 %m월 %d일')
                        st.caption(f"현재 시점: **{current_date_in_anim}**")
                        
                    time.sleep(0.05) # 부드러운 재생을 위해 지연 시간 0.05초 유지
                
                # 애니메이션 완료 후 최종 상태로 업데이트하고 UI 갱신
                st.session_state.current_index = max_index
                st.rerun()
                
        # --- 차트 및 요약 결과 표시 ---
        
        # 현재 슬라이더/애니메이션 상태에 따라 데이터 슬라이싱
        current_data = combined_data_full.iloc[:st.session_state.current_index + 1]

        # 4.3. 차트 표시
        with chart_viz_placeholder:
            fig = create_plotly_chart(current_data)
            st.plotly_chart(fig, use_container_width=True)
        
        with chart_date_caption_placeholder:
            st.caption(f"차트 시점: **{current_date_display}**") # 애니메이션 후 또는 슬라이더 조작 시 캡션

        # 4.4. 최종 결과 요약 계산 및 표시
        if st.session_state.current_index > 0:
            
            with summary_placeholder:
                st.markdown("#### 누적 투자 요약")
                
                investment_summary = []

                for code in current_data.columns:
                    series = current_data[code].dropna()
                    if series.empty:
                        continue

                    # 투자 원금 계산: 데이터가 존재하는 월 수
                    invested_months = series.index.to_series().dt.to_period('M').nunique()
                    total_invested_principal = invested_months * monthly_amount_krw
                    
                    final_value = series.iloc[-1] if not series.empty else 0
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
                    summary_df = pd.DataFrame(investment_summary)
                    st.dataframe(
                        summary_df, 
                        hide_index=True,
                        use_container_width=True,
                    )
        
    else:
        st.info("선택된 기간 및 코드로 시뮬레이션할 유효한 데이터가 없습니다.")
