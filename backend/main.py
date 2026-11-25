from datetime import datetime, timedelta, date
import base64, hashlib, hmac, json, os, re, time, secrets, urllib.request, urllib.error
from pathlib import Path
from decimal import Decimal
from typing import Any
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT_DIR / '.env'
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding='utf-8').splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip())

DB = dict(dbname=os.getenv('POTOLOK_DB_NAME','potolok_db'), host=os.getenv('POTOLOK_DB_HOST','localhost'), port=int(os.getenv('POTOLOK_DB_PORT','5432')), user=os.getenv('POTOLOK_DB_USER','postgres'), password=os.getenv('POTOLOK_DB_PASSWORD',''))
app = FastAPI(title='Potolok API')
CORS_ORIGINS = [origin.strip() for origin in os.getenv('POTOLOK_CORS_ORIGINS', '*').split(',') if origin.strip()]
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=['GET','POST','PUT','PATCH','DELETE','OPTIONS'], allow_headers=['*'])

TOKEN_SECRET = os.getenv('POTOLOK_ADMIN_SECRET', 'change-this-admin-secret')
ADMIN_READ_PATHS = {'/applications/','/orders/','/products/','/services/','/clients/','/employees/','/brigades/','/installers/','/payments/','/deliveries/'}
APPLICATION_STATUSES = {'Новая','В работе','Назначен исполнитель','Подтверждена','Выполняется','Завершена','Отменена'}
ORDER_STATUSES = {'Новый','Ожидает оплаты','Оплачен','Собирается','Передан в доставку','Завершён','Отменён'}
PAYMENT_STATUSES = {'Ожидает оплаты','Оплачен','Ошибка','Возврат'}
DELIVERY_STATUSES = {'Ожидает обработки','Передан в доставку','Передан','Доставлен'}
DELIVERY_METHODS = {'delivery','installer','pickup'}
PAYMENT_METHODS = {'online','cash','card_on_delivery'}
ACTIVE_APPLICATION_STATUSES = {'Новая','В работе','Назначен исполнитель','Подтверждена','Выполняется'}
LOGIN_FAILURES = {}
def password_hash(value: str) -> str:
    return hashlib.pbkdf2_hmac('sha256', value.encode(), b'potolok-admin', 120000).hex()
def make_token(employee_id: int) -> str:
    payload = {'employee_id': employee_id, 'exp': int((datetime.utcnow()+timedelta(hours=12)).timestamp())}
    raw = base64.urlsafe_b64encode(json.dumps(payload,separators=(',',':')).encode()).decode().rstrip('=')
    sig = hmac.new(TOKEN_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return raw + '.' + sig
def valid_token(value: str | None) -> bool:
    try:
        raw, sig = value.split('.', 1); expected=hmac.new(TOKEN_SECRET.encode(),raw.encode(),hashlib.sha256).hexdigest()
        payload=json.loads(base64.urlsafe_b64decode(raw+'='*(-len(raw)%4)))
        if not hmac.compare_digest(sig, expected) or payload['exp'] <= int(datetime.utcnow().timestamp()): return False
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute('select 1 from employees where id_employee=%s', (payload['employee_id'],))
            return cur.fetchone() is not None
    except Exception: return False

def validate_email(value: str):
    if value and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', value):
        raise HTTPException(422, 'Укажите корректный email')

def normalize_service_rules(executor_type: str, requires_visit: bool, requires_date: bool):
    if executor_type not in {'installer','brigade','either','none'}:
        raise HTTPException(400, 'Недопустимый тип исполнителя')
    if not requires_visit or executor_type == 'none':
        return 'none', False, False
    return executor_type, True, requires_date

def apply_schema_compatibility():
    statements = [
        "ALTER TABLE applications ADD COLUMN IF NOT EXISTS id_installer INTEGER REFERENCES installers(id_installer)",
        "ALTER TABLE applications ADD COLUMN IF NOT EXISTS privacy_consent_at TIMESTAMP",
        "ALTER TABLE services ADD COLUMN IF NOT EXISTS executor_type VARCHAR(20) NOT NULL DEFAULT 'either'",
        "ALTER TABLE services ADD COLUMN IF NOT EXISTS requires_visit BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE services ADD COLUMN IF NOT EXISTS requires_date BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS id_application INTEGER REFERENCES applications(id_application)",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS comment TEXT",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS privacy_consent_at TIMESTAMP",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_access_token VARCHAR(128)",
        "ALTER TABLE deliveries ADD COLUMN IF NOT EXISTS carrier VARCHAR(100)",
        "ALTER TABLE payments ADD COLUMN IF NOT EXISTS paid_at TIMESTAMP",
        "CREATE INDEX IF NOT EXISTS applications_installer_date_idx ON applications(id_installer, installation_date)",
        "CREATE INDEX IF NOT EXISTS orders_application_idx ON orders(id_application)",
        "CREATE UNIQUE INDEX IF NOT EXISTS orders_payment_access_token_idx ON orders(payment_access_token) WHERE payment_access_token IS NOT NULL",
    ]
    try:
        with get_conn() as conn, conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)
            cur.execute('select id_order from orders where payment_access_token is null')
            for row in cur.fetchall():
                cur.execute('update orders set payment_access_token=%s where id_order=%s', (secrets.token_urlsafe(32), row[0]))
            conn.commit()
    except Exception:
        # Startup must remain available when the database is temporarily offline.
        pass

@app.on_event('startup')
def startup_migrations():
    apply_schema_compatibility()

@app.middleware('http')
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
    return response

