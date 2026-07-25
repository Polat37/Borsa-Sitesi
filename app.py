import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, date
import google.generativeai as genai
import requests
import re
import json
import firebase_admin
from firebase_admin import credentials, firestore

# ==========================================
# API AYARLARI
# ==========================================
GEMINI_API_KEY = ""

# ==========================================
# FIREBASE BULUT VERİTABANI BAĞLANTISI
# ==========================================
if not firebase_admin._apps:
    if "FIREBASE_KEY" in st.secrets:
        try:
            key_dict = json.loads(st.secrets["FIREBASE_KEY"])
            cred = credentials.Certificate(key_dict)
            firebase_admin.initialize_app(cred)
        except Exception as e:
            st.error(f"Firebase bağlantı hatası: {e}")
            st.stop()
    else:
        st.error("⚠️ Firebase Gizli Anahtarı (FIREBASE_KEY) Streamlit Secrets içinde bulunamadı!")
        st.stop()

db = firestore.client()

# --- BİST 100 VE POPÜLER YABANCI HİSSELER ---
bist100_hisseleri = [
    "AGHOL.IS", "AKBNK.IS", "AKCNS.IS", "AKFGY.IS", "AKSA.IS", "AKSEN.IS", "ALARK.IS", "ALBRK.IS", "ALFAS.IS", 
    "ARCLK.IS", "ASELS.IS", "ASTOR.IS", "ASUZU.IS", "AYDEM.IS", "BAGFS.IS", "BERA.IS", "BIENY.IS", "BIMAS.IS", 
    "BIOEN.IS", "BOBET.IS", "BRSAN.IS", "BRYAT.IS", "BUCIM.IS", "CANTE.IS", "CCOLA.IS", "CEMAS.IS", "CIMSA.IS", 
    "CWENE.IS", "DOHOL.IS", "DOAS.IS", "ECILC.IS", "ECZYT.IS", "EGEEN.IS", "EKGYO.IS", "ENERY.IS", "ENJSA.IS", 
    "ENKAI.IS", "EREGL.IS", "EUPWR.IS", "EUREN.IS", "FROTO.IS", "GARAN.IS", "GENIL.IS", "GESAN.IS", "GLYHO.IS", 
    "GUBRF.IS", "GWIND.IS", "HALKB.IS", "HEKTS.IS", "HKTM.IS", "HLGYO.IS", "IPEKE.IS", "ISCTR.IS", "ISDMR.IS", 
    "ISGYO.IS", "ISMEN.IS", "IZENR.IS", "KALES.IS", "KARSN.IS", "KCAER.IS", "KCHOL.IS", "KMPUR.IS", "KONTR.IS", 
    "KONYA.IS", "KOZAA.IS", "KOZAL.IS", "KRDMD.IS", "KZBGY.IS", "MAVI.IS", "MGROS.IS", "MIATK.IS", "ODAS.IS", 
    "OTKAR.IS", "OYAKC.IS", "PENTA.IS", "PETKM.IS", "PGSUS.IS", "PNLSN.IS", "QUAGR.IS", "SAHOL.IS", "SASA.IS", 
    "SAYAS.IS", "SISE.IS", "SKBNK.IS", "SMRTG.IS", "SOKM.IS", "TABGD.IS", "TAVHL.IS", "TCELL.IS", "THYAO.IS", 
    "TKFEN.IS", "TOASO.IS", "TSKB.IS", "TTKOM.IS", "TUKAS.IS", "TUPRS.IS", "ULKER.IS", "VAKBN.IS", "VESBE.IS", 
    "VESTL.IS", "YEOTK.IS", "YKBNK.IS", "YYLGD.IS", "ZOREN.IS"
]

populer_yabanci = [
    "AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "GOOGL", "META", "AMD", "INTC", 
    "SPY", "QQQ", "VOO", "PLTR", "COIN", "BABA", "NFLX", "MSTR", "SPCX"
]

tum_semboller = bist100_hisseleri + populer_yabanci

# --- 1. AYARLAR ---
st.set_page_config(page_title="Canlı Portföy & Analiz", page_icon="📈", layout="wide")

# --- ÖZEL CSS ---
st.markdown("""
    <style>
        div[data-baseweb="select"], 
        div[data-baseweb="select"] > div, 
        div[data-baseweb="select"] > div > div {
            border-radius: 30px !important;
        }
        div[data-baseweb="select"] > div {
            padding-left: 10px !important;
            overflow: hidden !important;
        }
        .block-container {
            padding-top: 2rem !important; 
        }
    </style>
""", unsafe_allow_html=True)

if 'aktif_sayfa' not in st.session_state:
    st.session_state.aktif_sayfa = "Portföy"

# --- TEFAS VERİ KAZIYICI ---
def get_tefas_fiyat(fon_kodu):
    url = f"https://www.tefas.gov.tr/FonAnaliz.aspx?FonKod={fon_kodu.upper()}"
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7'
        }
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            match = re.search(r'LabelPrice">([\d.,]+)</span>', response.text)
            if match:
                fiyat_str = match.group(1).replace('.', '').replace(',', '.')
                return float(fiyat_str)
    except: pass
    return None

# --- TEKNİK ANALİZ YARDIMCI FONKSİYONLARI ---
def sinyal_etiketi_ver(skor, max_skor):
    if max_skor == 0: return "⚪ Nötr"
    oran = skor / max_skor
    if oran >= 0.8: return "🚀 Güçlü AL"
    elif oran >= 0.6: return "🟢 AL"
    elif oran >= 0.4: return "⚪ Nötr"
    elif oran >= 0.2: return "🔴 SAT"
    else: return "💥 Güçlü SAT"

def analiz_et(df, periyot, aktif_araclar):
    if len(df) < max(periyot, 20): return 0
    skor = 0
    son_gun = df.iloc[-1]
    
    if "RSI (14)" in aktif_araclar:
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi_val = 100 - (100 / (1 + rs)).iloc[-1]
        if rsi_val < 30 or rsi_val > 50: skor += 1
    if "SMA (Basit Ortalama)" in aktif_araclar:
        sma = df['Close'].rolling(periyot).mean().iloc[-1]
        if son_gun['Close'] > sma: skor += 1
    if "EMA (Üstel Ortalama)" in aktif_araclar:
        ema = df['Close'].ewm(span=periyot, adjust=False).mean().iloc[-1]
        if son_gun['Close'] > ema: skor += 1
    if "MACD" in aktif_araclar:
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal_line = macd.ewm(span=9, adjust=False).mean()
        if macd.iloc[-1] > signal_line.iloc[-1]: skor += 1
    if "Bollinger Bantları" in aktif_araclar:
        sma20 = df['Close'].rolling(20).mean()
        std = df['Close'].rolling(20).std()
        b_alt = (sma20 - (std * 2)).iloc[-1]
        if son_gun['Close'] <= b_alt * 1.05: skor += 1
    if "Stochastic" in aktif_araclar:
        low14 = df['Low'].rolling(14).min()
        high14 = df['High'].rolling(14).max()
        stoch_k = (100 * (df['Close'] - low14) / (high14 - low14)).iloc[-1]
        if stoch_k < 20: skor += 1
    if "Williams %R" in aktif_araclar:
        low14 = df['Low'].rolling(14).min()
        high14 = df['High'].rolling(14).max()
        will_r = (-100 * (high14 - df['Close']) / (high14 - low14)).iloc[-1]
        if will_r < -80: skor += 1
    if "ROC" in aktif_araclar:
        roc = (((df['Close'] - df['Close'].shift(14)) / df['Close'].shift(14)) * 100).iloc[-1]
        if roc > 0: skor += 1
    if "Momentum" in aktif_araclar:
        mom = (df['Close'] - df['Close'].shift(10)).iloc[-1]
        if mom > 0: skor += 1
    if "CCI (Emtia Kanal Endeksi)" in aktif_araclar:
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        sma_tp = tp.rolling(20).mean()
        md = tp.rolling(20).apply(lambda x: (x - x.mean()).abs().mean(), raw=False)
        cci = ((tp - sma_tp) / (0.015 * md)).iloc[-1]
        if cci < -100: skor += 1
    return skor

