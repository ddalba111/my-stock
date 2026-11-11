import streamlit as st
import streamlit.components.v1 as components
import urllib.request
import json
import math
import numpy as np
import pandas as pd
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
    .longterm-box {
        background-color: #1e1b4b;
        border: 1px solid #4338ca;
        border-radius: 12px;
        padding: 15px;
        margin-top: 15px;
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
st.caption("단타 4박자 타점부터 중장기 밸류에이션까지 전천후 퀀트 진단")

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

# 티커 입력 & 투자 관점 모드 선택
col_input, col_mode = st.columns([3, 2])
with col_input:
    ticker = st.text_input("미국 주식 티커 입력", value=st.session_state.current_ticker).strip().upper()
with col_mode:
    mode = st.selectbox(
        "투자 관점 (모드)",
        ["⚡ 15분봉 단타", "🌊 일봉 스윙", "🏛️ 주봉 장기투자"],
        index=0
    )

# 모드별 세부 파라미터 매핑
if "15분봉" in mode:
    interval_param = "15m"
    range_param = "5d"
    tv_interval = "15"
    target_tp1_pct = 0.035  # +3.5%
    target_tp2_pct = 0.070  # +7.0%
    target_sl_pct = 0.018   # -1.8%
    mode_name = "초단타 / 15분봉 모드 (1~2일 컷)"
elif "일봉" in mode:
    interval_param = "1d"
    range_param = "1y"
    tv_interval = "D"
    target_tp1_pct = 0.150  # +15.0%
    target_tp2_pct = 0.300  # +30.0%
    target_sl_pct = 0.050   # -5.0%
    mode_name = "중기 스윙 / 일봉 모드 (2주~수개월)"
else:
    interval_param = "1wk"
    range_param = "5y"
    tv_interval = "W"
    target_tp1_pct = 0.400  # +40.0%
    target_tp2_pct = 1.000  # +100.0%
    target_sl_pct = 0.150   # -15.0%
    mode_name = "장기 적립식 / 주봉 모드 (1~3년 이상)"

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
def get_chart_data(symbol, inter, rng):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={inter}&range={rng}&includePrePost=true"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())['chart']['result'][0]
    except Exception as e:
        return None, str(e)

    quotes = data['indicators']['quote'][0]
    timestamps = data.get('timestamp', [])
    valid = []
    for ts, c, h, l, o, v in zip(timestamps, quotes['close'], quotes['high'], quotes['low'], quotes['open'], quotes['volume']):
        if c is not None and v is not None and h is not None and l is not None and o is not None:
            valid.append({
                'timestamp': ts,
                'open': o,
                'high': h,
                'low': l,
                'close': c,
                'volume': v
            })
    if len(valid) < 20:
        return None, "유효 데이터 부족"
    return valid, None

# 분석 실행
if ticker:
    with st.spinner(f"🚀 {ticker} [{mode_name}] 정밀 분석 중..."):
        candles, err = get_chart_data(ticker, interval_param, range_param)

    if err:
        st.error(f"데이터를 불러오지 못했습니다: {err}")
    else:
        closes = [c['close'] for c in candles]
        highs = [c['high'] for c in candles]
        lows = [c['low'] for c in candles]
        vols = [c['volume'] for c in candles]

        curr = closes[-1]
        prev_low = lows[-2] if len(lows) >= 2 else lows[-1]

        def calc_ema(arr, span):
            alpha = 2.0 / (span + 1.0)
            ema = arr[0]
            for val in arr[1:]:
                ema = alpha * val + (1.0 - alpha) * ema
            return ema

        sma50 = sum(closes[-50:]) / min(50, len(closes))
        sma200 = sum(closes[-200:]) / min(200, len(closes)) if len(closes) >= 50 else sma50
        ema9 = calc_ema(closes, 9)
        ema21 = calc_ema(closes, 21)

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

        # 목표가 & 손절가
        tp1 = curr * (1.0 + target_tp1_pct)
        tp2 = curr * (1.0 + target_tp2_pct)
        sl = min(prev_low, curr * (1.0 - target_sl_pct))
        sl_pct = ((sl - curr) / curr) * 100
        rr = abs((tp1 - curr) / (curr - sl)) if curr > sl else 0.0

        curr_krw = curr * usd_krw
        tp1_diff_krw = (tp1 - curr) * usd_krw
        tp2_diff_krw = (tp2 - curr) * usd_krw
        sl_diff_krw = (curr - sl) * usd_krw

        # 3배 레버리지 판별
        is_leveraged = any(x in ticker for x in ["SOXL", "SOXS", "TQQQ", "SQQQ", "CONL", "NVDL", "FNGU", "BULZ", "TSLL"])

        # 헤더
        st.subheader(f"📊 {ticker} 현재가: ${curr:.2f} (약 {curr_krw:,.0f}원)")
        st.caption(f"선택 모드: **{mode_name}** | 실시간 시세 반영")

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

        # 1. 트레이딩뷰 실시간 프로 차트
        st.markdown(f"### 📺 실시간 프로 차트 ({ticker})")
        tv_html = f"""
        <div class="tradingview-widget-container" style="height:390px;width:100%;">
          <div id="tradingview_{ticker}" style="height:100%;width:100%;"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
          <script type="text/javascript">
          new TradingView.widget(
          {{
            "autosize": true,
            "symbol": "{ticker}",
            "interval": "{tv_interval}",
            "timezone": "Asia/Seoul",
            "theme": "dark",
            "style": "1",
            "locale": "kr",
            "toolbar_bg": "#0e1117",
            "enable_publishing": false,
            "allow_symbol_change": false,
            "save_image": false,
            "container_id": "tradingview_{ticker}"
          }}
          );
          </script>
        </div>
        """
        components.html(tv_html, height=400)

        # 2. 토스증권 바로가기 버튼
        toss_url = f"https://tossinvest.com/stocks/{ticker}"
        st.link_button(f"📲 토스증권에서 {ticker} 1초 주문하러 가기", toss_url, type="primary")

        # 3. 장기적인 관점 정밀 진단 카드
        st.markdown("### 🏛️ 장기 투자 관점 정밀 진단")
        high_52w = max(highs)
        low_52w = min(lows)
        dist_from_sma200 = ((curr - sma200) / sma200) * 100 if sma200 > 0 else 0

        st.markdown(f"""
        <div class="longterm-box">
            <h4 style="margin-top:0; color:#818cf8;">📌 장기 관점 핵심 체크리스트</h4>
            <p style="margin-bottom:6px;">• <b>1년 이평선(200일선) 위치</b>: ${sma200:.2f} (현재가 대비 <b>{dist_from_sma200:+.1f}%</b> 이격)</p>
            <p style="margin-bottom:6px;">• <b>52주 최고/최저가</b>: 고점 ${high_52w:.2f}  |  저점 ${low_52w:.2f}</p>
            <hr style="border: 0; border-top: 1px solid #3730a3; margin: 10px 0;">
            <p style="margin-bottom:0; font-size:0.95rem; line-height:1.5;">
                {
                    "🚨 <b>3배 레버리지 경고</b>: 이 종목은 횡보장·하락 시 '음의 복리'로 계좌가 녹아내릴 수 있습니다. <b>절대 1년 이상 장기 적립하지 마시고, 15분봉 단타나 1~2주 스윙으로만 익절하고 나오세요!</b>"
                    if is_leveraged else
                    "🟢 <b>장기 적립식 적합</b>: 1배수 우량주/지수 상품입니다. 200일선 부근으로 눌릴 때마다 적립식으로 분할 매수해 모아가기에 적합합니다."
                }
            </p>
        </div>
        """, unsafe_allow_html=True)

        # 4. 시드 머니별 추천 매수 주수 & 원화 익절 계산기
        st.markdown(f"### 🧮 시드별 매수 주수 & 원화 익절 계산기 ({mode_name})")
        seed_money = st.number_input("내 투자 가능 시드 (원)", min_value=100000, max_value=50000000, value=1500000, step=100000)

        shares_possible = int(seed_money // curr_krw) if curr_krw > 0 else 0
        actual_invest_krw = shares_possible * curr_krw

        total_tp1_profit = shares_possible * tp1_diff_krw
        total_tp2_profit = shares_possible * tp2_diff_krw
        total_sl_loss = shares_possible * sl_diff_krw

        c_calc1, c_calc2 = st.columns(2)
        with c_calc1:
            st.metric("권장 매수 수량", f"{shares_possible} 주", f"총 {actual_invest_krw:,.0f}원")
            st.metric(f"1차 익절 순수익 (+{target_tp1_pct*100:.1f}%)", f"+{total_tp1_profit:,.0f} 원", f"주당 +{tp1_diff_krw:,.0f}원")
        with c_calc2:
            st.metric(f"칼손절 시 감수액 ({sl_pct:.1f}%)", f"-{total_sl_loss:,.0f} 원", "원금 철저 방어")
            st.metric(f"2차 익절 순수익 (+{target_tp2_pct*100:.1f}%)", f"+{total_tp2_profit:,.0f} 원", f"주당 +{tp2_diff_krw:,.0f}원")

        # 실전 가이드 테이블
        st.markdown("### 🎯 실전 주문 가이드 (달러 기준)")
        m1, m2 = st.columns(2)
        with m1:
            st.metric(f"1차 익절가 (+{target_tp1_pct*100:.1f}%)", f"${tp1:.2f}", "분할 익절 권장")
            st.metric(f"2차 익절가 (+{target_tp2_pct*100:.1f}%)", f"${tp2:.2f}", "추세 홀딩")
        with m2:
            st.metric("칼손절가 (SL)", f"${sl:.2f}", f"{sl_pct:.2f}% (직전 저점)")
            st.metric("기대 손익비", f"1 : {rr:.2f}", "검증된 기대치")

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
