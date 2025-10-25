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
# StringIO wird für die Simulation der CSV benötigt, BytesIO für PDF
from io import BytesIO, StringIO 

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
    st.set_page_config(layout="wide", page_title="Park 55 Immobilienrechner")
except st.errors.StreamlitAPIException:
    pass

# --- KONSTANTEN & STANDARDWERTE ---

# [Konstanten bleiben unverändert]
GREST_SATZ = 0.05
NOTAR_AG_SATZ = 0.015
ERWERBSNEBENKOSTEN_SATZ = GREST_SATZ + NOTAR_AG_SATZ
SOLI_ZUSCHLAG = 0.055
AFA_TYP = "Denkmal"
AFA_ALTBAU_SATZ = 0.02
AFA_DENKMAL_J1_8 = 0.09
AFA_DENKMAL_J9_12 = 0.07
BERECHNUNGSZEITRAUM = 30
KFW_LIMIT_PRO_WE_BASIS = 150000
KFW_ZUSCHUSS_261_SATZ = 0.40
KFW_ZUSCHUSS_BB_SATZ = 0.50
KOSTEN_BB_PRO_WE_DEFAULT = 3998

STEUERJAHRE_OPTIONEN = [2024, 2025]
STEUERJAHRE_OPTIONEN.sort(reverse=True)
STEUERJAHR_DEFAULT = STEUERJAHRE_OPTIONEN[0]

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
    "Steuerliche Vorteile, KfW-Förderungen und Kostenansätze sind beispielhaft und können abweichen. "
    "Alle Ergebnisse erfolgen ohne Gewähr. Eine rechtliche, steuerliche oder finanzielle Beratung wird ausdrücklich nicht erbracht."
)

# Konstante für manuelle Auswahl im Dropdown
MANUAL_INPUT = "--- Manuelle Eingabe / Freie Berechnung ---"

