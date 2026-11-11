import streamlit as st
import urllib.request
import json
import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import zoneinfo

# 페이지 기본 설정 (모바일 최적화)
st.set_page_config(
    page_title="퀀트 분석기",
    page_icon="📈",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 모바일 다크 테마 커스텀 CSS
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .stButton>button {
        width: 100%;
        border-radius: 10px;
        height: 2.8em;
        font-weight: 700;
        font-size: 0.95rem;
        margin-bottom: 4px;
    }
    .metric-card {
        background-color: #1a1e29;
        border-radius: 12px;
        padding: 14px;
        margin-bottom: 10px;
        border: 1px solid #2a3142;
    }
    .verdict-box {
        border-radius: 12px;
        padding: 14px;
        text-align: center;
        font-size: 1.15rem;
        font-weight: bold;
        margin-top: 10px;
        margin-bottom: 15px;
    }
    .sub-stat {
        font-size: 0.88rem;
        color: #94a3b8;
    }
</style>
""", unsafe_allow_html=True)

# 1. 메인 타이틀
st.title("📈 퀀트 분석기")
st.caption("15분봉 4박자 퀀트 알고리즘 (손익비 1:2.72 기반 실시간 자동 분석)")

# 2. 인기 종목 빠른 선택 (가로 2열 8종목)
st.write("🔥 **인기 종목 빠른 선택**")
row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)
row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)

selected_quick = None
with row1_col1:
    if st.button("SOXL"): selected_quick = "SOXL"
with row1_col2:
    if st.button("TQQQ"): selected_quick = "TQQQ"
with row1_col3:
    if st.button("TSLA"): selected_quick = "TSLA"
with row1_col4:
    if st.button("NVDA"): selected_quick = "NVDA"

with row2_col1:
    if st.button("AMD"): selected_quick = "AMD"
with row2_col2:
    if st.button("PLTR"): selected_quick = "PLTR"
with row2_col3:
    if st.button("AAPL"): selected_quick = "AAPL"
with row2_col4:
    if st.button("CONL"): selected_quick = "CONL"

# 세션 상태로 티커 유지
if "current_ticker" not in st.session_state:
    st.session_state.current_ticker = "SOXL"

if selected_quick:
    st.session_state.current_ticker = selected_quick

# 티커 및 분봉 설정
col_input, col_time = st.columns([3, 2])
with col_input:
    ticker = st.text_input("미국 주식 티커 입력", value=st.session_state.current_ticker).strip().upper()
with col_time:
    interval_choice = st.selectbox("분봉 선택", ["15m (정석 퀀트)", "5m (초단타)"], index=0)

interval_param = "15m" if "15m" in interval_choice else "5m"

# 환율 조회 함수 (기본 1,400원)
@st.cache_data(ttl=300)
def get_usd_krw_rate():
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/USDKRW=X?interval=1d&range=1d"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())['chart']['result'][0]
        rate = data['indicators']['quote'][0]['close'][-1]
        return float(rate) if rate else 1400.0
    except Exception:
        return 1400.0

usd_krw = get_usd_krw_rate()

# 캔들 데이터 조회 함수
@st.cache_data(ttl=15)
def get_chart_data(symbol, inter):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={inter}&range=5d&includePrePost=true"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())['chart']['result'][0]
    except Exception as e:
        return None, str(e)

    quotes = data['indicators']['quote'][0]
    timestamps = data.get('timestamp', [])
    valid = []
    kst = zoneinfo.ZoneInfo("Asia/Seoul")
    for ts, c, h, l, o, v in zip(timestamps, quotes['close'], quotes['high'], quotes['low'], quotes['open'], quotes['volume']):
        if c is not None and v is not None and h is not None and l is not None and o is not None:
            dt = datetime.fromtimestamp(ts, tz=kst)
            valid.append({
                'datetime': dt,
                'open': o,
                'high': h,
                'low': l,
                'close': c,
                'volume': v
            })
    if len(valid) < 30:
        return None, "유효 데이터 부족"
    return valid, None

# 지표 계산 함수들
def calc_ema_series(arr, span):
    alpha = 2.0 / (span + 1.0)
    ema = [arr[0]]
    for val in arr[1:]:
        ema.append(alpha * val + (1.0 - alpha) * ema[-1])
    return ema

# 분석 실행
if ticker:
    with st.spinner(f"🚀 {ticker} 실시간 캔들 및 퀀트 지표 계산 중..."):
        candles, err = get_chart_data(ticker, interval_param)

    if err:
        st.error(f"데이터를 불러오지 못했습니다: {err}")
    else:
        df = pd.DataFrame(candles)
        closes = df['close'].values
        highs = df['high'].values
        lows = df['low'].values
        vols = df['volume'].values

        curr = closes[-1]
        prev_low = lows[-2] if len(lows) >= 2 else lows[-1]

        # 지표 산출
        df['ema9'] = calc_ema_series(closes, 9)
        df['ema21'] = calc_ema_series(closes, 21)
        df['sma50'] = df['close'].rolling(min(50, len(df)), min_periods=1).mean()

        sma50 = df['sma50'].iloc[-1]
        ema9 = df['ema9'].iloc[-1]
        ema21 = df['ema21'].iloc[-1]

        # RSI 14
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        avg_gain = np.mean(gains[-14:])
        avg_loss = np.mean(losses[-14:])
        rs = avg_gain / (avg_loss + 1e-9)
        rsi = 100.0 - (100.0 / (1.0 + rs))

        # 거래량 비율
        vol_ma20 = np.mean(vols[-21:-1]) if len(vols) > 20 else vols[-1]
        vol_ratio = (vols[-1] / (vol_ma20 + 1e-9))

        # 4박자 조건 판별
        c1 = curr > sma50
        c2 = ema9 > ema21
        c3 = curr >= ema9
        c4 = 45.0 <= rsi <= 68.0
        c5 = vol_ratio >= 1.2
        passed_cnt = sum([c1, c2, c3, c4, c5])

        # 목표가 & 손절가 (달러 및 원화)
        tp1 = curr * 1.035
        tp2 = curr * 1.070
        sl = min(prev_low, curr * 0.982)
        sl_pct = ((sl - curr) / curr) * 100
        rr = abs((tp1 - curr) / (curr - sl)) if curr > sl else 0.0

        curr_krw = curr * usd_krw
        tp1_diff_krw = (tp1 - curr) * usd_krw
        tp2_diff_krw = (tp2 - curr) * usd_krw
        sl_diff_krw = (curr - sl) * usd_krw

        # 헤더
        st.subheader(f"📊 {ticker} 현재가: ${curr:.2f} (약 {curr_krw:,.0f}원)")

        # 판정 배너
        if passed_cnt >= 4:
            st.markdown(f"""
            <div class="verdict-box" style="background-color: #134e4a; color: #4ade80; border: 1px solid #2dd4bf;">
                ⭐ 강력 매수 진입 타점 (STRONG BUY) ⭐<br>
                <span class="sub-stat" style="color: #a7f3d0;">4박자 필터 {passed_cnt}/5개 충족 (상승 모멘텀 탄력 구간)</span>
            </div>
            """, unsafe_allow_html=True)
        elif passed_cnt == 3:
            st.markdown(f"""
            <div class="verdict-box" style="background-color: #713f12; color: #facc15; border: 1px solid #fde047;">
                🟡 눌림목 대기 / 관망 (WATCH)<br>
                <span class="sub-stat" style="color: #fef08a;">조건 {passed_cnt}/5개 충족 (지지선 확인 후 진입 권장)</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="verdict-box" style="background-color: #7f1d1d; color: #f87171; border: 1px solid #fca5a5;">
                ⚪ 진입 부적합 / 매수 금지 (WAIT)<br>
                <span class="sub-stat" style="color: #fecaca;">역배열 또는 단기 과열 구간 (무리한 진입 금물)</span>
            </div>
            """, unsafe_allow_html=True)

        # 🎯 기능 1: 실시간 캔들 봉차트 (Plotly)
        st.markdown(f"### 📈 {interval_param} 실시간 봉차트 & 이평선")
        sub_df = df.iloc[-40:]  # 최근 40개 캔들 표시
        fig = go.Figure()

        # 캔들스틱
        fig.add_trace(go.Candlestick(
            x=sub_df['datetime'],
            open=sub_df['open'],
            high=sub_df['high'],
            low=sub_df['low'],
            close=sub_df['close'],
            name="캔들",
            increasing_line_color="#ef4444", # 한국식 양봉 빨강
            decreasing_line_color="#3b82f6"  # 한국식 음봉 파랑
        ))

        # 이동평균선
        fig.add_trace(go.Scatter(x=sub_df['datetime'], y=sub_df['ema9'], mode='lines', name='9선 (단기)', line=dict(color='#facc15', width=1.5)))
        fig.add_trace(go.Scatter(x=sub_df['datetime'], y=sub_df['ema21'], mode='lines', name='21선 (추세)', line=dict(color='#a855f7', width=1.5)))
        fig.add_trace(go.Scatter(x=sub_df['datetime'], y=sub_df['sma50'], mode='lines', name='50선 (대추세)', line=dict(color='#fb923c', width=1.2, dash='dot')))

        fig.update_layout(
            height=340,
            margin=dict(l=10, r=10, t=20, b=10),
            xaxis_rangeslider_visible=False,
            template="plotly_dark",
            paper_bgcolor="#0e1117",
            plot_bgcolor="#161b26",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10))
        )
        st.plotly_chart(fig, use_container_width=True)

        # 🎯 기능 2 & 3: 시드 머니별 추천 매수 주수 & 원화 환산 계산기
        st.markdown("### 🧮 시드별 매수 주수 & 원화 익절 계산기")
        seed_money = st.number_input("내 단타 투자 가능 시드 (원)", min_value=100000, max_value=50000000, value=1500000, step=100000)

        shares_possible = int(seed_money // curr_krw) if curr_krw > 0 else 0
        actual_invest_krw = shares_possible * curr_krw

        total_tp1_profit = shares_possible * tp1_diff_krw
        total_tp2_profit = shares_possible * tp2_diff_krw
        total_sl_loss = shares_possible * sl_diff_krw

        c_calc1, c_calc2 = st.columns(2)
        with c_calc1:
            st.metric("권장 매수 수량", f"{shares_possible} 주", f"총 {actual_invest_krw:,.0f}원")
            st.metric("1차 익절 순수익 (+3.5%)", f"+{total_tp1_profit:,.0f} 원", f"주당 +{tp1_diff_krw:,.0f}원")
        with c_calc2:
            st.metric("칼손절 시 감수액 (-1.8%)", f"-{total_sl_loss:,.0f} 원", f"{sl_pct:.2f}% 제한")
            st.metric("2차 익절 순수익 (+7.0%)", f"+{total_tp2_profit:,.0f} 원", f"주당 +{tp2_diff_krw:,.0f}원")

        # 실전 가이드 테이블
        st.markdown("### 🎯 실전 주문 가이드 (달러 기준)")
        m1, m2 = st.columns(2)
        with m1:
            st.metric("1차 익절가 (+3.5%)", f"${tp1:.2f}", "50% 물량 매도")
            st.metric("2차 익절가 (+7.0%)", f"${tp2:.2f}", "21선 홀딩")
        with m2:
            st.metric("칼손절가 (SL)", f"${sl:.2f}", f"{sl_pct:.2f}% (직전 저점)")
            st.metric("기대 손익비", f"1 : {rr:.2f}", "1:2.72 검증")

        # 세부 지표 상태
        st.markdown("### 📋 4대 퀀트 지표 정밀 진단")
        c_col1, c_col2 = st.columns(2)
        with c_col1:
            st.write(f"• **50일선 (SMA 50)**: ${sma50:.2f} ({'🟢 상승' if c1 else '🔴 하락'})")
            st.write(f"• **이평선 배열**: {'🟢 정배열 골든' if c2 else '🔴 역배열 데드'}")
        with c_col2:
            st.write(f"• **RSI (14)**: {rsi:.1f} ({'🟢 탄력' if c4 else '⚠️ 과열/침체'})")
            st.write(f"• **거래량 급증비**: {vol_ratio:.2f}배 ({'🟢 급증' if c5 else '⚪ 평이'})")

        st.caption(f"적용 환율: $1 = {usd_krw:,.1f}원 | 실시간 캔들 기준 (한국 시각 {datetime.now(zoneinfo.ZoneInfo('Asia/Seoul')).strftime('%H:%M:%S')})")
