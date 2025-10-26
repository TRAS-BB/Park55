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
MODELL_BAUTRAEGER = "Bauträgermodell (Schlüsselfertig)"
MODELL_KAUF_GU = "Kauf & GU-Vertrag (Getrennte Verträge)"
ERWERBSMODELLE = [MODELL_BAUTRAEGER, MODELL_KAUF_GU]


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

    # Erwerbsmodell Default
    'erwerbsmodell': MODELL_BAUTRAEGER,

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

    # Erwerbsmodell Auswahl
    st.markdown("---")
    st.radio(
        "Wählen Sie das Erwerbsmodell (Basis für Grunderwerbsteuer/Notar):",
        options=ERWERBSMODELLE,
        key='erwerbsmodell',
        horizontal=True
    )
    if st.session_state.erwerbsmodell == MODELL_BAUTRAEGER:
        st.info(f"Bauträgermodell: Die KNK ({format_percent(ERWERBSNEBENKOSTEN_SATZ)}) werden auf die gesamten GIK (Kaufpreis + Sanierung) berechnet.")
    else:
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

# (run_calculations, convert_inputs_to_params, calculate_investment, calculate_revenues_costs bleiben unverändert)

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
    erwerbsmodell = params.get('erwerbsmodell', MODELL_BAUTRAEGER)

    if erwerbsmodell == MODELL_KAUF_GU:
        sanierungskostenanteil = params.get('input_sanierungskostenanteil', 0.0)
        bemessungsgrundlage_knk = gik_netto * (1.0 - sanierungskostenanteil)
        results['knk_berechnungsbasis_info'] = f"Basis KNK (Kauf & GU): {format_euro(bemessungsgrundlage_knk, 0)} (GIK exkl. Sanierung)"
    else:
        bemessungsgrundlage_knk = gik_netto
        results['knk_berechnungsbasis_info'] = f"Basis KNK (Bauträger): {format_euro(bemessungsgrundlage_knk, 0)} (Gesamte GIK)"

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
    if erwerbsmodell == MODELL_KAUF_GU:
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

    else:
        # Bauträgermodell
        if gik_netto > 0:
            anteil_grundstueck = params['input_grundstuecksanteil']
            anteil_sanierung = params['input_sanierungskostenanteil']
            anteil_altbau = params['input_altbauanteil']
        else:
            anteil_grundstueck, anteil_sanierung, anteil_altbau = 0, 0, 0

        knk_auf_grundstueck = erwerbsnebenkosten * anteil_grundstueck
        knk_auf_sanierung = erwerbsnebenkosten * anteil_sanierung
        knk_auf_altbau = erwerbsnebenkosten * anteil_altbau

        afa_basis_grundstueck = wert_grundstueck + knk_auf_grundstueck
        afa_basis_sanierung_vor_foerderung = wert_sanierung + knk_auf_sanierung + aktivierung_baubegleitung
        afa_basis_altbau = wert_altbau + knk_auf_altbau

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
        annuitaet_bank = darlehen_bank * (zins_bank + tilgung_bank)
        
        restschuld = darlehen_bank
        zinsen_liste, tilgung_liste, restschuld_liste = [], [], []

        for jahr in df.index:
            if restschuld <= 0.01:
                zinsen_liste.append(0); tilgung_liste.append(0); restschuld_liste.append(0)
                continue

            zins_betrag = restschuld * zins_bank
            tilgung_betrag = annuitaet_bank - zins_betrag
            
            if tilgung_betrag > restschuld:
                tilgung_betrag = restschuld
            
            restschuld -= tilgung_betrag
            
            zinsen_liste.append(zins_betrag)
            tilgung_liste.append(tilgung_betrag)
            restschuld_liste.append(restschuld)

        df['Zins Bank'] = zinsen_liste
        df['Tilgung Bank'] = tilgung_liste
        df['Restschuld Bank'] = restschuld_liste
    else:
        df['Zins Bank'] = 0; df['Tilgung Bank'] = 0; df['Restschuld Bank'] = 0

    # --- KfW-Darlehen (NEU: Annuität oder Endfällig) ---
    darlehen_kfw = results['kfw_darlehen']
    zins_kfw = params['kfw_zins']
    laufzeit_kfw = params['kfw_gesamtlaufzeit']
    darlehenstyp_kfw = params.get('kfw_darlehenstyp', KFW_ANNUITAET)

    # Nur KfW Zuschüsse (Tilgung + BB) reduzieren das KfW Darlehen.
    zuschuss_kfw_gesamt = results['kfw_tilgungszuschuss'] + results['zuschuss_baubegleitung']

    if darlehen_kfw > 0:
        restschuld = darlehen_kfw
        zinsen_liste, tilgung_liste, restschuld_liste = [], [], []

        # NEU: Fallunterscheidung nach Darlehenstyp
        if darlehenstyp_kfw == KFW_ENDFAELLIG:
            # --- Logik für Endfälliges Darlehen ---
            for jahr in df.index:
                if restschuld <= 0.01:
                     zinsen_liste.append(0); tilgung_liste.append(0); restschuld_liste.append(0)
                     continue

                if jahr < laufzeit_kfw:
                    # Zinszahlung, keine Tilgung
                    zins_betrag = restschuld * zins_kfw
                    tilgung_betrag = 0
                    # Restschuld bleibt gleich
                elif jahr == laufzeit_kfw:
                    # Letztes Jahr: Zinszahlung + Endfällige Tilgung (abzgl. Zuschuss)
                    zins_betrag = restschuld * zins_kfw
                    # Die zu leistende Tilgung ist die Restschuld abzgl. Zuschuss.
                    tilgung_betrag = max(0, restschuld - zuschuss_kfw_gesamt)
                    restschuld = 0 # Darlehen ist getilgt
                else:
                    # Nach Laufzeitende
                    zins_betrag = 0
                    tilgung_betrag = 0
                    restschuld = 0
                
                # Wichtig: Bei Endfällig wird die Restschuld NICHT durch die Tilgung reduziert, 
                # außer im letzten Jahr (wo es oben auf 0 gesetzt wurde).
                if jahr < laufzeit_kfw:
                     restschuld_liste.append(restschuld)
                else:
                     # Im letzten Jahr und danach ist die Restschuld 0
                     restschuld_liste.append(0)

                zinsen_liste.append(zins_betrag)
                tilgung_liste.append(tilgung_betrag)
                

        else:
            # --- Logik für Annuitätendarlehen (Bestehend) ---
            tilgungsfrei_kfw = params['kfw_tilgungsfreie_jahre']
            restlaufzeit = laufzeit_kfw - tilgungsfrei_kfw
            annuitaet_kfw_nach_tf = 0

            for jahr in df.index:
                if restschuld <= 0.01:
                    zinsen_liste.append(0); tilgung_liste.append(0); restschuld_liste.append(0)
                    continue

                # Tilgungsfreie Zeit
                if jahr <= tilgungsfrei_kfw:
                    zins_betrag = restschuld * zins_kfw
                    tilgung_betrag = 0
                
                # Tilgungsphase beginnt
                else:
                    if jahr == tilgungsfrei_kfw + 1:
                        # Erster Tilgungsjahr: KfW Zuschuss anwenden
                        restschuld = max(0, restschuld - zuschuss_kfw_gesamt)

                        # Berechnung der Annuität für die Restlaufzeit
                        if restschuld > 0:
                            if IRR_ENABLED:
                                try:
                                    annuitaet_kfw_nach_tf = -npf.pmt(zins_kfw, restlaufzeit, restschuld)
                                except Exception as e:
                                    logging.error(f"Fehler bei npf.pmt Berechnung: {e}")
                                    raise RuntimeError("Finanzmathematische Berechnung fehlgeschlagen (KfW Annuität).")
                            else:
                                q = 1 + zins_kfw
                                if q == 1:
                                    annuitaet_kfw_nach_tf = restschuld / restlaufzeit if restlaufzeit > 0 else 0
                                else:
                                    annuitaet_kfw_nach_tf = restschuld * (q**restlaufzeit * (q-1)) / (q**restlaufzeit - 1)
                            
                    zins_betrag = restschuld * zins_kfw
                    tilgung_betrag = annuitaet_kfw_nach_tf - zins_betrag

                    if tilgung_betrag > restschuld:
                        tilgung_betrag = restschuld
                
                restschuld -= tilgung_betrag

                zinsen_liste.append(zins_betrag)
                tilgung_liste.append(tilgung_betrag)
                restschuld_liste.append(restschuld)

        # NEU: Zuweisung der Listen zum DataFrame (gilt für beide Typen)
        df['Zins KfW'] = zinsen_liste
        df['Tilgung KfW'] = tilgung_liste
        df['Restschuld KfW'] = restschuld_liste

    else:
        df['Zins KfW'] = 0; df['Tilgung KfW'] = 0; df['Restschuld KfW'] = 0

    # Gesamtsummen
    df['Zinsen Gesamt'] = df['Zins Bank'] + df['Zins KfW']
    df['Tilgung Gesamt'] = df['Tilgung Bank'] + df['Tilgung KfW']
    # Annuität Gesamt = Gesamte Kapitaldienstleistung (Zins + Tilgung)
    df['Annuität Gesamt'] = df['Zinsen Gesamt'] + df['Tilgung Gesamt']
    df['Restschuld Gesamt'] = df['Restschuld Bank'] + df['Restschuld KfW']

    return df