@app.middleware('http')
async def protect_admin_api(request: Request, call_next):
    path=request.url.path.rstrip('/')
    public = ((path in {'/products','/services'} and request.method == 'GET') or
              (path in {'/applications','/orders','/payments/webhook'} and request.method == 'POST') or
              (re.fullmatch(r'/orders/\d+/payment', path) and request.method == 'POST'))
    protected = any(path == base.rstrip('/') or path.startswith(base) for base in ADMIN_READ_PATHS | {'/availability/'}) and not public
    if protected and request.method != 'OPTIONS' and not valid_token(request.headers.get('Authorization','').removeprefix('Bearer ')):
        from starlette.responses import JSONResponse
        return JSONResponse({'detail':'Требуется вход администратора'}, status_code=401)
    return await call_next(request)

def get_conn(): return psycopg2.connect(**DB)
def one(cur):
    row=cur.fetchone(); return dict(row) if row else None

apply_schema_compatibility()

class ApplicationIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    number_phone: str = Field(min_length=5, max_length=20)
    email: str = ""
    area: float = Field(gt=0)
    service: str
    address: str = Field(min_length=3, max_length=255)
    comment: str | None = None
    privacy_consent: bool = False
class OrderItemIn(BaseModel):
    product_id: Any = None
    name: str = ''
    quantity: int = Field(gt=0, le=99)
    price: float | None = None
class OrderIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    number_phone: str = Field(min_length=5, max_length=20)
    email: str = ""
    address: str | None = None
    comment: str | None = None
    delivery: str = 'delivery'
    items: list[OrderItemIn] = Field(min_length=1)
    total: float | None = Field(default=None, ge=0)
    payment_method: str = 'online'
    application_id: int | None = None
    privacy_consent: bool = False
    return_url: str | None = None
    carrier: str | None = None

class LoginIn(BaseModel):
    login: str
    password: str

class PaymentSessionIn(BaseModel):
    access_token: str = Field(min_length=20, max_length=128)
    return_url: str | None = None

@app.post('/auth/login')
def admin_login(payload: LoginIn, request: Request):
    ip=request.client.host if request.client else 'unknown'
    now=time.monotonic()
    failures=[stamp for stamp in LOGIN_FAILURES.get(ip, []) if now-stamp < 900]
    LOGIN_FAILURES[ip]=failures
    if len(failures) >= 10:
        raise HTTPException(429, 'Слишком много попыток входа. Повторите через 15 минут')
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('select id_employee,full_name,position,login,password_hash from employees where login=%s',(payload.login,)); employee=one(cur)
    if not employee or not hmac.compare_digest(employee['password_hash'], password_hash(payload.password)):
        failures.append(now)
        raise HTTPException(401,'Неверный логин или пароль')
    LOGIN_FAILURES.pop(ip, None)
    return {'access_token':make_token(employee['id_employee']),'employee':{k:employee[k] for k in ('id_employee','full_name','position','login')}}

@app.get('/auth/me')
def admin_me(request: Request):
    if not valid_token(request.headers.get('Authorization','').removeprefix('Bearer ')): raise HTTPException(401,'Требуется вход администратора')
    return {'authenticated':True}

@app.get('/')
def home(): return {'message':'Сервер работает!'}
@app.get('/check-db')
def check_database():
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("select tablename from pg_tables where schemaname='public' order by tablename")
            return {'status':'success','database':'potolok_db','tables':[r[0] for r in cur.fetchall()]}
    except Exception as e: raise HTTPException(500, str(e))

@app.get('/products/')
def get_products():
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('select id_product, name, description, price, stock_quantity, image from products order by id_product')
        return [dict(r) for r in cur.fetchall()]

@app.post('/applications/', status_code=201)
def create_application(payload: ApplicationIn):
    if not payload.privacy_consent: raise HTTPException(400, 'Нужно согласиться с политикой конфиденциальности')
    validate_email(payload.email)
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("insert into clients(full_name,phone,email) values (%s,%s,%s) on conflict (phone) do update set full_name=excluded.full_name,email=case when excluded.email<>'' then excluded.email else clients.email end returning id_client", (payload.name,payload.number_phone,payload.email))
        client=one(cur)
        if not client:
            cur.execute('select id_client from clients where phone=%s', (payload.number_phone,)); client=one(cur)
        cur.execute('select id_service from services where name=%s', (payload.service,)); service=one(cur)
        if not service: raise HTTPException(400, 'Выбранная услуга не найдена')
        cur.execute('''insert into applications(id_client,id_service,created_at,preliminary_area,installation_address,comment,status,privacy_consent_at)
                       values (%s,%s,current_timestamp,%s,%s,%s,%s,current_timestamp) returning id_application''', (client['id_client'],service['id_service'],payload.area,payload.address,payload.comment,'Новая'))
        app_row=one(cur); conn.commit(); return {'status':'success','id_application':app_row['id_application']}

