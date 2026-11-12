import streamlit as st
import streamlit.components.v1 as components
import urllib.request
import json
import math
import os
import numpy as np
import pandas as pd
from datetime import datetime
import zoneinfo

# 페이지 기본 설정 (모바일 최적화)
st.set_page_config(
    page_title="퀀트 분석기 & 내 잔고",
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
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 44px;
        white-space: pre-wrap;
        background-color: #1a1e29;
        border-radius: 8px 8px 0px 0px;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
        font-weight: bold;
    }
    .stTabs [aria-selected="true"] {
        background-color: #3b82f6 !important;
        color: white !important;
    }
</style>
""", unsafe_allow_html=True)

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

# 시장 상태 판별 함수 (한국 시간 기준)
def get_market_status():
    now_kst = datetime.now(zoneinfo.ZoneInfo("Asia/Seoul"))
    h = now_kst.hour
    m = now_kst.minute
    total_m = h * 60 + m
    if total_m >= 23 * 60 + 30 or total_m < 6 * 60:
        return "🟢 정규장 실시간"
    elif 6 * 60 <= total_m < 10 * 60:
        return "🌙 애프터마켓 실시간"
    elif 10 * 60 <= total_m < 18 * 60:
        return "⏸️ 미국 증시 휴장"
    else:
        return "🌅 프리마켓 실시간"

# 실시간 단일 주가 조회 함수 (프리마켓/정규장/애프터마켓 전구간 실시간 반영)
@st.cache_data(ttl=15)
def get_live_price(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=15m&range=1d&includePrePost=true"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())['chart']['result'][0]
        meta = data.get('meta', {})
        quotes = data['indicators']['quote'][0]
        c = [x for x in quotes['close'] if x is not None]
        if c:
            return float(c[-1])
        reg = meta.get('regularMarketPrice')
        if reg:
            return float(reg)
        return 0.0
    except Exception:
        return 0.0

# 장기 통계 조회 함수 (1년치 일봉 기준 실제 200일선 및 52주 고저가)
@st.cache_data(ttl=3600)
def get_daily_stats(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1y"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())['chart']['result'][0]
        q = data['indicators']['quote'][0]
        c = [x for x in q['close'] if x is not None]
        h = [x for x in q['high'] if x is not None]
        l = [x for x in q['low'] if x is not None]
        sma_val = sum(c[-200:]) / min(200, len(c)) if c else 0.0
        h_val = max(h) if h else 0.0
        l_val = min(l) if l else 0.0
        return sma_val, h_val, l_val
    except Exception:
        return 0.0, 0.0, 0.0

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

def calc_ema(arr, span):
    if not arr:
        return 0.0
    alpha = 2.0 / (span + 1.0)
    ema = arr[0]
    for val in arr[1:]:
        ema = alpha * val + (1.0 - alpha) * ema
    return ema

@st.cache_data(ttl=60)
def scan_radar_opportunities():
    radar_symbols = ["SOXL", "TQQQ", "TSLA", "NVDA", "AAPL", "AMD", "PLTR", "CONL"]
    hits = []
    for s in radar_symbols:
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?interval=15m&range=5d&includePrePost=true"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())['chart']['result'][0]
            q = data['indicators']['quote'][0]
            c = [x for x in q['close'] if x is not None]
            if len(c) < 30: continue
            cur_p = c[-1]
            s50 = sum(c[-50:]) / min(50, len(c))
            e9 = calc_ema(c, 9)
            e21 = calc_ema(c, 21)
            deltas = np.diff(c)
            gains = np.where(deltas > 0, deltas, 0.0)
            losses = np.where(deltas < 0, -deltas, 0.0)
            ag = np.mean(gains[-14:])
            al = np.mean(losses[-14:])
            rs_val = ag / (al + 1e-9)
            r_val = 100.0 - (100.0 / (1.0 + rs_val))
            c1 = cur_p > s50
            c2 = e9 > e21
            c3 = cur_p >= e9
            c4 = 48.0 <= r_val <= 65.0
            if sum([c1, c2, c3, c4]) >= 4:
                hits.append({"symbol": s, "price": cur_p, "rsi": r_val})
        except Exception:
            pass
    return hits

@st.cache_data(ttl=300)
def get_fear_and_greed():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Referer': 'https://www.cnn.com/markets/fear-and-greed',
        'Origin': 'https://www.cnn.com'
    }
    try:
        url = 'https://production.dataviz.cnn.io/index/fearandgreed/graphdata'
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=4) as r:
            d = json.loads(r.read().decode())
            score = round(d['fear_and_greed']['score'], 1)
            rating = d['fear_and_greed']['rating'].lower()
            if "extreme fear" in rating:
                return score, "😱 극단적 공포 (바닥 매수 찬스)", "#60a5fa", "#1e3a8a"
            elif "fear" in rating:
                return score, "😨 공포 (시장 위축 구간)", "#93c5fd", "#1e293b"
            elif "neutral" in rating:
                return score, "😐 중립 (관망 구간)", "#facc15", "#713f12"
            elif "extreme greed" in rating:
                return score, "🔥 극단적 탐욕 (고점 과열 경보)", "#f87171", "#7f1d1d"
            else:
                return score, "🤑 탐욕 (상승 모멘텀)", "#4ade80", "#14532d"
    except Exception:
        pass
    return 38.0, "😨 공포 (시장 위축 구간)", "#93c5fd", "#1e293b"

PORTFOLIO_FILE = "portfolio.json"
JOURNAL_FILE = "trade_journal.json"

def load_journal():
    if os.path.exists(JOURNAL_FILE):
        try:
            with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                if isinstance(d, list):
                    return d
        except Exception:
            pass
    return []

def save_journal(data):
    try:
        with open(JOURNAL_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def parse_portfolio_from_params():
    try:
        if hasattr(st, "query_params") and "p" in st.query_params:
            p_val = st.query_params["p"]
            d = {}
            for item in p_val.split("_"):
                parts = item.split(":")
                if len(parts) == 3:
                    sym, sh, avg = parts[0].upper(), int(parts[1]), float(parts[2])
                    if sh > 0:
                        d[sym] = {"shares": sh, "avg_price": avg}
            if d:
                return d
    except Exception:
        pass
    return None

def sync_portfolio_to_params(data):
    try:
        items = []
        for s, inf in data.items():
            sh = inf.get("shares", 0)
            avg = inf.get("avg_price", 0.0)
            if sh > 0:
                items.append(f"{s}:{sh}:{avg}")
        if hasattr(st, "query_params"):
            if items:
                st.query_params["p"] = "_".join(items)
            elif "p" in st.query_params:
                del st.query_params["p"]
    except Exception:
        pass

def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                if isinstance(d, dict):
                    if len(d) == 0:
                        if hasattr(st, "query_params") and "p" in st.query_params:
                            del st.query_params["p"]
                        return {}
                    return d
        except Exception:
            pass
    return {}

def save_portfolio(data):
    try:
        with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    sync_portfolio_to_params(data)

def set_active_ticker(sym):
    st.session_state["main_ticker_input"] = sym
    st.session_state.current_ticker = sym

# 세션 상태 초기화 (영구 파일에서 로드)
if "my_portfolio" not in st.session_state:
    st.session_state.my_portfolio = load_portfolio()

if "current_ticker" not in st.session_state:
    st.session_state.current_ticker = "SOXL"

if "main_ticker_input" not in st.session_state:
    st.session_state.main_ticker_input = "SOXL"

# 1. 메인 타이틀 & 새로고침 버튼 (슬림 헤더)
col_title, col_ref = st.columns([3, 2])
with col_title:
    st.title("📈 퀀트 분석기")
with col_ref:
    st.write("")
    if st.button("🔄 새로고침", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.session_state.my_portfolio = load_portfolio()
        st.rerun()

now_kr_str = datetime.now(zoneinfo.ZoneInfo("Asia/Seoul")).strftime("%H:%M:%S")

# ==============================================================================
# 🔥 [상시 고정] 스마트 올인원 상태 대시보드
# ==============================================================================
total_invest_usd = 0.0
total_curr_usd = 0.0
portfolio_items = []

for sym, info in st.session_state.my_portfolio.items():
    sh = info.get("shares", 0)
    avg = info.get("avg_price", 0.0)
    if sh > 0 and avg > 0:
        lp = get_live_price(sym)
        if lp == 0.0:
            lp = avg
        inv = sh * avg
        cur = sh * lp
        diff = cur - inv
        diff_pct = (diff / inv) * 100 if inv > 0 else 0
        total_invest_usd += inv
        total_curr_usd += cur
        portfolio_items.append({
            "symbol": sym,
            "shares": sh,
            "avg_price": avg,
            "live_price": lp,
            "invested_usd": inv,
            "current_usd": cur,
            "pnl_usd": diff,
            "pnl_pct": diff_pct
        })

total_pnl_usd = total_curr_usd - total_invest_usd
total_pnl_krw = total_pnl_usd * usd_krw
total_pnl_pct = (total_pnl_usd / total_invest_usd) * 100 if total_invest_usd > 0 else 0
is_total_profit = total_pnl_usd >= 0
bar_color = "#4ade80" if is_total_profit else "#f87171"
bar_bg = "#134e4a" if is_total_profit else "#7f1d1d"
bar_border = "#2dd4bf" if is_total_profit else "#f87171"
bar_sign = "+" if is_total_profit else ""

fg_score, fg_label, fg_color, fg_bg = get_fear_and_greed()
radar_hits = scan_radar_opportunities()
market_badge = get_market_status()

if portfolio_items:
    item_summaries = " · ".join([f"<b>{item['symbol']}</b> {item['shares']}주 (${item['live_price']:.2f})" for item in portfolio_items])
    top_bar_html = (
        f'<div style="background-color: {bar_bg}; border: 1px solid {bar_border}; border-radius: 12px; padding: 12px 16px; margin-bottom: 8px;">'
        f'<div style="display:flex; justify-content:space-between; align-items:center;">'
        f'<span style="font-size:0.95rem; font-weight:bold; color:#e2e8f0;">💼 실시간 총 손익</span>'
        f'<span style="font-size:1.25rem; font-weight:800; color:{bar_color};">{bar_sign}${total_pnl_usd:.2f} ({bar_sign}{total_pnl_pct:.2f}%)</span>'
        f'</div>'
        f'<div style="display:flex; justify-content:space-between; align-items:center; margin-top:2px;">'
        f'<span style="font-size:0.85rem; color:#cbd5e1;">{item_summaries}</span>'
        f'<span style="font-size:1.15rem; font-weight:800; color:{bar_color};">{bar_sign}{total_pnl_krw:,.0f} 원</span>'
        f'</div>'
        f'<hr style="border: 0; border-top: 1px solid rgba(255,255,255,0.12); margin: 8px 0 6px 0;">'
        f'<div style="display:flex; justify-content:space-between; align-items:center; font-size:0.8rem; color:#cbd5e1;">'
        f'<span>🧠 월가 심리: <b style="color:{fg_color};">{fg_score:.0f}점 {fg_label.split()[1] if len(fg_label.split())>1 else ""}</b></span>'
        f'<span>{market_badge}</span>'
        f'<span>📡 타점: <b>{"🚨 포착!" if radar_hits else "안전 관망"}</b></span>'
        f'</div>'
        f'</div>'
    )
    st.markdown(top_bar_html, unsafe_allow_html=True)
else:
    no_port_html = (
        f'<div style="background-color: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 12px 16px; margin-bottom: 8px;">'
        f'<div style="display:flex; justify-content:space-between; align-items:center;">'
        f'<span style="font-size:0.9rem; color:#94a3b8;">💼 등록된 보유 주식 없음</span>'
        f'<span style="font-size:0.8rem; color:#cbd5e1;">{market_badge} · 🧠 심리: <b style="color:{fg_color};">{fg_score:.0f}점</b></span>'
        f'</div>'
        f'</div>'
    )
    st.markdown(no_port_html, unsafe_allow_html=True)

# 🚦 내 보유 종목 실시간 신호등 바 (모바일 네이티브 스타일)
if portfolio_items:
    cards_html = []
    for item in portfolio_items:
        sym = item["symbol"]
        pct = item["pnl_pct"]
        lp = item["live_price"]

        if pct >= 3.5:
            light = "🟢"
            status_text = "익절 권장"
            status_color = "#4ade80"
        elif pct >= 0:
            light = "🟢"
            status_text = "홀딩 순항"
            status_color = "#38bdf8"
        elif pct >= -1.5:
            light = "🟡"
            status_text = "관망 지지"
            status_color = "#facc15"
        else:
            light = "🔴"
            status_text = "손절 주의"
            status_color = "#f87171"

        sign = "+" if pct >= 0 else ""
        card_item = (
            f'<div style="flex:1; min-width:70px; background-color:#1e293b; border-radius:8px; padding:8px 4px; text-align:center; border:1px solid rgba(255,255,255,0.08);">'
            f'<div style="font-size:0.8rem; font-weight:bold; color:white;">{light} {sym}</div>'
            f'<div style="font-size:0.95rem; font-weight:800; color:{status_color}; margin:2px 0;">{sign}{pct:.1f}%</div>'
            f'<div style="font-size:0.7rem; color:#94a3b8;">{status_text}</div>'
            f'</div>'
        )
        cards_html.append(card_item)

    all_cards = "".join(cards_html)
    st.markdown(
        f'<div style="background-color: #0f172a; border: 1px solid #1e293b; border-radius: 12px; padding: 10px 12px; margin-bottom: 8px;">'
        f'<div style="font-size:0.8rem; font-weight:bold; color:#94a3b8; margin-bottom:6px;">🚦 내 보유 종목 실시간 신호등</div>'
        f'<div style="display:flex; gap:6px; justify-content:space-between; overflow-x:auto;">'
        f'{all_cards}'
        f'</div></div>',
        unsafe_allow_html=True
    )

# 레이더 타점 포착 시에만 특별 배너 표시
if radar_hits:
    hit_texts = " · ".join([f"<b>{h['symbol']}</b> (${h['price']:.2f})" for h in radar_hits])
    st.markdown(f"""
    <div style="background-color: #14532d; border: 1.5px solid #22c55e; border-radius: 10px; padding: 10px 14px; margin-bottom: 8px;">
        <span style="font-size:0.95rem; font-weight:800; color:#86efac;">🚨 [실시간 타점 포착] 매수 유력: {hit_texts}</span>
    </div>
    """, unsafe_allow_html=True)

# 실시간 익절/손절 도달 알림 (조건 부합 시에만 슬림하게 1줄 표시)
for item in portfolio_items:
    i_sym = item['symbol']
    i_pct = item['pnl_pct']
    i_pnl_krw = item['pnl_usd'] * usd_krw
    i_live = item['live_price']
    if i_pct >= 7.0:
        st.markdown(f"""
        <div style="background-color: #064e3b; border: 1.5px solid #10b981; border-radius: 10px; padding: 8px 14px; margin-bottom: 8px;">
            <span style="font-size:0.9rem; font-weight:800; color:#6ee7b7;">🎉 [익절 도달] {i_sym} 2차 목표(+7%) 돌파! (${i_live:.2f}, +{i_pnl_krw:,.0f}원) — 전량/분할 익절 권장!</span>
        </div>
        """, unsafe_allow_html=True)
    elif i_pct >= 3.5:
        st.markdown(f"""
        <div style="background-color: #1e3a8a; border: 1.5px solid #3b82f6; border-radius: 10px; padding: 8px 14px; margin-bottom: 8px;">
            <span style="font-size:0.9rem; font-weight:800; color:#93c5fd;">🎯 [익절 도달] {i_sym} 1차 목표(+3.5%) 도달! (${i_live:.2f}, +{i_pnl_krw:,.0f}원) — 50% 분할 매도 권장!</span>
        </div>
        """, unsafe_allow_html=True)
    elif i_pct <= -1.8:
        st.markdown(f"""
        <div style="background-color: #7f1d1d; border: 1.5px solid #ef4444; border-radius: 10px; padding: 8px 14px; margin-bottom: 8px;">
            <span style="font-size:0.9rem; font-weight:800; color:#fca5a5;">⚠️ [손절 경고] {i_sym} 손절선(-1.8%) 이탈! (${i_live:.2f}) — 칼손절 권장!</span>
        </div>
        """, unsafe_allow_html=True)

# ==============================================================================
# 2대 메인 탭 분리: [1. 💼 내 보유 잔고 전용 화면] vs [2. 📈 종목별 퀀트 타점 분석]
# ==============================================================================
tab_portfolio, tab_analysis = st.tabs(["💼 내 보유 주식만 보기", "📈 종목별 퀀트 타점 분석"])

# ------------------------------------------------------------------------------
# TAB 1: 내 보유 주식만 따로 보는 전용 화면 (토스증권 스타일 슈퍼 미니멀)
# ------------------------------------------------------------------------------
with tab_portfolio:
    if portfolio_items:
        # 1. 상단 총 자산 요약 (심플 1줄 카드)
        tot_krw_invest = total_invest_usd * usd_krw
        tot_krw_curr = total_curr_usd * usd_krw
        tot_color = "#4ade80" if total_pnl_usd >= 0 else "#f87171"
        
        st.markdown(f"""
        <div style="background-color: #1a1e29; border: 1px solid #2a3142; border-radius: 12px; padding: 14px 18px; margin-bottom: 12px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:0.95rem; font-weight:bold; color:#cbd5e1;">💼 총 평가 자산</span>
                <span style="font-size:1.3rem; font-weight:900; color:white;">${total_curr_usd:,.2f} <span style="font-size:0.95rem; font-weight:normal; color:#94a3b8;">({tot_krw_curr:,.0f}원)</span></span>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center; margin-top:8px; border-top: 1px solid rgba(255,255,255,0.08); padding-top:8px;">
                <span style="font-size:0.85rem; color:#94a3b8;">총 평가 손익</span>
                <span style="font-size:1.15rem; font-weight:800; color:{tot_color};">{bar_sign}${total_pnl_usd:.2f} ({bar_sign}{total_pnl_pct:.2f}%, {bar_sign}{total_pnl_krw:,.0f}원)</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # 2. 토스증권 스타일 종목별 미니멀 카드 (군더더기 1도 없이 딱 종목 정보만!)
        for item in portfolio_items:
            s_sym = item["symbol"]
            s_shares = item["shares"]
            s_avg = item["avg_price"]
            s_live = item["live_price"]
            s_pnl = item["pnl_usd"]
            s_pct = item["pnl_pct"]
            s_krw = s_pnl * usd_krw
            s_is_profit = s_pnl >= 0
            s_color = "#4ade80" if s_is_profit else "#f87171"
            s_sign = "+" if s_is_profit else ""

            st.markdown(f"""
            <div style="background-color: #131722; border: 1px solid #232738; border-radius: 12px; padding: 14px 16px; margin-bottom: 8px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-size:1.15rem; font-weight:800; color:white;">🔥 {s_sym} <span style="font-size:0.9rem; font-weight:normal; color:#94a3b8;">{s_shares}주</span></span>
                    <span style="font-size:1.15rem; font-weight:800; color:{s_color};">{s_sign}${s_pnl:.2f} ({s_sign}{s_pct:.2f}%)</span>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center; margin-top:4px;">
                    <span style="font-size:0.85rem; color:#64748b;">평단 ${s_avg:.2f} → 현재가 <b>${s_live:.2f}</b></span>
                    <span style="font-size:1.0rem; font-weight:700; color:{s_color};">{s_sign}{s_krw:,.0f} 원</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="background-color: #1a1e29; border: 1.5px dashed #334155; border-radius: 12px; padding: 24px; text-align: center; margin-bottom: 12px;">
            <span style="font-size:1.1rem; font-weight:bold; color:#cbd5e1;">현재 등록된 보유 종목이 없습니다 (0종목).</span><br>
            <span style="font-size:0.85rem; color:#64748b;">종목 데이터가 깨끗하게 비워진 상태입니다.</span>
        </div>
        """, unsafe_allow_html=True)

    # 3. ⚙️ [수량 & 평단가 편집 / 종목 추가]
    st.markdown("---")
    with st.expander("⚙️ 보유 종목 편집 및 새 종목 추가", expanded=(not bool(portfolio_items))):
        if st.session_state.my_portfolio:
            st.caption("수정할 종목의 수량이나 평단가를 고친 뒤 아래 [저장하기]를 누르세요.")
            updated_p = {}
            for s_sym, s_inf in st.session_state.my_portfolio.items():
                c_l, c_s, c_p = st.columns([1.5, 2, 2])
                with c_l:
                    st.markdown(f"<div style='font-size:1.0rem; font-weight:bold; color:white; padding-top:6px;'>🔥 {s_sym}</div>", unsafe_allow_html=True)
                with c_s:
                    n_s = st.number_input(f"{s_sym} 수량", min_value=0, value=s_inf.get("shares", 0), step=1, key=f"ed_s_{s_sym}")
                with c_p:
                    n_p = st.number_input(f"{s_sym} 평단($)", min_value=0.01, value=float(s_inf.get("avg_price", 0.0)), step=0.1, format="%.2f", key=f"ed_p_{s_sym}")
                
                if n_s > 0:
                    updated_p[s_sym] = {"shares": int(n_s), "avg_price": round(float(n_p), 2)}

            col_sv, col_rst, col_clr = st.columns([1.5, 1.2, 1.2])
            with col_sv:
                if st.button("💾 저장하기", type="primary", use_container_width=True, key="save_port_btn"):
                    st.session_state.my_portfolio = updated_p
                    save_portfolio(updated_p)
                    st.success("저장되었습니다!")
                    st.rerun()
            with col_rst:
                if st.button("🔄 토스 원본 복원", use_container_width=True, key="rst_btn"):
                    default_data = {
                        "SOXL": {"shares": 20, "avg_price": 66.10},
                        "TQQQ": {"shares": 15, "avg_price": 60.03},
                        "TSLA": {"shares": 1, "avg_price": 393.02},
                        "NVDA": {"shares": 2, "avg_price": 174.93}
                    }
                    st.session_state.my_portfolio = default_data
                    save_portfolio(default_data)
                    st.rerun()
            with col_clr:
                if st.button("🗑️ 전체 비우기", use_container_width=True, key="clr_btn"):
                    st.session_state.my_portfolio = {}
                    save_portfolio({})
                    st.rerun()
        else:
            if st.button("🔄 토스 계좌 원본 불러오기 (20주/15주)", type="primary", use_container_width=True, key="restore_toss_btn"):
                default_data = {
                    "SOXL": {"shares": 20, "avg_price": 66.10},
                    "TQQQ": {"shares": 15, "avg_price": 60.03},
                    "TSLA": {"shares": 1, "avg_price": 393.02},
                    "NVDA": {"shares": 2, "avg_price": 174.93}
                }
                st.session_state.my_portfolio = default_data
                save_portfolio(default_data)
                st.rerun()

        st.markdown("---")
        st.markdown("##### ➕ 새 종목 추가")
        q_c = st.columns(6)
        for idx, pt in enumerate(["SOXL", "TQQQ", "TSLA", "NVDA", "NVDL", "CONL"]):
            with q_c[idx]:
                if st.button(pt, key=f"add_p_{pt}", use_container_width=True):
                    st.session_state["add_p_sym"] = pt
        
        init_new = st.session_state.get("add_p_sym", "")
        c_n1, c_n2, c_n3, c_n4 = st.columns([1.5, 1.5, 1.5, 1.5])
        with c_n1:
            add_sym = st.text_input("티커", value=init_new, key="add_p_input").strip().upper()
        with c_n2:
            add_sh = st.number_input("수량", min_value=1, value=1, step=1)
        with c_n3:
            add_pr = st.number_input("평단가($)", min_value=0.01, value=50.0, step=0.1, format="%.2f")
        with c_n4:
            st.write("")
            st.write("")
            if st.button("추가", use_container_width=True):
                if add_sym:
                    st.session_state.my_portfolio[add_sym] = {"shares": int(add_sh), "avg_price": round(float(add_pr), 2)}
                    save_portfolio(st.session_state.my_portfolio)
                    st.rerun()

    # --------------------------------------------------------------------------
    # 하단: 시드 퀘스트 & 장부 (접어두기)
    # --------------------------------------------------------------------------
    st.markdown("---")
    with st.expander("🎮 1,000만 원 복리 퀘스트 & 매매 장부", expanded=False):
        journal_entries = load_journal()
        tot_realized_krw = sum(x.get("profit_krw", 0) for x in journal_entries)
        win_trades = len([x for x in journal_entries if x.get("profit_krw", 0) > 0])
        base_seed = 5000000
        target_seed = 10000000
        current_asset = base_seed + tot_realized_krw
        progress_val = min(1.0, max(0.0, tot_realized_krw / (target_seed - base_seed)))
        progress_pct = progress_val * 100
        trades_left = max(0, 20 - win_trades)
        remaining_krw = max(0, target_seed - current_asset)
        level_num = min(20, win_trades)
        sign_real = "+" if tot_realized_krw >= 0 else ""

        st.markdown(f"""
        <div style="background-color: #1e1b4b; border: 1px solid #6366f1; border-radius: 10px; padding: 12px; margin-bottom: 10px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-weight:bold; color:#c7d2fe;">🏆 LEVEL {level_num} ({progress_pct:.1f}%)</span>
                <span style="font-size:0.85rem; color:#a5b4fc;">남은 익절: {trades_left}회</span>
            </div>
            <div style="margin: 6px 0;">
                <div style="background-color: #312e81; border-radius: 6px; height: 10px; overflow: hidden;">
                    <div style="background: linear-gradient(90deg, #6366f1, #a855f7); width: {max(5, int(progress_pct))}%; height: 100%;"></div>
                </div>
            </div>
            <div style="font-size:0.8rem; color:#e0e7ff;">현재 누적 수익: <b>{sign_real}{tot_realized_krw:,.0f}원</b></div>
        </div>
        """, unsafe_allow_html=True)

        if journal_entries:
            for idx, j in enumerate(journal_entries):
                p_c = "#4ade80" if j.get("profit_krw", 0) >= 0 else "#f87171"
                p_s = "+" if j.get("profit_krw", 0) >= 0 else ""
                st.markdown(f"""
                <div style="background-color: #0f172a; border-radius: 6px; padding: 6px 10px; margin-bottom: 4px; display:flex; justify-content:space-between; font-size:0.85rem;">
                    <span style="color:white;">{j.get("symbol")} ({j.get("shares")}주 @ ${j.get("sell_price"):.2f})</span>
                    <span style="font-weight:bold; color:{p_c};">{p_s}{j.get("profit_krw"):,.0f}원</span>
                </div>
                """, unsafe_allow_html=True)
            if st.button("⚠️ 장부 기록 전체 삭제", type="secondary"):
                save_journal([])
                st.rerun()
        else:
            st.caption("아직 기록된 매매 일지가 없습니다.")

