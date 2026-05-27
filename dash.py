import streamlit as st
import pandas as pd
import hashlib
import datetime
import base64
import requests
from streamlit_gsheets import GSheetsConnection
import plotly.express as px
import extra_streamlit_components as stx
import numpy as np

# ==========================================
# 1. 페이지 설정 및 세션 초기화
# ==========================================
st.set_page_config(page_title="Agri-AX 통합 관리 시스템", layout="wide")

today = datetime.date.today()
target_month = today.month - 1 if today.month > 1 else 12
#시스템 가볍게 만들기 위한 캐시데이터 기간 설정
@st.cache_data(ttl=600) # 10분간 메모리에 저장
def load_data(sheet_name):
    df = conn.read(worksheet=sheet_name)
    df.columns = df.columns.str.strip()
    return df
def get_user_master():
    df = conn.read(worksheet="User_Master")
    df.columns = df.columns.str.strip()
    return df

@st.cache_data(ttl=300) # 5분간 저장
def get_performance_master():
    df = conn.read(worksheet="Performance_Master")
    df.columns = df.columns.str.strip()
    return df

#쿠키/자동복구 설정
AUTO_LOGIN_WINDOW_MINUTES = 10   # 새로고침 복구 허용 시간 (예: 10분)
COOKIE_EXPIRE_DAYS = 30          # 쿠키 자체 보관 기간
cookie_manager = stx.CookieManager(key="agri_ax_cookie_manager")
def clear_login_cookies():
    cookie_manager.delete("agri_ax_user")
    cookie_manager.delete("agri_ax_login_time")
    expired_at = now_dt() - datetime.timedelta(days=1)
    try:
        cookie_manager.set("agri_ax_user", "", expires_at=expired_at)
        cookie_manager.set("agri_ax_login_time", "", expires_at=expired_at)
    except:
        pass
    # 세션 초기화
    st.session_state['logged_in'] = False
    st.session_state['user_id'] = None
    st.session_state['user_role'] = None
    st.session_state['user_info'] = None
COOKIE_AUTH_NAME = "agri_ax_auth_v1"  # 쿠키 이름 정의
def now_dt():
    return datetime.datetime.now()
def dt_to_str(dt_obj):
    return dt_obj.strftime("%Y-%m-%d %H:%M:%S")
def str_to_dt(dt_str):
    try:
        return datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    except:
        return None
def make_auth_cookie(user_id: str) -> str:
    return f"{user_id}|{dt_to_str(now_dt())}"

def parse_auth_cookie(cookie_value: str):
    try:
        user_id, login_time_str = cookie_value.split("|", 1)
        return user_id, login_time_str
    except:
        return None, None

def clear_login_cookies():
    # delete만 사용 (set으로 빈값 덮어쓰기 금지)
    try:
        cookie_manager.delete(COOKIE_AUTH_NAME)
    except:
        pass

    st.session_state['logged_in'] = False
    st.session_state['user_id'] = None
    st.session_state['user_role'] = None
    st.session_state['user_info'] = None
cookie_user_id = cookie_manager.get(cookie="agri_ax_user")
cookie_auth = cookie_manager.get(cookie=COOKIE_AUTH_NAME)
cookie_user_id, cookie_login_time = parse_auth_cookie(cookie_auth) if cookie_auth else (None, None)
if 'logged_in' not in st.session_state:
    st.session_state.update({
        'logged_in': False,
        'user_id': None,
        'user_role': None,
        'user_info': None,
        'just_logged_out': False
    })
# ==========================================
# 2. 공통 함수 및 구글 시트 연결
# ==========================================
def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def upload_to_drive(uploaded_file, custom_filename):
    if uploaded_file is None:
        return ""
    webhook_url = "https://script.google.com/macros/s/AKfycbx0c58zJ9nnfl6VTC0rwZ0uafKZB4SnIX8SanV8hNPmO6NxhzCSOibrQJMfLQZ0hd1-/exec"
    file_bytes = uploaded_file.getvalue()
    encoded_file = base64.b64encode(file_bytes).decode('utf-8')
    extension = uploaded_file.name.split('.')[-1]
    final_name = f"{custom_filename}.{extension}"
    payload = {
        "fileName": final_name,
        "mimeType": uploaded_file.type,
        "fileData": encoded_file
    }
    try:
        response = requests.post(webhook_url, data=payload, timeout=30)
        return response.text if response.status_code == 200 else "업로드 실패"
    except Exception as e:
        return f"통신 에러: {str(e)}"
conn = st.connection("gsheets", type=GSheetsConnection)

