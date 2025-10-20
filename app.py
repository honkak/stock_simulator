import streamlit as st
import FinanceDataReader as fdr
import datetime
import pandas as pd
import plotly.graph_objects as go # Plotly graph_objects 사용
import time
import yfinance as yf # ⭐ yfinance 라이브러리 추가

# ==============================================================================
# 0. Session State 및 UI Helper Functions
# ==============================================================================

# 차트 표시 모드 초기화 ('animation' 또는 'static')
if 'display_mode' not in st.session_state:
    st.session_state.display_mode = 'animation'

# 한국 주식 코드 판별 헬퍼 (6자리 숫자로 판단)
def is_korean_stock(code):
    return code.isdigit() and len(code) == 6

# ⭐ 종목 코드 -> 야후 파이낸스 티커 변환 헬퍼
def get_yf_ticker(code):
    """종목 코드를 받아 yfinance에서 인식할 수 있는 티커로 변환합니다."""
    code = code.strip().upper()
    if not code:
        return None
    
    # 한국 주식 (6자리 숫자)
    if is_korean_stock(code):
        return f"{code}.KS"
    
    # 주요 지수 (yfinance에서 ^를 사용하는 경우가 일반적)
    index_map = {
        'DJI': '^DJI', 'IXIC': '^IXIC', 'GSPC': '^GSPC', 'VIX': '^VIX',
        # KRX 지수는 FinanceDataReader에서 지원하지만, 종목명 조회를 위해 yfinance가 인식 가능한 코드로 변환하지 않습니다. 
        # (KRX 지수 코드는 fdr로만 가격을 가져옴)
    }
    return index_map.get(code, code) # 매핑된 지수 코드를 반환하거나, 그대로 (미국 주식/ETF) 반환

