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

# --- GÜVENLİ SAYI DÖNÜŞTÜRME ---
def safe_int(val):
    try:
        if pd.isna(val) or str(val).strip() == "": return 0
        return int(float(str(val).replace(",", ".")))
    except: return 0

def safe_float(val):
    try:
        if pd.isna(val) or str(val).strip() == "": return 0.0
        return float(str(val).replace("TL","").replace(".","").replace(",", "."))
    except: return 0.0

# --- VERİ İŞLEMLERİ ---
def verileri_getir(sayfa_adi):
    sh = get_sheet()
    try:
        w = sh.worksheet(sayfa_adi)
        return w.get_all_records()
    except gspread.exceptions.WorksheetNotFound:
        # Eğer sayfa yoksa boş liste dön, hata verme
        return []
    except Exception as e:
        return []

def siparis_ekle(satir):
    sh = get_sheet()
    try: w = sh.worksheet("Siparisler")
    except:
        w = sh.add_worksheet(title="Siparisler", rows=100, cols=20)
        # Başlıkları yaz (İlk oluşum)
        w.append_row(["Siparis No","Tarih","Durum","Müşteri","Telefon","TC No","Mail","Ürün 1","Adet 1","İsim 1","Ürün 2","Adet 2","İsim 2","Tutar","Ödeme","Kaynak","Adres","Not","Fatura Durumu"])
    w.append_row(satir)

def cari_islem_ekle(satir):
    sh = get_sheet()
    try: 
        w = sh.worksheet("Cariler")
    except:
        # Sayfa yoksa otomatik oluştur
        w = sh.add_worksheet(title="Cariler", rows=100, cols=5)
        w.append_row(["Cari Adı", "Tarih", "İşlem Tipi", "Açıklama", "Tutar"])
    w.append_row(satir)

def alis_faturasi_ekle(satir):
    sh = get_sheet()
    try: w = sh.worksheet("Alislar")
    except:
        w = sh.add_worksheet(title="Alislar", rows=100, cols=9)
        w.append_row(["Tarih", "Bağlı Sipariş", "Cari Hesap", "Ürün", "Adet", "Birim Fiyat", "Toplam", "Durum", "Not"])
    w.append_row(satir)

def yeni_urun_resim_ekle(ad, resim_adi):
    sh = get_sheet()
    try: w = sh.worksheet("Urunler")
    except: 
        w = sh.add_worksheet(title="Urunler", rows=100, cols=2)
        w.append_row(["Urun Adi", "Resim Dosya Adi"])
    w.append_row([ad, resim_adi])

# --- ÖZEL FONKSİYONLAR ---
def fatura_durumunu_kesildi_yap(siparis_nolar):
    sh = get_sheet()
    w = sh.worksheet("Siparisler")
    try:
        headers = w.row_values(1)
        sip_no_col = headers.index("Siparis No") + 1
        fatura_col = headers.index("Fatura Durumu") + 1
        for sip_no in siparis_nolar:
            cell = w.find(str(sip_no), in_column=sip_no_col)
            if cell: w.update_cell(cell.row, fatura_col, "KESİLDİ")
        return "BAŞARILI"
    except Exception as e: return f"HATA: {e}"

def alis_faturasi_onayla(alis_indexler):
    sh = get_sheet()
    try: ws_alis = sh.worksheet("Alislar")
    except: return "Alislar sayfası yok"
    
    try: ws_cari = sh.worksheet("Cariler")
    except: 
        # Cariler yoksa oluştur
        ws_cari = sh.add_worksheet(title="Cariler", rows=100, cols=5)
        ws_cari.append_row(["Cari Adı", "Tarih", "İşlem Tipi", "Açıklama", "Tutar"])
    
    tarih_str = simdi().strftime("%d.%m.%Y")
    
    try:
        headers = ws_alis.row_values(1)
        durum_col = headers.index("Durum") + 1
        
        for row_num, cari_hesap, tutar, aciklama in alis_indexler:
            ws_alis.update_cell(row_num + 2, durum_col, "FATURALAŞTI")
            cari_satir = [cari_hesap, tarih_str, "FATURA (Borç)", aciklama, tutar]
            ws_cari.append_row(cari_satir)
        return "BAŞARILI"
    except Exception as e: return f"HATA: {e}"

