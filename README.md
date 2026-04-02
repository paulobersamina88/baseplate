# AISC Base Plate Design Streamlit App

A Streamlit app for **axial compression steel column base plate design** using an AISC-style workflow.

## Covered section families
- WF (wide flange)
- HSS Rectangular / Square
- PIPE / Round HSS

## Included features
- ASD and LRFD mode
- Section selector from built-in CSV databases
- Optional CSV upload to replace the built-in section database
- Concrete bearing check
- WF base plate geometry using `m`, `n`, `n'`, `x`, `λ`, and governing projection `l`
- HSS rectangular / square and PIPE / round HSS projection-based thickness design
- Required vs provided base plate thickness check
- Clear design summary tables for quick review

## Important scope note
This version is focused on **axial compression only**.
It does **not yet include**:
- anchor rod design
- uplift / tension
- base plate moment from bending or eccentric load
- shear lug design
- grout or pedestal detailing
- seismic anchor design

## Folder contents
- `app.py` - Streamlit application
- `requirements.txt` - Python dependencies
- `data/wf_sections.csv` - built-in WF sample database
- `data/hss_rect_sections.csv` - built-in HSS rectangular/square sample database
- `data/pipe_round_sections.csv` - built-in PIPE/Round HSS sample database

## How to run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Expected uploaded CSV columns
### WF
```text
shape,d,bf,tw,tf,A,W
```

### HSS Rectangular / Square
```text
shape,H,B,t,A,W
```

### PIPE / Round HSS
```text
shape,OD,t,A,W
```

## Engineering notes
- Concrete bearing is based on the common **AISC 360 J8 style** expression used in manual base plate checks.
- WF geometry follows the same parameter style shown in the user sample screenshot.
- HSS rectangular / square and PIPE / round HSS use a conservative clear-projection plate approach.
- Final engineering validation should still be done against your preferred AISC Manual / Design Guide workflow and project-specific load combinations.
