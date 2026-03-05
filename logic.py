import google.generativeai as genai
import os
import time
import re
from dotenv import load_dotenv
from PIL import Image
import streamlit as st
from google.api_core import exceptions

# 로컬 테스트용 환경 변수 로드
load_dotenv()

def optimize_image(image):
    """
    이미지 최적화: 흑백 변환 + 리사이징 (토큰 절약)
    """
    img = image.convert('L') # 흑백
    max_size = 1024
    width, height = img.size
    
    if max(width, height) > max_size:
        ratio = max_size / float(max(width, height))
        new_width = int(width * ratio)
        new_height = int(height * ratio)
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    return img

# 🌟 파이썬 정규식을 활용한 확실한 'rm' 후처리 함수 🌟
def apply_hwp_rm_rule(text):
    # HWP 수식 예약어 (대문자로 된 명령어들은 rm을 붙이면 안 됨)
    reserved = {"LEFT", "RIGHT", "SUCC", "PREC", "GE", "LE", "OVER", "ROOT", "OF", "CDOT", "CDOTS"}
    
    # 정규식 설명: 앞/뒤에 다른 알파벳이 없는 대문자 묶음을 찾음. (단, 이미 앞에 'rm '이 있는 경우는 제외)
    pattern = r'(?<!rm )(?<![a-zA-Z])([A-Z]+)(?![a-zA-Z])'
    
    def repl(m):
        word = m.group(1)
        # 예약어인 경우 그대로 반환
        if word in reserved:
            return word
        # 일반 대문자 변수(A, B, ABC 등)인 경우 앞에 'rm '을 붙임
        return f"rm {word}"
        
    return re.sub(pattern, repl, text)