# (calculate_depreciation_schedule, calculate_kpis, calculate_irr bleiben unverändert)

def calculate_depreciation_schedule(df, results):
    """Berechnet die jährlichen AfA-Beträge (Denkmal und Linear)."""
    
    basis_sanierung = results['afa_basis_sanierung']
    basis_altbau = results['afa_basis_altbau']

    # 1. Denkmal-AfA (Sonder-AfA)
    afa_denkmal_liste = []
    for jahr in df.index:
        if 1 <= jahr <= 8:
            afa_betrag = basis_sanierung * AFA_DENKMAL_J1_8
        elif 9 <= jahr <= 12:
            afa_betrag = basis_sanierung * AFA_DENKMAL_J9_12
        else:
            afa_betrag = 0
        afa_denkmal_liste.append(afa_betrag)
    
    # 2. Lineare AfA (Altbau)
    afa_linear_liste = []
    restwert_altbau = basis_altbau
    for jahr in df.index:
        afa_betrag = basis_altbau * AFA_ALTBAU_SATZ
        if afa_betrag > restwert_altbau:
            afa_betrag = restwert_altbau
        
        restwert_altbau -= afa_betrag
        afa_linear_liste.append(afa_betrag)

    df['AfA Denkmal (Sonder)'] = afa_denkmal_liste
    df['AfA Altbau (Linear)'] = afa_linear_liste
    df['AfA Gesamt'] = df['AfA Denkmal (Sonder)'] + df['AfA Altbau (Linear)']
    return df