# Defaults (bleiben unverändert zur letzten Version)
DEFAULTS = {
    # Objektdaten (Defaults für Manuelle Eingabe)
    'objekt_name': 'Freie Berechnung',
    'input_gik_netto': 0,
    'input_sanierungskostenanteil_pct': 0.0,
    'input_grundstuecksanteil_pct': 0.0,
    'input_wohnflaeche': 0.0,
    'input_anzahl_whg': 1,
    'input_kellerflaeche': 0.0,
    'input_anzahl_stellplaetze': 0,
    
    'input_kfw_darlehen_261_basis': KFW_LIMIT_PRO_WE_BASIS, # Default für 1 WE
    'kosten_baubegleitung_pro_we': KOSTEN_BB_PRO_WE_DEFAULT,

    # Berechnungsparameter
    'ek_quote_pct': 15.0,
    'bank_zins_pct': 4.20,
    'bank_tilgung_pct': 2.00,
    'kfw_zins_pct': 2.92,
    'kfw_gesamtlaufzeit': 30,
    'kfw_tilgungsfreie_jahre': 4,

    'steuer_modus': STEUER_MODI[0], 'zve': 150000,
    'steuersatz_manuell_pct': 42.0,
    'steuertabelle': 'Grund',
    'kirchensteuer_option': KIRCHENSTEUER_DEFAULT,
    'steuerjahr': STEUERJAHR_DEFAULT,
    'geplanter_verkauf': 12,

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

@st.cache_data
def load_object_data():
    """Lädt und bereinigt die Objektdaten aus der CSV-Datei."""
    
    # --- ECHTE DATEI LADEN (Hier aktivieren, wenn bereit) ---
    # file_path = "2025-10-16_Park 55_Rohdaten_Immobilienrechner App_v3.csv" 
    # logging.info(f"Versuche, Objektdaten von {file_path} zu laden...")
    # try:
    #     # Wichtig: delimiter=';' setzen. 
    #     # decimal='.' ist korrekt, da die Flächenspalten den Punkt verwenden.
    #     df_raw = pd.read_csv(file_path, delimiter=';', decimal='.', encoding='utf-8')
    # except FileNotFoundError:
    #     st.error(f"FEHLER: Objektdaten-Datei nicht gefunden: '{file_path}'")
    #     return pd.DataFrame()
    # except Exception as e:
    #     st.error(f"Fehler beim Laden der CSV: {e}")
    #     return pd.DataFrame()
    # -----------------------------------------------------------

    # --- SIMULATION START (Entfernen, wenn echte Datei genutzt wird) ---
    logging.info("Lade simulierte Objektdaten (Neue Struktur)...")
    # Der Inhalt Ihrer bereitgestellten CSV-Datei wird hier eingefügt (Auszug)
    csv_data = """Objekt_ID;Strasse;Hausnummer;Ort;Baujahr;AfA_Typ;Sanierungsgebiet_7h;Kaufpreis;Wohnflaeche_neu_qm;Anzahl_Wohneinheiten;Sanierungskosten;Foerderfaehige_Kosten_KFW;KFW_Zuschuss_Prozent;Kommunale_Foerderung_Betrag;Grundstuecksanteil_Kaufpreis;Vermietungsstatus;Wohnflaeche_qm;Kellerflaeche_qm;Anzahl_Stellplaetze;Wohnflaeche_Bestand_qm;Anzahl_Wohneinheiten_Bestand;Objekttyp;Grundstuecksgroesse_antlg;GIK_brutto;GIK_netto;Grund_Boden;Altsubstanz;SanAnteil_brutto;SanAnteil_netto
SZ001;Breite Strasse;1;Salzgitter;1939;Denkmal;ja;174278;375.37;6;1219946;1000356;0.4;112610;42150;teilvermietet;375.37;86.34;0;268.12;4;Kettenhaus;562;1405552,07;932213,02;4,82 %;15,09 %;86,79 %;80,09 %
SZ002;Breite Strasse;3;Salzgitter;1939;Denkmal;ja;174278;375.37;6;1219946;1000356;0.4;112610;42150;teilvermietet;375.37;86.34;0;268.12;4;Kettenhaus;562;1405552,07;932213,02;4,82 %;15,09 %;86,79 %;80,09 %
SZ003;Breite Strasse;5;Salzgitter;1939;Denkmal;ja;162832;350.71;6;1139821;934653;0.4;105214;42150;leerstehend;350.71;80.66;0;250.51;4;Kettenhaus;562;1313236,05;870985,69;5,15 %;14,76 %;86,79 %;80,09 %
SZ163;Weserstrasse;30a;Salzgitter;1939;Denkmal;ja;19500;42.00;1;136500;111930;0.4;12600;525;vollvermietet;42.00;9.66;0;30.00;1;Kettenhaus;7;157267,50;104305,50;0,54 %;19,37 %;86,79 %;80,09 %
"""
    try:
        # Wichtig: sep=';' und decimal='.'
        df_raw = pd.read_csv(StringIO(csv_data), sep=';', decimal='.')
    except Exception as e:
        st.error(f"Fehler beim Einlesen der Datenstruktur: {e}")
        return pd.DataFrame()
    # --- SIMULATION ENDE ---


    # --- Datenbereinigung und Transformation ---
    df = pd.DataFrame()

    # 1. Erstelle einen benutzerfreundlichen Objektnamen für das Dropdown
    try:
        # Konvertiere Hausnummer zu String, um Fehler bei gemischten Typen zu vermeiden
        df['Objektname'] = df_raw['Objekt_ID'] + " - " + df_raw['Strasse'] + " " + df_raw['Hausnummer'].astype(str)
    except KeyError as e:
        st.error(f"CSV-Datei fehlen notwendige Spalten für den Objektnamen (Objekt_ID, Strasse oder Hausnummer): {e}")
        return pd.DataFrame()

    # 2. Wähle die benötigten Spalten aus und benenne sie um
    # Wir laden nur physische Eigenschaften (Flächen, Einheiten).
    required_cols = {
        'Wohnflaeche_neu_qm': 'Wohnflaeche',
        'Anzahl_Wohneinheiten': 'Anzahl_Whg',
        'Kellerflaeche_qm': 'Kellerflaeche',
        'Anzahl_Stellplaetze': 'Anzahl_Stellplaetze'
    }
    
    # 3. Übertrage und konvertiere Daten
    for csv_col, app_col in required_cols.items():
        if csv_col in df_raw.columns:
            # Da wir decimal='.' gesetzt haben, sollten diese Spalten bereits numerisch sein.
            # Wir erzwingen die Konvertierung und füllen Fehler (NaN) mit 0.
            df[app_col] = pd.to_numeric(df_raw[csv_col], errors='coerce').fillna(0)
        else:
            # Warnung, falls eine erwartete Spalte fehlt
            logging.warning(f"Spalte '{csv_col}' nicht in CSV gefunden. Setze auf 0.")
            df[app_col] = 0

    # 4. Stelle korrekte Datentypen sicher
    df['Wohnflaeche'] = df['Wohnflaeche'].astype(float)
    df['Kellerflaeche'] = df['Kellerflaeche'].astype(float)
    df['Anzahl_Whg'] = df['Anzahl_Whg'].astype(int)
    df['Anzahl_Stellplaetze'] = df['Anzahl_Stellplaetze'].astype(int)

    # Sicherstellen, dass mindestens 1 WE vorhanden ist (Stabilität)
    df['Anzahl_Whg'] = df['Anzahl_Whg'].apply(lambda x: max(1, x))
        
    # Entferne leere Zeilen am Ende, falls vorhanden
    df = df.dropna(subset=['Objektname'])
        
    logging.info(f"Erfolgreich {len(df)} Objekte geladen.")
    return df


def initialize_session_state():
    """Initialisiert den Streamlit Session State mit Default-Werten."""
    if 'initialized' not in st.session_state:
        logging.info("Initialisiere Session State...")
        # Lade die globalen Defaults
        for key, value in DEFAULTS.items():
            if key not in st.session_state:
                st.session_state[key] = value
        
        # Initialisiere den berechneten Altbauanteil
        st.session_state['input_altbauanteil_pct'] = 100.0 - DEFAULTS['input_sanierungskostenanteil_pct'] - DEFAULTS['input_grundstuecksanteil_pct']
        
        # Initialisiere die Objektauswahl auf Manuell
        st.session_state['selected_object'] = MANUAL_INPUT
        st.session_state['initialized'] = True

def update_state_from_selection():
    """
    Callback-Funktion: Aktualisiert den Session State bei Objektauswahl.
    Lädt nur strukturelle Daten, keine GIK/Anteile.
    """
    selected_name = st.session_state.selected_object
    df = load_object_data()

    if selected_name == MANUAL_INPUT:
        # Setze auf globale Defaults zurück
        target_data = {
            'Objektname': DEFAULTS['objekt_name'],
            'Wohnflaeche': DEFAULTS['input_wohnflaeche'],
            'Anzahl_Whg': DEFAULTS['input_anzahl_whg'],
            'Kellerflaeche': DEFAULTS['input_kellerflaeche'],
            'Anzahl_Stellplaetze': DEFAULTS['input_anzahl_stellplaetze']
        }
        # Wichtig: GIK und Anteile explizit auf Default (0) zurücksetzen, falls sie vorher manuell geändert wurden.
        st.session_state.input_gik_netto = DEFAULTS['input_gik_netto']
        st.session_state.input_sanierungskostenanteil_pct = DEFAULTS['input_sanierungskostenanteil_pct']
        st.session_state.input_grundstuecksanteil_pct = DEFAULTS['input_grundstuecksanteil_pct']

    elif not df.empty and selected_name in df['Objektname'].values:
        # Lade Daten aus dem (bereinigten) DataFrame
        target_data = df[df['Objektname'] == selected_name].iloc[0].to_dict()
        # GIK und Anteile werden hier NICHT geladen, sie behalten ihren aktuellen Wert (z.B. 0).
    else:
        return # Nichts tun, wenn Auswahl ungültig ist

    # 1. Aktualisiere Basisdaten im State
    st.session_state.objekt_name = target_data['Objektname']
    st.session_state.input_wohnflaeche = float(target_data['Wohnflaeche'])
    st.session_state.input_anzahl_whg = int(target_data['Anzahl_Whg'])
    st.session_state.input_kellerflaeche = float(target_data['Kellerflaeche'])
    st.session_state.input_anzahl_stellplaetze = int(target_data['Anzahl_Stellplaetze'])
    
    # 2. Berechne und aktualisiere abgeleitete Werte (KfW, BB)
    anzahl_whg = st.session_state.input_anzahl_whg
    
    # KfW Basisdarlehen (Maximalbetrag)
    kfw_basis = anzahl_whg * KFW_LIMIT_PRO_WE_BASIS
    st.session_state.input_kfw_darlehen_261_basis = kfw_basis
    
    # Kosten Baubegleitung (Standardwert pro WE)
    st.session_state.kosten_baubegleitung_pro_we = KOSTEN_BB_PRO_WE_DEFAULT

# ====================================================================================
# HILFSFUNKTIONEN & FORMATIERUNG
# ====================================================================================
# [Formatierungsfunktionen bleiben unverändert]

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
         value = float(value)
         return f"{value*100:,.{decimals}f} %".replace('.', ',')
     except (ValueError, TypeError):
         return "0,00 %"

def format_aligned_line(label, value_str, label_width=28):
    return f"{label:<{label_width}}{value_str:>15}"


# --- VALIDIERUNGSLOGIK ---
# [Validierungslogik bleibt unverändert]

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

    # Nur warnen, wenn eine Investitionssumme > 0 eingegeben wurde
    if altbauanteil_pct < 5.0 and altbauanteil_pct >= 0 and st.session_state.get('input_gik_netto', 0) > 0:
        msg = f"Hinweis: Anteil Altbausubstanz ({altbauanteil_pct:.2f}%) ist sehr gering."
        return True, altbauanteil_pct, "warning", msg

    return True, altbauanteil_pct, "success", "Plausibel."

# --- DESIGN & STYLING ---

def set_custom_style():
    # JavaScript Snippet für den "Keyboard Arrow Scroll Fix"
    # Verhindert das Scrollen der Seite, wenn Pfeiltasten in Number Inputs verwendet werden.
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
    if (!window.parent.keyboardFixAttached) {
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

        /* Sidebar Styling */
        [data-testid="stSidebar"] {{
            background-color: {COLOR_LIGHT_BG};
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
# INPUT WIDGETS (Sidebar)
# ====================================================================================
# [Sidebar Widgets bleiben unverändert]

def display_sidebar_inputs():
    """
    Zeigt alle Input-Widgets in der Sidebar an.
    """
    st.sidebar.header("Eingabedaten")

    # --- 0. Objektauswahl ---
    st.sidebar.subheader("0. Objektauswahl")
    df_objects = load_object_data()
    
    if not df_objects.empty:
        object_options = [MANUAL_INPUT] + df_objects['Objektname'].tolist()
        
        # Das Selectbox Widget. Der Callback (on_change) wird ausgelöst, wenn sich die Auswahl ändert.
        st.sidebar.selectbox(
            "Wählen Sie ein Objekt aus der Liste:",
            options=object_options,
            key='selected_object',
            on_change=update_state_from_selection # Hier wird der Callback registriert
        )
    else:
        st.sidebar.warning("Objektdaten konnten nicht geladen werden. Prüfen Sie die Datenquelle (CSV).")

    # --- 1. Objektdaten ---
    st.sidebar.subheader("1. Objektdaten & GIK")
    # Der Wert für 'objekt_name' wird nun durch den Callback gesteuert
    st.sidebar.text_input("Objektname / Beschreibung", key='objekt_name')
    st.sidebar.number_input("Gesamtinvestitionskosten (GIK) Netto (€)", min_value=0, step=10000, key='input_gik_netto')

    # GIK Aufteilung & Validierung (Prozentual)
    st.sidebar.markdown("**Aufteilung GIK (für AfA-Berechnung):**")
    col1, col2 = st.sidebar.columns(2)
    col1.number_input("Sanierungskostenanteil (%)", min_value=0.0, max_value=100.0, step=1.0, format="%.0f", key='input_sanierungskostenanteil_pct')
    col2.number_input("Grundstücksanteil (%)", min_value=0.0, max_value=100.0, step=1.0, format="%.0f", key='input_grundstuecksanteil_pct')

    # Validierungslogik
    gik_is_valid, altbauanteil_pct, msg_type, msg = validate_gik_anteile(
        st.session_state.input_sanierungskostenanteil_pct,
        st.session_state.input_grundstuecksanteil_pct
    )

    if msg_type == "error":
        st.sidebar.error(msg)
    elif msg_type == "warning":
        st.sidebar.warning(msg)

    st.sidebar.number_input("Altbausubstanz (berechnet, %)", value=altbauanteil_pct, disabled=True, format="%.1f")

    # Weitere Objektdaten (Werte werden durch Callback gesteuert)
    st.sidebar.markdown("**Flächen & Einheiten:**")
    col_w1, col_w2 = st.sidebar.columns(2)
    col_w1.number_input("Wohnfläche (m²)", min_value=0.0, step=1.0, key='input_wohnflaeche')
    col_w2.number_input("Anzahl Wohnungen", min_value=1, step=1, key='input_anzahl_whg')

    col_k1, col_k2 = st.sidebar.columns(2)
    col_k1.number_input("Kellerfläche (m², optional)", min_value=0.0, step=1.0, key='input_kellerflaeche')
    col_k2.number_input("Anzahl Stellplätze", min_value=0, step=1, key='input_anzahl_stellplaetze')


    # --- 2. KfW-Förderung ---
    st.sidebar.subheader("2. KfW-Förderung (Programm 261)")

    # Wert wird durch Callback gesteuert
    st.sidebar.number_input("Kosten Baubegleitung (pro WE, €)", min_value=0, max_value=4000, step=1, format="%d", key='kosten_baubegleitung_pro_we')

    # Berechnung des Max-Limits (nur Basis)
    anzahl_whg = int(st.session_state.get('input_anzahl_whg', 1))
    max_kfw_darlehen_basis = anzahl_whg * KFW_LIMIT_PRO_WE_BASIS

    # Robustheits-Fix (Stellt sicher, dass der Wert im State nicht das neue Maximum überschreitet)
    current_kfw_value = st.session_state.get('input_kfw_darlehen_261_basis', DEFAULTS['input_kfw_darlehen_261_basis'])
    
    try:
        current_kfw_value = float(current_kfw_value)
        max_kfw_darlehen_basis = float(max_kfw_darlehen_basis)
    except (ValueError, TypeError):
        current_kfw_value = 0.0
        max_kfw_darlehen_basis = 0.0

    if current_kfw_value > max_kfw_darlehen_basis:
        st.session_state.input_kfw_darlehen_261_basis = int(max_kfw_darlehen_basis)

    # Widget rendern (Wert wird durch Callback gesteuert)
    st.sidebar.number_input(f"Darlehenssumme Basis (Max: {format_euro(int(max_kfw_darlehen_basis),0)})", min_value=0, max_value=int(max_kfw_darlehen_basis), step=1000, key='input_kfw_darlehen_261_basis')
    
    # Information über das Gesamtdarlehen
    kosten_bb_pro_we = float(st.session_state.get('kosten_baubegleitung_pro_we', 0))
    kosten_baubegleitung_gesamt = kosten_bb_pro_we * anzahl_whg
    kfw_gesamt = st.session_state.input_kfw_darlehen_261_basis + kosten_baubegleitung_gesamt
    st.sidebar.info(f"Das gesamte KfW-Darlehen beträgt {format_euro(kfw_gesamt, 0)} (Basis + Baubegleitung).")

    kfw_is_valid = True


    # --- 3. Finanzierung (Bank) ---
    st.sidebar.subheader("3. Finanzierung & Eigenkapital")
    st.sidebar.number_input("Eigenkapitalquote (%)", min_value=0.0, max_value=100.0, step=0.1, format="%.1f", key='ek_quote_pct')

    st.sidebar.markdown("**Bankdarlehen:**")
    col_z1, col_t1 = st.sidebar.columns(2)
    col_z1.number_input("Zinssatz Bank (p.a. %)", min_value=0.0, step=0.01, format="%.2f", key='bank_zins_pct')
    col_t1.number_input("Tilgungsrate Bank (%)", min_value=0.0, step=0.01, format="%.2f", key='bank_tilgung_pct')

    st.sidebar.markdown("**KfW-Darlehen (Konditionen):**")
    st.sidebar.number_input("Zinssatz KfW (p.a. %)", min_value=0.0, step=0.01, format="%.2f", key='kfw_zins_pct')
    col_lz, col_tf = st.sidebar.columns(2)
    
    gesamtlaufzeit = st.session_state.kfw_gesamtlaufzeit
    max_tilgungsfrei = max(0, gesamtlaufzeit - 1)
    
    if st.session_state.kfw_tilgungsfreie_jahre > max_tilgungsfrei:
        st.session_state.kfw_tilgungsfreie_jahre = max_tilgungsfrei

    col_lz.number_input("Gesamtlaufzeit (Jahre)", min_value=1, max_value=35, step=1, key='kfw_gesamtlaufzeit')
    col_tf.number_input("Tilgungsfreie Jahre", min_value=0, max_value=max_tilgungsfrei, step=1, key='kfw_tilgungsfreie_jahre')


    # --- 4. Steuerliche Daten ---
    st.sidebar.subheader("4. Steuerliche Annahmen")
    
    st.sidebar.radio("Steuersatz-Ermittlung", STEUER_MODI, key='steuer_modus', horizontal=True)

    if st.session_state.steuer_modus == STEUER_MODI[0]:
        st.sidebar.number_input("Zu versteuerndes Einkommen (zvE)", min_value=0, step=10000, key='zve')
        col_t, col_j = st.sidebar.columns([2, 1])
        col_t.radio("Tabelle", ['Grund', 'Splitting'], key='steuertabelle')
        col_j.selectbox("Steuerjahr", STEUERJAHRE_OPTIONEN, key='steuerjahr')

    else: # Steuersatz
        st.sidebar.number_input("Grenzsteuersatz (%)", min_value=0.0, max_value=45.0, step=1.0, format="%.0f", key='steuersatz_manuell_pct')

    st.sidebar.selectbox("Kirchensteuer", list(KIRCHENSTEUER_MAP.keys()), key='kirchensteuer_option')

    # --- 5. Parameter & Prognose ---
    st.sidebar.subheader("5. Parameter & Prognose")
    st.sidebar.number_input("Geplanter Verkauf nach (Jahren)", min_value=10, step=1, key='geplanter_verkauf')

    st.sidebar.markdown("**Mieten (Startwerte):**")
    col_m1, col_m2 = st.sidebar.columns(2)
    # Miete Wohnen: 8.00 bis 12.50, Step 0.10
    col_m1.number_input("Miete Wohnen (€/m²)", min_value=8.0, max_value=12.50, step=0.1, format="%.2f", key='miete_wohnen')
    # Miete Keller: 0.00 bis 5.00, Step 0.10
    col_m2.number_input("Miete Keller (€/m²)", min_value=0.0, max_value=5.00, step=0.1, format="%.2f", key='miete_keller')
    # Miete Stellplatz: 20.00 bis 60.00, Step 5.00
    st.sidebar.number_input("Miete Stellplatz (€/Stk.)", min_value=20.0, max_value=60.0, step=5.0, format="%.2f", key='miete_stellplatz')

    st.sidebar.markdown("**Entwicklung (p.a. %):**")
    # Steigerungen: 0 bis 5% (Miete/Kosten) bzw. 10% (Wert), Step 0.5%
    col_e1, col_e2 = st.sidebar.columns(2)
    col_e1.number_input("Mietsteigerung (%)", min_value=0.0, max_value=5.0, step=0.5, format="%.1f", key='mietsteigerung_pa_pct')
    col_e2.number_input("Wertsteigerung (%)", min_value=0.0, max_value=10.0, step=0.5, format="%.1f", key='wertsteigerung_pa_pct')
    
    st.sidebar.markdown("**Kosten (Startwerte):**")
    # Verwaltung: 0.00 bis 40.00, Step 0.10
    st.sidebar.number_input("Verwaltung (€/Whg./Monat)", min_value=0.0, max_value=40.0, step=0.10, format="%.2f", key='nk_pro_wohnung')
    st.sidebar.number_input("Kostensteigerung (%)", min_value=0.0, max_value=5.0, step=0.5, format="%.1f", key='kostensteigerung_pa_pct')

    # Sicherheitsabschlag: 0 bis 20%, Step 1%
    st.sidebar.number_input("Sicherheitsabschlag Miete (%)", min_value=0.0, max_value=20.0, step=1.0, format="%.0f", key='sicherheitsabschlag_pct')

    st.sidebar.markdown("---")
    
    st.sidebar.caption("©TRAS Beratungs- und Beteiligungs GmbH – Urheberrechtlich geschützte Anwendung. Alle Rechte vorbehalten.")

    return gik_is_valid, kfw_is_valid

# ====================================================================================
# BERECHNUNGSLOGIK (Kern der Anwendung)
# ====================================================================================
# [Die Berechnungsfunktionen (run_calculations bis calculate_irr) bleiben unverändert.]

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

    # 5. Zeitreihenentwicklung (Cashflow, AfA, Finanzierung)
    results = calculate_projection(params, results)

    # 6. KPIs
    # Division durch Null verhindern, falls GIK 0 ist
    if results['gik_brutto'] > 0:
        results['kpi_bruttomietrendite'] = results['jahreskaltmiete_netto'] / results['gik_brutto']
    else:
        results['kpi_bruttomietrendite'] = 0
    
    wohnflaeche = float(params['input_wohnflaeche'])
    if wohnflaeche > 0:
        results['kpi_nettokaufpreis_qm_brutto'] = results['gik_brutto'] / wohnflaeche
        results['kpi_nettokaufpreis_qm_netto'] = (results['investitionssumme_gesamt'] - results['gesamtzuschuss']) / wohnflaeche
    else:
        results['kpi_nettokaufpreis_qm_brutto'] = 0
        results['kpi_nettokaufpreis_qm_netto'] = 0

    # IRR Berechnung
    results = calculate_irr(params, results)

    return results, params # Gebe auch params zurück für PDF Export

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
                # Handle potential None or empty string inputs gracefully
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

    # 1.1 GIK und Nebenkosten
    gik_netto = float(params['input_gik_netto'])
    erwerbsnebenkosten = gik_netto * ERWERBSNEBENKOSTEN_SATZ
    gik_brutto = gik_netto + erwerbsnebenkosten

    results['gik_netto'] = gik_netto
    results['erwerbsnebenkosten'] = erwerbsnebenkosten
    results['gik_brutto'] = gik_brutto

    # 1.2 Baubegleitung (Kosten und Zuschuss)
    kosten_bb_pro_we = float(params['kosten_baubegleitung_pro_we'])
    anzahl_whg = int(params['input_anzahl_whg'])

    kosten_baubegleitung_gesamt = kosten_bb_pro_we * anzahl_whg
    # Zuschuss Baubegleitung (50%)
    zuschuss_baubegleitung = kosten_baubegleitung_gesamt * KFW_ZUSCHUSS_BB_SATZ
    # Aktivierung für AfA (Restbetrag)
    aktivierung_baubegleitung = kosten_baubegleitung_gesamt - zuschuss_baubegleitung

    results['kosten_baubegleitung_gesamt'] = kosten_baubegleitung_gesamt
    results['zuschuss_baubegleitung'] = zuschuss_baubegleitung
    results['aktivierung_baubegleitung'] = aktivierung_baubegleitung

    # Investitionssumme Gesamt (inkl. Kosten BB)
    investitionssumme_gesamt = gik_brutto + kosten_baubegleitung_gesamt
    results['investitionssumme_gesamt'] = investitionssumme_gesamt

    # 1.3 AfA-Bemessungsgrundlagen
    wert_grundstueck = gik_netto * params['input_grundstuecksanteil']
    wert_sanierung = gik_netto * params['input_sanierungskostenanteil']
    wert_altbau = gik_netto * params['input_altbauanteil']

    nk_faktor = (1 + ERWERBSNEBENKOSTEN_SATZ)

    afa_basis_grundstueck = wert_grundstueck * nk_faktor
    # AfA Sanierung inkludiert aktivierte Baubegleitung
    afa_basis_sanierung = (wert_sanierung * nk_faktor) + aktivierung_baubegleitung
    afa_basis_altbau = wert_altbau * nk_faktor

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

    # Neue KfW Logik (Basis + BB automatisch)
    kfw_darlehen_basis = float(params['input_kfw_darlehen_261_basis'])
    
    # Das gesamte KfW-Darlehen ist die Summe aus Basis und den Kosten für BB
    kfw_darlehen_gesamt = kfw_darlehen_basis + kosten_baubegleitung_gesamt

    # Validierung gegen Fremdkapitalbedarf
    # Prüfung ob fremdkapital_bedarf > 0
    if kfw_darlehen_gesamt > fremdkapital_bedarf and fremdkapital_bedarf > 0:
        # Reduziere das Gesamtdarlehen, falls es den Bedarf übersteigt
        reduktion = kfw_darlehen_gesamt - fremdkapital_bedarf
        kfw_darlehen_gesamt = fremdkapital_bedarf
        
        # Versuche die Reduktion zuerst vom Basis-Darlehen abzuziehen (Priorität für BB-Finanzierung)
        if kfw_darlehen_basis >= reduktion:
            kfw_darlehen_basis -= reduktion
        else:
            # Wenn Basis nicht ausreicht, setze Basis auf 0.
            kfw_darlehen_basis = 0
            
        results['finanzierung_hinweis'] = "Hinweis: Das berechnete KfW-Darlehen (Basis+BB) war höher als der Fremdkapitalbedarf. Es wurde für die Berechnung auf den maximal benötigten Betrag reduziert."

    # Berechnung des Tilgungszuschusses (TZ)
    # Der TZ (40%) gilt nur für das (ggf. reduzierte) Basis-Darlehen
    kfw_tilgungszuschuss = kfw_darlehen_basis * KFW_ZUSCHUSS_261_SATZ
    
    # Bankdarlehen ist der Rest
    bankdarlehen = fremdkapital_bedarf - kfw_darlehen_gesamt

    results['eigenkapital_bedarf'] = eigenkapital_bedarf
    results['fremdkapital_bedarf'] = fremdkapital_bedarf
    results['kfw_darlehen'] = kfw_darlehen_gesamt # Speichere das Gesamtdarlehen
    results['kfw_darlehen_basis'] = kfw_darlehen_basis # Speichere Basis separat für Kontext
    results['kfw_tilgungszuschuss'] = kfw_tilgungszuschuss
    results['bankdarlehen'] = bankdarlehen

    # Gesamtzuschuss (Tilgungszuschuss + BB-Zuschuss)
    results['gesamtzuschuss'] = kfw_tilgungszuschuss + zuschuss_baubegleitung
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
# [Projektionsfunktionen bleiben unverändert]

def calculate_projection(params, results):
    """Führt die detaillierte Projektion über den Berechnungszeitraum durch."""
    
    # Handle edge case where investment is 0
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

    # Wachstumsfaktoren
    miet_faktoren = (1 + mietsteigerung) ** np.arange(BERECHNUNGSZEITRAUM)
    kosten_faktoren = (1 + kostensteigerung) ** np.arange(BERECHNUNGSZEITRAUM)
    wert_faktoren = (1 + wertsteigerung) ** np.arange(1, BERECHNUNGSZEITRAUM + 1)

    df['Mieteinnahmen (Netto)'] = results['jahreskaltmiete_netto'] * miet_faktoren
    df['Betriebskosten'] = results['jahresverwaltungskosten'] * kosten_faktoren
    df['Einnahmenüberschuss'] = df['Mieteinnahmen (Netto)'] - df['Betriebskosten']
    df['Immobilienwert'] = results['investitionssumme_gesamt'] * wert_faktoren

    # 2. Finanzierung (Tilgungspläne)
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
    df['Cashflow vor Steuer'] = df['Einnahmenüberschuss'] - df['Annuität Gesamt']
    df['Cashflow nach Steuer'] = df['Cashflow vor Steuer'] + df['Steuerersparnis']
    
    # 6. Nettovermögen
    df['Nettovermögen'] = df['Immobilienwert'] - df['Restschuld Gesamt']

    results['projection_df'] = df
    return results

def calculate_financing_schedule(df, params, results):
    """Berechnet die Tilgungspläne für Bank- und KfW-Darlehen."""
    
    # --- Bankdarlehen (Standard Annuität) ---
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

    # --- KfW-Darlehen (Tilgungsfrei + Zuschuss) ---
    # Nutzt das Gesamt-KfW-Darlehen (Basis + BB)
    darlehen_kfw = results['kfw_darlehen']
    zins_kfw = params['kfw_zins']
    laufzeit_kfw = params['kfw_gesamtlaufzeit']
    tilgungsfrei_kfw = params['kfw_tilgungsfreie_jahre']
    
    # Beide Zuschüsse (Tilgungszuschuss und Zuschuss BB) werden bei der Tilgung berücksichtigt
    zuschuss_kfw_gesamt = results['kfw_tilgungszuschuss'] + results['zuschuss_baubegleitung']

    # Berechnung der Restlaufzeit.
    restlaufzeit = laufzeit_kfw - tilgungsfrei_kfw

    if darlehen_kfw > 0:
        restschuld = darlehen_kfw
        zinsen_liste, tilgung_liste, restschuld_liste = [], [], []
        annuitaet_kfw_nach_tf = 0

        for jahr in df.index:
            if restschuld <= 0.01:
                 # Restliche Jahre auffüllen
                zinsen_liste.append(0); tilgung_liste.append(0); restschuld_liste.append(0)
                continue

            # Tilgungsfreie Zeit
            if jahr <= tilgungsfrei_kfw:
                zins_betrag = restschuld * zins_kfw
                tilgung_betrag = 0
            
            # Tilgungsphase beginnt
            else:
                if jahr == tilgungsfrei_kfw + 1:
                    # Erster Tilgungsjahr: Gesamten Zuschuss anwenden und Annuität neu berechnen
                    restschuld = max(0, restschuld - zuschuss_kfw_gesamt)

                    # Berechnung der Annuität für die Restlaufzeit
                    if restschuld > 0:
                        if IRR_ENABLED:
                            try:
                                # Nutze npf.pmt für präzise Annuitätenberechnung
                                annuitaet_kfw_nach_tf = -npf.pmt(zins_kfw, restlaufzeit, restschuld)
                            except Exception as e:
                                logging.error(f"Fehler bei npf.pmt Berechnung: {e}")
                                raise RuntimeError("Finanzmathematische Berechnung fehlgeschlagen (KfW Annuität).")
                        else:
                             # Fallback ohne numpy_financial (inkl. Robustheit für Zins=0)
                             q = 1 + zins_kfw
                             if q == 1:
                                 annuitaet_kfw_nach_tf = restschuld / restlaufzeit if restlaufzeit > 0 else 0
                             else:
                                annuitaet_kfw_nach_tf = restschuld * (q**restlaufzeit * (q-1)) / (q**restlaufzeit - 1)
                        
                # Annuität anwenden
                zins_betrag = restschuld * zins_kfw
                tilgung_betrag = annuitaet_kfw_nach_tf - zins_betrag

                # Anpassung der letzten Rate
                if tilgung_betrag > restschuld:
                    tilgung_betrag = restschuld
            
            restschuld -= tilgung_betrag

            zinsen_liste.append(zins_betrag)
            tilgung_liste.append(tilgung_betrag)
            restschuld_liste.append(restschuld)

        df['Zins KfW'] = zinsen_liste
        df['Tilgung KfW'] = tilgung_liste
        df['Restschuld KfW'] = restschuld_liste

    else:
        df['Zins KfW'] = 0; df['Tilgung KfW'] = 0; df['Restschuld KfW'] = 0

    # Gesamtsummen
    df['Zinsen Gesamt'] = df['Zins Bank'] + df['Zins KfW']
    df['Tilgung Gesamt'] = df['Tilgung Bank'] + df['Tilgung KfW']
    df['Annuität Gesamt'] = df['Zinsen Gesamt'] + df['Tilgung Gesamt']
    df['Restschuld Gesamt'] = df['Restschuld Bank'] + df['Restschuld KfW']

    return df

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

def calculate_irr(params, results):
    """Berechnet den Internal Rate of Return (IRR) nach Steuern."""
    if not IRR_ENABLED:
        results['kpi_irr_nach_steuer'] = "N/A"
        return results
        
    try:
        haltedauer = int(params['geplanter_verkauf'])
    except (ValueError, TypeError):
        haltedauer = 10 # Fallback

    # Prüfe, ob Projektionsdaten vorhanden sind
    if 'projection_df' not in results or results['projection_df'].empty:
        results['kpi_irr_nach_steuer'] = 0.0
        return results
        
    df = results['projection_df']

    if haltedauer > BERECHNUNGSZEITRAUM:
        haltedauer = BERECHNUNGSZEITRAUM

    # Cashflows während der Haltedauer
    cashflows = df['Cashflow nach Steuer'].head(haltedauer).tolist()

    # Anfangsinvestition (Jahr 0): Eigenkapital Bedarf
    initial_investment = results['eigenkapital_bedarf']

    # Verkaufserlös am Ende der Haltedauer (Jahr X)
    if haltedauer in df.index:
        exit_erloes = df.loc[haltedauer, 'Nettovermögen']
    else:
        exit_erloes = 0

    
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
# [PDF-Funktionen bleiben unverändert]

def add_footer(canvas, doc):
    """Fügt den Disclaimer als Fußzeile auf jeder Seite hinzu."""
    canvas.saveState()
    styles = getSampleStyleSheet()
    # Stil für die Fußzeile definieren (klein, grau, linksbündig)
    footer_style = ParagraphStyle(name='FooterStyle', parent=styles['Normal'], fontSize=8, leading=10, textColor=colors.grey, alignment=0)
    
    # Erstelle den Paragraph für die Fußzeile
    footer = Paragraph(PDF_DISCLAIMER_TEXT, footer_style)
    
    # Berechne die Dimensionen des Textes (doc.width ist die nutzbare Breite)
    w, h = footer.wrapOn(canvas, doc.width, doc.bottomMargin)
    
    # Platziere den Text unten links
    footer.drawOn(canvas, doc.leftMargin, 1*cm)
    canvas.restoreState()


def create_pdf_report(results, params):
    """Generiert einen PDF-Bericht der Analyse."""
    if not PDF_EXPORT_ENABLED:
        return None

    buffer = BytesIO()
    # Seitenformat auf Querformat (landscape(A4))
    page_size = landscape(A4)
    doc = SimpleDocTemplate(buffer, pagesize=page_size,
                            rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=2*cm, bottomMargin=2.5*cm) # Mehr Platz unten für Fußzeile
    
    # Styling
    styles = getSampleStyleSheet()
    
    # Benutzerdefinierte Stile
    styles.add(ParagraphStyle(name='TitleStyle', fontSize=18, leading=22, spaceAfter=12, fontName='Helvetica-Bold', textColor=RL_COLOR_PRIMARY))
    styles.add(ParagraphStyle(name='HeaderStyle', fontSize=14, leading=18, spaceAfter=10, fontName='Helvetica-Bold', textColor=RL_COLOR_PRIMARY))
    styles.add(ParagraphStyle(name='NormalStyle', fontSize=10, leading=14))
    styles.add(ParagraphStyle(name='SmallStyle', fontSize=8, leading=12))

    story = []

    # --- Titel ---
    story.append(Paragraph("Park 55 Immobilienrechner - Analysebericht", styles['TitleStyle']))
    story.append(Paragraph(f"Objekt: {params['objekt_name']}", styles['HeaderStyle']))
    # Anpassung für das Datum
    story.append(Paragraph(f"Berechnung vom: {datetime.date.today().strftime('%d.%m.%Y')}", styles['NormalStyle']))
    story.append(Spacer(1, 0.5*cm))

    # --- Zusammenfassung (KPIs) ---
    story.append(Paragraph("Zusammenfassung (KPIs)", styles['HeaderStyle']))
    
    kpi_irr_value = results.get('kpi_irr_nach_steuer', 0)
    kpi_irr_formatted = format_percent(kpi_irr_value) if isinstance(kpi_irr_value, float) else str(kpi_irr_value)

    kpi_data = [
        ["Kaufpreis/m² (Netto)", "Kaufpreis/m² (Brutto)", "KfW-Zuschuss Gesamt", "IRR nach Steuer"],
        [
            format_euro(results['kpi_nettokaufpreis_qm_netto'], 0),
            format_euro(results['kpi_nettokaufpreis_qm_brutto'], 0),
            format_euro(results['gesamtzuschuss'], 0),
            kpi_irr_formatted
        ]
    ]
    
    # Breitere Spalten für Querformat
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

    # --- Investition & Finanzierung ---
    story.append(Paragraph("Investition & Finanzierung", styles['HeaderStyle']))
    
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

    # Angepasste Spaltenbreiten
    t_inv = Table(inv_data, colWidths=[8*cm, 5*cm])
    t_inv.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), RL_COLOR_PRIMARY),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTNAME', (0,4), (-1,4), 'Helvetica-Bold'), # Investitionssumme Gesamt
        ('FONTNAME', (0,6), (-1,6), 'Helvetica-Bold'), # Finanzierung durch
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('SPAN', (0,6), (1,6)), # Merge Finanzierung durch
    ]))
    story.append(t_inv)
    story.append(Spacer(1, 1*cm))

    # --- Detaillierte Tabellen ---
    # Funktion zum Hinzufügen von Tabellen aus DataFrames
    def add_dataframe_to_story(df, title, style=None):
        story.append(PageBreak())
        story.append(Paragraph(title, styles['HeaderStyle']))
        
        # Konvertiere DataFrame in Liste von Listen für ReportLab
        data = [["Jahr"] + df.columns.tolist()]
        for index, row in df.iterrows():
            formatted_row = [str(index)]
            for item in row:
                # Formatieren und "€" entfernen für Kompaktheit
                formatted_row.append(format_euro(item, 0).replace(" €", ""))
            data.append(formatted_row)
        
        # Dynamische Spaltenbreiten
        num_cols = len(df.columns) + 1
        
        # Berechne Seitenbreite für Querformat (doc.width ist die nutzbare Breite)
        page_width = doc.width
        
        # Adjustierung für bessere Lesbarkeit im Querformat
        if num_cols > 1:
            # Jahr-Spalte schmaler, Rest breiter
            jahr_width = min((page_width / num_cols) * 0.5, 2*cm)
            rest_width = (page_width - jahr_width) / (num_cols - 1)
            col_widths = [jahr_width] + [rest_width] * (num_cols - 1)
        else:
            col_widths = [page_width]

        t = Table(data, colWidths=col_widths)
        
        # Basis Tabellenstil
        base_style = TableStyle([
            ('BACKGROUND', (0,0), (-1,0), RL_COLOR_PRIMARY),
            ('TEXTCOLOR',(0,0),(-1,0),colors.white),
            ('ALIGN', (1,0), (-1,-1), 'RIGHT'), # Spalten 1 bis Ende rechtsbündig
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ])
        
        # Alternierende Zeilenfarben
        for i in range(1, len(data)):
            if i % 2 == 0:
                base_style.add('BACKGROUND', (0, i), (-1, i), colors.whitesmoke)
            else:
                 base_style.add('BACKGROUND', (0, i), (-1, i), RL_COLOR_LIGHT_BG)

        if style:
            base_style.add(style)
            
        t.setStyle(base_style)
        story.append(t)

    # Handle empty dataframe if investment is 0
    if 'projection_df' not in results or results['projection_df'].empty:
        story.append(Paragraph("Keine Daten verfügbar, da die Investitionssumme 0 ist oder keine Berechnung erfolgte.", styles['NormalStyle']))
    else:
        df_proj = results['projection_df']
        # 1. Cashflow Tabelle
        cf_cols = ['Mieteinnahmen (Netto)', 'Betriebskosten', 'Einnahmenüberschuss', 'Annuität Gesamt', 'Cashflow vor Steuer', 'Steuerersparnis', 'Cashflow nach Steuer']
        # Filter columns that actually exist in the DataFrame
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
# [Anzeige-Funktionen bleiben unverändert]