def maliyet_kaydet(veriler):
    sh = get_sheet()
    try: w = sh.worksheet("Maliyetler")
    except: return "Maliyetler sayfası bulunamadı."
    tum = w.get_all_records()
    df = pd.DataFrame(tum)
    yeni = [veriler.get("Görsel",""), veriler.get("Ürün Kod",""), veriler.get("Ürün Id",""), veriler.get("Tahta",0), veriler.get("VERNİK",0), veriler.get("YAKMA",0), veriler.get("BOYA",0), veriler.get("MUSLUK",0), veriler.get("BORU",0), veriler.get("HALAT",0), veriler.get("Metal çubuk",0), veriler.get("CAM",0), veriler.get("UĞUR KAR",0), veriler.get("MALİYET",0)]
    try:
        col = "Ürün Id"
        if col not in df.columns: 
            if "Urun Id" in df.columns: col="Urun Id"
            elif "Ürün ID" in df.columns: col="Ürün ID"
            else: return "HATA: Sütun yok"
        idx = df.index[df[col].astype(str) == str(veriler["Ürün Id"])].tolist()
        if idx:
            r = idx[0] + 2
            w.update(f"A{r}:N{r}", [yeni])
            return "GÜNCELLENDİ"
        w.append_row(yeni)
        return "EKLENDİ"
    except Exception as e: return f"HATA: {e}"

# --- ÜRÜNLERİ GETİR ---
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
    db_urunler = verileri_getir("Urunler")
    for u in db_urunler:
        if isinstance(u, dict) and "Urun Adi" in u and "Resim Dosya Adi" in u:
            sabitler[u["Urun Adi"]] = u["Resim Dosya Adi"]
    return sabitler

GUNCEL_URUNLER = get_urun_resimleri()

# --- PDF OLUŞTURMA ---
def create_pdf(s, urun_dict):
    pdf = FPDF()
    pdf.add_page()
    try: pdf.add_font('ArialTR', '', 'arial.ttf', uni=True); pdf.set_font('ArialTR', '', 12)
    except: pdf.set_font("Arial", size=12)
    pdf.set_fill_color(40, 40, 40); pdf.rect(0, 0, 210, 30, 'F')
    pdf.set_text_color(255, 255, 255); pdf.set_font_size(20); pdf.text(10, 20, "MINIVAGON")
    pdf.set_font_size(10); pdf.set_text_color(200, 200, 200)
    pdf.text(150, 15, f"Siparis No: #{s.get('Siparis No')}")
    pdf.text(150, 22, f"Tarih: {s.get('Tarih')}")
    def resim_koy(u_adi, x_pos):
        if u_adi in urun_dict:
            dosya_adi = urun_dict[u_adi]
            full_path = os.path.join(RESIM_KLASORU, dosya_adi)
            if os.path.exists(full_path):
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                        img = Image.open(full_path).convert('RGB'); img.thumbnail((300, 220)); img.save(tmp.name)
                        pdf.image(tmp.name, x=x_pos, y=40, h=60)
                except: pass
    if s.get('Ürün 2'): resim_koy(s.get('Ürün 1'), 15); resim_koy(s.get('Ürün 2'), 110)
    else: resim_koy(s.get('Ürün 1'), 65)
    pdf.set_y(110); pdf.set_text_color(0, 0, 0); pdf.set_font_size(12)
    def tr(t): return str(t).replace("ğ","g").replace("Ğ","G").replace("ş","s").replace("Ş","S").replace("İ","I").replace("ı","i").encode('latin-1','replace').decode('latin-1') if t else ""
    pdf.set_fill_color(240, 240, 240); pdf.cell(0, 10, "  URUN DETAYLARI", ln=1, fill=True); pdf.ln(2)
    ek1 = f" - Isim: {s.get('İsim 1')}" if s.get('İsim 1') else ""
    pdf.cell(0, 8, tr(f"1) {s.get('Ürün 1')} ({s.get('Adet 1')} Adet){ek1}"), ln=1)
    if s.get('Ürün 2'): ek2 = f" - Isim: {s.get('İsim 2')}" if s.get('İsim 2') else ""; pdf.cell(0, 8, tr(f"2) {s.get('Ürün 2')} ({s.get('Adet 2')} Adet){ek2}"), ln=1)
    pdf.ln(5)
    if "KAPIDA" in str(s.get('Ödeme')):
        pdf.set_fill_color(255, 230, 100); pdf.rect(10, pdf.get_y(), 190, 25, 'F'); pdf.set_xy(12, pdf.get_y()+2)
        pdf.cell(0, 10, tr(f"ODEME: {s.get('Ödeme')}"), ln=1); pdf.set_text_color(200, 0, 0); pdf.set_font_size(16)
        pdf.cell(0, 10, tr(f"TAHSIL EDILECEK TUTAR: {s.get('Tutar')} TL"), ln=1); pdf.set_text_color(0, 0, 0); pdf.set_font_size(12); pdf.ln(5)
    else: pdf.cell(0, 10, tr(f"Odeme: {s.get('Ödeme')} | Tutar: {s.get('Tutar')} TL"), ln=1); pdf.ln(5)
    pdf.set_fill_color(240, 240, 240); pdf.cell(0, 10, "  MUSTERI BILGILERI", ln=1, fill=True); pdf.ln(2)
    pdf.cell(0, 8, tr(f"Musteri: {s.get('Müşteri')}"), ln=1); pdf.cell(0, 8, tr(f"Telefon: {s.get('Telefon')}"), ln=1)
    pdf.multi_cell(0, 8, tr(f"Adres: {s.get('Adres')}"))
    if s.get('Not'): pdf.multi_cell(0, 8, tr(f"NOT: {s.get('Not')}"))
    return pdf.output(dest='S').encode('latin-1')