@st.cache_data(ttl=3600)
def coklu_zaman_dilimi_taramasi(analiz_periyodu, aktif_araclar):
    data = yf.download(" ".join(bist100_hisseleri), period="5y", progress=False)
    sonuclar = []
    max_skor = len(aktif_araclar)
    
    for hisse in bist100_hisseleri:
        try:
            df_gunluk = pd.DataFrame()
            df_gunluk['Open'] = data['Open'][hisse] if len(bist100_hisseleri) > 1 else data['Open']
            df_gunluk['High'] = data['High'][hisse] if len(bist100_hisseleri) > 1 else data['High']
            df_gunluk['Low'] = data['Low'][hisse] if len(bist100_hisseleri) > 1 else data['Low']
            df_gunluk['Close'] = data['Close'][hisse] if len(bist100_hisseleri) > 1 else data['Close']
            df_gunluk = df_gunluk.dropna()
            
            if len(df_gunluk) < 200: continue
            
            df_haftalik = df_gunluk.resample('W').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last'}).dropna()
            df_aylik = df_gunluk.resample('ME').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last'}).dropna()
            
            skor_kisa = analiz_et(df_gunluk, analiz_periyodu, aktif_araclar)
            skor_orta = analiz_et(df_haftalik, analiz_periyodu, aktif_araclar)
            skor_uzun = analiz_et(df_aylik, analiz_periyodu, aktif_araclar)
            
            sonuclar.append({
                "Hisse": hisse,
                "Fiyat": float(df_gunluk['Close'].iloc[-1]),
                "Kısa Vade (<1 Ay)": sinyal_etiketi_ver(skor_kisa, max_skor),
                "Orta Vade (1-6 Ay)": sinyal_etiketi_ver(skor_orta, max_skor),
                "Uzun Vade (6+ Ay)": sinyal_etiketi_ver(skor_uzun, max_skor),
                "Skor (K | O | U)": f"{skor_kisa} | {skor_orta} | {skor_uzun}",
                "Toplam Puan": skor_kisa + skor_orta + skor_uzun 
            })
        except Exception:
            continue
    return sorted(sonuclar, key=lambda x: x["Toplam Puan"], reverse=True)

def hisse_coklu_vade_analizi(hisse):
    try:
        df_g = yf.download(hisse, period="2y", progress=False)
        if isinstance(df_g.columns, pd.MultiIndex): df_g.columns = df_g.columns.get_level_values(0)
        df_g = df_g.dropna()
        if len(df_g) < 50: return "Veri Yetersiz", "Veri Yetersiz", "Veri Yetersiz"
        
        df_w = df_g.resample('W').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last'}).dropna()
        df_m = df_g.resample('ME').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last'}).dropna()
        
        araclar = ["RSI (14)", "SMA (Basit Ortalama)", "MACD", "Bollinger Bantları"]
        sk_kisa = analiz_et(df_g, 20, araclar)
        sk_orta = analiz_et(df_w, 10, araclar)
        sk_uzun = analiz_et(df_m, 6, araclar)
        max_s = len(araclar)
        
        return sinyal_etiketi_ver(sk_kisa, max_s), sinyal_etiketi_ver(sk_orta, max_s), sinyal_etiketi_ver(sk_uzun, max_s)
    except:
        return "Hata", "Hata", "Hata"

# --- FIREBASE VERİ FONKSİYONLARI ---
def get_portfoy():
    docs = db.collection('islemler').order_by('tarih', direction=firestore.Query.ASCENDING).stream()
    portfoy = {}
    
    for doc in docs:
        row = doc.to_dict()
        hisse = row.get('hisse_kodu', '').upper()
        tip = row.get('islem_tipi', '')
        adet = float(row.get('adet', 0))
        fiyat = float(row.get('fiyat', 0))
        
        if hisse not in portfoy: portfoy[hisse] = {"adet": 0.0, "ort_maliyet": 0.0}
        m_adet, m_maliyet = portfoy[hisse]["adet"], portfoy[hisse]["ort_maliyet"]
        
        if tip == 'AL':
            yeni_adet = m_adet + adet
            portfoy[hisse]["ort_maliyet"] = ((m_adet * m_maliyet) + (adet * fiyat)) / yeni_adet if yeni_adet > 0 else 0
            portfoy[hisse]["adet"] = yeni_adet
        elif tip == 'SAT':
            portfoy[hisse]["adet"] = max(0.0, m_adet - adet)
            if portfoy[hisse]["adet"] < 0.0001: portfoy[hisse]["ort_maliyet"] = 0.0
            
    return {k: v for k, v in portfoy.items() if v["adet"] > 0}

def get_islem_gecmisi():
    docs = db.collection('islemler').order_by('tarih', direction=firestore.Query.ASCENDING).stream()
    gecmis = []
    durum = {} 

    for doc in docs:
        row = doc.to_dict()
        islem_id = doc.id
        hisse = row.get('hisse_kodu', '')
        tip = row.get('islem_tipi', '')
        adet = float(row.get('adet', 0))
        fiyat = float(row.get('fiyat', 0))
        tarih = row.get('tarih', '')[:16].replace('T', ' ')

        if hisse not in durum:
            durum[hisse] = {'adet': 0.0, 'maliyet': 0.0}

        m_adet = durum[hisse]['adet']
        m_maliyet = durum[hisse]['maliyet']
        
        tutar = adet * fiyat
        kar_zarar = None

        if tip == 'AL':
            yeni_adet = m_adet + adet
            yeni_maliyet = ((m_adet * m_maliyet) + tutar) / yeni_adet if yeni_adet > 0 else 0
            durum[hisse]['adet'] = yeni_adet
            durum[hisse]['maliyet'] = yeni_maliyet
        elif tip == 'SAT':
            kar_zarar = (fiyat - m_maliyet) * adet
            durum[hisse]['adet'] = max(0.0, m_adet - adet)
            if durum[hisse]['adet'] < 0.0001:
                durum[hisse]['maliyet'] = 0.0

        gecmis.append({
            "ID": islem_id,
            "Tarih": tarih,
            "Varlık": hisse.replace('.TEFAS', ' (Fon)'),
            "İşlem": "🟢 AL" if tip == 'AL' else "🔴 SAT",
            "Fiyat": fiyat,
            "Adet": adet,
            "Toplam Tutar": tutar,
            "Kar/Zarar": kar_zarar
        })
        
    return list(reversed(gecmis))

