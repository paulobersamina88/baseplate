import math
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title='AISC Base Plate Design App', layout='wide')

APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / 'data'

# -----------------------------
# Data loading
# -----------------------------

def load_builtin_csv(name: str) -> pd.DataFrame:
    path = DATA_DIR / name
    return pd.read_csv(path)


def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def choose_database(section_family: str, uploaded_file):
    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            df = clean_columns(df)
            return df, 'Uploaded CSV'
        except Exception as e:
            st.warning(f'Could not read uploaded CSV. Using built-in database instead. Details: {e}')

    if section_family == 'WF':
        return clean_columns(load_builtin_csv('wf_sections.csv')), 'Built-in WF database'
    if section_family == 'HSS Rectangular / Square':
        return clean_columns(load_builtin_csv('hss_rect_sections.csv')), 'Built-in HSS Rectangular/Square database'
    return clean_columns(load_builtin_csv('pipe_round_sections.csv')), 'Built-in PIPE / Round HSS database'


# -----------------------------
# Engineering helpers
# -----------------------------

def min_sqrt_ratio(A2: float, A1: float) -> float:
    if A1 <= 0:
        return 1.0
    return min(math.sqrt(max(A2 / A1, 0.0)), 2.0)


def concrete_bearing_strength(fc_ksi: float, A1: float, A2: float, method: str):
    """
    AISC 360 J8 style concrete bearing strength.
    fc in ksi, A1 and A2 in in^2, result in kips.
    """
    ratio = min_sqrt_ratio(A2, A1)
    if method == 'ASD':
        omega_c = 2.50
        strength = (0.85 * fc_ksi * A1 * ratio) / omega_c
        return strength, {'omega_c': omega_c, 'phi_c': None, 'ratio': ratio}
    phi_c = 0.65
    strength = phi_c * 0.85 * fc_ksi * A1 * ratio
    return strength, {'omega_c': None, 'phi_c': phi_c, 'ratio': ratio}


def wf_geometry(N: float, B: float, d: float, bf: float, load: float, bearing_strength: float):
    m = 0.5 * (N - 0.95 * d)
    n = 0.5 * (B - 0.80 * bf)
    n_prime = 0.25 * math.sqrt(d * bf)

    x_geom = 4 * d * bf / ((d + bf) ** 2) if (d + bf) > 0 else 1.0
    x_load = load / bearing_strength if bearing_strength > 0 else 1.0
    x = min(x_geom * x_load, 1.0)

    if x >= 1.0:
        lam = 1.0
    else:
        lam = min((2 * math.sqrt(x)) / (1 + math.sqrt(1 - x)), 1.0)

    governing_projection = max(m, n, lam * n_prime)
    return {
        'm': m,
        'n': n,
        'n_prime': n_prime,
        'x': x,
        'lambda': lam,
        'governing_projection': governing_projection,
    }


def rect_hss_geometry(N: float, B: float, h: float, b: float):
    # Conservative plate cantilever projection from HSS outer wall.
    m = 0.5 * (N - h)
    n = 0.5 * (B - b)
    governing_projection = max(m, n)
    return {
        'm': m,
        'n': n,
        'governing_projection': governing_projection,
    }


def pipe_geometry(N: float, B: float, od: float):
    edge_n = 0.5 * (N - od)
    edge_b = 0.5 * (B - od)
    governing_projection = max(edge_n, edge_b)
    return {
        'edge_n': edge_n,
        'edge_b': edge_b,
        'governing_projection': governing_projection,
    }


def required_thickness(governing_projection: float, load: float, N: float, B: float, Fy: float, method: str):
    q = load / (N * B) if N * B > 0 else 0.0  # kip/in^2
    # Similar to common AISC manual presentation for axial compression base plates.
    coeff = 3.33 if method == 'ASD' else 2.50
    t_req = governing_projection * math.sqrt((coeff * q) / Fy) if Fy > 0 else 0.0
    return t_req, q, coeff