# --- MENÜ ---
menu_options = ["📦 Sipariş Girişi", "📋 Sipariş Listesi", "🧾 Fatura Takibi", "🧾 Alış ve Tedarik", "📊 Raporlar", "💰 Cari Hesaplar", "📉 Maliyet Yönetimi", "➕ Ürün Yönetimi"]
menu = st.sidebar.radio("Menü", menu_options)

# 1. SİPARİŞ GİRİŞİ
if menu == "📦 Sipariş Girişi":
    st.header("Yeni Sipariş Ekle")
    col1, col2 = st.columns([1, 2])
    with col1:
        st.info("🛒 Ürün Bilgileri")
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
            if u2 in GUNCEL_URUNLER and os.path.exists(os.path.join(RESIM_KLASORU, GUNCEL_URUNLER[u2])):
                st.image(os.path.join(RESIM_KLASORU, GUNCEL_URUNLER[u2]), width=250)
            a2 = st.number_input("2. Ürün Adet", 1, 100, 1, key="a2_n")
            i2 = st.text_input("2. Ürün Özel İsim", key="i2_t")
    with col2:
        st.info("💳 Müşteri ve Finans")
        with st.form("siparis"):
            c1, c2 = st.columns(2)
            tutar = c1.text_input("Tutar (TL)")
            odeme = c2.selectbox("Ödeme", ["KAPIDA NAKİT", "KAPIDA K.KARTI", "HAVALE/EFT", "WEB SİTESİ"])
            c3, c4 = st.columns(2)
            kaynak = c3.selectbox("Kaynak", ["Instagram", "Web Sitesi", "Trendyol", "Whatsapp"])
            durum = c4.selectbox("Durum", ["YENİ SİPARİŞ", "KARGOLANDI", "TESLİM EDİLDİ"])
            st.divider()
            ad = st.text_input("Ad Soyad")
            tel = st.text_input("Telefon")
            tc = st.text_input("TC (Opsiyonel)")
            mail = st.text_input("Mail (Opsiyonel)")
            adres = st.text_area("Adres", height=100)
            notlar = st.text_input("Not")
            fatura = "KESİLDİ" if st.checkbox("Faturası Kesildi") else "KESİLMEDİ"
            if st.form_submit_button("KAYDET", type="primary"):
                try:
                    mevcut = verileri_getir("Siparisler")
                    yeni_no = 1000
                    if mevcut:
                        df_m = pd.DataFrame(mevcut)
                        if not df_m.empty and 'Siparis No' in df_m.columns:
                            try: yeni_no = int(pd.to_numeric(df_m['Siparis No'], errors='coerce').max()) + 1
                            except: pass
                    tarih = simdi().strftime("%d.%m.%Y %H:%M")
                    satir = [yeni_no, tarih, durum, ad, tel, tc, mail, u1, a1, i1, u2, a2, i2, tutar, odeme, kaynak, adres, notlar, fatura]
                    siparis_ekle(satir)
                    st.success(f"✅ Sipariş #{yeni_no} Kaydedildi!")
                except Exception as e: st.error(f"Hata: {e}")

