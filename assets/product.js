document.addEventListener("DOMContentLoaded", async () => {
  const catalog = {
    "spot-01": {
      name: "Светильник встраиваемый Luma",
      price: 590,
      category: "Светильники",
      image: "photo/1.jpg",
      desc: "Компактный встраиваемый светильник для аккуратного потолочного освещения.",
      spec: [
        ["Тип", "Встраиваемый"],
        ["Назначение", "Потолочное освещение"],
        ["Цвет света", "Зависит от выбранной лампы"]
      ]
    },
    "spot-02": {
      name: "Светильник накладной Forma",
      price: 890,
      category: "Светильники",
      image: "photo/2.avif",
      desc: "Накладной светильник с лаконичным дизайном для современных интерьеров.",
      spec: [
        ["Тип", "Накладной"],
        ["Назначение", "Общее освещение"],
        ["Стиль", "Современный"]
      ]
    },
    "spot-03": {
      name: "Светильник поворотный Spot",
      price: 750,
      category: "Светильники",
      image: "photo/3.webp",
      desc: "Поворотный светильник для направленного акцентного света.",
      spec: [
        ["Тип", "Поворотный"],
        ["Назначение", "Акцентное освещение"],
        ["Монтаж", "Встраиваемый"]
      ]
    },
    "lustre-01": {
      name: "Люстра подвесная Ring",
      price: 4900,
      category: "Люстры",
      image: "photo/4.jpeg",
      desc: "Круглая подвесная люстра с мягким рассеянным светом.",
      spec: [
        ["Тип", "Подвесная"],
        ["Форма", "Круглая"],
        ["Стиль", "Современный"]
      ]
    },
    "lustre-02": {
      name: "Люстра каскадная Cascade",
      price: 6500,
      category: "Люстры",
      image: "photo/5.jpg",
      desc: "Каскадная люстра с несколькими уровнями подвесов.",
      spec: [
        ["Тип", "Каскадная"],
        ["Уровни", "Несколько"],
        ["Стиль", "Декоративный"]
      ]
    },
    "lustre-03": {
      name: "Люстра минималистичная Line",
      price: 5200,
      category: "Люстры",
      image: "photo/6.webp",
      desc: "Линейная люстра для лаконичных современных интерьеров.",
      spec: [
        ["Тип", "Линейная"],
        ["Стиль", "Минимализм"],
        ["Назначение", "Общее освещение"]
      ]
    },
    "track-01": {
      name: "Трековый модуль Line",
      price: 2490,
      category: "Трековое освещение",
      image: "photo/7.webp",
      desc: "Модуль для организации направленного света и акцентного освещения.",
      spec: [
        ["Тип", "Трековый модуль"],
        ["Назначение", "Акцентное освещение"],
        ["Монтаж", "На совместимую трековую систему"]
      ]
    },
    "track-02": {
      name: "Трековая система 1 м",
      price: 1890,
      category: "Трековое освещение",
      image: "photo/8.webp",
      desc: "Базовый трек длиной 1 м для монтажа модулей освещения.",
      spec: [
        ["Длина", "1 м"],
        ["Тип", "Базовый трек"],
        ["Монтаж", "Потолочный"]
      ]
    },
    "led-01": {
      name: "LED-лента Warm 5 м",
      price: 1250,
      category: "LED-ленты",
      image: "photo/9.webp",
      desc: "Светодиодная лента для декоративной подсветки ниш, карнизов и потолочных конструкций.",
      spec: [
        ["Длина", "5 м"],
        ["Оттенок", "Тёплый"],
        ["Назначение", "Декоративная подсветка"]
      ]
    },
    "led-02": {
      name: "LED-лента Neutral 5 м",
      price: 1390,
      category: "LED-ленты",
      image: "photo/10.webp",
      desc: "Лента нейтрального оттенка для дополнительного освещения помещения.",
      spec: [
        ["Длина", "5 м"],
        ["Оттенок", "Нейтральный"],
        ["Назначение", "Подсветка"]
      ]
    },
    "line-01": {
      name: "Световая линия Profile 1 м",
      price: 3200,
      category: "Световые линии",
      image: "photo/11.png",
      desc: "Готовая световая линия в профиле для ровного потолочного света.",
      spec: [
        ["Длина", "1 м"],
        ["Тип", "Профильная"],
        ["Назначение", "Основное освещение"]
      ]
    },
    "line-02": {
      name: "Световая линия Duo 1 м",
      price: 3900,
      category: "Световые линии",
      image: "photo/12.webp",
      desc: "Двойная световая линия для выразительного акцентного освещения.",
      spec: [
        ["Длина", "1 м"],
        ["Тип", "Двойная"],
        ["Назначение", "Акцентное освещение"]
      ]
    }
  };

  const id = new URLSearchParams(location.search).get("id") || "spot-01";
  let product = catalog[id];
  const root = document.querySelector("#productDetail");

  if (!product) {
    root.innerHTML = `
      <div class="empty-state">
        <h3>Товар не найден</h3>
        <a class="btn btn-dark" href="shop.html">Вернуться в магазин</a>
      </div>
    `;
    return;
  }

  try {
    const response = await fetch(`${API_BASE}/products/`);
    if (response.ok) {
      const liveProduct = (await response.json()).find(item => Number(item.id_product) === PRODUCT_IDS[id]);
      if (liveProduct) {
        product = {...product, name: liveProduct.name, price: Number(liveProduct.price), image: liveProduct.image || product.image, desc: liveProduct.description || product.desc, stock: Number(liveProduct.stock_quantity)};
      }
    }
  } catch {
    // При недоступности API карточка использует сохранённые данные каталога.
  }

  root.innerHTML = `
    <img src="${escapeHTML(product.image || "")}" alt="${escapeHTML(product.name)}">
    <div>
      <div class="kicker">${escapeHTML(product.category)}</div>
      <h1>${escapeHTML(product.name)}</h1>
      <p>${escapeHTML(product.desc)}</p>
      <div class="product-price">
        ${new Intl.NumberFormat("ru-RU").format(product.price)} ₽
      </div>
      <div class="spec-list">
        ${product.spec.map(([label, value]) => `
          <div>
          <span class="muted">${escapeHTML(label)}</span>
          <b>${escapeHTML(value)}</b>
          </div>
        `).join("")}
      </div>
      <div class="quantity">
        <button id="minus">−</button>
        <input id="qty" type="number" min="1" max="99" value="1">
        <button id="plus">+</button>
      </div>
      <button class="btn btn-accent" id="add" ${product.stock === 0 ? "disabled" : ""}>${product.stock === 0 ? "Нет в наличии" : "Добавить в корзину ↗"}</button>
      <p class="muted" style="margin-top:18px">
        Товар можно приобрести отдельно от услуги установки потолка.
      </p>
    </div>
  `;

  const qty = root.querySelector("#qty");

  root.querySelector("#minus").onclick = () => {
    qty.value = Math.max(1, +qty.value - 1);
  };

  root.querySelector("#plus").onclick = () => {
    qty.value = Math.min(99, +qty.value + 1);
  };

  root.querySelector("#add").onclick = () => {
    addToCart(
      {
        id,
        productId: PRODUCT_IDS[id] || id,
        name: product.name,
        price: product.price,
        image: product.image
      },
      Math.max(1, Math.min(99, +qty.value || 1))
    );
  };
});
