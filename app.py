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
# 🛡️ SABİT (STICKY) HEADER İÇİN ÖZEL CSS
# ============================================================
st.markdown("""
<style>
    /* 1. GEREKSİZLERİ GİZLE */
    header {visibility: hidden !important;}
    .stDeployButton, [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stSidebar"], footer {
        display: none !important;
    }

    /* 2. ANA SAYFA DÜZENİ (BOŞLUK AYARLARI) */
    .block-container {
        padding-top: 250px !important; /* Sabit panel için üstten güvenli boşluk */
        padding-bottom: 120px !important; /* Sohbet kutusu için alttan boşluk */
        max-width: 1000px !important;
    }

    /* 3. İŞTE SİHİRLİ KOD: KUTUCUKLARI DA SABİTLEYEN CSS */
    /* İçinde 'sticky-header-marker' olan bloğu bul ve sabitle */
    div[data-testid="stVerticalBlock"]:has(div#sticky-header-marker) {
        position: fixed !important;
        top: 0px !important;
        left: 0px !important;
        width: 100% !important;
        z-index: 99999 !important;
        background-color: #0f172a !important; /* Koyu Lacivert Zemin */
        border-bottom: 2px solid #334155; /* Alt Çizgi */
        padding: 1rem 2rem 1rem 2rem !important;
        box-shadow: 0 5px 20px rgba(0,0,0,0.5); /* Gölge */
        gap: 0.5rem !important; /* Elemanlar arası boşluk */
    }

    /* 4. BAŞLIK TASARIMI */
    .main-title {
        font-size: 2rem;
        font-weight: 800;
        text-align: center;
        margin: 0 !important;
        background: -webkit-linear-gradient(45deg, #fff, #94a3b8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }

    /* 5. SOHBET KUTUSU (ALTA SABİT VE ŞIK) */
    [data-testid="stChatInput"] {
        bottom: 30px !important;
        background: transparent !important;
        display: flex !important;
        justify-content: center !important;
    }
    [data-testid="stChatInput"] > div {
        background-color: #1e293b !important;
        border: 1px solid #475569 !important;
        border-radius: 25px !important;
        color: white !important;
        width: 100% !important;
        max-width: 900px !important;
        box-shadow: 0 -5px 15px rgba(0,0,0,0.3) !important;
    }
    .stChatInput textarea {
        background-color: transparent !important;
        border: none !important;
        color: white !important;
    }

    /* ROZETLER */
    .user-badge {
        background: #334155; color: white; padding: 4px 10px; border-radius: 8px; font-size: 0.8rem;
    }
    .pro-badge {
        background: linear-gradient(90deg, #fbbf24, #d946ef); color: white; padding: 4px 10px; border-radius: 8px; font-weight: bold; font-size: 0.8rem;
    }
    
    /* Mobil Uyumlu Butonlar */
    .stButton button {
        width: 100%;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# 🔒 API VE MODEL
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
    conn.commit(); return True, "✅ Premium Aktif!"

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

# ============================================================
# 📌 SABİT (STICKY) PANEL - ÇAPA YÖNTEMİ
# ============================================================
# Bu container CSS ile yakalanıp sabitlenecek
header_container = st.container()

with header_container:
    # 1. GÖRÜNMEZ ÇAPA (CSS Bunu Bulup Sabitleyecek)
    st.markdown('<div id="sticky-header-marker"></div>', unsafe_allow_html=True)
    
    # 2. BAŞLIK
    st.markdown('<div class="main-title">🎓 Okul Asistanı</div>', unsafe_allow_html=True)
    
    # 3. KULLANICI BİLGİSİ
    c_info, c_btn = st.columns([4, 1])
    with c_info:
        if is_premium:
            st.markdown(f"<span class='pro-badge'>💎 PRO</span> <b>{username}</b>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span class='user-badge'>ÖĞRENCİ</span> <b>{username}</b> | Hak: {kredi}", unsafe_allow_html=True)
    with c_btn:
        if st.button("Çıkış", key="out"):
            st.session_state.username = None; st.session_state.messages = []; st.rerun()

    # 4. MENÜLER (Artık sabit alanda olduğu için kaymayacak)
    c1, c2, c3 = st.columns(3)
    with c1:
        seviye = st.selectbox("Sınıf", ["İlkokul", "Ortaokul", "Lise", "Üniversite"], label_visibility="collapsed")
    with c2:
        mod = st.selectbox("Mod", ["❓ Soru Çözümü", "📚 Konu Anlatımı", "📝 Kompozisyon Yaz", "💬 Sohbet", "🏠 Ödev Yardımı", "📂 Dosya Analizi (Pro)"], label_visibility="collapsed")
    with c3:
        if is_premium:
            persona = st.selectbox("Stil", ["Normal", "Komik", "Disiplinli"], label_visibility="collapsed")
        else:
            st.selectbox("Stil", ["Normal"], disabled=True, label_visibility="collapsed"); persona="Normal"

    # 5. DOSYA & PREMIUM (Gerektiğinde Görünür)
    if is_premium and "Dosya" in mod:
        st.file_uploader("Dosya", type=['pdf','docx','png'], label_visibility="collapsed")
    
    if not is_premium:
        with st.expander("💎 Premium Kod Gir"):
            kod = st.text_input("Kod:", placeholder="SOA-XXXX", label_visibility="collapsed")
            if st.button("Aktifleştir"):
                ok, msg = activate_premium(conn, username, kod.strip())
                if ok: st.balloons(); st.success(msg); st.rerun()
                else: st.error(msg)


# ============================================================
# 💬 SOHBET AKIŞI (PANELİN ALTINDAN BAŞLAR)
# ============================================================
uploaded_text, uploaded_image = "", None
if "Dosya" in mod and is_premium:
    # Dosya okuma (Basit)
    pass 

# Geçmiş Mesajlar
for r, c in history:
    with st.chat_message(r): st.markdown(c)

# Yeni Mesaj Girişi
if prompt := st.chat_input("Buraya yaz..."):
    # Kod Girişi
    if prompt.startswith("SOA-") and not is_premium:
        ok, msg = activate_premium(conn, username, prompt.strip())
        if ok: st.balloons(); st.success(msg); st.rerun()
        else: st.error(msg)
    
    elif kredi <= 0 and not is_premium: st.error("Günlük hakkın bitti.")
    else:
        save_message(conn, username, "user", prompt)
        st.session_state.messages.append({"role":"user", "content":prompt})
        with st.chat_message("user"): st.markdown(prompt)

        with st.chat_message("assistant"):
            box = st.empty(); box.markdown("...")
            try:
                system_prompt = f"""
                Sen 'Okul Asistanı' adında özel bir yapay zekasın. 
                Asla Google/Gemini olduğunu söyleme.
                Seviye: {seviye}, Mod: {mod}, Stil: {persona}
                Soru: {prompt}
                """
                con = [system_prompt]
                res = model.generate_content(con).text
                box.markdown(res)
                save_message(conn, username, "assistant", res)
                
                if not is_premium: deduct_credit(conn, username)
                if is_premium:
                    try: 
                        tts = gTTS(clean_text(res), lang='tr')
                        aud = io.BytesIO(); tts.write_to_fp(aud)
                        st.audio(aud, format='audio/mp3')
                    except: pass
            except Exception as e: box.error(f"Hata: {e}")
