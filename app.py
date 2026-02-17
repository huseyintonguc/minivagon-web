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

# Ürün Kataloğu
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

def yeni_urun_ekle(ad, resim_adi):
    sh = get_sheet()
    try:
        w = sh.worksheet("Urunler")
    except:
        w = sh.add_worksheet(title="Urunler", rows=100, cols=2)
        w.append_row(["Urun Adi", "Resim Dosya Adi"])
    w.append_row([ad, resim_adi])

def urunleri_getir():
    try:
        sh = get_sheet()
        try:
            w = sh.worksheet("Urunler")
            kayitlar = w.get_all_records()
            if not kayitlar: return URUNLER
            guncel_urunler = {item['Urun Adi']: item['Resim Dosya Adi'] for item in kayitlar}
            # Sabit listeyle birleştir (Eksik kalmasın)
            return {**URUNLER, **guncel_urunler}
        except:
            return URUNLER
    except:
        return URUNLER

def verileri_getir(sayfa_adi):
    sh = get_sheet()
    w = sh.worksheet(sayfa_adi)
    return w.get_all_records()

# --- PDF OLUŞTURMA ---
def create_pdf(s, urun_dict):
    pdf = FPDF()
    pdf.add_page()
    try: pdf.add_font('ArialTR', '', 'arial.ttf', uni=True); pdf.set_font('ArialTR', '', 12)
    except: pdf.set_font("Arial", size=12)

    # Başlık
    pdf.set_fill_color(40, 40, 40); pdf.rect(0, 0, 210, 30, 'F')
    pdf.set_text_color(255, 255, 255); pdf.set_font_size(20); pdf.text(10, 20, "MINIVAGON")
    pdf.set_font_size(10); pdf.set_text_color(200, 200, 200)
    pdf.text(150, 15, f"Siparis No: #{s.get('Siparis No')}")
    pdf.text(150, 22, f"Tarih: {s.get('Tarih')}")

    # Resim Ekleme
    def resim_koy(u_adi, x_pos):
        if u_adi in urun_dict:
            dosya_adi = urun_dict[u_adi]
            full_path = os.path.join(RESIM_KLASORU, dosya_adi)
            if os.path.exists(full_path):
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                        img = Image.open(full_path).convert('RGB')
                        img.thumbnail((300, 220))
                        img.save(tmp.name)
                        pdf.image(tmp.name, x=x_pos, y=40, h=60)
                except: pass

    if s.get('Ürün 2'):
        resim_koy(s.get('Ürün 1'), 15)
        resim_koy(s.get('Ürün 2'), 110)
    else:
        resim_koy(s.get('Ürün 1'), 65)

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
menu = st.sidebar.radio("Menü", ["📦 Sipariş Girişi", "📋 Sipariş Listesi", "📊 Raporlar", "💰 Cari Hesaplar", "📉 Maliyet Hesap", "➕ Ürün Yönetimi"])

# Güncel ürünleri çek
GUNCEL_URUNLER = urunleri_getir()

# -----------------------------------------------------------------------------
# 1. SİPARİŞ GİRİŞİ
# -----------------------------------------------------------------------------
if menu == "📦 Sipariş Girişi":
    st.header("Yeni Sipariş Ekle")
    col1, col2 = st.columns([1, 2])
    with col1:
        st.info("🛒 Ürün Bilgileri")
        u1 = st.selectbox("1. Ürün Seçimi", list(GUNCEL_URUNLER.keys()))
        if u1 in GUNCEL_URUNLER:
            img_path1 = os.path.join(RESIM_KLASORU, GUNCEL_URUNLER[u1])
            if os.path.exists(img_path1): st.image(img_path1, width=250, caption=u1)
        a1 = st.number_input("1. Ürün Adet", 1, 100, 1)
        i1 = st.text_input("1. Ürün Özel İsim (Varsa)")
        st.markdown("---")
        ikinci_urun_aktif = st.checkbox("2. Ürün Ekle (+)")
        u2, a2, i2 = "", "", ""
        if ikinci_urun_aktif:
            u2 = st.selectbox("2. Ürün Seçimi", list(GUNCEL_URUNLER.keys()), key="u2_sel")
            if u2 in GUNCEL_URUNLER:
                img_path2 = os.path.join(RESIM_KLASORU, GUNCEL_URUNLER[u2])
                if os.path.exists(img_path2): st.image(img_path2, width=250, caption=u2)
            a2 = st.number_input("2. Ürün Adet", 1, 100, 1, key="a2_inp")
            i2 = st.text_input("2. Ürün Özel İsim", key="i2_inp")

    with col2:
        st.info("💳 Müşteri ve Finans")
        with st.form("siparis_form", clear_on_submit=True):
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
            adres = st.text_area("Adres", height=100)
            notlar = st.text_input("Sipariş Notu")
            fatura_kesildi = st.checkbox("Faturası Kesildi")
            submitted = st.form_submit_button("SİPARİŞİ KAYDET", type="primary")
            
            if submitted:
                try:
                    mevcut = verileri_getir("Siparisler")
                    yeni_no = 1000
                    if mevcut:
                        df_m = pd.DataFrame(mevcut)
                        if not df_m.empty and 'Siparis No' in df_m.columns:
                            try: yeni_no = int(pd.to_numeric(df_m['Siparis No'], errors='coerce').max()) + 1
                            except: pass
                    tarih = simdi().strftime("%d.%m.%Y %H:%M")
                    fatura_durum = "KESİLDİ" if fatura_kesildi else "KESİLMEDİ"
                    satir = [yeni_no, tarih, durum, ad, tel, tc, mail, u1, a1, i1, u2, a2, i2, tutar, odeme, kaynak, adres, notlar, fatura_durum]
                    siparis_ekle(satir)
                    st.success(f"✅ Sipariş #{yeni_no} Başarıyla Kaydedildi!")
                except Exception as e:
                    st.error(f"Hata oluştu: {e}")

