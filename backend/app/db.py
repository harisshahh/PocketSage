from google.cloud import firestore
from .models import Transaction
import os

db = firestore.client(project=os.getenv('GCP_PROJECT_ID'))

TRANSACTIONS_COLLECTION = 'transactions'
TOKENS_COLLECTION = 'plaid_tokens'



async def create_transaction(transaction: Transaction):
    data = transaction.model_dump()

    data['created_at'] = firestore.SERVER_TIMESTAMP

    try:
        doc_ref = db.collection(TRANSACTIONS_COLLECTION).add(data)
        return {"id": doc_ref.id, "message": "Transaction saved successfully!"}
    except Exception as e:
        print(f"Error saving transaction: {e}")
        return {"error": str(e)}

async def save_plaid_access_token(public_token: str, access_token: str, item_id: str):
    user_id = "user1"

    data = {
        "access_token": access_token,
        "item_id": item_id,
        "created_at": firestore.SERVER_TIMESTAMP,
        "last_public_token": public_token
    }

    try:
        doc_ref = db.collection(TOKENS_COLLECTION).document(user_id)
        await doc_ref.set(data)
        return {"user_id": user_id, "message": "Plaid token saved successfully!"}
    except Exception as e:
        print(f"Error saving Plaid token: {e}")
        return {"error": str(e)}
    

async def get_plaid_access_token(user_id: str = "user1"):
    try:
        doc = db.collection(TOKENS_COLLECTION).document(user_id).get()
        if doc.exists:
            return doc.to_dict().get('access_token')
        return None
    except Exception as e:
        print(f"Error getting Plaid token: {e}")
        return None
        
