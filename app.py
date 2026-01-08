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
# 🛠️ GÖRÜNÜM DÜZELTME (SOL TARAFTAKİ BOZUKLUK GİDERİLDİ)
# ============================================================
st.markdown("""
<style>
    /* 1. GİZLİLİK (Logoları Yok Et) */
    header {visibility: hidden !important;}
    .stDeployButton {display: none !important;}
    [data-testid="stToolbar"] {display: none !important;}
    [data-testid="stDecoration"] {display: none !important;}
    [data-testid="stSidebar"] {display: none !important;}
    footer {visibility: hidden !important; height: 0px !important;}

    /* 2. SAYFA DÜZENİ */
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 120px !important;
        max-width: 1000px !important;
    }

    /* 3. SOHBET KUTUSU TAMİRİ (KESİN ÇÖZÜM) */
    
    /* Ana Taşıyıcıyı Ortala ve Sabitle */
    [data-testid="stChatInput"] {
        bottom: 40px !important; /* Biraz daha yukarı al */
        background: transparent !important; /* Arka planı temizle */
        display: flex !important;
        justify-content: center !important; /* İçeriği ortala */
    }

    /* Yazı Kutusunun Dış Çerçevesi (Gri Alan Burası Olacak) */
    [data-testid="stChatInput"] > div {
        background-color: #334155 !important; /* Koyu gri renk */
        border: 1px solid #475569 !important; /* İnce çerçeve */
        border-radius: 25px !important; /* Tam oval köşeler */
        width: 100% !important;
        max-width: 900px !important; /* Genişlik sınırı */
        box-shadow: 0 4px 10px rgba(0,0,0,0.3) !important; /* Hafif gölge */
    }

    /* İçerideki Yazı Alanı (Şeffaf Yapıyoruz ki Kayma Olmasın) */
    .stChatInput textarea {
        background-color: transparent !important; /* Rengi üstteki kutudan alsın */
        border: none !important; /* Kenarlığı kaldır (çift çizgi olmasın) */
        color: white !important;
        min-height: 50px !important;
        padding: 15px !important; /* Yazı kenarlara yapışmasın */
        font-size: 16px !important;
    }
    
    /* Odaklanınca (Tıklayınca) oluşan mavi çizgiyi kaldır */
    .stChatInput textarea:focus {
        box-shadow: none !important;
    }

    /* Gönder Butonu Rengi */
    [data-testid="stChatInputSubmitButton"] {
        background: transparent !important;
        color: #94a3b8 !important;
    }
    [data-testid="stChatInputSubmitButton"]:hover {
        color: white !important;
    }

    /* 4. KONTROL PANELİ TASARIMI */
    .control-panel {
        background-color: #1e293b;
        border: 1px solid #334155;
        padding: 15px;
        border-radius: 15px;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }

    /* PREMIUM ROZETİ */
    .premium-badge {
        background: linear-gradient(45deg, #7c3aed, #db2777);
        color: white;
        padding: 5px 10px;
        border-radius: 8px;
        font-weight: bold;
        font-size: 0.8rem;
        display: inline-block;
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

# BAŞLIK
c1, c2 = st.columns([3, 1])
with c1: st.title("🎓 Okul Asistanı")
with c2:
    if st.button("Çıkış Yap 🚪"):
        st.session_state.username = None; st.session_state.messages = []; st.rerun()

# ============================================================
# 🎛️ KONTROL PANELİ
# ============================================================
with st.container():
    st.markdown('<div class="control-panel">', unsafe_allow_html=True)
    
    k1, k2 = st.columns([3, 1])
    with k1:
        if is_premium: st.markdown(f"👤 **{username}** <span class='premium-badge'>💎 PREMIUM</span>", unsafe_allow_html=True)
        else: st.write(f"👤 **{username}** | Kalan Hak: **{kredi}/5**")
    with k2:
        if not is_premium:
            if st.button("💎 Premium Ol"): st.toast("Aşağıdan kod girebilirsin 👇")

    st.divider()

    col1, col2, col3 = st.columns(3)
    with col1: seviye = st.selectbox("Sınıf Seviyesi", ["🐣 İlkokul", "📘 Ortaokul", "🏫 Lise", "🎓 Üniversite"])
    with col2: mod = st.selectbox("Çalışma Modu", ["❓ Soru Çözümü", "📚 Konu Anlatımı", "📝 Kompozisyon Yaz", "💬 Sohbet", "🏠 Ödev Yardımı", "📂 Dosya Analizi (Pro)"])
    with col3:
        if is_premium: persona = st.selectbox("Öğretmen Tarzı", ["😐 Normal", "😂 Komik", "🫡 Disiplinli", "🥰 Samimi"])
        else: st.selectbox("Öğretmen Tarzı", ["🔒 Normal (Premium)"], disabled=True); persona = "Normal"

    if "Dosya" in mod and is_premium:
        st.info("📂 Dosya Yükleme Aktif")
        uploaded_file = st.file_uploader("Dosya Seç", type=['pdf', 'docx', 'png', 'jpg'], label_visibility="collapsed")
    else: uploaded_file = None
    
    if not is_premium:
        with st.expander("🎫 Premium Kodunu Gir"):
            kod = st.text_input("Kod:", placeholder="SOA-XXXX")
            if st.button("Kodu Onayla"):
                ok, msg = activate_premium(conn, username, kod.strip())
                if ok: st.balloons(); st.success(msg); st.rerun()
                else: st.error(msg)
                
    st.markdown('</div>', unsafe_allow_html=True)

# ============================================================
# 💬 SOHBET VE KİMLİK KORUMASI
# ============================================================
uploaded_text, uploaded_image = "", None
if "Dosya" in mod and is_premium and uploaded_file:
    try:
        if uploaded_file.name.endswith(".pdf"): r=pypdf.PdfReader(uploaded_file); uploaded_text="".join([p.extract_text() for p in r.pages])
        elif uploaded_file.name.endswith(('.png','.jpg')): uploaded_image=Image.open(uploaded_file)
        elif uploaded_file.name.endswith(".docx"): d=Document(uploaded_file); uploaded_text="\n".join([p.text for p in d.paragraphs])
    except: pass

# Geçmişi göster
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
                # KİMLİK KORUMASI VE TALİMATLAR
                system_prompt = f"""
                Sen 'Okul Asistanı' adında, öğrenciler için tasarlanmış özel bir yapay zeka asistanısın.
                KİMLİK KURALI: Asla kendini 'Google', 'Gemini', 'OpenAI' veya başka bir şirketin ürünü olarak tanıtma.
                Eğer kim olduğun veya kim tarafından geliştirildiğin sorulursa: "Ben Okul Asistanı'yım, senin derslerine yardımcı olmak için buradayım" de.
                
                Seviye: {seviye}
                Mod: {mod}
                Stil: {persona}
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
                    try:
                        tts = gTTS(clean_text(res), lang='tr')
                        aud = io.BytesIO(); tts.write_to_fp(aud)
                        st.audio(aud, format='audio/mp3')
                    except: pass
            except Exception as e: box.error(f"Hata: {e}")
