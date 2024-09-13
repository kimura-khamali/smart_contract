from django.db import models

# Create your models here.
from django.db import models

class Transaction(models.Model):
    buyer = models.CharField(max_length=100)
    seller = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    proof_of_payment = models.ImageField(upload_to='proof_of_payments/')
    lawyer_details = models.TextField()
    seller_details = models.TextField()
    is_verified = models.BooleanField(default=False)
    smart_contract_address = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Transaction {self.id} - {self.buyer} to {self.seller}"