@app.post('/orders/', status_code=201)
def create_order(payload: OrderIn):
    if not payload.privacy_consent: raise HTTPException(400, 'Нужно согласиться с политикой конфиденциальности')
    validate_email(payload.email)
    if payload.delivery not in {'delivery', 'installer'}:
        raise HTTPException(400, 'Недопустимый способ получения заказа')
    payment_method = 'online' if payload.delivery == 'delivery' else 'with_application'
    if payload.delivery == 'delivery' and not (payload.address or '').strip():
        raise HTTPException(400, 'Укажите адрес доставки')
    if payload.delivery == 'delivery' and payload.carrier not in {'СДЭК','Почта России','Другая'}:
        raise HTTPException(400, 'Выберите службу доставки')
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        digits = re.sub(r'\D', '', payload.number_phone)
        if len(digits) == 11 and digits[0] == '8': digits = '7' + digits[1:]
        if len(digits) < 10: raise HTTPException(400, 'Укажите корректный номер телефона')
        application = None
        if payload.delivery == 'installer':
            cur.execute('''select a.id_application,a.id_client,a.status,a.installation_address,s.name service_name
                           from applications a join clients c using(id_client) join services s using(id_service)
                           where right(regexp_replace(c.phone, '[^0-9]', '', 'g'),10)=%s
                           and lower(trim(c.full_name))=lower(trim(%s))
                           and a.status not in ('Отменена','Завершена') and s.requires_visit=true
                           order by a.created_at desc''', (digits[-10:], payload.name))
            candidates=[dict(row) for row in cur.fetchall()]
            if not candidates: raise HTTPException(400, 'Активная заявка с таким именем и телефоном не найдена. Оставьте заявку или проверьте данные.')
            if payload.application_id is None and len(candidates)>1:
                raise HTTPException(409, {'code':'choose_application','message':'Найдено несколько заявок. Выберите нужную.','applications':[{'id':a['id_application'],'address':a['installation_address'],'service':a['service_name']} for a in candidates]})
            application=next((a for a in candidates if a['id_application']==payload.application_id),None) if payload.application_id else candidates[0]
            if not application: raise HTTPException(400, 'Выбранная заявка не найдена среди активных заявок')
            cur.execute('select id_application,status from applications where id_application=%s for update', (application['id_application'],))
            locked=one(cur)
            if not locked or locked['status'] in {'Отменена','Завершена'}: raise HTTPException(409, 'Заявка уже закрыта')
            client={'id_client':application['id_client']}
        else:
            cur.execute("insert into clients(full_name,phone,email) values (%s,%s,%s) on conflict (phone) do update set full_name=excluded.full_name,email=case when excluded.email<>'' then excluded.email else clients.email end returning id_client", (payload.name,payload.number_phone,payload.email))
            client=one(cur)
        requested_quantities={}
        products_by_id={}
        for item in payload.items:
            product=None
            if isinstance(item.product_id, int) or (isinstance(item.product_id, str) and item.product_id.isdigit()):
                cur.execute('select id_product,name,price,stock_quantity from products where id_product=%s for update',(int(item.product_id),)); product=one(cur)
            if not product and item.name:
                cur.execute('select id_product,name,price,stock_quantity from products where name=%s for update',(item.name,)); product=one(cur)
            if not product:
                raise HTTPException(400, f'Товар не найден: {item.name or item.product_id}')
            product_id=product['id_product']
            products_by_id[product_id]=product
            requested_quantities[product_id]=requested_quantities.get(product_id, 0)+item.quantity
        for product_id, quantity in requested_quantities.items():
            product=products_by_id[product_id]
            if product['stock_quantity'] < quantity:
                raise HTTPException(400, f'Недостаточно товара на складе: {product["name"]}')
        normalized=[(products_by_id[product_id], quantity) for product_id, quantity in requested_quantities.items()]
        total=sum(Decimal(str(product['price']))*quantity for product,quantity in normalized)
        payment_access_token=secrets.token_urlsafe(32)
        cur.execute('''insert into orders(id_client,id_application,order_date,total_amount,status,comment,privacy_consent_at,payment_access_token)
                       values (%s,%s,current_timestamp,%s,%s,%s,current_timestamp,%s) returning id_order''',
                    (client['id_client'], application['id_application'] if application else None, total, 'Новый', payload.comment, payment_access_token))
        order=one(cur)
        for product, quantity in normalized:
            cur.execute('insert into order_items(id_order,id_product,quantity,purchase_price) values (%s,%s,%s,%s)',(order['id_order'],product['id_product'],quantity,product['price']))
            cur.execute('update products set stock_quantity=stock_quantity-%s where id_product=%s',(quantity,product['id_product']))
        address = payload.address if payload.delivery == 'delivery' else None
        if payload.delivery == 'delivery' and not address:
            raise HTTPException(400, 'Укажите адрес доставки')
        cur.execute('insert into deliveries(id_order,delivery_method,address,status,carrier) values (%s,%s,%s,%s,%s)',(order['id_order'],payload.delivery,address,'Ожидает обработки',payload.carrier if payload.delivery == 'delivery' else None))
        cur.execute('insert into payments(id_order,amount,payment_method,status) values (%s,%s,%s,%s)',(order['id_order'],total,payment_method,'Ожидает оплаты'))
        conn.commit()
        return {'status':'success','id_order':order['id_order'],'total':float(total),'checkout_token':payment_access_token}

def yookassa_payment(order_id: int, amount: Decimal, return_url: str):
    shop_id=os.getenv('YOOKASSA_SHOP_ID')
    secret_key=os.getenv('YOOKASSA_SECRET_KEY')
    if not shop_id or not secret_key:
        return None
    payload=json.dumps({
        'amount': {'value': f'{amount:.2f}', 'currency': 'RUB'},
        'capture': True,
        'confirmation': {'type': 'redirect', 'return_url': return_url},
        'description': f'Оплата заказа №{order_id}',
        'metadata': {'order_id': str(order_id)}
    }).encode()
    request=urllib.request.Request('https://api.yookassa.ru/v3/payments', data=payload, method='POST')
    credentials=base64.b64encode(f'{shop_id}:{secret_key}'.encode()).decode()
    request.add_header('Authorization', f'Basic {credentials}')
    request.add_header('Content-Type', 'application/json')
    request.add_header('Idempotence-Key', secrets.token_hex(16))
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        detail=error.read().decode(errors='replace')[:500]
        raise HTTPException(502, f'Платёжный сервис вернул ошибку: {detail}')
    except (urllib.error.URLError, TimeoutError):
        raise HTTPException(502, 'Платёжный сервис временно недоступен')

