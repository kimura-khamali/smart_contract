# transactions/views.py
import datetime
import os
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

    def post(self, request):
        if 'file1' not in request.FILES or 'file2' not in request.FILES:
            return Response({"error": "Both files (file1 and file2) must be provided"}, status=400)
        image_file1 = request.FILES['file1']
        image_file2 = request.FILES['file2']
        client = vision.ImageAnnotatorClient()
        def extract_data_from_image(image_file):
            try:
                image_content = image_file.read()
            except Exception as e:
                raise ValueError(f"Failed to read file: {str(e)}")
            image = vision.Image(content=image_content)
            try:
                response = client.text_detection(image=image)
                texts = response.text_annotations
                extracted_text = texts[0].description if texts else ""
            except Exception as e:
                raise ValueError(f"Failed to process image: {str(e)}")
            print(f"Extracted Text: {extracted_text}")
            patterns = {
                'amount': [r'Ksh\s*([\d,]+\.\d{2})', r'KES\s*([\d,]+\.\d{2})'],
                'date': [r'on\s*(\d{1,2}/\d{1,2}/\d{2})', r'(\d{1,2}/\d{1,2}/\d{4})'],
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
        try:
            data1 = extract_data_from_image(image_file1)
            data2 = extract_data_from_image(image_file2)
        except ValueError as e:
            return Response({"error": str(e)}, status=400)
        if all(k in data1 and k in data2 for k in ['amount', 'date', 'code']):
            try:
                amount1 = float(data1['amount'].replace(',', ''))
                amount2 = float(data2['amount'].replace(',', ''))
            except ValueError:
                return Response({"error": "Invalid amount format in one of the images"}, status=400)
            date1 = data1['date']
            date2 = data2['date']
            date_formats = ['%d/%m/%y', '%d/%m/%Y']
            date_obj1 = date_obj2 = None

            for fmt in date_formats:
                try:
                    date_obj1 = datetime.strptime(date1, fmt)
                    date_obj2 = datetime.strptime(date2, fmt)
                    break
                except ValueError:
                    continue
            if date_obj1 is None or date_obj2 is None:
                return Response({"error": "Date format is incorrect"}, status=400)
            formatted_date1 = date_obj1.strftime('%Y-%m-%d') 
            formatted_date2 = date_obj2.strftime('%Y-%m-%d')
            if (amount1 == amount2 and
                formatted_date1 == formatted_date2 and
                data1['code'] == data2['code']):
                try:
                    transaction, created = Transactions.objects.update_or_create(
                        amount=amount1,
                        date=formatted_date1,
                        defaults={'status': 'complete',
                        'unique_code': data1['code']
                        }
                    )
                    if created:
                        message = "Transaction created and marked as complete"
                    else:
                        message = "Transaction updated and marked as complete"
                except Exception as e:
                    return Response({"error": f"Failed to save transaction: {str(e)}"}, status=500)
                return Response({"message": message, "amount": amount1}, status=201)
            else:
                return Response({
                    "error": "The amounts, dates, or unique codes do not match",
                    "amount1": amount1,
                    "amount2": amount2,
                    "date1": formatted_date1,
                    "date2": formatted_date2,
                    "code1": data1['code'],
                    "code2": data2['code']
                }, status=400)
        else:
            return Response({"error": "Could not extract all required information from both images"}, status=400)

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
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = settings.GOOGLE_APPLICATION_CREDENTIALS
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
            # Add more details as needed, e.g., lawyer_details, seller_details
        ]
        
        all_details_present = all(detail in full_text for detail in details_to_verify)
        
        if all_details_present:
            print("All required details verified in the proof of payment.")
            return True
        else:
            print("Wrong transaction does not match")
            # print("Some details are missing or do not match.")
            return False

    def verify_payment_on_blockchain(self, transaction):
        w3 = Web3(Web3.HTTPProvider('http://localhost:8545'))  
        contract_abi = load_contract_abi()
        contract_address = transaction.smart_contract_address
        
        contract = w3.eth.contract(address=contract_address, abi=contract_abi)
        
        try:
            tx_hash = contract.functions.verifyPayment(
                transaction.id, 
                str(transaction.amount)  
            ).transact({'from': w3.eth.accounts[0]})
            
            w3.eth.wait_for_transaction_receipt(tx_hash)
            
            is_verified = contract.functions.isPaymentVerified(transaction.id).call()
            return is_verified
        except Exception as e:
            print(f"Error verifying payment on blockchain: {e}")
            return False