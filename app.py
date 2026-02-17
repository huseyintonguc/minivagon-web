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
SHEET_ADI = "MiniVagonDB"  # Google Drive'daki dosyanızın adı
RESIM_KLASORU = "resimler" # GitHub'a resimleri de yüklemeyi unutmayın!

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
    # Streamlit Secrets'tan anahtarı alacağız
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"]) # Secrets'taki başlık bu olmalı
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

# --- PDF OLUŞTURMA (Bulut Uyumlu) ---
def create_pdf(s):
    pdf = FPDF()
    pdf.add_page()
    
    # Font (Bulutta Windows fontu yok, Arial'i simüle ediyoruz)
    pdf.set_font("Arial", size=12)

    # Başlık
    pdf.set_fill_color(40, 40, 40)
    pdf.rect(0, 0, 210, 30, 'F')
    pdf.set_text_color(255, 255, 255)
    pdf.set_font_size(20)
    pdf.text(10, 20, "MINIVAGON")
    
    pdf.set_font_size(10)
    pdf.set_text_color(200, 200, 200)
    pdf.text(150, 15, f"Siparis No: #{s.get('siparis_no')}")
    pdf.text(150, 22, f"Tarih: {s.get('tarih')}")

    # Resim Ekleme (Varsa)
    if os.path.exists(RESIM_KLASORU):
        urun_adi = s.get('urun')
        if urun_adi in URUNLER:
            resim_yolu = os.path.join(RESIM_KLASORU, URUNLER[urun_adi])
            if os.path.exists(resim_yolu):
                try:
                    # Geçici dosya oluştur (Cloud hatasını önlemek için)
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                        img = Image.open(resim_yolu).convert('RGB')
                        img.thumbnail((300, 220))
                        img.save(tmp.name)
                        pdf.image(tmp.name, x=65, y=40, h=60)
                except: pass

    # İçerik
    pdf.set_y(110)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font_size(12)
    
    # Türkçe karakter düzeltmesi (Basit yöntem)
    def tr(txt):
        if not txt: return ""
        return str(txt).replace("ğ","g").replace("Ğ","G").replace("ş","s").replace("Ş","S").replace("İ","I").replace("ı","i").encode('latin-1', 'replace').decode('latin-1')

    pdf.set_fill_color(240, 240, 240)
    pdf.cell(0, 10, "  URUN DETAYLARI", ln=1, fill=True)
    pdf.ln(2)
    pdf.cell(0, 8, tr(f"URUN: {s.get('urun')} ({s.get('adet')} Adet)"), ln=1)
    
    if "KAPIDA" in str(s.get('odeme_tipi')):
        pdf.set_fill_color(255, 230, 100)
        pdf.rect(10, pdf.get_y(), 190, 25, 'F')
        pdf.set_xy(12, pdf.get_y()+2)
        pdf.cell(0, 10, tr(f"ODEME: {s.get('odeme_tipi')}"), ln=1)
        pdf.set_text_color(200, 0, 0); pdf.set_font_size(16)
        pdf.cell(0, 10, tr(f"TUTAR: {s.get('tutar')} TL"), ln=1)
        pdf.set_text_color(0, 0, 0); pdf.set_font_size(12)
        pdf.ln(5)
    else:
        pdf.cell(0, 10, tr(f"Odeme: {s.get('odeme_tipi')} | Tutar: {s.get('tutar')} TL"), ln=1)
        pdf.ln(5)

    pdf.set_fill_color(240, 240, 240)
    pdf.cell(0, 10, "  MUSTERI BILGILERI", ln=1, fill=True)
    pdf.ln(2)
    pdf.cell(0, 8, tr(f"Ad Soyad: {s.get('ad_soyad')}"), ln=1)
    pdf.cell(0, 8, tr(f"Telefon: {s.get('telefon')}"), ln=1)
    pdf.multi_cell(0, 8, tr(f"Adres: {s.get('adres')}"))
    if s.get('not'): pdf.multi_cell(0, 8, tr(f"NOT: {s.get('not')}"))

    return pdf.output(dest='S').encode('latin-1')

# --- MENÜLER ---
menu = st.sidebar.radio("Menü", ["📦 Sipariş Girişi", "📋 Sipariş Listesi", "💰 Cari Hesaplar"])

