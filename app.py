import streamlit as st
from PIL import Image
import fitz  # PyMuPDF
import io
import re
from logic import get_hwp_conversion

# --------------------------------------------------------------------------
# 1. 페이지 설정 (사이드바 관련 옵션 제거)
# --------------------------------------------------------------------------
st.set_page_config(page_title="Math HWP Agent", 
                   page_icon="🧮", 
                   layout="wide")

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

# 🌟 "1, 2, 4-6" -> [1, 2, 4, 5, 6] 으로 쪼개주는 스마트 파서 추가 🌟
def parse_page_numbers(page_str, max_pages):
    pages = set()
    for part in page_str.split(','):
        part = part.strip()
        if not part: continue
        if '-' in part:
            try:
                start, end = map(int, part.split('-'))
                if 1 <= start <= end <= max_pages:
                    pages.update(range(start, end + 1))
            except: pass
        else:
            try:
                p = int(part)
                if 1 <= p <= max_pages:
                    pages.add(p)
            except: pass
    return sorted(list(pages))

# --------------------------------------------------------------------------
# 4. 메인 화면 UI 및 설정 (사이드바 없음)
# --------------------------------------------------------------------------
st.title("🧮 수학 문제 HWP 변환기 (일괄 처리 지원)")

# API 키 설정
with st.expander("🔑 API 키 설정", expanded=False):
    user_api_key = st.text_input(
        "Google API Key", 
        type="password", 
        placeholder="AIzaSy...",
        help="입력한 키는 저장되지 않고 휘발됩니다."
    )

# 파일 업로드
uploaded_file = st.file_uploader("교재 PDF/이미지 업로드", type=["pdf", "jpg", "png"])

if uploaded_file:
    images_to_process = []
    page_key_prefix = ""
    
    if uploaded_file.type == "application/pdf":
        doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
        total_pages = len(doc)
        
        # 🌟 UI 변경: 텍스트 입력창으로 여러 페이지 받기 🌟
        col_page, _ = st.columns([1.5, 3.5])
        with col_page:
            page_input = st.text_input(
                f"📄 변환할 페이지 입력 (총 {total_pages}장)", 
                value="1", 
                help="쉼표(,)나 하이픈(-)을 사용. 예: 1, 3, 5-7"
            )
        
        selected_pages = parse_page_numbers(page_input, total_pages)
        if not selected_pages:
            st.warning("유효한 페이지 번호를 입력해주세요.")
            
        page_key_prefix = f"{uploaded_file.name}_pages_{'_'.join(map(str, selected_pages))}"
    else:
        origin_image = Image.open(uploaded_file)
        page_key_prefix = uploaded_file.name
        selected_pages = [1] # 이미지는 기본 1장 취급

    st.markdown("---")

    # 헤더 영역: 설정 및 변환 버튼
    set_c1, set_c2, set_c3 = st.columns([1.5, 1.5, 1])
    
    with set_c1:
        doc_type = st.radio("문서 유형", ["문제", "상세 해설", "빠른 정답"], horizontal=True)
    with set_c2:
        crop_mode = st.selectbox("영역 선택 (선택한 모든 페이지 적용)", ["전체 페이지", "왼쪽 절반", "오른쪽 절반", "위쪽 절반", "아래쪽 절반"])
    with set_c3:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        # 🌟 버튼 텍스트 변경: 호출을 강조 🌟
        convert_btn = st.button(f"선택한 {len(selected_pages)}페이지 일괄 변환 🚀", type="primary", use_container_width=True)

    # 🌟 선택한 페이지들을 모두 이미지 리스트로 만들기 🌟
    if uploaded_file.type == "application/pdf" and selected_pages:
        for p_num in selected_pages:
            page = doc.load_page(p_num - 1)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img = Image.open(io.BytesIO(pix.tobytes()))
            images_to_process.append(crop_image(img, crop_mode))
    elif uploaded_file.type != "application/pdf":
        images_to_process.append(crop_image(origin_image, crop_mode))

    page_key = f"{page_key_prefix}_{crop_mode}_{doc_type}"

    st.divider()

    # ---------------- 좌/우 분할 뷰어 (원본 이미지 & 변환 결과) ----------------
    show_image = st.toggle("📄 원본 이미지 함께 보기", value=True, help="스위치를 끄면 결과창이 전체 너비로 확장됩니다.")
    
    if show_image and images_to_process:
        col_left, col_right = st.columns(2)
        with col_left:
            # 🌟 여러 장을 스크롤 내리며 볼 수 있게 렌더링 🌟
            for idx, img in enumerate(images_to_process):
                st.image(img, caption=f"변환 대상: 페이지 {selected_pages[idx] if uploaded_file.type == 'application/pdf' else '이미지'}", use_container_width=True)
        result_container = col_right
    else:
        result_container = st.container()

    # 결과 출력 영역
    with result_container:
        st.subheader("📝 변환 결과")
        
        if convert_btn and images_to_process:
            if st.session_state.last_page_key != page_key:
                st.session_state.curr_idx = 0
                st.session_state.last_page_key = page_key

            if page_key in st.session_state.converted_cache:
                st.success("⚡ 저장된 결과를 불러왔습니다!")
                result_text = st.session_state.converted_cache[page_key]
                st.session_state.problems_list = parse_problems(result_text)
                
            else:
                # API 호출! 리스트가 통째로 넘어감
                with st.spinner(f"🤖 AI가 {len(images_to_process)}장의 페이지에서 모든 {doc_type}을(를) 분석 중입니다..."):
                    result_text = get_hwp_conversion(images_to_process, doc_type, user_api_key)
                    
                    if "API 오류" not in result_text and "키가 없습니다" not in result_text and "🚨" not in result_text:
                        st.session_state.converted_cache[page_key] = result_text
                        st.session_state.problems_list = parse_problems(result_text)
                        st.session_state.curr_idx = 0
                    else:
                        st.error(result_text)

        if st.session_state.problems_list:
            c1, c2, c3 = st.columns([1, 2, 1])
            with c1:
                if st.button("⬅️ 이전 항목"):
                    if st.session_state.curr_idx > 0: st.session_state.curr_idx -= 1
            with c2:
                cur = st.session_state.curr_idx + 1
                tot = len(st.session_state.problems_list)
                st.markdown(f"<div style='text-align:center; font-size:1.1em;'><b>항목 {cur} / {tot}</b></div>", unsafe_allow_html=True)
            with c3:
                if st.button("다음 항목 ➡️"):
                    if st.session_state.curr_idx < tot - 1: st.session_state.curr_idx += 1
            
            st.info("우측 상단의 복사(Copy) 아이콘을 눌러 한글(HWP)에 붙여넣으세요.")
            target_prob = st.session_state.problems_list[st.session_state.curr_idx]
            st.code(target_prob, language="text")
        else:
            st.info("👆 위에 있는 버튼을 누르면 여기에 결과가 나타납니다.")
        
else:
    st.info("👆 위에 파일을 먼저 업로드해 주세요.")