# Funktion für alle KPIs
def calculate_kpis(params, results):
    """Berechnet alle relevanten KPIs."""

    gik_brutto = results.get('gik_brutto', 0)
    investitionssumme_gesamt = results.get('investitionssumme_gesamt', 0)
    gesamtzuschuss = results.get('gesamtzuschuss', 0)
    jahreskaltmiete_netto = results.get('jahreskaltmiete_netto', 0)
    einnahmen_ueberschuss_j1 = results.get('einnahmen_ueberschuss_vor_finanz_steuer', 0)
    wohnflaeche = float(params.get('input_wohnflaeche', 0))
    eigenkapital_bedarf = results.get('eigenkapital_bedarf', 0)
    
    try:
        haltedauer = int(params['geplanter_verkauf'])
    except (ValueError, TypeError):
        haltedauer = 10

    if haltedauer > BERECHNUNGSZEITRAUM:
        haltedauer = BERECHNUNGSZEITRAUM

    df = results.get('projection_df')

    # --- Renditekennzahlen (Jahr 1) ---

    # Bruttomietrendite
    if investitionssumme_gesamt > 0:
        results['kpi_bruttomietrendite'] = jahreskaltmiete_netto / investitionssumme_gesamt
    else:
        results['kpi_bruttomietrendite'] = 0
    
    # Nettomietrendite
    if investitionssumme_gesamt > 0:
        results['kpi_nettomietrendite'] = einnahmen_ueberschuss_j1 / investitionssumme_gesamt
    else:
        results['kpi_nettomietrendite'] = 0

    # --- Kaufpreiskennzahlen (pro m²) ---

    if wohnflaeche > 0:
        # Brutto
        results['kpi_kaufpreis_qm_brutto'] = gik_brutto / wohnflaeche
        # Netto (nach allen Zuschüssen)
        results['kpi_kaufpreis_qm_netto'] = (investitionssumme_gesamt - gesamtzuschuss) / wohnflaeche
    else:
        results['kpi_kaufpreis_qm_brutto'] = 0
        results['kpi_kaufpreis_qm_netto'] = 0

    # --- Erweiterte KPIs (Haltedauer-basiert) ---

    if df is None or df.empty:
        results['kpi_irr_nach_steuer'] = 0.0
        results['kpi_steuerfreier_gewinn'] = 0.0
        results['kpi_kaufpreis_qm_effektiv'] = results.get('kpi_kaufpreis_qm_netto', 0)
        results['kpi_gesamtrendite_nach_steuer'] = 0.0
        return results

    # 1. Exit-Erlös
    # Nutzt .iloc[-1] als Fallback, falls haltedauer außerhalb des Index liegt (sollte durch obigen Check verhindert sein)
    if haltedauer in df.index:
        exit_erloes = df.loc[haltedauer, 'Nettovermögen']
    else:
        exit_erloes = df['Nettovermögen'].iloc[-1] if not df.empty else 0


    # 2. Kumulierte Cashflows und Steuern
    cum_cashflow_nach_steuer = df['Cashflow nach Steuer'].head(haltedauer).sum()
    cum_steuerersparnis = df['Steuerersparnis'].head(haltedauer).sum()

    # 3. Kaufpreis/m² (Effektiv)
    if wohnflaeche > 0:
        steuerersparnis_pro_qm = cum_steuerersparnis / wohnflaeche
        results['kpi_kaufpreis_qm_effektiv'] = results['kpi_kaufpreis_qm_netto'] - steuerersparnis_pro_qm
    else:
        results['kpi_kaufpreis_qm_effektiv'] = 0

    # 4. Steuerfreier Gewinn (Total Profit)
    total_profit = cum_cashflow_nach_steuer + exit_erloes - eigenkapital_bedarf
    results['kpi_steuerfreier_gewinn'] = total_profit

    # 5. Gesamtrendite nach Steuern (RoE)
    if eigenkapital_bedarf > 0:
        results['kpi_gesamtrendite_nach_steuer'] = total_profit / eigenkapital_bedarf
    else:
        results['kpi_gesamtrendite_nach_steuer'] = float('inf') if total_profit > 0 else 0

    # 6. IRR Berechnung
    results = calculate_irr(results, eigenkapital_bedarf, df, haltedauer, exit_erloes)

    return results


def calculate_irr(results, initial_investment, df, haltedauer, exit_erloes):
    """Berechnet den Internal Rate of Return (IRR) nach Steuern."""
    if not IRR_ENABLED:
        results['kpi_irr_nach_steuer'] = "N/A"
        return results
        
    # Cashflows während der Haltedauer (inkl. Sonderzufluss Jahr 1)
    cashflows = df['Cashflow nach Steuer'].head(haltedauer).tolist()

    # Gesamte Cashflow-Reihe für IRR
    irr_stream = [-initial_investment] + cashflows
    
    # Füge den Exit-Erlös zum letzten Jahr hinzu
    if len(irr_stream) > 1:
        irr_stream[-1] += exit_erloes
    
    try:
        irr = npf.irr(irr_stream)
        if pd.isna(irr) or not np.isreal(irr):
            results['kpi_irr_nach_steuer'] = 0.0
        else:
            results['kpi_irr_nach_steuer'] = float(irr)
    except Exception as e:
        logging.error(f"IRR calculation failed: {e}")
        results['kpi_irr_nach_steuer'] = "Fehler"

    return results

# ====================================================================================
# PDF EXPORT LOGIK
# ====================================================================================

# (PDF Exportfunktionen wurden minimal angepasst, um den KfW Typ aufzunehmen)

def add_footer(canvas, doc):
    """Fügt den Disclaimer als Fußzeile auf jeder Seite hinzu."""
    canvas.saveState()
    styles = getSampleStyleSheet()
    footer_style = ParagraphStyle(name='FooterStyle', parent=styles['Normal'], fontSize=8, leading=10, textColor=colors.grey, alignment=0)
    footer = Paragraph(PDF_DISCLAIMER_TEXT, footer_style)
    w, h = footer.wrapOn(canvas, doc.width, doc.bottomMargin)
    footer.drawOn(canvas, doc.leftMargin, 1*cm)
    canvas.restoreState()