@app.post('/orders/{order_id}/payment')
def create_payment_session(order_id: int, payload: PaymentSessionIn):
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('''select o.id_order,o.total_amount,o.status,o.payment_access_token,
                              p.id_payment,p.status payment_status,p.payment_method,p.transaction_number
                       from orders o join payments p using(id_order)
                       where o.id_order=%s and o.payment_access_token=%s for update''', (order_id,payload.access_token))
        order=one(cur)
        if not order: raise HTTPException(404, 'Заказ не найден')
        if order['status'] in {'Отменён','Завершён'}: raise HTTPException(409, 'Заказ уже закрыт')
        if order['payment_status'] == 'Оплачен': return {'status':'paid','id_order':order_id}
        if order['payment_method'] != 'online': raise HTTPException(400, 'Для этого заказа выбрана оплата при получении')
        return_url=payload.return_url or os.getenv('POTOLOK_PAYMENT_RETURN_URL') or 'http://localhost:5500/cart.html'
        provider_result=yookassa_payment(order_id, Decimal(str(order['total_amount'])), return_url)
        if provider_result is None:
            conn.commit()
            return {'status':'manual','id_order':order_id,'message':'Платёжный сервис ещё не настроен. Менеджер отправит ссылку на оплату.'}
        provider_id=provider_result.get('id')
        confirmation_url=(provider_result.get('confirmation') or {}).get('confirmation_url')
        if not provider_id or not confirmation_url: raise HTTPException(502, 'Платёжный сервис не вернул ссылку на оплату')
        cur.execute('update payments set transaction_number=%s,status=%s where id_payment=%s returning id_payment',(provider_id,'Ожидает оплаты',order['id_payment']))
        conn.commit()
        return {'status':'redirect','id_order':order_id,'payment_id':provider_id,'confirmation_url':confirmation_url}

@app.post('/payments/webhook')
def payment_webhook(payload: dict[str, Any]):
    event=payload.get('event')
    payment_object=payload.get('object') or {}
    provider_id=payment_object.get('id')
    provider_status=payment_object.get('status')
    if not provider_id or not event: raise HTTPException(400, 'Некорректное уведомление платёжного сервиса')
    mapped_status={'payment.succeeded':'Оплачен','payment.canceled':'Ошибка'}.get(event)
    if not mapped_status: return {'accepted':True,'ignored':True}
    shop_id=os.getenv('YOOKASSA_SHOP_ID'); secret_key=os.getenv('YOOKASSA_SECRET_KEY')
    if not shop_id or not secret_key: raise HTTPException(503, 'Платёжный сервис не настроен')
    if not re.fullmatch(r'[A-Za-z0-9-]{1,100}', str(provider_id)): raise HTTPException(400, 'Некорректный идентификатор платежа')
    request=urllib.request.Request(f'https://api.yookassa.ru/v3/payments/{provider_id}')
    request.add_header('Authorization', 'Basic ' + base64.b64encode(f'{shop_id}:{secret_key}'.encode()).decode())
    try:
        with urllib.request.urlopen(request, timeout=15) as response: verified=json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError): raise HTTPException(502, 'Не удалось проверить платёж')
    expected_status={'payment.succeeded':'succeeded','payment.canceled':'canceled'}[event]
    if verified.get('id') != provider_id or verified.get('status') != expected_status:
        raise HTTPException(400, 'Статус платежа не подтверждён')
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('select id_payment,id_order from payments where transaction_number=%s for update',(provider_id,)); payment=one(cur)
        if not payment: return {'accepted':True,'ignored':True}
        cur.execute('''update payments set status=%s,paid_at=case when %s='Оплачен' then coalesce(paid_at,current_timestamp) else null end,
                       payment_date=case when %s='Оплачен' then coalesce(payment_date,current_timestamp) else payment_date end
                       where id_payment=%s''',(mapped_status,mapped_status,mapped_status,payment['id_payment']))
        if mapped_status == 'Оплачен': cur.execute("update orders set status='Оплачен' where id_order=%s and status not in ('Отменён','Завершён')",(payment['id_order'],))
        conn.commit()
    return {'accepted':True,'status':mapped_status,'provider_status':provider_status}

# Административные API-методы для управления данными системы
class ProductIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str = ''
    price: float = Field(ge=0)
    stock_quantity: int = Field(ge=0)
    image: str | None = None
class StatusIn(BaseModel):
    status: str = Field(min_length=1, max_length=50)
class AssignApplicationIn(BaseModel):
    employee_id: int | None = None
    installer_id: int | None = None
    brigade_id: int | None = None
    installation_date: datetime | None = None
class EmployeeIn(BaseModel):
    full_name: str; phone: str; position: str; login: str; password_hash: str
class BrigadeIn(BaseModel):
    brigade_name: str; phone: str
class InstallerIn(BaseModel):
    full_name: str; phone: str; id_brigade: int
class ServiceIn(BaseModel):
    name: str; description: str = ''; base_price: float = Field(ge=0)
    executor_type: str = 'either'
    requires_visit: bool = True
    requires_date: bool = True


def rows(sql, params=()):
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

def execute_returning(sql, params=()):
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params); result=one(cur); conn.commit(); return result

@app.get('/applications/')
def list_applications():
    return rows('''select a.*, c.full_name client_name, c.phone client_phone, c.email client_email,
                         s.name service_name, s.executor_type, s.requires_visit, s.requires_date,
                         e.full_name employee_name, b.brigade_name, i.full_name installer_name
                  from applications a join clients c using(id_client) join services s using(id_service)
                  left join employees e using(id_employee) left join brigades b using(id_brigade)
                  left join installers i using(id_installer)
                  order by a.created_at desc''')

@app.patch('/applications/{application_id}/status')
def update_application_status(application_id: int, payload: StatusIn):
    if payload.status not in APPLICATION_STATUSES: raise HTTPException(400,'Недопустимый статус заявки')
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('''select a.*,s.requires_visit,s.requires_date from applications a
                       join services s using(id_service) where a.id_application=%s for update''',(application_id,))
        application=one(cur)
        if not application: raise HTTPException(404,'Заявка не найдена')
        needs_executor=payload.status in {'Назначен исполнитель','Подтверждена','Выполняется'}
        if needs_executor and application['requires_visit']:
            if not application['id_installer'] and not application['id_brigade']:
                raise HTTPException(400,'Сначала назначьте монтажника или бригаду')
            if application['requires_date'] and not application['installation_date']:
                raise HTTPException(400,'Сначала укажите дату монтажа')
        cur.execute('update applications set status=%s where id_application=%s returning *',(payload.status,application_id))
        result=one(cur); conn.commit(); return result

