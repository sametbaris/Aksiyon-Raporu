import streamlit as st
import pandas as pd
import requests
import time
import concurrent.futures
from datetime import datetime
import base64
import re
import gspread
from google.oauth2.service_account import Credentials
import io

# ================= SAYFA AYARLARI =================
st.set_page_config(page_title="Aksiyon Raporu & BBX", layout="wide", initial_sidebar_state="collapsed")

# ================= SESSION (OTURUM) YÖNETİMİ =================
if "current_view" not in st.session_state:
    st.session_state.current_view = "ana_sayfa"
if "bbx_authenticated" not in st.session_state:
    st.session_state.bbx_authenticated = False

# ================= ORİJİNAL ANA SAYFA FONKSİYONLARI =================
def fetch_product_link(barcode, is_hepsiburada=False):
    if is_hepsiburada:
        search_url = f"https://www.hepsiburada.com/ara?q={barcode}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.hepsiburada.com/"
        }
        try:
            response = requests.get(search_url, headers=headers, timeout=10)
            if response.status_code == 200:
                html_content = response.text
                match = re.search(r'<a[^>]+href="(/[^"]+-p-[^"]+)"[^>]*>', html_content)
                if match:
                    return f"https://www.hepsiburada.com{match.group(1)}"
                match2 = re.search(r'<a[^>]+href="(/magaza/[^"]+)"[^>]*>', html_content)
                if match2:
                    return f"https://www.hepsiburada.com{match2.group(1)}"
        except Exception:
            pass
        return ""
    else:
        search_url = f"https://public-mdc.trendyol.com/discovery-web-searchgw-service/v2/api/infinite-scroll/sr?q={barcode}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.trendyol.com",
            "Referer": f"https://www.trendyol.com/sr?q={barcode}"
        }
        try:
            response = requests.get(search_url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("result", {}).get("products"):
                    return f"https://www.trendyol.com{data['result']['products'][0]['url']}"
        except Exception:
            pass
        return ""

def process_links(df):
    if 'TY Link' not in df.columns: df['TY Link'] = ""
    if 'HB Link' not in df.columns: df['HB Link'] = ""
        
    missing_ty = df[df['TY Link'].isna() | (df['TY Link'] == '')]
    missing_hb = df[df['HB Link'].isna() | (df['HB Link'] == '')]
    total_missing = len(missing_ty) + len(missing_hb)
    
    if total_missing == 0: return df, 0
        
    progress_bar = st.progress(0)
    status_text = st.empty()
    processed = 0
    
    if len(missing_ty) > 0:
        status_text.text(f"Trendyol linkleri aranıyor... (0/{len(missing_ty)})")
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_idx = {executor.submit(fetch_product_link, row['Barkod'], False): idx for idx, row in missing_ty.iterrows()}
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    link = future.result()
                    if link: df.at[idx, 'TY Link'] = link
                except Exception: pass
                processed += 1
                progress_bar.progress(processed / total_missing)
                status_text.text(f"Linkler aranıyor... ({processed}/{total_missing})")
                time.sleep(0.1)

    if len(missing_hb) > 0:
        status_text.text(f"Hepsiburada linkleri aranıyor... (0/{len(missing_hb)})")
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_idx = {executor.submit(fetch_product_link, row['Barkod'], True): idx for idx, row in missing_hb.iterrows()}
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    link = future.result()
                    if link: df.at[idx, 'HB Link'] = link
                except Exception: pass
                processed += 1
                progress_bar.progress(processed / total_missing)
                status_text.text(f"Linkler aranıyor... ({processed}/{total_missing})")
                time.sleep(0.5)

    progress_bar.empty()
    status_text.empty()
    return df, processed

def get_table_download_link(df, filename="aksiyon_raporu_guncel.csv"):
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    return f'<a href="data:file/csv;base64,{b64}" download="{filename}" style="display: inline-block; padding: 0.5em 1em; color: #ffffff; background-color: #4facfe; border-radius: 5px; text-decoration: none; font-weight: bold; text-align: center; width: 100%; margin-top: 10px;">Tüm Tabloyu İndir (CSV)</a>'

@st.cache_data(ttl=600)
def load_data(sheet_id, sheet_name="Stok"):
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
    try: return pd.read_csv(url)
    except Exception as e:
        st.error(f"Veri çekme hatası: {e}")
        return None

# ================= BBX PANELİ İÇİN FONKSİYON =================
def get_bbx_data_from_sheets():
    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        credentials = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        client = gspread.authorize(credentials)
        return client.open("Aksiyon_Guncel").worksheet("BBX").get_all_values()
    except Exception as e:
        st.error(f"Google Sheets'e bağlanırken hata: {e}")
        return []

# ================= EKRAN YÖNLENDİRMELERİ =================
if st.session_state.current_view == "ana_sayfa":
    # ---------------------------------------------------------
    # EKRAN 1: AKSİYON RAPORU (ANA SAYFA - ORİJİNAL)
    # ---------------------------------------------------------
    
    # Orijinal başlık ve tarih
    st.markdown("<h1 style='text-align: left; background: linear-gradient(90deg, #f8f9fa, #e9ecef); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-family: sans-serif; font-weight: 800; font-size: 2.5rem;'>Aksiyon Raporu</h1>", unsafe_allow_html=True)
    st.write(f"Son Güncelleme: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
    
    # BBX Butonu (Standart Streamlit butonu, CSS'siz)
    if st.button("🔐 BBX Paneline Giriş Yap (Şifreli)", use_container_width=True):
        st.session_state.current_view = "bbx_paneli"
        st.rerun()
    st.markdown("---")

    SHEET_ID = "142yZJ90wUoU9YF48S9N2-T9_6lZg6iC1w9EAS7l9XW4"
    df = load_data(SHEET_ID)

    if df is not None:
        with st.sidebar:
            st.header("🔗 Link İşlemleri")
            st.write("Eksik olan Trendyol ve Hepsiburada linklerini otomatik çekin.")
            if st.button("Linkleri Çek", type="primary"):
                with st.spinner("Linkler aranıyor..."):
                    updated_df, count = process_links(df)
                    if count > 0:
                        st.success(f"Başarıyla {count} yeni link bulundu!")
                        st.session_state['updated_df'] = updated_df
                    else:
                        st.info("Tüm linkler zaten mevcut veya bulunamadı.")
            if 'updated_df' in st.session_state:
                st.markdown(get_table_download_link(st.session_state['updated_df'], "aksiyon_raporu_linkli.csv"), unsafe_allow_html=True)
            st.markdown("---")
            st.header("Filtreler")

        if 'Önerilen Aksiyon' in df.columns:
            toplam_aksiyon = len(df[df['Önerilen Aksiyon'].str.strip() != ''])
            indirim_sayisi = len(df[df['Önerilen Aksiyon'].str.contains('Fiyat Düş', na=False)])
            zam_sayisi = len(df[df['Önerilen Aksiyon'].str.contains('Fiyat Artır', na=False)])
            stok_uyari = len(df[df['Önerilen Aksiyon'].str.contains('Stok Çek', na=False)])

            # Orijinal metrik kartları (Senin gönderdiğin app (10).py'deki CSS'li hali)
            col1, col2, col3, col4 = st.columns(4)
            
            metric_css = """
            <style>
            .m-card { background-color: #262730; border-radius: 10px; padding: 20px; text-align: center; border: 1px solid #3a3b45; }
            .m-val { font-size: 2.5rem; font-weight: bold; margin: 10px 0; }
            .m-lbl { font-size: 1.1rem; color: #a0aabf; }
            .m-sub { font-size: 0.9rem; color: #6c757d; }
            </style>
            """
            st.markdown(metric_css, unsafe_allow_html=True)
            
            with col1: st.markdown(f'<div class="m-card"><div class="m-lbl">Toplam Aksiyon Bekleyen</div><div class="m-val" style="color: #4facfe;">{toplam_aksiyon}</div><div class="m-sub">İncelenmesi gereken ürün</div></div>', unsafe_allow_html=True)
            with col2: st.markdown(f'<div class="m-card"><div class="m-lbl">İndirim Önerisi</div><div class="m-val" style="color: #00f2fe;">{indirim_sayisi}</div><div class="m-sub">Rakiplerin altına inmek için</div></div>', unsafe_allow_html=True)
            with col3: st.markdown(f'<div class="m-card"><div class="m-lbl">Zam Önerisi</div><div class="m-val" style="color: #ff9a9e;">{zam_sayisi}</div><div class="m-sub">Kar marjını artırmak için</div></div>', unsafe_allow_html=True)
            with col4: st.markdown(f'<div class="m-card"><div class="m-lbl">Stok Tükendi</div><div class="m-val" style="color: #fecfef;">{stok_uyari}</div><div class="m-sub">Acil stok girişi gerekenler</div></div>', unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            if 'updated_df' in st.session_state:
                df = st.session_state['updated_df']

            search_term = st.sidebar.text_input("🔍 SKU veya Barkod Ara:")
            alt_grup_filter = st.sidebar.multiselect("Alt Grup Seçin:", options=sorted(df['Alt Grup'].dropna().unique()) if 'Alt Grup' in df.columns else [])
            aksiyon_filter = st.sidebar.multiselect("Aksiyon Tipi:", options=sorted(df['Önerilen Aksiyon'].dropna().unique()))

            filtered_df = df.copy()
            if search_term:
                filtered_df = filtered_df[filtered_df.astype(str).apply(lambda x: x.str.contains(search_term, case=False, na=False)).any(axis=1)]
            if alt_grup_filter:
                filtered_df = filtered_df[filtered_df['Alt Grup'].isin(alt_grup_filter)]
            if aksiyon_filter:
                filtered_df = filtered_df[filtered_df['Önerilen Aksiyon'].isin(aksiyon_filter)]

            tab1, tab2 = st.tabs(["📋 Detaylı Aksiyon Listesi", "📈 Trend Analizi (Yakında)"])

            with tab1:
                st.dataframe(filtered_df, use_container_width=True, height=600, hide_index=True)
                final_df = filtered_df if (search_term or alt_grup_filter or aksiyon_filter) else df
                st.markdown(get_table_download_link(final_df), unsafe_allow_html=True)

            with tab2:
                st.info("Trend analizi ve grafikler bu sekmede yer alacaktır.")
                
        else:
            st.error("'Önerilen Aksiyon' sütunu bulunamadı.")
            st.dataframe(df.head())

elif st.session_state.current_view == "bbx_paneli":
    # ---------------------------------------------------------
    # EKRAN 2: BBX PANELİ (ŞİFRELİ ALAN)
    # ---------------------------------------------------------
    st.markdown("<h1 style='background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 2.8rem; font-weight: 800; font-family: sans-serif;'>🛒 BBX Fiyat & Satıcı Analizi</h1>", unsafe_allow_html=True)
    st.write("Trendyol ve Hepsiburada Buybox durumunuzu takip edin, müdahale gereken ürünleri alarm butonlarıyla anında dışa aktarın.")
    
    if st.button("🔙 Aksiyon Raporuna Geri Dön", use_container_width=True):
        st.session_state.current_view = "ana_sayfa"
        st.rerun()
        
    st.markdown("---")

    if not st.session_state.bbx_authenticated:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.info("ℹ️ Bu alana erişim kısıtlanmıştır. Lütfen yönetici şifresini giriniz.")
            pwd = st.text_input("Giriş Şifresi:", type="password")
            if pwd == "mobese":
                st.session_state.bbx_authenticated = True
                st.success("✅ Şifre doğru! Giriş yapılıyor...")
                st.rerun()
            elif pwd:
                st.error("❌ Hatalı şifre!")
    else:
        raw_data = get_bbx_data_from_sheets()

        if raw_data:
            all_export_data = []
            ty_alarm_data = []
            hb_alarm_data = []
            
            html_table = """
            <style>
                .bbx-table-wrapper { background-color: var(--background-color); border-radius: 12px; padding: 1px; overflow: hidden; margin-top: 5px; border: 1px solid var(--secondary-background-color); }
                .bbx-table { width: 100%; border-collapse: collapse; font-family: sans-serif; font-size: 13px; color: var(--text-color); }
                .bbx-table th, .bbx-table td { border: 1px solid var(--secondary-background-color); padding: 12px 6px; text-align: center; vertical-align: middle; }
                .bbx-table th { background-color: var(--secondary-background-color); font-weight: 600; text-transform: uppercase; font-size: 12px; }
                .bbx-sku { color: #0078ff !important; font-weight: bold; font-size: 14px; } 
                .pill-satici { background-color: var(--secondary-background-color); border: 1px solid rgba(128, 128, 128, 0.2); border-radius: 20px; padding: 4px 12px; font-weight: 600; font-size: 12px; display: inline-block; max-width: 130px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
                .pill-fiyat { background-color: rgba(0, 184, 76, 0.1); border: 1px solid rgba(0, 184, 76, 0.3); color: #00b84c; border-radius: 20px; padding: 4px 14px; font-weight: bold; font-size: 13px; display: inline-block; }
                @keyframes blink { 0% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(1.1); } 100% { opacity: 1; transform: scale(1); } }
                .status-dot { height: 14px; width: 14px; border-radius: 50%; display: inline-block; animation: blink 1.5s infinite; }
                .dot-green { background-color: #00e676; box-shadow: 0 0 10px #00e676; }
                .dot-yellow { background-color: #ffea00; box-shadow: 0 0 10px #ffea00; }
                .dot-red { background-color: #ff1744; box-shadow: 0 0 10px #ff1744; }
                .n-b-b { border-bottom: none !important; padding-bottom: 2px !important; }
                .n-b-t { border-top: none !important; padding-top: 2px !important; }
                .p-div { border-bottom: 2px solid var(--secondary-background-color) !important; }
            </style>
            
            <div class="bbx-table-wrapper">
            <table class="bbx-table">
                <thead>
                    <tr>
                        <th rowspan="2">Barkod</th>
                        <th rowspan="2">HB Kod</th>
                        <th rowspan="2">SKU</th>
                        <th rowspan="2">Alt Grup</th>
                        <th colspan="4">TRENDYOL</th>
                        <th colspan="4">HEPSİBURADA</th>
                    </tr>
                    <tr>
                        <th style="width: 45px;">Durum</th>
                        <th>1. Satıcı</th>
                        <th>2. Satıcı</th>
                        <th>3. Satıcı</th>
                        <th style="width: 45px;">Durum</th>
                        <th>1. Satıcı</th>
                        <th>2. Satıcı</th>
                        <th>3. Satıcı</th>
                    </tr>
                </thead>
                <tbody>
            """
            
            for row in raw_data:
                while len(row) < 16: row.append("")
                barkod, sku = str(row[0]).strip(), str(row[2]).strip()
                if "barkod" in barkod.lower() or "fiyat" in barkod.lower() or "satıcı" in barkod.lower(): continue
                if len("".join(row).strip()) < 3: continue
                    
                hb_kod, alt_grup = str(row[1]).strip() if row[1] else "-", str(row[3]).strip() if row[3] else "-"
                barkod, sku = barkod if barkod else "-", sku if sku else "-"

                t1, t2, t3 = str(row[4]).strip().lower(), str(row[6]).strip().lower(), str(row[8]).strip().lower()
                h1, h2, h3 = str(row[10]).strip().lower(), str(row[12]).strip().lower(), str(row[14]).strip().lower()

                def is_ty(sn): return "trendyol" in sn or "braun shop" in sn
                ty_s_txt = ""
                if is_ty(t1): ty_dot, ty_s_txt = "dot-green", "Sorun Yok"
                elif is_ty(t2) or is_ty(t3): ty_dot, ty_s_txt = "dot-yellow", "Buybox 2. veya 3."
                else: ty_dot, ty_s_txt = "dot-red", "Buybox Kaybedildi"

                def is_hb(sn): return "hepsiburada" in sn or "braun shop" in sn
                hb_s_txt = ""
                if is_hb(h1): hb_dot, hb_s_txt = "dot-green", "Sorun Yok"
                elif is_hb(h2) or is_hb(h3): hb_dot, hb_s_txt = "dot-yellow", "Buybox 2. veya 3."
                else: hb_dot, hb_s_txt = "dot-red", "Buybox Kaybedildi"

                all_export_data.append({"Barkod": barkod, "HB Kod": hb_kod, "SKU": sku, "Alt Grup": alt_grup, "TY Durum": ty_s_txt, "TY S1": str(row[4]), "TY F1": str(row[5]), "TY S2": str(row[6]), "TY F2": str(row[7]), "TY S3": str(row[8]), "TY F3": str(row[9]), "HB Durum": hb_s_txt, "HB S1": str(row[10]), "HB F1": str(row[11]), "HB S2": str(row[12]), "HB F2": str(row[13]), "HB S3": str(row[14]), "HB F3": str(row[15])})
                
                if ty_dot in ["dot-yellow", "dot-red"]:
                    ty_alarm_data.append({"Barkod": barkod, "HB Kod": hb_kod, "SKU": sku, "Alt Grup": alt_grup, "Alarm": ty_s_txt, "S1": str(row[4]), "F1": str(row[5]), "S2": str(row[6]), "F2": str(row[7]), "S3": str(row[8]), "F3": str(row[9])})

                if hb_dot in ["dot-yellow", "dot-red"]:
                    hb_alarm_data.append({"Barkod": barkod, "HB Kod": hb_kod, "SKU": sku, "Alt Grup": alt_grup, "Alarm": hb_s_txt, "S1": str(row[10]), "F1": str(row[11]), "S2": str(row[12]), "F2": str(row[13]), "S3": str(row[14]), "F3": str(row[15])})

                def ps(v): return f"<span class='pill-satici'>{v}</span>" if v and v != "-" and v.lower() != "nan" else "-"
                def pf(f): return f"<span class='pill-fiyat'>{f} TL</span>" if f and f != "-" and f.lower() != "nan" and "TL" not in f else (f"<span class='pill-fiyat'>{f}</span>" if f and f != "-" and f.lower() != "nan" else "-")

                ts1, tf1 = ps(row[4]), pf(row[5])
                ts2, tf2 = ps(row[6]), pf(row[7])
                ts3, tf3 = ps(row[8]), pf(row[9])
                hs1, hf1 = ps(row[10]), pf(row[11])
                hs2, hf2 = ps(row[12]), pf(row[13])
                hs3, hf3 = ps(row[14]), pf(row[15])

                html_table += f"<tr><td rowspan='2' class='p-div'>{barkod}</td><td rowspan='2' class='p-div'>{hb_kod}</td><td rowspan='2' class='bbx-sku p-div'>{sku}</td><td rowspan='2' class='p-div'>{alt_grup}</td><td rowspan='2' class='p-div'><div class='status-dot {ty_dot}'></div></td><td class='n-b-b'>{ts1}</td><td class='n-b-b'>{ts2}</td><td class='n-b-b'>{ts3}</td><td rowspan='2' class='p-div'><div class='status-dot {hb_dot}'></div></td><td class='n-b-b'>{hs1}</td><td class='n-b-b'>{hs2}</td><td class='n-b-b'>{hs3}</td></tr><tr><td class='n-b-t p-div'>{tf1}</td><td class='n-b-t p-div'>{tf2}</td><td class='n-b-t p-div'>{tf3}</td><td class='n-b-t p-div'>{hf1}</td><td class='n-b-t p-div'>{hf2}</td><td class='n-b-t p-div'>{hf3}</td></tr>"
                
            html_table += "</tbody></table></div>"
            
            b_all, b_ty, b_hb = io.BytesIO(), io.BytesIO(), io.BytesIO()
            with pd.ExcelWriter(b_all, engine='openpyxl') as w: pd.DataFrame(all_export_data).to_excel(w, index=False)
            with pd.ExcelWriter(b_ty, engine='openpyxl') as w: pd.DataFrame(ty_alarm_data).to_excel(w, index=False)
            with pd.ExcelWriter(b_hb, engine='openpyxl') as w: pd.DataFrame(hb_alarm_data).to_excel(w, index=False)

            c1, c2, c3 = st.columns([0.30, 0.35, 0.35])
            with c1: st.download_button("📥 Tüm Tabloyu İndir", b_all.getvalue(), "Tum_BBX.xlsx", use_container_width=True)
            with c2: st.download_button("🚨 Trendyol Alarm İndir", b_ty.getvalue(), "TY_Alarm.xlsx", use_container_width=True) if ty_alarm_data else st.success("Trendyol Kusursuz!")
            with c3: st.download_button("🚨 Hepsiburada Alarm İndir", b_hb.getvalue(), "HB_Alarm.xlsx", use_container_width=True) if hb_alarm_data else st.success("Hepsiburada Kusursuz!")

            st.markdown(html_table.replace('\n', ''), unsafe_allow_html=True)
