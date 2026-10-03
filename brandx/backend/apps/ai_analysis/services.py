"""AI Analysis Service - optional Groq-powered business commentary"""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.customers.models import Customer
from apps.products.models import ProductVariant
from apps.sales import services as sales_services


class FinancialDataCollector:
    """Collects and formats business data for analysis."""

    def __init__(self, store):
        self.store = store

    def get_sales_summary(self, days: int = 30) -> dict:
        end = timezone.localdate()
        start = end - timedelta(days=days - 1)
        ops = sales_services.operational_stats(start, end, store=self.store)
        return {
            'sales_count': ops['sales_count'],
            'units_sold': ops['units_sold'],
            'revenue': float(ops['net_revenue']),
            'cash': float(ops['cash_total']),
            'card': float(ops['card_total']),
            'average_check': float(ops['average_check']),
            'returns': float(ops['returns_total']),
        }

    def get_top_products(self, limit: int = 10) -> list:
        end = timezone.localdate()
        start = end - timedelta(days=29)
        return sales_services.top_products(start, end, limit, store=self.store)

    def get_inventory_health(self) -> dict:
        variants = ProductVariant.objects.filter(store=self.store, is_active=True, product__is_active=True)
        out_of_stock = variants.filter(stock_quantity=0).count()
        low_stock = variants.filter(stock_quantity__gt=0).filter(
            stock_quantity__lte=models_low_threshold()
        ).count()
        total = variants.count()
        return {
            'total_variants': total,
            'out_of_stock': out_of_stock,
            'low_stock': low_stock,
            'in_stock': total - out_of_stock - low_stock,
        }

    def get_customer_insights(self) -> dict:
        return {'total_customers': Customer.objects.filter(store=self.store, is_active=True).count()}


def models_low_threshold():
    from django.db.models import F
    return F('low_stock_threshold')


class AIAnalysisService:
    """
    Optional AI commentary using Groq's free API.

    Falls back to a rule-based summary when no API key is configured, so the
    feature never breaks the app.
    """

    def __init__(self, store):
        self.api_key = getattr(settings, 'GROQ_API_KEY', '')
        self.model = getattr(settings, 'AI_MODEL', 'llama3-8b-8192')
        self.collector = FinancialDataCollector(store)

    def analyze(self, query: str, context_type: str = 'general') -> dict:
        context = self._build_context()
        if self.api_key:
            return self._call_groq(self._build_prompt(query, context))
        return self._rule_based_analysis(context)

    def _build_context(self) -> dict:
        return {
            'sales': self.collector.get_sales_summary(30),
            'inventory': self.collector.get_inventory_health(),
            'customers': self.collector.get_customer_insights(),
            'top_products': self.collector.get_top_products(5),
        }

    def _build_prompt(self, query: str, context: dict) -> str:
        return f"""You are a retail analyst for a clothing shop called BrandX.
Analyse the business data below and answer the question.

DATA (last 30 days):
Sales: {context['sales']}
Inventory: {context['inventory']}
Customers: {context['customers']}
Top products: {context['top_products']}

QUESTION: {query}

Answer with a short summary, key findings and concrete recommendations."""

    def _call_groq(self, prompt: str) -> dict:
        try:
            from groq import Groq
            client = Groq(api_key=self.api_key)
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {'role': 'system',
                     'content': 'You are a professional retail business analyst.'},
                    {'role': 'user', 'content': prompt},
                ],
                max_tokens=1024,
                temperature=0.3,
            )
            return {'analysis': response.choices[0].message.content,
                    'model': self.model, 'source': 'groq_ai'}
        except Exception:  # noqa: BLE001
            return self._rule_based_analysis(self._build_context())

    def _rule_based_analysis(self, context: dict) -> dict:
        sales = context.get('sales', {})
        inventory = context.get('inventory', {})

        insights, recommendations = [], []
        if sales:
            if sales.get('average_check', 0) and sales.get('sales_count', 0):
                insights.append(
                    f"Average check is {sales['average_check']:.0f} across "
                    f"{sales['sales_count']} sales."
                )
            if sales.get('returns', 0) and sales.get('revenue', 0):
                share = sales['returns'] / (sales['revenue'] + sales['returns'] + 1) * 100
                if share > 5:
                    insights.append(f'Returns are {share:.1f}% of revenue - worth reviewing.')
                    recommendations.append('Check return reasons (size vs. defect).')

        if inventory:
            if inventory.get('out_of_stock', 0):
                insights.append(f"{inventory['out_of_stock']} variants are out of stock.")
                recommendations.append('Restock out-of-stock items to avoid lost sales.')
            if inventory.get('low_stock', 0):
                insights.append(f"{inventory['low_stock']} variants are running low.")
                recommendations.append('Create a goods receipt for the low-stock items.')

        analysis = '**Biznes tahlili**\n\n'
        if insights:
            analysis += '**Asosiy xulosalar:**\n' + '\n'.join(f'• {i}' for i in insights)
        if recommendations:
            analysis += '\n\n**Tavsiyalar:**\n' + '\n'.join(f'• {r}' for r in recommendations)
        if not insights:
            analysis += 'Ko\u2018rsatkichlar me\u2019yorida.'

        return {'analysis': analysis, 'model': 'rule_based', 'source': 'local'}
