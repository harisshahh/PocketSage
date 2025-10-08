from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from . import db, gemini_service
from . models import Transaction, AdviceQuery, PlaidTokenExchangeResponse
import os
import json
import plaid
from plaid.api import plaid_api
from plaid.model.plaid_error import PlaidError as PlaidApiException
from plaid.exceptions import ApiException
from plaid.model.products import Products
from plaid.model.country_code import CountryCode
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest

from plaid.model.webhook_verification_key_get_request import WebhookVerificationKeyGetRequest
from plaid.model.plaid_error import PlaidError
from plaid.model.transactions_get_request import TransactionsGetRequest
from datetime import datetime, timedelta

from starlette.concurrency import run_in_threadpool



PLAID_CLIENT_ID = os.getenv('PLAID_CLIENT_ID')
PLAID_SECRET = os.getenv('PLAID_SECRET')
PLAID_ENV = os.getenv('PLAID_ENV', 'sandbox')
PLAID_PRODUCTS = [Products('transactions')]
PLAID_COUNTRY_CODES = [CountryCode('US')]
FULL_WEBHOOK_URL = os.getenv("FULL_WEBHOOK_URL", "")



def get_plaid_environment():
    if PLAID_ENV == 'production':
        return plaid.Environment.Production
    elif PLAID_ENV == 'development':
        return plaid.Environment.Development
    else:
        return plaid.Environment.Sandbox

'''
configuration = plaid.Configuration(
    host = get_plaid_environment(),
    api_key = {
        'clientId': PLAID_CLIENT_ID,
        'secret': PLAID_SECRET,
        'plaidVersion': '2020-09-14'
    }
)
'''
configuration = plaid.Configuration(
    host=plaid.Environment.Sandbox,
    api_key={
        'clientId': PLAID_CLIENT_ID,
        'secret': PLAID_SECRET,
    },
    #plaid_version='2020-09-14',
)


api_client = plaid.ApiClient(configuration)
plaid_client = plaid_api.PlaidApi(api_client)


app = FastAPI()

origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins = origins,
    allow_credentials = True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "PocketSage API is running."}



@app.post("/transactions")
async def create_new_transaction(transaction: Transaction):
    print(f"Received manual transaction: {transaction.name}")
    result = await run_in_threadpool(db.create_transaction, transaction)
    return result

@app.post("/plaid/create_link_token")
async def create_link_token():
    try:
        request_body = {
            "user": LinkTokenCreateRequestUser(client_user_id = 'user1'),
            "client_name": "PocketSage",
            "products": PLAID_PRODUCTS,
            "country_codes": PLAID_COUNTRY_CODES,
            "language": 'en',
        }

        if FULL_WEBHOOK_URL:
            request_body['webhook'] = FULL_WEBHOOK_URL

        request = LinkTokenCreateRequest(**request_body)
        response = plaid_client.link_token_create(request)
        return {'link_token': response.link_token}
    except ApiException as e:
        error_response = json.loads(e.body)
        print(f"Plaid API Error creating the link token: {error_response}")
        raise HTTPException(status_code=500, detail=f"Plaid Link Token error: {error_response.get('error_message')}")
    except Exception as e:
        print(f"Error creating link token: {e}")
        raise HTTPException(status_code=500, detail = f"General error: {e}")
    
@app.post("/plaid/set_access_token")
async def set_access_token(exchange_request: PlaidTokenExchangeResponse):
    try:
        request = ItemPublicTokenExchangeRequest(
            public_token = exchange_request.public_token
        )
        exchange_response = plaid_client.item_public_token_exchange(request)
        access_token = exchange_response.access_token
        item_id = exchange_response.item_id

        await run_in_threadpool(db.save_plaid_access_token, exchange_request.public_token, access_token, item_id)

        return {
            'message': 'Token exchange successful and access token saved.',
            'item_id': item_id,
        }
    except ApiException as e:
        error_response = json.loads(e.body)
        print(f"Plaid API Error exchanging the token: {error_response}")
        raise HTTPException(status_code=500, detail = f"Plaid Token Exchange error: {error_response.get('error_message')}")
    except Exception as e:
        print(f"Error exchanging token: {e}")
        raise HTTPException(status_code=500, detail = f"General error: {e}")
    
@app.get("/plaid/transactions")
async def get_plaid_transactions():
    access_token = await run_in_threadpool(db.get_plaid_access_token)

    if not access_token:
        raise HTTPException(status_code=500, detail="No linked account found. Please connect your bank.")
    
    try:
        today = datetime.now()
        thirty_days_ago = today - timedelta(days=30)

        request = TransactionsGetRequest(
            access_token = access_token,
            start_date = thirty_days_ago.strftime('%Y-%m-%d'),
            end_date = today.strftime('%Y-%m-%d')
        )
        response = await run_in_threadpool(plaid_client.transactions_get, request)
        transactions = response.transactions

        processed_transactions = []
        for txn in transactions:
            gemini_result = await run_in_threadpool(gemini_service.analyze_transaction_nlp, txn.name)

            processed_txn = {
                "amount": txn.amount,
                "date": txn.date,
                "name": txn.name,
                "category_plaid": txn.category[0] if txn.category else 'Plaid Uncategorized', # Plaid's own category
                "category_nlp": gemini_result['category'], # My NLP category
                "plaid_id": txn.transaction_id
            }
            processed_transactions.append(processed_txn)
        return {"message": "Transactions fetched and analyzed", "transactions": processed_transactions}
    except ApiException as e:
        error_response = json.loads(e.body)
        print(f"Plaid API error fetching transactions: {error_response}")
        raise HTTPException(status_code=500, detail= f"Plaid Transactions error: {error_response}")
    except Exception as e:
        print(f"General error fetching transactions: {e}")
        raise HTTPException(status_code=500, detail= f"General error: {e}")

        

@app.post("/gemini/advice")
async def get_advice(query: AdviceQuery):
    print(f"Received advice query: {query.query}")
    result = await run_in_threadpool(gemini_service.get_investment_advice, query.query)

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result



'''
@app.post("/plaid/webhook")
async def receive_plaid_webhook(webhook_data: dict):
    webhook_type = webhook_data.get('webhook_type')
    code = webhook_data.get('webhook_code')
    item_id = webhook_data.get('item_id')

    print(f"Received Plaid Webhook: Type={webhook_type}, Code={code}, Item={item_id} ")

    if webhook_type == 'TRANSACTIONS' and code == 'INITIAL_UPDATE':
        return {"status": "successful", "message": "Plaid webhook received and processing initiated"}
    return {"status": "successful", "message": "Webhook received, no action taken"}

'''

