import psycopg2
from config import DB_NAME, DB_PARAMS
c=psycopg2.connect(dbname=DB_NAME, **DB_PARAMS); c.autocommit=True
cur=c.cursor(); cur.execute('ALTER TABLE products ADD COLUMN IF NOT EXISTS image VARCHAR(255)')
services=[('Монтаж натяжного потолка','Монтаж потолочной конструкции',5000),('Слив воды','Слив воды после затопления',2500),('Демонтаж старого потолка','Демонтаж существующей конструкции',3000),('Ремонт и вставка полотна','Ремонт и замена полотна',3500)]
for x in services: cur.execute('insert into services(name,description,base_price) values (%s,%s,%s) on conflict do nothing',x)
products=[('Светильник встраиваемый Luma','Встраиваемый светильник',590, 'photo/1.jpg'),('Светильник накладной Forma','Накладной светильник',890,'photo/2.avif'),('Светильник поворотный Spot','Поворотный светильник',750,'photo/3.webp'),('Люстра подвесная Ring','Подвесная люстра',4900,'photo/4.jpeg'),('Люстра каскадная Cascade','Каскадная люстра',6500,'photo/5.jpg'),('Люстра минималистичная Line','Минималистичная люстра',5200,'photo/6.webp'),('Трековый модуль Line','Трековый модуль',2490,'photo/7.webp'),('Трековая система 1 м','Трековая система',1890,'photo/8.webp'),('LED-лента Warm 5 м','LED-лента',1250,'photo/9.webp'),('LED-лента Neutral 5 м','LED-лента',1390,'photo/10.webp'),('Световая линия Profile 1 м','Световая линия',3200,'photo/11.png'),('Световая линия Duo 1 м','Световая линия',3900,'photo/12.webp')]
for x in products: cur.execute('insert into products(name,description,price,stock_quantity,image) values (%s,%s,%s,100,%s) on conflict do nothing',x)
c.close(); print('seeded')