# 2. SİPARİŞ LİSTESİ
elif menu == "📋 Sipariş Listesi":
    st.header("Sipariş Geçmişi")
    data = verileri_getir("Siparisler")
    if data:
        df = pd.DataFrame(data)
        if 'Siparis No' in df.columns:
            df['Siparis No'] = pd.to_numeric(df['Siparis No'], errors='coerce')
            df = df.sort_values(by="Siparis No", ascending=False)
        col1, col2 = st.columns([3, 1])
        arama = col1.text_input("Arama")
        if arama: df = df[df.astype(str).apply(lambda x: x.str.contains(arama, case=False)).any(axis=1)]
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.divider()
        if 'Siparis No' in df.columns and not df.empty:
            secenekler = df.apply(lambda x: f"{int(x['Siparis No'])} - {x['Müşteri']}", axis=1)
            secilen = st.selectbox("Fiş Yazdır:", secenekler)
            if st.button("📄 FİŞ OLUŞTUR"):
                s_no = int(secilen.split(" - ")[0])
                sip = df[df['Siparis No'] == s_no].iloc[0].to_dict()
                pdf_data = create_pdf(sip, GUNCEL_URUNLER)
                st.download_button("📥 İNDİR", pdf_data, f"Siparis_{s_no}.pdf", "application/pdf", type="primary")

# 3. FATURA TAKİBİ
elif menu == "🧾 Fatura Takibi":
    st.header("Müşteri Fatura Yönetimi")
    try:
        raw_data = verileri_getir("Siparisler")
        if raw_data:
            df = pd.DataFrame(raw_data)
            df['Tutar_float'] = df['Tutar'].apply(lambda x: safe_float(x))
            if "Fatura Durumu" not in df.columns: st.error("Veritabanında 'Fatura Durumu' sütunu bulunamadı.")
            else:
                tab1, tab2 = st.tabs(["🔴 Kesilecekler", "🟢 Kesilenler"])
                with tab1:
                    bekleyenler = df[df["Fatura Durumu"] != "KESİLDİ"].copy()
                    if not bekleyenler.empty:
                        st.metric("Bekleyen Tutar", f"{bekleyenler['Tutar_float'].sum():,.2f} TL")
                        st.dataframe(bekleyenler[["Siparis No", "Tarih", "Müşteri", "Tutar", "Fatura Durumu"]], use_container_width=True)
                        secenekler = bekleyenler.apply(lambda x: f"{x['Siparis No']} - {x['Müşteri']} ({x['Tutar']})", axis=1).tolist()
                        secilen_faturalar = st.multiselect("Kesildi İşaretle:", secenekler)
                        if st.button("ONAYLA"):
                            if secilen_faturalar:
                                siparis_nolar = [int(s.split(" - ")[0]) for s in secilen_faturalar]
                                sonuc = fatura_durumunu_kesildi_yap(siparis_nolar)
                                if sonuc == "BAŞARILI":
                                    st.success("Güncellendi!")
                                    st.cache_resource.clear()
                                    st.rerun()
                                else: st.error(sonuc)
                    else: st.success("Kesilecek fatura kalmadı.")
                with tab2:
                    kesilenler = df[df["Fatura Durumu"] == "KESİLDİ"]
                    st.dataframe(kesilenler[["Siparis No", "Tarih", "Müşteri", "Tutar", "Fatura Durumu"]], use_container_width=True)
    except Exception as e: st.error(f"Hata: {e}")

