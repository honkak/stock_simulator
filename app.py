import streamlit as st
import FinanceDataReader as fdr
import datetime
import pandas as pd
import plotly.graph_objects as go
import time # 실시간 업데이트를 위한 지연 시간 제어

# ==============================================================================
# 0. Session State 및 UI Helper Functions
# (변경 없음: 이전 코드와 동일)
# ==============================================================================

# 차트 표시 모드 초기화 ('animation_loop' 또는 'static')
if 'display_mode' not in st.session_state:
    st.session_state.display_mode = 'animation_loop' 

# 애니메이션 재생 상태 ('ready', 'playing')
if 'animation_state' not in st.session_state:
    st.session_state.animation_state = 'ready'

# 한국 주식 코드 판별 헬퍼 (6자리 숫자로 판단)
def is_korean_stock(code):
    return code.isdigit() and len(code) == 6

# 환율 데이터 (USD/KRW)를 가져오는 헬퍼 함수
@st.cache_data
def get_usd_krw_rate(start_date, end_date):
    """원/달러 환율(USD/KRW) 종가를 가져옵니다."""
    try:
        rate_df = fdr.DataReader('USD/KRW', start_date, end_date)
        return rate_df['Close'].rename('USD/KRW')
    except Exception:
        st.warning("⚠️ 원/달러 환율 데이터를 불러오는데 실패했습니다. 미국 주식 계산에 환율이 적용되지 않습니다. (1 USD = 1,300 KRW 가정)")
        return pd.Series(1300.0, index=pd.to_datetime([])) 

# ********************** 실시간 요약 테이블 업데이트 함수 (변경 없음) **********************
def update_summary_table(data_up_to_date, principal_series_full, current_index, monthly_amount_krw, placeholder):
    """
    특정 시점까지의 데이터를 바탕으로 투자 요약 테이블을 계산하고 
    지정된 플레이스홀더에 표시합니다.
    """
    
    data_cut = data_up_to_date.iloc[:current_index + 1]
    principal_series_cut = principal_series_full.iloc[:current_index + 1].dropna()
    valid_data_length = len(principal_series_cut)
    
    if valid_data_length == 0:
        return
        
    total_invested_principal = principal_series_cut.iloc[-1]

    investment_summary = []
    
    principal_value = total_invested_principal
    if principal_value > 0:
        investment_summary.append({
            '종목': '총 적립 원금',
            '총 투자 원금 (원)': f"{principal_value:,.0f}",
            '현재 자산 가치 (원)': f"{principal_value:,.0f}",
            '수익 / 손실 (원)': f"{0:,.0f}", 
            '수익률 (%)': f"{0.00:,.2f}%"
        })

    for code in data_cut.columns:
        if code == '총 적립 원금':
            continue

        final_value = data_cut[code].iloc[-1]
        
        profit_loss = final_value - total_invested_principal
        return_rate = (profit_loss / total_invested_principal) * 100 if total_invested_principal > 0 else 0

        color = 'red' if profit_loss < 0 else ('blue' if profit_loss > 0 else 'black')
        
        investment_summary.append({
            '종목': code,
            '총 투자 원금 (원)': f"{total_invested_principal:,.0f}",
            '현재 자산 가치 (원)': f"{final_value:,.0f}",
            '수익 / 손실 (원)': f"<span style='color:{color}; font-weight:bold;'>{profit_loss:,.0f}</span>",
            '수익률 (%)': f"<span style='color:{color}; font-weight:bold;'>{return_rate:,.2f}%</span>"
        })

    if investment_summary:
        summary_df = pd.DataFrame(investment_summary)
        summary_date_str = pd.to_datetime(data_cut.index[-1]).strftime('%Y년 %m월 %d일')
        
        with placeholder.container():
            st.markdown(f"#### 🚀 실시간 시뮬레이션 요약 (기준일: **{summary_date_str}**)")
            st.dataframe(
                summary_df, 
                hide_index=True,
                use_container_width=True,
                column_config={
                    '수익 / 손실 (원)': st.column_config.MarkdownColumn('수익 / 손실 (원)'),
                    '수익률 (%)': st.column_config.MarkdownColumn('수익률 (%)'),
                }
            )


