# -*- coding: utf-8 -*-
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import streamlit as st
import pandas as pd
import numpy as np
import traceback
import datetime
import logging
import warnings
from io import BytesIO

# Logging Konfiguration
logging.basicConfig(level=logging.INFO)
warnings.filterwarnings("ignore", category=RuntimeWarning)

# Import für IRR Berechnung und Finanzmathematik
try:
    import numpy_financial as npf
    IRR_ENABLED = True
except ImportError:
    IRR_ENABLED = False
    npf = None

# Bibliotheken für PDF Export
try:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    PDF_EXPORT_ENABLED = True
except ImportError:
    PDF_EXPORT_ENABLED = False

# --- SETUP & KONFIGURATION ---
try:
    st.set_page_config(layout="wide", page_title="Park 55 | Investitionsrechner")
except st.errors.StreamlitAPIException:
    pass

# --- KONSTANTEN & STANDARDWERTE ---

GREST_SATZ = 0.05
NOTAR_AG_SATZ = 0.015
ERWERBSNEBENKOSTEN_SATZ = GREST_SATZ + NOTAR_AG_SATZ
SOLI_ZUSCHLAG = 0.055
AFA_TYP = "Denkmal"
AFA_ALTBAU_SATZ = 0.02
AFA_DENKMAL_J1_8 = 0.09
AFA_DENKMAL_J9_12 = 0.07
# Erhöht auf 35, um maximale KfW Laufzeiten abzubilden
BERECHNUNGSZEITRAUM = 35 
KFW_LIMIT_PRO_WE_BASIS = 150000
KFW_ZUSCHUSS_261_SATZ = 0.40
KFW_ZUSCHUSS_BB_SATZ = 0.50
KOSTEN_BB_PRO_WE_DEFAULT = 3998

# NEU: KfW Darlehenstypen
KFW_ANNUITAET = "Annuitätendarlehen"
KFW_ENDFAELLIG = "Endfälliges Darlehen"
KFW_DARLEHENSTYPEN = [KFW_ANNUITAET, KFW_ENDFAELLIG]


# Anpassung für das Datum und Steuerjahre
MIN_STEUERJAHR = 2024
try:
    CURRENT_YEAR = datetime.date.today().year
except Exception:
    try:
        import datetime as real_datetime
        CURRENT_YEAR = real_datetime.date.today().year
    except:
        CURRENT_YEAR = 2025 # Sicherer Fallback

STEUERJAHRE_OPTIONEN = list(range(MIN_STEUERJAHR, max(MIN_STEUERJAHR + 1, CURRENT_YEAR + 2)))
STEUERJAHRE_OPTIONEN.sort(reverse=True)
STEUERJAHR_DEFAULT = 2024


KIRCHENSTEUER_MAP = {
    "Keine": 0.0,
    "8% (Wohnsitz BY/BW)": 0.08,
    "9% (Wohnsitz andere BL)": 0.09
}
KIRCHENSTEUER_DEFAULT = "9% (Wohnsitz andere BL)"
STEUER_MODI = ['Basis Einkommen (zvE)', 'Steuersatz']

COLOR_PRIMARY = "#3b6c36"
COLOR_SECONDARY = "#b29d6e"
COLOR_LIGHT_BG = "#e9f5e7"

RL_COLOR_PRIMARY = colors.HexColor(COLOR_PRIMARY) if PDF_EXPORT_ENABLED else None
RL_COLOR_LIGHT_BG = colors.HexColor(COLOR_LIGHT_BG) if PDF_EXPORT_ENABLED else None

PDF_DISCLAIMER_TEXT = (
    "Disclaimer: Diese Berechnung dient Ihrer Orientierung und basiert auf den von Ihnen gemachten Angaben und Annahmen. "
    "Steuerliche Vorteile, KfW-Förderungen, kommunale Zuschüsse und Kostenansätze sind beispielhaft und können abweichen. "
    "Alle Ergebnisse erfolgen ohne Gewähr. Eine rechtliche, steuerliche oder finanzielle Beratung wird ausdrücklich nicht erbracht."
)

# Konstanten für Input Modus
MODE_MANUAL = "Manuelle Eingabe"
MODE_LIST = "Objektauswahl aus Liste"

# Konstanten für Erwerbsmodell
# MODELL_BAUTRAEGER = "Bauträgermodell (Schlüsselfertig)" # ENTFERNT
MODELL_KAUF_GU = "Kauf & GU-Vertrag (Getrennte Verträge)"
# ERWERBSMODELLE = [MODELL_BAUTRAEGER, MODELL_KAUF_GU] # ENTFERNT - Nur noch Kauf & GU


# Defaults
DEFAULTS = {
    # Objektdaten (Defaults für Manuelle Eingabe)
    'objekt_name': '',
    'input_gik_netto': 0,
    'input_sanierungskostenanteil_pct': 80.0,
    'input_grundstuecksanteil_pct': 8.0,
    'input_wohnflaeche': 0.0,
    'input_anzahl_whg': 1,
    'input_kellerflaeche': 0.0,
    'input_anzahl_stellplaetze': 0,

    'input_kommunale_foerderung': 0,

    'input_kfw_darlehen_261_basis': KFW_LIMIT_PRO_WE_BASIS,
    'kosten_baubegleitung_pro_we': KOSTEN_BB_PRO_WE_DEFAULT,

    # Erwerbsmodell Default (JETZT FIX AUF KAUF & GU)
    'erwerbsmodell': MODELL_KAUF_GU,

    # Berechnungsparameter
    'ek_quote_pct': 20.0,
    'bank_zins_pct': 4.20,
    'bank_tilgung_pct': 2.00,
    
    # NEU: KfW Parameter inkl. Typ
    'kfw_darlehenstyp': KFW_ANNUITAET,
    'kfw_zins_pct': 2.92,
    'kfw_gesamtlaufzeit': 30,
    'kfw_tilgungsfreie_jahre': 4,

    'steuer_modus': STEUER_MODI[0],
    'zve': 100000,
    'steuersatz_manuell_pct': 42.0,
    'steuertabelle': 'Grund',
    'kirchensteuer_option': KIRCHENSTEUER_DEFAULT,
    'steuerjahr': STEUERJAHR_DEFAULT,
    'geplanter_verkauf': 10,

    # Parameter & Prognose
    'sicherheitsabschlag_pct': 5.0,
    'mietsteigerung_pa_pct': 2.0,
    'kostensteigerung_pa_pct': 1.5,
    'wertsteigerung_pa_pct': 2.0,
    'nk_pro_wohnung': 30.00,
    'miete_wohnen': 9.50,
    'miete_keller': 4.00,
    'miete_stellplatz': 40.00,
}