def display_results(results, params):
    """
    Stellt die berechneten Ergebnisse dar und bietet den PDF-Download an.
    """
    st.header(f"Ergebnisse der Berechnung: {st.session_state['objekt_name']}")

    if results['investitionssumme_gesamt'] == 0:
        st.warning("Die Gesamtinvestitionskosten (GIK) sind 0. Bitte geben Sie die Daten ein, um die Berechnung zu starten.")
        return

    if 'finanzierung_hinweis' in results:
        st.warning(results['finanzierung_hinweis'])

    # --- 1. Prominente KPIs ---
    display_kpi_section(results)
    
    # --- PDF Download Button ---
    if PDF_EXPORT_ENABLED:
        try:
            # Generate PDF on the fly when needed for download
            with st.spinner("Generiere PDF-Bericht (Querformat)..."):
                pdf_buffer = create_pdf_report(results, params)
            
            if pdf_buffer:
                # Bereinige den Objektnamen für den Dateinamen
                safe_filename = "".join([c for c in params['objekt_name'] if c.isalnum() or c in (' ', '-', '_')]).rstrip().replace(' ', '_')
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

    # --- 2. Tabs für Detailergebnisse (Namen angepasst) ---
    tab_overview, tab_investment, tab_finance_value, tab_cashflow, tab_tax = st.tabs([
        "Übersicht",
        "Investition & AfA",
        "Finanzierung & Wertentwicklung",
        "Cashflow-Entwicklung",
        "Steuern"
    ])

    with tab_overview:
        display_overview(results)

    with tab_investment:
        display_investment_details(results)

    with tab_finance_value:
        display_finance_value_dev(results)

    with tab_cashflow:
        display_cashflow_details(results)

    with tab_tax:
        display_tax_details(results)

