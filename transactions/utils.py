import json
from django.conf import settings

def load_contract_abi():
    with open(settings.LAND_TRANSACTION_ABI_PATH, 'r') as abi_file:
        return json.load(abi_file)