# ====================================================================================
# DATENMANAGEMENT & SESSION STATE
# ====================================================================================

# (load_object_data, initialize_session_state, handle_mode_change, handle_anzahl_whg_change, update_state_from_selection bleiben unverändert)

@st.cache_data
def load_object_data():
    """Lädt und bereinigt die Objektdaten aus der CSV-Datei."""

    # HINWEIS: Der Dateiname muss ggf. angepasst werden, falls er sich ändert.
    file_path = "2025-10-25_Park 55_Rohdaten_Denkmalrechner App_final.csv"
    logging.info(f"Versuche, Objektdaten von {file_path} zu laden...")
    try:
        df_raw = pd.read_csv(file_path, delimiter=';', decimal='.', encoding='utf-8')
    except FileNotFoundError:
        logging.warning(f"Objektdaten-Datei nicht gefunden: '{file_path}'.")
        return pd.DataFrame()
    except Exception as e:
        logging.error(f"Allgemeiner Fehler beim Laden der CSV: {e}")
        return pd.DataFrame()

    # --- Datenbereinigung und Transformation ---
    df = pd.DataFrame()

    try:
        df['Objektname'] = df_raw['Strasse'] + " " + df_raw['Hausnummer'].astype(str) + " (" + df_raw['Objekt_ID'] + ")"
    except KeyError as e:
        logging.error(f"CSV-Datei fehlen notwendige Spalten für den Objektnamen: {e}")
        return pd.DataFrame()

    required_cols = {
        'Wohnflaeche_neu_qm': 'Wohnflaeche',
        'Anzahl_Wohneinheiten': 'Anzahl_Whg',
        'Kellerflaeche_qm': 'Kellerflaeche',
        'Anzahl_Stellplaetze': 'Anzahl_Stellplaetze'
    }

    for csv_col, app_col in required_cols.items():
        if csv_col in df_raw.columns:
            df[app_col] = pd.to_numeric(df_raw[csv_col], errors='coerce').fillna(0)
        else:
            df[app_col] = 0

    try:
        df['Wohnflaeche'] = df['Wohnflaeche'].astype(float)
        df['Kellerflaeche'] = df['Kellerflaeche'].astype(float)
        df['Anzahl_Whg'] = df['Anzahl_Whg'].astype(int)
        df['Anzahl_Stellplaetze'] = df['Anzahl_Stellplaetze'].astype(int)
    except Exception as e:
        logging.error(f"Fehler bei der Konvertierung der Objektdaten: {e}")
        return pd.DataFrame()

    df['Anzahl_Whg'] = df['Anzahl_Whg'].apply(lambda x: max(1, x))
    df = df.dropna(subset=['Objektname'])

    logging.info(f"Erfolgreich {len(df)} Objekte geladen.")
    return df


def initialize_session_state():
    """Initialisiert den Streamlit Session State mit Default-Werten."""
    if 'initialized' not in st.session_state:
        logging.info("Initialisiere Session State...")
        for key, value in DEFAULTS.items():
            if key not in st.session_state:
                st.session_state[key] = value

        st.session_state['input_altbauanteil_pct'] = 100.0 - DEFAULTS['input_sanierungskostenanteil_pct'] - DEFAULTS['input_grundstuecksanteil_pct']

        st.session_state['input_mode'] = MODE_MANUAL
        st.session_state['selected_object'] = None
        st.session_state['initialized'] = True

# Callback für Moduswechsel (Radio Button)
def handle_mode_change():
    """Wird aufgerufen, wenn der Radio Button (Manuell vs Liste) geändert wird."""
    if st.session_state.input_mode == MODE_MANUAL:
        st.session_state.selected_object = None
        update_state_from_selection()
    elif st.session_state.input_mode == MODE_LIST:
        df = load_object_data()
        if not df.empty:
            if st.session_state.selected_object is None or st.session_state.selected_object not in df['Objektname'].values:
                st.session_state.selected_object = df['Objektname'].iloc[0]
            update_state_from_selection()

# Callback für Änderung der Anzahl Wohnungen (Manuelle Eingabe)
def handle_anzahl_whg_change():
    """Aktualisiert das maximale KfW-Darlehen und setzt den Default-Wert darauf, wenn die Anzahl WE manuell geändert wird."""
    if st.session_state.get('input_mode') == MODE_MANUAL:
        anzahl_whg = st.session_state.get('input_anzahl_whg', 1)
        max_kfw_darlehen_basis = anzahl_whg * KFW_LIMIT_PRO_WE_BASIS
        st.session_state.input_kfw_darlehen_261_basis = int(max_kfw_darlehen_basis)