def format_pass(ok: bool) -> str:
    return 'PASS' if ok else 'FAIL'


def find_section_row(df: pd.DataFrame, selected: str, key_col: str = 'shape'):
    row = df[df[key_col].astype(str) == selected]
    if row.empty:
        raise ValueError(f'Section {selected} was not found in the selected database.')
    return row.iloc[0].to_dict()


# -----------------------------
# UI
# -----------------------------
st.title('Steel Column Base Plate Design App')
st.caption('Axial compression base plate design following AISC-style procedures for WF, HSS rectangular/square, and PIPE/Round HSS sections.')

with st.sidebar:
    st.header('Design Controls')
    method = st.selectbox('Design method', ['ASD', 'LRFD'])
    section_family = st.selectbox('Section family', ['WF', 'HSS Rectangular / Square', 'PIPE / Round HSS'])
    uploaded_csv = st.file_uploader('Optional: upload section database CSV', type=['csv'])
    st.markdown('**Expected uploaded CSV columns**')
    if section_family == 'WF':
        st.code('shape,d,bf,tw,tf,A,W', language='text')
    elif section_family == 'HSS Rectangular / Square':
        st.code('shape,H,B,t,A,W', language='text')
    else:
        st.code('shape,OD,t,A,W', language='text')


df_sections, db_label = choose_database(section_family, uploaded_csv)
st.info(f'Using: {db_label}')

if 'shape' not in df_sections.columns:
    st.error("The section database must include a 'shape' column.")
    st.stop()

section_list = df_sections['shape'].astype(str).tolist()
if not section_list:
    st.error('No sections found in the database.')
    st.stop()

col1, col2 = st.columns([1.1, 1])

with col1:
    st.subheader('Input Data')
    section_name = st.selectbox('Column section', section_list)

    c1, c2, c3 = st.columns(3)
    with c1:
        load = st.number_input(
            f"{'Service' if method == 'ASD' else 'Factored'} axial compression load ({'kips'})",
            min_value=1.0,
            value=200.0,
            step=10.0,
        )
        Fy = st.number_input('Base plate yield stress, Fy (ksi)', min_value=30.0, value=60.0, step=1.0)
    with c2:
        fc = st.number_input("Concrete strength, f'c (ksi)", min_value=2.0, value=3.0, step=0.5)
        N = st.number_input('Base plate length N (in)', min_value=4.0, value=16.0, step=0.5)
    with c3:
        B = st.number_input('Base plate width B (in)', min_value=4.0, value=16.0, step=0.5)
        A2 = st.number_input('Concrete support area A2 (in²)', min_value=1.0, value=1156.0, step=10.0)

    provided_thickness = st.number_input('Provided base plate thickness (in)', min_value=0.25, value=1.0, step=0.125)

row = find_section_row(df_sections, section_name)

# Extract geometry by family
if section_family == 'WF':
    required_cols = ['d', 'bf']
    missing = [c for c in required_cols if c not in row]
    if missing:
        st.error(f'Missing required WF columns: {missing}')
        st.stop()
    d = float(row['d'])
    bf = float(row['bf'])
    geom = wf_geometry(N, B, d, bf, load, 1.0)  # placeholder, reset later once bearing strength known
    section_summary = {
        'Shape': section_name,
        'Depth d (in)': d,
        'Flange width bf (in)': bf,
        'Area A (in²)': row.get('a', row.get('A', '—')),
        'Weight (lb/ft)': row.get('w', row.get('W', '—')),
    }
elif section_family == 'HSS Rectangular / Square':
    required_cols = ['h', 'b']
    missing = [c for c in required_cols if c not in row]
    if missing:
        st.error(f'Missing required HSS rectangular/square columns: {missing}')
        st.stop()
    h = float(row['h'])
    b = float(row['b'])
    geom = rect_hss_geometry(N, B, h, b)
    section_summary = {
        'Shape': section_name,
        'Outside depth H (in)': h,
        'Outside width B (in)': b,
        'Wall thickness t (in)': row.get('t', '—'),
        'Area A (in²)': row.get('a', row.get('A', '—')),
        'Weight (lb/ft)': row.get('w', row.get('W', '—')),
    }