def create_pdf_report(results, params):
    """Generiert einen PDF-Bericht der Analyse."""
    if not PDF_EXPORT_ENABLED:
        return None

    buffer = BytesIO()
    page_size = landscape(A4)
    doc = SimpleDocTemplate(buffer, pagesize=page_size,
                            rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=2*cm, bottomMargin=2.5*cm)
    
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TitleStyle', fontSize=18, leading=22, spaceAfter=12, fontName='Helvetica-Bold', textColor=RL_COLOR_PRIMARY))
    styles.add(ParagraphStyle(name='HeaderStyle', fontSize=14, leading=18, spaceAfter=10, fontName='Helvetica-Bold', textColor=RL_COLOR_PRIMARY))
    styles.add(ParagraphStyle(name='NormalStyle', fontSize=10, leading=14))
    styles.add(ParagraphStyle(name='SmallStyle', fontSize=8, leading=12))

    story = []
    haltedauer = params.get('geplanter_verkauf', 10)

    # --- Titel ---
    story.append(Paragraph("Park 55 | Investitionsrechner - Analysebericht", styles['TitleStyle']))
    objekt_name_display = params['objekt_name'] if params['objekt_name'] else "Freie Berechnung"
    story.append(Paragraph(f"Objekt: {objekt_name_display}", styles['HeaderStyle']))
    
    story.append(Paragraph(f"Erwerbsmodell: {params.get('erwerbsmodell', 'N/A')}", styles['NormalStyle']))
    # NEU: KfW Typ anzeigen
    story.append(Paragraph(f"KfW-Darlehenstyp: {params.get('kfw_darlehenstyp', 'N/A')}", styles['NormalStyle']))


    try:
        today_date = datetime.date.today().strftime('%d.%m.%Y')
    except Exception:
        today_date = "N/A"
        
    story.append(Paragraph(f"Berechnung vom: {today_date}", styles['NormalStyle']))
    story.append(Spacer(1, 0.5*cm))

    # --- Zusammenfassung (KPIs) ---
    story.append(Paragraph("Zusammenfassung (Prominente KPIs)", styles['HeaderStyle']))
    
    kpi_data = [
        ["Kaufpreis/m² (Netto)", f"KP/m² (Effektiv, {haltedauer} J.)", "Zuschüsse Gesamt (KfW+Komm.)", f"Steuerfreier Gewinn ({haltedauer} J.)"],
        [
            format_euro(results.get('kpi_kaufpreis_qm_netto', 0), 0),
            format_euro(results.get('kpi_kaufpreis_qm_effektiv', 0), 0),
            format_euro(results.get('gesamtzuschuss', 0), 0),
            format_euro(results.get('kpi_steuerfreier_gewinn', 0), 0)
        ]
    ]
    
    t = Table(kpi_data, colWidths=[6*cm]*4)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), RL_COLOR_PRIMARY),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('BACKGROUND', (0,1), (-1,-1), RL_COLOR_LIGHT_BG),
        ('GRID', (0,0), (-1,-1), 1, colors.grey)
    ]))
    story.append(t)
    story.append(Spacer(1, 0.5*cm))

    # --- Zentrale KPIs (Details) ---
    story.append(Paragraph("Zentrale KPIs (Details)", styles['HeaderStyle']))

    kpi_irr_value = results.get('kpi_irr_nach_steuer', 0)
    kpi_irr_formatted = format_percent(kpi_irr_value) if isinstance(kpi_irr_value, float) else str(kpi_irr_value)

    rendite_value = results.get('kpi_gesamtrendite_nach_steuer', 0)
    rendite_formatted = f"{format_percent(rendite_value, 1)} (RoE)"

    kpi_detail_data = [
        ["Wirtschaftlichkeit", "Wert", "Investitionskontext", "Wert"],
        ["Gesamtrendite n. St.", rendite_formatted, "Kaufpreis/m² (Brutto)", format_euro(results.get('kpi_kaufpreis_qm_brutto', 0), 0)],
        ["IRR n. St.", kpi_irr_formatted, "Kommunale Förderung", format_euro(results.get('kommunale_foerderung', 0), 0)],
        ["Nettomietrendite", format_percent(results.get('kpi_nettomietrendite', 0), 2), "", ""],
    ]

    t_kpi_detail = Table(kpi_detail_data, colWidths=[6*cm, 5*cm, 6*cm, 5*cm])
    t_kpi_detail.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), RL_COLOR_PRIMARY),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (1,1), (1,-1), 'RIGHT'),
        ('ALIGN', (3,1), (3,-1), 'RIGHT'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('SPAN', (2,3), (3,3)),
    ]))
    story.append(t_kpi_detail)
    story.append(Spacer(1, 0.8*cm))


    # --- Investition & Finanzierung ---
    story.append(Paragraph("Investition & Finanzierung", styles['HeaderStyle']))
    
    knk_info = results.get('knk_berechnungsbasis_info', 'Basis KNK: N/A')
    story.append(Paragraph(knk_info, styles['SmallStyle']))
    story.append(Spacer(1, 0.2*cm))

    inv_data = [
        ["Position", "Betrag"],
        ["GIK Netto", format_euro(results['gik_netto'], 0)],
        ["+ Erwerbsnebenkosten", format_euro(results['erwerbsnebenkosten'], 0)],
        ["+ Kosten Baubegleitung", format_euro(results['kosten_baubegleitung_gesamt'], 0)],
        ["= Investitionssumme Gesamt", format_euro(results['investitionssumme_gesamt'], 0)],
        ["", ""],
        ["Finanzierung durch:", ""],
        ["Eigenkapital", format_euro(results['eigenkapital_bedarf'], 0)],
        ["Bankdarlehen", format_euro(results['bankdarlehen'], 0)],
        ["KfW-Darlehen (inkl. BB)", format_euro(results['kfw_darlehen'], 0)],
    ]

    t_inv = Table(inv_data, colWidths=[8*cm, 5*cm])
    t_inv.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), RL_COLOR_PRIMARY),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTNAME', (0,4), (-1,4), 'Helvetica-Bold'),
        ('FONTNAME', (0,6), (-1,6), 'Helvetica-Bold'),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('SPAN', (0,6), (1,6)),
    ]))
    story.append(t_inv)
    story.append(Spacer(1, 1*cm))

    # --- Detaillierte Tabellen ---
    def add_dataframe_to_story(df, title, style=None):
        story.append(PageBreak())
        story.append(Paragraph(title, styles['HeaderStyle']))
        
        data = [["Jahr"] + df.columns.tolist()]
        for index, row in df.iterrows():
            formatted_row = [str(index)]
            for item in row:
                formatted_row.append(format_euro(item, 0).replace(" €", ""))
            data.append(formatted_row)
        
        num_cols = len(df.columns) + 1
        page_width = doc.width
        
        if num_cols > 1:
            jahr_width = min((page_width / num_cols) * 0.5, 2*cm)
            rest_width = (page_width - jahr_width) / (num_cols - 1)
            col_widths = [jahr_width] + [rest_width] * (num_cols - 1)
        else:
            col_widths = [page_width]

        t = Table(data, colWidths=col_widths)
        
        base_style = TableStyle([
            ('BACKGROUND', (0,0), (-1,0), RL_COLOR_PRIMARY),
            ('TEXTCOLOR',(0,0),(-1,0),colors.white),
            ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ])
        
        for i in range(1, len(data)):
            if i % 2 == 0:
                base_style.add('BACKGROUND', (0, i), (-1, i), colors.whitesmoke)
            else:
                 base_style.add('BACKGROUND', (0, i), (-1, i), RL_COLOR_LIGHT_BG)

        if style:
            base_style.add(style)
            
        t.setStyle(base_style)
        story.append(t)

    if 'projection_df' not in results or results['projection_df'].empty:
        story.append(Paragraph("Keine Daten verfügbar, da die Investitionssumme 0 ist oder keine Berechnung erfolgte.", styles['NormalStyle']))
    else:
        df_proj = results['projection_df']
        # 1. Cashflow Tabelle
        cf_cols = ['Mieteinnahmen (Netto)', 'Betriebskosten', 'Einnahmenüberschuss', 'Annuität Gesamt', 'Cashflow vor Steuer', 'Steuerersparnis', 'Sonderzufluss', 'Cashflow nach Steuer']
        existing_cf_cols = [col for col in cf_cols if col in df_proj.columns]
        add_dataframe_to_story(df_proj[existing_cf_cols], "Cashflow-Entwicklung (Werte in EUR)")

        # 2. Steuer Tabelle
        tax_cols = ['Einnahmenüberschuss', 'Zinsen Gesamt', 'AfA Gesamt', 'Steuerliches Ergebnis (V+V)', 'Steuerersparnis']
        existing_tax_cols = [col for col in tax_cols if col in df_proj.columns]
        add_dataframe_to_story(df_proj[existing_tax_cols], "Steuerliche Entwicklung (Werte in EUR)")
        
        # 3. Wertentwicklung
        value_cols = ['Immobilienwert', 'Restschuld Gesamt', 'Nettovermögen']
        existing_value_cols = [col for col in value_cols if col in df_proj.columns]
        add_dataframe_to_story(df_proj[existing_value_cols], "Vermögensentwicklung (Werte in EUR)")
    
    # --- Disclaimer (Am Ende des Dokuments) ---
    story.append(Spacer(1, 1*cm))
    story.append(HRFlowable(width="100%", thickness=1, lineCap='round', color=colors.grey, spaceAfter=10))
    story.append(Paragraph(PDF_DISCLAIMER_TEXT, styles['SmallStyle']))
    story.append(Paragraph("©TRAS Beratungs- und Beteiligungs GmbH", styles['SmallStyle']))

    # Build-Prozess mit Fußzeilen-Handler
    doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
    buffer.seek(0)
    return buffer

