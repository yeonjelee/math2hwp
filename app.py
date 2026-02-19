import streamlit as st
from PIL import Image
import fitz  # PyMuPDF
import io
import re
from logic import get_hwp_conversion

# --------------------------------------------------------------------------
# 1. 페이지 설정
# --------------------------------------------------------------------------
st.set_page_config(page_title="Math HWP Agent", page_icon="🧮", layout="wide")

# --------------------------------------------------------------------------
# 2. 세션 상태 초기화
# --------------------------------------------------------------------------
if "converted_cache" not in st.session_state:
    st.session_state.converted_cache = {}  # { "키": "결과텍스트" }

if "problems_list" not in st.session_state:
    st.session_state.problems_list = []
    
if "curr_idx" not in st.session_state:
    st.session_state.curr_idx = 0

if "last_page_key" not in st.session_state:
    st.session_state.last_page_key = ""

# --------------------------------------------------------------------------
# 3. 유틸리티 함수
# --------------------------------------------------------------------------
def crop_image(img, mode):
    width, height = img.size
    if mode == "전체 페이지": return img
    elif mode == "왼쪽 절반": return img.crop((0, 0, width // 2, height))
    elif mode == "오른쪽 절반": return img.crop((width // 2, 0, width, height))
    elif mode == "위쪽 절반": return img.crop((0, 0, width, height // 2))
    elif mode == "아래쪽 절반": return img.crop((0, height // 2, width, height))
    return img

def parse_problems(text):
    """결과 텍스트를 '==== [번호] ====' 패턴으로 쪼개기"""
    # 프롬프트에서 강제한 구분자를 기준으로 분리
    parts = re.split(r'(?=====\s*\[.*?\]\s*====)', text)
    return [p.strip() for p in parts if p.strip()]

# --------------------------------------------------------------------------
# 4. 사이드바 UI
# --------------------------------------------------------------------------
with st.sidebar:
    st.title("🧮 설정 및 입력")
    
    # [API 키 입력 가이드]
    with st.expander("🔑 API 키 설정", expanded=False):
        user_api_key = st.text_input(
            "Google API Key", 
            type="password", 
            placeholder="AIzaSy...",
            help="입력한 키는 저장되지 않고 휘발됩니다."
        )

    st.divider()

    st.header("1️⃣ 파일 업로드")
    uploaded_file = st.file_uploader("교재 PDF/이미지", type=["pdf", "jpg", "png"])
    
    image_to_process = None
    page_key_prefix = "" 

    if uploaded_file:
        # PDF 처리
        if uploaded_file.type == "application/pdf":
            doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
            total_pages = len(doc)
            st.caption(f"총 {total_pages}페이지")
            
            # 페이지 선택
            page_num = st.number_input("페이지 선택", 1, total_pages, 1)
            
            # 이미지 변환 (줌 2배로 고화질)
            page = doc.load_page(page_num - 1)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            origin_image = Image.open(io.BytesIO(pix.tobytes()))
            
            page_key_prefix = f"{uploaded_file.name}_p{page_num}"
            
        # 이미지 파일 처리
        else:
            origin_image = Image.open(uploaded_file)
            page_key_prefix = uploaded_file.name

        st.markdown("---")
        st.header("2️⃣ 설정 및 영역 선택")
        
        # 🌟 문서 유형 선택 추가
        doc_type = st.radio("문서 유형", ["문제", "상세 해설", "빠른 정답"])
        
        # 영역 자르기
        crop_mode = st.selectbox("영역 선택", ["전체 페이지", "왼쪽 절반", "오른쪽 절반", "위쪽 절반", "아래쪽 절반"])
        image_to_process = crop_image(origin_image, crop_mode)
        
        # 키 생성 (문서 유형도 키에 포함시켜서 캐시 충돌 방지)
        page_key = f"{page_key_prefix}_{crop_mode}_{doc_type}"

        convert_btn = st.button("보이는 문제 전체 변환 🚀", type="primary", use_container_width=True)

# --------------------------------------------------------------------------
# 5. 메인 화면
# --------------------------------------------------------------------------
st.title("🧮 수학 문제 HWP 변환기")

if image_to_process:
    # 1) 원본 보기 토글
    with st.expander("📄 원본 이미지 확인하기 (클릭)", expanded=True):
        st.image(image_to_process, caption="변환 대상 영역", use_container_width=True)

    # 2) 변환 로직 (캐싱 적용)
    if convert_btn:
        if st.session_state.last_page_key != page_key:
            st.session_state.curr_idx = 0
            st.session_state.last_page_key = page_key

        if page_key in st.session_state.converted_cache:
            st.success("⚡ 저장된 결과를 불러왔습니다! (API 미사용)")
            result_text = st.session_state.converted_cache[page_key]
            st.session_state.problems_list = parse_problems(result_text)
            
        else:
            with st.spinner(f"🤖 AI가 페이지 내 모든 {doc_type}을(를) 분석 중입니다..."):
                # doc_type 전달
                result_text = get_hwp_conversion(image_to_process, doc_type, user_api_key)
                
                if "API 오류" not in result_text and "키가 없습니다" not in result_text:
                    st.session_state.converted_cache[page_key] = result_text
                    st.session_state.problems_list = parse_problems(result_text)
                    st.session_state.curr_idx = 0
                else:
                    st.error(result_text)

    # 3) 결과 뷰어 (하나씩 보기)
    if st.session_state.problems_list:
        st.divider()
        st.subheader("📝 변환 결과")
        
        # 네비게이션
        c1, c2, c3 = st.columns([1, 2, 1])
        with c1:
            if st.button("⬅️ 이전 문제"):
                if st.session_state.curr_idx > 0: st.session_state.curr_idx -= 1
        with c2:
            cur = st.session_state.curr_idx + 1
            tot = len(st.session_state.problems_list)
            st.markdown(f"<div style='text-align:center; font-size:1.2em;'><b>항목 {cur} / {tot}</b></div>", unsafe_allow_html=True)
        with c3:
            if st.button("다음 문제 ➡️"):
                if st.session_state.curr_idx < tot - 1: st.session_state.curr_idx += 1
        
        # 코드 출력
        st.info("우측 상단의 복사(Copy) 아이콘을 눌러 한글(HWP)에 붙여넣으세요.")
        target_prob = st.session_state.problems_list[st.session_state.curr_idx]
        st.code(target_prob, language="text")
        
else:
    st.info("👈 왼쪽 사이드바에서 PDF를 업로드하고 API 키를 입력하세요.")