else:
    required_cols = ['od']
    missing = [c for c in required_cols if c not in row]
    if missing:
        st.error(f'Missing required PIPE / Round HSS columns: {missing}')
        st.stop()
    od = float(row['od'])
    geom = pipe_geometry(N, B, od)
    section_summary = {
        'Shape': section_name,
        'Outside diameter OD (in)': od,
        'Wall thickness t (in)': row.get('t', '—'),
        'Area A (in²)': row.get('a', row.get('A', '—')),
        'Weight (lb/ft)': row.get('w', row.get('W', '—')),
    }

A1 = N * B
bearing_strength, bearing_meta = concrete_bearing_strength(fc, A1, A2, method)
bearing_ok = bearing_strength >= load

if section_family == 'WF':
    geom = wf_geometry(N, B, d, bf, load, bearing_strength)

t_req, q, thickness_coeff = required_thickness(geom['governing_projection'], load, N, B, Fy, method)
thickness_ok = provided_thickness >= t_req

with col2:
    st.subheader('Section Summary')
    st.dataframe(pd.DataFrame([section_summary]), use_container_width=True, hide_index=True)

    st.subheader('Design Summary')
    summary_df = pd.DataFrame([
        {'Item': 'Design method', 'Value': method},
        {'Item': 'Load used (kips)', 'Value': round(load, 3)},
        {'Item': 'Concrete bearing strength (kips)', 'Value': round(bearing_strength, 3)},
        {'Item': 'Bearing check', 'Value': format_pass(bearing_ok)},
        {'Item': 'Uniform bearing pressure q (kip/in²)', 'Value': round(q, 5)},
        {'Item': 'Governing plate projection l (in)', 'Value': round(geom['governing_projection'], 3)},
        {'Item': 'Required plate thickness t_req (in)', 'Value': round(t_req, 3)},
        {'Item': 'Provided plate thickness (in)', 'Value': round(provided_thickness, 3)},
        {'Item': 'Thickness check', 'Value': format_pass(thickness_ok)},
    ])
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

st.markdown('---')

r1, r2 = st.columns(2)

with r1:
    st.subheader('1) Concrete Bearing Check')
    if method == 'ASD':
        st.latex(r"P_{allow} = \frac{0.85 f'_c A_1}{\Omega_c} \min\left(\sqrt{\frac{A_2}{A_1}}, 2\right)")
        st.write(f"Ωc = {bearing_meta['omega_c']:.2f}")
    else:
        st.latex(r"\phi P_n = \phi_c\,0.85 f'_c A_1 \min\left(\sqrt{\frac{A_2}{A_1}}, 2\right)")
        st.write(f"ϕc = {bearing_meta['phi_c']:.2f}")

    bearing_table = pd.DataFrame([
        {'Parameter': 'A1 = N × B (in²)', 'Value': round(A1, 3)},
        {'Parameter': 'A2 (in²)', 'Value': round(A2, 3)},
        {'Parameter': 'min(√(A2/A1), 2)', 'Value': round(bearing_meta['ratio'], 4)},
        {'Parameter': 'Bearing strength (kips)', 'Value': round(bearing_strength, 3)},
        {'Parameter': 'Applied load (kips)', 'Value': round(load, 3)},
        {'Parameter': 'Status', 'Value': format_pass(bearing_ok)},
    ])
    st.dataframe(bearing_table, use_container_width=True, hide_index=True)