@app.patch('/applications/{application_id}/assign')
def assign_application(application_id: int, payload: AssignApplicationIn):
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('''select a.id_application,a.status,a.id_employee,a.id_installer,a.id_brigade,a.installation_date,
                              s.executor_type,s.requires_visit,s.requires_date
                       from applications a join services s using(id_service)
                       where a.id_application=%s for update''',(application_id,)); application=one(cur)
        if not application: raise HTTPException(404,'Заявка не найдена')
        if payload.employee_id is not None:
            cur.execute('select id_employee from employees where id_employee=%s',(payload.employee_id,))
            if not cur.fetchone(): raise HTTPException(400,'Сотрудник не найден')
        if payload.brigade_id is not None:
            cur.execute('select id_brigade from brigades where id_brigade=%s',(payload.brigade_id,))
            if not cur.fetchone(): raise HTTPException(400,'Бригада не найдена')
        if payload.installer_id is not None:
            cur.execute('select id_installer,id_brigade from installers where id_installer=%s',(payload.installer_id,))
            installer=one(cur)
            if not installer: raise HTTPException(400,'Монтажник не найден')
        else:
            installer=None
        if payload.installer_id is not None and payload.brigade_id is not None:
            raise HTTPException(400,'Выберите монтажника или бригаду')
        if not application['requires_visit']:
            if payload.installer_id is not None or payload.brigade_id is not None or payload.installation_date is not None:
                raise HTTPException(400,'Для этой услуги выезд не требуется')
        executor_type=application['executor_type']
        selected='installer' if payload.installer_id is not None else ('brigade' if payload.brigade_id is not None else None)
        if application['requires_visit']:
            if executor_type == 'installer' and selected != 'installer': raise HTTPException(400,'Для услуги нужен монтажник')
            if executor_type == 'brigade' and selected != 'brigade': raise HTTPException(400,'Для услуги нужна бригада')
            if executor_type == 'either' and selected is None: raise HTTPException(400,'Выберите монтажника или бригаду')
            if application['requires_date'] and payload.installation_date is None: raise HTTPException(400,'Укажите дату монтажа')
            if payload.installation_date is not None and payload.installation_date.date() < date.today():
                raise HTTPException(400, 'Дата назначения не может быть в прошлом')
        if selected is not None and payload.installation_date is not None:
            lock_key=f'brigade:{installer["id_brigade"] if installer else payload.brigade_id}:{payload.installation_date.date()}'
            cur.execute('select pg_advisory_xact_lock(hashtext(%s))', (lock_key,))
            brigade_id_for_check=installer['id_brigade'] if installer else payload.brigade_id
            brigade_condition='a.id_brigade=%s' if selected == 'brigade' else '(a.id_brigade=%s and a.id_installer is null)'
            cur.execute(f"""select a.id_application from applications a where {brigade_condition} and a.installation_date is not null
                           and a.installation_date::date=%s and a.id_application<>%s
                           and a.status = any(%s) for update""",(brigade_id_for_check,payload.installation_date.date(),application_id,list(ACTIVE_APPLICATION_STATUSES)))
            busy=cur.fetchone()
            if busy and selected == 'brigade': raise HTTPException(409,'Бригада уже занята на выбранную дату')
            if busy and selected == 'installer': raise HTTPException(409,'Бригада уже занята на выбранную дату')
            if payload.installer_id is not None:
                cur.execute("""select a.id_application from applications a where a.id_installer=%s
                              and a.installation_date::date=%s and a.id_application<>%s
                              and a.status = any(%s) for update""",(payload.installer_id,payload.installation_date.date(),application_id,list(ACTIVE_APPLICATION_STATUSES)))
                if cur.fetchone(): raise HTTPException(409,'Монтажник уже занят на выбранную дату')
        employee_id=payload.employee_id
        installer_id=payload.installer_id
        brigade_id=payload.brigade_id
        installation_date=payload.installation_date
        if installation_date is not None and selected is None: raise HTTPException(400,'Сначала выберите исполнителя')
        status='Назначен исполнитель' if selected else ('В работе' if employee_id is not None else 'Новая')
        cur.execute('''update applications set id_employee=%s,id_installer=%s,id_brigade=%s,
                       installation_date=%s,status=%s where id_application=%s returning *''',(employee_id,installer_id,brigade_id,installation_date,status,application_id))
        result=one(cur); conn.commit(); return result

@app.get('/availability/')
def availability(selected_date: date = Query(..., alias='date')):
    return rows("""select b.id_brigade,b.brigade_name,b.phone,
                          a.id_application,a.installation_date,a.status,c.full_name client_name
                   from brigades b left join applications a on a.id_brigade=b.id_brigade
                     and a.installation_date::date=%s and a.status = any(%s)
                   left join clients c on c.id_client=a.id_client order by b.id_brigade""",(selected_date,list(ACTIVE_APPLICATION_STATUSES)))

@app.get('/brigades/{brigade_id}/schedule')
def brigade_schedule(brigade_id: int):
    return rows("""select a.id_application,a.installation_date,a.status,c.full_name client_name,a.installation_address
                   from applications a join clients c using(id_client)
                   where a.id_brigade=%s and a.installation_date is not null order by a.installation_date""",(brigade_id,))

