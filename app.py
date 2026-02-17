import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, date
import pytz
from fpdf import FPDF
from PIL import Image
import os
import tempfile
import plotly.express as px

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="MiniVagon Bulut", page_icon="☁️", layout="wide")

# --- SABİTLER ---
SHEET_ADI = "MiniVagonDB"
RESIM_KLASORU = "resimler"

# --- ZAMAN AYARI ---
def simdi():
    tz = pytz.timezone('Europe/Istanbul')
    return datetime.now(tz)

# --- GOOGLE SHEETS BAĞLANTISI ---
@st.cache_resource
def get_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def get_sheet():
    client = get_client()
    return client.open(SHEET_ADI)

# --- AKILLI PARA VE SAYI ÇEVİRİCİ ---
def safe_float(val):
    """Her türlü para formatını (51.805,20 veya 1250.50) float sayıya çevirir."""
    try:
        if pd.isna(val) or str(val).strip() == "": return 0.0
        if isinstance(val, (int, float)): return float(val)
        
        s = str(val).replace("TL", "").replace("tl", "").replace("₺", "").replace(" ", "").strip()
        
        # Karmaşık format kontrolü (Binlik ayraçlı mı?)
        if "." in s and "," in s:
            if s.rfind(",") > s.rfind("."): # 1.250,50 (TR)
                s = s.replace(".", "").replace(",", ".")
            else: # 1,250.50 (EN)
                s = s.replace(",", "")
        elif "," in s: # Sadece virgül varsa (1250,50)
            s = s.replace(",", ".")
            
        return float(s)
    except:
        return 0.0

def safe_int(val):
    return int(safe_float(val))

def format_tl(val):
    """Sayıyı 1.250,50 TL formatına çevirir."""
    try:
        return "{:,.2f} TL".format(val).replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "0,00 TL"

# --- VERİ İŞLEMLERİ ---
@st.cache_data(ttl=5)
def verileri_getir(sayfa_adi):
    sh = get_sheet()
    try:
        w = sh.worksheet(sayfa_adi)
        return w.get_all_records()
    except:
        return []

def cache_temizle():
    st.cache_data.clear()

def siparis_ekle(satir):
    sh = get_sheet()
    try: w = sh.worksheet("Siparisler")
    except:
        w = sh.add_worksheet(title="Siparisler", rows=100, cols=20)
        w.append_row(["Siparis No","Tarih","Durum","Müşteri","Telefon","TC No","Mail","Ürün 1","Adet 1","İsim 1","Ürün 2","Adet 2","İsim 2","Tutar","Ödeme","Kaynak","Adres","Not","Fatura Durumu","Tedarik Durumu"])
    w.append_row(satir)
    cache_temizle()

def cari_islem_ekle(satir):
    sh = get_sheet()
    try: w = sh.worksheet("Cariler")
    except:
        w = sh.add_worksheet(title="Cariler", rows=100, cols=6)
        w.append_row(["Cari Adı", "Tarih", "Fatura No", "Not", "Tutar", "Tip"])
    w.append_row(satir)
    cache_temizle()

def alis_faturasi_ekle(satir):
    sh = get_sheet()
    try: w = sh.worksheet("Alislar")
    except:
        w = sh.add_worksheet(title="Alislar", rows=100, cols=9)
        w.append_row(["Tarih", "Bağlı Sipariş", "Cari Hesap", "Ürün", "Adet", "Birim Fiyat", "Toplam", "Durum", "Not"])
    w.append_row(satir)
    cache_temizle()

