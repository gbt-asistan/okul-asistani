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
# 🎨 DÜZELTİLMİŞ TASARIM (MESAJLAR ARTIK GİZLENMEYECEK)
# ============================================================
st.markdown("""
<style>
    /* 1. GEREKSİZLERİ GİZLE */
    header {visibility: hidden !important;}
    .stDeployButton, [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stSidebar"], footer {
        display: none !important;
    }

    /* 2. SAYFA DÜZENİ (KRİTİK DÜZELTME BURADA) */
    /* Üst boşluğu 450px yapıyoruz ki panelin altında hiçbir şey kalmasın */
    .block-container {
        padding-top: 450px !important; 
        padding-bottom: 150px !important;
        max-width: 1000px !important;
    }

    /* 3. SABİT ÜST PANEL (APP BAR) */
    .fixed-app-bar {
        position: fixed !important;
        top: 0 !important;
        left: 0 !important;
        width: 100% !important;
        z-index: 99999 !important;
        background-color: #0f172a !important; /* Koyu Lacivert */
        border-bottom: 1px solid #334155;
        box-shadow: 0 4px 25px rgba(0,0,0,0.6);
        padding: 15px 20px 20px 20px !important;
        height: auto !important; /* Yükseklik içeriğe göre uzasın */
    }

    /* 4. BAŞLIK TASARIMI */
    .app-title {
        font-size: 2rem;
        font-weight: 800;
        text-align: center;
        margin-bottom: 15px;
        background: -webkit-linear-gradient(45deg, #fff, #94a3b8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }

    /* 5. SOHBET KUTUSU (ALTA SABİT) */
    [data-testid="stChatInput"] {
        bottom: 30px !important;
        background: transparent !important;
        display: flex !important;
        justify-content: center !important;
        z-index: 9999 !important;
    }
    [data-testid="stChatInput"] > div {
        background-color: #1e293b !important;
        border: 1px solid #475569 !important;
        border-radius: 25px !important;
        color: white !important;
        width: 100% !important;
        max-width: 900px !important;
        box-shadow: 0 -5px 20px rgba(0,0,0,0.4) !important;
    }
    .stChatInput textarea {
        background-color: transparent !important;
        border: none !important;
        color: white !important;
    }

    /* 6. MESAJ BALONCUKLARI (DAHA BELİRGİN OLSUN) */
    .stChatMessage {
        background-color: rgba(30, 41, 59, 0.5) !important;
        border-radius: 10px !important;
        padding: 10px !important;
        border: 1px solid #334155 !important;
    }

    /* ROZETLER */
    .user-info-bar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        background: #1e293b;
        padding: 8px 15px;
        border-radius: 12px;
        margin-bottom: 15px;
        border: 1px solid #334155;
    }
    .badge-std { background: #475569; color: white; padding: 4px 10px; border-radius: 6px; font-size: 0.85rem; }
    .badge-pro { background: linear-gradient(90deg, #fbbf24, #d946ef); color: white; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 0.85rem; }
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
# 📌 SABİT ÜST PANEL (APP BAR)
# ============================================================
header = st.container()

with header:
    st.markdown('<div class="fixed-app-bar">', unsafe_allow_html=True)
    
    # 1. BAŞLIK
    st.markdown('<div class="app-title">🎓 Okul Asistanı</div>', unsafe_allow_html=True)

    # 2. KULLANICI BİLGİSİ
    col_inf, col_out = st.columns([4, 1])
    with col_inf:
        if is_premium:
            st.markdown(f"<div class='user-info-bar'><span class='badge-pro'>PRO</span>&nbsp; <b>{username}</b></div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='user-info-bar'><span class='badge-std'>ÖĞRENCİ</span>&nbsp; <b>{username}</b> | Hak: {kredi}</div>", unsafe_allow_html=True)
    with col_out:
        if st.button("Çıkış", key="exit_btn", use_container_width=True):
            st.session_state.username = None; st.session_state.messages = []; st.rerun()

    # 3. AYARLAR
    c1, c2, c3 = st.columns(3)
    with c1:
        seviye = st.selectbox("Sınıf", ["İlkokul", "Ortaokul", "Lise", "Üniversite"], label_visibility="collapsed")
    with c2:
        mod = st.selectbox("Mod", ["❓ Soru Çözümü", "📚 Konu Anlatımı", "📝 Kompozisyon Yaz", "💬 Sohbet", "🏠 Ödev Yardımı", "📂 Dosya Analizi (Pro)"], label_visibility="collapsed")
    with c3:
        if is_premium:
            persona = st.selectbox("Tarz", ["Normal", "Komik", "Disiplinli"], label_visibility="collapsed")
        else:
            st.selectbox("Tarz", ["Normal"], disabled=True, label_visibility="collapsed"); persona="Normal"

    # 4. DOSYA (Premium)
    if is_premium and "Dosya" in mod:
        st.file_uploader("Dosya", type=['pdf','docx','png'], label_visibility="collapsed")

    # 5. PREMIUM ALMA
    if not is_premium:
        with st.expander("💎 Premium Kod Gir"):
            kod = st.text_input("Kod:", placeholder="SOA-XXXX", label_visibility="collapsed")
            if st.button("Aktifleştir"):
                ok, msg = activate_premium(conn, username, kod.strip())
                if ok: st.balloons(); st.success(msg); st.rerun()
                else: st.error(msg)
                
    st.markdown('</div>', unsafe_allow_html=True)

# ============================================================
# 💬 SOHBET AKIŞI
# ============================================================
uploaded_text, uploaded_image = "", None
if "Dosya" in mod and is_premium:
    # Dosya okuma logic (Basitleştirilmiş)
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
                Asla kendini Google veya Gemini olarak tanıtma.
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