# 4. ALIŞ VE TEDARİK
elif menu == "🧾 Alış ve Tedarik":
    st.header("Mal Alım / Tedarikçi Takibi")
    
    # Cari Hesaplarını Çek
    cariler_data = verileri_getir("Cariler")
    df_cariler = pd.DataFrame(cariler_data)
    cari_listesi = df_cariler["Cari Adı"].unique().tolist() if not df_cariler.empty and "Cari Adı" in df_cariler.columns else []
    
    # Siparişleri Çek (Bağlantı için)
    siparis_data = verileri_getir("Siparisler")
    df_siparis = pd.DataFrame(siparis_data)
    siparis_listesi = []
    if not df_siparis.empty:
        df_siparis = df_siparis.sort_values(by="Siparis No", ascending=False).head(100)
        siparis_listesi = df_siparis.apply(lambda x: f"{x['Siparis No']} - {x['Müşteri']}", axis=1).tolist()

    tab1, tab2 = st.tabs(["➕ Yeni Mal Alımı Gir", "📋 Faturası Beklenenler / Geçmiş"])
    
    with tab1:
        st.info("Bu mal alımını hangi müşteri siparişi için yapıyorsunuz?")
        with st.form("alis_form"):
            col_sip = st.selectbox("Bağlı Olduğu Sipariş (Zorunlu Değil)", ["Genel Stok"] + siparis_listesi)
            
            c1, c2 = st.columns(2)
            # Eğer cari listesi boşsa manuel giriş kutusu göster
            if cari_listesi:
                secilen_cari = c1.selectbox("Tedarikçi (Cari Hesap)", cari_listesi)
            else:
                secilen_cari = c1.text_input("Tedarikçi Adı (Yeni)")
                
            urun_sec = c2.selectbox("Ürün", list(GUNCEL_URUNLER.keys()) + ["Diğer"])
            if urun_sec == "Diğer": urun_final = c2.text_input("Ürün Adı Manuel")
            else: urun_final = urun_sec
            
            c3, c4 = st.columns(2)
            adet = c3.number_input("Adet", min_value=1, value=1)
            birim_fiyat = c4.number_input("Birim Fiyat (TL)", min_value=0.0, format="%.2f")
            notlar = st.text_area("Not")
            
            toplam = adet * birim_fiyat
            st.metric("Toplam Tahmini Tutar", f"{toplam:,.2f} TL")
            
            if st.form_submit_button("SİPARİŞİ OLUŞTUR"):
                if secilen_cari and urun_final:
                    tarih = simdi().strftime("%d.%m.%Y %H:%M")
                    # Eğer cari listede yoksa otomatik oluştur
                    if secilen_cari not in cari_listesi:
                        cari_islem_ekle([secilen_cari, tarih, "AÇILIŞ", "Otomatik Oluşturuldu", 0])
                    
                    satir = [tarih, col_sip, secilen_cari, urun_final, adet, birim_fiyat, toplam, "BEKLİYOR", notlar]
                    alis_faturasi_ekle(satir)
                    st.success("✅ Alış talimatı sisteme girildi!")
                else: st.warning("Tedarikçi ve Ürün seçiniz.")

    with tab2:
        st.subheader("Alış Siparişleri Durumu")
        try:
            alis_data = verileri_getir("Alislar")
            if alis_data:
                df_alis = pd.DataFrame(alis_data)
                
                # Sütun kontrolü (Eski formatta kalmasın)
                if "Bağlı Sipariş" not in df_alis.columns:
                    st.warning("⚠️ Google Sheets 'Alislar' sayfasında 'Bağlı Sipariş' sütunu eksik olabilir. Lütfen güncelleyin.")
                else:
                    st.markdown("### 🔴 Faturası Gelmeyenler (Stok Bekleyen)")
                    bekleyenler = df_alis[df_alis["Durum"] == "BEKLİYOR"].copy()
                    
                    if not bekleyenler.empty:
                        # Filtre
                        unique_orders = bekleyenler["Bağlı Sipariş"].unique()
                        secili_filtre = st.multiselect("Siparişe Göre Filtrele:", unique_orders)
                        if secili_filtre: bekleyenler = bekleyenler[bekleyenler["Bağlı Sipariş"].isin(secili_filtre)]

                        secenekler = []
                        for idx, row in bekleyenler.iterrows():
                            bag = row.get('Bağlı Sipariş', '-')
                            secenekler.append(f"{idx} - {row['Cari Hesap']} | {row['Ürün']} | Sipariş: {bag} | {row['Toplam']} TL")
                        
                        secilen_alislar = st.multiselect("Faturası Gelenleri Seçip İşleyin:", secenekler)
                        
                        if st.button("FATURA GELDİ & CARİYE İŞLE"):
                            if secilen_alislar:
                                islem_listesi = []
                                for secim in secilen_alislar:
                                    idx = int(secim.split(" - ")[0])
                                    row = bekleyenler.loc[idx]
                                    aciklama = f"Alış Fat.: {row['Ürün']} ({row.get('Bağlı Sipariş','Genel')})"
                                    islem_listesi.append((idx, row['Cari Hesap'], row['Toplam'], aciklama))
                                
                                sonuc = alis_faturasi_onayla(islem_listesi)
                                if sonuc == "BAŞARILI":
                                    st.success("✅ İşlem tamamlandı!")
                                    st.cache_resource.clear()
                                    st.rerun()
                                else: st.error(sonuc)
                        
                        st.dataframe(bekleyenler, use_container_width=True)
                    else: st.success("Bekleyen fatura yok.")
                    
                    st.divider()
                    st.markdown("### 🟢 Geçmiş (Faturalaşanlar)")
                    gecmis = df_alis[df_alis["Durum"] != "BEKLİYOR"]
                    st.dataframe(gecmis, use_container_width=True)
            else: st.info("Kayıt yok.")
        except Exception as e: st.error(f"Hata: {e}")