# --- TEDARİK VE CARİ ENTEGRASYONU ---
def tedarik_durumunu_guncelle_ve_cariye_isle(siparis_bilgileri, cari_hesap, maliyet_sozlugu):
    sh = get_sheet()
    ws_siparis = sh.worksheet("Siparisler")
    ws_cari = sh.worksheet("Cariler")
    tarih_str = simdi().strftime("%d.%m.%Y")
    
    try:
        headers = ws_siparis.row_values(1)
        sip_no_col = headers.index("Siparis No") + 1
        tedarik_col = headers.index("Tedarik Durumu") + 1

        toplam_net_maliyet = 0
        islenen_nolar = []

        for sip in siparis_bilgileri:
            sip_no = sip['Siparis No']
            u1, a1 = sip.get('Ürün 1', ''), safe_int(sip.get('Adet 1', 0))
            u2, a2 = sip.get('Ürün 2', ''), safe_int(sip.get('Adet 2', 0))
            
            toplam_net_maliyet += (maliyet_sozlugu.get(u1, 0) * a1) + (maliyet_sozlugu.get(u2, 0) * a2)
            islenen_nolar.append(str(sip_no))
            
            cell = ws_siparis.find(str(sip_no), in_column=sip_no_col)
            if cell: ws_siparis.update_cell(cell.row, tedarik_col, "TEDARİKÇİ KESTİ")

        # KDV Ekleme (%20)
        tutar_kdv_dahil = toplam_net_maliyet * 1.20
        aciklama = f"Sipariş Maliyetleri: {', '.join(islenen_nolar)}"
        
        ws_cari.append_row([cari_hesap, tarih_str, "OTO-ALIS", aciklama, tutar_kdv_dahil, "BORÇ"])
        cache_temizle()
        return "BAŞARILI"
    except Exception as e: return f"HATA: {e}"

# --- ÜRÜN VE MALİYET SÖZLÜĞÜ ---
def get_urun_resimleri():
    sabitler = {
        "6 LI KADEHLİK": "6likadehlik.jpg", "2 LI KALPLİ KADEHLİK": "2likalplikadehlik.jpg",
        "3 LÜ KADEHLİK": "3lukadehlik.jpg", "İKİLİ STAND": "ikilistand.jpg",
        "ÇİFTLİ FIÇI": "ciftlifici.jpg", "TEKLİ FIÇI": "teklifici.jpg",
        "TEKLİ STAND": "teklistand.jpg", "TEKLİ STAND RAFLI": "teklistandrafli.jpg",
        "Viski Çerezlik": "tekliviski.jpg", "SATRANÇ": "satranc.jpg",
        "ALTIGEN": "altigen.jpg", "MAÇA AS": "macaas.jpg",
        "KUPA AS": "kupaas.jpg", "KARO AS": "karoas.jpg",
        "SİNEK AS": "sinekas.jpg", "YANIK NARGİLE SEHPA": "yaniknargilesehpa.jpg",
        "AÇIK RENK NARGİLE SEHPA": "acikrenknargilesehpa.jpg", "SİYAH TEKLİ STAND": "syhteklistand.jpg"
    }
    db = verileri_getir("Urunler")
    for u in db:
        if isinstance(u, dict) and "Urun Adi" in u: sabitler[u["Urun Adi"]] = u["Resim Dosya Adi"]
    return sabitler

GUNCEL_URUNLER = get_urun_resimleri()

def get_maliyet_dict():
    db = verileri_getir("Maliyetler")
    m_dict = {}
    for m in db:
        u_id = m.get("Ürün Id") or m.get("Urun Id")
        cost = safe_float(m.get("MALİYET") or m.get("Maliyet"))
        if u_id: m_dict[u_id] = cost
    return m_dict

