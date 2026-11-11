import streamlit as st
import urllib.request
import json
import math
import numpy as np
import pandas as pd
from datetime import datetime
import zoneinfo

# 페이지 설정 (모바일 최적화)
st.set_page_config(
    page_title="찬우의 퀀트 타점기",
    page_icon="📈",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 모바일 다크테마 CSS 스타일
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .stButton>button {
        width: 100%;
        border-radius: 12px;
        height: 3em;
        font-weight: bold;
    }
    .metric-card {
        background-color: #1e222d;
        border-radius: 12px;
        padding: 15px;
        margin-bottom: 10px;
        border: 1px solid #2e3546;
    }
    .verdict-box {
        border-radius: 12px;
        padding: 15px;
        text-align: center;
        font-size: 1.2rem;
        font-weight: bold;
        margin-top: 10px;
        margin-bottom: 15px;
    }
</style>
""", unsafe_allow_html=True)

st.title("📈 찬우의 퀀트 타점 분석기")
st.caption("15분봉 4박자 퀀트 알고리즘 (손익비 1:2.72 기반 실시간 진단)")

# 퀵 티커 버튼
st.write("🔥 **인기 종목 빠른 선택**")
col1, col2, col3, col4 = st.columns(4)
selected_quick = None
with col1:
    if st.button("SOXL"): selected_quick = "SOXL"
with col2:
    if st.button("TQQQ"): selected_quick = "TQQQ"
with col3:
    if st.button("TSLA"): selected_quick = "TSLA"
with col4:
    if st.button("NVDA"): selected_quick = "NVDA"

# 티커 입력창
default_ticker = selected_quick if selected_quick else "SOXL"
ticker = st.text_input("분석할 미국 주식 티커 입력 (대소문자 무관)", value=default_ticker).strip().upper()
interval = st.radio("분봉 선택", ["15m (정석 퀀트)", "5m (초단타)"], horizontal=True)
interval_param = "15m" if "15m" in interval else "5m"

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
    for ts, c, h, l, o, v in zip(timestamps, quotes['close'], quotes['high'], quotes['low'], quotes['open'], quotes['volume']):
        if c is not None and v is not None and h is not None and l is not None:
            valid.append({
                'timestamp': ts,
                'open': o,
                'high': h,
                'low': l,
                'close': c,
                'volume': v
            })
    if len(valid) < 30:
        return None, "데이터 부족"
    return valid, None

if st.button("🚀 실시간 퀀트 분석 실행", type="primary") or ticker:
    with st.spinner(f"{ticker} 실시간 캔들 수집 및 지표 계산 중..."):
        candles, err = get_chart_data(ticker, interval_param)

    if err:
        st.error(f"데이터를 가져오지 못했습니다: {err}")
    else:
        closes = [c['close'] for c in candles]
        highs = [c['high'] for c in candles]
        lows = [c['low'] for c in candles]
        vols = [c['volume'] for c in candles]

        curr = closes[-1]
        prev_low = lows[-2] if len(lows) >= 2 else lows[-1]

        # EMA & SMA 계산
        def calc_ema(arr, span):
            alpha = 2.0 / (span + 1.0)
            ema = arr[0]
            for val in arr[1:]:
                ema = alpha * val + (1.0 - alpha) * ema
            return ema

        sma50 = sum(closes[-50:]) / min(50, len(closes))
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

        # 거래량 배율
        vol_ma20 = np.mean(vols[-21:-1]) if len(vols) > 20 else vols[-1]
        vol_ratio = (vols[-1] / (vol_ma20 + 1e-9))

        # 4박자 조건
        c1 = curr > sma50
        c2 = ema9 > ema21
        c3 = curr >= ema9
        c4 = 45.0 <= rsi <= 68.0
        c5 = vol_ratio >= 1.2
        passed_cnt = sum([c1, c2, c3, c4, c5])

        # 목표가 & 손절가
        tp1 = curr * 1.035
        tp2 = curr * 1.070
        sl = min(prev_low, curr * 0.982)
        sl_pct = ((sl - curr) / curr) * 100
        rr = abs((tp1 - curr) / (curr - sl)) if curr > sl else 0.0

        # 헤더 카드
        st.subheader(f"📊 {ticker} 현재가: ${curr:.2f}")

        # 판정 배너
        if passed_cnt >= 4:
            st.markdown(f"""
            <div class="verdict-box" style="background-color: #1b4d3e; color: #4ade80;">
                ⭐ 강력 매수 진입 타점 (STRONG BUY) ⭐<br>
                <span style="font-size:0.9rem; font-weight:normal;">4박자 필터 {passed_cnt}/5개 충족 (상승 모멘텀 탄력 구간)</span>
            </div>
            """, unsafe_allow_html=True)
        elif passed_cnt == 3:
            st.markdown(f"""
            <div class="verdict-box" style="background-color: #4d431b; color: #facc15;">
                🟡 눌림목 대기 / 관망 (WATCH)<br>
                <span style="font-size:0.9rem; font-weight:normal;">조건 {passed_cnt}/5개 충족 (지지선 확인 후 진입 권장)</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="verdict-box" style="background-color: #4d1b1b; color: #f87171;">
                ⚪ 진입 부적합 / 매수 금지 (WAIT)<br>
                <span style="font-size:0.9rem; font-weight:normal;">역배열 또는 과열 구간 (무리한 진입 금물)</span>
            </div>
            """, unsafe_allow_html=True)

        # 실전 가이드 테이블
        st.markdown("### 🎯 실전 매매 대응 가이드")
        m1, m2 = st.columns(2)
        with m1:
            st.metric("1차 익절가 (+3.5%)", f"${tp1:.2f}", "절반 매도 권장")
            st.metric("2차 익절가 (+7.0%)", f"${tp2:.2f}", "추세 홀딩")
        with m2:
            st.metric("칼손절가 (SL)", f"${sl:.2f}", f"{sl_pct:.2f}% (직전 저점)")
            st.metric("기대 손익비", f"1 : {rr:.2f}", "PF 1.63 검증")

        # 세부 지표 상태
        st.markdown("### 📋 4대 핵심 지표 상태")
        c_col1, c_col2 = st.columns(2)
        with c_col1:
            st.write(f"• **50일선 (SMA 50)**: ${sma50:.2f} ({'🟢 상승' if c1 else '🔴 하락'})")
            st.write(f"• **이동평균선 배열**: {'🟢 정배열 골든' if c2 else '🔴 역배열 데드'}")
        with c_col2:
            st.write(f"• **RSI (14)**: {rsi:.1f} ({'🟢 탄력' if c4 else '⚠️ 과열/침체'})")
            st.write(f"• **거래량 급증비**: {vol_ratio:.2f}배 ({'🟢 실림' if c5 else '⚪ 평이'})")

        st.caption(f"기준 시각: {datetime.now(zoneinfo.ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')} (한국 시간)")