# 5. RAPORLAR
elif menu == "📊 Raporlar":
    st.header("Satış Raporları")
    try:
        raw_data = verileri_getir("Siparisler")
        if raw_data:
            df = pd.DataFrame(raw_data)
            df['Tarih_dt'] = pd.to_datetime(df['Tarih'], format="%d.%m.%Y %H:%M", errors='coerce')
            df['Tarih_gun'] = df['Tarih_dt'].dt.date
            df['Tutar_float'] = df['Tutar'].apply(lambda x: safe_float(x))
            f1, f2, f3 = st.columns([1, 1, 2])
            with f1:
                secilen_urunler = st.multiselect("Ürün Seçiniz:", list(GUNCEL_URUNLER.keys()))
            with f2:
                zaman_secimi = st.selectbox("Dönem:", ["Bugün", "Dün", "Bu Ay", "Geçen Ay", "Son 7 Gün", "Son 30 Gün", "Son 1 Yıl", "Tarih Aralığı Seç"])

            bugun = simdi().date()
            bas, bit = bugun, bugun

            if zaman_secimi == "Bugün": pass
            elif zaman_secimi == "Dün": bas = bugun - timedelta(days=1); bit = bas
            elif zaman_secimi == "Son 7 Gün": bas = bugun - timedelta(days=7)
            elif zaman_secimi == "Son 30 Gün": bas = bugun - timedelta(days=30)
            elif zaman_secimi == "Son 1 Yıl": bas = bugun - timedelta(days=365)
            elif zaman_secimi == "Bu Ay": bas = bugun.replace(day=1)
            elif zaman_secimi == "Geçen Ay":
                bu_ay_ilk = bugun.replace(day=1)
                gecen_ay_son = bu_ay_ilk - timedelta(days=1)
                bas = gecen_ay_son.replace(day=1); bit = gecen_ay_son
            elif zaman_secimi == "Tarih Aralığı Seç":
                with f3:
                    d_range = st.date_input("Aralık:", (bugun - timedelta(days=7), bugun))
                    if len(d_range) == 2: bas, bit = d_range

            df_f = df[(df['Tarih_gun'] >= bas) & (df['Tarih_gun'] <= bit)]
            if secilen_urunler:
                df_f = df_f[df_f['Ürün 1'].isin(secilen_urunler) | df_f['Ürün 2'].isin(secilen_urunler)]

            if not df_f.empty:
                st.info(f"📅 {bas.strftime('%d.%m.%Y')} - {bit.strftime('%d.%m.%Y')}")
                top_ciro = df_f['Tutar_float'].sum()
                top_sip = len(df_f)
                a1 = pd.to_numeric(df_f['Adet 1'], errors='coerce').fillna(0).sum()
                a2 = pd.to_numeric(df_f['Adet 2'], errors='coerce').fillna(0).sum()
                top_urun = a1 + a2

                k1, k2, k3 = st.columns(3)
                k1.metric("Toplam Ciro", f"{top_ciro:,.2f} TL")
                k2.metric("Sipariş Sayısı", f"{top_sip}")
                k3.metric("Satılan Ürün", f"{int(top_urun)}")

                g1, g2 = st.columns(2)
                with g1:
                    u1c = df_f['Ürün 1'].value_counts()
                    u2c = df_f['Ürün 2'].value_counts()
                    total = u1c.add(u2c, fill_value=0).sort_values(ascending=True)
                    if '' in total.index: total = total.drop('')
                    if not total.empty:
                        fig = px.bar(x=total.values, y=total.index, orientation='h', labels={'x':'Adet','y':''})
                        st.plotly_chart(fig, use_container_width=True)
                with g2:
                    if not df_f.empty:
                        df_grp = df_f.groupby('Tarih_gun')['Tutar_float'].sum().reset_index()
                        fig2 = px.line(df_grp, x='Tarih_gun', y='Tutar_float', markers=True)
                        st.plotly_chart(fig2, use_container_width=True)
            else: st.warning("Veri bulunamadı.")
        else: st.info("Veri yok.")
    except Exception as e: st.error(f"Hata: {e}")