# --- PDF ---
def create_pdf(s, urun_dict):
    pdf = FPDF()
    pdf.add_page()
    try: pdf.add_font('ArialTR', '', 'arial.ttf', uni=True); pdf.set_font('ArialTR', '', 12)
    except: pdf.set_font("Arial", size=12)
    pdf.set_fill_color(40, 40, 40); pdf.rect(0, 0, 210, 30, 'F')
    pdf.set_text_color(255, 255, 255); pdf.set_font_size(20); pdf.text(10, 20, "MINIVAGON")
    pdf.set_font_size(10); pdf.set_text_color(200, 200, 200)
    pdf.text(150, 15, f"Siparis No: #{s.get('Siparis No')}"); pdf.text(150, 22, f"Tarih: {s.get('Tarih')}")
    def r_k(u, x):
        if u in urun_dict:
            full = os.path.join(RESIM_KLASORU, urun_dict[u])
            if os.path.exists(full):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                    i = Image.open(full).convert('RGB'); i.thumbnail((300, 220)); i.save(tmp.name)
                    pdf.image(tmp.name, x=x, y=40, h=60)
    if s.get('Ürün 2'): r_k(s.get('Ürün 1'), 15); r_k(s.get('Ürün 2'), 110)
    else: r_k(s.get('Ürün 1'), 65)
    pdf.set_y(110); pdf.set_text_color(0, 0, 0); pdf.set_font_size(12)
    def tr(t): return str(t).replace("ğ","g").replace("Ğ","G").replace("ş","s").replace("Ş","S").replace("İ","I").replace("ı","i").encode('latin-1','replace').decode('latin-1') if t else ""
    pdf.set_fill_color(240, 240, 240); pdf.cell(0, 10, "  URUN DETAYLARI", ln=1, fill=True); pdf.ln(2)
    pdf.cell(0, 8, tr(f"1) {s.get('Ürün 1')} ({s.get('Adet 1')} Adet)"), ln=1)
    if s.get('Ürün 2'): pdf.cell(0, 8, tr(f"2) {s.get('Ürün 2')} ({s.get('Adet 2')} Adet)"), ln=1)
    pdf.ln(5)
    tutar_str = format_tl(safe_float(s.get('Tutar')))
    pdf.cell(0, 10, tr(f"Odeme: {s.get('Ödeme')} | Tutar: {tutar_str}"), ln=1); pdf.ln(5)
    pdf.set_fill_color(240, 240, 240); pdf.cell(0, 10, "  MUSTERI BILGILERI", ln=1, fill=True); pdf.ln(2)
    pdf.cell(0, 8, tr(f"Musteri: {s.get('Müşteri')}"), ln=1); pdf.cell(0, 8, tr(f"Telefon: {s.get('Telefon')}"), ln=1)
    pdf.multi_cell(0, 8, tr(f"Adres: {s.get('Adres')}"))
    return pdf.output(dest='S').encode('latin-1')

# --- MENÜ ---
menu = st.sidebar.radio("Menü", ["📦 Sipariş Girişi", "📋 Sipariş Listesi", "🧾 Fatura Takibi", "🧾 Alış ve Tedarik", "📊 Raporlar", "💰 Cari Hesaplar", "📉 Maliyet Yönetimi", "➕ Ürün Yönetimi"])

# --------------------------------------------------------------------------------
# 1. SİPARİŞ GİRİŞİ
# --------------------------------------------------------------------------------
if menu == "📦 Sipariş Girişi":
    st.header("Yeni Sipariş Ekle")
    col1, col2 = st.columns([1, 2])
    with col1:
        u1 = st.selectbox("1. Ürün Seçimi", list(GUNCEL_URUNLER.keys()))
        if u1 in GUNCEL_URUNLER and os.path.exists(os.path.join(RESIM_KLASORU, GUNCEL_URUNLER[u1])):
            st.image(os.path.join(RESIM_KLASORU, GUNCEL_URUNLER[u1]), width=250)
        a1 = st.number_input("1. Ürün Adet", 1, 100, 1)
        i1 = st.text_input("1. Ürün Özel İsim")
        st.markdown("---")
        ikinci = st.checkbox("2. Ürün Ekle (+)")
        u2, a2, i2 = "", "", ""
        if ikinci:
            u2 = st.selectbox("2. Ürün Seçimi", list(GUNCEL_URUNLER.keys()), key="u2_sel")
            a2 = st.number_input("2. Ürün Adet", 1, 100, 1, key="a2_n")
            i2 = st.text_input("2. Ürün Özel İsim", key="i2_t")
    with col2:
        with st.form("siparis"):
            c1, c2 = st.columns(2)
            t_inp = c1.text_input("Sipariş Tutarı (Örn: 1.250,50)")
            # Önizleme
            if t_inp: c1.caption(f"Sistem: {format_tl(safe_float(t_inp))}")
            odeme = c2.selectbox("Ödeme", ["KAPIDA NAKİT", "KAPIDA K.KARTI", "HAVALE/EFT", "WEB SİTESİ"])
            durum = st.selectbox("Durum", ["YENİ SİPARİŞ", "KARGOLANDI", "TESLİM EDİLDİ"])
            ad = st.text_input("Ad Soyad")
            tel = st.text_input("Telefon")
            adres = st.text_area("Adres", height=100)
            fatura = "KESİLDİ" if st.checkbox("Faturası Kesildi") else "KESİLMEDİ"
            if st.form_submit_button("KAYDET", type="primary"):
                try:
                    mevcut = verileri_getir("Siparisler")
                    yeni_no = 1000
                    if mevcut:
                        df_m = pd.DataFrame(mevcut)
                        yeni_no = int(pd.to_numeric(df_m['Siparis No'], errors='coerce').max()) + 1
                    satir = [yeni_no, simdi().strftime("%d.%m.%Y %H:%M"), durum, ad, tel, "", "", u1, a1, i1, u2, a2, i2, safe_float(t_inp), odeme, "Whatsapp", adres, "", fatura, "BEKLİYOR"]
                    siparis_ekle(satir)
                    st.success(f"✅ Sipariş #{yeni_no} Kaydedildi!")
                except Exception as e: st.error(f"Hata: {e}")