# ====================================================================================
# ERGEBNISANZEIGE (Darstellung der Ergebnisse)
# ====================================================================================

# (display_results, display_kpi_section, display_central_kpis, display_overview, display_investment_details bleiben unverändert)

def display_results(results, params):
    """
    Stellt die berechneten Ergebnisse dar und bietet den PDF-Download an.
    """

    if results['investitionssumme_gesamt'] == 0:
        st.warning("Die Gesamtinvestitionskosten (GIK) sind 0. Bitte geben Sie die Daten ein, um die Berechnung zu starten.")
        return

    if 'finanzierung_hinweis' in results:
        st.warning(results['finanzierung_hinweis'])
    
    if 'afa_hinweis' in results:
        st.warning(results['afa_hinweis'])

    # --- 1. Prominente KPIs ---
    display_kpi_section(results, params)

    # --- PDF Download Button ---
    if PDF_EXPORT_ENABLED:
        try:
            with st.spinner("Generiere PDF-Bericht (Querformat)..."):
                pdf_buffer = create_pdf_report(results, params)

            if pdf_buffer:
                objekt_name_for_file = params['objekt_name'] if params['objekt_name'] else "Freie_Berechnung"
                safe_filename = "".join([c for c in objekt_name_for_file if c.isalnum() or c in (' ', '-', '_')]).rstrip().replace(' ', '_')
                st.download_button(
                    label="⬇️ Analyse als PDF herunterladen",
                    data=pdf_buffer,
                    file_name=f"Park55_Analyse_{safe_filename}.pdf",
                    mime="application/pdf"
                )
        except Exception as e:
            st.error(f"Fehler bei der PDF-Generierung. Bitte prüfen Sie die Server-Logs.")
            logging.error("Fehler bei der PDF-Generierung:")
            logging.error(traceback.format_exc())

    # --- 2. Tabs für Detailergebnisse ---
    tab_kpis, tab_overview, tab_investment, tab_finance_value, tab_cashflow, tab_tax = st.tabs([
        "Zentrale KPIs",
        "Übersicht",
        "Investition & AfA",
        "Finanzierung & Wertentwicklung",
        "Cashflow-Entwicklung",
        "Steuern"
    ])

    with tab_kpis:
        display_central_kpis(results, params)

    with tab_overview:
        display_overview(results)

    with tab_investment:
        display_investment_details(results)

    with tab_finance_value:
        display_finance_value_dev(results, params) # NEU: Params übergeben

    with tab_cashflow:
        display_cashflow_details(results)

    with tab_tax:
        display_tax_details(results)

# Angepasste KPI Sektion
def display_kpi_section(results, params):
    """Zeigt die wichtigsten KPIs in der gewünschten Reihenfolge."""
    st.markdown('<div class="prominent-kpi-container">', unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)

    haltedauer = params['geplanter_verkauf']

    # 1. Kaufpreis/m² (Netto)
    with col1:
        st.metric("Kaufpreis/m² (Netto)", format_euro(results.get('kpi_kaufpreis_qm_netto', 0), 0))
        st.caption("KP nach Zuschüssen/m² (KfW + Kommunal)")

    # 2. Kaufpreis/m² (Effektiv)
    with col2:
        st.metric("Kaufpreis/m² (Effektiv)", format_euro(results.get('kpi_kaufpreis_qm_effektiv', 0), 0))
        st.caption(f"Netto abzgl. Steuerersparnis (über {haltedauer} J.)")

    # 3. Zuschüsse Gesamt
    with col3:
        st.metric("Zuschüsse Gesamt", format_euro(results.get('gesamtzuschuss', 0), 0))
        st.caption("KfW (TZ+BB) + Kommunale Förderung")

    # 4. Steuerfreier Gewinn
    with col4:
        st.metric("Steuerfreier Gewinn (Profit)", format_euro(results.get('kpi_steuerfreier_gewinn', 0), 0))
        st.caption(f"Gesamtgewinn nach {haltedauer} Jahren.")

    st.markdown('</div>', unsafe_allow_html=True)


# Funktion für den Tab "Zentrale KPIs"
def display_central_kpis(results, params):
    """Zeigt die detaillierten Investment-KPIs."""
    st.subheader("Zentrale Investment-Kennzahlen")

    haltedauer = params.get('geplanter_verkauf', 10)

    # --- 1. Gesamtergebnisindikatoren ---
    st.markdown("#### Gesamtergebnisindikatoren")

    col1_1, col1_2 = st.columns(2)

    with col1_1:
        # Gesamtrendite nach Steuern (RoE)
        rendite_value = results.get('kpi_gesamtrendite_nach_steuer', 0)
        st.metric(f"Gesamtrendite nach Steuern ({haltedauer} J.)", format_percent(rendite_value, 1))
        st.caption("Return on Equity (RoE): Gesamtgewinn / Initiales Eigenkapital.")

    with col1_2:
         # Steuerfreier Gewinn (Absolut)
        st.metric(f"Steuerfreier Gewinn (Absolut)", format_euro(results.get('kpi_steuerfreier_gewinn', 0), 0))
        st.caption(f"Gesamtgewinn (Profit) nach {haltedauer} Jahren.")


    # --- 2. Wirtschaftlichkeit ---
    st.markdown("#### Wirtschaftlichkeit")

    col2_1, col2_2 = st.columns(2)

    with col2_1:
        # IRR nach Steuer
        irr_value = results.get('kpi_irr_nach_steuer', "N/A")
        if isinstance(irr_value, float):
            st.metric(f"Internal Rate of Return (IRR, n. St.)", format_percent(irr_value))
        else:
            st.metric(f"Internal Rate of Return (IRR, n. St.)", irr_value)
        st.caption(f"Interner Zinsfuß über Haltedauer von {haltedauer} Jahren.")

    with col2_2:
        # Nettomietrendite
        st.metric("Nettomietrendite (Jahr 1)", format_percent(results.get('kpi_nettomietrendite', 0), 2))
        st.caption("Einnahmenüberschuss / Investitionssumme Gesamt.")

    # --- 3. Kontext ---
    st.markdown("#### Kontext")
    
    col3_1, col3_2 = st.columns(2)
    
    with col3_1:
        # Kaufpreis/m² (Brutto)
        st.metric("Kaufpreis/m² (Brutto)", format_euro(results.get('kpi_kaufpreis_qm_brutto', 0), 0))
        st.caption("GIK Brutto (Kaufpreis + KNK) / Wohnfläche.")
    
    with col3_2:
        # Kommunale Förderung (Absolut) anzeigen
        st.metric("Kommunale Förderung (Absolut)", format_euro(results.get('kommunale_foerderung', 0), 0))
        st.caption("Zuschüsse aus kommunalen Programmen.")