# Angepasster Callback für Objektauswahl
def update_state_from_selection():
    """
    Callback-Funktion: Aktualisiert den Session State bei Objektauswahl oder Moduswechsel.
    """
    selected_name = st.session_state.get('selected_object')
    df = load_object_data()

    if selected_name is None:
        # Setze auf globale Defaults zurück
        target_data = {
            'Objektname': DEFAULTS['objekt_name'],
            'Wohnflaeche': DEFAULTS['input_wohnflaeche'],
            'Anzahl_Whg': DEFAULTS['input_anzahl_whg'],
            'Kellerflaeche': DEFAULTS['input_kellerflaeche'],
            'Anzahl_Stellplaetze': DEFAULTS['input_anzahl_stellplaetze']
        }
        st.session_state.input_gik_netto = DEFAULTS['input_gik_netto']
        st.session_state.input_sanierungskostenanteil_pct = DEFAULTS['input_sanierungskostenanteil_pct']
        st.session_state.input_grundstuecksanteil_pct = DEFAULTS['input_grundstuecksanteil_pct']
        st.session_state.input_kommunale_foerderung = DEFAULTS['input_kommunale_foerderung']

    elif not df.empty and selected_name in df['Objektname'].values:
        target_data = df[df['Objektname'] == selected_name].iloc[0].to_dict()
    else:
        return

    # 1. Aktualisiere Basisdaten im State
    st.session_state.objekt_name = target_data['Objektname']
    st.session_state.input_wohnflaeche = float(target_data['Wohnflaeche'])
    st.session_state.input_anzahl_whg = int(target_data['Anzahl_Whg'])
    st.session_state.input_kellerflaeche = float(target_data['Kellerflaeche'])
    st.session_state.input_anzahl_stellplaetze = int(target_data['Anzahl_Stellplaetze'])

    # 2. Berechne und aktualisiere abgeleitete Werte (KfW, BB)
    anzahl_whg = st.session_state.input_anzahl_whg

    kfw_basis = anzahl_whg * KFW_LIMIT_PRO_WE_BASIS
    st.session_state.input_kfw_darlehen_261_basis = kfw_basis

    st.session_state.kosten_baubegleitung_pro_we = KOSTEN_BB_PRO_WE_DEFAULT

# ====================================================================================
# HILFSFUNKTIONEN & FORMATIERUNG
# ====================================================================================

# (format_euro, format_percent, format_aligned_line, validate_gik_anteile, set_custom_style bleiben unverändert)

def format_euro(value, decimals=2):
    try:
        if pd.isna(value): return "-"
        value = float(value)
        if decimals == 0:
            return f"{int(round(value, 0)):,} €".replace(',', '.')
        else:
            return f"{value:,.{decimals}f} €".replace(',', 'X').replace('.', ',').replace('X', '.')
    except (ValueError, TypeError):
        return "0,00 €" if decimals==2 else "0 €"

def format_percent(value, decimals=2):
     try:
        if pd.isna(value): return "N/A"
        if value == float('inf'): return "∞ %" # Handle infinite RoE
        value = float(value)
        if decimals == 0:
            return f"{int(round(value*100, 0))}%"
        return f"{value*100:,.{decimals}f} %".replace('.', ',')
     except (ValueError, TypeError):
        return "0,00 %"

def format_aligned_line(label, value_str, label_width=28):
    return f"{label:<{label_width}}{value_str:>15}"


# --- VALIDIERUNGSLOGIK ---

def validate_gik_anteile(sanierung_pct, grundstueck_pct):
    """Prüft, ob die GIK-Anteile (in Prozent) plausibel sind."""
    try:
        sanierung_pct = float(sanierung_pct)
        grundstueck_pct = float(grundstueck_pct)
    except (ValueError, TypeError):
        return False, 0, "error", "Ungültige numerische Eingabe."

    summe_anteile_pct = sanierung_pct + grundstueck_pct

    if summe_anteile_pct > 100.000001:
        msg = f"Die Summe übersteigt 100% (Aktuell: {summe_anteile_pct:.2f}%)."
        return False, 0, "error", msg

    altbauanteil_pct = 100.0 - summe_anteile_pct
    st.session_state['input_altbauanteil_pct'] = altbauanteil_pct

    if altbauanteil_pct < 5.0 and altbauanteil_pct >= 0 and st.session_state.get('input_gik_netto', 0) > 0:
        msg = f"Hinweis: Anteil Altbausubstanz ({altbauanteil_pct:.2f}%) ist sehr gering."
        return True, altbauanteil_pct, "warning", msg

    return True, altbauanteil_pct, "success", "Plausibel."