# --- MODALLAR (FIREBASE UYUMLU) ---
@st.dialog("📝 Manuel İşlem Ekle")
def manuel_islem_modali():
    with st.form("manuel_islem_formu"):
        varlik_tipi = st.radio("Varlık Tipi Seçin", ["Hisse / Borsa Fonu (BİST & ABD)", "TEFAS Yatırım Fonu (Örn: MAC, TI3)"], horizontal=True)
        girilen_hisse = st.text_input("Varlık Kodu (Örn: TUPRS.IS, AAPL veya MAC)")
        islem_tipi = st.selectbox("İşlem Tipi", ["AL", "SAT"])
        fiyat = st.number_input("İşlem Fiyatı", min_value=0.0, format="%.4f")
        adet = st.number_input("Adet", min_value=0.001, step=1.0, format="%.3f")
        kaydet = st.form_submit_button("İşlemi Kaydet", type="primary", use_container_width=True)
        
        if kaydet and girilen_hisse:
            temiz_kod = girilen_hisse.strip().upper()
            kaydedilecek_kod = f"{temiz_kod}.TEFAS" if "TEFAS" in varlik_tipi else temiz_kod
            
            db.collection('islemler').add({
                'hisse_kodu': kaydedilecek_kod,
                'islem_tipi': islem_tipi,
                'fiyat': fiyat,
                'adet': adet,
                'tarih': datetime.now().isoformat()
            })
            st.cache_data.clear()
            st.rerun()

@st.dialog("📊 Detaylar ve Hızlı İşlem", width="large")
def grafik_ve_getiri_modali(hisse):
    if hisse.endswith('.TEFAS'):
        fon_kodu = hisse.replace('.TEFAS', '')
        with st.spinner(f"TEFAS üzerinden {fon_kodu} güncel fiyatı çekiliyor..."):
            fiyat = get_tefas_fiyat(fon_kodu)
            st.subheader(f"🏦 {fon_kodu} - TEFAS Yatırım Fonu")
            if fiyat is not None:
                st.markdown(f"<h2 style='color: #00FF00;'>{fiyat:,.4f} ₺</h2>", unsafe_allow_html=True)
                st.info("TEFAS fonları için anlık fiyat web üzerinden çekilmektedir.")
            else:
                st.error("TEFAS sisteminden fiyat çekilemedi.")
                fiyat = 0.0
            st.divider()
            st.subheader(f"⚡ {fon_kodu} Hızlı İşlem")
            with st.form(f"hizli_islem_formu_{hisse}"):
                fc1, fc2, fc3 = st.columns(3)
                i_tipi = fc1.selectbox("İşlem Tipi", ["AL", "SAT"])
                i_fiyat = fc2.number_input("Fiyat", value=float(fiyat), format="%.4f")
                i_adet = fc3.number_input("Adet", min_value=0.001, step=1.0, format="%.3f")
                if st.form_submit_button("İşlemi Kaydet", type="primary", use_container_width=True):
                    db.collection('islemler').add({
                        'hisse_kodu': hisse.upper(),
                        'islem_tipi': i_tipi,
                        'fiyat': i_fiyat,
                        'adet': i_adet,
                        'tarih': datetime.now().isoformat()
                    })
                    if 'aranan_secim' in st.session_state: st.session_state.aranan_secim = None
                    st.cache_data.clear()
                    st.rerun()
        return 
    
    with st.spinner("Piyasa verileri, teknik analiz ve grafik yükleniyor..."):
        df = yf.download(hisse, period="1y", progress=False)
        temel_veriler = {'F/K': 'Yok', 'PD/DD': 'Yok', 'Piyasa Değeri': 'Yok', 'Temettü Verimi': 'Yok'}
        try:
            ticker_obj = yf.Ticker(hisse)
            info = ticker_obj.info
            fk = info.get('trailingPE', None)
            pddd = info.get('priceToBook', None)
            pd_deger = info.get('marketCap', None)
            temettu = info.get('dividendYield', None)
            if fk: temel_veriler['F/K'] = f"{fk:.2f}"
            if pddd: temel_veriler['PD/DD'] = f"{pddd:.2f}"
            if pd_deger:
                para_sembolu = "₺" if hisse.endswith(".IS") else "$"
                if pd_deger >= 1e9: temel_veriler['Piyasa Değeri'] = f"{pd_deger/1e9:.2f} Milyar {para_sembolu}"
                elif pd_deger >= 1e6: temel_veriler['Piyasa Değeri'] = f"{pd_deger/1e6:.2f} Milyon {para_sembolu}"
                else: temel_veriler['Piyasa Değeri'] = f"{pd_deger:,} {para_sembolu}"
            if temettu: temel_veriler['Temettü Verimi'] = f"%{temettu*100:.2f}"
        except: pass

        if df.empty:
            st.error("Veri bulunamadı.")
            return
            
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df.dropna(subset=['Open', 'High', 'Low', 'Close']).reset_index() 
        anlik_fiyat = float(df['Close'].iloc[-1])
        para_birimi = "₺" if hisse.endswith(".IS") else "$"
        
        col_baslik, col_fiyat = st.columns([2, 1])
        with col_baslik: st.subheader(f"{hisse} Performans Özeti")
        with col_fiyat: st.markdown(f"<h2 style='text-align: right; color: #00FF00; margin-top: -10px;'>{anlik_fiyat:,.2f} {para_birimi}</h2>", unsafe_allow_html=True)
        
        def getiri_hesapla(gun_farki):
            if len(df) > gun_farki:
                eski_fiyat = float(df['Close'].iloc[-(gun_farki + 1)])
                if eski_fiyat > 0: return ((anlik_fiyat - eski_fiyat) / eski_fiyat) * 100
            return None

        g_1h = getiri_hesapla(5)
        g_1a = getiri_hesapla(21)
        g_6a = getiri_hesapla(126)
        g_1y = getiri_hesapla(len(df)-1)

        c1, c2, c3, c4 = st.columns(4)
        def metrik_yaz(col, baslik, oran):
            if oran is not None: col.metric(baslik, f"%{oran:.2f}", delta=f"{oran:.2f}%")
            else: col.metric(baslik, "Veri Yok")

        metrik_yaz(c1, "1 Haftalık", g_1h)
        metrik_yaz(c2, "1 Aylık", g_1a)
        metrik_yaz(c3, "6 Aylık", g_6a)
        metrik_yaz(c4, "1 Yıllık", g_1y)
        st.divider()

        st.markdown("#### 🎯 Çoklu Vade Teknik Analiz Sinyalleri")
        sig_kisa, sig_orta, sig_uzun = hisse_coklu_vade_analizi(hisse)
        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("Kısa Vade (<1 Ay)", sig_kisa)
        sc2.metric("Orta Vade (1-6 Ay)", sig_orta)
        sc3.metric("Uzun Vade (6+ Ay)", sig_uzun)
        st.divider()

        st.markdown("#### 🏛️ Temel Analiz Verileri")
        t1, t2, t3, t4 = st.columns(4)
        t1.metric("F/K Oranı", temel_veriler['F/K'])
        t2.metric("PD/DD", temel_veriler['PD/DD'])
        t3.metric("Piyasa Değeri", temel_veriler['Piyasa Değeri'])
        t4.metric("Temettü Verimi", temel_veriler['Temettü Verimi'])
        st.divider()

        st.markdown("#### 🤖 Yapay Zeka Yorumu")
        if st.button(f"🧠 {hisse} İçin Gemini Yapay Zeka Analizi Üret", use_container_width=True):
            with st.spinner("Gemini analiz yapıyor..."):
                try:
                    genai.configure(api_key=GEMINI_API_KEY)
                    model = genai.GenerativeModel('gemini-3.5-flash')
                    val_1a = f"%{g_1a:.2f}" if g_1a is not None else "Veri Yok"
                    prompt = f"""Sen profesyonel bir yatırım danışmanısın. {hisse} varlığı için veriler: Fiyat: {anlik_fiyat} {para_birimi}, F/K: {temel_veriler['F/K']}, Teknik Sinyaller (Kısa/Orta/Uzun): {sig_kisa} / {sig_orta} / {sig_uzun}, 1 Aylık Getiri: {val_1a}. 4 cümleyi geçmeyecek şekilde özetle. En sona 'Yatırım tavsiyesi değildir.' ekle."""
                    response = model.generate_content(prompt)
                    st.info(response.text)
                except Exception as e:
                    st.error(f"Yapay zeka hatası: {e}")
        st.divider()
        
        grafik_alani = st.empty() 
        _, col_zaman_butonlari = st.columns([3, 2]) 
        with col_zaman_butonlari:
            secilen_aralik = st.radio("Zaman Aralığı", ["1 Hafta", "1 Ay", "6 Ay", "1 Yıl"], index=3, horizontal=True, label_visibility="collapsed")

        if secilen_aralik == "1 Hafta": df_grafik = df.tail(5) 
        elif secilen_aralik == "1 Ay": df_grafik = df.tail(21) 
        elif secilen_aralik == "6 Ay": df_grafik = df.tail(126) 
        else: df_grafik = df 

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_width=[0.2, 0.7])
        fig.add_trace(go.Candlestick(x=df_grafik['Date'], open=df_grafik['Open'], high=df_grafik['High'], low=df_grafik['Low'], close=df_grafik['Close'], increasing_line_color='#00FF00', decreasing_line_color='#FF4B4B'), row=1, col=1)
        colors = ['#00FF00' if row['Close'] >= row['Open'] else '#FF4B4B' for index, row in df_grafik.iterrows()]
        if 'Volume' in df_grafik.columns:
            fig.add_trace(go.Bar(x=df_grafik['Date'], y=df_grafik['Volume'], marker_color=colors), row=2, col=1)

        fig.update_layout(xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, t=30, b=0), showlegend=False, height=500)
        grafik_alani.plotly_chart(fig, use_container_width=True)
        st.divider()
        
        st.subheader(f"⚡ {hisse} Hızlı İşlem")
        with st.form(f"hizli_islem_formu_{hisse}"):
            fc1, fc2, fc3 = st.columns(3)
            i_tipi = fc1.selectbox("İşlem Tipi", ["AL", "SAT"])
            i_fiyat = fc2.number_input("Fiyat", value=anlik_fiyat, format="%.2f")
            i_adet = fc3.number_input("Adet", min_value=0.001, step=0.01, format="%.3f")
            if st.form_submit_button("İşlemi Kaydet", type="primary", use_container_width=True):
                db.collection('islemler').add({
                    'hisse_kodu': hisse.upper(),
                    'islem_tipi': i_tipi,
                    'fiyat': i_fiyat,
                    'adet': i_adet,
                    'tarih': datetime.now().isoformat()
                })
                if 'aranan_secim' in st.session_state: st.session_state.aranan_secim = None
                st.cache_data.clear()
                st.rerun()