def display_overview(results):
    """Zeigt eine Zusammenfassung."""
    st.subheader("Zusammenfassung der Investition")

    erwerbsmodell = st.session_state.get('erwerbsmodell', MODELL_BAUTRAEGER)
    st.markdown(f"**Erwerbsmodell:** {erwerbsmodell}")
    
    st.info(results.get('knk_berechnungsbasis_info', 'Information zur KNK-Basis nicht verfügbar.'))

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("#### Investitionsvolumen")
        
        st.markdown('<div class="calculation-breakdown">', unsafe_allow_html=True)
        st.text(format_aligned_line("GIK Netto:", format_euro(results['gik_netto'], 0)))
        st.text(format_aligned_line("+ Erwerbsnebenkosten:", format_euro(results['erwerbsnebenkosten'], 0)))
        st.text(format_aligned_line("+ Kosten Baubegleitung:", format_euro(results['kosten_baubegleitung_gesamt'], 0)))
        st.markdown('<div class="breakdown-intermediate">', unsafe_allow_html=True)
        st.text(format_aligned_line("= Investitionssumme:", format_euro(results['investitionssumme_gesamt'], 0)))
        st.markdown('</div></div>', unsafe_allow_html=True)

    with col2:
        st.markdown("#### Zuschüsse")
        st.markdown('<div class="calculation-breakdown">', unsafe_allow_html=True)
        st.text(format_aligned_line("KfW Tilgungszuschuss:", format_euro(results.get('kfw_tilgungszuschuss', 0), 0)))
        st.text(format_aligned_line("+ KfW BB-Zuschuss:", format_euro(results.get('zuschuss_baubegleitung', 0), 0)))
        st.text(format_aligned_line("+ Kommunale Förderung:", format_euro(results.get('kommunale_foerderung', 0), 0)))
        st.markdown('<div class="breakdown-intermediate">', unsafe_allow_html=True)
        st.text(format_aligned_line("= Gesamtzuschuss:", format_euro(results.get('gesamtzuschuss', 0), 0)))
        st.markdown('</div></div>', unsafe_allow_html=True)


    with col3:
        st.markdown("#### Finanzierungsstruktur")
        st.markdown('<div class="calculation-breakdown">', unsafe_allow_html=True)
        st.text(format_aligned_line("Eigenkapital:", format_euro(results['eigenkapital_bedarf'], 0)))
        st.text(format_aligned_line("+ Bankdarlehen:", format_euro(results['bankdarlehen'], 0)))
        st.text(format_aligned_line("+ KfW-Darlehen (Gesamt):", format_euro(results['kfw_darlehen'], 0)))
        st.markdown('<div class="breakdown-intermediate">', unsafe_allow_html=True)
        st.text(format_aligned_line("= Summe Finanzierung:", format_euro(results['investitionssumme_gesamt'], 0)))
        st.markdown('</div></div>', unsafe_allow_html=True)

def display_investment_details(results):
    """Details zur Investition und AfA."""
    st.subheader("AfA-Bemessungsgrundlage (Basis)")
    
    if st.session_state.get('erwerbsmodell') == MODELL_KAUF_GU:
        st.info("Basis: GIK Netto + Erwerbsnebenkosten (nur auf Bestand) + aktivierte Baubegleitung.")
    else:
        st.info("Basis: GIK Netto + Erwerbsnebenkosten (auf Gesamt-GIK) + aktivierte Baubegleitung.")


    st.markdown('<div class="calculation-breakdown">', unsafe_allow_html=True)
    LW = 38
    st.text(format_aligned_line("GIK Netto:", format_euro(results['gik_netto'], 0), LW))
    st.text(format_aligned_line("+ Erwerbsnebenkosten (Aktiviert):", format_euro(results['erwerbsnebenkosten'], 0), LW))
    st.text(format_aligned_line("+ Aktivierte Baubegleitung (Netto):", format_euro(results['aktivierung_baubegleitung'], 0), LW))
    st.text(format_aligned_line("- Kommunale Förderung (Mindert AfA):", format_euro(results.get('kommunale_foerderung', 0), 0), LW))
    
    st.markdown('<div class="breakdown-intermediate">', unsafe_allow_html=True)
    st.text(format_aligned_line("= AfA-Basis Gesamt:", format_euro(results['afa_basis_summe_check'], 0), LW))
    st.markdown('</div></div>', unsafe_allow_html=True)

    st.markdown("#### Aufteilung der AfA-Basis")
    
    if results.get('kommunale_foerderung', 0) > 0:
        st.info(f"Die Basis der Sanierungskosten wurde um die kommunale Förderung reduziert:")
        st.markdown('<div class="calculation-breakdown">', unsafe_allow_html=True)
        st.text(format_aligned_line("Basis vor Förderung:", format_euro(results.get('afa_basis_sanierung_vor_foerderung', 0), 0), LW))
        st.text(format_aligned_line("- Kommunale Förderung:", format_euro(results.get('kommunale_foerderung', 0), 0), LW))
        st.markdown('<div class="breakdown-intermediate">', unsafe_allow_html=True)
        st.text(format_aligned_line("= Basis nach Förderung:", format_euro(results.get('afa_basis_sanierung', 0), 0), LW))
        st.markdown('</div></div>', unsafe_allow_html=True)


    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Grundstücksanteil (Keine AfA)", format_euro(results['afa_basis_grundstueck'], 0))
        st.caption("Inkl. anteiliger Erwerbsnebenkosten.")
    with col2:
        st.metric(f"Sanierungskostenanteil ({AFA_TYP}-AfA)", format_euro(results['afa_basis_sanierung'], 0))
        st.caption("Erhöhte Abschreibung (§ 7h/i EStG). Nach Abzug kommunaler Förderung.")
    with col3:
        st.metric(f"Altbausubstanz ({format_percent(AFA_ALTBAU_SATZ)} linear)", format_euro(results['afa_basis_altbau'], 0))
        st.caption("Lineare Gebäude-AfA (§ 7 Abs. 4 EStG).")