@app.get('/installers/{installer_id}/schedule')
def installer_schedule(installer_id: int):
    return rows("""select a.id_application,a.installation_date,a.status,c.full_name client_name,
                         a.installation_address,s.name service_name
                  from applications a join clients c using(id_client)
                  join services s using(id_service)
                  where a.id_installer=%s and a.installation_date is not null
                  order by a.installation_date""", (installer_id,))

@app.get('/availability/installers/')
def installer_availability(selected_date: date = Query(..., alias='date')):
    return rows("""select i.id_installer,i.full_name,i.phone,i.id_brigade,b.brigade_name,
                  a.id_application,a.installation_date,a.status,c.full_name client_name,
                  (a.id_application is not null) as is_busy
                  from installers i join brigades b using(id_brigade)
                  left join applications a on (a.id_installer=i.id_installer or (a.id_brigade=i.id_brigade and a.id_installer is null))
                    and a.installation_date::date=%s and a.status = any(%s)
                  left join clients c on c.id_client=a.id_client order by i.id_installer""", (selected_date,list(ACTIVE_APPLICATION_STATUSES)))

@app.get('/orders/')
def list_orders():
    return rows('''select o.*, c.full_name client_name, c.phone client_phone, c.email,
                         e.full_name employee_name, a.status application_status,
                         a.installation_date, s.name service_name
                  from orders o join clients c using(id_client)
                  left join employees e using(id_employee)
                  left join applications a using(id_application)
                  left join services s on s.id_service=a.id_service
                  order by o.order_date desc''')

@app.get('/orders/{order_id}')
def get_order(order_id: int):
    order=rows('''select o.*, c.full_name client_name, c.phone client_phone, c.email,
                         a.status application_status,a.installation_date,s.name service_name
                  from orders o join clients c using(id_client)
                  left join applications a using(id_application)
                  left join services s on s.id_service=a.id_service
                  where o.id_order=%s''',(order_id,))
    if not order: raise HTTPException(404,'Заказ не найден')
    order[0]['items']=rows('''select oi.*, p.name product_name from order_items oi join products p using(id_product)
                              where oi.id_order=%s''',(order_id,))
    order[0]['payments']=rows('select * from payments where id_order=%s order by id_payment',(order_id,))
    order[0]['delivery']=rows('select * from deliveries where id_order=%s',(order_id,))
    return order[0]

@app.patch('/orders/{order_id}/status')
def update_order_status(order_id: int, payload: StatusIn):
    if payload.status not in ORDER_STATUSES: raise HTTPException(400,'Недопустимый статус заказа')
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('select * from orders where id_order=%s for update',(order_id,)); order=one(cur)
        if not order: raise HTTPException(404,'Заказ не найден')
        if payload.status == 'Оплачен':
            cur.execute("select 1 from payments where id_order=%s and status='Оплачен' limit 1",(order_id,))
            if not cur.fetchone(): raise HTTPException(400,'Сначала подтвердите оплату в разделе платежей')
        if payload.status == 'Передан в доставку':
            cur.execute("select 1 from deliveries where id_order=%s and status in ('Передан в доставку','Передан','Доставлен')",(order_id,))
            if not cur.fetchone(): raise HTTPException(400,'Сначала измените статус доставки')
        if payload.status == 'Завершён':
            cur.execute("select 1 from deliveries where id_order=%s and status in ('Передан','Доставлен')",(order_id,))
            if not cur.fetchone(): raise HTTPException(400,'Сначала подтвердите передачу или доставку заказа')
        cur.execute('update orders set status=%s where id_order=%s returning *',(payload.status,order_id))
        result=one(cur); conn.commit(); return result

@app.get('/clients/')
def list_clients(): return rows('select * from clients order by id_client desc')
@app.get('/employees/')
def list_employees(): return rows('select id_employee,full_name,phone,position,login from employees order by id_employee')
@app.post('/employees/', status_code=201)
def create_employee(payload: EmployeeIn):
    if len(payload.password_hash) < 8: raise HTTPException(400, 'Пароль должен содержать минимум 8 символов')
    try:
        return execute_returning('insert into employees(full_name,phone,position,login,password_hash) values (%s,%s,%s,%s,%s) returning id_employee,full_name,phone,position,login',(payload.full_name,payload.phone,payload.position,payload.login,password_hash(payload.password_hash)))
    except psycopg2.errors.UniqueViolation:
        raise HTTPException(409, 'Такой логин уже используется')
@app.get('/brigades/')
def list_brigades(): return rows('select b.*,count(i.id_installer)::int installer_count from brigades b left join installers i using(id_brigade) group by b.id_brigade order by b.id_brigade')
@app.post('/brigades/', status_code=201)
def create_brigade(payload: BrigadeIn): return execute_returning('insert into brigades(brigade_name,phone) values (%s,%s) returning *',(payload.brigade_name,payload.phone))
@app.get('/installers/')
def list_installers(selected_date: date | None = Query(default=None, alias='date')):
    if selected_date:
        return rows("""select i.*,b.brigade_name,exists(select 1 from applications a where (a.id_installer=i.id_installer or (a.id_brigade=i.id_brigade and a.id_installer is null)) and a.installation_date::date=%s and a.status = any(%s)) as is_busy,
                              (select a.installation_date from applications a where (a.id_installer=i.id_installer or (a.id_brigade=i.id_brigade and a.id_installer is null)) and a.installation_date::date=%s and a.status = any(%s) limit 1) as installation_date
                       from installers i join brigades b using(id_brigade) order by i.id_installer""",(selected_date,list(ACTIVE_APPLICATION_STATUSES),selected_date,list(ACTIVE_APPLICATION_STATUSES)))
    return rows('select i.*,b.brigade_name,false as is_busy,null::timestamp as installation_date from installers i join brigades b using(id_brigade) order by i.id_installer')

