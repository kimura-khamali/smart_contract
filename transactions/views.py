import datetime
import os
import re
from django.conf import settings
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Transaction
from .serializers import TransactionSerializer
from google.cloud import vision
from web3 import Web3
from .utils import load_contract_abi

class TransactionViewSet(viewsets.ModelViewSet):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer

    @action(detail=False, methods=['post'])
    def verify_transaction(self, request):
        if 'file1' not in request.FILES or 'file2' not in request.FILES:
            return Response({"error": "Both files (file1 and file2) must be provided"}, status=400)
        
        image_file1 = request.FILES['file1']
        image_file2 = request.FILES['file2']
        
        try:
            data1 = self.extract_data_from_image(image_file1)
            data2 = self.extract_data_from_image(image_file2)
        except ValueError as e:
            return Response({"error": str(e)}, status=400)

        if all(k in data1 and k in data2 for k in ['amount', 'date', 'code']):
            if self.compare_transaction_data(data1, data2):
                transaction = self.save_transaction(data1)
                return Response({
                    "message": "Transaction created and marked as complete",
                    "transaction_id": transaction.id,
                    "amount": transaction.amount
                }, status=201)
            else:
                return Response({
                    "error": "The amounts, dates, or unique codes do not match",
                    "data1": data1,
                    "data2": data2
                }, status=400)
        else:
            return Response({"error": "Could not extract all required information from both images"}, status=400)

    def extract_data_from_image(self, image_file):
        client = vision.ImageAnnotatorClient()
        try:
            image_content = image_file.read()
            image = vision.Image(content=image_content)
            response = client.text_detection(image=image)
            texts = response.text_annotations
            extracted_text = texts[0].description if texts else ""
        except Exception as e:
            raise ValueError(f"Failed to process image: {str(e)}")

        patterns = {
            'amount': [r'Ksh\s*([\d,]+\.\d{2})', r'KES\s*([\d,]+\.\d{2})'],
            'date': [r'on\s*(\d{1,2}/\d{1,2}/\d{2,4})', r'(\d{1,2}/\d{1,2}/\d{4})'],
            'code': [r'\b([A-Z0-9]{10})\b']
        }
        
        matches = {}
        for key, regex_list in patterns.items():
            for pattern in regex_list:
                match = re.search(pattern, extracted_text)
                if match:
                    matches[key] = match.group(1)
                    break
        return matches

    def compare_transaction_data(self, data1, data2):
        try:
            amount1 = float(data1['amount'].replace(',', ''))
            amount2 = float(data2['amount'].replace(',', ''))
            date1 = datetime.datetime.strptime(data1['date'], '%d/%m/%y').date()
            date2 = datetime.datetime.strptime(data2['date'], '%d/%m/%y').date()
            return (amount1 == amount2 and date1 == date2 and data1['code'] == data2['code'])
        except (ValueError, KeyError):
            return False

    def save_transaction(self, data):
        amount = float(data['amount'].replace(',', ''))
        date = datetime.datetime.strptime(data['date'], '%d/%m/%Y').date()
        transaction = Transaction.objects.create(
            amount=amount,
            buyer="Buyer Name", 
            seller="Seller Name", 
            proof_of_payment=None,  
            lawyer_details="Lawyer details",  
            seller_details="Seller details", 
            smart_contract_address=settings.SMART_CONTRACT_ADDRESS,
            is_verified=True
        )
        return transaction

    @action(detail=True, methods=['post'])
    def verify_payment(self, request, pk=None):
        transaction = self.get_object()
        
        if self.compare_details_with_vision(transaction):
            if self.verify_payment_on_blockchain(transaction):
                transaction.is_verified = True
                transaction.save()
                return Response({"message": "Payment verified successfully."}, status=status.HTTP_200_OK)
            else:
                return Response({"message": "Blockchain verification failed."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({"message": "Document verification failed."}, status=status.HTTP_400_BAD_REQUEST)
        
    def compare_details_with_vision(self, transaction):
        client = vision.ImageAnnotatorClient()
        
        with open(transaction.proof_of_payment.path, 'rb') as image_file:
            content = image_file.read()
        
        image = vision.Image(content=content)
        response = client.text_detection(image=image)
        texts = response.text_annotations
        
        if not texts:
            print("No text detected in the image.")
            return False
        
        full_text = texts[0].description.lower()
        
        details_to_verify = [
            str(transaction.amount),
            transaction.buyer.lower(),
            transaction.seller.lower(),
        ]
        
        return all(detail in full_text for detail in details_to_verify)

    def verify_payment_on_blockchain(self, transaction):
        w3 = Web3(Web3.HTTPProvider(settings.BLOCKCHAIN_PROVIDER_URL))
        contract_abi = load_contract_abi()
        contract_address = transaction.smart_contract_address
        
        contract = w3.eth.contract(address=contract_address, abi=contract_abi)
        
        try:
            tx_hash = contract.functions.verifyPayment(
                transaction.id, 
                int(transaction.amount * 100) 
            ).transact({'from': w3.eth.accounts[0]})
            
            w3.eth.wait_for_transaction_receipt(tx_hash)
            
            is_verified = contract.functions.isPaymentVerified(transaction.id).call()
            return is_verified
        except Exception as e:
            print(f"Error verifying payment on blockchain: {e}")
            return False