# ------------------------------------------------------------------------------
# TAB 2: 종목별 퀀트 타점 분석기
# ------------------------------------------------------------------------------
with tab_analysis:
    st.write("💼 **내 보유 종목 빠른 선택**")
    active_stocks = [s for s, inf in st.session_state.my_portfolio.items() if inf.get("shares", 0) > 0]

    if active_stocks:
        cols = st.columns(min(len(active_stocks), 4))
        for idx, s_ticker in enumerate(active_stocks):
            col = cols[idx % len(cols)]
            with col:
                sh_count = st.session_state.my_portfolio[s_ticker].get("shares", 0)
                st.button(
                    f"🔥 {s_ticker} ({sh_count}주)",
                    key=f"btn_my_{s_ticker}",
                    on_click=set_active_ticker,
                    args=(s_ticker,),
                    use_container_width=True
                )
    else:
        st.info("💡 등록된 보유 종목이 없습니다. '💼 내 보유 주식만 보기' 탭에서 종목을 등록하시면 여기에 빠른 분석 버튼이 생성됩니다!")

    col_input, col_mode = st.columns([3, 2])
    with col_input:
        ticker = st.text_input("미국 주식 티커 입력", key="main_ticker_input").strip().upper()
    with col_mode:
        mode = st.selectbox(
            "투자 관점 (모드)",
            ["⚡ 15분봉 단타", "🌊 일봉 스윙", "🏛️ 주봉 장기투자"],
            index=0,
            key="analysis_mode"
        )

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

            # 실시간 미완성 봉의 거래량이 0이면 직전 완성봉 참조
            target_vol = vols[-1] if (vols and vols[-1] > 0) else (vols[-2] if len(vols) >= 2 else 0)
            past_vols = [v for v in vols[-22:-1] if v > 0] if len(vols) >= 2 else [target_vol]
            vol_base = float(np.median(past_vols)) if past_vols else float(target_vol)
            vol_ratio = float(target_vol / (vol_base + 1e-9)) if vol_base > 0 else 1.0

            c1 = curr > sma50
            c2 = ema9 > ema21
            c3 = curr >= ema9
            c4 = 45.0 <= rsi <= 68.0
            c5 = vol_ratio >= 1.2
            passed_cnt = sum([c1, c2, c3, c4, c5])

            tp1 = curr * (1.0 + target_tp1_pct)
            tp2 = curr * (1.0 + target_tp2_pct)
            sl = min(prev_low, curr * (1.0 - target_sl_pct))
            sl_pct = ((sl - curr) / curr) * 100
            rr = abs((tp1 - curr) / (curr - sl)) if curr > sl else 0.0

            curr_krw = curr * usd_krw
            tp1_diff_krw = (tp1 - curr) * usd_krw
            tp2_diff_krw = (tp2 - curr) * usd_krw
            sl_diff_krw = (curr - sl) * usd_krw

            is_leveraged = any(x in ticker for x in ["SOXL", "SOXS", "TQQQ", "SQQQ", "CONL", "NVDL", "FNGU", "BULZ", "TSLL"])

            st.subheader(f"📊 {ticker} 현재가: ${curr:.2f} (약 {curr_krw:,.0f}원)")
            st.caption(f"선택 모드: **{mode_name}** | 실시간 시세 반영")

            # 1. 🎯 타점 판정 & 매수 권장가 통합 카드
            if passed_cnt >= 4:
                v_title = "⭐ 강력 매수 타점 (STRONG BUY)"
                v_color = "#4ade80"
                v_bg = "#134e4a"
                v_border = "#2dd4bf"
                v_sub = f"4박자 필터 {passed_cnt}/5개 충족 (상승 모멘텀 탄력)"
            elif passed_cnt == 3:
                v_title = "🟡 눌림목 대기 / 관망 (WATCH)"
                v_color = "#facc15"
                v_bg = "#713f12"
                v_border = "#fde047"
                v_sub = f"조건 {passed_cnt}/5개 충족 (지지선 확인 후 진입)"
            else:
                v_title = "⚪ 진입 부적합 / 대기 (WAIT)"
                v_color = "#f87171"
                v_bg = "#7f1d1d"
                v_border = "#fca5a5"
                v_sub = "역배열 또는 단기 과열 구간 (무리한 진입 금물)"

            buy_rec_low = min(curr, ema9)
            buy_rec_high = max(curr, ema9)
            buy_rec_krw = curr * usd_krw

            st.markdown(f"""
            <div style="background-color: {v_bg}; border: 1.5px solid {v_border}; border-radius: 12px; padding: 12px 16px; margin-bottom: 10px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-size:1.05rem; font-weight:800; color:{v_color};">{v_title}</span>
                    <span style="font-size:0.8rem; color:#e2e8f0;">{v_sub}</span>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center; margin-top:8px; border-top:1px solid rgba(255,255,255,0.15); padding-top:6px;">
                    <span style="font-size:0.85rem; color:#cbd5e1;">🎯 매수 권장가 (9선 지지)</span>
                    <span style="font-size:1.15rem; font-weight:800; color:#38bdf8;">${buy_rec_low:.2f} ~ ${buy_rec_high:.2f} <span style="font-size:0.85rem; color:#cbd5e1;">(약 {buy_rec_krw:,.0f}원)</span></span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # 2. 실전 주문 목표가
            m1, m2 = st.columns(2)
            with m1:
                st.metric(f"1차 익절가 (+{target_tp1_pct*100:.1f}%)", f"${tp1:.2f}", f"약 {tp1*usd_krw:,.0f}원")
                st.metric(f"2차 익절가 (+{target_tp2_pct*100:.1f}%)", f"${tp2:.2f}", f"약 {tp2*usd_krw:,.0f}원")
            with m2:
                st.metric("칼손절가 (SL)", f"${sl:.2f}", f"{sl_pct:.2f}% (직전 저점)")
                st.metric("기대 손익비", f"1 : {rr:.2f}", "검증된 기대치")

            # 3. 트레이딩뷰 프로 차트
            st.markdown(f"### 📺 실시간 차트 ({ticker})")
            tv_html = f"""
            <div class="tradingview-widget-container" style="height:400px;width:100%;">
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
                "hide_top_toolbar": false,
                "hide_legend": false,
                "save_image": false,
                "studies": [
                  "MASimple@tv-basicstudies",
                  "RSI@tv-basicstudies"
                ],
                "container_id": "tradingview_{ticker}"
              }}
              );
              </script>
            </div>
            """
            components.html(tv_html, height=410)

            # 4. 세부 지표 상태
            st.markdown("### 📋 4대 퀀트 지표 정밀 진단")
            c_col1, c_col2 = st.columns(2)
            with c_col1:
                st.write(f"• **50일선**: ${sma50:.2f} ({'🟢 상승' if c1 else '🔴 하락'})")
                st.write(f"• **이평배열**: {'🟢 정배열' if c2 else '🔴 역배열'}")
            with c_col2:
                st.write(f"• **RSI**: {rsi:.1f} ({'🟢 탄력' if c4 else '⚠️ 과열/침체'})")
                st.write(f"• **거래량비**: {vol_ratio:.2f}배 ({'🟢 급증' if c5 else '⚪ 평이'})")

            # 5. 장기 투자 관점 (접어두기)
            real_sma200, real_high52, real_low52 = get_daily_stats(ticker)
            if real_sma200 == 0.0:
                real_sma200, real_high52, real_low52 = sma50, max(highs), min(lows)
            dist_from_sma200 = ((curr - real_sma200) / real_sma200) * 100 if real_sma200 > 0 else 0

            with st.expander("🏛️ 장기 투자 관점 정밀 진단 (200일선 & 52주)", expanded=False):
                st.markdown(f"""
                <div class="longterm-box">
                    <p style="margin-bottom:6px;">• <b>실제 1년선(200일선)</b>: ${real_sma200:.2f} (현재가 대비 <b>{dist_from_sma200:+.1f}%</b> 이격)</p>
                    <p style="margin-bottom:6px;">• <b>52주 최고/최저</b>: 고점 ${real_high52:.2f}  |  저점 ${real_low52:.2f}</p>
                    <hr style="border: 0; border-top: 1px solid #3730a3; margin: 8px 0;">
                    <p style="margin-bottom:0; font-size:0.9rem; line-height:1.4;">
                        {
                            "🚨 <b>3배 레버리지 경고</b>: 하락 시 음의 복리로 계좌가 녹아내릴 수 있습니다. 절대 장기 적립하지 마시고 단타/스윙으로만 익절하고 나오세요!"
                            if is_leveraged else
                            "🟢 <b>장기 적립식 적합</b>: 1배수 우량주 상품입니다. 200일선 부근 눌림목에서 분할 매수해 모아가기에 적합합니다."
                        }
                    </p>
                </div>
                """, unsafe_allow_html=True)

st.caption(f"적용 환율: $1 = {usd_krw:,.1f}원 | 실시간 캔들 기준 (한국 시각 {datetime.now(zoneinfo.ZoneInfo('Asia/Seoul')).strftime('%H:%M:%S')})")