@app.post('/installers/', status_code=201)
def create_installer(payload: InstallerIn): return execute_returning('insert into installers(full_name,phone,id_brigade) values (%s,%s,%s) returning *',(payload.full_name,payload.phone,payload.id_brigade))
@app.get('/services/')
def list_services(): return rows('select * from services order by id_service')
@app.post('/services/', status_code=201)
def create_service(payload: ServiceIn):
    executor_type, requires_visit, requires_date = normalize_service_rules(payload.executor_type, payload.requires_visit, payload.requires_date)
    return execute_returning('''insert into services(name,description,base_price,executor_type,requires_visit,requires_date)
                                values (%s,%s,%s,%s,%s,%s) returning *''',(payload.name,payload.description,payload.base_price,executor_type,requires_visit,requires_date))
@app.post('/products/', status_code=201)
def create_product(payload: ProductIn): return execute_returning('insert into products(name,description,price,stock_quantity,image) values (%s,%s,%s,%s,%s) returning *',(payload.name,payload.description,payload.price,payload.stock_quantity,payload.image))
@app.patch('/products/{product_id}')
def update_product(product_id: int, payload: ProductIn):
    result=execute_returning('''update products set name=%s,description=%s,price=%s,stock_quantity=%s,image=%s
                                where id_product=%s returning *''',(payload.name,payload.description,payload.price,payload.stock_quantity,payload.image,product_id))
    if not result: raise HTTPException(404,'Товар не найден')
    return result
@app.delete('/clients/{client_id}')
def delete_client(client_id: int):
    try: result=execute_returning('delete from clients where id_client=%s returning id_client',(client_id,))
    except psycopg2.errors.ForeignKeyViolation: raise HTTPException(409,'У клиента есть заявки или заказы')
    if not result: raise HTTPException(404,'Клиент не найден')
    return {'status':'deleted','id_client':client_id}

@app.get('/payments/')
def list_payments(): return rows('select p.*,o.status order_status from payments p join orders o using(id_order) order by p.id_payment desc')
@app.get('/deliveries/')
def list_deliveries(): return rows('select d.*,o.status order_status from deliveries d join orders o using(id_order) order by d.id_delivery desc')

class DeliveryUpdateIn(BaseModel):
    delivery_method: str | None = None
    address: str | None = None
    delivery_date: datetime | None = None
    status: str | None = None
class PaymentStatusIn(BaseModel):
    status: str = Field(min_length=1, max_length=50)
class OrderAssignIn(BaseModel):
    employee_id: int | None = None
class EmployeeUpdateIn(BaseModel):
    full_name: str; phone: str; position: str; login: str; password_hash: str | None = None

@app.patch('/orders/{order_id}/assign')
def assign_order(order_id: int, payload: OrderAssignIn):
    result=execute_returning('update orders set id_employee=%s where id_order=%s returning *',(payload.employee_id,order_id))
    if not result: raise HTTPException(404,'Заказ не найден')
    return result

@app.put('/employees/{employee_id}')
def update_employee(employee_id: int, payload: EmployeeUpdateIn):
    if payload.password_hash is not None and len(payload.password_hash) < 8: raise HTTPException(400, 'Пароль должен содержать минимум 8 символов')
    result=execute_returning('''update employees set full_name=%s,phone=%s,position=%s,login=%s,
                                password_hash=coalesce(%s,password_hash) where id_employee=%s
                                returning id_employee,full_name,phone,position,login''',(payload.full_name,payload.phone,payload.position,payload.login,password_hash(payload.password_hash) if payload.password_hash else None,employee_id))
    if not result: raise HTTPException(404,'Сотрудник не найден')
    return result

@app.delete('/employees/{employee_id}')
def delete_employee(employee_id: int):
    try: result=execute_returning('delete from employees where id_employee=%s returning id_employee',(employee_id,))
    except psycopg2.errors.ForeignKeyViolation: raise HTTPException(409,'Сотрудник назначен в заявках или заказах')
    if not result: raise HTTPException(404,'Сотрудник не найден')
    return {'status':'deleted','id_employee':employee_id}

@app.put('/services/{service_id}')
def update_service(service_id: int, payload: ServiceIn):
    executor_type, requires_visit, requires_date = normalize_service_rules(payload.executor_type, payload.requires_visit, payload.requires_date)
    current=rows('select executor_type,requires_visit from services where id_service=%s',(service_id,))
    if not current: raise HTTPException(404,'Услуга не найдена')
    if current[0]['executor_type'] != executor_type or current[0]['requires_visit'] != requires_visit:
        active=rows('''select id_application from applications where id_service=%s
                       and status = any(%s) and (id_installer is not null or id_brigade is not null) limit 1''',(service_id,list(ACTIVE_APPLICATION_STATUSES)))
        if active: raise HTTPException(409,'Нельзя менять тип исполнителя у услуги с назначенными заявками')
    result=execute_returning('''update services set name=%s,description=%s,base_price=%s,executor_type=%s,
                                requires_visit=%s,requires_date=%s where id_service=%s returning *''',(payload.name,payload.description,payload.base_price,executor_type,requires_visit,requires_date,service_id))
    if not result: raise HTTPException(404,'Услуга не найдена')
    return result

@app.delete('/services/{service_id}')
def delete_service(service_id: int):
    try:
        result=execute_returning('delete from services where id_service=%s returning id_service',(service_id,))
    except psycopg2.errors.ForeignKeyViolation:
        raise HTTPException(409,'Услуга используется в заявках и не может быть удалена')
    if not result: raise HTTPException(404,'Услуга не найдена')
    return {'status':'deleted','id_service':service_id}

@app.put('/brigades/{brigade_id}')
def update_brigade(brigade_id: int, payload: BrigadeIn):
    result=execute_returning('update brigades set brigade_name=%s,phone=%s where id_brigade=%s returning *',(payload.brigade_name,payload.phone,brigade_id))
    if not result: raise HTTPException(404,'Бригада не найдена')
    return result

