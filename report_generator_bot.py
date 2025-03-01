import streamlit as st
import openai
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os
import pyperclip
from fpdf import FPDF
from datetime import datetime
import json

# Additional library for file processing
import pandas as pd
from io import BytesIO  # for creating the Excel template in memory

# Load environment variables (including your OpenAI API key)
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")


# ------------------------------------------------------------------------------
# Helper functions to normalize and parse keys from an uploaded Excel file
# ------------------------------------------------------------------------------
def normalize_key(s):
    """Normalize a key string by lowercasing and keeping only alphanumeric characters."""
    return ''.join(ch for ch in s.lower() if ch.isalnum())


# Map normalized keys to our internal questionnaire keys.
predefined_keys = {
    "companyname": "company_name",
    "industry": "industry",
    "overview": "overview",
    "governance": "governance",
    "ethics": "ethics",
    "businessmodel": "business_model",
    "strategy": "strategy",
    "stakeholderengagement": "stakeholder_engagement",
    "materiality": "materiality",
    "environmentalperformance": "environmental_performance",
    "environmentaltargets": "environmental_targets",
    "socialperformance": "social_performance",
    "communityengagement": "community_engagement",
    "laborpractices": "labor_practices",
    "humanrights": "human_rights",
    "supplychain": "supply_chain",
    "supplierevaluation": "supplier_evaluation",
    "financialsustainability": "financial_sustainability",
    "reportingframeworks": "reporting_frameworks",
    "dataassurance": "data_assurance",
    "kpi": "kpi",
    "futuregoals": "future_goals",
    "innovation": "innovation",
    "riskmanagement": "risk_management"
}


def parse_uploaded_excel(uploaded_file):
    """
    Parse an uploaded Excel file (XLSX or XLS) and extract key/value pairs.
    It expects the file to contain rows in the format:
      Key | Value
    or the first two columns in each row represent "Key" and "Value".
    """
    result = {}
    try:
        df = pd.read_excel(uploaded_file)
        if 'Key' in df.columns and 'Value' in df.columns:
            for index, row in df.iterrows():
                key_candidate = str(row['Key'])
                value = str(row['Value'])
                norm = normalize_key(key_candidate)
                if norm in predefined_keys:
                    result[predefined_keys[norm]] = value
        else:
            for index, row in df.iterrows():
                key_candidate = str(row.iloc[0])
                value = str(row.iloc[1]) if len(row) > 1 else ""
                norm = normalize_key(key_candidate)
                if norm in predefined_keys:
                    result[predefined_keys[norm]] = value
    except Exception as e:
        st.error(f"Error processing Excel file: {e}")
    return result


# ------------------------------------------------------------------------------
# Custom CSS for a minimalistic, tech-inspired look
# ------------------------------------------------------------------------------
def set_custom_css():
    st.markdown(
        """
        <style>
        .report-container {
            background-color: #F9FAFB;
            padding: 2rem;
            border-radius: 10px;
            border: 1px solid #E5E7EB;
        }
        h1, h2, h3, h4 {
            font-family: "Helvetica Neue", sans-serif;
            color: #111827;
        }
        div.stButton > button {
            background-color: #33505b !important;
            color: white !important;
            border-radius: 6px !important;
            border: none !important;
            font-weight: 600 !important;
        }
        .stProgress > div > div > div > div {
            background-color: #10B981 !important;
        }
        .stAlert {
            border-radius: 6px;
        }
        </style>
        """,
        unsafe_allow_html=True
    )


