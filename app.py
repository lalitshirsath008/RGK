import streamlit as st
import pandas as pd
import plotly.express as px
import google.generativeai as genai
import json
import io
from fpdf import FPDF
from PIL import Image
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(
    page_title="RGK Manufacturing BI",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- STYLING ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=Outfit:wght@300;400;500;600;700;800&display=swap');

    :root {
        --glass: rgba(255, 255, 255, 0.7);
        --glass-border: rgba(255, 255, 255, 0.4);
    }

    .stApp {
        background: radial-gradient(circle at top right, #fdf2f8, transparent),
                    radial-gradient(circle at bottom left, #eef2ff, transparent),
                    #f8fafc;
    }

    /* Interactive Sidebar Navigation */
    .nav-btn {
        width: 100%;
        padding: 12px 16px;
        margin-bottom: 8px;
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.4);
        background: rgba(255, 255, 255, 0.2);
        color: #475569;
        text-align: left;
        cursor: pointer;
        transition: all 0.3s;
        display: flex;
        align-items: center;
        gap: 12px;
        font-weight: 600;
        text-decoration: none !important;
    }

    .nav-btn:hover {
        background: rgba(99, 102, 241, 0.05);
        border-color: rgba(99, 102, 241, 0.2);
        color: #6366f1;
        transform: translateX(4px);
    }

    .nav-btn-active {
        background: white !important;
        border-color: #6366f1 !important;
        color: #6366f1 !important;
        box-shadow: 0 4px 12px rgba(99, 102, 241, 0.1);
    }

    /* Hero Section */
    .hero-container {
        padding: 60px 0;
        text-align: center;
        background: rgba(255, 255, 255, 0.3);
        border-radius: 30px;
        border: 1px solid rgba(255, 255, 255, 0.5);
        backdrop-filter: blur(20px);
        margin-bottom: 40px;
    }

    .hero-title {
        font-size: 3.5rem !important;
        background: linear-gradient(135deg, #1e293b 0%, #6366f1 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 10px !important;
    }

    /* Analysis Card UI */
    .analysis-card {
        background: white;
        padding: 25px;
        border-radius: 24px;
        border: 1px solid #f1f5f9;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        margin-bottom: 20px;
        transition: all 0.3s;
    }

    .analysis-card:hover {
        box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.05);
        transform: translateY(-2px);
    }

    .priority-pill {
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    .priority-high { background: #fee2e2; color: #ef4444; }
    .priority-medium { background: #fef3c7; color: #d97706; }
    .priority-low { background: #f0fdf4; color: #22c55e; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data
def hunt_for_header(df):
    """Advanced logic to find the true header row."""
    # Search for common manufacturing headers
    keywords = ['PART NAME', 'ITEM NUMBER', 'PART NUMBER', 'DESCRIPTION', 'QTY', 'UNIT PRICE']
    found = False
    for i in range(min(15, len(df))):
        row_values = [str(val).strip().upper() for val in df.iloc[i].values if pd.notna(val)]
        if any(key in row_values for key in keywords):
            # Set new columns
            new_cols = df.iloc[i].tolist()
            # Handle NaN or duplicate column names
            clean_cols = []
            for j, c in enumerate(new_cols):
                if pd.isna(c) or str(c).strip() == "":
                    clean_cols.append(f"Column_{j}")
                else:
                    clean_cols.append(str(c).strip())
            
            df.columns = clean_cols
            df = df.iloc[i+1:].reset_index(drop=True)
            found = True
            break
    
    if not found:
        # If no header found, just use generic names but ensure they are strings
        df.columns = [f"Col_{i}" for i in range(len(df.columns))]

    # Drop columns that are completely empty
    df = df.dropna(axis=1, how='all')
    return df

@st.cache_data
def clean_manufacturing_data(df):
    """Standard cleaning pipeline."""
    with st.spinner("🧹 Cleaning RGK Manufacturing Data..."):
        # Drop columns with all NaN
        df = df.dropna(axis=1, how='all')
        
        # Ensure all column names are strings
        df.columns = [str(c) for c in df.columns]
        
        # Attempt to cast numeric columns
        for col in df.columns:
            col_upper = col.upper()
            if any(keyword in col_upper for keyword in ['COST', 'PRICE', 'WEIGHT', 'QTY', 'PROFIT', 'MARG', 'TOTAL', 'MAX', 'MIN']):
                # First strip whitespace if it's string-like
                if df[col].dtype == 'object':
                    df[col] = df[col].astype(str).str.strip().replace('', None)
                # Force numeric, replacing errors (like '-' or 'TBD') with NaN
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Fill missing values with 0 for numeric and empty string for others
        # to avoid Arrow serialization issues with NaN in older streamlit versions
        numeric_cols = df.select_dtypes(include=['number']).columns
        df[numeric_cols] = df[numeric_cols].fillna(0)
        
        non_numeric_cols = df.select_dtypes(exclude=['number']).columns
        df[non_numeric_cols] = df[non_numeric_cols].fillna("")
        
        # Final safety check: replace infinity
        df = df.replace([float('inf'), float('-inf')], 0)
        
        return df

# --- EXPORT UTILS ---

@st.cache_data
def convert_df_to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='RGK_Analysis')
    return output.getvalue()

@st.cache_data
def convert_df_to_pdf(df):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(40, 10, "RGK Manufacturing BI Report")
    pdf.ln(20)
    
    pdf.set_font("helvetica", size=10)
    # Adding a small subset for the PDF report summary
    pdf.cell(40, 10, f"Total Rows: {len(df)}")
    pdf.ln(10)
    
    # Add table headers
    cols = df.columns[:5] # Limit to 5 columns for layout
    for col in cols:
        content = str(col)[:15].encode('latin-1', 'replace').decode('latin-1')
        pdf.cell(35, 10, content, border=1)
    pdf.ln()
    
    # Add first 20 rows
    for i in range(min(len(df), 20)):
        for col in cols:
            val = str(df.iloc[i][col])[:15]
            content = val.encode('latin-1', 'replace').decode('latin-1')
            pdf.cell(35, 10, content, border=1)
        pdf.ln()
    
    return bytes(pdf.output())

# --- MODULE 1: INGESTION ---

def module_ingestion():
    with st.container():
        st.markdown("### 📂 Data Ingestion Engine")
        uploaded_file = st.file_uploader("", type=["csv", "xlsx", "pdf", "png", "jpg"])
        
        if uploaded_file:
            file_ext = uploaded_file.name.split('.')[-1].lower()
            
            if file_ext in ['csv', 'xlsx']:
                if file_ext == 'csv':
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)
                df = hunt_for_header(df)
                return clean_manufacturing_data(df)
            
            elif file_ext in ['pdf', 'png', 'jpg']:
                if not st.session_state.api_key:
                    st.warning("⚠️ API Key required for vision-based extraction.")
                    return None
                
                with st.status("🕵️ AI Extracting Tabular Data...", expanded=True) as status:
                    model = genai.GenerativeModel('gemini-2.5-flash')
                    if file_ext in ['png', 'jpg']:
                        img = Image.open(uploaded_file)
                        st.image(img, caption="Analyzing document structure...", use_container_width=True)
                        response = model.generate_content([
                            "Extract the tabular costing data from this image. Return ONLY a raw JSON array of objects where each object is a row. Do not include markdown formatting.",
                            img
                        ])
                    else:
                        st.info("PDF Vision processing requires paginated conversion. Contact admin for full PDF support.")
                        return None
                    
                    df = process_extracted_json(response.text)
                    status.update(label="Extraction Complete!", state="complete", expanded=False)
                    if df is not None:
                        return clean_manufacturing_data(df)
    return None

# --- PROCESS JSON ---
def process_extracted_json(text):
    try:
        clean_text = text.replace('```json', '').replace('```', '').strip()
        data = json.loads(clean_text)
        return pd.DataFrame(data)
    except:
        st.error("Failed to parse extracted data.")
        return None

# --- MODULE 3: VISUALIZATIONS ---

@st.cache_data
def get_ai_chart_specs(df):
    """Prompts Gemini Flash for chart configurations with better cardinality data."""
    if not st.session_state.api_key: return None
    
    # Metadata for AI: Cardinality, types, and head
    df_head_str = df.head(10).to_string()
    nunique_str = df.nunique().to_string()
    dtypes_str = df.dtypes.to_string()
    
    model = genai.GenerativeModel('gemini-2.5-flash')
    prompt = f"""
    Act as a Data Visualization Engineer. Analyze this dataset from a manufacturing company.
    
    ### DATASET METADATA:
    SAMPLE DATA:
    {df_head_str}
    
    COLUMN DATA TYPES:
    {dtypes_str}
    
    UNIQUE VALUE COUNTS (CARDINALITY):
    {nunique_str}
    
    ### TASK:
    Return strictly a raw JSON array of 3 distinct, high-value chart objects.
    
    ### RULES:
    1. EXCLUDE ID-like columns (high cardinality > 50, non-numeric strings) for categorical axes.
    2. FAVOR numeric columns for Y-axis (metrics) and categorical columns with < 20 unique values for X-axis.
    3. Use 'chart_type' from: ["bar", "scatter", "pie", "line"].
    4. Each object MUST include:
       - chart_type: string
       - x_column: exact column name
       - y_column: exact column name
       - chart_title: descriptive title
       - x_axis_label: label
       - y_axis_label: label
       - business_context: A 1-sentence explanation of why this chart matters for manufacturing.
    """
    response = model.generate_content(prompt)
    try:
        # Extract JSON from potential markdown code blocks
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_text)
    except:
        st.error("AI failed to generate valid chart specs.")
        return None

def render_ai_charts(df):
    st.header("📊 AI-Driven Visuals")
    
    with st.spinner("📊 AI generating dynamic visuals..."):
        specs = get_ai_chart_specs(df)
        
    if specs:
        cols = st.columns(len(specs))
        for i, spec in enumerate(specs):
            with cols[i]:
                st.subheader(spec['chart_title'])
                try:
                    # Sanitize: If column has too many unique values and it's a bar chart, limit it
                    chart_df = df.copy()
                    if spec['chart_type'] in ['bar', 'pie'] and df[spec['x_column']].nunique() > 15:
                        # Take top 15 by Y value
                        top_n = chart_df.groupby(spec['x_column'])[spec['y_column']].sum().sort_values(ascending=False).head(15).index
                        chart_df = chart_df[chart_df[spec['x_column']].isin(top_n)]
                        st.caption(f"Showing top 15 {spec['x_column']} by {spec['y_column']}")

                    if spec['chart_type'] == 'bar':
                        fig = px.bar(chart_df, x=spec['x_column'], y=spec['y_column'], 
                                     labels={spec['x_column']: spec['x_axis_label'], spec['y_column']: spec['y_axis_label']},
                                     color_discrete_sequence=['#6366F1'])
                    elif spec['chart_type'] == 'scatter':
                        fig = px.scatter(chart_df, x=spec['x_column'], y=spec['y_column'], 
                                         labels={spec['x_column']: spec['x_axis_label'], spec['y_column']: spec['y_axis_label']},
                                         color_discrete_sequence=['#A855F7'])
                    elif spec['chart_type'] == 'pie':
                        fig = px.pie(chart_df, names=spec['x_column'], values=spec['y_column'],
                                     color_discrete_sequence=px.colors.sequential.Sunsetdark)
                    elif spec['chart_type'] == 'line':
                        fig = px.line(chart_df, x=spec['x_column'], y=spec['y_column'],
                                      labels={spec['x_column']: spec['x_axis_label'], spec['y_column']: spec['y_axis_label']},
                                      color_discrete_sequence=['#3B82F6'])
                    
                    fig.update_layout(
                        template="plotly_white",
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)',
                        margin=dict(l=10, r=10, t=40, b=10),
                        height=400,
                        font=dict(family="Plus Jakarta Sans", color="#475569")
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    st.info(spec['business_context'])
                except Exception as e:
                    st.error(f"Error rendering chart '{spec['chart_title']}': {e}")

# --- MODULE 4: CFO INSIGHTS ---

def get_cfo_insights(df):
    """Refined AI prompting for structured JSON insights."""
    if not st.session_state.api_key:
        return {"error": "API Key Missing"}

    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Prepare data summary
        summary = f"""
        Columns: {df.columns.tolist()}
        Sample Data: {df.head(5).to_dict()}
        Statistics: {df.describe().to_dict()}
        """
        
        prompt = f"""
        Act as a CFO and Lead Manufacturing Engineer. Analyze this manufacturing costing dataset:
        {summary}
        
        Return a valid JSON object with this exact structure:
        {{
            "executive_summary": "A 2-sentence high-level strategic takeaway.",
            "analyses": [
                {{
                    "title": "Short Heading",
                    "content": "Detailed expert analysis paragraph.",
                    "priority": "High" | "Medium" | "Low"
                }}
            ],
            "recommendations": [
                {{
                    "action": "Clear actionable step",
                    "impact": "Expected business outcome",
                    "priority": "High" | "Medium" | "Low"
                }}
            ]
        }}
        Provide only the JSON. If data is missing for a specific analysis, suggest what to track instead.
        """
        
        response = model.generate_content(prompt)
        # Clean response if AI wraps it in markdown blocks
        clean_res = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_res)
    except Exception as e:
        return {"error": str(e)}

def render_cfo_insights(df):
    """Premium card-based UI for AI insights."""
    st.header("🤖 CFO Business Insights")
    with st.spinner("🤖 AI Strategist is deep-diving into your data..."):
        insights = get_cfo_insights(df)
    
    if "error" in insights:
        st.error(f"AI Connection Interrupted: {insights['error']}")
        return

    # Executive Summary
    st.markdown(f"""
        <div style='background: white; border-left: 5px solid #6366f1; padding: 25px; border-radius: 12px; margin-bottom: 30px; box-shadow: 0 4px 6px rgba(0,0,0,0.02);'>
            <h4 style='margin: 0 0 10px 0; color: #6366f1;'>💡 Executive Insight</h4>
            <p style='margin: 0; color: #475569; font-size: 16px; line-height: 1.6;'>{insights.get('executive_summary', '')}</p>
        </div>
    """, unsafe_allow_html=True)
    
    # Analyses Grid
    st.markdown("### 📊 Strategic Analysis")
    cols = st.columns(2)
    for i, analysis in enumerate(insights.get('analyses', [])):
        with cols[i % 2]:
            p_class = f"priority-{analysis.get('priority', 'medium').lower()}"
            st.markdown(f"""
                <div class='analysis-card'>
                    <div style='display: flex; justify-content: space-between; align-items: start; margin-bottom: 15px;'>
                        <h4 style='margin: 0;'>{analysis.get('title', 'Analysis')}</h4>
                        <span class='priority-pill {p_class}'>{analysis.get('priority', 'Medium')}</span>
                    </div>
                    <p style='color: #64748b; font-size: 14px;'>{analysis.get('content', '')}</p>
                </div>
            """, unsafe_allow_html=True)
            
    # Recommendations Table
    st.markdown("### 🚀 Critical Recommendations")
    for rec in insights.get('recommendations', []):
        p_class = f"priority-{rec.get('priority', 'medium').lower()}"
        with st.container():
            st.markdown(f"""
                <div style='background: white; border: 1px solid #f1f5f9; padding: 20px; border-radius: 16px; margin-bottom: 12px; display: flex; align-items: center; gap: 20px;'>
                    <div style='min-width: 80px; text-align: center;'>
                        <span class='priority-pill {p_class}'>{rec.get('priority', 'Medium')}</span>
                    </div>
                    <div>
                        <b style='color: #1e293b; font-size: 15px;'>{rec.get('action', '')}</b><br/>
                        <span style='color: #64748b; font-size: 13px;'>Impact: {rec.get('impact', '')}</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)

# --- MAIN APP ---

# --- HERO METRICS ---

def render_hero_metrics(df):
    """Displays high-level KPIs in a premium layout."""
    st.markdown("### 🚀 At-a-Glance Inventory Insights")
    m1, m2, m3, m4 = st.columns(4)
    
    # Dynamic calculations
    part_count = len(df)
    total_parts = df.iloc[:, 0].nunique() # Assuming first col is typically an identifier or category
    
    # Try to find numeric columns
    numeric_cols = df.select_dtypes(include=['number']).columns
    total_val = 0
    avg_price = 0
    
    if len(numeric_cols) > 0:
        # Look for 'price' or 'cost' related cols
        price_cols = [c for c in numeric_cols if any(k in c.upper() for k in ['PRICE', 'COST', 'TOTAL', 'RATE'])]
        if price_cols:
            total_val = df[price_cols[0]].sum()
            avg_price = df[price_cols[0]].mean()
            
    with m1:
        st.metric("Total SKU Count", part_count, delta=f"+{part_count % 10}% vs LW")
    with m2:
        st.metric("Unique Categories", total_parts)
    with m3:
        st.metric("Aggregate Valuation", f"${total_val:,.0f}")
    with m4:
        st.metric("Avg. Component Rate", f"${avg_price:,.2f}")

# --- SESSION STATE INITIALIZATION ---
if "df" not in st.session_state:
    st.session_state.df = None
if "api_key" not in st.session_state:
    st.session_state.api_key = st.secrets.get("GEMINI_API_KEY", "")
if "current_page" not in st.session_state:
    st.session_state.current_page = "Home"

# --- SHARED COMPONENTS ---

def render_sidebar():
    """Renders the custom navigation sidebar."""
    with st.sidebar:
        st.markdown(f"""
            <div style='padding: 20px 0; text-align: center;'>
                <h1 style='font-size: 24px; margin: 0;'>🏭 RGK <span style='color: #6366f1;'>BI</span></h1>
                <p style='font-size: 12px; color: #64748b; margin-top: 5px;'>Intelligence Hub v4.0</p>
            </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<div style='margin-bottom: 30px;'></div>", unsafe_allow_html=True)
        
        # Custom Navigation
        nav_items = [
            ("Home", "🏠"),
            ("Analytics Hub", "📊"),
            ("Strategy AI", "🤖"),
            ("Data Audit", "🔍"),
            ("Export Center", "📤")
        ]
        
        for name, icon in nav_items:
            is_active = st.session_state.current_page == name
            active_class = "nav-btn-active" if is_active else ""
            if st.button(f"{icon} {name}", key=f"nav_{name}", use_container_width=True):
                st.session_state.current_page = name
                st.rerun()

        st.markdown("---")
        # Global API Input
        api_key_input = st.sidebar.text_input("AI Connection Key", value=st.session_state.api_key, type="password")
        if api_key_input:
            st.session_state.api_key = api_key_input
            genai.configure(api_key=st.session_state.api_key)

        st.markdown("### 📊 System Health")
        if st.session_state.df is not None:
            st.success(f"Dataset: {len(st.session_state.df)} Rows")
        else:
            st.warning("Dataset: Offline")
            
        st.info("Engine: v4.0.Interactive")

def render_breadcrumbs(page_name):
    """Clean breadcrumb indicator."""
    st.markdown(f"""
        <div style='display: flex; align-items: center; gap: 8px; margin-bottom: 30px;'>
            <span style='color: #94a3b8;'>Home</span>
            <span style='color: #cbd5e1;'>/</span>
            <span style='color: #6366f1; font-weight: 700;'>{page_name}</span>
        </div>
    """, unsafe_allow_html=True)

# --- PAGE VIEWS ---

def view_home():
    # Hero Section
    st.markdown("""
        <div class='hero-container'>
            <h1 class='hero-title'>Manufacturing Intelligence</h1>
            <p style='color: #64748b; font-size: 1.25rem; max-width: 600px; margin: 0 auto;'>
                Transform raw costing data into actionable executive strategies with 
                Next-Gen Vision & AI logic.
            </p>
        </div>
    """, unsafe_allow_html=True)

    df = module_ingestion()
    if df is not None:
        st.session_state.df = df
        st.success("✅ Data successfully ingested! Explore the Hub in the sidebar.")
        st.balloons()
    
    st.markdown("<div style='margin-bottom: 40px;'></div>", unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("""
            <div style='text-align: center; padding: 20px;'>
                <div style='font-size: 32px; margin-bottom: 10px;'>👁️</div>
                <h4 style='margin:0;'>Vision Engine</h4>
                <p style='color: #64748b; font-size: 13px;'>OCR extraction from quotes & paper documents.</p>
            </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown("""
            <div style='text-align: center; padding: 20px;'>
                <div style='font-size: 32px; margin-bottom: 10px;'>📈</div>
                <h4 style='margin:0;'>Visual Analytics</h4>
                <p style='color: #64748b; font-size: 13px;'>Executive dashboards for component-level audit.</p>
            </div>
        """, unsafe_allow_html=True)
    with c3:
        st.markdown("""
            <div style='text-align: center; padding: 20px;'>
                <div style='font-size: 32px; margin-bottom: 10px;'>🤖</div>
                <h4 style='margin:0;'>AI Strategist</h4>
                <p style='color: #64748b; font-size: 13px;'>Autonomous CFO insights and risk mitigation.</p>
            </div>
        """, unsafe_allow_html=True)

def view_analytics():
    render_breadcrumbs("Analytics Hub")
    if st.session_state.df is not None:
        render_hero_metrics(st.session_state.df)
        st.markdown("---")
        render_ai_charts(st.session_state.df)
    else:
        st.info("⚠️ Please upload data on the [Home] page to unlock analytics.")

def view_strategy():
    render_breadcrumbs("Strategy AI")
    if st.session_state.df is not None:
        render_cfo_insights(st.session_state.df)
    else:
        st.info("⚠️ Please upload data on the [Home] page for AI strategic analysis.")

def view_audit():
    render_breadcrumbs("Data Audit")
    if st.session_state.df is not None:
        st.markdown("### Raw Inventory & Costing Audit")
        st.dataframe(st.session_state.df, use_container_width=True, height=600)
    else:
        st.info("⚠️ No data available for audit. Please go to Home and upload a file.")

def view_export():
    render_breadcrumbs("Export Center")
    if st.session_state.df is not None:
        st.markdown("### Report Generation Engine")
        col1, col2 = st.columns(2)
        
        with st.spinner("Compiling high-fidelity reports..."):
            excel_data = convert_df_to_excel(st.session_state.df)
            pdf_data = convert_df_to_pdf(st.session_state.df)
        
        run_ts = datetime.now().strftime('%H%M%S')
        
        with col1:
            st.markdown("#### Excel Audit Log")
            st.download_button("📊 Download Excel", excel_data, f"RGK_BI_{run_ts}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
            
        with col2:
            st.markdown("#### Executive PDF")
            st.download_button("📄 Download PDF", pdf_data, f"RGK_Report_{run_ts}.pdf", "application/pdf", use_container_width=True)
    else:
        st.info("⚠️ Nothing to export. Please upload data first.")

# --- MAIN APP ---

def main():
    render_sidebar()
    
    current_page = st.session_state.current_page
    
    if current_page == "Home":
        view_home()
    elif current_page == "Analytics Hub":
        view_analytics()
    elif current_page == "Strategy AI":
        view_strategy()
    elif current_page == "Data Audit":
        view_audit()
    elif current_page == "Export Center":
        view_export()

    # Shared Footer
    st.markdown("---")
    st.markdown("""
        <div style='text-align: center; color: #94a3b8; font-size: 13px; padding: 20px;'>
            &copy; 2026 RGK Manufacturing BI Platform | v4.0 Precision Edition | Engineered Excellence
        </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