@st.dialog("✏️ Düzenle")
def duzenle_modal(hisse, mevcut_adet, mevcut_maliyet):
    yeni_adet = st.number_input("Adet", value=float(mevcut_adet), format="%.3f")
    yeni_maliyet = st.number_input("Maliyet", value=float(mevcut_maliyet), format="%.4f")
    if st.button("Kaydet", type="primary"):
        # Eski kayıtları temizle
        docs = db.collection('islemler').where('hisse_kodu', '==', hisse).stream()
        for doc in docs: doc.reference.delete()
        
        # Yeni özet kayıt ekle
        db.collection('islemler').add({
            'hisse_kodu': hisse,
            'islem_tipi': 'AL',
            'fiyat': yeni_maliyet,
            'adet': yeni_adet,
            'tarih': datetime.now().isoformat()
        })
        st.cache_data.clear()
        st.rerun()

@st.dialog("🗑️ Varlığı Portföyden Sil")
def sil_modal(hisse):
    st.warning("Emin misiniz? Bu varlığa ait tüm portföy kayıtları silinecek.")
    if st.button("Evet, Sil", type="primary"):
        docs = db.collection('islemler').where('hisse_kodu', '==', hisse).stream()
        for doc in docs: doc.reference.delete()
        st.cache_data.clear()
        st.rerun()

@st.dialog("🗑️ İşlem Kaydını Sil")
def islem_gecmisi_sil_modal(islem_id):
    st.warning("Seçili işlem kaydını silmek istediğinize emin misiniz? Bu işlem portföy maliyet ve adetlerinizi etkileyebilir.")
    if st.button("Evet, Kaydı Sil", type="primary"):
        db.collection('islemler').document(islem_id).delete()
        st.cache_data.clear()
        st.rerun()

@st.dialog("🧹 Geçmişi Temizle (Portföyü Koru)")
def gecmisi_temizle_modal():
    st.warning("DİKKAT: Eski alım/satım tablo geçmişiniz temizlenecek. Ancak ŞU ANKİ mevcut portföyünüz (hisse adetleri ve maliyetleri) yeni bir başlangıç kaydı olarak KORUNACAK. Grafikleriniz bozulmayacaktır. Onaylıyor musunuz?")
    if st.button("Evet, Sadece Geçmiş Tablosunu Temizle", type="primary"):
        mevcut_portfoy = get_portfoy()
        
        for doc in db.collection('islemler').stream(): 
            doc.reference.delete()
            
        for hisse, veri in mevcut_portfoy.items():
            if veri['adet'] > 0:
                db.collection('islemler').add({
                    'hisse_kodu': hisse,
                    'islem_tipi': 'AL',
                    'fiyat': veri['ort_maliyet'],
                    'adet': veri['adet'],
                    'tarih': datetime.now().isoformat()
                })
        st.cache_data.clear()
        st.rerun()

@st.dialog("⚠️ Tüm Geçmişi Sıfırla")
def tumunu_sifirla_modal():
    st.error("DİKKAT: Bu buton tüm işlem geçmişinizi ve aktif portföyünüzü kalıcı olarak silecektir. Emin misiniz?")
    if st.button("Evet, Her Şeyi Sıfırla", type="primary"):
        for doc in db.collection('islemler').stream(): doc.reference.delete()
        for doc in db.collection('portfoy_gecmisi').stream(): doc.reference.delete()
        st.cache_data.clear()
        st.rerun()

# --- HARİCİ VERİ FONKSİYONLARI ---
@st.cache_data(ttl=300)
def get_stock_prices(tickers):
    if not tickers: return {}
    yfinance_tickers = [t for t in tickers if not t.endswith('.TEFAS')]
    tefas_tickers = [t for t in tickers if t.endswith('.TEFAS')]
    results = {}
    
    if yfinance_tickers:
        data = yf.download(" ".join(yfinance_tickers), period="2d", progress=False)
        for ticker in yfinance_tickers:
            try:
                close_prices = data['Close'][ticker] if len(yfinance_tickers) > 1 else data['Close']
                close_prices = close_prices.dropna()
                if len(close_prices) >= 2: results[ticker] = {"anlik_fiyat": float(close_prices.iloc[-1]), "dunku_kapanis": float(close_prices.iloc[-2])}
                elif len(close_prices) == 1: results[ticker] = {"anlik_fiyat": float(close_prices.iloc[0]), "dunku_kapanis": float(close_prices.iloc[0])}
            except: pass

    for ticker in tefas_tickers:
        kodu = ticker.replace('.TEFAS', '')
        fiyat = get_tefas_fiyat(kodu)
        if fiyat is not None:
            results[ticker] = {"anlik_fiyat": fiyat, "dunku_kapanis": fiyat}
        else:
            results[ticker] = {"anlik_fiyat": 0.0, "dunku_kapanis": 0.0} 
    return results