# ------------------------------------------------------------------------------
# Custom PDF class for nice formatting with header, footer, margins, and A4 format
# ------------------------------------------------------------------------------
class PDF(FPDF):

    def __init__(self, orientation='P', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.set_margins(20, 20, 20)

    def header(self):
        current_year = datetime.now().year
        self.set_font("Times", "B", 12)
        self.set_text_color(50, 50, 50)
        self.cell(0, 10, f"{current_year} Sustainability Report", ln=True, align="C")
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Times", "I", 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 10, f"Page {self.page_no()}", 0, 0, "C")


def create_pdf(report_text, company_name, standard):
    pdf = PDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=20)
    current_year = datetime.now().year
    pdf.set_font("Times", "B", 16)
    pdf.set_text_color(0, 0, 128)
    title_text = f"{current_year} - {company_name} - {standard} Report"
    pdf.cell(0, 10, title_text, ln=True, align="C")
    pdf.ln(5)
    pdf.set_font("Times", "", 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, f"Date: {datetime.now().strftime('%B %d, %Y')}", ln=True, align="C")
    pdf.ln(10)
    pdf.set_line_width(0.5)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(10)
    pdf.set_font("Times", "", 12)
    for line in report_text.split("\n"):
        line_stripped = line.strip()
        if not line_stripped:
            pdf.ln(2)
            continue
        if line_stripped.startswith("#"):
            heading_level = len(line_stripped) - len(line_stripped.lstrip("#"))
            heading_text = line_stripped.lstrip("#").strip()
            if heading_level == 1:
                pdf.set_font("Times", "B", 16)
            elif heading_level == 2:
                pdf.set_font("Times", "B", 14)
            else:
                pdf.set_font("Times", "B", 12)
            pdf.cell(0, 10, heading_text, ln=True)
            pdf.ln(2)
            pdf.set_font("Times", "", 12)
        else:
            line_clean = line_stripped.replace("**", "")
            pdf.multi_cell(0, 10, line_clean)
            pdf.ln(2)
    for key in list(pdf.pages.keys()):
        pdf.pages[key] = (
            pdf.pages[key]
            .replace('\u2013', '-')
            .replace('\u2014', '-')
            .replace('\u2019', "'")
        )
    pdf_bytes = pdf.output(dest="S").encode("latin1", errors="replace")
    return pdf_bytes


# ------------------------------------------------------------------------------
# New functions to generate report sections individually with a progress bar
# ------------------------------------------------------------------------------
def generate_section(section_key, question_text, answer, standard):
    """
    Generate a report section for a specific question and answer.
    Uses a per-section token limit.
    """
    if standard == "CSRD":
        prompt_intro = (
            "You are a professional sustainability consultant. "
            "Based on the provided answer, generate a detailed CSRD-compliant report section."
        )
    elif standard == "GRI":
        prompt_intro = (
            "You are a professional sustainability consultant. "
            "Based on the provided answer, generate a detailed GRI-compliant report section."
        )
    elif standard == "TCFD":
        prompt_intro = (
            "You are a professional sustainability consultant. "
            "Based on the provided answer, generate a detailed TCFD-aligned report section."
        )
    elif standard == "SASB":
        prompt_intro = (
            "You are a professional sustainability consultant. "
            "Based on the provided answer, generate a detailed SASB-compliant report section."
        )
    elif standard == "Integrated Reporting (<IR>)":
        prompt_intro = (
            "You are a professional sustainability consultant. "
            "Based on the provided answer, generate a detailed Integrated Reporting (<IR>)-compliant report section."
        )
    elif standard == "CDP":
        prompt_intro = (
            "You are a professional sustainability consultant. "
            "Based on the provided answer, generate a detailed CDP-compliant report section focused on environmental transparency."
        )
    elif standard == "AA1000":
        prompt_intro = (
            "You are a professional sustainability consultant. "
            "Based on the provided answer, generate a detailed AA1000-compliant report section emphasizing stakeholder engagement and accountability."
        )
    elif standard == "ISO 26000":
        prompt_intro = (
            "You are a professional sustainability consultant. "
            "Based on the provided answer, generate a detailed report section aligned with ISO 26000 guidance on social responsibility."
        )
    elif standard == "ISSB":
        prompt_intro = (
            "You are a professional sustainability consultant. "
            "Based on the provided answer, generate a detailed ISSB-compliant report section addressing both climate-related and general sustainability disclosures."
        )
    elif standard == "ESRS":
        prompt_intro = (
            "You are a professional sustainability consultant. "
            "Based on the provided answer, generate a detailed ESRS-compliant report section covering environmental, social, and governance disclosures."
        )
    else:
        prompt_intro = (
            "You are a professional sustainability consultant. "
            "Based on the provided answer, generate a detailed report section."
        )

    prompt = (
        f"{prompt_intro}\n\n"
        f"Section: {question_text}\n"
        f"Provided Answer: {answer}\n\n"
        "Please write a comprehensive section on this topic."
    )

    try:
        llm = ChatOpenAI(model="gpt-4-turbo", temperature=0.7, max_tokens=800, streaming=True)
        messages = [{"role": "user", "content": prompt}]
        response = llm(messages)
        return response.content
    except Exception as e:
        st.error(f"An error occurred during report generation: {e}")
        return ""