# --- DESIGN & STYLING ---
def set_custom_style():
    # JavaScript Snippet für den "Keyboard Arrow Scroll Fix"
    keyboard_arrow_scroll_fix = """
    <script>
    const streamlitDoc = window.parent.document;

    function handleNumberInputKeydown(e) {
        if (e.target.tagName === 'INPUT' && e.target.type === 'number') {
            if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
                e.preventDefault();
                try {
                    if (e.key === 'ArrowUp') {
                        e.target.stepUp();
                    } else {
                        e.target.stepDown();
                    }
                    e.target.dispatchEvent(new Event('change', { bubbles: true }));
                } catch (error) {
                    console.log("Could not step value:", error);
                }
            }
        }
    }

    // Attach listener only once to prevent duplicate execution on rerun
    if (typeof window.parent.keyboardFixAttached === 'undefined' || !window.parent.keyboardFixAttached) {
        streamlitDoc.addEventListener('keydown', handleNumberInputKeydown, true);
        window.parent.keyboardFixAttached = true;
    }
    </script>
    """

    # CSS Styling
    st.markdown(f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=Lato:wght@400;700&display=swap');

        /* Basis Styling */
        html, body {{ font-family: 'Lato', sans-serif; }}

        h1, h2, h3, h4, h5, h6 {{ font-family: 'Cinzel', serif; color: {COLOR_PRIMARY}; }}

        /* Input Container Styling */
        .input-container {{
            background-color: {COLOR_LIGHT_BG};
            padding: 25px;
            border-radius: 15px;
            margin-bottom: 30px;
            border: 1px solid {COLOR_PRIMARY};
        }}

        /* Tabs Styling */
        .stTabs [data-baseweb="tab"][aria-selected="true"] {{
                background-color: {COLOR_PRIMARY};
                color: white;
        }}
        .stTabs [data-baseweb="tab"][aria-selected="true"] p {{
            color: white !important;
        }}

        /* KPI Container */
        .prominent-kpi-container {{
            background-color: {COLOR_PRIMARY};
            border-radius: 10px;
            padding: 20px;
            color: white;
            text-align: center;
            margin-bottom: 20px;
        }}
        .prominent-kpi-container .stMetric > label {{ color: {COLOR_SECONDARY}; font-weight: 700; }}
        .prominent-kpi-container .stMetric > div {{ color: white; }}

        /* Calculation Breakdown Styling */
        .calculation-breakdown {{
            background-color: #fafafa;
            padding: 15px;
            border-radius: 10px;
            border: 1px solid #e6e6e6;
            margin-bottom: 10px;
            font-family: monospace;
            white-space: pre;
            text-align: left;
        }}

        .breakdown-intermediate {{
                font-weight: bold;
                border-top: 1px solid {COLOR_SECONDARY};
                margin-top: 5px;
                padding-top: 5px;
        }}
        </style>
        {keyboard_arrow_scroll_fix}
        """, unsafe_allow_html=True)

# ====================================================================================
# INPUT WIDGETS (Layout im Hauptbereich)
# ====================================================================================

def display_inputs():
    """
    Zeigt alle Input-Widgets im Hauptbereich in einem Spaltenlayout an.
    """

    # Wrapper für Styling
    st.markdown('<div class="input-container">', unsafe_allow_html=True)

    # --- Modusauswahl ---
    
    df_objects = load_object_data()
    if df_objects.empty:
        if st.session_state.input_mode != MODE_MANUAL:
             st.session_state.input_mode = MODE_MANUAL
             handle_mode_change()
        st.warning("Objektdatenliste (CSV) konnte nicht geladen werden oder war leer. Nur manuelle Eingabe möglich.")
        input_options = [MODE_MANUAL]
    else:
        input_options = [MODE_MANUAL, MODE_LIST]

    st.radio(
        "Wählen Sie den Eingabemodus:",
        options=input_options,
        key='input_mode',
        horizontal=True,
        on_change=handle_mode_change
    )

    # Erwerbsmodell Auswahl (ENTFERNT)
    st.markdown("---")
    # st.radio(
    #     "Wählen Sie das Erwerbsmodell (Basis für Grunderwerbsteuer/Notar):",
    #     options=ERWERBSMODELLE, # <-- Diese Liste existiert nicht mehr
    #     key='erwerbsmodell',
    #     horizontal=True
    # )
    
    # Statischer Text, da Bauträger entfernt wurde
    st.subheader(f"Erwerbsmodell: {MODELL_KAUF_GU}")
    st.info(f"Kauf & GU: Die KNK ({format_percent(ERWERBSNEBENKOSTEN_SATZ)}) werden nur auf den Bestand (GIK exklusive Sanierungskosten) berechnet. Die korrekte Aufteilung der GIK (siehe Spalte 1) ist hierfür entscheidend.")
    st.markdown("---")


    # Layout: 3 Spalten für die Eingabeblöcke
    col1, col2, col3 = st.columns(3)

    gik_is_valid = True
    kfw_is_valid = True

    # --- Spalte 1: Objektauswahl, GIK, Flächen ---
    with col1:
        st.subheader("1. Objekt & Investition")

        # 1.1 Objektauswahl
        if st.session_state.input_mode == MODE_LIST:
            if not df_objects.empty:
                object_options = df_objects['Objektname'].tolist()
                st.selectbox(
                    "Objekt aus Liste wählen:",
                    options=object_options,
                    key='selected_object',
                    on_change=update_state_from_selection
                )

        st.text_input("Objektname / Beschreibung", key='objekt_name', placeholder="Geben Sie einen Namen oder eine Beschreibung ein...")
        st.number_input("Gesamtinvestitionskosten (GIK) Netto (€)", min_value=0, step=10000, key='input_gik_netto')

        # 1.2 GIK Aufteilung
        st.markdown("**Aufteilung GIK (für AfA & KNK-Basis):**")
        st.number_input("Sanierungskostenanteil (%)", min_value=0.0, max_value=100.0, step=1.0, format="%.0f", key='input_sanierungskostenanteil_pct')
        st.number_input("Grundstücksanteil (%)", min_value=0.0, max_value=100.0, step=1.0, format="%.0f", key='input_grundstuecksanteil_pct')

        # Validierungslogik
        gik_is_valid, altbauanteil_pct, msg_type, msg = validate_gik_anteile(
            st.session_state.input_sanierungskostenanteil_pct,
            st.session_state.input_grundstuecksanteil_pct
        )

        if msg_type == "error":
            st.error(msg)
        elif msg_type == "warning":
            st.warning(msg)

        st.number_input("Altbausubstanz (berechnet, %)", value=altbauanteil_pct, disabled=True, format="%.1f")

        # 1.3 Flächen & Einheiten
        st.markdown("**Flächen & Einheiten:**")
        c_f1, c_f2 = st.columns(2)
        c_f1.number_input("Wohnfläche (m²)", min_value=0.0, step=1.0, key='input_wohnflaeche')
        c_f2.number_input("Anzahl Wohnungen", min_value=1, step=1, key='input_anzahl_whg', on_change=handle_anzahl_whg_change)
        c_f1.number_input("Kellerfläche (m²)", min_value=0.0, step=1.0, key='input_kellerflaeche')
        c_f2.number_input("Anzahl Stellplätze", min_value=0, step=1, key='input_anzahl_stellplaetze')


    # --- Spalte 2: KfW-Förderung, Finanzierung, Steuern ---
    with col2:
        st.subheader("2. Finanzierung & Steuern")

        # Kommunale Fördermittel
        st.markdown("**Fördermittel (Zuschüsse):**")
        st.number_input("Kommunale Fördermittel (€)", min_value=0, step=1000, key='input_kommunale_foerderung')
        st.caption("Wird als Zufluss (Jahr 1) gewertet und mindert die AfA-Basis Sanierung.")


        # 2.1 KfW-Förderung
        st.markdown("**KfW-Förderung (Programm 261):**")
        st.number_input("Kosten Baubegleitung (pro WE, €)", min_value=0, max_value=4000, step=1, format="%d", key='kosten_baubegleitung_pro_we')

        # Berechnung des Max-Limits
        anzahl_whg = int(st.session_state.get('input_anzahl_whg', 1))
        max_kfw_darlehen_basis = anzahl_whg * KFW_LIMIT_PRO_WE_BASIS

        # Robustheits-Fix
        current_kfw_value = st.session_state.get('input_kfw_darlehen_261_basis', DEFAULTS['input_kfw_darlehen_261_basis'])
        if float(current_kfw_value) > max_kfw_darlehen_basis:
            st.session_state.input_kfw_darlehen_261_basis = int(max_kfw_darlehen_basis)
            current_kfw_value = max_kfw_darlehen_basis

        st.number_input(f"Darlehen Basis (Max: {format_euro(int(max_kfw_darlehen_basis),0)})", min_value=0, max_value=int(max_kfw_darlehen_basis), step=1000, key='input_kfw_darlehen_261_basis')

        # Info Gesamtdarlehen
        current_kfw_value_from_input = st.session_state.input_kfw_darlehen_261_basis
        kosten_bb_pro_we = float(st.session_state.get('kosten_baubegleitung_pro_we', 0))
        kfw_gesamt = current_kfw_value_from_input + (kosten_bb_pro_we * anzahl_whg)
        st.caption(f"Gesamt KfW-Darlehen: {format_euro(kfw_gesamt, 0)}")

        # 2.2 Finanzierung
        st.markdown("**Finanzierungsstruktur:**")
        st.number_input("Eigenkapitalquote (%)", min_value=0.0, max_value=100.0, step=1.0, format="%.0f", key='ek_quote_pct')

        c_d1, c_d2 = st.columns(2)
        c_d1.markdown("**Bankdarlehen:**")
        c_d1.number_input("Zinssatz Bank (%)", min_value=0.0, step=0.01, format="%.2f", key='bank_zins_pct')
        c_d1.number_input("Tilgung Bank (%)", min_value=0.0, step=0.01, format="%.2f", key='bank_tilgung_pct')

        # NEU: KfW Darlehenstyp und dynamische Inputs
        c_d2.markdown("**KfW-Darlehen:**")
        
        # NEU: Auswahl Darlehenstyp
        c_d2.radio("Darlehenstyp", KFW_DARLEHENSTYPEN, key='kfw_darlehenstyp', horizontal=True)

        c_d2.number_input("Zinssatz KfW (%)", min_value=0.0, step=0.01, format="%.2f", key='kfw_zins_pct')

        # Laufzeit Logik (NEU: Dynamisch basierend auf Typ)
        is_annuitaet = st.session_state.kfw_darlehenstyp == KFW_ANNUITAET
        
        gesamtlaufzeit = st.session_state.kfw_gesamtlaufzeit
        
        # Nur relevant für Annuität
        if is_annuitaet:
            max_tilgungsfrei = max(0, gesamtlaufzeit - 1)
            if st.session_state.kfw_tilgungsfreie_jahre > max_tilgungsfrei:
                st.session_state.kfw_tilgungsfreie_jahre = max_tilgungsfrei
        else:
            # Bei endfällig sicherstellen, dass der Wert intern 0 ist (für Robustheit, auch wenn nicht genutzt)
            st.session_state.kfw_tilgungsfreie_jahre = 0
            max_tilgungsfrei = 0

        # NEU: Dynamisches Label für Laufzeit
        laufzeit_label = "Gesamtlaufzeit (J.)" if is_annuitaet else "Laufzeit bis Fälligkeit (J.)"
        c_d2.number_input(laufzeit_label, min_value=1, max_value=35, step=1, key='kfw_gesamtlaufzeit')
        
        # NEU: Tilgungsfrei nur anzeigen, wenn Annuität
        if is_annuitaet:
            c_d2.number_input("Tilgungsfrei (J.)", min_value=0, max_value=max_tilgungsfrei, step=1, key='kfw_tilgungsfreie_jahre')


        # 2.3 Steuerliche Annahmen
        st.markdown("**Steuerliche Annahmen:**")
        st.radio("Steuersatz-Ermittlung", STEUER_MODI, key='steuer_modus', horizontal=True)

        if st.session_state.steuer_modus == STEUER_MODI[0]:
            st.number_input("Zu versteuerndes Einkommen (zvE)", min_value=0, step=10000, key='zve')
            c_s1, c_s2 = st.columns(2)
            c_s1.radio("Tabelle", ['Grund', 'Splitting'], key='steuertabelle')
            
            try:
                default_index = STEUERJAHRE_OPTIONEN.index(st.session_state.steuerjahr)
            except ValueError:
                default_index = 0
                st.session_state.steuerjahr = STEUERJAHRE_OPTIONEN[0]

            c_s2.selectbox("Steuerjahr", STEUERJAHRE_OPTIONEN, index=default_index, key='steuerjahr')
        else:
            st.number_input("Grenzsteuersatz (%)", min_value=0.0, max_value=45.0, step=1.0, format="%.0f", key='steuersatz_manuell_pct')

        st.selectbox("Kirchensteuer", list(KIRCHENSTEUER_MAP.keys()), key='kirchensteuer_option')


    # --- Spalte 3: Parameter & Prognose (Slider) ---
    with col3:
        st.subheader("3. Parameter & Prognose")
        st.number_input("Geplanter Verkauf nach (Jahren)", min_value=10, step=1, key='geplanter_verkauf')

        st.markdown("**Mieten (Startwerte):**")
        st.slider("Miete Wohnen (€/m²)", min_value=8.0, max_value=12.50, step=0.1, format="%.2f €", key='miete_wohnen')
        st.slider("Miete Keller (€/m²)", min_value=0.0, max_value=5.00, step=0.1, format="%.2f €", key='miete_keller')
        st.slider("Miete Stellplatz (€/Stk.)", min_value=20.0, max_value=60.0, step=5.0, format="%.0f €", key='miete_stellplatz')

        st.markdown("**Entwicklung (p.a. %):**")
        st.slider("Mietsteigerung (%)", min_value=0.0, max_value=5.0, step=0.5, format="%.1f%%", key='mietsteigerung_pa_pct')
        st.slider("Wertsteigerung (%)", min_value=0.0, max_value=10.0, step=0.5, format="%.1f%%", key='wertsteigerung_pa_pct')

        st.markdown("**Kosten:**")
        st.slider("Verwaltung (€/Whg./Monat)", min_value=0.0, max_value=40.0, step=0.10, format="%.2f €", key='nk_pro_wohnung')
        st.slider("Kostensteigerung (%)", min_value=0.0, max_value=5.0, step=0.5, format="%.1f%%", key='kostensteigerung_pa_pct')

        st.slider("Sicherheitsabschlag Miete (%)", min_value=0.0, max_value=20.0, step=1.0, format="%.0f%%", key='sicherheitsabschlag_pct')

    st.markdown('</div>', unsafe_allow_html=True) # Schließe Wrapper

    return gik_is_valid, kfw_is_valid

# ====================================================================================
# BERECHNUNGSLOGIK (Kern der Anwendung)
# ====================================================================================

# (run_calculations, convert_inputs_to_params, calculate_revenues_costs bleiben unverändert)

def run_calculations(inputs_pct):
    """Führt die gesamte Immobilienberechnung durch."""
    results = {}

    # 1. Konvertiere Prozent-Inputs in Dezimalzahlen für die Berechnung
    params = convert_inputs_to_params(inputs_pct)

    # 2. Investitionsrechnung
    results = calculate_investment(params, results)

    # 3. Mieten und Kosten
    results = calculate_revenues_costs(params, results)

    # 4. Steuerberechnung (Grenzsteuersatz)
    if params['steuer_modus'] == 'Steuersatz':
        results['grenzsteuersatz_netto'] = params['steuersatz_manuell']
    else:
        # Platzhalter 42%
        results['grenzsteuersatz_netto'] = 0.42

    kirchensteuer_satz = KIRCHENSTEUER_MAP.get(params['kirchensteuer_option'], 0.0)
    results['grenzsteuersatz_brutto'] = results['grenzsteuersatz_netto'] * (1 + SOLI_ZUSCHLAG + kirchensteuer_satz)

    # 5. Zeitreihenentwicklung
    results = calculate_projection(params, results)

    # 6. KPIs
    results = calculate_kpis(params, results)

    return results, params

def convert_inputs_to_params(inputs_pct):
    """Konvertiert die Prozent-Inputs (_pct) aus dem Session State in Dezimalzahlen."""
    params = dict(inputs_pct)

    pct_keys = [
        'input_sanierungskostenanteil_pct', 'input_grundstuecksanteil_pct', 'input_altbauanteil_pct',
        'ek_quote_pct', 'bank_zins_pct', 'bank_tilgung_pct', 'kfw_zins_pct',
        'steuersatz_manuell_pct', 'sicherheitsabschlag_pct',
        'mietsteigerung_pa_pct', 'kostensteigerung_pa_pct', 'wertsteigerung_pa_pct'
    ]

    for key in pct_keys:
        if key in params:
            new_key = key.replace('_pct', '')
            try:
                value = params[key]
                if value is None or value == '':
                    params[new_key] = 0.0
                else:
                    params[new_key] = float(value) / 100.0
            except (ValueError, TypeError):
                params[new_key] = 0.0

    return params


def calculate_investment(params, results):
    """Berechnet GIK, Nebenkosten, AfA-Grundlagen und Finanzierungsstruktur."""

    # 1.0 Kommunale Fördermittel einlesen
    kommunale_foerderung = float(params.get('input_kommunale_foerderung', 0))
    results['kommunale_foerderung'] = kommunale_foerderung

    # 1.1 GIK und Nebenkosten
    gik_netto = float(params['input_gik_netto'])
    # erwerbsmodell = params.get('erwerbsmodell', MODELL_KAUF_GU) # Fallback geändert
    
    # Da MODELL_BAUTRAEGER entfernt wurde, gilt nur noch die Logik für KAUF_GU
    
    sanierungskostenanteil = params.get('input_sanierungskostenanteil', 0.0)
    bemessungsgrundlage_knk = gik_netto * (1.0 - sanierungskostenanteil)
    results['knk_berechnungsbasis_info'] = f"Basis KNK (Kauf & GU): {format_euro(bemessungsgrundlage_knk, 0)} (GIK exkl. Sanierung)"

    # Der "else"-Block für Bauträger wurde entfernt.

    erwerbsnebenkosten = bemessungsgrundlage_knk * ERWERBSNEBENKOSTEN_SATZ
    gik_brutto = gik_netto + erwerbsnebenkosten

    results['gik_netto'] = gik_netto
    results['erwerbsnebenkosten'] = erwerbsnebenkosten
    results['gik_brutto'] = gik_brutto

    # 1.2 Baubegleitung (Kosten und Zuschuss)
    kosten_bb_pro_we = float(params['kosten_baubegleitung_pro_we'])
    anzahl_whg = int(params['input_anzahl_whg'])

    kosten_baubegleitung_gesamt = kosten_bb_pro_we * anzahl_whg
    zuschuss_baubegleitung = kosten_baubegleitung_gesamt * KFW_ZUSCHUSS_BB_SATZ
    aktivierung_baubegleitung = kosten_baubegleitung_gesamt - zuschuss_baubegleitung

    results['kosten_baubegleitung_gesamt'] = kosten_baubegleitung_gesamt
    results['zuschuss_baubegleitung'] = zuschuss_baubegleitung
    results['aktivierung_baubegleitung'] = aktivierung_baubegleitung

    # Investitionssumme Gesamt
    investitionssumme_gesamt = gik_brutto + kosten_baubegleitung_gesamt
    results['investitionssumme_gesamt'] = investitionssumme_gesamt

    # 1.3 AfA-Bemessungsgrundlagen
    wert_grundstueck = gik_netto * params['input_grundstuecksanteil']
    wert_sanierung = gik_netto * params['input_sanierungskostenanteil']
    wert_altbau = gik_netto * params['input_altbauanteil']

    # Logik für AfA-Basis Aufteilung
    # Der "if erwerbsmodell == MODELL_KAUF_GU:" Check wurde entfernt, da dies die einzige verbleibende Logik ist.
    
    wert_bestand_summe = wert_grundstueck + wert_altbau
    if wert_bestand_summe > 0:
        anteil_grundstueck_am_bestand = wert_grundstueck / wert_bestand_summe
        anteil_altbau_am_bestand = wert_altbau / wert_bestand_summe
    else:
        anteil_grundstueck_am_bestand = 0
        anteil_altbau_am_bestand = 0

    knk_auf_grundstueck = erwerbsnebenkosten * anteil_grundstueck_am_bestand
    knk_auf_altbau = erwerbsnebenkosten * anteil_altbau_am_bestand

    afa_basis_grundstueck = wert_grundstueck + knk_auf_grundstueck
    afa_basis_altbau = wert_altbau + knk_auf_altbau
    afa_basis_sanierung_vor_foerderung = wert_sanierung + aktivierung_baubegleitung

    # Der "else:" Block (Bauträgermodell) wurde entfernt.

    # Kommunale Förderung von der AfA-Basis Sanierung abziehen
    afa_basis_sanierung = max(0, afa_basis_sanierung_vor_foerderung - kommunale_foerderung)
    
    if afa_basis_sanierung_vor_foerderung < kommunale_foerderung and afa_basis_sanierung_vor_foerderung > 0:
         results['afa_hinweis'] = f"Hinweis: Die kommunale Förderung übersteigt die Basis der Sanierungskosten. Die AfA-Basis Sanierung wurde auf 0 € gesetzt."

    
    results['afa_basis_sanierung_vor_foerderung'] = afa_basis_sanierung_vor_foerderung
    results['afa_basis_grundstueck'] = afa_basis_grundstueck
    results['afa_basis_sanierung'] = afa_basis_sanierung
    results['afa_basis_altbau'] = afa_basis_altbau

    results['afa_basis_summe_check'] = afa_basis_grundstueck + afa_basis_sanierung + afa_basis_altbau

    # 1.4 Finanzierung
    if investitionssumme_gesamt == 0:
        eigenkapital_bedarf = 0
        fremdkapital_bedarf = 0
    else:
        eigenkapital_bedarf = investitionssumme_gesamt * params['ek_quote']
        fremdkapital_bedarf = investitionssumme_gesamt - eigenkapital_bedarf

    # KfW Logik
    kfw_darlehen_basis = float(params['input_kfw_darlehen_261_basis'])
    kfw_darlehen_gesamt = kfw_darlehen_basis + kosten_baubegleitung_gesamt

    # Validierung gegen Fremdkapitalbedarf
    if kfw_darlehen_gesamt > fremdkapital_bedarf and fremdkapital_bedarf > 0:
        reduktion = kfw_darlehen_gesamt - fremdkapital_bedarf
        kfw_darlehen_gesamt = fremdkapital_bedarf

        if kfw_darlehen_basis >= reduktion:
            kfw_darlehen_basis -= reduktion
        else:
            kfw_darlehen_basis = 0

        results['finanzierung_hinweis'] = "Hinweis: Das berechnete KfW-Darlehen (Basis+BB) war höher als der Fremdkapitalbedarf. Es wurde für die Berechnung auf den maximal benötigten Betrag reduziert."

    kfw_tilgungszuschuss = kfw_darlehen_basis * KFW_ZUSCHUSS_261_SATZ
    bankdarlehen = fremdkapital_bedarf - kfw_darlehen_gesamt

    results['eigenkapital_bedarf'] = eigenkapital_bedarf
    results['fremdkapital_bedarf'] = fremdkapital_bedarf
    results['kfw_darlehen'] = kfw_darlehen_gesamt
    results['kfw_darlehen_basis'] = kfw_darlehen_basis
    results['kfw_tilgungszuschuss'] = kfw_tilgungszuschuss
    results['bankdarlehen'] = bankdarlehen

    # Gesamtzuschuss (KfW Tilgungszuschuss + KfW BB-Zuschuss + Kommunale Förderung)
    results['gesamtzuschuss'] = kfw_tilgungszuschuss + zuschuss_baubegleitung + kommunale_foerderung
    results['effektives_eigenkapital'] = max(0, eigenkapital_bedarf - results['gesamtzuschuss'])

    return results

def calculate_revenues_costs(params, results):
    """Berechnet die Startwerte für Mieten und Kosten (Jahr 1)."""
    # 2.1 Mieten
    miete_wohnen_mtl = float(params['input_wohnflaeche']) * float(params['miete_wohnen'])
    miete_keller_mtl = float(params['input_kellerflaeche']) * float(params['miete_keller'])
    miete_stellplatz_mtl = int(params['input_anzahl_stellplaetze']) * float(params['miete_stellplatz'])

    jahreskaltmiete = (miete_wohnen_mtl + miete_keller_mtl + miete_stellplatz_mtl) * 12

    results['miete_wohnen_mtl'] = miete_wohnen_mtl
    results['miete_keller_mtl'] = miete_keller_mtl
    results['miete_stellplatz_mtl'] = miete_stellplatz_mtl
    results['jahreskaltmiete'] = jahreskaltmiete

    # 2.2 Kosten & Abschlag
    jahresverwaltungskosten = float(params['nk_pro_wohnung']) * int(params['input_anzahl_whg']) * 12
    sicherheitsabschlag_absolut = jahreskaltmiete * params['sicherheitsabschlag']

    results['jahresverwaltungskosten'] = jahresverwaltungskosten
    results['sicherheitsabschlag_absolut'] = sicherheitsabschlag_absolut

    # 2.3 Netto-Einnahmen
    jahreskaltmiete_netto = jahreskaltmiete - sicherheitsabschlag_absolut
    betriebskosten_gesamt = jahresverwaltungskosten
    einnahmen_ueberschuss_vor_finanz_steuer = jahreskaltmiete_netto - betriebskosten_gesamt

    results['jahreskaltmiete_netto'] = jahreskaltmiete_netto
    results['betriebskosten_gesamt'] = betriebskosten_gesamt
    results['einnahmen_ueberschuss_vor_finanz_steuer'] = einnahmen_ueberschuss_vor_finanz_steuer

    return results

# ====================================================================================
# DETAILLIERTE PROJEKTIONSRECHNUNG (Finanzierung, Steuern, Cashflow)
# ====================================================================================

def calculate_projection(params, results):
    """Führt die detaillierte Projektion über den Berechnungszeitraum durch."""

    if results['investitionssumme_gesamt'] == 0:
        results['projection_df'] = pd.DataFrame()
        return results

    jahre = range(1, BERECHNUNGSZEITRAUM + 1)
    df = pd.DataFrame(index=jahre)
    df.index.name = 'Jahr'

    # 1. Einnahmen, Kosten und Wertentwicklung
    mietsteigerung = params['mietsteigerung_pa']
    kostensteigerung = params['kostensteigerung_pa']
    wertsteigerung = params['wertsteigerung_pa']

    miet_faktoren = (1 + mietsteigerung) ** np.arange(BERECHNUNGSZEITRAUM)
    kosten_faktoren = (1 + kostensteigerung) ** np.arange(BERECHNUNGSZEITRAUM)
    wert_faktoren = (1 + wertsteigerung) ** np.arange(1, BERECHNUNGSZEITRAUM + 1)

    df['Mieteinnahmen (Netto)'] = results['jahreskaltmiete_netto'] * miet_faktoren
    df['Betriebskosten'] = results['jahresverwaltungskosten'] * kosten_faktoren
    df['Einnahmenüberschuss'] = df['Mieteinnahmen (Netto)'] - df['Betriebskosten']
    
    df['Immobilienwert'] = results['gik_brutto'] * wert_faktoren

    # 2. Finanzierung (NEU: Inkl. Endfälliges Darlehen)
    df = calculate_financing_schedule(df, params, results)

    # 3. Abschreibung (AfA)
    df = calculate_depreciation_schedule(df, results)

    # 4. Steuerberechnung
    df['Steuerliches Ergebnis (V+V)'] = (
        df['Einnahmenüberschuss']
        - df['Zinsen Gesamt']
        - df['AfA Gesamt']
    )

    steuersatz = results['grenzsteuersatz_brutto']
    df['Steuerersparnis'] = -df['Steuerliches Ergebnis (V+V)'] * steuersatz

    # 5. Cashflow-Synthese
    # Annuität Gesamt beinhaltet hier den gesamten Kapitaldienst (Zins + Tilgung, auch die endfällige Tilgung)
    df['Cashflow vor Steuer'] = df['Einnahmenüberschuss'] - df['Annuität Gesamt']
    
    # Sonderzufluss (Kommunale Förderung) in Jahr 1
    df['Sonderzufluss'] = 0.0
    kommunale_foerderung = results.get('kommunale_foerderung', 0)
    if kommunale_foerderung > 0 and 1 in df.index:
        df.loc[1, 'Sonderzufluss'] = kommunale_foerderung

    df['Cashflow nach Steuer'] = df['Cashflow vor Steuer'] + df['Steuerersparnis'] + df['Sonderzufluss']

    # 6. Nettovermögen
    df['Nettovermögen'] = df['Immobilienwert'] - df['Restschuld Gesamt']

    results['projection_df'] = df
    return results


# NEU: Angepasste Funktion für Finanzierungspläne
def calculate_financing_schedule(df, params, results):
    """Berechnet die Tilgungspläne für Bank- und KfW-Darlehen (inkl. Endfällig)."""
    
    # --- Bankdarlehen (Standard Annuität) ---
    # (Unverändert)
    darlehen_bank = results['bankdarlehen']
    zins_bank = params['bank_zins']
    tilgung_bank = params['bank_tilgung']

    if darlehen_bank > 0 and (zins_bank + tilgung_bank) > 0: