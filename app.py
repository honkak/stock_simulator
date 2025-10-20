import streamlit as st
import FinanceDataReader as fdr
import datetime
import pandas as pd
import plotly.graph_objects as go # Plotly graph_objects 사용

# ==============================================================================
# 0. Session State 및 UI Helper Functions
# ==============================================================================

# 차트 표시 모드 초기화 ('animation' 또는 'static')
if 'display_mode' not in st.session_state:
    st.session_state.display_mode = 'animation'

# 시뮬레이션 요약 테이블을 계산하고 표시하는 헬퍼 함수
def display_final_summary_table(data, principal_series):
    """최종 시점의 데이터를 바탕으로 투자 요약 테이블을 계산하고 표시합니다."""
    max_index = len(data) - 1
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
        final_value = data[code].iloc[-1]
        
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
        st.markdown("#### 최종 시뮬레이션 요약")
        st.dataframe(
            summary_df, 
            hide_index=True,
            use_container_width=True,
        )

# ==============================================================================
# 1. UI 및 입력 설정
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

# 1.2. 적립 금액 입력 (한 줄 위로 이동)
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

# ==============================================================================
# 2. 적립식 시뮬레이션 로직
# ==============================================================================
@st.cache_data(show_spinner="⏳ 데이터 로딩 및 시뮬레이션 계산 중...")
def simulate_monthly_investment(code, start_date, end_date, monthly_amount):
    """월별 정액 적립식 투자의 누적 가치를 시뮬레이션합니다."""
    try:
        df = fdr.DataReader(code, start_date, end_date)
        close = df['Close']
        cumulative = pd.Series(0.0, index=close.index)
        shares = 0
        last_month = -1
        for date, price in close.items():
            current_month = date.month
            if current_month != last_month:
                shares += monthly_amount / price
                last_month = date.month
            cumulative[date] = shares * price
        cumulative.name = code
        return cumulative[cumulative.cumsum() != 0] # 첫 투자 시점 이후 데이터만 반환
    except Exception:
        st.warning(f"⚠️ 종목 코드 **{code}**의 데이터를 불러오는 데 문제가 발생했습니다.")
        return None

# ==============================================================================
# 3. 메인 실행 블록
# ==============================================================================

if codes:
    
    dfs = []
    for c in codes:
        series = simulate_monthly_investment(c, start_date, end_date, monthly_amount_krw)
        if series is not None:
            dfs.append(series)
            
    if not dfs:
        st.warning("유효한 데이터가 없습니다. 종목 코드나 날짜를 확인해 주세요.")
        st.stop()
        
    data = pd.concat(dfs, axis=1).dropna(how='all')

    # ==============================================================================
    # 3.1. 총 적립 원금 계산
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
    # 3.2. 제목 및 버튼 (좌우 배치)
    # ==============================================================================
    col_title, col_button = st.columns([1, 0.4])

    with col_title:
        st.markdown("<h3 style='font-size: 18px; text-align: left;'>📊 적립식 투자 시뮬레이션 결과</h3>", unsafe_allow_html=True)

    with col_button:
        # '최종 결과 바로 표시' 버튼 로직 (상태 토글)
        button_label = '최종 결과 바로 표시' if st.session_state.display_mode == 'animation' else '애니메이션 모드로 돌아가기'
        if st.button(
            button_label,
            use_container_width=True, 
            key='toggle_result',
            help="차트 표시 모드를 전환합니다."
        ):
            st.session_state.display_mode = 'static' if st.session_state.display_mode == 'animation' else 'animation'
            st.rerun() # 상태가 변경되었으므로 재실행하여 차트를 다시 그립니다.


    # ==============================================================================
    # 3.3. Plotly go.Figure 기반 애니메이션 (월별 프레임 최적화)
    # ==============================================================================
    
    # 1. 월별 첫 거래일 인덱스 추출 (프레임 최적화)
    data['YearMonth'] = data.index.to_series().dt.to_period('M')
    monthly_indices = data.groupby('YearMonth').apply(lambda x: x.index[0]).tolist()
    data = data.drop(columns=['YearMonth'])
    
    # 2. 프레임 생성
    frames = []
    # 애니메이션 모드일 경우에만 프레임을 생성
    if st.session_state.display_mode == 'animation':
        for date in monthly_indices:
            k = data.index.get_loc(date) 
            
            frame_data = []
            for col in data.columns:
                # 원금 라인은 밝은 회색 점선으로 특별 스타일링
                line_style = dict(color='lightgray', width=2, dash='dash') if col == '총 적립 원금' else None
                
                frame_data.append(
                    go.Scatter(
                        x=data.index[:k+1], 
                        y=data[col][:k+1], 
                        mode='lines', 
                        name=col,
                        line=line_style if line_style else None
                    )
                )

            frames.append(go.Frame(data=frame_data, name=date.strftime('%Y-%m-%d'), 
                                   layout=go.Layout(title=f"누적 자산 가치 변화 (시점: {date.strftime('%Y년 %m월')})")))
    
    # 3. 초기/정적 데이터 트레이스 생성
    initial_data = []
    
    # 정적 모드일 경우 모든 데이터를 포함
    data_to_render = data if st.session_state.display_mode == 'static' else data.iloc[[0]]

    for col in data.columns:
        line_style = dict(color='lightgray', width=2, dash='dash') if col == '총 적립 원금' else None
        
        initial_data.append(
            go.Scatter(
                x=data_to_render.index, 
                y=data_to_render[col], 
                mode='lines', 
                name=col,
                line=line_style if line_style else None
            )
        )

    # 4. Figure 생성 및 버튼 위치 조정
    fig = go.Figure(
        data=initial_data,
        layout=go.Layout(
            title="누적 자산 가치 변화",
            xaxis=dict(title="날짜"),
            yaxis=dict(title="가치 (원)", range=[0, data.max().max() * 1.1], tickformat=',.0f'),
            height=550,
        ),
        frames=frames
    )
    
    # 애니메이션 모드일 때만 Plotly 재생 버튼 추가 (범례 하단으로 이동 및 속도 개선)
    if st.session_state.display_mode == 'animation':
        fig.update_layout(
            updatemenus=[dict(type="buttons",
                             x=1.02, # x축 위치 (차트 오른쪽, 범례 근처)
                             y=0.85, # y축 위치 (범례 아래쪽)
                             showactive=False,
                             buttons=[
                                 dict(label="▶️ 재생 시작", 
                                      method="animate", 
                                      args=[None, {"frame": {"duration": 75, "redraw": True}, # 속도 조정 (75ms/월)
                                                   "fromcurrent": True, 
                                                   "transition": {"duration": 20, "easing": "linear"}}]), # 반응 속도 개선
                                 dict(label="⏸️ 정지", 
                                      method="animate", 
                                      args=[[None], {"frame": {"duration": 0, "redraw": False}, "mode": "immediate"}])
                             ])]
        )

    # 5. 차트 표시
    st.plotly_chart(fig, use_container_width=True)
    
    if st.session_state.display_mode == 'animation':
        st.caption("차트 우측 상단(범례 하단)의 '▶️ 재생 시작' 버튼과 시간 슬라이더를 사용하여 애니메이션을 제어하세요.")
    else:
        st.caption("현재 '최종 결과 바로 표시' 모드입니다. 왼쪽 버튼을 눌러 애니메이션 모드로 전환하세요.")

    # 6. 최종 요약 테이블 표시
    display_final_summary_table(data, cumulative_principal)
