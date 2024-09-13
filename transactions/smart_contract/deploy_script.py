from django.core.management.base import BaseCommand
from web3 import Web3
from transactions.models import LandTransaction
from transactions.utils import load_contract_abi

class Command(BaseCommand):
    help = 'Deploys the LandTransaction smart contract'

    def handle(self, *args, **options):
        w3 = Web3(Web3.HTTPProvider('http://localhost:8545'))
        account = w3.eth.accounts[0]

        contract_abi = load_contract_abi()
        contract_bytecode = "  0xC11D335a2C3977909eC2E8aBDfADE4AC84e4370C"  # Your contract bytecode here

        LandTransactionContract = w3.eth.contract(abi=contract_abi, bytecode=contract_bytecode)

        oracle_address = '0x6Fb0D27e38fA6437a3BC2Bd10328310c8bC7F994'  # Your oracle address

        tx_hash = LandTransactionContract.constructor(oracle_address).transact({'from': account})
        tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        contract_address = tx_receipt.contractAddress
        self.stdout.write(self.style.SUCCESS(f'Contract deployed to {contract_address}'))

        # Update all LandTransaction instances with the new contract address
        LandTransaction.objects.update(smart_contract_address=contract_address)