# 시뮬레이션 요약 테이블을 계산하고 표시하는 헬퍼 함수 (정적/최종 결과용)
def display_final_summary_table_static(data, principal_series):
    """최종 시점의 데이터를 바탕으로 투자 요약 테이블을 계산하고 표시합니다."""
    
    data_cut = data
    principal_series_cut = principal_series.dropna()
    
    valid_data_length = len(principal_series_cut)
    if valid_data_length == 0:
        return
        
    total_invested_principal = principal_series_cut.iloc[-1]

    investment_summary = []
    
    principal_value = total_invested_principal
    if principal_value > 0:
        investment_summary.append({
            '종목': '총 적립 원금',
            '총 투자 원금 (원)': f"{principal_value:,.0f}",
            '현재 자산 가치 (원)': f"{principal_value:,.0f}",
            '수익 / 손실 (원)': f"{0:,.0f}", 
            '수익률 (%)': f"{0.00:,.2f}%"
        })

    for code in data_cut.columns:
        if code == '총 적립 원금':
            continue

        final_value = data_cut[code].iloc[-1]
        
        profit_loss = final_value - total_invested_principal
        return_rate = (profit_loss / total_invested_principal) * 100 if total_invested_principal > 0 else 0
        
        color = 'red' if profit_loss < 0 else ('blue' if profit_loss > 0 else 'black')

        investment_summary.append({
            '종목': code,
            '총 투자 원금 (원)': f"{total_invested_principal:,.0f}",
            '현재 자산 가치 (원)': f"{final_value:,.0f}",
            '수익 / 손실 (원)': f"<span style='color:{color}; font-weight:bold;'>{profit_loss:,.0f}</span>",
            '수익률 (%)': f"<span style='color:{color}; font-weight:bold;'>{return_rate:,.2f}%</span>"
        })

    if investment_summary:
        summary_df = pd.DataFrame(investment_summary)
        st.markdown("#### 최종 시뮬레이션 요약")
        st.dataframe(
            summary_df, 
            hide_index=True,
            use_container_width=True,
            column_config={
                '수익 / 손실 (원)': st.column_config.MarkdownColumn('수익 / 손실 (원)'),
                '수익률 (%)': st.column_config.MarkdownColumn('수익률 (%)'),
            }
        )
# ********************** simulate_monthly_investment 함수 (변경 없음) **********************
@st.cache_data(show_spinner="⏳ 데이터 로딩 및 시뮬레이션 계산 중...")
def simulate_monthly_investment(code, start_date, end_date, monthly_amount, rate_series):
    """월별 정액 적립식 투자의 누적 가치를 시뮬레이션합니다."""
    try:
        df = fdr.DataReader(code, start_date, end_date)
        close = df['Close']
        cumulative = pd.Series(0.0, index=close.index)
        shares = 0
        last_month = -1
        is_kr_stock = is_korean_stock(code)
        
        default_rate = 1300.0
        if rate_series is not None and not rate_series.empty:
            aligned_rate = rate_series.reindex(close.index, method='ffill').fillna(default_rate)
        else:
            aligned_rate = pd.Series(default_rate, index=close.index)


        for date, price in close.items():
            current_month = date.month
            
            if is_kr_stock:
                investment_amount_local = monthly_amount
            else:
                exchange_rate = aligned_rate.loc[date]
                investment_amount_local = monthly_amount / exchange_rate 

            if current_month != last_month:
                shares += investment_amount_local / price
                last_month = date.month
            
            if is_kr_stock:
                cumulative[date] = shares * price 
            else:
                final_rate = aligned_rate.loc[date]
                cumulative[date] = shares * price * final_rate
                
        cumulative.name = code
        return cumulative[cumulative.cumsum() != 0] 
        
    except Exception:
        st.warning(f"⚠️ 종목 코드 **{code}**의 데이터를 불러오는 데 문제가 발생했습니다.")
        return None

# ==============================================================================
# 1. UI 및 입력 설정 (변경 없음)
# ==============================================================================
st.markdown("<h2 style='font-size: 24px; text-align: center; margin-bottom: 20px;'>💰 적립식 투자 시뮬레이션 (부드러운 Plotly 애니메이션) 📈</h2>", unsafe_allow_html=True)