@st.cache_data(ttl=300)
def get_exchange_rates():
    kurlar = {"USD": 33.0, "EUR": 36.0, "CNY": 4.5, "PLN": 8.0}
    try:
        data = yf.download("TRY=X EURTRY=X CNYTRY=X PLNTRY=X", period="1d", progress=False)
        if not data.empty:
            if 'TRY=X' in data['Close']: kurlar["USD"] = float(data['Close']['TRY=X'].dropna().iloc[-1])
            if 'EURTRY=X' in data['Close']: kurlar["EUR"] = float(data['Close']['EURTRY=X'].dropna().iloc[-1])
            if 'CNYTRY=X' in data['Close']: kurlar["CNY"] = float(data['Close']['CNYTRY=X'].dropna().iloc[-1])
            if 'PLNTRY=X' in data['Close']: kurlar["PLN"] = float(data['Close']['PLNTRY=X'].dropna().iloc[-1])
    except: pass
    return kurlar

# --- YAN MENÜ ---
st.sidebar.markdown("### 🧭 Menü")
if st.sidebar.button("💼 Portföyüm", use_container_width=True, type="primary" if st.session_state.aktif_sayfa == "Portföy" else "secondary"):
    st.session_state.aktif_sayfa = "Portföy"
    st.rerun()
if st.sidebar.button("👁️ İzleme Listesi", use_container_width=True, type="primary" if st.session_state.aktif_sayfa == "İzleme Listesi" else "secondary"):
    st.session_state.aktif_sayfa = "İzleme Listesi"
    st.rerun()
if st.sidebar.button("🎯 Çoklu Vade Tarayıcı", use_container_width=True, type="primary" if st.session_state.aktif_sayfa == "Tarayıcı" else "secondary"):
    st.session_state.aktif_sayfa = "Tarayıcı"
    st.rerun()
if st.sidebar.button("🤖 Yapay Zeka Asistanı", use_container_width=True, type="primary" if st.session_state.aktif_sayfa == "AI_Sohbet" else "secondary"):
    st.session_state.aktif_sayfa = "AI_Sohbet"
    st.rerun()
if st.sidebar.button("💸 Finansal Özgürlük", use_container_width=True, type="primary" if st.session_state.aktif_sayfa == "FIRE" else "secondary"):
    st.session_state.aktif_sayfa = "FIRE"
    st.rerun()

st.sidebar.divider()
kurlar = get_exchange_rates()
st.sidebar.markdown("### 💱 Anlık Kurlar (₺)")
c_kur1, c_kur2 = st.sidebar.columns(2)
c_kur1.caption(f"💵 USD: **{kurlar.get('USD', 0):.2f}**")
c_kur2.caption(f"💶 EUR: **{kurlar.get('EUR', 0):.2f}**")
c_kur3, c_kur4 = st.sidebar.columns(2)
c_kur3.caption(f"💴 CNY: **{kurlar.get('CNY', 0):.2f}**")
c_kur4.caption(f"🇵🇱 PLN: **{kurlar.get('PLN', 0):.2f}**")

# --- MERKEZE HİZALANMIŞ OVAL ARAMA ÇUBUĞU ---
if 'aranan_secim' not in st.session_state: st.session_state.aranan_secim = None
st.markdown("<div style='margin-top: 30px;'></div>", unsafe_allow_html=True)
bos_sol, arama_sutunu, bos_sag = st.columns([1.5, 2, 1.5])

with arama_sutunu:
    aranan_hisse = st.selectbox(
        "Arama", 
        options=tum_semboller, 
        index=None, 
        placeholder="🔍 Hisse Kodu Ara (Örn: THYAO.IS)...", 
        key="aranan_secim", 
        label_visibility="collapsed"
    )

if st.session_state.aranan_secim:
    grafik_ve_getiri_modali(st.session_state.aranan_secim)
st.divider()