@app.delete('/brigades/{brigade_id}')
def delete_brigade(brigade_id: int):
    try: result=execute_returning('delete from brigades where id_brigade=%s returning id_brigade',(brigade_id,))
    except psycopg2.errors.ForeignKeyViolation: raise HTTPException(409,'Бригада используется в заявках или содержит монтажников')
    if not result: raise HTTPException(404,'Бригада не найдена')
    return {'status':'deleted','id_brigade':brigade_id}

@app.put('/installers/{installer_id}')
def update_installer(installer_id: int, payload: InstallerIn):
    current=rows('select id_brigade from installers where id_installer=%s',(installer_id,))
    if not current: raise HTTPException(404,'Монтажник не найден')
    if current[0]['id_brigade'] != payload.id_brigade:
        assigned=rows('''select id_application from applications where id_installer=%s
                        and status = any(%s) limit 1''',(installer_id,list(ACTIVE_APPLICATION_STATUSES)))
        if assigned: raise HTTPException(409,'Нельзя менять бригаду у монтажника с активными заявками')
    result=execute_returning('update installers set full_name=%s,phone=%s,id_brigade=%s where id_installer=%s returning *',(payload.full_name,payload.phone,payload.id_brigade,installer_id))
    if not result: raise HTTPException(404,'Монтажник не найден')
    return result

@app.delete('/installers/{installer_id}')
def delete_installer(installer_id: int):
    try:
        result=execute_returning('delete from installers where id_installer=%s returning id_installer',(installer_id,))
    except psycopg2.errors.ForeignKeyViolation:
        raise HTTPException(409, 'Монтажник назначен в заявке и не может быть удалён')
    if not result: raise HTTPException(404,'Монтажник не найден')
    return {'status':'deleted','id_installer':installer_id}

@app.delete('/applications/{application_id}')
def delete_application(application_id: int):
    try:
        result=execute_returning('delete from applications where id_application=%s returning id_application',(application_id,))
    except psycopg2.errors.ForeignKeyViolation:
        raise HTTPException(409, 'Заявка связана с заказом и не может быть удалена')
    if not result: raise HTTPException(404,'Заявка не найдена')
    return {'status':'deleted','id_application':application_id}

@app.delete('/orders/{order_id}')
def delete_order(order_id: int):
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('select id_order,status from orders where id_order=%s for update',(order_id,)); order=one(cur)
        if not order: raise HTTPException(404,'Заказ не найден')
        if order['status'] not in {'Новый','Ожидает оплаты','Отменён'}:
            raise HTTPException(409, 'Заказ с таким статусом нельзя удалить')
        cur.execute('select id_product,quantity from order_items where id_order=%s',(order_id,))
        for item in cur.fetchall():
            cur.execute('update products set stock_quantity=stock_quantity+%s where id_product=%s',(item['quantity'],item['id_product']))
        cur.execute('delete from orders where id_order=%s returning id_order',(order_id,)); result=one(cur)
        conn.commit()
        return {'status':'deleted','id_order':result['id_order']}

@app.delete('/products/{product_id}')
def delete_product(product_id: int):
    try: result=execute_returning('delete from products where id_product=%s returning id_product',(product_id,))
    except psycopg2.errors.ForeignKeyViolation: raise HTTPException(409,'Товар есть в заказах и не может быть удалён')
    if not result: raise HTTPException(404,'Товар не найден')
    return {'status':'deleted','id_product':product_id}

@app.patch('/orders/{order_id}/delivery')
def update_delivery(order_id: int, payload: DeliveryUpdateIn):
    if payload.status is not None and payload.status not in DELIVERY_STATUSES: raise HTTPException(400,'Недопустимый статус доставки')
    if payload.delivery_method is not None and payload.delivery_method not in DELIVERY_METHODS: raise HTTPException(400,'Недопустимый способ доставки')
    if payload.delivery_method == 'delivery' and not payload.address: raise HTTPException(400,'Для доставки нужен адрес')
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('''update deliveries set delivery_method=coalesce(%s,delivery_method),address=coalesce(%s,address),
                       delivery_date=coalesce(%s,delivery_date),status=coalesce(%s,status)
                       where id_order=%s returning *''',(payload.delivery_method,payload.address,payload.delivery_date,payload.status,order_id)); result=one(cur)
        if not result: raise HTTPException(404,'Доставка для заказа не найдена')
        if payload.status in {'Передан','Доставлен'}:
            cur.execute("update orders set status='Завершён' where id_order=%s and status not in ('Отменён','Завершён')",(order_id,))
        elif payload.status == 'Передан в доставку':
            cur.execute("update orders set status='Передан в доставку' where id_order=%s and status not in ('Отменён','Завершён')",(order_id,))
        conn.commit(); return result

@app.patch('/payments/{payment_id}/status')
def update_payment(payment_id: int, payload: PaymentStatusIn):
    if payload.status not in PAYMENT_STATUSES: raise HTTPException(400,'Недопустимый статус платежа')
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('''update payments set status=%s,
                       paid_at=case when %s=%s then coalesce(paid_at,current_timestamp) else null end,
                       payment_date=case when %s=%s then coalesce(payment_date,current_timestamp) else payment_date end
                       where id_payment=%s returning *''',(payload.status,payload.status,'Оплачен',payload.status,'Оплачен',payment_id)); result=one(cur)
        if not result: raise HTTPException(404,'Платёж не найден')
        if payload.status == 'Оплачен': cur.execute("update orders set status='Оплачен' where id_order=%s and status not in ('Завершён','Отменён')",(result['id_order'],))
        elif payload.status in {'Ожидает оплаты','Ошибка'}:
            cur.execute("update orders set status='Ожидает оплаты' where id_order=%s and status='Оплачен'",(result['id_order'],))
        conn.commit(); return result
