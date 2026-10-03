from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AiAnalysisConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.ai_analysis'
    label = 'ai_analysis'
    verbose_name = _('AI analysis')