# -----------------------------------------------------------------------------
# 2. SİPARİŞ LİSTESİ
# -----------------------------------------------------------------------------
elif menu == "📋 Sipariş Listesi":
    st.header("Sipariş Geçmişi")
    try:
        data = verileri_getir("Siparisler")
        if data:
            df = pd.DataFrame(data)
            if 'Siparis No' in df.columns:
                df['Siparis No'] = pd.to_numeric(df['Siparis No'], errors='coerce')
                df = df.sort_values(by="Siparis No", ascending=False)
            col1, col2 = st.columns([3, 1])
            arama = col1.text_input("İsim veya Sipariş No Ara")
            if arama:
                df = df[df.astype(str).apply(lambda x: x.str.contains(arama, case=False)).any(axis=1)]
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
        else:
            st.info("Kayıt bulunamadı.")
    except Exception as e:
        st.error(f"Veri çekilemedi: {e}")

# -----------------------------------------------------------------------------
# 3. RAPORLAR
# -----------------------------------------------------------------------------
elif menu == "📊 Raporlar":
    st.header("Detaylı Satış Analizi")
    try:
        raw_data = verileri_getir("Siparisler")
        if raw_data:
            df = pd.DataFrame(raw_data)
            df['Tarih_dt'] = pd.to_datetime(df['Tarih'], format="%d.%m.%Y %H:%M", errors='coerce')
            df['Tarih_gun'] = df['Tarih_dt'].dt.date
            def temizle_tutar(val):
                try:
                    val = str(val).replace('TL', '').replace(' ', '')
                    if "," in val: val = val.replace('.', '').replace(',', '.') 
                    return float(val)
                except: return 0.0
            df['Tutar_float'] = df['Tutar'].apply(temizle_tutar)

            st.markdown("### 🔍 Filtreler")
            f1, f2, f3 = st.columns([1, 1, 2])
            with f1:
                secilen_urunler = st.multiselect("Ürün Seçiniz:", list(GUNCEL_URUNLER.keys()), placeholder="Tüm Ürünler")
            with f2:
                zaman_secimi = st.selectbox("Rapor Dönemi:", ["Bugün", "Dün", "Bu Ay", "Geçen Ay", "Son 7 Gün", "Son 30 Gün", "Son 1 Yıl", "Tarih Aralığı Seç"])

            bugun = simdi().date()
            baslangic_tarihi = bugun
            bitis_tarihi = bugun

            if zaman_secimi == "Bugün": pass
            elif zaman_secimi == "Dün":
                baslangic_tarihi = bugun - timedelta(days=1); bitis_tarihi = baslangic_tarihi
            elif zaman_secimi == "Son 7 Gün":
                baslangic_tarihi = bugun - timedelta(days=7)
            elif zaman_secimi == "Son 30 Gün":
                baslangic_tarihi = bugun - timedelta(days=30)
            elif zaman_secimi == "Bu Ay":
                baslangic_tarihi = bugun.replace(day=1)
            elif zaman_secimi == "Geçen Ay":
                bu_ay_ilk = bugun.replace(day=1)
                gecen_ay_son = bu_ay_ilk - timedelta(days=1)
                gecen_ay_ilk = gecen_ay_son.replace(day=1)
                baslangic_tarihi = gecen_ay_ilk; bitis_tarihi = gecen_ay_son
            elif zaman_secimi == "Son 1 Yıl":
                baslangic_tarihi = bugun - timedelta(days=365)
            elif zaman_secimi == "Tarih Aralığı Seç":
                with f3:
                    d_range = st.date_input("Tarih Aralığı:", (bugun - timedelta(days=7), bugun))
                    if len(d_range) == 2: baslangic_tarihi, bitis_tarihi = d_range

            df_filtered = df[(df['Tarih_gun'] >= baslangic_tarihi) & (df['Tarih_gun'] <= bitis_tarihi)]
            if secilen_urunler:
                df_filtered = df_filtered[df_filtered['Ürün 1'].isin(secilen_urunler) | df_filtered['Ürün 2'].isin(secilen_urunler)]

            st.divider()
            if not df_filtered.empty:
                st.subheader(f"📅 {baslangic_tarihi.strftime('%d.%m.%Y')} - {bitis_tarihi.strftime('%d.%m.%Y')}")
                toplam_ciro = df_filtered['Tutar_float'].sum()
                toplam_siparis = len(df_filtered)
                toplam_urun = pd.to_numeric(df_filtered['Adet 1'], errors='coerce').sum() + pd.to_numeric(df_filtered['Adet 2'], errors='coerce').fillna(0).sum()
                
                k1, k2, k3 = st.columns(3)
                k1.metric("Toplam Ciro", f"{toplam_ciro:,.2f} TL")
                k2.metric("Toplam Sipariş", f"{toplam_siparis}")
                k3.metric("Satılan Ürün", f"{int(toplam_urun)}")

                g1, g2 = st.columns(2)
                with g1:
                    u1_c = df_filtered['Ürün 1'].value_counts()
                    u2_c = df_filtered['Ürün 2'].value_counts()
                    total_counts = u1_c.add(u2_c, fill_value=0).sort_values(ascending=True)
                    if '' in total_counts.index: total_counts = total_counts.drop('')
                    fig_bar = px.bar(x=total_counts.values, y=total_counts.index, orientation='h', labels={'x':'Adet', 'y':'Ürün'}, title="En Çok Satanlar")
                    st.plotly_chart(fig_bar, use_container_width=True)
                with g2:
                    aylar_tr = {1:'Ocak', 2:'Şubat', 3:'Mart', 4:'Nisan', 5:'Mayıs', 6:'Haziran', 7:'Temmuz', 8:'Ağustos', 9:'Eylül', 10:'Ekim', 11:'Kasım', 12:'Aralık'}
                    df_chart = df_filtered.copy()
                    if (bitis_tarihi - baslangic_tarihi).days > 31:
                        df_chart['Ay'] = df_chart['Tarih_dt'].dt.month.map(aylar_tr)
                        df_grouped = df_chart.groupby('Ay')['Tutar_float'].sum().reset_index()
                        fig_line = px.line(df_grouped, x='Ay', y='Tutar_float', title="Aylık Ciro")
                    else:
                        df_grouped = df_chart.groupby('Tarih_gun')['Tutar_float'].sum().reset_index()
                        fig_line = px.line(df_grouped, x='Tarih_gun', y='Tutar_float', title="Günlük Ciro")
                    st.plotly_chart(fig_line, use_container_width=True)
            else:
                st.warning("Veri bulunamadı.")
    except Exception as e:
        st.error(f"Rapor hatası: {e}")