col_start_date, col_end_date = st.columns(2)
with col_start_date:
    start_date = st.date_input("📅 조회 시작일", datetime.datetime(2022, 1, 1), max_value=datetime.datetime.now())
with col_end_date:
    end_date = st.date_input("📅 조회 종료일", datetime.datetime.now(), max_value=datetime.datetime.now())

if start_date > end_date:
    st.warning("시작일이 종료일보다 늦습니다. 날짜를 자동으로 맞바꿔 반영합니다.")
    start_date, end_date = end_date, start_date

st.markdown("---")

monthly_amount_krw = st.number_input(
    '💵 매월 적립 금액 (원)',
    min_value=1000,
    value=500000, 
    step=10000
)

col_code1, col_code2, col_code3 = st.columns(3)
with col_code1: code1 = st.text_input('종목코드 1', value='QQQ', placeholder='(예시) QQQ')
with col_code2: code2 = st.text_input('종목코드 2', value='005930', placeholder='(예시) 005930')
with col_code3: code3 = st.text_input('종목코드 3', value='AAPL', placeholder='(예시) AAPL')

st.markdown("---")

codes = [c.strip() for c in [code1, code2, code3] if c.strip()]


# ==============================================================================
# 3. 메인 실행 블록
# ==============================================================================

if codes:
    
    usd_krw_rate_series = get_usd_krw_rate(start_date, end_date)

    dfs = []
    for c in codes:
        series = simulate_monthly_investment(c, start_date, end_date, monthly_amount_krw, usd_krw_rate_series)
        if series is not None:
            dfs.append(series)
            
    if not dfs:
        st.warning("유효한 데이터가 없습니다. 종목 코드나 날짜를 확인해 주세요.")
        st.stop()
        
    data = pd.concat(dfs, axis=1).ffill().dropna(how='all')

    # 3.1. 총 적립 원금 계산
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


    # 3.2. 제목 및 버튼 (좌우 배치)
    col_title, col_button = st.columns([1, 0.4])
    col_play_button = st.empty() 

    with col_title:
        st.markdown("<h3 style='font-size: 18px; text-align: left;'>📊 적립식 투자 시뮬레이션 결과</h3>", unsafe_allow_html=True)

    with col_button:
        button_label = '최종 결과 바로 표시' if st.session_state.display_mode == 'animation_loop' else '실시간 애니메이션으로 돌아가기'
        if st.button(
            button_label,
            use_container_width=True, 
            key='toggle_result',
            help="차트 표시 모드를 전환합니다."
        ):
            st.session_state.display_mode = 'static' if st.session_state.display_mode == 'animation_loop' else 'animation_loop'
            st.session_state.animation_state = 'ready'
            st.rerun() 

    # 플레이스홀더 설정
    chart_placeholder = st.empty()
    summary_placeholder = st.empty()

    # 3.3. Plotly go.Figure 기반 애니메이션
    
    # 월별 첫 거래일의 인덱스 번호 리스트
    data['YearMonth'] = data.index.to_series().dt.to_period('M')
    monthly_index_numbers = data.groupby('YearMonth').apply(lambda x: data.index.get_loc(x.index[0])).tolist()
    data = data.drop(columns=['YearMonth'])
    
    last_index = len(data) - 1
    if last_index not in monthly_index_numbers:
        monthly_index_numbers.append(last_index)
    
    
    # 2. 실시간 업데이트 루프 (animation_loop 모드일 때만 실행)
    if st.session_state.display_mode == 'animation_loop':
        
        # ********************** 수정: 초기 fig 생성 시 빈 Scatter 트레이스를 종목 수만큼 추가 **********************
        
        # 1. 초기 트레이스 생성: Plotly에 트레이스 구조를 알려주기 위함 (데이터는 비움)
        initial_data = []
        for col in data.columns:
            line_style = dict(color='dimgray', width=2, dash='dot') if col == '총 적립 원금' else None
            initial_data.append(
                # 빈 리스트 []를 x와 y로 설정
                go.Scatter(
                    x=[], 
                    y=[], 
                    mode='lines', 
                    name=col,
                    line=line_style if line_style else None
                )
            )
        
        initial_max_val = monthly_amount_krw * 2 
        
        fig = go.Figure(
            data=initial_data, # 빈 트레이스 구조로 초기화
            layout=go.Layout(
                title="누적 자산 가치 변화",
                xaxis=dict(title="날짜"),
                yaxis=dict(title="가치 (원)", range=[0, initial_max_val], tickformat=',.0f'), 
                height=550,
            )
        )
        
        # 재생 버튼 표시 (재생 상태가 ready일 때만)
        if st.session_state.animation_state == 'ready':
            with col_play_button.container():
                if st.button("▶️ **애니메이션 재생 시작**", key='start_anim', use_container_width=True):
                    st.session_state.animation_state = 'playing'
                    st.rerun()
            
            # 차트 비어있는 상태로 초기 표시
            with chart_placeholder:
                st.plotly_chart(fig, use_container_width=True)
            
            st.caption("차트가 비어있는 상태입니다. 상단의 '▶️ 애니메이션 재생 시작' 버튼을 눌러주세요.")
            
        elif st.session_state.animation_state == 'playing':
            
            st.caption("📈 **실시간 애니메이션 진행 중...** (아래 표를 확인하세요)")
            
            # 루프 시작: 기존 fig의 data를 업데이트
            for i in monthly_index_numbers:
                
                # 현재 시점까지의 데이터만 사용
                current_data_for_anim = data.iloc[:i+1]
                
                # ********************** 수정: fig.data 전체를 할당하는 대신, 각 트레이스의 x, y 속성만 업데이트 **********************
                
                # fig.data는 리스트이며, 각 요소가 트레이스 객체임
                for trace_index, col in enumerate(data.columns):
                    
                    # 해당 트레이스의 x, y 데이터만 업데이트
                    fig.data[trace_index].x = current_data_for_anim.index
                    fig.data[trace_index].y = current_data_for_anim[col]

                # 동적 Y축 범위 계산
                current_max = current_data_for_anim.drop(columns=['총 적립 원금'], errors='ignore').max().max()
                max_val_up_to_i = current_max * 1.1 if current_max > 0 else monthly_amount_krw * 2
                
                # Figure Layout 업데이트
                fig.update_layout(
                    title=f"누적 자산 가치 변화 (시점: {current_data_for_anim.index[-1].strftime('%Y년 %m월 %d일')})",
                    yaxis=dict(range=[0, max_val_up_to_i], title="가치 (원)", tickformat=',.0f')
                )
                
                # 2. 차트 플레이스홀더에 표시
                with chart_placeholder:
                    st.plotly_chart(fig, use_container_width=True)
                    
                # 3. 요약 테이블 업데이트 (실시간)
                update_summary_table(
                    data, 
                    cumulative_principal, 
                    i, 
                    monthly_amount_krw, 
                    summary_placeholder 
                )

                # 4. 애니메이션 속도 조절
                time.sleep(0.15) 

            # 루프 완료 후 최종 상태로 변경
            st.session_state.animation_state = 'ready'
            st.caption("✅ 실시간 애니메이션이 완료되었습니다. **재생 시작** 버튼을 다시 눌러 재시작할 수 있습니다.")
            st.rerun() 


    # 3.4. 정적/최종 결과 모드 (static)
    else:
        
        static_data = []
        for col in data.columns:
            line_style = dict(color='dimgray', width=2, dash='dot') if col == '총 적립 원금' else None
            static_data.append(
                go.Scatter(
                    x=data.index, 
                    y=data[col], 
                    mode='lines', 
                    name=col,
                    line=line_style if line_style else None
                )
            )
        
        max_val = data.drop(columns=['총 적립 원금'], errors='ignore').max().max() * 1.1
        if max_val == 0:
            max_val = monthly_amount_krw * 2

        fig = go.Figure(
            data=static_data,
            layout=go.Layout(
                title="누적 자산 가치 변화 (최종 결과)",
                xaxis=dict(title="날짜"),
                yaxis=dict(title="가치 (원)", range=[0, max_val], tickformat=',.0f'), 
                height=550,
            )
        )
        
        with chart_placeholder:
            st.plotly_chart(fig, use_container_width=True)
            
        st.caption("현재 '최종 결과 바로 표시' 모드입니다. 왼쪽 버튼을 눌러 실시간 애니메이션 모드로 전환하세요.")

        with summary_placeholder:
            display_final_summary_table_static(data, cumulative_principal)
