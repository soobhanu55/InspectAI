from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from config import get_settings
import json

settings = get_settings()

SYSTEM_PROMPT = """
You are a German manufacturing quality expert (Qualitätsexperte / Quality Engineer).
You work with Mittelstand manufacturers on defect analysis and process improvement.
You follow ISO 9001:2015 and IATF 16949 standards.

Given a detected defect, retrieved knowledge base context, and machine information,
you provide a strictly formatted JSON response. Do not output anything outside the JSON.

Output JSON format:
{{
  "root_cause": "Ursachenanalyse (Root Cause) in German, 2-3 sentences. Root Cause in English, 2-3 sentences.",
  "action_plan": ["Action 1", "Action 2", "Action 3"],
  "eu_ai_act_tier": "Minimal Risk (Art. 6) or Limited Risk (Art. 50)",
  "estimated_savings_eur": 5000
}}

Be specific, practical, and concise. Reference machine parameters where given.
Never recommend halting production unless defect severity is HIGH.
"""

def invoke_rca(defect_type: str, machine: str, part_type: str, context: str, severity: str) -> dict:
    try:
        api_key = settings.groq_api_key or "gsk_dummy"
        llm = ChatGroq(
            model=settings.groq_model,
            temperature=settings.groq_temperature,
            max_tokens=settings.groq_max_tokens,
            api_key=api_key
        )
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", f"Defect: {defect_type}\nSeverity: {severity}\nMachine: {machine}\nPart: {part_type}\nContext: {context}")
        ])
        
        chain = prompt | llm
        response = chain.invoke({})
        # Parse the JSON response
        # Groq might wrap in markdown ```json
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
            
        return json.loads(content.strip())
    except Exception as e:
        print(f"RCA Parse Error: {e}")
        return {
            "root_cause": f"Ursachenanalyse konnte nicht generiert werden. Fehler: {e}",
            "action_plan": ["Manuelle Untersuchung erforderlich"],
            "eu_ai_act_tier": "Minimal Risk (Art. 6)",
            "estimated_savings_eur": 0
        }
