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

# 실시간 단일 주가 조회 함수
@st.cache_data(ttl=15)
def get_live_price(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=15m&range=1d&includePrePost=true"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())['chart']['result'][0]
        c = [x for x in data['indicators']['quote'][0]['close'] if x is not None]
        return float(c[-1]) if c else 0.0
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
        if items and hasattr(st, "query_params"):
            st.query_params["p"] = "_".join(items)
    except Exception:
        pass

def load_portfolio():
    param_data = parse_portfolio_from_params()
    if param_data:
        return param_data
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                if isinstance(d, dict) and d:
                    return d
        except Exception:
            pass
    return {"SOXL": {"shares": 15, "avg_price": 63.56}}

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

# 1. 메인 타이틀 & 새로고침 버튼
col_title, col_ref = st.columns([3, 2])
with col_title:
    st.title("📈 퀀트 분석기")
with col_ref:
    st.write("")
    if st.button("🔄 실시간 새로고침", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

now_kr_str = datetime.now(zoneinfo.ZoneInfo("Asia/Seoul")).strftime("%H:%M:%S")
st.caption(f"⚡ 실시간 호가 연동 (최근 갱신: 한국 시각 {now_kr_str})")

# ==============================================================================
# 🔥 [상시 고정] 내 실시간 보유 주식 요약 바 (어떤 화면에서도 항상 보임)
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
            lp = avg  # 조회 실패 시 원금으로 폴백
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

if portfolio_items:
    item_summaries = " · ".join([f"<b>{item['symbol']}</b> {item['shares']}주 (${item['live_price']:.2f})" for item in portfolio_items])
    st.markdown(f"""
    <div style="background-color: {bar_bg}; border: 1px solid {bar_border}; border-radius: 12px; padding: 12px 16px; margin-bottom: 8px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="font-size:0.95rem; font-weight:bold; color:#e2e8f0;">💼 내 실시간 총 손익</span>
            <span style="font-size:1.25rem; font-weight:800; color:{bar_color};">{bar_sign}${total_pnl_usd:.2f} ({bar_sign}{total_pnl_pct:.2f}%)</span>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:3px;">
            <span style="font-size:0.85rem; color:#cbd5e1;">{item_summaries}</span>
            <span style="font-size:1.15rem; font-weight:800; color:{bar_color};">{bar_sign}{total_pnl_krw:,.0f} 원</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 1. 실시간 익절/손절 도달 알림 배너
    for item in portfolio_items:
        i_sym = item['symbol']
        i_pct = item['pnl_pct']
        i_pnl_krw = item['pnl_usd'] * usd_krw
        i_live = item['live_price']
        if i_pct >= 7.0:
            st.markdown(f"""
            <div style="background-color: #064e3b; border: 1.5px solid #10b981; border-radius: 10px; padding: 10px 14px; margin-bottom: 8px;">
                <span style="font-size:1.0rem; font-weight:800; color:#6ee7b7;">🎉 [익절 신호] {i_sym} 2차 목표가(+7.0%) 돌파 완료!</span><br>
                <span style="font-size:0.85rem; color:#e2e8f0;">현재가 ${i_live:.2f} (수익률 <b>+{i_pct:.2f}%</b>, 평가익 <b>+{i_pnl_krw:,.0f}원</b>) — 50% 분할 익절 또는 전량 익절 타이밍입니다!</span>
            </div>
            """, unsafe_allow_html=True)
        elif i_pct >= 3.5:
            st.markdown(f"""
            <div style="background-color: #1e3a8a; border: 1.5px solid #3b82f6; border-radius: 10px; padding: 10px 14px; margin-bottom: 8px;">
                <span style="font-size:1.0rem; font-weight:800; color:#93c5fd;">🎯 [익절 신호] {i_sym} 1차 목표가(+3.5%) 도달!</span><br>
                <span style="font-size:0.85rem; color:#e2e8f0;">현재가 ${i_live:.2f} (수익률 <b>+{i_pct:.2f}%</b>, 평가익 <b>+{i_pnl_krw:,.0f}원</b>) — 50% 분할 매도로 수익을 확정하세요!</span>
            </div>
            """, unsafe_allow_html=True)
        elif i_pct <= -1.8:
            st.markdown(f"""
            <div style="background-color: #7f1d1d; border: 1.5px solid #ef4444; border-radius: 10px; padding: 10px 14px; margin-bottom: 8px;">
                <span style="font-size:1.0rem; font-weight:800; color:#fca5a5;">⚠️ [손절 경고] {i_sym} 손절 기준선(-1.8%) 이탈!</span><br>
                <span style="font-size:0.85rem; color:#fecaca;">현재가 ${i_live:.2f} (손실률 <b>{i_pct:.2f}%</b>) — 원금 보존을 위해 칼손절을 권장합니다!</span>
            </div>
            """, unsafe_allow_html=True)
else:
    st.info("💡 등록된 보유 주식이 없습니다. 아래 '💼 내 보유 잔고' 탭에서 종목과 수량을 등록하세요!")

# ==============================================================================
# 2대 메인 탭 분리: [1. 💼 내 보유 잔고 전용 화면] vs [2. 📈 종목별 퀀트 타점 분석]
# ==============================================================================
tab_portfolio, tab_analysis = st.tabs(["💼 내 보유 주식만 보기", "📈 종목별 퀀트 타점 분석"])

# ------------------------------------------------------------------------------
# TAB 1: 내 보유 주식만 따로 보는 전용 화면
# ------------------------------------------------------------------------------
with tab_portfolio:
    st.subheader("💼 내 실시간 보유 잔고 포트폴리오")
    st.caption("내가 매수한 종목들의 실시간 평가 손익과 원화 수익금을 한눈에 확인합니다.")

    if portfolio_items:
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            st.metric("총 매수 원금", f"${total_invest_usd:,.2f}", f"{total_invest_usd * usd_krw:,.0f} 원")
            st.metric("총 평가 손익 (USD)", f"{bar_sign}${total_pnl_usd:.2f}", f"{bar_sign}{total_pnl_pct:.2f}%")
        with col_t2:
            st.metric("현재 총 평가액", f"${total_curr_usd:,.2f}", f"{total_curr_usd * usd_krw:,.0f} 원")
            st.metric("총 평가 손익 (KRW)", f"{bar_sign}{total_pnl_krw:,.0f} 원", f"적용 환율 {usd_krw:,.0f}원")

        st.markdown("### 📋 종목별 상세 보유 내역")
        for item in portfolio_items:
            s_sym = item['symbol']
            s_shares = item['shares']
            s_avg = item['avg_price']
            s_live = item['live_price']
            s_pnl = item['pnl_usd']
            s_pct = item['pnl_pct']
            s_krw = s_pnl * usd_krw
            s_is_profit = s_pnl >= 0
            s_color = "#4ade80" if s_is_profit else "#f87171"
            s_sign = "+" if s_is_profit else ""

            st.markdown(f"""
            <div style="background-color: #1a1e29; border: 1px solid #2a3142; border-radius: 12px; padding: 14px; margin-bottom: 10px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-size:1.15rem; font-weight:bold; color:white;">🔥 {s_sym} ({s_shares}주)</span>
                    <span style="font-size:1.2rem; font-weight:800; color:{s_color};">{s_sign}${s_pnl:.2f} ({s_sign}{s_pct:.2f}%)</span>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center; margin-top:4px;">
                    <span style="font-size:0.9rem; color:#94a3b8;">평단 ${s_avg:.2f} → 현재가 <b>${s_live:.2f}</b></span>
                    <span style="font-size:1.1rem; font-weight:800; color:{s_color};">{s_sign}{s_krw:,.0f} 원</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            if st.button(f"🎉 {s_sym} 익절 완료 기록 (장부에 저장)", key=f"rec_btn_{s_sym}", use_container_width=True):
                j_list = load_journal()
                j_list.insert(0, {
                    "date": datetime.now(zoneinfo.ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M"),
                    "symbol": s_sym,
                    "shares": s_shares,
                    "sell_price": s_live,
                    "profit_krw": int(s_krw),
                    "profit_usd": round(s_pnl, 2),
                    "pct": round(s_pct, 2),
                    "note": f"${s_live:.2f} 매도 확정"
                })
                save_journal(j_list)
                st.success(f"{s_sym} {s_shares}주 익절 기록 완료!")
                st.rerun()

        # 2. 누적 실현 손익 장부
        st.markdown("---")
        st.subheader("💰 이번 달 누적 실현 손익 (익절 장부)")
        journal_entries = load_journal()
        if journal_entries:
            tot_realized_krw = sum(x.get("profit_krw", 0) for x in journal_entries)
            tot_realized_usd = sum(x.get("profit_usd", 0.0) for x in journal_entries)
            j_color = "#4ade80" if tot_realized_krw >= 0 else "#f87171"
            j_sign = "+" if tot_realized_krw >= 0 else ""

            st.markdown(f"""
            <div style="background-color: #1a1e29; border: 1px solid #3b82f6; border-radius: 12px; padding: 14px 18px; margin-bottom: 12px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-size:1.0rem; font-weight:bold; color:#93c5fd;">총 누적 확정 수익금</span>
                    <span style="font-size:1.35rem; font-weight:800; color:{j_color};">{j_sign}{tot_realized_krw:,.0f} 원</span>
                </div>
                <div style="text-align:right; font-size:0.9rem; color:#cbd5e1; margin-top:2px;">
                    {j_sign}${tot_realized_usd:.2f} (총 {len(journal_entries)}회 매매 확정)
                </div>
            </div>
            """, unsafe_allow_html=True)

            for j in journal_entries[:5]:
                p_c = "#4ade80" if j.get("profit_krw", 0) >= 0 else "#f87171"
                p_s = "+" if j.get("profit_krw", 0) >= 0 else ""
                st.markdown(f"""
                <div style="background-color: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 10px 14px; margin-bottom: 6px;">
                    <div style="display:flex; justify-content:space-between;">
                        <span style="font-weight:bold; color:white;">{j.get('symbol')} ({j.get('shares')}주 @ ${j.get('sell_price'):.2f})</span>
                        <span style="font-weight:bold; color:{p_c};">{p_s}{j.get('profit_krw'):,.0f}원 ({p_s}{j.get('pct')}%)</span>
                    </div>
                    <div style="font-size:0.8rem; color:#64748b; margin-top:2px;">
                        {j.get('date')} · {j.get('note', '')}
                    </div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.write("아직 등록된 보유 종목이 없습니다.")

    st.markdown("---")
    st.markdown("### ⚙️ 보유 종목 추가 / 수정 / 삭제")
    with st.expander("➕ 새 종목 등록 또는 수량 변경", expanded=False):
        c_e1, c_e2, c_e3 = st.columns(3)
        with c_e1:
            edit_sym = st.text_input("티커 (예: SOXL, TSLA)", value="SOXL").strip().upper()
        with c_e2:
            edit_shares = st.number_input("보유 수량 (주, 0이면 삭제)", min_value=0, value=15, step=1)
        with c_e3:
            edit_avg = st.number_input("매수 평단가 ($)", min_value=0.0, value=63.56, step=0.1, format="%.2f")

        if st.button("💾 저장 / 수정하기"):
            if edit_sym:
                if edit_shares > 0:
                    st.session_state.my_portfolio[edit_sym] = {"shares": edit_shares, "avg_price": edit_avg}
                    save_portfolio(st.session_state.my_portfolio)
                    st.success(f"{edit_sym} {edit_shares}주 (${edit_avg:.2f}) 영구 저장 완료!")
                else:
                    if edit_sym in st.session_state.my_portfolio:
                        del st.session_state.my_portfolio[edit_sym]
                        save_portfolio(st.session_state.my_portfolio)
                        st.warning(f"{edit_sym} 삭제 완료!")
                st.rerun()

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

            vol_ma20 = np.mean(vols[-21:-1]) if len(vols) > 20 else vols[-1]
            vol_ratio = (vols[-1] / (vol_ma20 + 1e-9))

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

            # 트레이딩뷰 프로 차트
            st.markdown(f"### 📺 실시간 프로 차트 ({ticker})")
            st.caption("💡 캔들 위 이동평균선(MA)과 아래 RSI 지표가 기본 탑재되어 있으며, 상단 '지표(fx)' 메뉴에서 원하는 지표를 자유롭게 추가할 수 있습니다.")
            tv_html = f"""
            <div class="tradingview-widget-container" style="height:420px;width:100%;">
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
            components.html(tv_html, height=430)

            # 장기 투자 관점 정밀 진단 카드 (실제 1년치 일봉 데이터 기반)
            st.markdown("### 🏛️ 장기 투자 관점 정밀 진단")
            real_sma200, real_high52, real_low52 = get_daily_stats(ticker)
            if real_sma200 == 0.0:
                real_sma200, real_high52, real_low52 = sma50, max(highs), min(lows)
            dist_from_sma200 = ((curr - real_sma200) / real_sma200) * 100 if real_sma200 > 0 else 0

            st.markdown(f"""
            <div class="longterm-box">
                <h4 style="margin-top:0; color:#818cf8;">📌 장기 관점 핵심 체크리스트</h4>
                <p style="margin-bottom:6px;">• <b>실제 1년 이평선(200일선)</b>: ${real_sma200:.2f} (현재가 대비 <b>{dist_from_sma200:+.1f}%</b> 이격)</p>
                <p style="margin-bottom:6px;">• <b>실제 52주 최고/최저가</b>: 고점 ${real_high52:.2f}  |  저점 ${real_low52:.2f}</p>
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

            # 실전 가이드 테이블
            st.markdown("### 🎯 실전 주문 가이드 (달러 & 원화 기준)")
            buy_rec_low = min(curr, ema9)
            buy_rec_high = max(curr, ema9)
            buy_rec_krw = curr * usd_krw

            st.markdown(f"""
            <div style="background-color: #1e293b; border: 1.5px solid #3b82f6; border-radius: 12px; padding: 14px 18px; margin-bottom: 12px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-size:1.1rem; font-weight:bold; color:#60a5fa;">🎯 매수 권장가 (진입 타점)</span>
                    <span style="font-size:1.35rem; font-weight:800; color:#38bdf8;">${buy_rec_low:.2f} ~ ${buy_rec_high:.2f}</span>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center; margin-top:5px;">
                    <span style="font-size:0.85rem; color:#94a3b8;">9선 눌림목 지지 구간 (현재가: ${curr:.2f})</span>
                    <span style="font-size:1.1rem; font-weight:700; color:#f1f5f9;">약 {buy_rec_krw:,.0f} 원</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            m1, m2 = st.columns(2)
            with m1:
                st.metric(f"1차 익절가 (+{target_tp1_pct*100:.1f}%)", f"${tp1:.2f}", f"약 {tp1*usd_krw:,.0f}원")
                st.metric(f"2차 익절가 (+{target_tp2_pct*100:.1f}%)", f"${tp2:.2f}", f"약 {tp2*usd_krw:,.0f}원")
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