with r2:
    st.subheader('2) Plate Projection and Thickness')
    if section_family == 'WF':
        st.latex(r"m = 0.5(N - 0.95d)")
        st.latex(r"n = 0.5(B - 0.80b_f)")
        st.latex(r"n' = 0.25\sqrt{d b_f}")
        st.latex(r"x = \min\left[\left(\frac{4db_f}{(d+b_f)^2}\right)\left(\frac{P_a}{P_p}\right), 1\right]")
        st.latex(r"\lambda = \min\left(\frac{2\sqrt{x}}{1+\sqrt{1-x}}, 1\right)")
        geom_table = pd.DataFrame([
            {'Parameter': 'm (in)', 'Value': round(geom['m'], 3)},
            {'Parameter': 'n (in)', 'Value': round(geom['n'], 3)},
            {'Parameter': "n' (in)", 'Value': round(geom['n_prime'], 3)},
            {'Parameter': 'x', 'Value': round(geom['x'], 4)},
            {'Parameter': 'λ', 'Value': round(geom['lambda'], 4)},
            {'Parameter': 'l = max(m, n, λn′) (in)', 'Value': round(geom['governing_projection'], 3)},
        ])
    elif section_family == 'HSS Rectangular / Square':
        st.latex(r"m = 0.5(N - H)")
        st.latex(r"n = 0.5(B - B_{HSS})")
        geom_table = pd.DataFrame([
            {'Parameter': 'm (in)', 'Value': round(geom['m'], 3)},
            {'Parameter': 'n (in)', 'Value': round(geom['n'], 3)},
            {'Parameter': 'l = max(m, n) (in)', 'Value': round(geom['governing_projection'], 3)},
        ])
    else:
        st.latex(r"e_N = 0.5(N - OD)")
        st.latex(r"e_B = 0.5(B - OD)")
        geom_table = pd.DataFrame([
            {'Parameter': 'Edge projection along N (in)', 'Value': round(geom['edge_n'], 3)},
            {'Parameter': 'Edge projection along B (in)', 'Value': round(geom['edge_b'], 3)},
            {'Parameter': 'l = max(edge projections) (in)', 'Value': round(geom['governing_projection'], 3)},
        ])

    st.dataframe(geom_table, use_container_width=True, hide_index=True)

    st.latex(r"t_{req} = l \sqrt{\frac{C q}{F_y}}")
    st.write(f'Coefficient C used = {thickness_coeff:.2f}')
    thickness_table = pd.DataFrame([
        {'Parameter': 'q = P / (BN) (kip/in²)', 'Value': round(q, 5)},
        {'Parameter': 'Governing projection l (in)', 'Value': round(geom['governing_projection'], 3)},
        {'Parameter': 'Fy (ksi)', 'Value': round(Fy, 3)},
        {'Parameter': 't_req (in)', 'Value': round(t_req, 3)},
        {'Parameter': 't_provided (in)', 'Value': round(provided_thickness, 3)},
        {'Parameter': 'Status', 'Value': format_pass(thickness_ok)},
    ])
    st.dataframe(thickness_table, use_container_width=True, hide_index=True)

st.markdown('---')
st.subheader('Notes and Assumptions')
st.markdown(
    """
- This app is for **axial compression base plates** only.
- The concrete bearing check follows the **AISC 360 J8 style** expression used in common manual workflows.
- The WF procedure follows the same parameter style shown in your screenshot: **m, n, n', x, λ, and l**.
- For **HSS rectangular/square** and **PIPE/Round HSS**, the app uses a conservative plate projection approach based on the clear cantilever projection from the column wall to the plate edge.
- This version does **not yet cover** anchor rod tension, shear, uplift, moment, grout, or pedestal detailing.
- Always perform final engineering review against your preferred AISC Manual / Design Guide workflow and project-specific loading combinations.
"""
)

st.download_button(
    label='Download current section database as CSV',
    data=df_sections.to_csv(index=False).encode('utf-8'),
    file_name=f"{section_family.lower().replace(' / ', '_').replace(' ', '_')}_sections.csv",
    mime='text/csv',
)
