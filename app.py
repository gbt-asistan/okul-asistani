import streamlit as st
import google.generativeai as genai
import sqlite3
import datetime
from gtts import gTTS
import os
import io
import re

# --- SİTE AYARLARI ---
st.set_page_config(
    page_title="Okul Asistanı",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- KÜTÜPHANE KONTROLLERİ ---
try:
    import pypdf
    from docx import Document
    from PIL import Image
except ImportError:
    pass

# --- VERİTABANI BAŞLATMA ---
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

# --- OTURUM KONTROLÜ ---
if "messages" not in st.session_state: st.session_state.messages = []
if "username" not in st.session_state: st.session_state.username = None

# ============================================================
# 🚪 GİRİŞ EKRANI
# ============================================================
if not st.session_state.username:
    st.markdown("""
    <style>
        header, footer, [data-testid="stToolbar"] {display: none !important;}
        .block-container {
            display: flex; justify-content: center; align-items: center; height: 80vh;
        }
        .login-card {
            background-color: #1e293b; border: 1px solid #334155; padding: 40px; 
            border-radius: 20px; text-align: center; width: 100%; max-width: 400px;
        }
    </style>
    """, unsafe_allow_html=True)
    with st.container():
        st.markdown('<div class="login-card"><h1 style="color:white; font-size:2rem;">🎓 Okul Asistanı</h1>', unsafe_allow_html=True)
        username_input = st.text_input("Adın nedir?", placeholder="Örn: Ahmet")
        if st.button("Giriş Yap 🚀", use_container_width=True):
            if username_input:
                if not get_user(conn, username_input): create_user(conn, username_input)
                st.session_state.username = username_input
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    st.stop()


# ============================================================
# 🏠 ANA UYGULAMA
# ============================================================

# API
if "GOOGLE_API_KEY" in st.secrets: API_KEY = st.secrets["GOOGLE_API_KEY"]
else: st.warning("⚠️ API Anahtarı eksik."); st.stop()
try:
    genai.configure(api_key=API_KEY)
    secilen_model = "gemini-1.5-flash"
    try:
        modeller = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        if any('flash' in m for m in modeller): secilen_model = next(m for m in modeller if 'flash' in m)
    except: pass
    model = genai.GenerativeModel(secilen_model)
except Exception as e: st.error(f"Hata: {e}"); st.stop()

# --- CSS AYARLARI ---
st.markdown("""
<style>
    /* Temel Gizlemeler */
    header, footer, .stDeployButton, [data-testid="stToolbar"] {display: none !important;}

    /* 1. SAYFA DÜZENİ */
    .block-container {
        padding-top: 320px !important; /* Panel yüksekliği kadar boşluk */
        padding-bottom: 120px !important; /* Sohbet kutusu için boşluk */
        max-width: 1000px !important;
    }

    /* 2. SABİT HEADER (ÇAPA YÖNTEMİ) */
    div[data-testid="stVerticalBlock"] > div:has(div.fixed-marker) {
        position: fixed !important;
        top: 0 !important;
        left: 0 !important;
        width: 100% !important;
        z-index: 99999 !important;
        background-color: #0f172a !important; 
        border-bottom: 1px solid #334155;
        padding: 1rem 1rem 0 1rem !important;
        box-shadow: 0 4px 15px rgba(0,0,0,0.5);
    }

    /* 3. SOHBET KUTUSU */
    [data-testid="stChatInput"] {
        bottom: 20px !important;
        background: transparent !important;
    }
    [data-testid="stChatInput"] > div {
        background-color: #1e293b !important;
        border: 1px solid #475569 !important;
        border-radius: 20px !important;
        color: white !important;
    }

    /* 4. SATIN AL BUTONU TASARIMI */
    .buy-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 100%;
        padding: 0.6rem;
        background: linear-gradient(90deg, #ec4899, #8b5cf6); /* Pembe-Mor */
        color: white !important;
        text-align: center;
        border-radius: 8px;
        text-decoration: none;
        font-weight: bold;
        border: 1px solid #db2777;
        box-shadow: 0 2px 5px rgba(236, 72, 153, 0.4);
        transition: all 0.3s ease;
    }
    .buy-btn:hover {
        opacity: 0.9;
        transform: scale(1.02);
        color: white !important;
    }

    /* TASARIM DETAYLARI */
    .main-title {
        font-size: 1.8rem; font-weight: 800; text-align: center; color: white; margin-bottom: 5px;
    }
    .user-badge { background: #334155; color: white; padding: 4px 8px; border-radius: 6px; font-size: 0.8rem; }
    .pro-badge { background: linear-gradient(90deg, #fbbf24, #d946ef); color: white; padding: 4px 8px; border-radius: 6px; font-weight: bold; font-size: 0.8rem; }

</style>
""", unsafe_allow_html=True)

# KULLANICI BİLGİLERİ
username = st.session_state.username
kredi, is_premium, premium_expiry = update_credits(conn, username)
history = get_history(conn, username)

# 📌 SABİT HEADER ALANI
header_container = st.container()

with header_container:
    # CSS İşaretçisi
    st.markdown('<div class="fixed-marker"></div>', unsafe_allow_html=True)
    
    # Başlık
    st.markdown('<div class="main-title">🎓 Okul Asistanı</div>', unsafe_allow_html=True)
    
    # Kullanıcı Bilgisi
    c_inf, c_btn = st.columns([5,1])
    with c_inf:
        if is_premium: st.markdown(f"<span class='pro-badge'>💎 PRO</span> <b>{username}</b>", unsafe_allow_html=True)
        else: st.markdown(f"<span class='user-badge'>ÖĞRENCİ</span> <b>{username}</b> | Hak: {kredi}", unsafe_allow_html=True)
    with c_btn:
        if st.button("Çıkış", key="logout"):
            st.session_state.username = None; st.session_state.messages = []; st.rerun()

    # Menüler
    c1, c2, c3 = st.columns(3)
    with c1: seviye = st.selectbox("Sınıf", ["İlkokul", "Ortaokul", "Lise", "Üniversite"], label_visibility="collapsed")
    with c2: mod = st.selectbox("Mod", [
        "❓ Soru Çözümü", 
        "📚 Konu Anlatımı", 
        "📝 Kompozisyon Yaz", 
        "💬 Sohbet", 
        "🏠 Ödev Yardımı",
        "🌍 Tüm Diller Öğretmeni (Pro)",
        "📂 Dosya Analizi (Pro)"
    ], label_visibility="collapsed")
    with c3:
        if is_premium: persona = st.selectbox("Tarz", ["Normal", "Komik", "Disiplinli"], label_visibility="collapsed")
        else: st.selectbox("Tarz", ["Normal"], disabled=True, label_visibility="collapsed"); persona="Normal"

    # Ekstra Özellikler (Premium)
    if is_premium and "Dosya" in mod:
        st.file_uploader("Dosya", type=['pdf','docx','png'], label_visibility="collapsed")
    
    # Premium Satın Alma ve Kod Girme (Yan Yana Butonlar)
    if not is_premium:
        with st.expander("💎 Premium Kod Gir"):
            kod = st.text_input("Kod:", placeholder="SOA-XXXX", label_visibility="collapsed")
            
            # BURADA EKRANI İKİYE BÖLÜYORUZ: AKTİFLEŞTİR VE SATIN AL
            col_act, col_buy = st.columns([1, 1.5])
            
            with col_act:
                if st.button("Aktifleştir", use_container_width=True):
                    ok, msg = activate_premium(conn, username, kod.strip())
                    if ok: st.balloons(); st.success(msg); st.rerun()
                    else: st.error(msg)
            
            with col_buy:
                # Buraya kendi Shopier veya ödeme linkini yapıştırabilirsin
                link = "https://www.shopier.com/" 
                st.markdown(f'<a href="{link}" target="_blank" class="buy-btn">💳 3 Üyelik 49 TL - AL</a>', unsafe_allow_html=True)
    
    st.write("") 

# 💬 SOHBET AKIŞI
uploaded_text, uploaded_image = "", None
for r, c in history:
    with st.chat_message(r): st.markdown(c)

# MESAJ GİRİŞİ
if prompt := st.chat_input("Buraya yaz..."):
    # Hızlı Kod Girişi
    if prompt.startswith("SOA-") and not is_premium:
        ok, msg = activate_premium(conn, username, prompt.strip())
        if ok: st.balloons(); st.success(msg); st.rerun()
        else: st.error(msg)
    
    elif "Pro" in mod and not is_premium:
        st.error("🔒 Bu mod sadece Premium üyeler içindir.")
    elif kredi <= 0 and not is_premium:
        st.error("Günlük hakkın bitti.")
        
    else:
        save_message(conn, username, "user", prompt)
        st.session_state.messages.append({"role":"user", "content":prompt})
        with st.chat_message("user"): st.markdown(prompt)

        with st.chat_message("assistant"):
            box = st.empty(); box.markdown("...")
            try:
                system_prompt = f"Sen 'Okul Asistanı' adında yapay zekasın. Seviye: {seviye}, Mod: {mod}, Stil: {persona}. Soru: {prompt}"
                if "Dil" in mod: system_prompt += "\nRolün: Profesyonel dil öğretmeni."
                
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
