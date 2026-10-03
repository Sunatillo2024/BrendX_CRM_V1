from django.db import models, transaction
from django.db.models import Max


class Store(models.Model):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=40, unique=True)
    is_active = models.BooleanField(default=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    receipt_header = models.TextField(blank=True)
    receipt_footer = models.TextField(blank=True)
    currency_code = models.CharField(max_length=3, default='KGS')
    currency_symbol = models.CharField(max_length=12, default='сом')
    low_stock_threshold = models.PositiveIntegerField(default=5)
    default_language = models.CharField(max_length=2, choices=[('uz', 'Uzbek'), ('ru', 'Russian')], default='uz')
    timezone = models.CharField(max_length=64, default='Asia/Bishkek')
    sale_counter = models.PositiveIntegerField(default=0)
    receipt_counter = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    @transaction.atomic
    def next_number(self, kind):
        from apps.sales.models import Sale
        from apps.inventory.models import StockReceipt
        field, model = ('sale_counter', Sale) if kind == 'sale' else ('receipt_counter', StockReceipt)
        locked = Store.objects.select_for_update().get(pk=self.pk)
        last = model.objects.filter(store=locked).aggregate(n=Max('number'))['n'] or 0
        number = max(getattr(locked, field), last) + 1
        setattr(locked, field, number)
        locked.save(update_fields=[field])
        return number


class StoreOwned(models.Model):
    store = models.ForeignKey(Store, on_delete=models.PROTECT)

    class Meta:
        abstract = True