# ⭐ yfinance를 사용하여 종목명 조회 함수 (캐싱 적용)
@st.cache_data(show_spinner="📜 종목 정보를 불러오는 중...")
def get_stock_names_via_yf(codes_list):
    """yfinance를 사용하여 종목 코드-이름 매핑을 가져옵니다."""
    stock_name_map = {}
    
    # Fdr로 가져올 수 있는 KRX 종목 목록 (종목명 매핑을 돕기 위해 사용, yfinance의 shortName이 부정확할 때 대비)
    # yfinance가 해외 종목명을 더 잘 가져오므로, KRX 종목명만 fdr의 StockListing으로 보강합니다.
    krx_name_map = {}
    try:
        df_krx = fdr.StockListing('KRX')
        krx_name_map = df_krx.set_index('Symbol')['Name'].to_dict()
    except Exception:
        pass # fdr 로딩 실패 시 무시

    for code in codes_list:
        yf_ticker = get_yf_ticker(code)
        
        # 1. KRX 종목명 (fdr 보조)
        if is_korean_stock(code) and code in krx_name_map:
            stock_name_map[code] = krx_name_map[code]
            continue
            
        # 2. yfinance 조회
        if yf_ticker:
            try:
                stock = yf.Ticker(yf_ticker)
                # 'shortName' 또는 'longName'을 시도
                stock_name = stock.info.get('shortName', stock.info.get('longName', '이름을 찾을 수 없습니다.'))
                
                # 티커가 한국 종목(.KS)인데 이름이 부정확한 경우 보조 맵을 다시 확인
                if is_korean_stock(code) and stock_name in ['이름을 찾을 수 없습니다.', '']:
                    stock_name = krx_name_map.get(code, '이름을 찾을 수 없습니다.')
                    
                stock_name_map[code] = stock_name if stock_name else '이름을 찾을 수 없습니다.'
                
            except Exception:
                stock_name_map[code] = '이름을 찾을 수 없습니다.'
        else:
            stock_name_map[code] = '이름을 찾을 수 없습니다.'
            
    return stock_name_map


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
def display_final_summary_table(data, principal_series, monthly_amount, stock_name_map):
    """최종 시점의 데이터를 바탕으로 투자 요약 테이블을 계산하고 표시합니다."""

    valid_data_length = len(principal_series.dropna())
    if valid_data_length == 0:
        return

    max_index = valid_data_length - 1
    total_invested_principal = principal_series.iloc[max_index]

    # 총 적립 횟수 (총 개월 수) 계산: '총 적립 원금'이 월 적립 금액으로 나뉘는 횟수
    num_months = round(total_invested_principal / monthly_amount)
    annual_interest_rate = 0.03 # 연 3%
    monthly_interest_rate = annual_interest_rate / 12 # 월 이율

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

    # 2. 월 적금 3% 이율 (단리) 행 추가
    if num_months > 0:
        # 단리 적금 최종 가치 계산
        deposit_final_value = 0
        for k in range(1, num_months + 1):
            interest_period = num_months - k
            single_deposit_value = monthly_amount * (1 + monthly_interest_rate * interest_period)
            deposit_final_value += single_deposit_value

        deposit_profit_loss = deposit_final_value - total_invested_principal
        deposit_return_rate = (deposit_profit_loss / total_invested_principal) * 100 if total_invested_principal > 0 else 0

        investment_summary.append({
            '종목': '월 적금 3% 이율 (단리)',
            '총 투자 원금 (원)': f"{total_invested_principal:,.0f}",
            '현재 자산 가치 (원)': f"{deposit_final_value:,.0f}",
            '수익 / 손실 (원)': f"{deposit_profit_loss:,.0f}",
            '수익률 (%)': f"{deposit_return_rate:,.2f}%"
        })

    # 3. 각 종목별 최종 결과 추가
    for code in data.columns:
        if code == '총 적립 원금':
            continue

        # 종목 코드에 종목명 추가하여 포맷팅
        name = stock_name_map.get(code, '이름을 찾을 수 없습니다.')
        display_name = f"{code} ({name})" # 종목코드 (종목명) 포맷

        # 마지막 유효 값 (최종 자산 가치)
        final_value = data[code].dropna().iloc[-1]

        profit_loss = final_value - total_invested_principal
        return_rate = (profit_loss / total_invested_principal) * 100 if total_invested_principal > 0 else 0

        investment_summary.append({
            '종목': display_name,
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
        # FinanceDataReader를 사용하여 주가 데이터 가져오기 (fdr이 넓은 범위의 데이터를 잘 가져옴)
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

# 1.3. 종목 코드 입력 및 종목명 표시
# ⭐ 입력된 코드를 모아서 종목명 맵을 한 번에 로드합니다.
col_code1, col_code2, col_code3 = st.columns(3)
codes_for_name = []

with col_code1: 
    code1 = st.text_input('종목코드 1', value='QQQ', placeholder='(예시) QQQ')
    codes_for_name.append(code1.strip())
with col_code2: 
    code2 = st.text_input('종목코드 2', value='005930', placeholder='(예시) 005930')
    codes_for_name.append(code2.strip())
with col_code3: 
    code3 = st.text_input('종목코드 3', value='AAPL', placeholder='(예시) AAPL')
    codes_for_name.append(code3.strip())

# 유효한 코드만 필터링
codes_for_name = [c for c in codes_for_name if c] 

# ⭐ yfinance를 사용하여 종목명 매핑 데이터 로드 (캐싱 적용)
stock_name_map = get_stock_names_via_yf(codes_for_name)

# 종목명 표시
col_name1, col_name2, col_name3 = st.columns(3)
with col_name1:
    name1 = stock_name_map.get(code1.strip(), '이름을 찾을 수 없습니다.')
    st.markdown(f"**{name1}**" if name1 != '이름을 찾을 수 없습니다.' else f'<span style="color:red;">{name1}</span>', unsafe_allow_html=True)
with col_name2:
    name2 = stock_name_map.get(code2.strip(), '이름을 찾을 수 없습니다.')
    st.markdown(f"**{name2}**" if name2 != '이름을 찾을 수 없습니다.' else f'<span style="color:red;">{name2}</span>', unsafe_allow_html=True)
with col_name3:
    name3 = stock_name_map.get(code3.strip(), '이름을 찾을 수 없습니다.')
    st.markdown(f"**{name3}**" if name3 != '이름을 찾을 수 없습니다.' else f'<span style="color:red;">{name3}</span>', unsafe_allow_html=True)

st.markdown("---")

codes = [c.strip() for c in [code1, code2, code3] if c.strip()]

if codes:
    
    # 환율 데이터 선취 및 캐싱
    usd_krw_rate_series = get_usd_krw_rate(start_date, end_date)

    dfs = []
    for c in codes:
        # FinanceDataReader로 주가 데이터를 가져옴
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
    st.markdown("<h3 style='font-size: 18px; text-align: left;'>📊 적립식 투자 시뮬레이션 결과</h3>", unsafe_allow_html=True)

    # ==============================================================================
    # 3.3. Plotly go.Figure 기반 애니메이션 (위치 조정)
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

    # 4. Figure 생성 및 버튼 위치 조정 (수정된 부분 반영)
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

    # 애니메이션 모드일 때만 Plotly 재생 버튼 추가 (위치 수정: x=1.05, y=0.25)
    if st.session_state.display_mode == 'animation':
        fig.update_layout(
            updatemenus=[dict(type="buttons",
                              x=1.03,  # ⭐ 왼쪽으로 이동 (1.21 -> 1.05)
                              y=0.25,  # ⭐ 아래로 이동 (0.7 -> 0.25)
                              showactive=False,
                              xanchor='left', # x=1.05를 기준으로 버튼을 왼쪽에 고정
                              yanchor='middle', # y=0.25를 기준으로 버튼을 중앙에 고정
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

    # 5. Plotly Config 설정: 기본 모드바의 애니메이션 버튼을 제거
    config = {
        'modeBarButtonsToRemove': ['zoom2d', 'pan2d', 'select2d', 'lasso2d', 'zoomIn2d', 'zoomOut2d', 'autoScale2d', 'resetScale2d', 'toggleSpikelines', 'hoverCompareCartesian', 'hoverClosestCartesian', 'toImage', 'sendDataToCloud', 'editInChartStudio', 'tableRotation', 'v1hovermode', 'toggleHover', 'resetViewMapbox', 'resetViews', 'resetGeo', 'hoverClosestGeo', 'hoverClosestGl2d', 'hoverClosestPie', 'resetSankeyGroup', 'toggleHover', 'resetGeo', 'hoverClosest3d', 'orbitRotation', 'tableRotation', 'resetCameraDefault3d', 'resetCameraLastSave3d', 'tableRotation', 'zoom3d', 'pan3d', 'orbitRotation', 'tableRotation', 'resetCameraDefault3d', 'resetCameraLastSave3d', 'hoverClosest3d', 'tableRotation', 'zoomInGeo', 'zoomOutGeo', 'resetGeo', 'hoverClosestGeo', 'zoomInMapbox', 'zoomOutMapbox', 'resetMapbox', 'hoverClosestMapbox', 'resetViewMapbox', 'playButton', 'pauseButton']
    }
    # 5. 차트 표시 (config 추가)
    st.plotly_chart(fig, config=config, use_container_width=True)

    # ----------------------------------------------------------
    # 6. 최종 요약 테이블 표시
    # ----------------------------------------------------------
    # monthly_amount_krw, stock_name_map를 추가 인수로 전달
    display_final_summary_table(data, cumulative_principal, monthly_amount_krw, stock_name_map)

# ==============================================================================
# 4. 종목 코드 참고 자료 섹션 (추가됨)
# (변경 없음)
# ==============================================================================

# 수평선 추가
st.markdown("---")

# 체크박스 그룹
col1, col2, col3, col4 = st.columns(4)
with col1:
    show_us_etf = st.checkbox("미국ETF", value=False)  # 미국ETF
with col2:
    show_kr_etf = st.checkbox("한국ETF", value=False)  # 한국ETF
with col3:
    show_major_stocks = st.checkbox("주요종목", value=False)  # 주요종목
with col4:
    show_major_index = st.checkbox("지수", value=False)  # 지수


# '미국ETF' 체크박스와 연결된 데이터 행렬
data_matrix_us_etf = [
    ['-3X', '-2X', '-1X', '코드', '1X', '2X', '3X'],  # 1행
    ['SPXU', 'SDS', 'SH', 'S&P500', 'SPY', 'SSO', 'UPRO'],  # 2행
    ['SQQQ', 'QID', 'PSQ', '나스닥100', 'QQQ', 'QLD', 'TQQQ'],  # 3행
    ['SDOW', 'DXD', 'DOG', '다우존스', 'DIA', 'DDM', 'UDOW'],  # 4행
    ['TZA', 'TWM', 'RWM', '러셀2000', 'IWM', 'UWM', 'TNA'],  # 5행
    ['', '', '', '한국', 'EWY', 'KORU', ''],  # 6행
    ['YANG', 'FXP', 'CHAD', '중국', 'FXI', 'CHAU', 'YINN'],  # 7행
    ['', 'EWV', '', '일본', 'EWJ', 'EZJ', 'JPNL'],  # 8행
    ['', '', '', '베트남', 'VNM', '', ''],  # 9행
    ['INDZ', '', '', '인도', 'INDA', '', 'INDL'],  # 10행
    ['RUSS', '', '', '러시아', 'RSX', '', 'RUSL'],  # 11행
    ['', 'BZQ', '', '브라질', 'EWZ', '', 'BRZU'],  # 12행
    ['DGLD', 'GLL', 'DGZ', '금', 'GLD', 'DGP', 'UGLD'],  # 13행
    ['DSLV', 'ZSL', '', '은', 'SLV', 'AGQ', 'USLV'],  # 14행
    ['DWT', 'SCO', '', '원유', 'USO', 'UCO', ''],  # 15행
    ['DGAZ', 'KOLD', '', '천연가스', 'UNG', 'BOIL', 'UGAZ'],  # 16행
    ['', '', '', '농산물', 'DBA', '', ''],  # 17행
]

# '지수' 체크박스와 연결된 데이터 행렬
data_matrix_index = [
    ['한국코드', '설명', '미국코드', '설명', '기타코드', '설명'],  # 1행
    ['KS11', 'KOSPI지수', 'DJI', '다우존스', 'JP225', '닛케이225선물'],  # 2행
    ['KQ11', 'KOSDAQ지수', 'IXIC', '나스닥', 'STOXX50E', 'EuroStoxx50'],  # 3행
    ['KS50', 'KOSPI50지수', 'GSPC', 'S&P500', 'CSI300', 'CSI300(중국)'],  # 4행
    ['KS100', 'KOSPI100', 'VIX', 'S&P500VIX', 'HSI', '항셍(홍콩)'],  # 5행
    ['KRX100', 'KRX100', '-', '-', 'FTSE', '영국FTSE'],  # 6행
    ['KS200', '코스피200', '-', '-', 'DAX', '독일DAX30'],  # 7행
]

# 시가총액 상위 11개 종목 데이터 행렬
data_matrix_top_stocks = [
    ['미국종목코드', '설명', '한국종목코드', '설명'],  # 1행
    ['AAPL', '애플', '005930', '삼성전자'],  # 2행
    ['MSFT', '마이크로소프트', '000660', 'SK하이닉스'],  # 3행
    ['AMZN', '아마존', '373220', 'LG에너지솔루션'],  # 4행
    ['NVDA', '엔비디아', '207940', '삼성바이오로직스'],  # 5행
    ['GOOGL', '알파벳A', '005380', '현대차'],  # 6행
    ['META', '메타', '068270', '셀트리온'],  # 7행
    ['TSLA', '테슬라', '000270', '기아'],  # 8행
    ['BRK.B', '버크셔헤서웨이', '196170', '알테오젠'],  # 9행
    ['UNH', '유나이티드헬스', '247540', '에코프로비엠'],  # 10행
    ['JNJ', '존슨앤존슨', '086520', '에코프로'],  # 11행
]

# 한국ETF 체크박스와 연결된 데이터 행렬 (4열)
data_matrix_kr_etf = [
    ['한국종목코드', '설명', '한국종목코드', '설명'],  # 열 제목
    ['069500', 'KODEX 200', '122630', 'KODEX 레버리지'],
    ['229200', 'KODEX 코스닥150', '233740', 'KODEX 코스닥150레버리지'],
    ['114800', 'KODEX 인버스', '252670', 'KODEX 200선물인버스2X'],
    ['251340', 'KODEX 코스닥150선물인버스', '442580', 'PLUS 글로벌HBM반도체'],
    ['243890', 'TIGER 200에너지화학레버리지', '412570', 'TIGER 2차전지TOP10레버리지'],
    ['463640', 'KODEX 미국S&P500유틸리티', '379800', 'KODEX 미국S&P500TR'],
    ['379810', 'KODEX 미국나스닥100TR', '449190', 'KODEX 미국나스닥100(H)'],
    ['409820', 'KODEX 미국나스닥100레버리지(합성 H)', '438100', 'ACE 미국나스닥100채권혼합액티브'],
    ['447660', 'PLUS 애플채권혼합', '448540', 'ACE 엔비디아채권혼합블룸버그'],
    ['236350', 'TIGER 인도니프티50레버리지(합성)', '132030', 'KODEX 골드선물(H)'],
    ['144600', 'KODEX 은선물(H)', '530063', '삼성 레버리지 구리 선물 ETN(H)'],
    ['530031', '삼성 레버리지 WTI원유 선물 ETN', '530036', '삼성 인버스 2X WTI원유 선물 ETN'],
    ['438320', 'TIGER 차이나항셍테크레버리지(합성 H)', '371460', 'TIGER 차이나전기차SOLACTIVE'],
]

# '주요종목' 체크박스를 선택할 때 표 출력
if show_major_index or show_major_stocks or show_us_etf or show_kr_etf:
    # 미국ETF 표 출력
    if show_us_etf:
        st.markdown("<h4 style='font-size: 16px; text-align: left; margin-top: 20px;'>미국 ETF 주요 코드</h4>", unsafe_allow_html=True)
        html = '''
        <style>
        table {
            border-collapse: collapse;  
            width: 100%;  
            font-size: 10px;  /* 글자 크기를 10px로 설정 */
        }
        td {
            border: 1px solid black;  
            padding: 8px;  
            text-align: center;
            /* color: #333333; <-- 일반 셀의 텍스트 색상 고정 제거 */
        }
        .highlight {
            background-color: lightgray;
            color: #333333; /* 다크 모드에서도 대비가 확보되도록 텍스트 색상을 어두운 회색으로 고정 */
        }
        </style>
        <table>
        '''

        for i, row in enumerate(data_matrix_us_etf):
            html += '<tr>'
            for j, cell in enumerate(row):
                if i == 0 or j == 3:  # 첫 번째 행과 코드 열 강조
                    html += f'<td class="highlight">{cell}</td>'
                else:
                    html += f'<td>{cell}</td>'
            html += '</tr>'
        html += '</table>'
        st.markdown(html, unsafe_allow_html=True)

    # 한국ETF 표 출력
    if show_kr_etf:
        st.markdown("<h4 style='font-size: 16px; text-align: left; margin-top: 20px;'>한국 ETF 주요 코드</h4>", unsafe_allow_html=True)
        html_kr_etf = '''
        <style>
        table {
            border-collapse: collapse;  
            width: 100%;  
            font-size: 10px;  /* 글자 크기를 10px로 설정 */
        }
        td {
            border: 1px solid black;  
            padding: 8px;  
            text-align: center;
            /* color: #333333; <-- 일반 셀의 텍스트 색상 고정 제거 */
        }
        .highlight {
            background-color: lightgray;
            color: #333333; /* 다크 모드에서도 대비가 확보되도록 텍스트 색상을 어두운 회색으로 고정 */
        }
        </style>
        <table>
        '''

        for i, row in enumerate(data_matrix_kr_etf):
            html_kr_etf += '<tr>'
            for j, cell in enumerate(row):
                if i == 0 or j == 1 or j == 3:  # 첫 번째 행과 코드 열 강조
                    html_kr_etf += f'<td class="highlight">{cell}</td>'
                else:
                    html_kr_etf += f'<td>{cell}</td>'
            html_kr_etf += '</tr>'
        html_kr_etf += '</table>'
        st.markdown(html_kr_etf, unsafe_allow_html=True)

    # 주요종목 표 출력
    if show_major_stocks:
        st.markdown("<h4 style='font-size: 16px; text-align: left; margin-top: 20px;'>주요 시가총액 상위 종목 코드</h4>", unsafe_allow_html=True)
        html_major_stocks = '''
        <style>
        table {
            border-collapse: collapse;  
            width: 100%;  
            font-size: 10px;  /* 글자 크기를 10px로 설정 */
        }
        td {
            border: 1px solid black;  
            padding: 8px;  
            text-align: center;
            /* color: #333333; <-- 일반 셀의 텍스트 색상 고정 제거 */
        }
        .highlight {
            background-color: lightgray;
            color: #333333; /* 다크 모드에서도 대비가 확보되도록 텍스트 색상을 어두운 회색으로 고정 */
        }
        </style>
        <table>
        '''

        for i, row in enumerate(data_matrix_top_stocks):
            html_major_stocks += '<tr>'
            for j, cell in enumerate(row):
                if i == 0 or j == 1 or j == 3:  # 첫 번째 행과 코드 열 강조
                    html_major_stocks += f'<td class="highlight">{cell}</td>'
                else:
                    html_major_stocks += f'<td>{cell}</td>'
            html_major_stocks += '</tr>'
        html_major_stocks += '</table>'
        st.markdown(html_major_stocks, unsafe_allow_html=True)

    # 지수 표 출력
    if show_major_index:
        st.markdown("<h4 style='font-size: 16px; text-align: left; margin-top: 20px;'>주요 지수 코드</h4>", unsafe_allow_html=True)
        html_index = '''
        <style>
        table {
            border-collapse: collapse;  
            width: 100%;  
            font-size: 10px;  /* 글자 크기를 10px로 설정 */
        }
        td {
            border: 1px solid black;  
            padding: 8px;  
            text-align: center;
            /* color: #333333; <-- 일반 셀의 텍스트 색상 고정 제거 */
        }
        .highlight {
            background-color: lightgray;
            color: #333333; /* 다크 모드에서도 대비가 확보되도록 텍스트 색상을 어두운 회색으로 고정 */
        }
        </style>
        <table>
        '''

        for i, row in enumerate(data_matrix_index):
            html_index += '<tr>'
            for j, cell in enumerate(row):
                if i == 0 or j == 1 or j == 3 or j == 5:  # 첫 번째 행과 코드 열 강조
                    html_index += f'<td class="highlight">{cell}</td>'
                else:
                    html_index += f'<td>{cell}</td>'
            html_index += '</tr>'
        html_index += '</table>'
        st.markdown(html_index, unsafe_allow_html=True)
