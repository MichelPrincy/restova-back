"""Schémas des corps de requête (noms de champs identiques au contrat, en camelCase)."""
import re
from decimal import Decimal
from typing import Annotated, Any, Literal, Optional

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

from app.errors import CodedValueError

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------- briques réutilisables ----------

def _check_auth_email(v: str) -> str:
    if not EMAIL_RE.match(v):
        raise CodedValueError("INVALID_EMAIL", "Format d'email invalide.")
    return v


def _check_contact_email(v: str) -> str:
    if v and not EMAIL_RE.match(v):
        raise CodedValueError("VALIDATION_ERROR", "Format d'email invalide.")
    return v


def _check_password(v: str) -> str:
    if len(v) < 6:
        raise CodedValueError("WEAK_PASSWORD", "Le mot de passe doit contenir au moins 6 caractères.")
    return v


def _check_url(v: str) -> str:
    if v and not re.match(r"^https?://\S+$", v):
        raise CodedValueError("VALIDATION_ERROR", "URL invalide (http:// ou https:// attendu).")
    return v


def _clean_str_list(v: Any) -> Any:
    if isinstance(v, list):
        return [s.strip() for s in v if isinstance(s, str) and s.strip()]
    return v


def _s(max_len: int, min_len: int = 1) -> Any:
    return StringConstraints(strip_whitespace=True, min_length=min_len, max_length=max_len)


Name120 = Annotated[str, _s(120)]
Name200 = Annotated[str, _s(200)]
Phone = Annotated[str, _s(50)]
Address = Annotated[str, _s(500)]
ShortId = Annotated[str, _s(40)]
Text2000 = Annotated[str, _s(2000, 0)]
OptText = Annotated[str, _s(120, 0)]
Url = Annotated[str, _s(2048, 0), AfterValidator(_check_url)]
CleanList = Annotated[list[Name120], BeforeValidator(_clean_str_list)]

Money = Annotated[Decimal, Field(ge=0, le=Decimal("1000000000"), allow_inf_nan=False)]
Delta = Annotated[Decimal, Field(ge=Decimal("-1000000000"), le=Decimal("1000000000"), allow_inf_nan=False)]
Latitude = Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]
Longitude = Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]


class In(BaseModel):
    model_config = ConfigDict(extra="ignore")  # ignore id, createdAt, etc.


# ---------- auth ----------

class RegisterIn(In):
    restaurantName: Name200
    email: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, max_length=320),
                     AfterValidator(_check_auth_email)]
    password: Annotated[str, StringConstraints(max_length=256), AfterValidator(_check_password)]
    phone: Phone
    address: Address
    latitude: Latitude
    longitude: Longitude
    logoUrl: Optional[Url] = None


class LoginIn(In):
    email: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=1, max_length=320)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=256)]


class ProfileIn(In):
    name: Name200
    address: Address
    latitude: Latitude
    longitude: Longitude
    phone: Phone
    logoUrl: Url = ""
    openingHours: Annotated[str, _s(500, 0)] = ""
    currency: Annotated[str, _s(10)] = "Ar"
    email: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, max_length=320),
                     AfterValidator(_check_contact_email)] = ""
    tagline: Annotated[str, _s(500, 0)] = ""


# ---------- catégories ----------

class CategoryCreate(In):
    name: Name120
    icon: Annotated[str, _s(16, 0)] = "🍽️"
    description: Optional[Annotated[str, _s(500, 0)]] = None


class CategoryPatch(In):
    name: Optional[Name120] = None
    icon: Optional[Annotated[str, _s(16, 0)]] = None
    description: Optional[Annotated[str, _s(500, 0)]] = None


# ---------- menu ----------

class ExtraIn(In):
    id: Optional[ShortId] = None
    name: Name120
    price: Money


class OptionsIn(In):
    sauces: Optional[CleanList] = None
    extras: Optional[list[ExtraIn]] = None


class MenuItemCreate(In):
    name: Name200
    description: Text2000 = ""
    price: Money
    category: ShortId
    imageUrl: Url = ""
    isAvailable: bool = True
    isPopular: bool = False
    isSpicy: bool = False
    isVeggie: bool = False
    preparationTimeMinutes: int = Field(default=10, ge=0, le=1440)
    ingredients: CleanList = Field(default_factory=list)
    options: Optional[OptionsIn] = None


class MenuItemPatch(In):
    name: Optional[Name200] = None
    description: Optional[Text2000] = None
    price: Optional[Money] = None
    category: Optional[ShortId] = None
    imageUrl: Optional[Url] = None
    isAvailable: Optional[bool] = None
    isPopular: Optional[bool] = None
    isSpicy: Optional[bool] = None
    isVeggie: Optional[bool] = None
    preparationTimeMinutes: Optional[int] = Field(default=None, ge=0, le=1440)
    ingredients: Optional[CleanList] = None
    options: Optional[OptionsIn] = None


# ---------- stock ----------

class StockCreate(In):
    name: Name200
    category: Name120
    quantity: Money
    unit: Annotated[str, _s(30)]
    minThreshold: Money
    costPerUnit: Money
    supplier: Optional[Annotated[str, _s(200, 0)]] = None


class StockQuantityPatch(In):
    delta: Optional[Delta] = None
    quantity: Optional[Money] = None


# ---------- commandes ----------

OrderStatus = Literal["recue", "en_preparation", "prete", "en_livraison", "livree", "annulee"]
OrderType = Literal["sur_place", "a_emporter", "livraison"]
PaymentMethod = Literal["mvola", "orange_money", "airtel_money", "carte_bancaire", "especes"]


class OrderStatusIn(In):
    status: OrderStatus
    deliveryPersonName: Optional[Annotated[str, _s(200, 0)]] = None


class ExtraRef(In):
    id: ShortId
    name: Any = None   # ignoré : nom et prix viennent du menu
    price: Any = None


class CartItemIn(In):
    id: Any = None     # id de ligne du panier côté front, non conservé
    menuItemId: ShortId
    name: Optional[str] = None   # sert uniquement au message d'erreur
    price: Any = None            # ignoré : le prix est recalculé
    imageUrl: Any = None
    quantity: int = Field(ge=1, le=100)
    selectedSauce: Optional[Annotated[str, _s(120, 0)]] = None
    selectedExtras: list[ExtraRef] = Field(default_factory=list, max_length=30)
    specialInstructions: Optional[Annotated[str, _s(500, 0)]] = None


class Coordinates(In):
    lat: Latitude
    lng: Longitude


class PublicOrderIn(In):
    customerName: Name200
    customerPhone: Phone
    orderType: OrderType
    tableNumber: Optional[Annotated[str, _s(30, 0)]] = None
    deliveryAddress: Optional[Annotated[str, _s(500, 0)]] = None
    deliveryCoordinates: Optional[Coordinates] = None
    deliveryDistanceKm: Optional[float] = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    deliveryDurationMin: Optional[float] = Field(default=None, ge=0, le=100000, allow_inf_nan=False)
    deliveryInstructions: Optional[Annotated[str, _s(500, 0)]] = None
    items: list[CartItemIn] = Field(min_length=1, max_length=50)
    paymentMethod: PaymentMethod
    payerPhone: Optional[Annotated[str, _s(50, 0)]] = None
    note: Optional[Annotated[str, _s(500, 0)]] = None


# ---------- liens d'accès ----------

class AccessLinkCreate(In):
    tableNumber: Optional[Annotated[str, _s(30, 0)]] = None
    label: Optional[Annotated[str, _s(120, 0)]] = None
    expiresInHours: Optional[int] = Field(default=None, ge=1, le=24 * 365)