def display_kpi_section(results):
    """Zeigt die wichtigsten KPIs in der gewünschten Reihenfolge."""
    st.markdown('<div class="prominent-kpi-container">', unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)

    # 1. Kaufpreis/m² (Netto)
    with col1:
        st.metric("Kaufpreis/m² (Netto)", format_euro(results['kpi_nettokaufpreis_qm_netto'], 0))
        st.caption("KP nach KfW-Zuschüssen/m²")

    # 2. Kaufpreis/m² (Brutto)
    with col2:
        st.metric("Kaufpreis/m² (Brutto)", format_euro(results['kpi_nettokaufpreis_qm_brutto'], 0))
        st.caption("GIK (brutto) / Wohnfläche.")

    # 3. KfW-Zuschuss Gesamt
    with col3:
        st.metric("KfW-Zuschuss Gesamt", format_euro(results['gesamtzuschuss'], 0))
        st.caption("Tilgungszuschuss + Zuschuss BB")

    # 4. IRR nach Steuer
    with col4:
        irr_value = results['kpi_irr_nach_steuer']
        if isinstance(irr_value, float):
            st.metric("IRR nach Steuer", format_percent(irr_value))
        else:
            st.metric("IRR nach Steuer", irr_value)
        st.caption(f"über Haltedauer von {st.session_state['geplanter_verkauf']} Jahren.")

    st.markdown('</div>', unsafe_allow_html=True)