# NEU: Params hinzugefügt, um Darlehenstyp anzuzeigen
def display_finance_value_dev(results, params):
    """Details zur Finanzierung, Tilgungspläne und Wertentwicklung."""
    st.subheader("Finanzierungsübersicht")
    
    if 'finanzierung_hinweis' in results:
        st.warning(results['finanzierung_hinweis'])

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Bankdarlehen")
        st.metric("Darlehenssumme", format_euro(results['bankdarlehen'], 0))
        st.metric("Zinssatz", format_percent(st.session_state.bank_zins_pct / 100.0))
        st.metric("Anfängliche Tilgung", format_percent(st.session_state.bank_tilgung_pct / 100.0))

    with col2:
        st.markdown("#### KfW-Förderung (Programm 261)")
        # NEU: Darlehenstyp anzeigen
        st.metric("Darlehenstyp", params.get('kfw_darlehenstyp', KFW_ANNUITAET))

        st.metric("KfW-Darlehenssumme (Gesamt)", format_euro(results['kfw_darlehen'], 0))
        st.caption(f"Davon Basis-Darlehen: {format_euro(results['kfw_darlehen_basis'], 0)}")

        st.metric("Zinssatz KfW", format_percent(st.session_state.kfw_zins_pct / 100.0))
        st.metric(f"Tilgungszuschuss (auf Basis)", format_euro(results['kfw_tilgungszuschuss'], 0))
        st.metric("Zuschuss Baubegleitung", format_euro(results['zuschuss_baubegleitung'], 0))
        
        # NEU: Laufzeit-Info dynamisch anzeigen
        if params.get('kfw_darlehenstyp') == KFW_ENDFAELLIG:
             st.metric("Laufzeit bis Fälligkeit", f"{st.session_state.kfw_gesamtlaufzeit} Jahre")
        else:
             st.metric("Laufzeit / Tilgungsfrei", f"{st.session_state.kfw_gesamtlaufzeit} Jahre / {st.session_state.kfw_tilgungsfreie_jahre} Jahre")

    
    # --- Tilgungspläne ---
    st.subheader("Tilgungsplan (Zins, Tilgung, Restschuld)")
    
    df = results.get('projection_df', pd.DataFrame())

    fin_cols = [
        'Zins Bank', 'Tilgung Bank', 'Restschuld Bank',
        'Zins KfW', 'Tilgung KfW', 'Restschuld KfW',
        'Zinsen Gesamt', 'Tilgung Gesamt', 'Restschuld Gesamt'
    ]
    
    existing_fin_cols = [col for col in fin_cols if col in df.columns]

    if existing_fin_cols:
        display_dataframe(df[existing_fin_cols])
    else:
        st.info("Keine Finanzierungsdaten vorhanden (z.B. bei 100% Eigenkapital).")

    # --- Wertentwicklung ---
    st.subheader("Vermögensentwicklung (Wert vs. Restschuld)")
    
    value_cols = ['Immobilienwert', 'Restschuld Gesamt', 'Nettovermögen']
    if all(col in df.columns for col in value_cols):
        display_dataframe(df[value_cols])
    elif not df.empty:
        st.warning("Daten für Wertentwicklung nicht vollständig.")

    st.info(
        "Wenn Sie die Immobilie als Privatperson erworben haben, können Sie diese nach zehn Jahren steuerfrei veräußern. "
        "Bei Immobilien, die im Betriebsvermögen einer Kapital- oder Personengesellschaft gehalten werden, ist eine steuerfreie Veräußerung hingegen nicht möglich. "
        "In beiden Fällen wird der volle Steuervorteil aus der Sonder-AfA bei einer Haltedauer von zwölf Jahren erreicht."
    )

# (display_cashflow_details, display_tax_details, display_dataframe bleiben unverändert)

def display_cashflow_details(results):
    """Details zur Cashflow-Entwicklung."""
    st.subheader("Cashflow-Projektion (Jahr 1)")

    st.markdown("#### Einnahmen (Jahr 1)")
    st.markdown('<div class="calculation-breakdown">', unsafe_allow_html=True)
    st.text(format_aligned_line("Miete Wohnen:", format_euro(results['miete_wohnen_mtl']*12, 0)))
    st.text(format_aligned_line("+ Miete Keller:", format_euro(results['miete_keller_mtl']*12, 0)))
    st.text(format_aligned_line("+ Miete Stellplätze:", format_euro(results['miete_stellplatz_mtl']*12, 0)))
    st.markdown('<div class="breakdown-intermediate">', unsafe_allow_html=True)
    st.text(format_aligned_line("= Jahreskaltmiete (Brutto):", format_euro(results['jahreskaltmiete'], 0)))
    st.markdown('</div>', unsafe_allow_html=True)
    st.text(format_aligned_line("- Sicherheitsabschlag:", format_euro(results['sicherheitsabschlag_absolut'], 0)))
    st.markdown('<div class="breakdown-intermediate">', unsafe_allow_html=True)
    st.text(format_aligned_line("= Jahreskaltmiete (Netto):", format_euro(results['jahreskaltmiete_netto'], 0)))
    st.markdown('</div></div>', unsafe_allow_html=True)


    st.markdown("#### Betriebsergebnis (vor Finanzierung/Steuern, Jahr 1)")
    st.markdown('<div class="calculation-breakdown">', unsafe_allow_html=True)
    st.text(format_aligned_line("Jahreskaltmiete (Netto):", format_euro(results['jahreskaltmiete_netto'], 0)))
    st.text(format_aligned_line("- Verwaltungskosten:", format_euro(results['jahresverwaltungskosten'], 0)))
    st.markdown('<div class="breakdown-intermediate">', unsafe_allow_html=True)
    st.text(format_aligned_line("= Einnahmenüberschuss:", format_euro(results['einnahmen_ueberschuss_vor_finanz_steuer'], 0)))
    st.markdown('</div></div>', unsafe_allow_html=True)

    st.subheader("Cashflow-Tabelle")
    df = results.get('projection_df', pd.DataFrame())

    if not df.empty:
        # NEU: Annuität Gesamt (Kapitaldienst) hinzugefügt
        display_cols = [
            'Mieteinnahmen (Netto)', 'Betriebskosten', 'Einnahmenüberschuss',
            'Annuität Gesamt', 'Cashflow vor Steuer', 'Steuerersparnis', 'Sonderzufluss', 'Cashflow nach Steuer'
        ]
        existing_cols = [col for col in display_cols if col in df.columns]
        
        if existing_cols:
            display_dataframe(df[existing_cols])
        else:
             st.write("Keine Daten verfügbar.")
    else:
        st.write("Keine Daten verfügbar.")

