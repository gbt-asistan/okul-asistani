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
    st.error("Gerekli kütüphaneler eksik. requirements.txt dosyasını kontrol et.")
    st.stop()

# --- SİTE AYARLARI ---
st.set_page_config(
    page_title="Okul Asistanı",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="collapsed" # Telefondan girince menü kapalı başlar, temiz durur
)

# ============================================================
# 🛡️ GİZLİLİK VE GÖRÜNÜM AYARLARI (SENİN İSTEDİĞİN KISIM)
# ============================================================
st.markdown("""
<style>
    /* 1. Sağ üstteki 'Deploy' butonunu YOK ET */
    .stDeployButton {
        display: none !important;
        visibility: hidden !important;
    }
    
    /* 2. Sağ üstteki 'Seçenekler', 'GitHub' logosu ve Menü'yü YOK ET */
    /* Bu, GitHub'a giden linki de tamamen kaldırır */
    [data-testid="stToolbar"] {
        visibility: hidden !important;
        display: none !important;
        pointer-events: none !important; /* Tıklamayı engeller */
    }
    
    /* 3. En tepedeki renkli dekorasyon çizgisini gizle */
    [data-testid="stDecoration"] {
        display: none !important;
    }

    /* 4. En alttaki 'Made with Streamlit' yazısını ve footer'ı YOK ET */
    footer {
        visibility: hidden !important;
        display: none !important;
        pointer-events: none !important;
    }
    
    /* 5. MOBİL MENÜ BUTONU (SOL ÜST) GÖRÜNSÜN */
    /* Header'ı şeffaf yapıyoruz ama içindeki sol menü butonuna dokunmuyoruz */
    header {
        background: transparent !important;
    }

    /* Diğer Tasarım Ayarları (Senin Kodundan) */
    .stChatInput textarea { height: 100px; }
    .premium-box {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        border: 1px solid #8b5cf6; padding: 20px; border-radius: 12px;
        text-align: center; margin-bottom: 20px;
    }
    .buy-btn {
        background: linear-gradient(90deg, #ec4899, #8b5cf6);
        color: white !important; padding: 10px 20px; border-radius: 8px;
        text-decoration: none; font-weight: bold; display: block; margin-top:10px;
    }
    .badge {
        padding: 5px 10px; border-radius: 5px; color: #1e293b;
        font-weight: bold; font-size: 0.9em; margin-top: 5px;
        display: inline-block; width: 100%; text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# 🔒 GÜVENLİ API BAĞLANTISI
# ============================================================
if "GOOGLE_API_KEY" in st.secrets:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
else:
    st.warning("⚠️ API Anahtarı bulunamadı. Lütfen ayarlardan Secrets kısmına ekleyin.")
    st.stop()

# --- YAPAY ZEKA BAĞLANTISI (OTOMATİK MODEL SEÇİCİ) ---
try:
    genai.configure(api_key=API_KEY)
    
    # Mevcut modelleri listele ve çalışan bir tane seç
    calisan_model = "gemini-1.5-flash" # Varsayılan en hızlısı
    
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                if 'gemini' in m.name:
                    calisan_model = m.name
                    break
    except:
        pass 
        
    model = genai.GenerativeModel(calisan_model)
    
except Exception as e:
    st.error(f"Bağlantı Hatası: {e}")
    st.stop()

# --- VERİTABANI İŞLEMLERİ ---
def init_db():
    conn = sqlite3.connect('okul_veritabani.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, credits INTEGER, last_login_date TEXT, is_premium INTEGER, premium_expiry TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (username TEXT, role TEXT, content TEXT, timestamp TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS premium_codes
                 (code TEXT PRIMARY KEY, is_used INTEGER, used_by TEXT)''')
    conn.commit()
    return conn

def get_user(conn, username):
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=?", (username,))
    return c.fetchone()

def create_user(conn, username):
    c = conn.cursor()
    today = datetime.date.today().isoformat()
    c.execute("INSERT INTO users VALUES (?, 5, ?, 0, NULL)", (username, today))
    conn.commit()

def update_credits(conn, username):
    c = conn.cursor()
    user = get_user(conn, username)
    if user:
        credits, last_date, is_premium, expiry = user[1], user[2], user[3], user[4]
        today = datetime.date.today().isoformat()
        if last_date != today:
            credits = 5
            c.execute("UPDATE users SET credits=?, last_login_date=? WHERE username=?", (5, today, username))
            conn.commit()
        if is_premium and expiry:
            expiry_date = datetime.date.fromisoformat(expiry)
            if datetime.date.today() > expiry_date:
                c.execute("UPDATE users SET is_premium=0, premium_expiry=NULL WHERE username=?", (username,))
                conn.commit()
                is_premium = 0
        return credits, is_premium, expiry
    return 0, 0, None

def deduct_credit(conn, username):
    c = conn.cursor()
    c.execute("UPDATE users SET credits = credits - 1 WHERE username=?", (username,))
    conn.commit()

def save_message(conn, username, role, content):
    c = conn.cursor()
    now = datetime.datetime.now().isoformat()
    c.execute("INSERT INTO messages VALUES (?, ?, ?, ?)", (username, role, content, now))
    conn.commit()

def get_history(conn, username):
    c = conn.cursor()
    c.execute("SELECT role, content FROM messages WHERE username=? ORDER BY timestamp ASC", (username,))
    return c.fetchall()

def activate_premium(conn, username, code):
    c = conn.cursor()
    c.execute("SELECT * FROM premium_codes WHERE code=?", (code,))
    result = c.fetchone()
    if not result: return False, "❌ Geçersiz kod!"
    if result[1] == 1: return False, "⚠️ Bu kod daha önce kullanılmış."
    expiry = (datetime.date.today() + datetime.timedelta(days=90)).isoformat()
    c.execute("UPDATE users SET is_premium=1, premium_expiry=? WHERE username=?", (expiry, username))
    c.execute("UPDATE premium_codes SET is_used=1, used_by=? WHERE code=?", (username, code))
    conn.commit()
    return True, "✅ Premium aktif edildi! 🎉"

# --- SES İÇİN METİN TEMİZLEME ---
def temizle_ve_konus(metin):
    temiz_metin = metin.replace("**", "").replace("*", "")
    temiz_metin = temiz_metin.replace("##", "").replace("#", "")
    temiz_metin = re.sub(r'^- ', '', temiz_metin, flags=re.MULTILINE)
    temiz_metin = temiz_metin.strip()
    return temiz_metin

# --- UYGULAMA BAŞLANGICI ---
conn = init_db()

# Session State
if "messages" not in st.session_state:
    st.session_state.messages = []
if "username" not in st.session_state:
    st.session_state.username = None

# GİRİŞ EKRANI
if not st.session_state.username:
    st.markdown("<h1 style='text-align: center;'>🎓 Okul Asistanı Giriş</h1>", unsafe_allow_html=True)
    st.info("👋 Merhaba! Seni tanımam için bir isim girer misin?")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        username_input = st.text_input("Kullanıcı Adı", placeholder="Örn: ogrenci1")
        if st.button("Giriş Yap 🚀", use_container_width=True):
            if username_input:
                user = get_user(conn, username_input)
                if not user: create_user(conn, username_input)
                st.session_state.username = username_input
                st.rerun()
            else:
                st.warning("Lütfen bir isim yazın.")
    st.stop()

# --- ANA EKRAN ---
username = st.session_state.username
kredi, is_premium, premium_expiry = update_credits(conn, username)
history = get_history(conn, username)

# SOL PANEL (MENÜ)
with st.sidebar:
    st.title("⚙️ Panel")
    if is_premium:
        st.success(f"💎 PREMIUM ÜYE\nBitiş: {premium_expiry}")
    else:
        st.write(f"**Hak:** {kredi}/5")
        st.progress(kredi/5)
    st.divider()
    
    seviye = st.selectbox("Sınıf Seviyesi", ["🐣 İlkokul", "📘 Ortaokul", "🏫 Lise", "🎓 Üniversite"])
    mod = st.selectbox("Çalışma Modu", ["❓ Soru Çözümü", "📚 Konu Anlatımı", "📝 Kompozisyon Yaz", "💬 Sohbet", "🏠 Ödev Yardımı", "📂 Dosya Analizi (Premium)"])
    
    st.subheader("👨‍🏫 Öğretmen Tarzı")
    if is_premium:
        persona = st.radio("Seç:", ["Normal", "Komik", "Disiplinli", "Samimi"])
    else:
        st.info("🔒 Sadece Premium")
        persona = "Normal"
        
    st.divider()
    
    st.markdown("<div class='premium-box'>", unsafe_allow_html=True)
    if not is_premium:
        st.markdown("### 🚀 Premium Ol")
        st.markdown("Sınırsız Soru, Dosya Yükleme, Sesli Dinleme")
        st.markdown("<h2 style='color:white'>49 TL / 3 Ay</h2>", unsafe_allow_html=True)
        st.markdown('<a href="#" class="buy-btn">SATIN AL</a>', unsafe_allow_html=True)
        st.markdown("---")
        kod_giris = st.text_input("Kod Gir", placeholder="SOA-XXXX")
        if st.button("Aktifleştir"):
            if kod_giris:
                basari, mesaj = activate_premium(conn, username, kod_giris.strip())
                if basari: st.balloons(); st.success(mesaj); st.rerun()
                else: st.error(mesaj)
    else:
        st.write("Premium Keyfini Çıkar! 🎉")
    st.markdown("</div>", unsafe_allow_html=True)
    
    if st.button("Çıkış Yap"):
        st.session_state.username = None
        st.session_state.messages = []
        st.rerun()

# ANA BAŞLIK
st.title("🎓 Okul Asistanı")

if "Kompozisyon" in mod:
    st.info("📝 Kompozisyon Modu: Konuyu yaz, gerisini bana bırak.")

# Dosya Yükleme (Sadece Premium)
uploaded_text = ""
uploaded_image = None
if "Dosya Analizi" in mod:
    if is_premium:
        uploaded_file = st.file_uploader("Dosya Yükle", type=['pdf', 'docx', 'txt', 'png', 'jpg'])
        if uploaded_file:
            try:
                if uploaded_file.name.endswith(".pdf"):
                    pdf_reader = pypdf.PdfReader(uploaded_file)
                    for page in pdf_reader.pages: uploaded_text += page.extract_text()
                    st.success("PDF Okundu!")
                elif uploaded_file.name.endswith(('.png', '.jpg')):
                    uploaded_image = Image.open(uploaded_file)
                    st.image(uploaded_image, width=300)
                    st.success("Resim Yüklendi!")
                elif uploaded_file.name.endswith(".docx"):
                    doc = Document(uploaded_file)
                    for para in doc.paragraphs: uploaded_text += para.text + "\n"
                    st.success("Word Okundu!")
                elif uploaded_file.name.endswith(".txt"):
                    uploaded_text = str(uploaded_file.read(), "utf-8")
                    st.success("Metin Okundu!")
            except Exception as e:
                st.error(f"Dosya okuma hatası: {e}")
    else:
        st.warning("🔒 Dosya yüklemek için Premium olmalısın.")

# GEÇMİŞ MESAJLARI GÖSTER
for role, content in history:
    with st.chat_message(role):
        st.markdown(content)
if len(history) == 0:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

# KULLANICI MESAJ ALANI
prompt_text = "Sorunu buraya yaz..."
if "Kompozisyon" in mod: prompt_text = "Kompozisyon konusunu yaz..."

if prompt := st.chat_input(prompt_text):
    
    if kredi <= 0 and not is_premium:
        st.error("Günlük hakkın doldu. Yarın gel veya Premium al.")
    else:
        save_message(conn, username, "user", prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            msg_box = st.empty()
            msg_box.markdown("Düşünüyorum... 🧠")
            
            try:
                system_prompt = f"""Sen Okul Asistanısın. 
                Seviye: {seviye}
                Mod: {mod}
                Öğretmen Stili: {persona}
                Soru/Mesaj: {prompt}"""
                
                content_parts = [system_prompt]
                if uploaded_text: content_parts.append(f"\nDosya Metni: {uploaded_text}")
                if uploaded_image: content_parts.append(uploaded_image)

                response = model.generate_content(content_parts)
                cevap = response.text
                
                msg_box.markdown(cevap)
                save_message(conn, username, "assistant", cevap)
                
                if not is_premium:
                    deduct_credit(conn, username)
                
                if is_premium:
                    try:
                        tts_text = temizle_ve_konus(cevap)
                        tts = gTTS(text=tts_text, lang='tr')
                        audio_bytes = io.BytesIO()
                        tts.write_to_fp(audio_bytes)
                        st.audio(audio_bytes, format='audio/mp3')
                    except: pass

            except Exception as e:
                msg_box.error(f"Hata oluştu: {e}")
