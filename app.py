import streamlit as st
import google.generativeai as genai
import sqlite3
import datetime
from gtts import gTTS
import os
import io
import re

# --- KÜTÜPHANE KONTROLLERİ ---
try:
    import pypdf
    from docx import Document
    from PIL import Image
except ImportError:
    pass

# --- SİTE AYARLARI ---
st.set_page_config(
    page_title="Okul Asistanı",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ============================================================
# 🎨 LUXURY CSS TASARIMI (PREMIUM HİSSİYATI)
# ============================================================
st.markdown("""
<style>
    /* 1. GEREKSİZLERİ GİZLE */
    header {visibility: hidden !important;}
    .stDeployButton, [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stSidebar"], footer {
        display: none !important;
    }

    /* 2. SAYFA DÜZENİ */
    .block-container {
        padding-top: 2rem !important; /* Başlık için mesafe */
        padding-bottom: 120px !important;
        max-width: 1000px !important;
    }

    /* 3. BAŞLIK TASARIMI */
    .main-title {
        font-size: 2.5rem;
        font-weight: 800;
        background: -webkit-linear-gradient(45deg, #eee, #94a3b8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 10px;
    }

    /* 4. SOHBET KUTUSU (HATASIZ) */
    [data-testid="stChatInput"] {
        bottom: 30px !important;
        background: transparent !important;
        display: flex !important;
        justify-content: center !important;
    }
    [data-testid="stChatInput"] > div {
        background-color: #0f172a !important;
        border: 1px solid #334155 !important;
        border-radius: 25px !important;
        color: white !important;
        width: 100% !important;
        max-width: 900px !important;
        box-shadow: 0 4px 15px rgba(0,0,0,0.5) !important;
    }
    .stChatInput textarea {
        background-color: transparent !important;
        border: none !important;
        color: white !important;
        min-height: 50px !important;
    }

    /* 5. KONTROL PANELİ (STANDART) */
    .control-panel {
        background-color: #1e293b;
        border: 1px solid #334155;
        padding: 20px;
        border-radius: 20px;
        margin-bottom: 20px;
    }

    /* 6. PREMIUM PANEL (ALTIN/MOR PARLAMA EFEKTİ) */
    .premium-panel {
        background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%);
        border: 2px solid transparent;
        border-image: linear-gradient(45deg, #ffd700, #a855f7) 1;
        box-shadow: 0 0 20px rgba(168, 85, 247, 0.3);
        padding: 20px;
        border-radius: 20px; /* Border-image ile radius sorunu olursa diye fallback */
        margin-bottom: 20px;
        position: relative;
    }
    /* Border-radius hilesi */
    .premium-panel::before {
        content: "";
        position: absolute;
        inset: 0;
        border-radius: 20px; 
        padding: 2px; 
        background: linear-gradient(45deg, #fbbf24, #a855f7); 
        -webkit-mask: 
           linear-gradient(#fff 0 0) content-box, 
           linear-gradient(#fff 0 0);
        -webkit-mask-composite: xor;
        mask-composite: exclude;
        pointer-events: none;
    }

    /* ROZETLER */
    .user-badge {
        background-color: #334155;
        color: #e2e8f0;
        padding: 5px 12px;
        border-radius: 12px;
        font-weight: bold;
        font-size: 0.9rem;
    }
    .pro-badge {
        background: linear-gradient(90deg, #fbbf24, #d946ef);
        color: #fff;
        padding: 5px 12px;
        border-radius: 12px;
        font-weight: bold;
        font-size: 0.9rem;
        box-shadow: 0 2px 10px rgba(217, 70, 239, 0.4);
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# 🔒 API BAĞLANTISI
# ============================================================
if "GOOGLE_API_KEY" in st.secrets:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
else:
    st.warning("⚠️ API Anahtarı eksik.")
    st.stop()

try:
    genai.configure(api_key=API_KEY)
    secilen_model = "gemini-1.5-flash"
    try:
        modeller = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        if any('flash' in m for m in modeller): secilen_model = next(m for m in modeller if 'flash' in m)
    except: pass
    model = genai.GenerativeModel(secilen_model)
except Exception as e:
    st.error(f"Hata: {e}")
    st.stop()

# --- VERİTABANI ---
def init_db():
    conn = sqlite3.connect('okul_veritabani.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, credits INTEGER, last_login_date TEXT, is_premium INTEGER, premium_expiry TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages (username TEXT, role TEXT, content TEXT, timestamp TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS premium_codes (code TEXT PRIMARY KEY, is_used INTEGER, used_by TEXT)''')
    conn.commit()
    return conn

conn = init_db()

# --- FONKSİYONLAR ---
def get_user(conn, username): return conn.cursor().execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
def create_user(conn, username): conn.cursor().execute("INSERT INTO users VALUES (?, 5, ?, 0, NULL)", (username, datetime.date.today().isoformat())); conn.commit()
def deduct_credit(conn, username): conn.cursor().execute("UPDATE users SET credits = credits - 1 WHERE username=?", (username,)); conn.commit()
def save_message(conn, username, role, content): conn.cursor().execute("INSERT INTO messages VALUES (?, ?, ?, ?)", (username, role, content, datetime.datetime.now().isoformat())); conn.commit()
def get_history(conn, username): return conn.cursor().execute("SELECT role, content FROM messages WHERE username=? ORDER BY timestamp ASC", (username,)).fetchall()
def clean_text(text): return re.sub(r'^- ', '', text.replace("**", "").replace("*", "").replace("##", ""), flags=re.MULTILINE).strip()

def update_credits(conn, username):
    user = get_user(conn, username)
    if user:
        credits, last_date, is_prem, expiry = user[1], user[2], user[3], user[4]
        today = datetime.date.today().isoformat()
        if last_date != today:
            conn.cursor().execute("UPDATE users SET credits=?, last_login_date=? WHERE username=?", (5, today, username)); conn.commit(); credits=5
        return credits, is_prem, expiry
    return 0, 0, None

def activate_premium(conn, username, code):
    res = conn.cursor().execute("SELECT * FROM premium_codes WHERE code=?", (code,)).fetchone()
    if not res: return False, "❌ Geçersiz kod!"
    if res[1]: return False, "⚠️ Kod kullanılmış."
    exp = (datetime.date.today() + datetime.timedelta(days=90)).isoformat()
    conn.cursor().execute("UPDATE users SET is_premium=1, premium_expiry=? WHERE username=?", (exp, username))
    conn.cursor().execute("UPDATE premium_codes SET is_used=1, used_by=? WHERE code=?", (username, code))
    conn.commit(); return True, "✅ Premium Aktif! Hoş geldin VIP."

# --- UYGULAMA ---
if "messages" not in st.session_state: st.session_state.messages = []
if "username" not in st.session_state: st.session_state.username = None

# GİRİŞ EKRANI
if not st.session_state.username:
    st.markdown("<h1 style='text-align: center;'>🎓 Okul Asistanı</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        username_input = st.text_input("Adın nedir?", placeholder="Örn: Ahmet")
        if st.button("Giriş Yap 🚀", use_container_width=True):
            if username_input:
                if not get_user(conn, username_input): create_user(conn, username_input)
                st.session_state.username = username_input; st.rerun()
    st.stop()

# --- ANA EKRAN ---
username = st.session_state.username
kredi, is_premium, premium_expiry = update_credits(conn, username)
history = get_history(conn, username)

# 1. BAŞLIK (EN TEPEYE GELDİ)
st.markdown('<div class="main-title">🎓 Okul Asistanı</div>', unsafe_allow_html=True)

# 2. KONTROL PANELİ (PREMIUM İÇİN ÖZEL TASARIM)
# Premium ise "premium-panel", değilse "control-panel" sınıfını kullan
panel_class = "premium-panel" if is_premium else "control-panel"

st.markdown(f'<div class="{panel_class}">', unsafe_allow_html=True)

# Üst Satır: Kullanıcı Bilgisi ve Rozetler
top1, top2 = st.columns([3, 1])
with top1:
    if is_premium:
        st.markdown(f"<span class='pro-badge'>💎 PREMIUM ÜYE</span> &nbsp; **{username}**", unsafe_allow_html=True)
    else:
        st.markdown(f"<span class='user-badge'>ÖĞRENCİ</span> &nbsp; **{username}** | Hak: {kredi}/5", unsafe_allow_html=True)
with top2:
    if st.button("Çıkış", key="logout"):
        st.session_state.username = None; st.session_state.messages = []; st.rerun()

st.divider()

# Alt Satır: Ayarlar
c1, c2, c3 = st.columns(3)
with c1:
    seviye = st.selectbox("Sınıf Seviyesi", ["🐣 İlkokul", "📘 Ortaokul", "🏫 Lise", "🎓 Üniversite"])
with c2:
    mod = st.selectbox("Çalışma Modu", ["❓ Soru Çözümü", "📚 Konu Anlatımı", "📝 Kompozisyon Yaz", "💬 Sohbet", "🏠 Ödev Yardımı", "📂 Dosya Analizi (Pro)"])
with c3:
    if is_premium:
        persona = st.selectbox("Öğretmen Tarzı", ["😐 Normal", "😂 Komik", "🫡 Disiplinli", "🥰 Samimi"])
    else:
        st.selectbox("Öğretmen Tarzı", ["🔒 Normal (Premium)"], disabled=True); persona = "Normal"

# Dosya Yükleme (Sadece Premium)
if "Dosya" in mod and is_premium:
    st.markdown("---")
    uploaded_file = st.file_uploader("Dosya Yükle", type=['pdf','docx','png','jpg'], label_visibility="collapsed")
else: uploaded_file = None

# Premium Satın Alma (Sadece Standart Üyeler İçin)
if not is_premium:
    with st.expander("💎 Premium Kod Gir"):
        st.info("Sınırsız soru ve dosya yükleme hakkı kazan!")
        col_input, col_btn = st.columns([3,1])
        with col_input:
            kod = st.text_input("Kod:", placeholder="SOA-XXXX", label_visibility="collapsed")
        with col_btn:
            if st.button("Aktifleştir"):
                ok, msg = activate_premium(conn, username, kod.strip())
                if ok: st.balloons(); st.success(msg); st.rerun()
                else: st.error(msg)

st.markdown('</div>', unsafe_allow_html=True)

# ============================================================
# 💬 SOHBET ALANI
# ============================================================
uploaded_text, uploaded_image = "", None
if "Dosya" in mod and is_premium and uploaded_file:
    try:
        if uploaded_file.name.endswith(".pdf"): r=pypdf.PdfReader(uploaded_file); uploaded_text="".join([p.extract_text() for p in r.pages])
        elif uploaded_file.name.endswith(('.png','.jpg')): uploaded_image=Image.open(uploaded_file)
        elif uploaded_file.name.endswith(".docx"): d=Document(uploaded_file); uploaded_text="\n".join([p.text for p in d.paragraphs])
    except: pass

# Mesaj Geçmişi
for r, c in history:
    with st.chat_message(r): st.markdown(c)

# Mesaj Girişi
if prompt := st.chat_input("Buraya yaz..."):
    # Hızlı Kod Girişi (Yazı kutusundan da kod girilebilsin)
    if prompt.startswith("SOA-") and not is_premium:
        ok, msg = activate_premium(conn, username, prompt.strip())
        if ok: st.balloons(); st.success(msg); st.rerun()
        else: st.error(msg)
        
    elif kredi <= 0 and not is_premium: st.error("Günlük hakkın bitti. Premium alarak devam et.")
    else:
        save_message(conn, username, "user", prompt)
        st.session_state.messages.append({"role":"user", "content":prompt})
        with st.chat_message("user"): st.markdown(prompt)

        with st.chat_message("assistant"):
            box = st.empty(); box.markdown("...")
            try:
                system_prompt = f"""
                Sen 'Okul Asistanı' adında özel bir yapay zekasın. 
                Asla kendini Google veya Gemini olarak tanıtma.
                Seviye: {seviye}, Mod: {mod}, Stil: {persona}
                Soru: {prompt}
                """
                
                con = [system_prompt]
                if uploaded_text: con.append(f"Dosya: {uploaded_text}")
                if uploaded_image: con.append(uploaded_image)
                
                res = model.generate_content(con).text
                box.markdown(res)
                save_message(conn, username, "assistant", res)
                
                if not is_premium: deduct_credit(conn, username)
                if is_premium:
                    try: # Sesli okuma
                        tts = gTTS(clean_text(res), lang='tr')
                        aud = io.BytesIO(); tts.write_to_fp(aud)
                        st.audio(aud, format='audio/mp3')
                    except: pass
            except Exception as e: box.error(f"Hata: {e}")