def display_tax_details(results):
    """Detaillierte Darstellung der steuerlichen Komponenten."""
    st.subheader("Steuerliche Berechnungsgrundlagen")
    
    st.metric("Angenommener Grenzsteuersatz (Brutto, inkl. Soli/KiSt)", format_percent(results.get('grenzsteuersatz_brutto', 0)))
    
    if st.session_state.steuer_modus == 'Basis Einkommen (zvE)':
        st.info("Hinweis: Die Berechnung basiert auf einem angenommenen Grenzsteuersatz von 42% (netto). Eine exakte Ermittlung aus dem zvE ist nicht implementiert.")

    # --- Kumulierte Werte ---
    st.subheader("Kumulierte Steuerersparnis")
    df = results.get('projection_df', pd.DataFrame())
    
    try:
        haltedauer = int(st.session_state.geplanter_verkauf)
    except (ValueError, TypeError):
        haltedauer = 10 # Fallback

    if not df.empty:
        # Kumulation über 12 Jahre
        if len(df) >= 12:
            cum_tax_saving_12y = df['Steuerersparnis'].head(12).sum()
            st.metric(f"Gesamt nach 12 Jahren (Ende Denkmal-AfA)", format_euro(cum_tax_saving_12y, 0))
        
        # Kumulation über Haltedauer
        # Nutzt min(), falls Haltedauer länger als der Berechnungszeitraum ist
        effective_haltedauer = min(haltedauer, len(df))
        if effective_haltedauer > 0:
            cum_tax_saving_total = df['Steuerersparnis'].head(effective_haltedauer).sum()
            st.metric(f"Gesamt nach Haltedauer ({effective_haltedauer} J.)", format_euro(cum_tax_saving_total, 0))


    # --- Detailtabelle ---
    st.subheader("Detaillierte Steuerberechnung pro Jahr")
    
    if not df.empty:
        tax_cols = [
            'Einnahmenüberschuss', 'Zinsen Gesamt',
            'AfA Denkmal (Sonder)', 'AfA Altbau (Linear)', 'AfA Gesamt',
            'Steuerliches Ergebnis (V+V)', 'Steuerersparnis'
        ]
        
        existing_tax_cols = [col for col in tax_cols if col in df.columns]

        if existing_tax_cols:
            display_dataframe(df[existing_tax_cols])
        else:
            st.warning("Steuerdaten nicht vollständig.")

# Hilfsfunktion zur robusten Darstellung von DataFrames
def display_dataframe(df):
    """Helper function to display DataFrames with robust formatting."""
    try:
        # Use .map for modern Pandas (>= 2.1.0)
        st.dataframe(df.map(lambda x: format_euro(x, 0) if isinstance(x, (int, float, np.number)) else str(x)))
    except AttributeError:
        # Fallback for older pandas versions (.style.format)
        try:
            formatter = {col: lambda x: format_euro(x, 0) for col in df.select_dtypes(include=np.number).columns}
            st.dataframe(df.style.format(formatter))
        except Exception as e:
             logging.warning(f"DataFrame styling fallback failed: {e}")
             st.dataframe(df)
    except Exception as e:
        # Absolute Fallback
        logging.warning(f"DataFrame formatting failed: {e}")
        st.dataframe(df)

# ====================================================================================
# HAUPTPROGRAMM (Struktur)
# ====================================================================================

def main():
    # 1. Initialisierung und Styling
    initialize_session_state()
    set_custom_style()

    st.title("Park 55 | Investitionsrechner")

    st.info("Wählen Sie den Eingabemodus und das Erwerbsmodell. Die Berechnung wird automatisch bei jeder Änderung der Eingabeparameter durchgeführt.")

    # Optionale Warnings
    if not IRR_ENABLED:
        st.error("Modul 'numpy_financial' nicht gefunden. IRR-Berechnung deaktiviert.")
    if not PDF_EXPORT_ENABLED:
        st.warning("PDF Export ist deaktiviert (Modul 'reportlab' fehlt).")

    # ----------------------------------------------------------------
    # ANWENDUNGSLOGIK
    # ----------------------------------------------------------------

    # 1. Input-Widgets anzeigen
    gik_is_valid, kfw_is_valid = display_inputs()

    st.markdown("---")
    # Header für Ergebnisse
    objekt_name_header = st.session_state['objekt_name'] if st.session_state['objekt_name'] else 'Ihre Eingabe'
    st.header(f"Berechnungsergebnisse: {objekt_name_header}")

    # 2. Aufruf der Berechnung und Anzeige der Ergebnisse

    if not gik_is_valid:
        st.error("Berechnung nicht möglich: GIK-Aufteilung > 100%.")
    else:
        # Berechnung durchführen
        try:
            results, params = run_calculations(st.session_state)
            # Ergebnisse anzeigen
            display_results(results, params)
            
        except RuntimeError as e:
            st.error(f"Berechnungsfehler: {e}.")
            logging.error(traceback.format_exc())
        except Exception as e:
            # Allgemeine Fehlerbehandlung
            st.error(f"Ein unerwarteter Fehler ist während der Berechnung aufgetreten.")
            logging.error("Fehler bei der Berechnung:")
            logging.error(traceback.format_exc())

    # Footer Hinweis
    st.markdown("---")
    st.caption("©TRAS Beratungs- und Beteiligungs GmbH – Urheberrechtlich geschützte Anwendung. Alle Rechte vorbehalten.")

if __name__ == '__main__':
    # Globale Fehlerbehandlung
    try:
        main()
    except Exception as e:
        st.error("Ein unerwarteter technischer Fehler ist aufgetreten.")
        logging.error(traceback.format_exc())