# ==========================================
# SAYFA 1: PORTFÖYÜM
# ==========================================
if st.session_state.aktif_sayfa == "Portföy":
    c_title, c_btn = st.columns([3, 1])
    with c_title:
        st.title("📈 Canlı Portföy Durumu")
    with c_btn:
        st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)
        if st.button("➕ Manuel İşlem Ekle", use_container_width=True, type="primary"): 
            manuel_islem_modali()

    portfoy_verisi = get_portfoy()
    
    tickers = list(portfoy_verisi.keys()) if portfoy_verisi else []
    fiyatlar = get_stock_prices(tickers) if tickers else {}
    t_deger = t_maliyet = t_gunluk = 0
    pasta_verisi = [] 
    h_veriler = []
    usd_kur = kurlar.get("USD", 33.0)
    
    sektor_haritasi = {
        "THYAO.IS": "Ulaştırma", "PGSUS.IS": "Ulaştırma", "TAVHL.IS": "Ulaştırma",
        "AKBNK.IS": "Bankacılık", "GARAN.IS": "Bankacılık", "ISCTR.IS": "Bankacılık", "HALKB.IS": "Bankacılık", "VAKBN.IS": "Bankacılık", "YKBNK.IS": "Bankacılık", "TSKB.IS": "Bankacılık", "ALBRK.IS": "Bankacılık", "SKBNK.IS": "Bankacılık",
        "EREGL.IS": "Madencilik & Metal", "KRDMD.IS": "Madencilik & Metal", "KCAER.IS": "Madencilik & Metal", "BRSAN.IS": "Madencilik & Metal", "BUCIM.IS": "Madencilik & Metal", "CIMSA.IS": "Madencilik & Metal",
        "TUPRS.IS": "Enerji & Petrokimya", "PETKM.IS": "Enerji & Petrokimya", "ASTOR.IS": "Enerji & Petrokimya", "ENERY.IS": "Enerji & Petrokimya", "ZOREN.IS": "Enerji & Petrokimya", "AKSEN.IS": "Enerji & Petrokimya", "GWIND.IS": "Enerji & Petrokimya", "AYDEM.IS": "Enerji & Petrokimya", "EUPWR.IS": "Enerji & Petrokimya", "GESAN.IS": "Enerji & Petrokimya", "KONTR.IS": "Enerji & Petrokimya", "SMRTG.IS": "Enerji & Petrokimya", "YEOTK.IS": "Enerji & Petrokimya", "IZENR.IS": "Enerji & Petrokimya",
        "BIMAS.IS": "Perakende & Gıda", "MGROS.IS": "Perakende & Gıda", "SOKM.IS": "Perakende & Gıda", "ULKER.IS": "Perakende & Gıda", "CCOLA.IS": "Perakende & Gıda", "TUKAS.IS": "Perakende & Gıda", "MAVI.IS": "Perakende & Gıda", "TABGD.IS": "Perakende & Gıda", "YYLGD.IS": "Perakende & Gıda",
        "ASELS.IS": "Teknoloji & Savunma", "MIATK.IS": "Teknoloji & Savunma", "PENTA.IS": "Teknoloji & Savunma",
        "KCHOL.IS": "Holding", "SAHOL.IS": "Holding", "ALARK.IS": "Holding", "AGHOL.IS": "Holding", "DOHOL.IS": "Holding", "BERA.IS": "Holding", "GLYHO.IS": "Holding",
        "FROTO.IS": "Otomotiv", "TOASO.IS": "Otomotiv", "OTKAR.IS": "Otomotiv", "ASUZU.IS": "Otomotiv", "KARSN.IS": "Otomotiv",
        "VESTL.IS": "Dayanıklı Tüketim", "ARCLK.IS": "Dayanıklı Tüketim", "VESBE.IS": "Dayanıklı Tüketim"
    }
    sektor_verisi = {}

    if portfoy_verisi:
        for hisse, veri in portfoy_verisi.items():
            if hisse in fiyatlar:
                adet, maliyet = veri["adet"], veri["ort_maliyet"]
                anlik, dunku = fiyatlar[hisse]["anlik_fiyat"], fiyatlar[hisse]["dunku_kapanis"]
                
                if hisse.endswith(".IS") or hisse.endswith(".TEFAS"): pb, kur = "₺", 1.0
                else: pb, kur = "$", usd_kur
                
                h_mal_tl, h_gun_tl = adet * maliyet * kur, adet * anlik * kur
                t_deger += h_gun_tl
                t_maliyet += h_mal_tl
                t_gunluk += adet * (anlik - dunku) * kur
                
                gorunen_isim = hisse.replace('.TEFAS', ' (Fon)')
                pasta_verisi.append({"İsim": gorunen_isim, "Değer": h_gun_tl})
                
                if hisse.endswith(".TEFAS"): sektor = "Yatırım Fonları (TEFAS)"
                elif not hisse.endswith(".IS"): sektor = "Yabancı Fon/Hisse"
                else: sektor = sektor_haritasi.get(hisse, "Diğer Sektörler")
                
                sektor_verisi[sektor] = sektor_verisi.get(sektor, 0) + h_gun_tl
                h_veriler.append({"Hisse": hisse, "Gorunen": gorunen_isim, "Adet": adet, "Maliyet": maliyet, "Anlik": anlik, "PB": pb, "Top_TL": h_gun_tl, "KZ_TL": h_gun_tl - h_mal_tl, "KZ_Y": ((h_gun_tl - h_mal_tl) / h_mal_tl) * 100 if h_mal_tl > 0 else 0, "Gun_TL": adet * (anlik - dunku) * kur})

    sektor_liste = [{"İsim": k, "Değer": v} for k, v in sektor_verisi.items()]

    bugun = date.today().isoformat()
    if portfoy_verisi:
        db.collection('portfoy_gecmisi').document(bugun).set({'tarih': bugun, 'toplam_deger': t_deger})
    
    docs_gecmis = db.collection('portfoy_gecmisi').order_by('tarih').stream()
    gecmis_data = [doc.to_dict() for doc in docs_gecmis]
    df_gecmis = pd.DataFrame(gecmis_data) if gecmis_data else pd.DataFrame(columns=['tarih', 'toplam_deger'])

    net_kz = t_deger - t_maliyet
    col1, col2, col3 = st.columns(3)
    col1.metric("Portföy Değeri", f"{t_deger:,.2f} ₺")
    col2.metric("Toplam Kar/Zarar (Aktif)", f"{net_kz:,.2f} ₺", f"%{(net_kz / t_maliyet) * 100 if t_maliyet > 0 else 0:.2f}")
    col3.metric("Günlük Değişim", f"{t_gunluk:,.2f} ₺", f"{t_gunluk:,.2f}")
    st.divider()

    st.subheader("Hisse Detayları")
    if not portfoy_verisi:
         st.info("Portföyünüz şu an boş. Sağ üstteki 'Manuel İşlem Ekle' butonunu kullanarak varlık ekleyebilirsiniz.")
    else:
        h_cols = st.columns([1.5, 1, 1.2, 1.2, 1.5, 1.7, 1.2, 1.5, 0.8])
        basliklar = ["Varlık", "Adet", "Ort. Maliyet", "Anlık", "Değer (TL)", "Kar/Zarar", "Getiri", "Günlük", "Ayar"]
        for i, c in enumerate(h_cols): c.markdown(f"**<span style='font-size:14px'>{basliklar[i]}</span>**", unsafe_allow_html=True)
        st.divider()

        def get_color(val): return "#00FF00" if val > 0 else "#FF4B4B" if val < 0 else "white"

        for s in h_veriler:
            r_cols = st.columns([1.5, 1, 1.2, 1.2, 1.5, 1.7, 1.2, 1.5, 0.8])
            if r_cols[0].button(f"{s['Gorunen']}", key=f"btn_portfoy_{s['Hisse']}", use_container_width=True): grafik_ve_getiri_modali(s['Hisse'])
            r_cols[1].write(f"{s['Adet']:.3f}")
            r_cols[2].write(f"{s['PB']}{s['Maliyet']:.4f}")
            
            if s['Anlik'] == 0.0:
                r_cols[3].write("Bekleniyor...")
            else:
                r_cols[3].write(f"{s['PB']}{s['Anlik']:.4f}")
                
            r_cols[4].write(f"{s['Top_TL']:,.2f} ₺")
            r_cols[5].markdown(f"<span style='color:{get_color(s['KZ_TL'])}; font-weight:bold;'>{s['KZ_TL']:,.2f} ₺</span>", unsafe_allow_html=True)
            r_cols[6].markdown(f"<span style='color:{get_color(s['KZ_Y'])}; font-weight:bold;'>%{s['KZ_Y']:.2f}</span>", unsafe_allow_html=True)
            r_cols[7].markdown(f"<span style='color:{get_color(s['Gun_TL'])}; font-weight:bold;'>{s['Gun_TL']:,.2f} ₺</span>", unsafe_allow_html=True)
            with r_cols[8].popover("⋮"):
                if st.button("✏️ Düzenle", key=f"ed_{s['Hisse']}", use_container_width=True): duzenle_modal(s['Hisse'], s['Adet'], s['Maliyet'])
                if st.button("🗑️ Sil", key=f"dl_{s['Hisse']}", use_container_width=True): sil_modal(s['Hisse'])

    st.divider()
    c_pasta, c_grafik = st.columns(2)
    with c_pasta:
        pasta_tipi = st.radio("Pasta Grafik Modu", ["Hisse Dağılımı", "Sektörel Dağılım"], horizontal=True, label_visibility="collapsed")
        aktif_pasta_verisi = pasta_verisi if pasta_tipi == "Hisse Dağılımı" else sektor_liste
        st.subheader(f"📊 {pasta_tipi}")
        
        if aktif_pasta_verisi:
            fig1 = px.pie(pd.DataFrame(aktif_pasta_verisi), values='Değer', names='İsim', hole=0.4)
            fig1.update_layout(margin=dict(t=0, b=0, l=0, r=0), showlegend=False)
            fig1.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig1, use_container_width=True)
        else:
            st.caption("Grafiğin oluşması için portföyünüze varlık ekleyin.")
            
    with c_grafik:
        st.subheader("Portföy Büyüme Trendi")
        if len(df_gecmis) > 1:
            fig2 = px.area(df_gecmis, x='tarih', y='toplam_deger')
            fig2.update_layout(xaxis_title="", yaxis_title="₺", margin=dict(t=10, b=0, l=0, r=0))
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Büyüme trend grafiğinin oluşması için uygulamanın en az 2 gün kayıt alması gerekmektedir.")

    st.divider()
    c_gecmis_baslik, c_gecmis_bosluk, c_gecmis_btn = st.columns([3, 2, 1])
    with c_gecmis_baslik:
        st.subheader("📜 Geçmiş İşlem Kayıtları")
    with c_gecmis_btn:
        if st.button("🧹 Geçmişi Temizle", type="primary", use_container_width=True):
            gecmisi_temizle_modal()
            
    islem_gecmisi = get_islem_gecmisi()
    
    if islem_gecmisi:
        with st.container(height=350):
            g_cols = st.columns([2, 2, 1.5, 1.5, 1.5, 2, 2, 0.8])
            basliklar_gecmis = ["Tarih", "Varlık", "İşlem", "Fiyat", "Adet", "Tutar", "Kar/Zarar", "Sil"]
            for i, c in enumerate(g_cols): 
                c.markdown(f"**<span style='font-size:14px; color:#A0A0A0;'>{basliklar_gecmis[i]}</span>**", unsafe_allow_html=True)
            st.markdown("<hr style='margin-top: 0px; margin-bottom: 10px;'>", unsafe_allow_html=True)

            for s in islem_gecmisi:
                r_cols = st.columns([2, 2, 1.5, 1.5, 1.5, 2, 2, 0.8])
                r_cols[0].write(s['Tarih'])
                r_cols[1].write(s['Varlık'])
                r_cols[2].markdown(s['İşlem'], unsafe_allow_html=True)
                r_cols[3].write(f"{s['Fiyat']:,.4f}")
                r_cols[4].write(f"{s['Adet']:.3f}")
                r_cols[5].write(f"{s['Toplam Tutar']:,.2f} ₺")
                
                if s['Kar/Zarar'] is not None:
                    renk = "#00FF00" if s['Kar/Zarar'] > 0 else "#FF4B4B" if s['Kar/Zarar'] < 0 else "white"
                    r_cols[6].markdown(f"<span style='color:{renk}; font-weight:bold;'>{s['Kar/Zarar']:,.2f} ₺</span>", unsafe_allow_html=True)
                else:
                    r_cols[6].write("-")
                    
                if r_cols[7].button("❌", key=f"del_islem_{s['ID']}", help="Bu satırı sil"):
                    islem_gecmisi_sil_modal(s['ID'])
    else:
        st.info("Henüz hiçbir işlem kaydınız bulunmuyor.")

# ==========================================
# SAYFA 2: İZLEME LİSTESİ
# ==========================================
elif st.session_state.aktif_sayfa == "İzleme Listesi":
    st.title("👁️ İzleme Listesi")
    
    with st.form("izleme_ekle_form"):
        c1, c2 = st.columns([4, 1])
        yeni_izleme = c1.selectbox("Hisse/Fon", options=tum_semboller, index=None, placeholder="Kodu yazıp seçin...", label_visibility="collapsed")
        if c2.form_submit_button("Listeye Ekle", type="primary") and yeni_izleme:
            db.collection('izleme_listesi').document(yeni_izleme.upper()).set({'hisse_kodu': yeni_izleme.upper()})
            st.success("Eklendi!")
            st.rerun()

    docs = db.collection('izleme_listesi').stream()
    izlenenler = [doc.to_dict().get('hisse_kodu') for doc in docs]

    if izlenenler:
        with st.spinner("Güncelleniyor..."):
            data_wl = yf.download(" ".join(izlenenler), period="1y", progress=False)
        
        st.divider()
        h_cols = st.columns([2, 1.5, 1.5, 1.5, 1.5, 1.5, 1])
        basliklar = ["Hisse", "Fiyat", "Günlük", "1 Hafta", "1 Ay", "6 Ay", "Sil"]
        for i, c in enumerate(h_cols): c.markdown(f"**{basliklar[i]}**", unsafe_allow_html=True)
        st.divider()

        def get_g(df_h, a, g): return ((a - float(df_h.iloc[-(g + 1)])) / float(df_h.iloc[-(g + 1)])) * 100 if len(df_h)>g and float(df_h.iloc[-(g+1)])>0 else None

        for hisse in izlenenler:
            try:
                df_h = data_wl['Close'][hisse].dropna() if len(izlenenler) > 1 else data_wl['Close'].dropna()
                if df_h.empty: continue
                anlik = float(df_h.iloc[-1])
                r_cols = st.columns([2, 1.5, 1.5, 1.5, 1.5, 1.5, 1])
                if r_cols[0].button(f"{hisse}", key=f"wl_{hisse}", use_container_width=True): grafik_ve_getiri_modali(hisse)
                r_cols[1].write(f"{anlik:.2f} {'₺' if hisse.endswith('.IS') else '$'}")
                
                for i, v in enumerate([get_g(df_h, anlik, 1), get_g(df_h, anlik, 5), get_g(df_h, anlik, 21), get_g(df_h, anlik, 126)]):
                    if v is None: r_cols[i+2].write("-")
                    else: r_cols[i+2].markdown(f"<span style='color:{'#00FF00' if v>0 else '#FF4B4B'}; font-weight:bold;'>%{v:.2f}</span>", unsafe_allow_html=True)
                
                if r_cols[6].button("🗑️", key=f"d_wl_{hisse}"):
                    db.collection('izleme_listesi').document(hisse).delete()
                    st.rerun()
            except: pass

# ==========================================
# SAYFA 3: TARAYICI
# ==========================================
elif st.session_state.aktif_sayfa == "Tarayıcı":
    st.title("🎯 BİST 100 Çoklu Vade Tarayıcı")
    
    col_scan, col_ayar, _ = st.columns([2, 1, 2])
    
    with col_ayar.popover("⚙️ Tarama Ayarları (Filtreler)", use_container_width=True):
        st.markdown("**1. Analiz Periyodu**")
        analiz_periyodu = st.selectbox("Periyot", [10, 20, 50, 100, 200], index=1, label_visibility="collapsed")
        st.divider()
        st.markdown("**2. Teknik Araçlar (10 Adet)**")
        c1, c2 = st.columns(2)
        araclar = {
            "RSI (14)": c1.checkbox("RSI", True),
            "SMA (Basit Ortalama)": c1.checkbox(f"SMA {analiz_periyodu}", True),
            "EMA (Üstel Ortalama)": c1.checkbox(f"EMA {analiz_periyodu}", True),
            "MACD": c1.checkbox("MACD", True),
            "Bollinger Bantları": c1.checkbox("Bollinger", True),
            "Stochastic": c2.checkbox("Stochastic", False),
            "Williams %R": c2.checkbox("Williams %R", False),
            "ROC": c2.checkbox("ROC", False),
            "Momentum": c2.checkbox("Momentum", False),
            "CCI (Emtia Kanal Endeksi)": c2.checkbox("CCI Endeksi", False)
        }
        aktif_araclar = [isim for isim, secili_mi in araclar.items() if secili_mi]

    if col_scan.button("🚀 Piyasayı Canlı Tara", type="primary", use_container_width=True):
        if len(aktif_araclar) == 0:
            st.error("Lütfen ayarlardan en az 1 tane teknik araç seçiniz!")
        else:
            with st.spinner("BİST 100 hisseleri hesaplanıyor, bu işlem 1-2 dakika sürebilir..."):
                tarama_sonuclari = coklu_zaman_dilimi_taramasi(analiz_periyodu, aktif_araclar)
                st.session_state['son_tarama'] = tarama_sonuclari

    if 'son_tarama' in st.session_state and st.session_state['son_tarama']:
        st.divider()
        st.success("Taramalar tamamlandı! Grafiğini ve verilerini açmak için hisse ismine tıklayın.")
        h_cols = st.columns([1.5, 1.5, 2, 2, 2, 2])
        basliklar = ["Hisse", "Fiyat", "Kısa Vade (<1 Ay)", "Orta Vade (1-6 Ay)", "Uzun Vade (6+ Ay)", "Skor (K | O | U)"]
        for i, c in enumerate(h_cols): c.markdown(f"**<span style='font-size:14px'>{basliklar[i]}</span>**", unsafe_allow_html=True)
        st.divider()
        for s in st.session_state['son_tarama']:
            r_cols = st.columns([1.5, 1.5, 2, 2, 2, 2])
            if r_cols[0].button(f"{s['Hisse']}", key=f"btn_scan_{s['Hisse']}", use_container_width=True): grafik_ve_getiri_modali(s['Hisse'])
            r_cols[1].write(f"{s['Fiyat']:.2f} ₺")
            r_cols[2].write(s['Kısa Vade (<1 Ay)'])
            r_cols[3].write(s['Orta Vade (1-6 Ay)'])
            r_cols[4].write(s['Uzun Vade (6+ Ay)'])
            r_cols[5].write(s['Skor (K | O | U)'])

# ==========================================
# SAYFA 4: YAPAY ZEKA SOHBET ASİSTANI
# ==========================================
elif st.session_state.aktif_sayfa == "AI_Sohbet":
    st.title("🤖 Gemini Yapay Zeka Finans Asistanı")
    st.markdown("Portföyün, borsa stratejileri veya genel piyasalar hakkında dilediğin soruyu sorabilirsin.")

    if "ai_mesajlar" not in st.session_state:
        st.session_state.ai_mesajlar = [{"role": "assistant", "content": "Merhaba! Ben senin yapay zeka yatırım asistanınım. Bugün sana nasıl yardımcı olabilirim?"}]

    for mesaj in st.session_state.ai_mesajlar:
        with st.chat_message(mesaj["role"]): st.markdown(mesaj["content"])

    if kullanici_girdisi := st.chat_input("Yapay zekaya bir şeyler yaz... (Örn: Hangi sektörlere yatırım yapmalıyım?)"):
        st.session_state.ai_mesajlar.append({"role": "user", "content": kullanici_girdisi})
        with st.chat_message("user"): st.markdown(kullanici_girdisi)

        with st.chat_message("assistant"):
            with st.spinner("Gemini düşünüyor..."):
                try:
                    genai.configure(api_key=GEMINI_API_KEY)
                    model = genai.GenerativeModel('gemini-3.5-flash')
                    sohbet_gecmisi = [{"role": m["role"] if m["role"] == "user" else "model", "parts": [m["content"]]} for m in st.session_state.ai_mesajlar]
                    chat = model.start_chat(history=sohbet_gecmisi[:-1])
                    yanit = chat.send_message(kullanici_girdisi)
                    st.markdown(yanit.text)
                    st.session_state.ai_mesajlar.append({"role": "assistant", "content": yanit.text})
                except Exception as e:
                    st.error(f"Bağlantı hatası: {e}")

# ==========================================
# SAYFA 5: FIRE (FİNANSAL ÖZGÜRLÜK SİMÜLATÖRÜ)
# ==========================================
elif st.session_state.aktif_sayfa == "FIRE":
    st.title("💸 Bileşik Getiri & Finansal Özgürlük")
    st.markdown("Zamanın ve bileşik getirinin gücünü kullanarak finansal hedeflerinize ne zaman ulaşacağınızı hesaplayın.")

    col_input, col_chart = st.columns([1, 2.5])
    with col_input:
        st.subheader("⚙️ Yatırım Planınız")
        baslangic = st.number_input("Başlangıç Sermayesi (₺)", min_value=0.0, value=10000.0, step=1000.0)
        aylik_yatirim = st.number_input("Aylık Düzenli Yatırım (₺)", min_value=0.0, value=2000.0, step=500.0)
        yillik_getiri = st.slider("Beklenen Yıllık Getiri (%)", min_value=1, max_value=150, value=40, help="Türkiye şartlarında nominal (enflasyon dahil) getiri beklentisi.")
        sure_yil = st.slider("Yatırım Süresi (Yıl)", min_value=1, max_value=40, value=15)
        st.divider()
        st.markdown("#### 🎯 %4 Çekme Kuralı (FIRE)")
        st.caption("Finansal Özgürlük (FIRE) literatüründeki Trinity Çalışması'na göre; ulaştığınız toplam portföyün her yıl maksimum **%4'ünü** bozarak yaşarsanız, paranızın teorik olarak hiçbir zaman bitmemesi gerekir. Bu hesaplama size gelecekteki tahmini aylık maaşınızı gösterir.")

    with col_chart:
        aylik_getiri_orani = (1 + yillik_getiri / 100) ** (1/12) - 1
        aylar = sure_yil * 12
        mevcut_bakiye = baslangic
        toplam_yatirilan = baslangic
        
        veri = []
        for ay in range(1, aylar + 1):
            mevcut_bakiye = (mevcut_bakiye + aylik_yatirim) * (1 + aylik_getiri_orani)
            toplam_yatirilan += aylik_yatirim
            if ay % 12 == 0: 
                yil = ay // 12
                bilesik_getiri = mevcut_bakiye - toplam_yatirilan
                veri.append({
                    "Yıl": f"{yil}. Yıl",
                    "Yatırılan Ana Para": toplam_yatirilan,
                    "Bileşik Getiri Kârı": bilesik_getiri,
                    "Toplam Portföy": mevcut_bakiye
                })
        
        df_fire = pd.DataFrame(veri)
        son_portfoy = df_fire['Toplam Portföy'].iloc[-1]
        toplam_ana_para = df_fire['Yatırılan Ana Para'].iloc[-1]
        toplam_kar = son_portfoy - toplam_ana_para
        aylik_pasif_gelir = (son_portfoy * 0.04) / 12
        
        c1, c2, c3 = st.columns(3)
        c1.metric(f"{sure_yil} Yıl Sonu Toplam Portföy", f"{son_portfoy:,.0f} ₺")
        c2.metric("Toplam Kâr (Bileşik Getiri)", f"{toplam_kar:,.0f} ₺")
        c3.metric("Tahmini Aylık Pasif Gelir", f"{aylik_pasif_gelir:,.0f} ₺")
        st.divider()
        fig = px.bar(df_fire, x="Yıl", y=["Yatırılan Ana Para", "Bileşik Getiri Kârı"], 
                     title="Yıllara Göre Portföy Büyüme Projeksiyonu",
                     labels={"value": "Tutar (₺)", "variable": "Bileşen"},
                     color_discrete_map={"Yatırılan Ana Para": "#1f77b4", "Bileşik Getiri Kârı": "#00FF00"})
        fig.update_layout(barmode='stack', hovermode="x unified", margin=dict(t=40, b=0, l=0, r=0), legend_title="")
        st.plotly_chart(fig, use_container_width=True)