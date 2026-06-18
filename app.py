import io
import os
import xml.etree.ElementTree as ET
import zipfile

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    from docx import Document as DocxDocument
except ImportError:
    DocxDocument = None

try:
    import olefile
except ImportError:
    olefile = None

load_dotenv()

MODEL_NAME = "gpt-5.4-nano"
MAX_DOC_CHARS = 8000
HWP_FAIL_MESSAGE = (
    "해당 한글 문서는 텍스트 추출이 어렵습니다. "
    "PDF 또는 DOCX로 변환 후 다시 업로드해주세요."
)

SYSTEM_PROMPT_BASE = (
    "당신은 '마법사 AI'입니다. 사용자의 질문에 한국어로, 핵심만 간결하게 "
    "답변하세요. 다음 규칙을 반드시 지키세요.\n"
    "1. 답변 본문은 3~5문장 또는 5개 이하의 짧은 불릿으로 제한합니다. "
    "장황한 서론과 사족은 쓰지 않습니다.\n"
    "2. 본문 마지막에는 반드시 빈 줄을 두고 아래 형식의 추천을 덧붙입니다.\n\n"
    "🔮 **다음으로 해볼 작업**\n"
    "- (실행 가능한 다음 단계 1)\n"
    "- (실행 가능한 다음 단계 2, 선택)\n\n"
    "추천은 1~2개만, 사용자가 바로 시도할 수 있는 구체적인 행동으로 적어주세요."
)

DOC_INSTRUCTION = (
    "\n\n사용자가 업로드한 문서가 아래 <document> 태그 안에 있습니다. "
    "이 문서 내용을 우선 근거로 답변하세요. 문서에 명시되지 않은 내용은 "
    "추측하지 말고 '업로드된 문서에서 확인하기 어렵습니다'라고 답해주세요."
)

WEB_INSTRUCTION = (
    "\n\n사용자가 웹검색 모드를 켰습니다. 학습 시점 이후의 최신 정보가 "
    "필요할 수 있다는 점을 인지하고, 확실하지 않은 사실은 솔직하게 모른다고 "
    "말한 뒤 사용자가 직접 검색해 확인하도록 안내해주세요."
)

EXAMPLE_QUESTIONS = [
    "🪄 Streamlit으로 간단한 챗봇을 만드는 방법을 알려줘",
    "📜 OpenAI API 키는 어디에 안전하게 저장해야 할까?",
    "✨ 파이썬 초보가 다음으로 배우면 좋은 주제를 추천해줘",
]


def extract_pdf(data: bytes) -> str:
    if PdfReader is None:
        raise RuntimeError("pypdf가 설치되어 있지 않습니다. `uv sync`로 설치해주세요.")
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def extract_docx(data: bytes) -> str:
    if DocxDocument is None:
        raise RuntimeError("python-docx가 설치되어 있지 않습니다. `uv sync`로 설치해주세요.")
    doc = DocxDocument(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs).strip()


def extract_hwpx(data: bytes) -> str:
    texts: list[str] = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        section_names = sorted(
            name for name in zf.namelist()
            if name.startswith("Contents/section") and name.endswith(".xml")
        )
        if not section_names:
            raise ValueError("HWPX 본문 섹션을 찾지 못했습니다.")
        for name in section_names:
            with zf.open(name) as f:
                tree = ET.parse(f)
            for elem in tree.iter():
                tag = elem.tag.rsplit("}", 1)[-1] if "}" in elem.tag else elem.tag
                if tag == "t" and elem.text:
                    texts.append(elem.text)
    return "\n".join(texts).strip()


def extract_hwp(data: bytes) -> str:
    if olefile is None:
        raise RuntimeError("olefile이 설치되어 있지 않습니다. `uv sync`로 설치해주세요.")
    ole = olefile.OleFileIO(io.BytesIO(data))
    try:
        if not ole.exists("PrvText"):
            raise ValueError("PrvText 스트림이 없습니다.")
        raw = ole.openstream("PrvText").read()
    finally:
        ole.close()
    return raw.decode("utf-16-le", errors="ignore").strip()


EXTRACTORS = {
    "pdf": extract_pdf,
    "docx": extract_docx,
    "hwpx": extract_hwpx,
    "hwp": extract_hwp,
}