def display_overview(results):
    """Zeigt eine Zusammenfassung."""
    st.subheader("Zusammenfassung der Investition")

    col1, col2 = st.columns(2)

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
        st.markdown("#### Finanzierungsstruktur")
        st.markdown('<div class="calculation-breakdown">', unsafe_allow_html=True)
        st.text(format_aligned_line("Eigenkapital:", format_euro(results['eigenkapital_bedarf'], 0)))
        st.text(format_aligned_line("+ Bankdarlehen:", format_euro(results['bankdarlehen'], 0)))
        # Zeigt das gesamte KfW Darlehen (Basis + BB)
        st.text(format_aligned_line("+ KfW-Darlehen (Gesamt):", format_euro(results['kfw_darlehen'], 0)))
        st.markdown('<div class="breakdown-intermediate">', unsafe_allow_html=True)
        st.text(format_aligned_line("= Summe Finanzierung:", format_euro(results['investitionssumme_gesamt'], 0)))
        st.markdown('</div></div>', unsafe_allow_html=True)

def display_investment_details(results):
    """Details zur Investition und AfA."""
    st.subheader("AfA-Bemessungsgrundlage")
    st.info("Basis: GIK Netto + Erwerbsnebenkosten (GrESt, Notar/Grundbuch) + aktivierte Baubegleitung.")

    st.markdown('<div class="calculation-breakdown">', unsafe_allow_html=True)
    LW = 35
    st.text(format_aligned_line("GIK Netto:", format_euro(results['gik_netto'], 0), LW))
    st.text(format_aligned_line("+ Erwerbsnebenkosten (Aktiviert):", format_euro(results['erwerbsnebenkosten'], 0), LW))
    st.text(format_aligned_line("+ Aktivierte Baubegleitung:", format_euro(results['aktivierung_baubegleitung'], 0), LW))
    st.markdown('<div class="breakdown-intermediate">', unsafe_allow_html=True)
    st.text(format_aligned_line("= AfA-Basis Gesamt (Check):", format_euro(results['afa_basis_summe_check'], 0), LW))
    st.markdown('</div></div>', unsafe_allow_html=True)

    st.markdown("#### Aufteilung der AfA-Basis")
    
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Grundstücksanteil (Keine AfA)", format_euro(results['afa_basis_grundstueck'], 0))
    with col2:
        st.metric(f"Sanierungskostenanteil ({AFA_TYP}-AfA)", format_euro(results['afa_basis_sanierung'], 0))
        st.caption("Erhöhte Abschreibung (§ 7h/i EStG). Inkl. aktivierter Baubegleitung.")
    with col3:
        st.metric(f"Altbausubstanz ({format_percent(AFA_ALTBAU_SATZ)} linear)", format_euro(results['afa_basis_altbau'], 0))
        st.caption("Lineare Gebäude-AfA (§ 7 Abs. 4 EStG).")