# --------------------------------------------------------------------------------
# 2. SİPARİŞ LİSTESİ
# --------------------------------------------------------------------------------
elif menu == "📋 Sipariş Listesi":
    st.header("Sipariş Geçmişi")
    data = verileri_getir("Siparisler")
    if data:
        df = pd.DataFrame(data)
        if 'Siparis No' in df.columns:
            df['Siparis No'] = pd.to_numeric(df['Siparis No'], errors='coerce')
            df = df.sort_values(by="Siparis No", ascending=False)
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.divider()
        secilen = st.selectbox("Fiş Yazdır:", df.apply(lambda x: f"{int(x['Siparis No'])} - {x['Müşteri']}", axis=1))
        if st.button("📄 FİŞ OLUŞTUR"):
            s_no = int(secilen.split(" - ")[0])
            sip = df[df['Siparis No'] == s_no].iloc[0].to_dict()
            pdf_data = create_pdf(sip, GUNCEL_URUNLER)
            st.download_button("📥 İNDİR", pdf_data, f"Siparis_{s_no}.pdf", "application/pdf")

# --------------------------------------------------------------------------------
# 4. ALIŞ VE TEDARİK
# --------------------------------------------------------------------------------
elif menu == "🧾 Alış ve Tedarik":
    st.header("Tedarikçi Alış Yönetimi")
    cariler_data = verileri_getir("Cariler")
    cari_listesi = []
    if cariler_data:
        df_cariler = pd.DataFrame(cariler_data)
        if "Cari Adı" in df_cariler.columns: cari_listesi = df_cariler["Cari Adı"].unique().tolist()
    
    m_dict = get_maliyet_dict()
    s_data = verileri_getir("Siparisler")
    
    if s_data:
        df_s = pd.DataFrame(s_data)
        bekleyenler = df_s[df_s["Tedarik Durumu"] != "TEDARİKÇİ KESTİ"].copy()
        
        if not bekleyenler.empty:
            st.subheader("Tedarikçisi Fatura Kesmeyen Siparişler")
            secilen_cari = st.selectbox("Tedarikçi (Cari):", cari_listesi)
            st.dataframe(bekleyenler[["Siparis No", "Müşteri", "Ürün 1", "Adet 1", "Ürün 2", "Adet 2"]], use_container_width=True)
            
            secenekler = bekleyenler.apply(lambda x: f"{x['Siparis No']} - {x['Müşteri']} ({x['Ürün 1']})", axis=1).tolist()
            secilen_siparisler = st.multiselect("Faturası Gelenleri Seç:", secenekler)
            
            if st.button("SEÇİLENLERİ ONAYLA & CARİYE İŞLE"):
                if secilen_siparisler and secilen_cari:
                    sec_nolar = [int(s.split(" - ")[0]) for s in secilen_siparisler]
                    islenecek = bekleyenler[bekleyenler['Siparis No'].isin(sec_nolar)].to_dict('records')
                    res = tedarik_durumunu_guncelle_ve_cariye_isle(islenecek, secilen_cari, m_dict)
                    if res == "BAŞARILI": st.success("✅ Cari hesaba %20 KDV dahil işlendi!"); st.rerun()
                    else: st.error(res)
        else: st.success("Tüm tedarikler tamam!")