# ==========================================
# 3. 새로고침 시 쿠키로 세션 복구 (10분 유효성 검사)
# ==========================================
login_dt = str_to_dt(cookie_login_time)
if not st.session_state.get('logged_in') and cookie_auth:
    cookie_user_id, cookie_login_time = parse_auth_cookie(cookie_auth)
    if cookie_user_id and cookie_login_time:
        # 10분 이내 체크
        if login_dt and (now_dt() - login_dt).total_seconds() < (AUTO_LOGIN_WINDOW_MINUTES * 60):
            user_df = load_data("User_Master")  # 캐싱된 데이터 사용
            user_match = user_df[user_df['로그인ID'] == cookie_user_id]
            if not user_match.empty:
                st.session_state.update({
                    'logged_in': True,
                    'user_id': cookie_user_id,
                    'user_role': user_match.iloc[0]['권한범위'],
                    'user_info': user_match.iloc[0].to_dict()
                })
    if login_dt and (now_dt() - login_dt).total_seconds() < (AUTO_LOGIN_WINDOW_MINUTES * 60):
        try:
            user_df = conn.read(worksheet="User_Master", ttl=60)
            user_df.columns = user_df.columns.str.strip()
            user_match = user_df[user_df['로그인ID'] == cookie_user_id]

            if not user_match.empty:
                st.session_state.update({
                    'logged_in': True,
                    'user_id': cookie_user_id,
                    'user_role': user_match.iloc[0]['권한범위'],
                    'user_info': user_match.iloc[0].to_dict()
                })
        except Exception as e:
            st.error(f"세션 복구 중 오류: {e}")
    else:
        clear_login_cookies()

# ==========================================
# 4. [로그인 전 화면]
# ==========================================
if not st.session_state.get('logged_in'):
    st.markdown("<h1 style='text-align: center; margin-top: 50px;'>🚜 Agri-AX 통합 관리 시스템</h1>", unsafe_allow_html=True)
    _, col2, _ = st.columns([1, 1.5, 1])
    with col2:
        with st.container(border=True):
            input_id = st.text_input("사용자 ID (로그인ID)", key="login_id_input")
            input_pw = st.text_input("비밀번호", type="password", key="login_pw_input")
            login_submitted = st.button("로그인", use_container_width=True, type="primary")
            if login_submitted:
                user_df = load_data("User_Master")
                user_match = user_df[user_df['로그인ID'] == input_id]

                if not user_match.empty:
                    stored_hash = str(user_match.iloc[0]['비밀번호_해시']).strip()
                    input_hash = hash_password(input_pw)

                    if stored_hash == input_hash:
                        # 1. 세션 상태 업데이트
                        st.session_state.update({
                            'logged_in': True,
                            'user_id': input_id,
                            'user_role': user_match.iloc[0]['권한범위'],
                            'user_info': user_match.iloc[0].to_dict(),
                            'just_logged_out': False
                        })

                        # 통합 인증 쿠키 생성 및 저장
                        auth_value = make_auth_cookie(input_id)
                        expires = now_dt() + datetime.timedelta(days=COOKIE_EXPIRE_DAYS)
                        cookie_manager.set(COOKIE_AUTH_NAME, auth_value, expires_at=expires)

                        st.success(f"✅ {input_id}님 환영합니다!")
                        st.rerun()
                    else:
                        st.error("❌ 비밀번호가 틀렸습니다.")
                else:
                    st.error("❌ 존재하지 않는 아이디입니다.")

        if st.button("💡 시스템 이용 문의", use_container_width=True):
            st.toast("운영사무국: 02-123-4567 / help@agri-ax.kr")
            st.info("관리자(PMO): 박지윤 선임 (jypark@rnextep.kr)")
    st.stop()