# -----------------------------------------------------------------------------
# 4. CARİ HESAPLAR
# -----------------------------------------------------------------------------
elif menu == "💰 Cari Hesaplar":
    st.header("Cari Takip")
    try:
        data = verileri_getir("Cariler")
        c1, c2 = st.columns([1, 2])
        with c1:
            st.subheader("İşlem Ekle")
            with st.form("cari_ekle"):
                c_ad = st.text_input("Cari Adı")
                c_tip = st.selectbox("İşlem", ["FATURA (Borç)", "ÖDEME (Alacak)"])
                c_desc = st.text_input("Açıklama")
                c_tutar = st.number_input("Tutar", min_value=0.0, format="%.2f")
                if st.form_submit_button("KAYDET"):
                    tarih = simdi().strftime("%d.%m.%Y")
                    cari_islem_ekle([c_ad, tarih, c_tip, c_desc, c_tutar])
                    st.success("Kaydedildi!")
                    st.rerun()
        with c2:
            if data:
                df = pd.DataFrame(data)
                if 'cari_adi' in df.columns:
                    cariler = df['cari_adi'].unique()
                    secili = st.selectbox("Hesap Seçiniz:", cariler)
                    if secili:
                        sub_df = df[df['cari_adi'] == secili]
                        st.table(sub_df)
                        borc = sub_df[sub_df['islem_tipi'].astype(str).str.contains("FATURA")]['tutar'].sum()
                        alacak = sub_df[sub_df['islem_tipi'].astype(str).str.contains("ÖDEME")]['tutar'].sum()
                        k1, k2, k3 = st.columns(3)
                        k1.metric("Toplam Borç", f"{borc:,.2f}")
                        k2.metric("Toplam Ödeme", f"{alacak:,.2f}")
                        k3.metric("BAKİYE", f"{alacak - borc:,.2f} TL", delta_color="normal")
    except Exception as e:
        st.error(f"Hata: {e}")

