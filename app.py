import streamlit as st
import random

st.set_page_config(page_title="BLACK SKY", layout="wide")

# --------------------
# 초기 상태 설정
# --------------------
if "week" not in st.session_state:
    st.session_state.week = 1
    st.session_state.trust = 70
    st.session_state.fear = 20
    st.session_state.economy = 65
    st.session_state.order = 72
    st.session_state.food = 70
    st.session_state.infra = 70
    st.session_state.intel = 50

# --------------------
# UI
# --------------------
st.title("🕊️ BLACK SKY")
st.subheader(f"Week {st.session_state.week}")

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 📊 국가 지표")
    st.metric("정부 신뢰", st.session_state.trust)
    st.metric("공포 수준", st.session_state.fear)
    st.metric("경제력", st.session_state.economy)

with col2:
    st.markdown("### ⚙️ 사회 상태")
    st.metric("사회 질서", st.session_state.order)
    st.metric("식량 공급", st.session_state.food)
    st.metric("인프라", st.session_state.infra)
    st.metric("정보력", st.session_state.intel)

st.divider()

st.markdown("## 🎯 이번 턴 정책 선택")

policy = st.selectbox(
    "정책을 선택하세요",
    [
        "아무것도 하지 않음",
        "공항 방어 강화",
        "농업 방어 강화",
        "정보전 대응",
        "연구 투자 확대",
    ],
)

def apply_policy(p):
    if p == "공항 방어 강화":
        st.session_state.order += 2
        st.session_state.economy -= 2
    elif p == "농업 방어 강화":
        st.session_state.food += 3
        st.session_state.economy -= 1
    elif p == "정보전 대응":
        st.session_state.trust += 2
        st.session_state.fear -= 2
    elif p == "연구 투자 확대":
        st.session_state.intel += 4
        st.session_state.economy -= 3

def crow_attack():
    # 초지능 까마귀 기만 로직 (단순화 버전)
    if st.session_state.intel < 60:
        st.session_state.trust -= random.randint(2,4)
        st.session_state.fear += random.randint(3,6)
    else:
        st.session_state.infra -= random.randint(1,3)
        st.session_state.economy -= random.randint(1,2)

if st.button("⏭️ 다음 턴"):
    apply_policy(policy)
    crow_attack()
    st.session_state.week += 1

    # 자동 붕괴 효과
    if st.session_state.fear > 60:
        st.session_state.order -= 5
        st.session_state.trust -= 3

    st.rerun()

st.divider()

if st.session_state.trust <= 0 or st.session_state.order <= 0:
    st.error("💀 국가 붕괴. 원인은 명확하지 않다...")