# ==========================================
# 5. [로그인 후 화면]
# ==========================================
if st.session_state.get('logged_in'):
    # ------------------------------------------
    # [1] 공통 사이드바 (관리자/기업 공용)
    # ------------------------------------------
    with st.sidebar:
        st.success(f"✅ {st.session_state.user_id}님")
        st.write(f"**성명:** {st.session_state.user_info['성명']}")
        st.write(f"**권한:** {st.session_state.user_role}")

        # [공통] 로그아웃 버튼
        if st.button("로그아웃", use_container_width=True, type="secondary"):
            clear_login_cookies()
            st.session_state['just_logged_out'] = True
            st.rerun()
        st.divider()
        # --- [관리자 전용 메뉴 추가] ---
        if st.session_state.user_role == "sys_admin":
            st.markdown("### 🏢 PMO 관리 메뉴")
            try:
                # 미처리 건수 실시간 계산 (ttl=60)
                req_log_df = conn.read(worksheet="Budgetchange_req_Log", ttl=60)
                req_log_df.columns = req_log_df.columns.str.strip()
                pending_count = len(req_log_df[req_log_df['처리상태'] != '대응완료'])
            except:
                pending_count = 0
                req_log_df = pd.DataFrame()

            req_label = "📑 예산변경 신청현황"
            if pending_count > 0:
                req_label += f" (🔔 {pending_count})"

            # 관리자 전용 페이지 선택 변수
            admin_page = st.radio("이동할 페이지 선택:", ["📊 통합 모니터링", req_label])
            st.divider()

        # [공통] 비밀번호 변경 기능
        with st.expander("🔐 내 비밀번호 변경"):
            new_pw = st.text_input("새 비밀번호", type="password", key="change_pw")
            confirm_pw = st.text_input("비밀번호 확인", type="password", key="confirm_pw")
            if st.button("비밀번호 저장", use_container_width=True):
                if new_pw == confirm_pw and len(new_pw) >= 4:
                    new_pw_hashed = hash_password(new_pw)
                    user_df = conn.read(worksheet="User_Master")
                    user_idx = user_df[user_df['로그인ID'] == st.session_state.user_id].index[0]
                    user_df.at[user_idx, '비밀번호_해시'] = new_pw_hashed
                    conn.update(worksheet="User_Master", data=user_df)
                    st.success("✅ 비밀번호가 변경되었습니다.")
                else:
                    st.error("❌ 4자리 이상, 일치 여부 확인!")
    # ------------------------------------------
    # [A] 관리자 권한 (sys_admin) 대시보드
    # ------------------------------------------
    # 3. [페이지 1] 통합 모니터링
    if st.session_state.user_role == "sys_admin":
        if admin_page == "📊 통합 모니터링":
            st.title("📊 PMO 운영본부 통합 모니터링")
            st.divider()
            # 데이터 로딩 단일화 및 전처리
            with st.spinner("데이터를 불러오는 중입니다..."):
                # 1. 시트 데이터 일괄 로드
                log_df = conn.read(worksheet="Performance_Log", ttl=300)
                perf_master = conn.read(worksheet="Performance_Master", ttl=300)

                # 2. 컬럼 공백 제거 (공통)
                for df in [log_df, perf_master]:
                    df.columns = df.columns.str.strip()

                # 3. 데이터 가공 (필터링 및 월 추출)
                    # 특정 기업 제외
                perf_master = perf_master[perf_master['기업명(기관명)'] != '(주)라온넥스텝']
                log_df = log_df[log_df['기업명(기관명)'] != '(주)라온넥스텝']
                    # 월(Month) 정보 추출
                if not log_df.empty and '실적대상월' in log_df.columns:
                    log_df['월'] = pd.to_datetime(log_df['실적대상월'], errors='coerce').dt.month
                else:
                    log_df['월'] = pd.Series(dtype='int')
                    # 유효 기관 리스트 확보
                valid_orgs = perf_master['기업명(기관명)'].unique().tolist()
                pass

                tab1, tab2, tab3, tab4 = st.tabs(["🗓️ 월별 제출 현황", "📈 성과 분석", "💰 예산 분석", "📋 전체 로그"])
                with tab1:
                    st.subheader("🗓️ 월별 실적 제출 현황 점검")
                    if not log_df.empty and '월' in log_df.columns:
                        avail_months = sorted(log_df['월'].dropna().unique().astype(int).tolist())
                    else:
                        avail_months = [target_month]
                    avail_months = sorted(log_df['월'].dropna().unique().astype(int).tolist()) if not log_df[
                        '월'].dropna().empty else [target_month]
                    sel_month = st.selectbox("조회 월 선택:", options=avail_months)
                    month_log = log_df[log_df['월'] == sel_month]
                    sub_codes = month_log['기관고유코드'].unique()
                    sub_orgs = perf_master[perf_master['기관고유코드'].isin(sub_codes)][['기관고유코드', '기업명(기관명)', '담당자명', '연락처']]
                    mis_orgs = perf_master[~perf_master['기관고유코드'].isin(sub_codes)][['기관고유코드', '기업명(기관명)', '담당자명', '연락처']]
                    c1, c2 = st.columns(2)
                    with c1:
                        st.success(f"✅ 제출 완료 ({len(sub_orgs)}개)")
                        st.dataframe(sub_orgs, use_container_width=True)
                    with c2:
                        st.error(f"⚠️ 미제출 ({len(mis_orgs)}개)")
                        st.dataframe(mis_orgs, use_container_width=True)

                with tab2:
                    st.subheader("🚀 전체 참여기관 성과 달성 현황 (%)")
                    latest_logs = log_df.sort_values('제출일시').groupby('기업명(기관명)').tail(1)
                    all_orgs_base = perf_master[['기관고유코드', '기업명(기관명)']].drop_duplicates()
                    combined_perf = pd.merge(all_orgs_base, latest_logs[['기업명(기관명)', '성과_종합달성률']], on='기업명(기관명)',
                                             how='left').fillna(0)
                    #전체 차트 출력
                    fig_all_perf = px.bar(combined_perf, x='기업명(기관명)', y='성과_종합달성률', text='성과_종합달성률',
                                          color_discrete_sequence=["#FF4B4B"])
                    fig_all_perf.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
                    st.plotly_chart(fig_all_perf, use_container_width=True)
                    st.divider()
                    st.subheader("🔍 기관별 성과지표 상세 분석")
                    sel_org_perf = st.selectbox("상세 조회 기관:", valid_orgs)
                    # 해당 기관 데이터 필터링
                    org_log = log_df[log_df['기업명(기관명)'] == sel_org_perf]
                    org_master_match = perf_master[perf_master['기업명(기관명)'] == sel_org_perf]
                    if not org_master_match.empty:
                        org_master = org_master_match.iloc[0]
                        perf_data = []
                    for i in range(1, 5):
                        name = org_master.get(f'성과지표{i}_지표명', '')
                        if pd.isna(name) or not str(name).strip(): continue
                        target = float(org_master.get(f'성과지표{i}_목표', 0))
                        unit = org_master.get(f'성과지표{i}_단위', '')
                        # log_df의 해당 지표 컬럼 합산 (누적치 계산)
                        col_name = f'실적_지표{i}'
                        actual = org_log[col_name].astype(float).sum() if col_name in org_log.columns else 0

                        rate = (actual / target * 100) if target > 0 else 0
                        perf_data.append(
                            {"성과지표명": name, "누적성과(실적)": f"{actual:,.1f} {unit}", "목표치": f"{target:,.1f} {unit}",
                             "달성률(%)": f"{rate:.1f}%", "달성률(%)": rate})
                    if perf_data:
                        df_perf = pd.DataFrame(perf_data)
                        fig_det_perf = px.bar(df_perf, x='성과지표명', y='달성률(%)', text='달성률(%)',
                                              color_discrete_sequence=["#FF4B4B"])
                        fig_det_perf.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
                        st.plotly_chart(fig_det_perf, use_container_width=True)
                        st.markdown("**📊 상세 성과 지표 데이터 테이블**")
                        st.table(df_perf[["성과지표명", "누적성과(실적)", "목표치", "달성률(%)"]])

                with tab3:
                    view_mode = st.radio("📊 데이터 조회 기준 선택:", ["금액 기준 (천 원)", "달성률 기준 (%)"], horizontal=True)
                    st.subheader("💰 전체 참여기관 예산 누적 집행 현황")
                    # 예산 집행 데이터 집계
                    cum_b_total = log_df.groupby('기업명(기관명)')['당월_총집행액'].sum().reset_index()
                    all_b_base = perf_master[['기업명(기관명)', '기업별_총사업비']].copy()
                    all_b_base['기업별_총사업비'] = pd.to_numeric(all_b_base['기업별_총사업비'], errors='coerce').fillna(0)
                    budget_total_merge = pd.merge(all_b_base, cum_b_total, on='기업명(기관명)', how='left').fillna(0)

                    plot_all_amt, plot_all_rate = [], []
                    for _, row in budget_total_merge.iterrows():
                        t_amt, a_amt = row['기업별_총사업비'] / 1000, row['당월_총집행액'] / 1000
                        rate = (a_amt / t_amt * 100) if t_amt > 0 else 0
                        plot_all_amt.extend([{"기업명": row['기업명(기관명)'], "구분": "배정 총사업비", "값": t_amt},
                                             {"기업명": row['기업명(기관명)'], "구분": "누적 집행액", "값": a_amt}])
                        plot_all_rate.append({"기업명": row['기업명(기관명)'], "구분": "누적 집행률", "값": rate})

                    # 메인차트 출력
                    if "금액" in view_mode:
                        df_all = pd.DataFrame(plot_all_amt)
                        # [수정] text='값' 으로 변경
                        fig_all_b = px.bar(df_all, x='기업명', y='값', color='구분', barmode='group', text='값',
                                           labels={'값': '금액 (천 원)'},
                                           color_discrete_map={"배정 총사업비": "#D3D3D3", "누적 집행액": "#0068C9"})
                        fig_all_b.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
                    else:
                        df_all = pd.DataFrame(plot_all_rate)
                        # [수정] text='값' 으로 변경
                        fig_all_b = px.bar(df_all, x='기업명', y='값', color='구분', barmode='group', text='값',
                                           labels={'값': '집행률 (%)'},
                                           color_discrete_map={"목표치 (100%)": "#D3D3D3", "누적 집행률": "#0068C9"})
                        fig_all_b.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
                        # Y축 범위 조정 (달성률)
                        fig_all_b.update_yaxes(range=[0, max(df_all['값'].max() * 1.2, 110)])

                    st.plotly_chart(fig_all_b, use_container_width=True)
                    st.divider()

                    # 기관별 상세 예산 현황
                    st.subheader("🔍 기관별 예산 세목 상세 현황")
                    sel_org_budget = st.selectbox("조회 기관 선택:", valid_orgs, key="budget_sel_v4")
                    org_log_b = log_df[log_df['기업명(기관명)'] == sel_org_budget]
                    org_master_match = perf_master[perf_master['기업명(기관명)'] == sel_org_budget]

                    if not org_master_match.empty:
                        org_master_b = org_master_match.iloc[0]
                        categories = ['내부인건비', '과제수당', '구입설치_유형자산', '구입설치_무형자산', '구입설치_부대비용', '시설장비임차', '재료구입비',
                                      '제품제작비', '외부전문기술활용비', '과제관리비']
                        sources = ['국비', '지방비', '민간현금', '민간현물']

                        detail_rows, plot_det_amt, plot_det_rate = [], [], []

                        for cat in categories:
                            t_val_sum, a_val_sum = 0, 0
                            for src in sources:
                                t_val_sum += float(org_master_b.get(f"예산_{src}_{cat}", 0))
                                log_col = f"집행_{src}_{cat}"
                                # 숫자 변환 시 오류 방지
                                a_val_sum += pd.to_numeric(org_log_b[log_col],
                                                           errors='coerce').sum() if log_col in org_log_b.columns else 0

                            # 단위 변환 및 집계
                            t_val_sum_k, a_val_sum_k = t_val_sum / 1000, a_val_sum / 1000
                            if t_val_sum_k > 0 or a_val_sum_k > 0:
                                rate = (a_val_sum_k / t_val_sum_k * 100) if t_val_sum_k > 0 else 0
                                detail_rows.append(
                                    {"세목": cat, "배정예산(천원)": round(t_val_sum_k), "누적집행액(천원)": round(a_val_sum_k),
                                     "집행률(%)": f"{rate:.1f}%"})
                                # [수정] 키 이름을 '값'으로 통일
                                plot_det_amt.extend(
                                    [{"세목": cat, "구분": "배정 예산", "값": t_val_sum_k},
                                     {"세목": cat, "구분": "누적 집행액", "값": a_val_sum_k}])
                                plot_det_rate.append({"세목": cat, "구분": "누적 집행률", "값": rate})

                        if detail_rows:
                            if "금액" in view_mode:
                                df_det = pd.DataFrame(plot_det_amt)
                                # [수정] text='값'
                                fig_sub = px.bar(df_det, x='세목', y='값', color='구분', barmode='group', text='값',
                                                 labels={'값': '금액 (천 원)'},
                                                 color_discrete_map={"배정 예산": "#D3D3D3", "누적 집행액": "#0068C9"})
                                fig_sub.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
                            else:
                                df_det = pd.DataFrame(plot_det_rate)
                                # [수정] text='값'
                                fig_sub = px.bar(df_det, x='세목', y='값', color='구분', barmode='group', text='값',
                                                 labels={'값': '집행률 (%)'}, color_discrete_sequence=["#0068C9"])
                                fig_sub.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
                                # Y축 범위 조정 (달성률)
                                fig_sub.update_yaxes(range=[0, max(df_det['값'].max() * 1.2, 110)])

                            st.plotly_chart(fig_sub, use_container_width=True)

                            # 테이블 가독성 처리
                            display_df = pd.DataFrame(detail_rows)
                            display_df['배정예산(천원)'] = display_df['배정예산(천원)'].apply(lambda x: f"{x:,}")
                            display_df['누적집행액(천원)'] = display_df['누적집행액(천원)'].apply(lambda x: f"{x:,}")
                            st.table(display_df.set_index("세목"))
                with tab4:
                    st.subheader("📋 전체 제출 데이터 로그")
                    st.dataframe(log_df.sort_values(by="제출일시", ascending=False), use_container_width=True)

        # 4. [페이지 2] 예산변경 신청현황
        elif "📑 예산변경" in admin_page:
            st.title("📑 예산 변경 신청 관리")
            st.markdown(f"현재 처리가 필요한 신청 건이 **{pending_count}건** 있습니다.")
            st.divider()

            if not req_log_df.empty:
                # 1. 필터링 및 목록 표시
                show_all = st.checkbox("처리 완료된 내역도 포함해서 보기", value=False)
                display_df = req_log_df if show_all else req_log_df[req_log_df['처리상태'] != '대응완료']
                display_df = display_df.sort_values(by="신청일시", ascending=False)

                st.subheader("📋 신청 목록 (행을 클릭하여 상세 비교)")
                # selection_mode를 통해 행 선택 가능하게 설정
                event = st.dataframe(
                    display_df,
                    use_container_width=True,
                    hide_index=True,
                    on_select="rerun",  # 행 선택 시 화면 리런
                    selection_mode="single-row",
                    column_config={
                        "증빙파일": st.column_config.LinkColumn("🔗 증빙확인"),
                        "신청일시": st.column_config.DatetimeColumn("신청시간"),
                    }
                )
                ## 2. 선택된 행이 있을 경우 상세 비교 (병렬 배치)
            if event.selection.rows:
                selected_idx = event.selection.rows[0]
                selected_row = display_df.iloc[selected_idx]
                st.markdown("---")
                st.subheader(f"🔍 [{selected_row['기업명(기관명)']}] 예산 변경 내역 비교")
                # 비교 데이터 추출 (Performance_Master에서 현재 값 가져오기)
                perf_master = conn.read(worksheet="Performance_Master", ttl=300)
                orig_data = perf_master[perf_master['기관고유코드'] == selected_row['기관고유코드']].iloc[0]
                categories = ['내부인건비', '과제수당', '구입설치_유형자산', '구입설치_무형자산', '구입설치_부대비용', '시설장비임차', '재료구입비', '제품제작비', '외부전문기술활용비', '과제관리비']
                sources = ['국비', '지방비', '민간현금', '민간현물']
                # --- [기존 예산 Matrix] ---
                orig_matrix = []
                for cat in categories:
                    row = {"세목": cat}
                    for src in sources:
                        row[src] = float(orig_data.get(f"예산_{src}_{cat}", 0))
                    orig_matrix.append(row)
                df_orig_matrix = pd.DataFrame(orig_matrix).set_index("세목")
                # --- [신청 예산 Matrix] ---
                req_matrix = []
                for cat in categories:
                    row = {"세목": cat}
                    for src in sources:
                        row[src] = float(selected_row.get(f"예산_{src}_{cat}", 0))
                    req_matrix.append(row)
                df_req_matrix = pd.DataFrame(req_matrix).set_index("세목")
                # 3. 화면 병렬 배치 (Column 2개 사용)
                col_left, col_right = st.columns(2)

                with col_left:
                    st.info("📌 **[변경 전] 현재 협약 예산 (원)**")
                    # 값이 모두 0인 행은 숨겨서 깔끔하게 표시
                    df_orig_display = df_orig_matrix[(df_orig_matrix.T != 0).any()]
                    st.dataframe(df_orig_display.style.format("{:,.0f}"), use_container_width=True)

                with col_right:
                    st.warning("🚀 **[변경 후] 신청 예산 내역 (원)**")
                    df_req_display = df_req_matrix[(df_req_matrix.T != 0).any()]


                    # 신청 예산 표 스타일링 (기존과 값이 다르면 강조)
                    def highlight_changes(data):
                        attr = 'background-color: #fff3cd; color: #856404; font-weight: bold;'  # 변경된 셀 강조색
                        is_diff = data != df_orig_matrix.loc[data.index, data.columns]
                        return pd.DataFrame(np.where(is_diff, attr, ''), index=data.index, columns=data.columns)

                    st.dataframe(
                        df_req_display.style.format("{:,.0f}").apply(highlight_changes, axis=None),
                        use_container_width=True
                    )
                    # 신청 예산 표 스타일링 (기존과 값이 다르면 강조)
                    def highlight_changes(data):
                        attr = 'background-color: #fff3cd; color: #856404; font-weight: bold;'  # 변경된 셀 강조색
                        is_diff = data != df_orig_matrix.loc[data.index, data.columns]
                        return pd.DataFrame(np.where(is_diff, attr, ''), index=data.index, columns=data.columns)
                # 4. 하단 상세 정보 및 처리 버튼
                with st.container(border=True):
                    st.markdown(f"**📄 변경 신청 사유:**\n> {selected_row['변경사유']}")
                    st.write(f"📅 **협약변경기준일:** {selected_row['협약변경기준일']}")

    # ------------------------------------------
    # [B] 기업 권한 - 실적입력 및 예산변경 반영 신청
    # ------------------------------------------
    else:
        # 기업권한용 데이터셋 준비
        user_info = st.session_state.user_info
        org_code = user_info['기관고유코드']
        # 마스터 및 로그 데이터 읽기
        df_master_perf = conn.read(worksheet="Performance_Master")
        df_master_perf.columns = df_master_perf.columns.str.strip()
        user_data_df = df_master_perf[df_master_perf['기관고유코드'] == org_code]
        if user_data_df.empty:
            st.error(f"🚨 '{org_code}' 기관 정보를 찾을 수 없습니다.")
            st.stop()
        user_data = user_data_df.iloc[0].to_dict()
        existing_logs = conn.read(worksheet="Performance_Log", ttl=300)
        existing_logs.columns = existing_logs.columns.str.strip()
        if not existing_logs.empty and '기관고유코드' in existing_logs.columns:
            my_past_logs = existing_logs[existing_logs['기관고유코드'] == org_code]
        else:
            my_past_logs = pd.DataFrame()

        record_month_str = f"{today.year}-{target_month:02d}"

        st.title(f"📊 {user_data['기업명(기관명)']} 워크스페이스")
        total_budget = float(user_data.get('기업별_총사업비', 0))
        st.caption(
            f"기관고유코드: {user_data['기관고유코드']} | 사업유형: {user_data.get('사업유형', '')} | 배정 총사업비: {int(total_budget):,} 원")
        st.markdown("---")

        # 공통 세목 및 재원 정의
        categories = ['내부인건비', '과제수당', '구입설치_유형자산', '구입설치_무형자산', '구입설치_부대비용', '시설장비임차', '재료구입비', '제품제작비', '외부전문기술활용비',
                      '과제관리비']
        sources = ['국비', '지방비', '민간현금', '민간현물']

        # 탭 구성
        tab_input, tab_change = st.tabs(["📝 당월 실적 및 예산 집행 등록", "⚙️ 수행계획서 예산 변경 신청"])

        # ---------------------------------------------------------
        # TAB 1: 당월 실적 및 예산 집행 등록
        # ---------------------------------------------------------
        with tab_input:
            st.subheader(f"💰 1. 예산 집행 내역 ({target_month}월)")
            st.markdown("💡 **Tip:** 우측 표의 빈칸을 더블클릭하여 당월 집행 금액(원)을 입력하세요.")
            balance_data = []
            input_template = []
            for cat in categories:
                bal_row = {"세목": cat}
                in_row = {"세목": cat}
                for src in sources:
                    master_col = f"예산_{src}_{cat}"
                    log_col = f"집행_{src}_{cat}"
                    allocated = float(user_data.get(master_col, 0))
                    executed = my_past_logs[log_col].astype(
                        float).sum() if not my_past_logs.empty and log_col in my_past_logs.columns else 0
                    balance = allocated - executed
                    bal_row[src] = balance
                    in_row[src] = 0.0
                balance_data.append(bal_row)
                input_template.append(in_row)
            df_balance = pd.DataFrame(balance_data).set_index("세목")
            df_input = pd.DataFrame(input_template).set_index("세목")

            col_bal, col_inp = st.columns([1, 1])
            with col_bal:
                st.caption("🔍 **현재 재원별 잔액 현황 (Read-only)**")
                st.dataframe(df_balance.style.format("{:,.0f}"), use_container_width=True)

            with col_inp:
                st.caption("✍️ **당월 집행액 입력란 (더블클릭하여 수정)**")
                edited_df = st.data_editor(df_input, use_container_width=True, key="monthly_input_editor")

                # [수정] 입력된 데이터를 검증하고 전송용 딕셔너리로 변환하는 과정을 버튼 '밖'에서 준비만 합니다.
                budget_error = False
                flat_budget_inputs = {}
                total_monthly_executed = 0

                for cat in categories:
                    for src in sources:
                        input_val = float(edited_df.at[cat, src])
                        bal_val = float(df_balance.at[cat, src])
                        if input_val > bal_val:
                            budget_error = True
                            # 에러 메시지는 보여주되, 제출은 못하게 막는 용도
                        flat_budget_inputs[f"집행_{src}_{cat}"] = input_val
                        total_monthly_executed += input_val

                if budget_error:
                    st.error("🚨 입력한 금액이 잔액보다 큰 항목이 있습니다. 수정 후 제출해주세요.")

                st.info(f"**💸 당월 총 예산 집행액 합계:** {total_monthly_executed:,.0f} 원")
                st.markdown("---")

            # --- 2. 성과 지표 ---
            st.subheader("🎯 2. 성과 지표 입력")
            cols_quant = st.columns(4)
            quant_inputs = {}
            achieved_rates = []

            for i in range(1, 5):
                ind_name = user_data.get(f'성과지표{i}_지표명', '')
                if pd.isna(ind_name) or not str(ind_name).strip():
                    quant_inputs[f'실적_지표{i}'] = 0
                    continue

                ind_target = float(user_data.get(f'성과지표{i}_목표', 0))
                ind_unit = user_data.get(f'성과지표{i}_단위', '')
                log_col = f'실적_지표{i}'

                past_sum = my_past_logs[log_col].astype(
                    float).sum() if not my_past_logs.empty and log_col in my_past_logs.columns else 0

                with cols_quant[i - 1]:
                    label_text = f"{ind_name} (목표: {ind_target:g}{ind_unit} | 누적: {past_sum:g}{ind_unit})"
                    val = st.number_input(label_text, min_value=0.0, step=1.0, key=f"q_{i}")
                    quant_inputs[log_col] = val

                    cum_total = past_sum + val
                    rate = (cum_total / ind_target * 100) if ind_target > 0 else 0
                    achieved_rates.append(rate)

                    st.progress(min(int(rate), 100))
                    st.caption(f"당월 입력: {val:g} / 총 누적: {cum_total:g} {ind_unit}")
                    st.write(f"📈 **달성률: {rate:.1f}%**")

            total_achievement = sum(achieved_rates) / len(achieved_rates) if achieved_rates else 0
            st.success(f"**🎯 종합 평균 달성률:** {total_achievement:.1f} %")
            st.markdown("---")

            # --- 3. 수행 보고 ---
            st.subheader("📝 3. 수행 보고 및 우수 성과 제출")

            col_t1, col_t2 = st.columns(2)
            with col_t1:
                report_1 = st.text_area("당월 주요 수행내용", height=100, placeholder="이번 달에 추진한 핵심 업무와 성과를 요약해주세요.")
                report_2 = st.text_area("기타 성과 및 특이사항", height=100, placeholder="특이사항을 적어주세요.")
            with col_t2:
                report_3 = st.text_area("차월 수행 계획", height=100)
                pmo_support_options = ["선택안함", "사업계획/목표 변경 문의", "사업비 정산 문의", "기타 사업 운영/기술 지원 요청"]
                report_4_type = st.selectbox("PMO/주관기관 지원 요청 유형", options=pmo_support_options)
                report_4_detail = st.text_input("지원 요청 상세 내용 (선택)")

                final_report_4 = f"[{report_4_type}] {report_4_detail}" if report_4_type != "선택안함" else "특이사항 없음"

            evidence_file = st.file_uploader("📂 성과 증빙자료 업로드 (ZIP 권장)", type=['pdf', 'zip', 'jpg', 'png'])

            if st.button("🚀 최종 실적 제출", use_container_width=True):
                comp_name = user_data['기업명(기관명)']
                with st.spinner('실적 데이터 전송 중... ⚡'):
                    # 1. 파일 업로드 (기존 방식 유지)
                    file_link = upload_to_drive(evidence_file, f"{record_month_str}_{comp_name}_실적증빙")
                if budget_error:
                    st.error("🚨 잔액 초과 오류를 먼저 해결해주세요.")
                elif evidence_file is None:
                    st.error("🚨 필수 증빙자료 파일이 누락되었습니다.")
                else:
                    with st.spinner('저장 중입니다... ⏳'):
                        file_link = upload_to_drive(evidence_file, f"{record_month_str}_{comp_name}_실적증빙")
                        new_row = {
                            "제출일시": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "실적대상월": record_month_str,
                            "작성자ID": st.session_state.user_id,
                            "기관고유코드": org_code,
                            "기업명(기관명)": comp_name,
                            **flat_budget_inputs,
                            "당월_총집행액": total_monthly_executed,
                            **quant_inputs,
                            "성과_종합달성률": round(total_achievement, 2),
                            "성과업로드_증빙파일": file_link,
                            "당월 주요 수행내용": report_1,
                            "애로사항 및 리스크": report_2,
                            "차월 수행 계획": report_3,
                            "PMO/주관기관 지원 요청사항": final_report_4
                        }
                        conn = st.connection("gsheets", type=GSheetsConnection)
                        existing_data = conn.read(worksheet="Performance_Log", ttl=300)
                        updated_df = pd.concat([existing_data, pd.DataFrame([new_row])], ignore_index=True)
                        conn.update(worksheet="Performance_Log", data=updated_df)
                        st.cache_data.clear()
                        st.success(f"✅ ({record_month_str}) 집행예산 및 성과 제출이 완료되었습니다!")
                    st.cache_data.clear()

        # ---------------------------------------------------------
        # TAB 2: 수행계획서 예산 변경 신청
        # ---------------------------------------------------------
        with tab_change:
            st.subheader("📑 수행계획서 예산 변경 신청")
            st.info("💡 현재 협약 예산 내역입니다. 변경이 필요한 경우, 세목별 금액을 수정하여 신청해주세요.")

            # 현재 예산을 바탕으로 엑셀 그리드 생성
            req_budget_data = []
            for cat in categories:
                row = {"세목": cat}
                for src in sources:
                    master_col = f"예산_{src}_{cat}"
                    row[src] = float(user_data.get(master_col, 0))
                req_budget_data.append(row)

            df_req_budget = pd.DataFrame(req_budget_data).set_index("세목")

            st.caption("✍️ **변경 요청할 예산 입력란 (더블클릭하여 수정하세요)**")
            edited_req_df = st.data_editor(
                df_req_budget,
                use_container_width=True,
                key="req_grid",
                column_config={
                    "국비": st.column_config.NumberColumn("국비", format="%,d"),
                    "지방비": st.column_config.NumberColumn("지방비", format="%,d"),
                    "민간현금": st.column_config.NumberColumn("민간현금", format="%,d"),
                    "민간현물": st.column_config.NumberColumn("민간현물", format="%,d"),
                }
            )
            st.divider()
            col_r1, col_r2 = st.columns(2)
            with col_r1:
                change_date = st.date_input("협약변경기준일", value=today)
            with col_r2:
                change_file = st.file_uploader("📂 변경 승인 요청 공문 업로드 (필수, PDF)", type=['pdf'], key="change_file")

            change_reason = st.text_area("변경 신청 사유",
                                         placeholder="예: [비목 신설] 기존 재료비 부족으로 인한 외부기술활용비 -> 재료비 전용 요청",
                                         height=100)

            if st.button("📨 예산 변경 신청서 제출", type="primary", key="btn_budget_change"):
                # 1. 유효성 검사
                if not change_reason:
                    st.error("🚨 변경 사유를 입력해주세요.")
                elif change_file is None:
                    st.error("🚨 변경 승인 요청 공문을 업로드해주세요.")
                else:
                    # 2. 버튼 클릭 시에만 실행되는 프로세스
                    with st.spinner('신청서를 접수 중입니다... 🚀'):
                        try:
                            # 파일 업로드
                            doc_link = upload_to_drive(change_file,
                                                       f"{today.strftime('%Y%m%d')}_{user_data['기업명(기관명)']}_예산변경신청")

                            # 데이터 평탄화
                            flat_req_budget = {}
                            for cat in categories:
                                for src in sources:
                                    flat_req_budget[f"예산_{src}_{cat}"] = float(edited_req_df.at[cat, src])

                            # 전송 데이터 구성
                            change_row = {
                                "신청일시": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "기관고유코드": org_code,
                                "기업명(기관명)": user_data['기업명(기관명)'],
                                "협약변경기준일": change_date.strftime("%Y-%m-%d"),
                                "변경사유": change_reason,
                                "처리상태": "접수",
                                "증빙파일": doc_link,
                                **flat_req_budget
                            }

                            # GSheets 전송
                            change_conn = st.connection("gsheets", type=GSheetsConnection)
                            old_change_log = change_conn.read(worksheet="Budgetchange_req_Log",
                                                              ttl=60)  # 업데이트 주기ttl=60 (1분)
                            new_change_df = pd.concat([old_change_log, pd.DataFrame([change_row])], ignore_index=True)
                            change_conn.update(worksheet="Budgetchange_req_Log", data=new_change_df)

                            st.success("✅ 예산 변경 신청이 접수되었습니다.")
                            st.cache_data.clear()
                        except Exception as e:
                            st.error(f"⚠️ 저장 오류: {str(e)}")