if menu == "📦 Sipariş Girişi":
    st.header("Yeni Sipariş Ekle")
    with st.form("siparis_form", clear_on_submit=True):
        col1, col2 = st.columns([1, 2])
        with col1:
            urun = st.selectbox("Ürün", list(URUNLER.keys()))
            
            # Resim Gösterme (Varsa)
            img_path = os.path.join(RESIM_KLASORU, URUNLER[urun])
            if os.path.exists(img_path):
                st.image(img_path, width=200)
            
            adet = st.number_input("Adet", 1, 100, 1)
        
        with col2:
            tutar = st.text_input("Tutar (TL)")
            odeme = st.selectbox("Ödeme", ["KAPIDA NAKİT", "KAPIDA K.KARTI", "HAVALE", "WEB SİTESİ"])
            durum = st.selectbox("Durum", ["YENİ SİPARİŞ", "KARGOLANDI", "TESLİM EDİLDİ"])
            st.divider()
            ad = st.text_input("Müşteri Adı")
            tel = st.text_input("Telefon")
            adres = st.text_area("Adres")
            notlar = st.text_input("Not")

        if st.form_submit_button("KAYDET", type="primary"):
            try:
                # Yeni numara üretme (Listeden en büyüğü bulup +1 ekler)
                mevcut = verileri_getir("Siparisler")
                yeni_no = 1000
                if mevcut:
                    df_temp = pd.DataFrame(mevcut)
                    if not df_temp.empty and 'siparis_no' in df_temp.columns:
                        # Sayısal olmayanları temizle ve en büyüğü bul
                        nums = pd.to_numeric(df_temp['siparis_no'], errors='coerce').fillna(1000)
                        yeni_no = int(nums.max()) + 1
                
                tarih = datetime.now().strftime("%d.%m.%Y %H:%M")
                # Sıra: siparis_no, tarih, durum, ad_soyad, telefon, urun, adet, tutar, odeme_tipi, adres, not
                satir = [yeni_no, tarih, durum, ad, tel, urun, adet, tutar, odeme, adres, notlar]
                
                siparis_ekle(satir)
                st.success(f"✅ Sipariş #{yeni_no} başarıyla buluta kaydedildi!")
            except Exception as e:
                st.error(f"Hata: {e}")

elif menu == "📋 Sipariş Listesi":
    st.header("Siparişler")
    try:
        data = verileri_getir("Siparisler")
        if data:
            df = pd.DataFrame(data)
            # Tabloyu Göster
            st.dataframe(df, use_container_width=True)
            
            st.divider()
            # PDF Alanı
            st.subheader("Fiş Yazdır")
            if 'siparis_no' in df.columns:
                secim = st.selectbox("Sipariş Seç:", df['siparis_no'].astype(str) + " - " + df['ad_soyad'])
                if st.button("PDF İNDİR"):
                    s_no = int(secim.split(" - ")[0])
                    # Seçilen satırı bul
                    s_row = df[df['siparis_no'] == s_no].iloc[0].to_dict()
                    pdf_byte = create_pdf(s_row)
                    st.download_button("📥 İNDİR", pdf_byte, f"Siparis_{s_no}.pdf", "application/pdf", type="primary")
        else:
            st.info("Kayıt yok.")
    except Exception as e:
        st.error(f"Veri çekilemedi. Google Sheets ayarlarını kontrol edin. Hata: {e}")

elif menu == "💰 Cari Hesaplar":
    st.header("Cari Takip")
    try:
        data = verileri_getir("Cariler")
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.subheader("İşlem Ekle")
            with st.form("cari_form", clear_on_submit=True):
                c_ad = st.text_input("Cari Adı (Müşteri/Tedarikçi)")
                c_tip = st.selectbox("İşlem", ["FATURA (Borç)", "ÖDEME (Alacak)"])
                c_desc = st.text_input("Açıklama / Fat No")
                c_tutar = st.number_input("Tutar", min_value=0.0, format="%.2f")
                
                if st.form_submit_button("KAYDET"):
                    tarih = datetime.now().strftime("%d.%m.%Y")
                    # Sıra: cari_adi, tarih, islem_tipi, aciklama, tutar
                    cari_islem_ekle([c_ad, tarih, c_tip, c_desc, c_tutar])
                    st.success("Kaydedildi!")
                    st.rerun()
        
        with col2:
            st.subheader("Hesap Özeti")
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
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Toplam Borç", f"{borc:,.2f}")
                    c2.metric("Toplam Ödeme", f"{alacak:,.2f}")
                    c3.metric("BAKİYE", f"{bakiye:,.2f}", delta_color="normal")
            else:
                st.info("Kayıt yok.")

    except Exception as e:
        st.error(f"Hata: {e}")