def generate_full_report(report_data, standard="CSRD"):
    """
    Generate the full sustainability report by iterating over each questionnaire item.
    Each section is generated separately, with a progress bar showing the generation percentage.
    """
    full_report = ""
    # Determine the total number of sections that have content.
    answered_keys = [key for key, _ in questions if report_data.get(key, "").strip()]
    total_sections = len(answered_keys)
    if total_sections == 0:
        st.error("No responses provided.")
        return ""

    progress_bar = st.progress(0)  # Initialize progress bar at 0%
    completed = 0

    for key, question_text in questions:
        answer = report_data.get(key, "")
        if answer.strip():
            section_content = generate_section(key, question_text, answer, standard)
            full_report += f"# {section_content}\n\n"
            completed += 1
            progress_percent = int((completed / total_sections) * 100)
            progress_bar.progress(progress_percent)
    return full_report


# ------------------------------------------------------------------------------
# Evaluate report with AI: returns detailed insights as a JSON object
# ------------------------------------------------------------------------------
def measure_compliance(report_text, standard="CSRD"):
    if standard == "CSRD":
        compliance_prompt = (
            "You are an expert in sustainability reporting with extensive knowledge of the CSRD standard. "
            "Evaluate the compliance of the following report with the CSRD standard and provide your evaluation "
            "in a JSON format with the following keys: 'score' (a number between 1 and 100), 'strengths', "
            "'weaknesses', and 'recommendations'. Here is the report:\n\n" + report_text
        )
    elif standard == "GRI":
        compliance_prompt = (
            "You are an expert in sustainability reporting with extensive knowledge of the GRI standards. "
            "Evaluate the compliance of the following report with the GRI standards and provide your evaluation "
            "in a JSON format with the following keys: 'score' (a number between 1 and 100), 'strengths', "
            "'weaknesses', and 'recommendations'. Here is the report:\n\n" + report_text
        )
    elif standard == "TCFD":
        compliance_prompt = (
            "You are an expert in sustainability reporting with extensive knowledge of the TCFD recommendations. "
            "Evaluate the compliance of the following report with the TCFD recommendations and provide your evaluation "
            "in a JSON format with the following keys: 'score' (a number between 1 and 100), 'strengths', "
            "'weaknesses', and 'recommendations'. Here is the report:\n\n" + report_text
        )
    elif standard == "SASB":
        compliance_prompt = (
            "You are an expert in sustainability reporting with extensive knowledge of SASB standards. "
            "Evaluate the compliance of the following report with SASB standards and provide your evaluation "
            "in a JSON format with the following keys: 'score' (a number between 1 and 100), 'strengths', "
            "'weaknesses', and 'recommendations'. Here is the report:\n\n" + report_text
        )
    elif standard == "Integrated Reporting (<IR>)":
        compliance_prompt = (
            "You are an expert in sustainability reporting with extensive knowledge of Integrated Reporting (<IR>) guidelines. "
            "Evaluate the compliance of the following report with Integrated Reporting guidelines and provide your evaluation "
            "in a JSON format with the following keys: 'score' (a number between 1 and 100), 'strengths', "
            "'weaknesses', and 'recommendations'. Here is the report:\n\n" + report_text
        )
    elif standard == "CDP":
        compliance_prompt = (
            "You are an expert in sustainability reporting with extensive knowledge of CDP requirements. "
            "Evaluate the compliance of the following report with CDP guidelines and provide your evaluation "
            "in a JSON format with the following keys: 'score' (a number between 1 and 100), 'strengths', "
            "'weaknesses', and 'recommendations'. Here is the report:\n\n" + report_text
        )
    elif standard == "AA1000":
        compliance_prompt = (
            "You are an expert in sustainability reporting with extensive knowledge of AA1000 standards. "
            "Evaluate the compliance of the following report with AA1000 principles and provide your evaluation "
            "in a JSON format with the following keys: 'score' (a number between 1 and 100), 'strengths', "
            "'weaknesses', and 'recommendations'. Here is the report:\n\n" + report_text
        )
    elif standard == "ISO 26000":
        compliance_prompt = (
            "You are an expert in sustainability reporting with extensive knowledge of ISO 26000 guidance. "
            "Evaluate the compliance of the following report with ISO 26000 principles on social responsibility and provide your evaluation "
            "in a JSON format with the following keys: 'score' (a number between 1 and 100), 'strengths', "
            "'weaknesses', and 'recommendations'. Here is the report:\n\n" + report_text
        )
    elif standard == "ISSB":
        compliance_prompt = (
            "You are an expert in sustainability reporting with extensive knowledge of ISSB guidelines. "
            "Evaluate the compliance of the following report with ISSB standards and provide your evaluation "
            "in a JSON format with the following keys: 'score' (a number between 1 and 100), 'strengths', "
            "'weaknesses', and 'recommendations'. Here is the report:\n\n" + report_text
        )
    elif standard == "ESRS":
        compliance_prompt = (
            "You are an expert in sustainability reporting with extensive knowledge of the European Sustainability Reporting Standards (ESRS). "
            "Evaluate the compliance of the following report with ESRS and provide your evaluation "
            "in a JSON format with the following keys: 'score' (a number between 1 and 100), 'strengths', "
            "'weaknesses', and 'recommendations'. Here is the report:\n\n" + report_text
        )
    else:
        compliance_prompt = (
            "You are an expert in sustainability reporting. "
            "Evaluate the compliance of the following report with the relevant sustainability reporting standards "
            "and provide your evaluation in a JSON format with the following keys: 'score' (a number between 1 and 100), "
            "'strengths', 'weaknesses', and 'recommendations'. Here is the report:\n\n" + report_text
        )
    llm = ChatOpenAI(model="gpt-4", temperature=0.7)
    messages = [{"role": "user", "content": compliance_prompt}]
    response = llm(messages)
    result = response.content.strip()
    try:
        data = json.loads(result)
        if not isinstance(data, dict):
            data = {"score": None, "strengths": result, "weaknesses": "", "recommendations": ""}
    except Exception:
        data = {"score": None, "strengths": result, "weaknesses": "", "recommendations": ""}
    return data