def display_finance_value_dev(results):
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
        # Zeigt das Gesamtdarlehen und die Basis
        st.metric("KfW-Darlehenssumme (Gesamt)", format_euro(results['kfw_darlehen'], 0))
        st.caption(f"Davon Basis-Darlehen: {format_euro(results['kfw_darlehen_basis'], 0)}")

        st.metric("Zinssatz KfW", format_percent(st.session_state.kfw_zins_pct / 100.0))
        st.metric(f"Tilgungszuschuss (auf Basis)", format_euro(results['kfw_tilgungszuschuss'], 0))
        st.metric("Zuschuss Baubegleitung", format_euro(results['zuschuss_baubegleitung'], 0))
        st.metric("Laufzeit / Tilgungsfrei", f"{st.session_state.kfw_gesamtlaufzeit} Jahre / {st.session_state.kfw_tilgungsfreie_jahre} Jahre")

    
    # --- Tilgungspläne ---
    st.subheader("Tilgungsplan (Zins, Tilgung, Restschuld)")
    
    df = results['projection_df']

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
    else:
        st.warning("Daten für Wertentwicklung nicht vollständig.")

    st.info(
        "Wenn Sie die Immobilie als Privatperson erworben haben, können Sie diese nach zehn Jahren steuerfrei veräußern. "
        "Bei Immobilien, die im Betriebsvermögen einer Kapital- oder Personengesellschaft gehalten werden, ist eine steuerfreie Veräußerung hingegen nicht möglich. "
        "In beiden Fällen wird der volle Steuervorteil aus der Sonder-AfA bei einer Haltedauer von zwölf Jahren erreicht."
    )


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
    df = results['projection_df']

    if not df.empty:
        display_cols = [
            'Mieteinnahmen (Netto)', 'Betriebskosten', 'Einnahmenüberschuss', 
            'Annuität Gesamt', 'Cashflow vor Steuer', 'Steuerersparnis', 'Cashflow nach Steuer'
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
    
    st.metric("Angenommener Grenzsteuersatz (Brutto, inkl. Soli/KiSt)", format_percent(results['grenzsteuersatz_brutto']))
    
    if st.session_state.steuer_modus == 'Basis Einkommen (zvE)':
        st.info("Hinweis: Die Berechnung basiert auf einem angenommenen Grenzsteuersatz von 42% (netto). Eine exakte Ermittlung aus dem zvE ist nicht implementiert.")

    # --- Kumulierte Werte ---
    st.subheader("Kumulierte Steuerersparnis")
    df = results['projection_df']
    
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
        if len(df) >= haltedauer:
             cum_tax_saving_total = df['Steuerersparnis'].head(haltedauer).sum()
             st.metric(f"Gesamt nach Haltedauer ({haltedauer} J.)", format_euro(cum_tax_saving_total, 0))


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
            # Apply formatting only to numeric columns
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
    # Muss vor dem ersten Widget-Aufruf erfolgen, damit Callbacks funktionieren
    initialize_session_state()
    set_custom_style()

    st.title("Park 55 Immobilienrechner")

    # Einführungstext (Angepasst)
    st.info("Wählen Sie ein Objekt aus oder starten Sie eine freie Berechnung (über 'Manuelle Eingabe'). Die Berechnung wird automatisch bei jeder Änderung der Eingabeparameter durchgeführt.")

    # Optionale Warnings
    if not IRR_ENABLED:
        st.error("Modul 'numpy_financial' nicht gefunden. Bitte 'pip install numpy-financial' ausführen.")
    if not PDF_EXPORT_ENABLED:
        st.warning("PDF Export ist deaktiviert. Bitte 'pip install reportlab' ausführen.")

    # ----------------------------------------------------------------
    # ANWENDUNGSLOGIK
    # ----------------------------------------------------------------

    # 1. Input-Widgets (Sidebar) anzeigen.
    gik_is_valid, kfw_is_valid = display_sidebar_inputs()

    # 2. Aufruf der Berechnung und Anzeige der Ergebnisse

    if not gik_is_valid:
        st.error("Berechnung nicht möglich: GIK-Aufteilung > 100%.")
    else:
        # Berechnung durchführen
        try:
            # st.session_state enthält die Inputs (entweder aus CSV oder manuell geändert)
            results, params = run_calculations(st.session_state)
            # Ergebnisse anzeigen
            display_results(results, params)
            
        except RuntimeError as e:
            st.error(f"Berechnungsfehler: {e}.")
            logging.error(traceback.format_exc())
        except Exception as e:
            st.error(f"Ein unerwarteter Fehler ist während der Berechnung aufgetreten.")
            logging.error("Fehler bei der Berechnung:")
            logging.error(traceback.format_exc())

if __name__ == '__main__':
    # Globale Fehlerbehandlung
    try:
        main() 
    except Exception as e:
        st.error("Ein unerwarteter technischer Fehler ist aufgetreten.")
        logging.error(traceback.format_exc())
