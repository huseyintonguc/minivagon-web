import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from fpdf import FPDF
from PIL import Image
import os
import tempfile

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="MiniVagon Bulut", page_icon="☁️", layout="wide")

# --- SABİTLER ---
SHEET_ADI = "MiniVagonDB"
RESIM_KLASORU = "resimler"

# Ürün Listesi
URUNLER = {
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

# --- GOOGLE SHEETS BAĞLANTISI ---
def get_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open(SHEET_ADI)

# --- VERİ İŞLEMLERİ ---
def siparis_ekle(satir):
    sh = get_sheet()
    w = sh.worksheet("Siparisler")
    w.append_row(satir)

def cari_islem_ekle(satir):
    sh = get_sheet()
    w = sh.worksheet("Cariler")
    w.append_row(satir)

def verileri_getir(sayfa_adi):
    sh = get_sheet()
    w = sh.worksheet(sayfa_adi)
    return w.get_all_records()

# --- PDF OLUŞTURMA ---
def create_pdf(s):
    pdf = FPDF()
    pdf.add_page()
    # Font
    try: pdf.add_font('ArialTR', '', 'arial.ttf', uni=True); pdf.set_font('ArialTR', '', 12)
    except: pdf.set_font("Arial", size=12)

    # Başlık
    pdf.set_fill_color(40, 40, 40); pdf.rect(0, 0, 210, 30, 'F')
    pdf.set_text_color(255, 255, 255); pdf.set_font_size(20); pdf.text(10, 20, "MINIVAGON")
    pdf.set_font_size(10); pdf.set_text_color(200, 200, 200)
    pdf.text(150, 15, f"Siparis No: #{s.get('Siparis No')}")
    pdf.text(150, 22, f"Tarih: {s.get('Tarih')}")

    # Resim Ekleme (Geçici Dosya ile)
    def resim_koy(u_adi, x_pos):
        if u_adi in URUNLER and os.path.exists(os.path.join(RESIM_KLASORU, URUNLER[u_adi])):
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                    img = Image.open(os.path.join(RESIM_KLASORU, URUNLER[u_adi])).convert('RGB')
                    img.thumbnail((300, 220))
                    img.save(tmp.name)
                    pdf.image(tmp.name, x=x_pos, y=40, h=60)
            except: pass

    resim_koy(s.get('Ürün 1'), 65)
    if s.get('Ürün 2'):
        resim_koy(s.get('Ürün 1'), 15)
        resim_koy(s.get('Ürün 2'), 110)

    # İçerik
    pdf.set_y(110); pdf.set_text_color(0, 0, 0); pdf.set_font_size(12)
    def tr(t): return str(t).replace("ğ","g").replace("Ğ","G").replace("ş","s").replace("Ş","S").replace("İ","I").replace("ı","i").encode('latin-1','replace').decode('latin-1') if t else ""

    pdf.set_fill_color(240, 240, 240); pdf.cell(0, 10, "  URUN DETAYLARI", ln=1, fill=True); pdf.ln(2)
    
    ek1 = f" - Isim: {s.get('İsim 1')}" if s.get('İsim 1') else ""
    pdf.cell(0, 8, tr(f"1) {s.get('Ürün 1')} ({s.get('Adet 1')} Adet){ek1}"), ln=1)
    
    if s.get('Ürün 2'):
        ek2 = f" - Isim: {s.get('İsim 2')}" if s.get('İsim 2') else ""
        pdf.cell(0, 8, tr(f"2) {s.get('Ürün 2')} ({s.get('Adet 2')} Adet){ek2}"), ln=1)
    pdf.ln(5)

    if "KAPIDA" in str(s.get('Ödeme')):
        pdf.set_fill_color(255, 230, 100); pdf.rect(10, pdf.get_y(), 190, 25, 'F'); pdf.set_xy(12, pdf.get_y()+2)
        pdf.cell(0, 10, tr(f"ODEME: {s.get('Ödeme')}"), ln=1)
        pdf.set_text_color(200, 0, 0); pdf.set_font_size(16)
        pdf.cell(0, 10, tr(f"TAHSIL EDILECEK TUTAR: {s.get('Tutar')} TL"), ln=1)
        pdf.set_text_color(0, 0, 0); pdf.set_font_size(12); pdf.ln(5)
    else:
        pdf.cell(0, 10, tr(f"Odeme: {s.get('Ödeme')} | Tutar: {s.get('Tutar')} TL"), ln=1); pdf.ln(5)

    pdf.set_fill_color(240, 240, 240); pdf.cell(0, 10, "  MUSTERI BILGILERI", ln=1, fill=True); pdf.ln(2)
    pdf.cell(0, 8, tr(f"Musteri: {s.get('Müşteri')}"), ln=1)
    pdf.cell(0, 8, tr(f"Telefon: {s.get('Telefon')}"), ln=1)
    pdf.multi_cell(0, 8, tr(f"Adres: {s.get('Adres')}"))
    if s.get('Not'): pdf.multi_cell(0, 8, tr(f"NOT: {s.get('Not')}"))

    return pdf.output(dest='S').encode('latin-1')

# --- MENÜLER ---
menu = st.sidebar.radio("Menü", ["📦 Sipariş Girişi", "📋 Sipariş Listesi", "💰 Cari Hesaplar"])

# --- 1. SİPARİŞ GİRİŞİ ---
if menu == "📦 Sipariş Girişi":
    st.header("Yeni Sipariş Ekle (Tam Detaylı)")
    with st.form("siparis_ekle", clear_on_submit=True):
        c1, c2 = st.columns([1, 2])
        
        with c1:
            st.info("🛒 Ürün Bilgileri")
            u1 = st.selectbox("1. Ürün", list(URUNLER.keys()))
            if os.path.exists(os.path.join(RESIM_KLASORU, URUNLER[u1])):
                st.image(os.path.join(RESIM_KLASORU, URUNLER[u1]), width=200)
            a1 = st.number_input("Adet", 1, 100, 1)
            i1 = st.text_input("Özel İsim (1. Ürün)")
            
            st.markdown("---")
            ikinci_urun = st.checkbox("2. Ürün Ekle")
            u2, a2, i2 = "", "", ""
            if ikinci_urun:
                u2 = st.selectbox("2. Ürün", list(URUNLER.keys()), key="u2")
                a2 = st.number_input("2. Ürün Adet", 1, 100, 1, key="a2")
                i2 = st.text_input("Özel İsim (2. Ürün)", key="i2")

        with c2:
            st.info("💳 Müşteri ve Finans")
            k1, k2 = st.columns(2)
            tutar = k1.text_input("Tutar (TL)")
            odeme = k2.selectbox("Ödeme", ["KAPIDA NAKİT", "KAPIDA K.KARTI", "HAVALE/EFT", "WEB SİTESİ"])
            
            k3, k4 = st.columns(2)
            kaynak = k3.selectbox("Kaynak", ["Instagram", "Web Sitesi", "Trendyol", "Whatsapp"])
            durum = k4.selectbox("Durum", ["YENİ SİPARİŞ", "HAZIRLANIYOR", "KARGOLANDI", "TESLİM EDİLDİ"])
            
            st.markdown("---")
            ad = st.text_input("Ad Soyad")
            tel = st.text_input("Telefon")
            tc = st.text_input("TC Kimlik (Opsiyonel)")
            mail = st.text_input("E-Mail (Opsiyonel)")
            adres = st.text_area("Adres")
            notlar = st.text_input("Sipariş Notu")
            fatura = "KESİLDİ" if st.checkbox("Faturası Kesildi") else "KESİLMEDİ"

        if st.form_submit_button("KAYDET", type="primary"):
            try:
                # Sipariş No Üretme
                mevcut = verileri_getir("Siparisler")
                yeni_no = 1000
                if mevcut:
                    df_m = pd.DataFrame(mevcut)
                    if not df_m.empty and 'Siparis No' in df_m.columns:
                        try: yeni_no = int(pd.to_numeric(df_m['Siparis No'], errors='coerce').max()) + 1
                        except: pass
                
                tarih = datetime.now().strftime("%d.%m.%Y %H:%M")
                
                # Sütun Sırası: Siparis No, Tarih, Durum, Müşteri, Telefon, TC No, Mail, Ürün 1, Adet 1, İsim 1, Ürün 2, Adet 2, İsim 2, Tutar, Ödeme, Kaynak, Adres, Not, Fatura Durumu
                satir = [yeni_no, tarih, durum, ad, tel, tc, mail, u1, a1, i1, u2, a2, i2, tutar, odeme, kaynak, adres, notlar, fatura]
                
                siparis_ekle(satir)
                st.success(f"✅ Sipariş #{yeni_no} Buluta Kaydedildi!")
            except Exception as e:
                st.error(f"Hata: {e}")

# --- 2. SİPARİŞ LİSTESİ ---
elif menu == "📋 Sipariş Listesi":
    st.header("Sipariş Geçmişi")
    try:
        data = verileri_getir("Siparisler")
        if data:
            df = pd.DataFrame(data)
            
            # Tabloyu Göster
            col1, col2 = st.columns([3, 1])
            arama = col1.text_input("İsim veya Sipariş No Ara")
            if arama:
                df = df[df.astype(str).apply(lambda x: x.str.contains(arama, case=False)).any(axis=1)]
            
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # PDF
            st.divider()
            if 'Siparis No' in df.columns:
                secilen = st.selectbox("Fiş Yazdır:", df['Siparis No'].astype(str) + " - " + df['Müşteri'])
                if st.button("📄 FİŞ OLUŞTUR"):
                    s_no = int(secilen.split(" - ")[0])
                    sip = df[df['Siparis No'] == s_no].iloc[0].to_dict()
                    pdf_data = create_pdf(sip)
                    st.download_button("📥 İNDİR", pdf_data, f"Siparis_{s_no}.pdf", "application/pdf", type="primary")
    except Exception as e:
        st.error(f"Veri çekilemedi: {e}")

# --- 3. CARİ HESAPLAR ---
elif menu == "💰 Cari Hesaplar":
    st.header("Cari Takip (Sadeleştirilmiş)")
    try:
        data = verileri_getir("Cariler")
        
        c1, c2 = st.columns([1, 2])
        with c1:
            st.subheader("İşlem Ekle")
            with st.form("cari_ekle"):
                c_ad = st.text_input("Cari Adı (Firma/Şahıs)")
                c_tip = st.selectbox("İşlem", ["FATURA (Borç)", "ÖDEME (Alacak)"])
                c_desc = st.text_input("Açıklama / Fatura No")
                c_tutar = st.number_input("Tutar", min_value=0.0, format="%.2f")
                
                if st.form_submit_button("KAYDET"):
                    tarih = datetime.now().strftime("%d.%m.%Y")
                    # Sütunlar: cari_adi, tarih, islem_tipi, aciklama, tutar
                    cari_islem_ekle([c_ad, tarih, c_tip, c_desc, c_tutar])
                    st.success("Kaydedildi!")
                    st.rerun()
        
        with c2:
            if data:
                df = pd.DataFrame(data)
                cariler = df['cari_adi'].unique() if 'cari_adi' in df.columns else []
                secili = st.selectbox("Hesap Seçiniz:", cariler)
                
                if secili:
                    sub_df = df[df['cari_adi'] == secili]
                    st.table(sub_df)
                    
                    borc = sub_df[sub_df['islem_tipi'].astype(str).str.contains("FATURA")]['tutar'].sum()
                    alacak = sub_df[sub_df['islem_tipi'].astype(str).str.contains("ÖDEME")]['tutar'].sum()
                    bakiye = alacak - borc
                    
                    k1, k2, k3 = st.columns(3)
                    k1.metric("Toplam Borç", f"{borc:,.2f}")
                    k2.metric("Toplam Ödeme", f"{alacak:,.2f}")
                    k3.metric("BAKİYE", f"{bakiye:,.2f}", delta_color="normal")
    except Exception as e:
        st.error(f"Hata: {e}")
