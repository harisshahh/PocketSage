from pydantic import BaseModel


class Transaction(BaseModel):
    amount: float
    date: str
    category: str
    name: str

class AdviceQuery(BaseModel):
    query: str

class PlaidTokenExchangeResponse(BaseModel):
    public_token: str

