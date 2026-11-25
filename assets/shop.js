document.addEventListener("DOMContentLoaded", async () => {
  const grid = document.querySelector(".product-grid");
  if (!grid) return;

  const cards = [...grid.querySelectorAll("[data-product]")];
  const search = document.querySelector("#productSearch");
  const category = document.querySelector("#categoryFilter");
  const sort = document.querySelector("#sortFilter");
  const noProducts = document.querySelector("#noProducts");

  async function syncCatalog() {
    try {
      const response = await fetch(`${API_BASE}/products/`);
      if (!response.ok) return;
      const products = await response.json();
      const byId = new Map(products.map(product => [Number(product.id_product), product]));
      cards.forEach(card => {
        const product = byId.get(PRODUCT_IDS[card.dataset.id]);
        if (!product) return;
        card.dataset.name = product.name;
        card.dataset.price = product.price;
        if (product.image) card.dataset.image = product.image;
        const title = card.querySelector("h3");
        const description = card.querySelector(".product-info p");
        const price = card.querySelector(".product-price");
        const image = card.querySelector("img");
        const addButton = card.querySelector("[data-add-product]");
        if (title) title.textContent = product.name;
        if (description && product.description) description.textContent = product.description;
        if (price) price.textContent = money(product.price);
        if (image && product.image) {
          image.src = product.image;
          image.alt = product.name;
        }
        if (addButton) {
          addButton.disabled = Number(product.stock_quantity) <= 0;
          addButton.textContent = Number(product.stock_quantity) > 0 ? "В корзину" : "Нет в наличии";
        }
      });
    } catch {
      // Статические карточки остаются доступными при временной недоступности API.
    }
  }

  function apply() {
    const query = search.value.trim().toLowerCase();
    const selectedCategory = category.value;

    let visible = cards.filter(card => {
      const matchesSearch =
        card.dataset.name.toLowerCase().includes(query) ||
        card.dataset.category.toLowerCase().includes(query);
      const matchesCategory =
        selectedCategory === "all" || card.dataset.category === selectedCategory;
      return matchesSearch && matchesCategory;
    });

    visible.sort((a, b) => {
      if (sort.value === "asc") return Number(a.dataset.price) - Number(b.dataset.price);
      if (sort.value === "desc") return Number(b.dataset.price) - Number(a.dataset.price);
      return 0;
    });

    cards.forEach(card => {
      card.hidden = !visible.includes(card);
    });

    visible.forEach(card => {
      grid.append(card);
    });

    noProducts.hidden = visible.length > 0;
  }

  [search, category, sort].forEach(el => {
    el.addEventListener("input", apply);
  });

  await syncCatalog();
  apply();
});