def display_insights_as_list_or_text(content):
    if isinstance(content, list):
        for item in content:
            st.markdown(f"- {item}")
    else:
        st.write(content)


# ------------------------------------------------------------------------------
# Global questionnaire: List of tuples (key, question_text)
# ------------------------------------------------------------------------------
questions = [
    ("company_name", "What is the name of your company?"),
    ("industry", "What industry does your company operate in?"),
    ("overview", "Briefly describe your company's main products or services and the regions/countries where you operate."),
    ("governance", "Describe your company's governance structure, including board composition and sustainability oversight."),
    ("ethics", "What policies and practices are in place to ensure ethical behavior and prevent corruption?"),
    ("business_model", "Describe your business model and how it integrates sustainability considerations."),
    ("strategy", "What is your company's overall sustainability strategy and long-term vision? How does sustainability factor into strategic decision-making?"),
    ("stakeholder_engagement", "Who are the key stakeholders your company engages with (e.g., employees, customers, suppliers, community), and how are they involved in your sustainability initiatives?"),
    ("materiality", "Describe the materiality assessment process used to identify key sustainability issues for your company."),
    ("environmental_performance", "Detail your company's environmental performance, including greenhouse gas emissions, energy consumption, water usage, waste management, and resource efficiency."),
    ("environmental_targets", "What environmental targets or goals has your company set, and how are these measured?"),
    ("social_performance", "Describe your company's social policies and practices, including employee well-being, diversity, and inclusion."),
    ("community_engagement", "How does your company contribute to and engage with the local communities in which it operates?"),
    ("labor_practices", "Outline your company's approach to labor practices, including workplace safety, training, and development."),
    ("human_rights", "How does your company ensure compliance with human rights standards and prevent human rights abuses in your operations and supply chain?"),
    ("supply_chain", "Describe how your company assesses and manages sustainability risks in its supply chain."),
    ("supplier_evaluation", "What criteria do you use to evaluate the sustainability performance of your suppliers?"),
    ("financial_sustainability", "What financial risks and opportunities related to sustainability does your company face, and how are these integrated into your financial planning?"),
    ("reporting_frameworks", "Which sustainability reporting frameworks or standards does your company currently use or intend to use?"),
    ("data_assurance", "How is the sustainability data collected, verified, and assured (e.g., through internal audits or external assurance)?"),
    ("kpi", "What key performance indicators (KPIs) do you monitor to track your sustainability performance?"),
    ("future_goals", "What are your company's sustainability goals for the next 5-10 years, and what strategies are in place to achieve them?"),
    ("innovation", "Describe any innovative initiatives or technologies your company is implementing to improve sustainability performance."),
    ("risk_management", "How does your company manage and mitigate sustainability-related risks, including those associated with climate change?")
]


