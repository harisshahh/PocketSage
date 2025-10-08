from google import genai
from google.genai import types
import os


try:
    client = genai.Client()
except Exception as e:
    print(f"Error initializing the Gemini Client: {e}")
    client = None

def get_investment_advice(query: str):
    if not client:
        return {"advice": "AI assistance is currently not available."}
    
    system_instruction = (
        "You are an expert personal finance advisor named PocketSage."
        "Your advice must always be concise, actionable, and based on conservative. long-term financial principles. Never recommend speculative trading."
    )

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.3 # low temp for more factual/conservative responses
    )

    try:
        response = client.models.generate_content(
            model = 'gemini-2.5-flash',
            contents = query,
            config = config,
        )
        return {"advice": response.text}
    except Exception as e:
        return {"error": f"Gemini API Error: {e}"}
    
def analyze_transaction_nlp(raw_transaction_text: str):
    if not client:
        return {"category": "Uncategorized (AI service error)"}
    
    prompt = (
        f"Categorize the following raw bank transaction description into ONE of these"
        f"categories: 'Groceries, 'Entertainment', 'Transport', 'Income', 'Savings/Investment', 'Rent/Mortgage', 'Utilities', or 'Miscellaneous'.\n" 
        f"Transaction: '{raw_transaction_text}'"
        f"Respond ONLY with the category name, nothing else. Do not use quotes or punctuation."
    )

    try:
        response = client.models.generate_content(
            model= 'gemini-2.5-flash',
            contents=prompt,
        )
        category = response.text.strip().replace('.', '') # cleans the response so that only category name is returned
        return {"category": category}
    except Exception:
        return {"category": "Miscellaneous (NLP Failure)"}