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
        df['Objektname'] = df_raw['Strasse'] + " " + df_raw['Haus