# --------------------------------------------------------------------------------
# 6. CARİ HESAPLAR
# --------------------------------------------------------------------------------
elif menu == "💰 Cari Hesaplar":
    st.header("Cari Takip")
    with st.expander("➕ Yeni Fatura / Ödeme İşle", expanded=True):
        with st.form("cari"):
            c1, c2 = st.columns(2)
            m_data = verileri_getir("Cariler")
            c_list = list(set([r['Cari Adı'] for r in m_data])) if m_data else []
            cari_secim = c1.selectbox("Cari Hesap:", ["Yeni Ekle..."] + c_list)
            if cari_secim == "Yeni Ekle...": ad = c1.text_input("Cari Adı:")
            else: ad = cari_secim
            
            f_no = c2.text_input("Fatura No")
            not_ac = st.text_input("Not")
            t_inp = st.text_input("Tutar (KDV DAHİL - Örn: 51.805,20)")
            if t_inp: st.caption(f"Sistem Algıladı: {format_tl(safe_float(t_inp))}")
            tip = st.radio("İşlem Türü:", ["Fatura Girişi (BORÇ)", "Ödeme Yapıldı (ALACAK)"])
            
            if st.form_submit_button("KAYDET"):
                if ad:
                    t_val = safe_float(t_inp)
                    cari_islem_ekle([ad, simdi().strftime("%d.%m.%Y"), f_no, not_ac, t_val, "BORÇ" if "BORÇ" in tip else "ALACAK"])
                    st.success(f"✅ Kaydedildi! {format_tl(t_val)}")
                    st.rerun()

    if m_data:
        df = pd.DataFrame(m_data)
        secili_c = st.selectbox("Hesap Seç:", df['Cari Adı'].unique())
        if secili_c:
            sub = df[df['Cari Adı'] == secili_c].copy()
            # Rakamları sayıya çevirerek bakiye hesapla
            sub['T_Float'] = sub['Tutar'].apply(safe_float)
            st.table(sub[["Tarih", "Fatura No", "Not", "Tutar", "Tip"]])
            
            borc = sub[sub['Tip'] == "BORÇ"]['T_Float'].sum()
            alacak = sub[sub['Tip'] == "ALACAK"]['T_Float'].sum()
            st.metric("GÜNCEL BAKİYE", format_tl(alacak - borc))

# --- DİĞER MENÜLER (Fatura Takibi, Raporlar, Maliyet, Ürün) Önceki Sürümlerdeki gibi devam eder ---
elif menu == "🧾 Fatura Takibi":
    st.header("Müşteri Fatura Yönetimi")
    data = verileri_getir("Siparisler")
    if data:
        df = pd.DataFrame(data)
        bekleyen = df[df["Fatura Durumu"] != "KESİLDİ"]
        st.metric("Bekleyen Fatura Tutarı", format_tl(bekleyen['Tutar'].apply(safe_float).sum()))
        st.dataframe(bekleyen[["Siparis No", "Müşteri", "Tutar", "Fatura Durumu"]])
        sel = st.multiselect("Kesildi Olarak İşaretle:", bekleyen.apply(lambda x: f"{x['Siparis No']} - {x['Müşteri']}", axis=1))
        if st.button("ONAYLA"):
            res = fatura_durumunu_kesildi_yap([int(s.split(" - ")[0]) for s in sel])
            if res == "BAŞARILI": st.success("Tamamlandı!"); st.rerun()

elif menu == "📊 Raporlar":
    st.header("Genel Satış Raporları")
    data = verileri_getir("Siparisler")
    if data:
        df = pd.DataFrame(data)
        df['T_Float'] = df['Tutar'].apply(safe_float)
        st.metric("Toplam Ciro", format_tl(df['T_Float'].sum()))
        st.plotly_chart(px.bar(df, x='Müşteri', y='T_Float', title="Müşteri Bazlı Ciro"))

elif menu == "📉 Maliyet Yönetimi":
    st.header("Ürün Maliyetleri")
    data = verileri_getir("Maliyetler")
    if data:
        st.dataframe(pd.DataFrame(data), use_container_width=True)

elif menu == "➕ Ürün Yönetimi":
    st.header("Ürün Tanımlama")
    with st.form("y_u"):
        ad = st.text_input("Ürün Adı")
        res = st.file_uploader("Resim", type=['jpg','png','jpeg'])
        if st.form_submit_button("EKLE"):
            if ad and res:
                dosya = f"{ad.replace(' ','_')}.jpg"
                Image.open(res).convert('RGB').save(os.path.join(RESIM_KLASORU, dosya))
                yeni_urun_resim_ekle(ad, dosya)
                st.success("Başarıyla Eklendi!")
