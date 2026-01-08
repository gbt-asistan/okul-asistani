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
# 🛠️ GELİŞMİŞ CSS: SABİT ÜST BAR & KAYAN SOHBET
# ============================================================
st.markdown("""
<style>
    /* 1. GEREKSİZLERİ GİZLE */
    header {visibility: hidden !important;}
    .stDeployButton, [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stSidebar"], footer {
        display: none !important;
    }

    /* 2. SAYFA DÜZENİ (ÇOK ÖNEMLİ) */
    /* Üstten 220px boşluk bırak ki sabit panel yazıları kapatmasın */
    /* Alttan 100px boşluk bırak ki sohbet kutusu en son mesajı kapatmasın */
    .block-container {
        padding-top: 220px !important;
        padding-bottom: 120px !important;
        max-width: 1000px !important;
    }

    /* 3. SABİT ÜST PANEL (HEADER) */
    /* Bu sınıfı Python tarafında bir container'a vereceğiz */
    .fixed-panel {
        position: fixed !important;
        top: 0 !important;
        left: 0 !important;
        width: 100% !important;
        background-color: #0f172a !important; /* Koyu Arka Plan */
        z-index: 99999 !important; /* En üstte dur */
        border-bottom: 1px solid #334155;
        padding: 1rem 1rem 0.5rem 1rem !important;
        box-shadow: 0 4px 15px rgba(0,0,0,0.5);
    }
    
    /* Panel içindeki widget'ların düzeni */
    .stSelectbox, .stButton {
        margin-bottom: 0px !important;
    }

    /* 4. SOHBET KUTUSU (ALTA SABİTLEME) */
    [data-testid="stChatInput"] {
        bottom: 30px !important;
        background: transparent !important;
        z-index: 9999 !important;
    }
    
    /* Sohbet kutusu stil */
    [data-testid="stChatInput"] > div {
        background-color: #1e293b !important;
        border: 1px solid #334155 !important;
        border-radius: 20px !important;
        color: white !important;
    }
    
    /* 5. PREMIUM BUTON TASARIMI */
    .buy-button {
        display: inline-block;
        background: linear-gradient(90deg, #ec4899, #8b5cf6);
        color: white;
        padding: 8px 16px;
        border-radius: 8px;
        text-decoration: none;
        font-weight: bold;
        text-align: center;
        width: 100%;
        margin-bottom: 10px;
    }
    .buy-button:hover {
        color: #f0fdf4;
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
        elif any('pro' in m for m in modeller): secilen_model = next(m for m in modeller if 'pro' in m)
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
    if res[1]: return False, "⚠️ Kullanılmış kod."
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
# 📌 SABİT ÜST PANEL (HİLELİ YÖNTEMLE)
# ============================================================
# Streamlit'te bir container'ı sabitlemek için bu CSS enjekte edilir.
# Bu container sayfanın en üstünde asılı kalır.

# 1. Sabit Panel Başlangıcı
header_container = st.container()
with header_container:
    # Bu HTML, içine girdiği container'ı 'fixed-panel' sınıfına dönüştürür
    st.markdown('<div class="fixed-panel">', unsafe_allow_html=True)
    
    # 2. Üst Bilgi Satırı
    col_info, col_btn = st.columns([3, 1])
    with col_info:
        if is_premium: st.markdown(f"**{username}** | 💎 PREMIUM")
        else: st.markdown(f"**{username}** | Hak: {kredi}")
    with col_btn:
        if st.button("Çıkış"):
            st.session_state.username = None; st.session_state.messages = []; st.rerun()
            
    # 3. Ayarlar Satırı (Seçimler)
    c1, c2 = st.columns(2)
    with c1:
        seviye = st.selectbox("Sınıf", ["İlkokul", "Ortaokul", "Lise", "Üniversite"], label_visibility="collapsed")
    with c2:
        mod = st.selectbox("Mod", ["❓ Soru Çözümü", "📚 Konu Anlatımı", "📝 Kompozisyon Yaz", "💬 Sohbet", "🏠 Ödev Yardımı", "📂 Dosya Analizi (Pro)"], label_visibility="collapsed")

    # 4. Premium Menüsü (Açılır Kapanır)
    if not is_premium:
        with st.expander("💎 Premium İşlemleri (Satın Al / Kod Gir)"):
            st.markdown('<a href="https://www.shopier.com/" target="_blank" class="buy-button">PREMIUM AL (49 TL)</a>', unsafe_allow_html=True)
            col_code, col_act = st.columns([2,1])
            with col_code:
                kod_girisi = st.text_input("Kod:", placeholder="SOA-XXXX", label_visibility="collapsed")
            with col_act:
                if st.button("Onayla"):
                    ok, msg = activate_premium(conn, username, kod_girisi.strip())
                    if ok: st.balloons(); st.success(msg); st.rerun()
                    else: st.error(msg)
    else:
        # Premium üyeler için ekstra ayar
        persona = st.selectbox("Öğretmen Tarzı", ["Normal", "Komik", "Disiplinli", "Samimi"])

    # Dosya Yükleme (Sadece Premium ve Dosya Modunda)
    if is_premium and "Dosya" in mod:
        st.file_uploader("Dosya", type=['pdf','docx','png'], label_visibility="collapsed")
    
    st.markdown('</div>', unsafe_allow_html=True) # Div kapat

# ============================================================
# 💬 SOHBET ALANI
# ============================================================
# Mesaj geçmişini göster
for r, c in history:
    with st.chat_message(r): st.markdown(c)

# YENİ MESAJ GİRİŞİ
if prompt := st.chat_input("Buraya yaz..."):
    if kredi <= 0 and not is_premium: st.error("Günlük hakkın bitti.")
    else:
        save_message(conn, username, "user", prompt)
        st.session_state.messages.append({"role":"user", "content":prompt})
        with st.chat_message("user"): st.markdown(prompt)

        with st.chat_message("assistant"):
            box = st.empty(); box.markdown("...")
            try:
                system_prompt = f"""
                Sen 'Okul Asistanı' adında özel bir yapay zekasın. 
                Asla Google, Gemini veya OpenAI olduğunu söyleme.
                Seviye: {seviye}, Mod: {mod}, Stil: {persona if is_premium else 'Normal'}
                Soru: {prompt}
                """
                
                # Model çağrısı (Basitleştirilmiş)
                res = model.generate_content(system_prompt).text
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
