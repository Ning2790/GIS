"""模型登记表：集中导入所有模块的 ORM 模型。

Alembic 自动生成迁移、init_db() 建表都依赖此文件。**新增模块后必须在此加一行 import**，
否则该模块的表不会被检测到。
"""

from app.modules.admin.models import AuditLog  # noqa: F401
from app.modules.ai.models import AiConversation, AiMessage, KnowledgeChunk  # noqa: F401
from app.modules.auth.models import DeviceBinding, LoginSession  # noqa: F401
from app.modules.b2b.models import B2bDemand, B2bMatch, B2bSupply  # noqa: F401
from app.modules.cs.models import CsMessage, CsSession  # noqa: F401
from app.modules.files.models import FileObject  # noqa: F401
from app.modules.gear.models import GearRecommendation, WeatherSnapshot  # noqa: F401
from app.modules.notifications.models import Notification  # noqa: F401
from app.modules.shop.models import AfterSale, AfterSaleMessage, Order, Product  # noqa: F401
from app.modules.travel.models import (  # noqa: F401
    Attraction,
    Itinerary,
    ItineraryStop,
    Route,
    RouteStop,
    Ticket,
)
from app.modules.users.models import Address, User  # noqa: F401

__all__ = [
    "Address",
    "AfterSale",
    "AfterSaleMessage",
    "AiConversation",
    "AiMessage",
    "Attraction",
    "AuditLog",
    "B2bDemand",
    "B2bMatch",
    "B2bSupply",
    "CsMessage",
    "CsSession",
    "DeviceBinding",
    "FileObject",
    "GearRecommendation",
    "Itinerary",
    "ItineraryStop",
    "LoginSession",
    "Notification",
    "Order",
    "Product",
    "Route",
    "RouteStop",
    "Ticket",
    "User",
    "WeatherSnapshot",
]