def get_hwp_conversion(images_list, doc_type, user_api_key=None):
    """
    gemini-flash-latest 모델을 강제로 사용하여 HWP 수식 변환
    여러 장의 이미지(images_list)를 한 번에 받아서 처리함
    """
    
    final_key = user_api_key
    if not final_key:
        final_key = os.getenv("GOOGLE_API_KEY")
        if not final_key:
            try:
                final_key = st.secrets["GOOGLE_API_KEY"]
            except:
                pass
    
    if not final_key:
        return "🚫 API 키가 없습니다. 사이드바에서 키를 입력해주세요."

    try:
        genai.configure(api_key=final_key)
        
        model = genai.GenerativeModel('gemini-flash-latest')
        
        # 문서 유형별 추가 지시사항
        if doc_type == "문제":
            doc_instruction = "풀이나 정답은 무시하고, 각 문제의 지문과 수식만 추출하라."
        elif doc_type == "상세 해설":
            doc_instruction = "각 문제 번호에 해당하는 상세한 풀이 과정(해설)과 수식을 추출하라."
        else: # 빠른 정답
            doc_instruction = "각 문제 번호와 그에 해당하는 최종 정답만 추출하라. 긴 풀이 과정은 생략하라."

        system_prompt = f"""
        너는 대한민국 수학 교재 편집 전문가다. 
        주어진 이미지에서 **식별 가능한 모든 수학 내용**을 찾아 '한글(HWP) 수식 스크립트'로 변환하라.
        
        [작업 지침]
        1. 이미지에 보이는 **모든 문항/해설/정답**을 순서대로 변환하라.
        2. 불필요한 요소(쪽번호 등)는 무시하라.
        3. 문서 유형: {doc_type}. {doc_instruction}

        [출력 구조 규칙 - 🚨매우 중요🚨]
        각 항목을 시작할 때는 반드시 다음과 같이 고유한 번호 구분자로 시작하라.
        ==== [문제 번호] ==== 
        (예: ==== [0383] ====, ==== [1] ====)

        🚨 마크다운 코드 블록(```text, ``` 등)은 절대 사용하지 말고, 오직 '일반 텍스트'로만 출력하라.
        지문(또는 해설)을 먼저 작성하고, 수식은 본문 아래에 [1], [2] 등 번호를 매겨 따로 나열하라.
        
        🚨 [수식 및 기호 100% 분리 원칙]
        문제나 해설 텍스트 내에 존재하는 **모든 숫자, 영어 알파벳, 수학 기호, 수식**은 단 하나도 빠짐없이 
        [1], [2] 와 같이 기호로 치환하고, 하단에 HWP 수식 스크립트로 따로 작성하라.
        (본문 텍스트에는 순수 한글만 남아있어야 한다.)
        
        🚨 [쉼표(,) 나열 묶음 규칙 - 반드시 지킬 것!]
        수식, 숫자, 기호가 쉼표(,)로 나열된 경우(예: A, B, C 또는 x=1, y=2 등), 본문에서 이를 절대 개별적으로 쪼개지 말고 **전체를 묶어서 단일 기호(예: [1])**로 치환하라.
        그리고 하단 수식 스크립트에 작성할 때 쉼표(,) 뒤에 반드시 물결표(~)를 넣어 간격을 띄워라.
        (잘못된 예시: 본문 "두 점 [1], [2], [3]에서" -> [1]: A ` / [2]: B ` / [3]: C ` )
        (올바른 예시: 본문 "두 점 [1]에서" -> [1]: A,~B,~C ` )
        
        **출력 형태 예시**
        ==== [0383] ====
        (지문 또는 해설 내용... 쉼표로 나열된 기호는 한 번에 묶어서 [1]로 치환)
        
        [1]
        x=1,~y=2` 

        [2]
        5` 
        
        ---

        [HWP 수식 문법 (절대 준수 규칙)]
        1. **끝맺음:** 모든 수식 끝에는 반드시 백틱(`)이 필수다. (예: y=x^2` )
        2. **나열 및 간격:** 여러 수식이나 기호를 나열할 때 쉼표(,) 뒤에는 반드시 물결표(~)를 사용하여 간격을 띄워라. (예: A,~B,~C / 1,~2,~cdots,~n)
        3. **괄호 묶기:** 첨자나 분모/분자가 두 글자 이상일 경우 반드시 중괄호 {{ }}로 묶어라. (예: a_{{n+1}}, x^{{2n}})
        4. **분수와 근호:** 분수는 `{{분자}} over {{분모}}`, 루트는 `root {{n}} of {{x}}` (제곱근은 n 생략)
        5. **연산 및 대소 기호:**
           - 크다/작다: `SUCC`, `PREC`
           - 크거나 같다 / 작거나 같다: `GE` / `LE`
           - 같지 않다: `!=`
           - 플러스마이너스: `+-`
           - 줄임표(점점점): `cdots`
        6. **도형 및 기하:**
           - 선분: `overline {{AB}}`
           - 벡터: `vec {{v}}` 또는 `vec {{AB}}`
           - 삼각형: `triangle ABC`, 각(`∠`): `angle A`
           - 각도의 도(°): 반드시 숫자 뒤에 `DEG`를 사용하라. (예: 30°, 90° -> 30 DEG, 90 DEG)
           - 수직: `bot`, 평행: `//`
        7. **집합 및 논리:**
           - 원소이다/아니다: `in` / `notin`
           - 부분집합: `sub` (또는 `subset`)
           - 합집합/교집합: `cup` / `cap`
           - 공집합: `empty`
           - 그러므로/왜냐하면: `therefore` / `because`
        8. **미적분 및 함수:**
           - 극한과 시그마: `lim _{{x -> a}}`, `sum _{{k=1}} ^{{n}}`
           - 적분: `int _{{a}} ^{{b}} f(x) dx`
           - 무한대: `inf`
           - 삼각/로그 띄어쓰기: log, sin, cos 등은 띄어쓰기 대신 백틱(`) 사용. (예: log`5, sin`A)
        9. **그리스 문자:** 파이(`pi`), 세타(`theta`), 알파(`alpha`), 베타(`beta`) 등은 영문 소문자로 그대로 작성하라.
        10. **대문자 알파벳:** 수식 내에 대문자 알파벳(A, B, P 등)이 들어갈 경우, 반드시 글자 앞에 `rm `을 붙여라. (예: rm A, rm B, rm P 등)
        """

        # 🌟 여러 이미지를 하나의 배열로 합쳐서 프롬프트 구성
        prompt_parts = [system_prompt]
        for img in images_list:
            prompt_parts.append(optimize_image(img))

        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 합쳐진 프롬프트 배열을 한 번의 API 호출로 전송!
                response = model.generate_content(prompt_parts)
                
                result_text = response.text
                final_processed_text = apply_hwp_rm_rule(result_text)
                
                return final_processed_text
            
            except exceptions.ResourceExhausted:
                time.sleep(5)
                continue
            except Exception as e:
                return f"🚨 오류 발생: {str(e)}"

        return "🚫 사용량이 많아 잠시 제한되었습니다. 1분 뒤 다시 시도해주세요."

    except Exception as e:
        return f"🚨 설정 오류: {str(e)}"
