import streamlit as st
from PIL import Image
import fitz  # PyMuPDF
import io
import re
from logic import get_hwp_conversion

# --------------------------------------------------------------------------
# 1. 페이지 설정
# --------------------------------------------------------------------------
st.set_page_config(page_title="Math HWP Agent", 
                   page_icon="🧮", 
                   layout="wide", 
                  initial_sidebar_state="collapsed")

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
    """결과 텍스트를 쪼개고 ==== [번호] ==== 부분은 화면에서 보이지 않게 제거하기"""
    parts = re.split(r'(?=====\s*\[.*?\]\s*====)', text)
    
    cleaned_parts = []
    for p in parts:
        if p.strip():
            # ==== [번호] ==== 패턴을 찾아서 빈 문자열로 싹 지워버림
            cleaned_text = re.sub(r'====\s*\[.*?\]\s*====\s*', '', p).strip()
            if cleaned_text:  # 지우고 나서 내용이 남아있으면 리스트에 추가
                cleaned_parts.append(cleaned_text)
                
    return cleaned_parts

# --------------------------------------------------------------------------
# 4. 사이드바 UI
# --------------------------------------------------------------------------
with st.sidebar:
    st.title("🧮 설정 및 입력")
    
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

    st.markdown("---")
    st.header("2️⃣ 설정 및 영역 선택")
    
    doc_type = st.radio("문서 유형", ["문제", "상세 해설", "빠른 정답"])
    crop_mode = st.selectbox("영역 선택", ["전체 페이지", "왼쪽 절반", "오른쪽 절반", "위쪽 절반", "아래쪽 절반"])
    
    convert_btn = st.button("보이는 문제 전체 변환 🚀", type="primary", use_container_width=True)

# --------------------------------------------------------------------------
# 5. 메인 화면
# --------------------------------------------------------------------------
st.title("🧮 수학 문제 HWP 변환기")

if uploaded_file:
    # 🌟 메인 화면에서 파일 처리 및 페이지 선택 수행 🌟
    if uploaded_file.type == "application/pdf":
        doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
        total_pages = len(doc)
        
        # 페이지 선택 입력창을 메인 화면 상단에 배치
        col1, col2 = st.columns([1, 4])
        with col1:
            page_num = st.number_input(f"📄 페이지 선택 (총 {total_pages}장)", min_value=1, max_value=total_pages, value=1)
        
        page = doc.load_page(page_num - 1)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        origin_image = Image.open(io.BytesIO(pix.tobytes()))
        page_key_prefix = f"{uploaded_file.name}_p{page_num}"
    else:
        origin_image = Image.open(uploaded_file)
        page_key_prefix = uploaded_file.name

    image_to_process = crop_image(origin_image, crop_mode)
    page_key = f"{page_key_prefix}_{crop_mode}_{doc_type}"

    st.divider()

    # 원본 이미지 끄기/켜기 토글 스위치
    show_image = st.toggle("📄 원본 이미지 함께 보기", value=True, help="스위치를 끄면 결과창이 전체 너비로 확장됩니다.")
    
    if show_image:
        col_left, col_right = st.columns(2)
        with col_left:
            st.image(image_to_process, caption="변환 대상 영역", use_container_width=True)
        result_container = col_right
    else:
        result_container = st.container()

    # ---------------- 변환 및 결과 출력 영역 ----------------
    with result_container:
        st.subheader("📝 변환 결과")
        
        if convert_btn:
            if st.session_state.last_page_key != page_key:
                st.session_state.curr_idx = 0
                st.session_state.last_page_key = page_key

            if page_key in st.session_state.converted_cache:
                st.success("⚡ 저장된 결과를 불러왔습니다!")
                result_text = st.session_state.converted_cache[page_key]
                st.session_state.problems_list = parse_problems(result_text)
                
            else:
                with st.spinner(f"🤖 AI가 페이지 내 모든 {doc_type}을(를) 분석 중입니다..."):
                    result_text = get_hwp_conversion(image_to_process, doc_type, user_api_key)
                    
                    if "API 오류" not in result_text and "키가 없습니다" not in result_text:
                        st.session_state.converted_cache[page_key] = result_text
                        st.session_state.problems_list = parse_problems(result_text)
                        st.session_state.curr_idx = 0
                    else:
                        st.error(result_text)

        if st.session_state.problems_list:
            c1, c2, c3 = st.columns([1, 2, 1])
            with c1:
                if st.button("⬅️ 이전 문제"):
                    if st.session_state.curr_idx > 0: st.session_state.curr_idx -= 1
            with c2:
                cur = st.session_state.curr_idx + 1
                tot = len(st.session_state.problems_list)
                st.markdown(f"<div style='text-align:center; font-size:1.1em;'><b>항목 {cur} / {tot}</b></div>", unsafe_allow_html=True)
            with c3:
                if st.button("다음 문제 ➡️"):
                    if st.session_state.curr_idx < tot - 1: st.session_state.curr_idx += 1
            
            st.info("우측 상단의 복사(Copy) 아이콘을 눌러 한글(HWP)에 붙여넣으세요.")
            target_prob = st.session_state.problems_list[st.session_state.curr_idx]
            st.code(target_prob, language="text")
        else:
            st.info("👈 사이드바의 '보이는 문제 전체 변환 🚀' 버튼을 누르면 여기에 결과가 나타납니다.")
        
else:
    st.info("👈 왼쪽 사이드바에서 PDF를 업로드하세요.")