# ------------------------------------------------------------------------------
# Main function: Streamlit app workflow
# ------------------------------------------------------------------------------
def main():
    set_custom_css()
    st.title("Resonate AI Sustainability Report Builder")

    # --- Initialize Session State Variables ---
    if "step" not in st.session_state:
        st.session_state.step = 0
    if "mode" not in st.session_state:
        st.session_state.mode = None
    if "report_data" not in st.session_state:
        st.session_state.report_data = {}
    if "generated_report" not in st.session_state:
        st.session_state.generated_report = ""
    if "current_standard" not in st.session_state:
        st.session_state.current_standard = ""
    if "compliance_result" not in st.session_state:
        st.session_state.compliance_result = {}

    # --- INITIAL CHOICE: Explanation & Options ---
    if st.session_state.mode is None:
        st.markdown("### Welcome!")
        st.write(
            """
            Welcome to the Multi-Framework Sustainability Report Builder!

            **Process Overview:**
            1. **Input Your Data:** You can either fill out a detailed questionnaire or upload an Excel file with pre-filled responses.
            2. **Review & Edit:** After entering your information, you'll have the chance to review and edit your answers.
            3. **Select Your Reporting Standard:** At the end of the questionnaire, you will choose the sustainability reporting standard you wish to use (e.g., CSRD, GRI, TCFD, SASB, Integrated Reporting (<IR>), CDP, AA1000, ISO 26000, ISSB, or ESRS).
            4. **Generate Your Report:** The app will then generate a comprehensive, professional report based on your inputs and the selected standard.
            5. **Additional Features:** You can copy the report to your clipboard, download it as a PDF, and even evaluate it with AI for compliance insights.

            Choose your preferred method below to get started!
            """
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Start Questionnaire"):
                st.session_state.mode = "questionnaire"
        with col2:
            if st.button("Upload File"):
                st.session_state.mode = "upload"

    # --- FILE UPLOAD MODE (Excel Only) ---
    if st.session_state.mode == "upload":
        st.markdown("### Upload Your Excel File")
        st.write("If you need a template, download it below, fill it out, and then upload your file.")

        # Create an Excel template DataFrame
        template_df = pd.DataFrame({
            "Key": [
                "Company Name", "Industry", "Overview", "Governance", "Ethics",
                "Business Model", "Strategy", "Stakeholder Engagement", "Materiality",
                "Environmental Performance", "Environmental Targets", "Social Performance",
                "Community Engagement", "Labor Practices", "Human Rights", "Supply Chain",
                "Supplier Evaluation", "Financial Sustainability", "Reporting Frameworks",
                "Data Assurance", "KPI", "Future Goals", "Innovation", "Risk Management"
            ],
            "Value": ["" for _ in range(24)]
        })

        # Save the template as an Excel file in memory
        excel_buffer = BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
            template_df.to_excel(writer, index=False)
        excel_data = excel_buffer.getvalue()

        # Provide a download button for the template
        st.download_button(
            label="Download Excel Template",
            data=excel_data,
            file_name="sustainability_report_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        # File uploader for users to upload their filled-out Excel file
        uploaded_file = st.file_uploader("Upload your filled-out file (XLSX or XLS)", type=["xlsx", "xls"])
        if uploaded_file is not None:
            parsed_data = parse_uploaded_excel(uploaded_file)
            st.session_state.report_data.update(parsed_data)
            st.success("File processed and responses filled!")
            # Jump directly to review/edit stage.
            st.session_state.step = len(questions)

    # --- QUESTIONNAIRE FLOW ---
    if st.session_state.mode == "questionnaire" and st.session_state.step < len(questions):
        # Back Button: if pressed on the first question, return to the welcome page.
        if st.button("Back", key="back_button"):
            if st.session_state.step > 0:
                st.session_state.step -= 1
            else:
                st.session_state.mode = None

        key, question_text = questions[st.session_state.step]
        st.header(f"Question {st.session_state.step + 1} of {len(questions)}")
        with st.form(key=f"form_{key}"):
            user_input = st.text_area(question_text, height=150, value=st.session_state.report_data.get(key, ""))
            submitted = st.form_submit_button("Submit Answer ➡️")
            if submitted and user_input.strip():
                st.session_state.report_data[key] = user_input.strip()
                st.session_state.step += 1

    # --- REVIEW & REPORT GENERATION STAGE ---
    elif st.session_state.mode in ["questionnaire", "upload"] and st.session_state.step >= len(questions):
        st.header("Review and Edit Your Responses ✏️")
        for i, (k, q) in enumerate(questions):
            st.markdown(f"**{q}**")
            updated_value = st.text_area(f"Edit: {q}", value=st.session_state.report_data.get(k, ""))
            st.session_state.report_data[k] = updated_value
            st.write("---")

        st.subheader("Generate Your Sustainability Report 📄")
        st.markdown("**Select a reporting standard** (Only **GRI** is available for Demo purposes)")
        # Render a dropdown that is interactive but with all options other than GRI disabled.
        dropdown_html = """
        <select id="reporting-standard" style="width: 100%; padding: 10px; border-radius: 5px;">
          <option value="CSRD" disabled style="color: gray;">CSRD</option>
          <option value="GRI" selected>GRI</option>
          <option value="TCFD" disabled style="color: gray;">TCFD</option>
          <option value="SASB" disabled style="color: gray;">SASB</option>
          <option value="Integrated Reporting (<IR>)" disabled style="color: gray;">Integrated Reporting (&lt;IR&gt;)</option>
          <option value="CDP" disabled style="color: gray;">CDP</option>
          <option value="AA1000" disabled style="color: gray;">AA1000</option>
          <option value="ISO 26000" disabled style="color: gray;">ISO 26000</option>
          <option value="ISSB" disabled style="color: gray;">ISSB</option>
          <option value="ESRS" disabled style="color: gray;">ESRS</option>
        </select>
        """
        st.markdown(dropdown_html, unsafe_allow_html=True)
        # The reporting standard is set to GRI regardless of the dropdown, since all other options are disabled.
        selected_standard = "GRI"

        if st.button("Generate Report"):
            st.session_state.current_standard = selected_standard
            with st.spinner(f"Generating {selected_standard} report..."):
                # Generate the full report by section, with a progress bar
                st.session_state.generated_report = generate_full_report(
                    st.session_state.report_data, standard=selected_standard
                )
            st.success(f"{selected_standard} report generated successfully!")

        if st.session_state.generated_report:
            st.subheader("Your Sustainability Report")
            st.write(st.session_state.generated_report)

            c1, c2 = st.columns(2)
            with c1:
                if st.button("Copy to Clipboard"):
                    pyperclip.copy(st.session_state.generated_report)
                    st.success("Report copied to clipboard!")
            with c2:
                pdf_bytes = create_pdf(
                    st.session_state.generated_report,
                    st.session_state.report_data.get("company_name", "company"),
                    st.session_state.current_standard
                )
                current_year = datetime.now().year
                file_name = f"{current_year} {st.session_state.report_data.get('company_name', 'company')} - {st.session_state.current_standard} Report.pdf"
                st.download_button(
                    label="Download as PDF 📥",
                    data=pdf_bytes,
                    file_name=file_name,
                    mime="application/pdf"
                )

            def shorten_text(text, max_chars=3000):
                """
                Simple function to truncate the text to a maximum number of characters.
                You may also consider a summarization approach for a more refined summary.
                """
                return text if len(text) <= max_chars else text[:max_chars]

            if st.button("Evaluate with AI 🤖"):
                with st.spinner("Evaluating report..."):
                    # Shorten the generated report to ensure it fits within token limits
                    short_report = shorten_text(st.session_state.generated_report)
                    st.session_state.compliance_result = measure_compliance(short_report,
                                                                            st.session_state.current_standard)
                st.success("AI evaluation complete!")

            if st.session_state.compliance_result:
                st.subheader("AI Score and Insights")
                compliance_data = st.session_state.compliance_result
                if isinstance(compliance_data, dict):
                    score = compliance_data.get("score")
                    strengths = compliance_data.get("strengths", "")
                    weaknesses = compliance_data.get("weaknesses", "")
                    recommendations = compliance_data.get("recommendations", "")
                else:
                    score = None
                    strengths = compliance_data
                    weaknesses = ""
                    recommendations = ""

                if score is not None:
                    st.markdown(f"### AI Score: **{score}** / 100")
                    st.progress(int(score))
                else:
                    st.markdown("### AI Score: Not Available")

                st.markdown("### Strengths")
                display_insights_as_list_or_text(strengths)
                st.markdown("### Weaknesses")
                display_insights_as_list_or_text(weaknesses)
                st.markdown("### Recommendations")
                display_insights_as_list_or_text(recommendations)

        if st.button("Start Over 🔄"):
            st.session_state.step = 0
            st.session_state.report_data = {}
            st.session_state.generated_report = ""
            st.session_state.compliance_result = {}
            st.session_state.current_standard = ""
            st.session_state.mode = None

    st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