# -----------------------------------------------------------------------------
# 5. MALİYET HESAPLAMA (YENİ - EXCEL TABLOSU)
# -----------------------------------------------------------------------------
elif menu == "📉 Maliyet Hesap":
    st.header("Ürün Maliyet Tablosu")
    
    try:
        data = verileri_getir("Maliyetler")
        if data:
            df = pd.DataFrame(data)
            
            # Ürün Seçimi ile Filtreleme
            urun_listesi = df["Ürün Id"].unique().tolist()
            secili_urun = st.selectbox("Detaylı İncelemek İçin Ürün Seçin:", ["Tümü"] + urun_listesi)
            
            if secili_urun != "Tümü":
                st.subheader(f"📌 {secili_urun} - Maliyet Detayı")
                
                # Seçilen ürünün satırını bul
                urun_detay = df[df["Ürün Id"] == secili_urun].iloc[0]
                
                # Maliyet Kartı Gösterimi
                col1, col2 = st.columns([1, 2])
                with col1:
                    # Toplam Maliyet
                    toplam_maliyet = urun_detay.get("MALİYET", 0)
                    st.metric("TOPLAM MALİYET", f"{toplam_maliyet} TL")
                    st.info(f"Kod: {urun_detay.get('Ürün Kod', '-')}")
                
                with col2:
                    # Maliyet Bileşenleri Tablosu
                    bilesenler = {k: v for k, v in urun_detay.items() if k not in ["Görsel", "Ürün Kod", "Ürün Id", "MALİYET"] and v}
                    df_bilesen = pd.DataFrame(list(bilesenler.items()), columns=["Kalem", "Tutar (TL)"])
                    st.table(df_bilesen)
            
            st.divider()
            st.markdown("### 📋 Tüm Liste")
            st.dataframe(df, use_container_width=True)
            
        else:
            st.warning("Maliyet tablosu boş veya okunamadı. Google Sheets'te 'Maliyetler' sayfasını kontrol edin.")
            
    except Exception as e:
        st.error(f"Veri çekme hatası: {e}")
        st.info("Lütfen Google Sheets dosyanızda 'Maliyetler' adında bir sayfa olduğundan emin olun.")

# -----------------------------------------------------------------------------
# 6. ÜRÜN YÖNETİMİ
# -----------------------------------------------------------------------------
elif menu == "➕ Ürün Yönetimi":
    st.header("Yeni Ürün Tanımla")
    with st.form("yeni_urun_form", clear_on_submit=True):
        yeni_urun_adi = st.text_input("Ürün Adı")
        uploaded_file = st.file_uploader("Ürün Görseli (JPG/PNG)", type=['jpg', 'png', 'jpeg'])
        submit_urun = st.form_submit_button("ÜRÜNÜ EKLE")
        
        if submit_urun:
            if yeni_urun_adi and uploaded_file:
                dosya_adi = f"{yeni_urun_adi.replace(' ', '_')}.jpg"
                save_path = os.path.join(RESIM_KLASORU, dosya_adi)
                try:
                    image = Image.open(uploaded_file).convert('RGB')
                    image.save(save_path)
                    yeni_urun_ekle(yeni_urun_adi, dosya_adi)
                    st.success(f"✅ {yeni_urun_adi} eklendi!")
                except Exception as e:
                    st.error(f"Hata: {e}")
            else:
                st.warning("İsim ve Resim zorunludur.")
    
    st.divider()
    st.subheader("Mevcut Ürün Listesi")
    df_urunler = pd.DataFrame(list(GUNCEL_URUNLER.items()), columns=['Ürün Adı', 'Dosya Yolu'])
    st.dataframe(df_urunler, use_container_width=True)