# 6. CARİ HESAPLAR
elif menu == "💰 Cari Hesaplar":
    st.header("Cari Takip")
    try:
        data = verileri_getir("Cariler")
        c1, c2 = st.columns([1,2])
        with c1:
            st.subheader("İşlem Ekle")
            with st.form("cari"):
                ad = st.text_input("Cari Adı")
                tip = st.selectbox("İşlem", ["FATURA (Borç)", "ÖDEME (Alacak)"])
                desc = st.text_input("Açıklama")
                tutar = st.number_input("Tutar", min_value=0.0, format="%.2f")
                if st.form_submit_button("KAYDET"):
                    cari_islem_ekle([ad, simdi().strftime("%d.%m.%Y"), tip, desc, tutar])
                    st.success("Kaydedildi!")
                    st.rerun()
        with c2:
            if data:
                df = pd.DataFrame(data)
                if 'Cari Adı' in df.columns:
                    secili = st.selectbox("Hesap:", df['Cari Adı'].unique())
                    if secili:
                        sub = df[df['Cari Adı'] == secili]
                        st.table(sub)
                        borc = sub[sub['İşlem Tipi'].astype(str).str.contains("FATURA")]['Tutar'].sum()
                        alacak = sub[sub['İşlem Tipi'].astype(str).str.contains("ÖDEME")]['Tutar'].sum()
                        st.metric("BAKİYE", f"{alacak - borc:,.2f} TL")
    except: st.error("Cari verisi alınamadı.")

# 7. MALİYET YÖNETİMİ
elif menu == "📉 Maliyet Yönetimi":
    st.header("Ürün Maliyet Yönetimi")
    try:
        maliyet_data = verileri_getir("Maliyetler")
        df_m = pd.DataFrame(maliyet_data)
    except: df_m = pd.DataFrame()

    tab1, tab2 = st.tabs(["📋 Liste / Detay", "➕ Ekle / Güncelle"])

    with tab1:
        if not df_m.empty:
            st.dataframe(df_m, use_container_width=True)
            if "Ürün Id" in df_m.columns:
                urunler = df_m["Ürün Id"].unique().tolist()
                secili = st.selectbox("Detay Gör:", ["Seçiniz..."] + urunler)
                if secili != "Seçiniz...":
                    detay = df_m[df_m["Ürün Id"] == secili].iloc[0]
                    c1, c2 = st.columns([1, 2])
                    c1.metric("TOPLAM MALİYET", f"{detay.get('MALİYET',0)} TL")
                    items = {k: v for k, v in detay.items() if k not in ["Görsel", "Ürün Kod", "Ürün Id", "MALİYET"] and isinstance(v, (int, float)) and v > 0}
                    c2.table(pd.DataFrame(list(items.items()), columns=["Kalem", "Tutar"]))
            else: st.warning("Excel'de 'Ürün Id' sütunu eksik.")
        else: st.warning("Maliyet tablosu boş veya okunamadı.")

    with tab2:
        st.subheader("Maliyet Kartı")
        mod = st.radio("İşlem:", ["Güncelle", "Yeni Ekle"], horizontal=True)
        vals = {}
        if mod == "Güncelle" and not df_m.empty and "Ürün Id" in