def extract_text(filename: str, data: bytes) -> tuple[str | None, str | None]:
    ext = filename.rsplit(".", 1)[-1].lower()
    extractor = EXTRACTORS.get(ext)
    if extractor is None:
        return None, f"지원하지 않는 파일 형식이에요: .{ext}"
    try:
        text = extractor(data)
    except Exception as e:
        if ext in ("hwp", "hwpx"):
            return None, HWP_FAIL_MESSAGE
        return None, f"파일을 읽는 중 문제가 생겼어요. (오류: {e})"
    if not text:
        if ext in ("hwp", "hwpx"):
            return None, HWP_FAIL_MESSAGE
        return None, "추출된 텍스트가 비어 있습니다."
    return text, None


st.set_page_config(
    page_title="나의 마법 AI 프로젝트 챗봇",
    page_icon="🔮",
    layout="centered",
)

st.markdown(
    """
    <style>
        .stApp {
            background: radial-gradient(circle at 20% 10%, #2b1055 0%, #1a0938 40%, #0d041f 100%);
            color: #f3e9ff;
        }
        .stApp, .stApp p, .stApp li, .stApp span, .stApp label,
        .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
        .stApp div, .stApp strong, .stApp em, .stApp code {
            color: #f3e9ff !important;
        }
        .stApp a { color: #fcd34d !important; }
        .stApp code {
            background: rgba(255, 255, 255, 0.08) !important;
            padding: 0.05rem 0.35rem;
            border-radius: 6px;
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #1f0d3d 0%, #100525 100%);
            border-right: 1px solid rgba(192, 132, 252, 0.25);
        }
        [data-testid="stSidebar"] * { color: #f3e9ff !important; }
        [data-testid="stSidebar"] h3 { color: #fcd34d !important; }
        [data-testid="stFileUploaderDropzone"] {
            background: rgba(255, 255, 255, 0.05) !important;
            border: 1px dashed rgba(192, 132, 252, 0.5) !important;
        }
        .magic-title, .magic-title * {
            -webkit-text-fill-color: transparent !important;
            color: transparent !important;
        }
        .magic-title {
            text-align: center;
            font-size: 2.2rem;
            font-weight: 800;
            background: linear-gradient(90deg, #c084fc, #f0abfc, #fcd34d);
            -webkit-background-clip: text;
            margin-bottom: 0.2rem;
        }
        .magic-sub {
            text-align: center;
            color: #d8b4fe !important;
            margin-bottom: 1.2rem;
            font-size: 0.95rem;
        }
        .magic-card {
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(192, 132, 252, 0.35);
            border-radius: 14px;
            padding: 0.9rem 1.1rem;
            margin-bottom: 1rem;
            box-shadow: 0 0 18px rgba(168, 85, 247, 0.15);
        }
        .magic-card h4 { margin: 0 0 0.4rem 0; color: #fcd34d !important; font-size: 1rem; }
        .magic-card p, .magic-card li { font-size: 0.92rem; margin: 0.15rem 0; }
        div.stButton > button {
            width: 100%;
            background: rgba(139, 92, 246, 0.18);
            color: #f5f3ff !important;
            border: 1px solid rgba(192, 132, 252, 0.5);
            border-radius: 12px;
            padding: 0.55rem 0.7rem;
            font-size: 0.88rem;
            transition: all 0.2s ease-in-out;
        }
        div.stButton > button:hover {
            background: rgba(192, 132, 252, 0.35);
            border-color: #fcd34d;
            color: #fff !important;
            transform: translateY(-1px);
        }
        [data-testid="stChatMessage"] {
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(192, 132, 252, 0.2);
            border-radius: 14px;
            padding: 0.6rem 0.9rem;
        }
        [data-testid="stChatInput"] textarea {
            background: #ffffff !important;
            color: #1a0938 !important;
            caret-color: #1a0938 !important;
        }
        [data-testid="stChatInput"] textarea::placeholder { color: #6b7280 !important; }
        [data-testid="stChatInput"] > div {
            background: #ffffff !important;
            border-radius: 12px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### 🪄 마법 설정")
    use_web_search = st.checkbox(
        "🌐 웹검색 사용하기",
        value=False,
        help="최신 정보가 필요할 때 모델이 한계를 인지하도록 합니다.",
    )
    use_doc_qa = st.checkbox(
        "📚 문서 기반 답변 사용하기",
        value=False,
        help="아래에 업로드한 문서 내용을 근거로 답변합니다.",
    )

    st.markdown("---")
    st.markdown("#### 📎 문서 업로드")
    uploaded_file = st.file_uploader(
        "PDF · DOCX · HWP · HWPX",
        type=["pdf", "docx", "hwp", "hwpx"],
        accept_multiple_files=False,
        label_visibility="collapsed",
    )

    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        cache_key = (uploaded_file.name, len(file_bytes))
        if st.session_state.get("doc_cache_key") != cache_key:
            text, err = extract_text(uploaded_file.name, file_bytes)
            st.session_state.doc_cache_key = cache_key
            st.session_state.doc_text = text
            st.session_state.doc_error = err
            st.session_state.doc_name = uploaded_file.name
            st.session_state.doc_ext = uploaded_file.name.rsplit(".", 1)[-1].lower()

        st.markdown(
            f"""
            <div class="magic-card" style="margin-top:0.6rem;">
                <p>📄 <b>파일명</b>: {st.session_state.doc_name}</p>
                <p>🧾 <b>형식</b>: .{st.session_state.doc_ext.upper()}</p>
                <p>✍️ <b>추출 글자 수</b>: {len(st.session_state.doc_text):,}자</p>
            </div>
            """ if st.session_state.get("doc_text") else
            f"""
            <div class="magic-card" style="margin-top:0.6rem;">
                <p>📄 <b>파일명</b>: {uploaded_file.name}</p>
                <p>🧾 <b>형식</b>: .{uploaded_file.name.rsplit('.', 1)[-1].upper()}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.session_state.get("doc_text") and len(st.session_state.doc_text) > MAX_DOC_CHARS:
            st.caption(f"⚠️ 문서가 길어서 앞 {MAX_DOC_CHARS:,}자만 답변에 사용합니다.")
        if st.session_state.get("doc_error"):
            st.warning(st.session_state.doc_error)
    else:
        for k in ("doc_cache_key", "doc_text", "doc_error", "doc_name", "doc_ext"):
            st.session_state.pop(k, None)

    st.markdown("---")
    if st.button("🧹 대화 초기화"):
        st.session_state.messages = []
        st.rerun()

st.markdown(
    '<div class="magic-title">🪄 나의 마법 AI 프로젝트 챗봇 🔮</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="magic-sub">요술지팡이를 흔들고 수정 구슬에 물어보세요 ✨</div>',
    unsafe_allow_html=True,
)

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    st.error(
        "OPENAI_API_KEY를 찾을 수 없습니다. 프로젝트 폴더의 .env 파일에 "
        "OPENAI_API_KEY=sk-... 형태로 키를 저장한 뒤 앱을 다시 실행해주세요."
    )
    st.stop()

client = OpenAI(api_key=api_key)

if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_prompt" not in st.session_state:
    st.session_state.pending_prompt = None

if not st.session_state.messages:
    st.markdown(
        """
        <div class="magic-card">
            <h4>📖 사용 방법</h4>
            <p>1. 아래 입력창에 궁금한 점을 적고 Enter를 누르세요.</p>
            <p>2. 예시 질문 버튼을 눌러 바로 시작할 수도 있어요.</p>
            <p>3. 사이드바에서 <b>웹검색</b> · <b>문서 기반 답변</b>을 켤 수 있어요.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("##### ✨ 이런 질문을 해보세요")
    cols = st.columns(3)
    for col, question in zip(cols, EXAMPLE_QUESTIONS):
        with col:
            if st.button(question, key=f"example_{question}"):
                st.session_state.pending_prompt = question
                st.rerun()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

user_input = st.chat_input("🪄 무엇이든 물어보세요…")
prompt = user_input or st.session_state.pending_prompt
st.session_state.pending_prompt = None

if prompt:
    if use_doc_qa and not st.session_state.get("doc_text"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            guide = (
                "📎 먼저 문서를 업로드해주세요. 사이드바의 업로드 영역에서 "
                "PDF / DOCX / HWPX / HWP 파일을 올린 뒤 다시 질문해주세요."
            )
            st.markdown(guide)
            st.session_state.messages.append({"role": "assistant", "content": guide})
    else:
        system_prompt = SYSTEM_PROMPT_BASE
        if use_web_search:
            system_prompt += WEB_INSTRUCTION
        if use_doc_qa and st.session_state.get("doc_text"):
            doc_snippet = st.session_state.doc_text[:MAX_DOC_CHARS]
            system_prompt += (
                DOC_INSTRUCTION
                + f'\n\n<document filename="{st.session_state.doc_name}">\n'
                + doc_snippet
                + "\n</document>"
            )

        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            try:
                with st.spinner("🔮 수정 구슬이 답을 길어 올리는 중..."):
                    response = client.chat.completions.create(
                        model=MODEL_NAME,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            *st.session_state.messages,
                        ],
                    )
                answer = response.choices[0].message.content
                st.markdown(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})
            except Exception as e:
                st.session_state.messages.pop()
                st.error(
                    "답변을 생성하지 못했어요. 잠시 후 다시 시도해주세요.\n\n"
                    f"(오류 내용: {e})"
                )
